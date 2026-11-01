# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Showdown Regulation M-C Battle Log Parser (engine/tactics/showdown_parser.py)

Deterministically reconstructs turn-by-turn board states from either human-readable
Showdown replay logs or pipe-delimited Showdown protocol streams (|turn|, |switch|,
|move|, |-damage|, |faint|, |-mega|, |-weather|, |-fieldstart|).
Directly grounded in engine/turn_simulator.py (BASE_STATS_DB, MOVE_DB, and
calculate_level_50_stats) to produce states compatible with ClientReplaySimulator.
"""

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Dict, List, Optional

from engine.turn_simulator import (
    BASE_STATS_DB,
    PROTECT_MOVES,
    calculate_level_50_stats,
)


@dataclass
class SlotState:
    """Represents the exact state of a single active Pokemon slot."""

    species: str
    hp_pct: float = 1.0
    is_mega: bool = False
    status: str = "None"
    fainted: bool = False
    speed_tier: float = 100.0
    item: str = ""
    ability: str = ""
    boosts: Dict[str, int] = field(
        default_factory=lambda: {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    )

    def clone(self) -> "SlotState":
        """Return a deep copy of this slot state."""
        return SlotState(
            species=self.species,
            hp_pct=round(self.hp_pct, 4),
            is_mega=self.is_mega,
            status=self.status,
            fainted=self.fainted,
            speed_tier=self.speed_tier,
            item=self.item,
            ability=self.ability,
            boosts=dict(self.boosts),
        )


@dataclass
class TurnAction:
    """Represents a move or switch action executed during a turn."""

    actor_side: str
    pokemon: str
    move: str
    target: str = ""
    is_protect: bool = False
    blocked_by_protect: bool = False
    is_redirection: bool = False


@dataclass
class TurnSnapshot:
    """Complete deterministic board snapshot at a specific turn."""

    turn_number: int
    p1_slots: List[SlotState] = field(default_factory=list)
    p2_slots: List[SlotState] = field(default_factory=list)
    p1_bench_alive: int = 2
    p2_bench_alive: int = 2
    p1_mega_used: bool = False
    p2_mega_used: bool = False
    weather: str = "Clear"
    weather_turns: int = 0
    terrain: str = "None"
    terrain_turns: int = 0
    actions: List[TurnAction] = field(default_factory=list)
    hp_deltas: Dict[str, float] = field(default_factory=dict)
    kos: List[str] = field(default_factory=list)
    mega_evolutions: List[str] = field(default_factory=list)
    weather_changed: bool = False
    terrain_changed: bool = False
    redirection_active: bool = False
    protect_absorptions: int = 0


@dataclass
class BattleHistory:
    """Structured multi-turn history reconstructed from a Showdown battle log."""

    match_id: str
    p1_name: str
    p2_name: str
    p1_team: List[str] = field(default_factory=list)
    p2_team: List[str] = field(default_factory=list)
    winner: str = ""
    turns: List[TurnSnapshot] = field(default_factory=list)


class ShowdownParser:
    """
    Deterministic parser for Pokemon Showdown Regulation M-C logs.

    Grounded in engine/turn_simulator.py to resolve Level 50 stats, typings,
    abilities, and instantaneous Mega Evolution speed scaling. Can export any
    TurnSnapshot directly into a ClientReplaySimulator state dictionary.
    """

    def parse(self, raw_log: str) -> BattleHistory:
        """
        Parse a raw Showdown log string into a structured BattleHistory.

        Args:
            raw_log: Raw plain-text or pipe-delimited Showdown battle log.

        Returns:
            BattleHistory containing metadata and ordered TurnSnapshots.

        Raises:
            ValueError: If raw_log is empty or contains no recognizable turns.
        """
        if not raw_log or not raw_log.strip():
            raise ValueError("Cannot parse empty Showdown battle log.")

        digest = hashlib.sha256(raw_log.encode("utf-8")).hexdigest()[:8].upper()
        match_id = f"MC-{digest}"

        if "|turn|" in raw_log:
            return self._parse_pipe_protocol(raw_log, match_id)
        return self._parse_text_protocol(raw_log, match_id)

    def _canonical_species(self, raw_name: str) -> str:
        """Normalize species strings by stripping nicknames and parentheses."""
        cleaned = raw_name.strip().rstrip("!")
        if "(" in cleaned and cleaned.endswith(")"):
            inner = cleaned.split("(")[-1].rstrip(")").strip()
            if inner:
                return inner
        if cleaned == "Floette":
            return "Floette-Eternal"
        return cleaned

    def _resolve_mega_species(self, species: str) -> str:
        """Resolve canonical Mega species entry in turn_simulator.BASE_STATS_DB."""
        candidates = [
            f"Mega {species} Y",
            f"Mega {species}",
            f"{species}-Mega-Y",
            f"{species}-Mega",
            "Floette-Mega" if "Floette" in species else "",
            "Charizard-Mega-Y" if "Charizard" in species else "",
        ]
        for cand in candidates:
            if cand and cand in BASE_STATS_DB:
                return cand
        return species

    def _lookup_speed(self, species: str, is_mega: bool = False) -> float:
        """Compute Level 50 Speed stat using turn_simulator.calculate_level_50_stats."""
        target_sp = self._resolve_mega_species(species) if is_mega else species
        if target_sp in BASE_STATS_DB:
            return float(BASE_STATS_DB[target_sp]["spe"])
        if is_mega and "Floette" in species:
            return 112.0
        if is_mega and "Charizard" in species:
            return 100.0
        _, stats = calculate_level_50_stats(target_sp, {}, "Hardy")
        return float(stats.get("spe", 80))

    def to_simulator_state(self, snapshot: TurnSnapshot) -> Dict[str, Any]:
        """
        Convert a TurnSnapshot into the exact state_dict schema for ClientReplaySimulator.

        Args:
            snapshot: Parsed TurnSnapshot from a Showdown battle log.

        Returns:
            Dictionary ready to pass into ClientReplaySimulator(state_dict, choices_dict).
        """
        weather_norm = None
        if snapshot.weather and snapshot.weather.lower() not in ("clear", "none"):
            w_low = snapshot.weather.lower()
            weather_norm = "sun" if "sun" in w_low else w_low

        terrain_norm = None
        if snapshot.terrain and snapshot.terrain.lower() not in ("none", "clear"):
            terrain_norm = snapshot.terrain.lower()

        slots_dict: Dict[str, Any] = {}
        for side_prefix, slot_list in (("p1", snapshot.p1_slots), ("p2", snapshot.p2_slots)):
            for idx, s in enumerate(slot_list[:2]):
                slot_id = f"{side_prefix}{'a' if idx == 0 else 'b'}"
                sim_species = self._resolve_mega_species(s.species) if s.is_mega else s.species
                max_hp, stats = calculate_level_50_stats(
                    sim_species, {"atk": 16, "spa": 16, "spe": 16, "hp": 18}, "Hardy"
                )
                db_entry = BASE_STATS_DB.get(sim_species, {})
                types = list(db_entry.get("types", ["Normal"]))
                default_ab = db_entry.get("abilities", {}).get("0", "Pressure")
                slots_dict[slot_id] = {
                    "slot_id": slot_id,
                    "species": sim_species,
                    "name": s.species,
                    "types": types,
                    "ability": s.ability or default_ab,
                    "item": s.item,
                    "status": None if s.status == "None" else s.status,
                    "current_hp_pct": round(s.hp_pct * 100.0, 1),
                    "max_hp": max_hp,
                    "stats": stats,
                    "boosts": dict(s.boosts),
                }

        return {
            "turn": snapshot.turn_number,
            "field": {
                "weather": weather_norm,
                "weather_turns": snapshot.weather_turns,
                "terrain": terrain_norm,
                "terrain_turns": snapshot.terrain_turns,
                "trick_room_turns": 0,
            },
            "p1": {"player": "p1", "tailwind_turns": 0, "reflect_turns": 0},
            "p2": {"player": "p2", "tailwind_turns": 0, "reflect_turns": 0},
            "slots": slots_dict,
        }

    def _parse_text_protocol(self, raw_log: str, match_id: str) -> BattleHistory:
        """Parse human-readable Showdown replay text into BattleHistory."""
        lines = [line.strip() for line in raw_log.splitlines() if line.strip()]

        p1_name = "aws_secret"
        p2_name = "Opponent"
        p1_team: List[str] = []
        p2_team: List[str] = []
        winner = ""

        for idx, line in enumerate(lines):
            battle_match = re.match(r"^Battle started between (.+) and (.+)!$", line)
            if battle_match:
                p1_name = battle_match.group(1).strip()
                p2_name = battle_match.group(2).strip()
            if line.endswith("'s team:") and idx + 1 < len(lines):
                owner = line.replace("'s team:", "").strip()
                roster = [s.strip() for s in lines[idx + 1].split("/") if s.strip()]
                if owner == p1_name or not p1_team:
                    p1_team = roster
                else:
                    p2_team = roster
            win_match = re.match(r"^(.+) won the battle!$", line)
            if win_match:
                winner = win_match.group(1).strip()

        p1_active: List[SlotState] = []
        p2_active: List[SlotState] = []
        p1_hp_map: Dict[str, float] = {}
        p2_hp_map: Dict[str, float] = {}
        p1_mega_map: Dict[str, bool] = {}
        p2_mega_map: Dict[str, bool] = {}
        p1_fainted_set = set()
        p2_fainted_set = set()

        p1_mega_used = False
        p2_mega_used = False
        weather = "Clear"
        weather_turns = 0
        terrain = "None"
        terrain_turns = 0

        turns: List[TurnSnapshot] = []
        current_turn: Optional[TurnSnapshot] = None
        last_action: Optional[TurnAction] = None

        def _update_slot_list(side: str, mon_name: str) -> None:
            """Insert or update an active slot entry for the specified player side."""
            canon = self._canonical_species(mon_name)
            hp_map = p1_hp_map if side == "p1" else p2_hp_map
            mega_map = p1_mega_map if side == "p1" else p2_mega_map
            active_list = p1_active if side == "p1" else p2_active

            if canon not in hp_map:
                hp_map[canon] = 1.0
            is_m = mega_map.get(canon, False)
            slot_obj = SlotState(
                species=canon,
                hp_pct=hp_map[canon],
                is_mega=is_m,
                fainted=(hp_map[canon] <= 0.0),
                speed_tier=self._lookup_speed(canon, is_m),
            )
            existing_idx = next(
                (i for i, s in enumerate(active_list) if s.species == canon), None
            )
            if existing_idx is not None:
                active_list[existing_idx] = slot_obj
            elif len(active_list) < 2:
                active_list.append(slot_obj)
            else:
                fainted_idx = next(
                    (i for i, s in enumerate(active_list) if s.fainted or s.hp_pct <= 0.0),
                    0,
                )
                active_list[fainted_idx] = slot_obj

        all_protect_names = set(PROTECT_MOVES) | {"Quick Guard", "Wide Guard"}

        for line in lines:
            turn_match = re.match(r"^Turn (\d+)$", line)
            if turn_match:
                if current_turn is not None:
                    self._finalize_turn_snapshot(
                        current_turn,
                        p1_active,
                        p2_active,
                        p1_fainted_set,
                        p2_fainted_set,
                    )
                    turns.append(current_turn)

                t_num = int(turn_match.group(1))
                if weather_turns > 0:
                    weather_turns -= 1
                    if weather_turns == 0:
                        weather = "Clear"
                if terrain_turns > 0:
                    terrain_turns -= 1
                    if terrain_turns == 0:
                        terrain = "None"

                current_turn = TurnSnapshot(
                    turn_number=t_num,
                    p1_slots=[s.clone() for s in p1_active],
                    p2_slots=[s.clone() for s in p2_active],
                    p1_bench_alive=max(0, 4 - len(p1_fainted_set) - len(p1_active)),
                    p2_bench_alive=max(0, 4 - len(p2_fainted_set) - len(p2_active)),
                    p1_mega_used=p1_mega_used,
                    p2_mega_used=p2_mega_used,
                    weather=weather,
                    weather_turns=weather_turns,
                    terrain=terrain,
                    terrain_turns=terrain_turns,
                )
                last_action = None
                continue

            if line.startswith("Go! "):
                mon = line.replace("Go! ", "").rstrip("!")
                _update_slot_list("p1", mon)
                continue

            opp_sent = re.match(r"^.+ sent out (.+)!$", line)
            if opp_sent:
                mon = opp_sent.group(1)
                _update_slot_list("p2", mon)
                continue

            withdrew_match = re.match(r"^(.+) withdrew (.+)!$", line)
            if withdrew_match:
                trainer = withdrew_match.group(1).strip()
                mon = self._canonical_species(withdrew_match.group(2))
                side = "p1" if trainer == p1_name else "p2"
                active_list = p1_active if side == "p1" else p2_active
                active_list[:] = [s for s in active_list if s.species != mon]
                if current_turn is not None:
                    act = TurnAction(actor_side=side, pokemon=mon, move="Switch")
                    current_turn.actions.append(act)
                continue

            mega_match = re.match(
                r"^(The opposing )?(.+) has Mega Evolved into (.+)!$", line
            )
            if mega_match:
                is_opp = bool(mega_match.group(1))
                base_mon = self._canonical_species(mega_match.group(2))
                if is_opp:
                    p2_mega_used = True
                    p2_mega_map[base_mon] = True
                    for s in p2_active:
                        if s.species == base_mon:
                            s.is_mega = True
                            s.speed_tier = self._lookup_speed(base_mon, True)
                    if current_turn is not None:
                        current_turn.p2_mega_used = True
                        current_turn.mega_evolutions.append(f"p2:{base_mon}")
                else:
                    p1_mega_used = True
                    p1_mega_map[base_mon] = True
                    for s in p1_active:
                        if s.species == base_mon:
                            s.is_mega = True
                            s.speed_tier = self._lookup_speed(base_mon, True)
                    if current_turn is not None:
                        current_turn.p1_mega_used = True
                        current_turn.mega_evolutions.append(f"p1:{base_mon}")
                continue

            if "The sunlight turned harsh!" in line:
                weather = "Sun"
                weather_turns = 5
                if current_turn is not None:
                    current_turn.weather = "Sun"
                    current_turn.weather_turns = 5
                    current_turn.weather_changed = True
                continue

            if "Psychic Terrain" in line or "weirdness rose" in line:
                terrain = "Psychic"
                terrain_turns = 5
                if current_turn is not None:
                    current_turn.terrain = "Psychic"
                    current_turn.terrain_turns = 5
                    current_turn.terrain_changed = True
                continue

            move_match = re.match(r"^(The opposing )?(.+) used (.+)!$", line)
            if move_match and current_turn is not None:
                is_opp = bool(move_match.group(1))
                actor = self._canonical_species(move_match.group(2))
                move_name = move_match.group(3).strip()
                side = "p2" if is_opp else "p1"
                is_prot = move_name in all_protect_names
                is_redir = move_name in ("Rage Powder", "Follow Me")
                if is_redir:
                    current_turn.redirection_active = True
                last_action = TurnAction(
                    actor_side=side,
                    pokemon=actor,
                    move=move_name,
                    is_protect=is_prot,
                    is_redirection=is_redir,
                )
                current_turn.actions.append(last_action)
                continue

            prot_match = re.match(r"^(The opposing )?(.+) protected itself!$", line)
            if prot_match and current_turn is not None and last_action is not None:
                if not last_action.is_protect:
                    last_action.blocked_by_protect = True
                    current_turn.protect_absorptions += 1
                continue

            dmg_match = re.match(
                r"^\((The opposing )?(.+) lost ([\d\.]+)% of its health!\)$", line
            )
            if dmg_match and current_turn is not None:
                is_opp = bool(dmg_match.group(1))
                victim = self._canonical_species(dmg_match.group(2))
                pct = float(dmg_match.group(3)) / 100.0
                key = f"{'p2' if is_opp else 'p1'}:{victim}"
                current_turn.hp_deltas[key] = round(
                    current_turn.hp_deltas.get(key, 0.0) + pct, 4
                )

                hp_map = p2_hp_map if is_opp else p1_hp_map
                active_list = p2_active if is_opp else p1_active
                hp_map[victim] = max(0.0, round(hp_map.get(victim, 1.0) - pct, 4))
                for s in active_list:
                    if s.species == victim:
                        s.hp_pct = hp_map[victim]
                if last_action is not None and not last_action.target:
                    last_action.target = key
                continue

            faint_match = re.match(r"^(The opposing )?(.+) fainted!$", line)
            if faint_match and current_turn is not None:
                is_opp = bool(faint_match.group(1))
                victim = self._canonical_species(faint_match.group(2))
                key = f"{'p2' if is_opp else 'p1'}:{victim}"
                current_turn.kos.append(key)
                if is_opp:
                    p2_hp_map[victim] = 0.0
                    p2_fainted_set.add(victim)
                    for s in p2_active:
                        if s.species == victim:
                            s.hp_pct = 0.0
                            s.fainted = True
                else:
                    p1_hp_map[victim] = 0.0
                    p1_fainted_set.add(victim)
                    for s in p1_active:
                        if s.species == victim:
                            s.hp_pct = 0.0
                            s.fainted = True
                continue

        if current_turn is not None:
            self._finalize_turn_snapshot(
                current_turn, p1_active, p2_active, p1_fainted_set, p2_fainted_set
            )
            turns.append(current_turn)

        if not turns:
            raise ValueError("No valid turns found in Showdown battle log.")

        return BattleHistory(
            match_id=match_id,
            p1_name=p1_name,
            p2_name=p2_name,
            p1_team=p1_team,
            p2_team=p2_team,
            winner=winner or p1_name,
            turns=turns,
        )

    def _finalize_turn_snapshot(
        self,
        snapshot: TurnSnapshot,
        p1_active: List[SlotState],
        p2_active: List[SlotState],
        p1_fainted: set,
        p2_fainted: set,
    ) -> None:
        """Update alive bench counts while preserving pre-replacement turn decision slots."""
        if not snapshot.p1_slots:
            snapshot.p1_slots = [s.clone() for s in p1_active]
        if not snapshot.p2_slots:
            snapshot.p2_slots = [s.clone() for s in p2_active]
        for s in snapshot.p1_slots:
            if f"p1:{s.species}" in snapshot.mega_evolutions:
                s.is_mega = True
                s.speed_tier = self._lookup_speed(s.species, True)
        for s in snapshot.p2_slots:
            if f"p2:{s.species}" in snapshot.mega_evolutions:
                s.is_mega = True
                s.speed_tier = self._lookup_speed(s.species, True)
        p1_alive_total = max(0, 4 - len(p1_fainted))
        p2_alive_total = max(0, 4 - len(p2_fainted))
        p1_active_alive = sum(1 for s in p1_active if not s.fainted)
        p2_active_alive = sum(1 for s in p2_active if not s.fainted)
        snapshot.p1_bench_alive = max(0, p1_alive_total - p1_active_alive)
        snapshot.p2_bench_alive = max(0, p2_alive_total - p2_active_alive)

    def _parse_pipe_protocol(self, raw_log: str, match_id: str) -> BattleHistory:
        """Parse pipe-delimited Showdown protocol stream (|turn|, |switch|, |move|, etc.)."""
        p1_name = "aws_secret"
        p2_name = "Opponent"
        winner = ""
        p1_slots: Dict[str, SlotState] = {}
        p2_slots: Dict[str, SlotState] = {}
        turns: List[TurnSnapshot] = []
        current_turn: Optional[TurnSnapshot] = None
        p1_mega_used = False
        p2_mega_used = False
        weather = "Clear"
        terrain = "None"
        all_protect_names = set(PROTECT_MOVES) | {"Quick Guard", "Wide Guard"}

        for raw_line in raw_log.splitlines():
            line = raw_line.strip()
            if not line.startswith("|"):
                continue
            parts = line.split("|")
            tag = parts[1] if len(parts) > 1 else ""

            if tag == "player" and len(parts) >= 4:
                if parts[2] == "p1" and parts[3]:
                    p1_name = parts[3]
                elif parts[2] == "p2" and parts[3]:
                    p2_name = parts[3]
            elif tag == "switch" and len(parts) >= 4:
                ident = parts[2]
                species = parts[3].split(",")[0].strip()
                slot_obj = SlotState(
                    species=species,
                    hp_pct=1.0,
                    speed_tier=self._lookup_speed(species, False),
                )
                if ident.startswith("p1"):
                    p1_slots[ident[:3]] = slot_obj
                else:
                    p2_slots[ident[:3]] = slot_obj
            elif tag == "turn" and len(parts) >= 3:
                if current_turn is not None:
                    current_turn.p1_slots = [s.clone() for s in p1_slots.values()]
                    current_turn.p2_slots = [s.clone() for s in p2_slots.values()]
                    turns.append(current_turn)
                current_turn = TurnSnapshot(
                    turn_number=int(parts[2]),
                    p1_slots=[s.clone() for s in p1_slots.values()],
                    p2_slots=[s.clone() for s in p2_slots.values()],
                    p1_mega_used=p1_mega_used,
                    p2_mega_used=p2_mega_used,
                    weather=weather,
                    terrain=terrain,
                )
            elif tag == "-mega" and current_turn is not None and len(parts) >= 4:
                ident = parts[2]
                side = "p1" if ident.startswith("p1") else "p2"
                slot_key = ident[:3]
                target_dict = p1_slots if side == "p1" else p2_slots
                if slot_key in target_dict:
                    target_dict[slot_key].is_mega = True
                    target_dict[slot_key].speed_tier = self._lookup_speed(
                        target_dict[slot_key].species, True
                    )
                if side == "p1":
                    p1_mega_used = True
                    current_turn.p1_mega_used = True
                else:
                    p2_mega_used = True
                    current_turn.p2_mega_used = True
                current_turn.mega_evolutions.append(f"{side}:{parts[3]}")
            elif tag == "move" and current_turn is not None and len(parts) >= 4:
                ident = parts[2]
                side = "p1" if ident.startswith("p1") else "p2"
                mon_name = ident.split(":")[-1].strip()
                move_name = parts[3].strip()
                target = parts[4].strip() if len(parts) >= 5 else ""
                is_prot = move_name in all_protect_names
                is_redir = move_name in ("Rage Powder", "Follow Me")
                if is_redir:
                    current_turn.redirection_active = True
                current_turn.actions.append(
                    TurnAction(
                        actor_side=side,
                        pokemon=mon_name,
                        move=move_name,
                        target=target,
                        is_protect=is_prot,
                        is_redirection=is_redir,
                    )
                )
            elif tag == "-activate" and current_turn is not None and "Protect" in line:
                current_turn.protect_absorptions += 1
                if current_turn.actions:
                    current_turn.actions[-1].blocked_by_protect = True
            elif tag == "-damage" and current_turn is not None and len(parts) >= 4:
                ident = parts[2]
                side = "p1" if ident.startswith("p1") else "p2"
                slot_key = ident[:3]
                mon_name = ident.split(":")[-1].strip()
                hp_str = parts[3].split()[0]
                new_hp = 0.0
                if "/" in hp_str:
                    num, den = hp_str.split("/")
                    new_hp = float(num) / float(den)
                target_dict = p1_slots if side == "p1" else p2_slots
                old_hp = target_dict[slot_key].hp_pct if slot_key in target_dict else 1.0
                delta = max(0.0, old_hp - new_hp)
                if slot_key in target_dict:
                    target_dict[slot_key].hp_pct = new_hp
                current_turn.hp_deltas[f"{side}:{mon_name}"] = round(delta, 4)
            elif tag == "faint" and current_turn is not None and len(parts) >= 3:
                ident = parts[2]
                side = "p1" if ident.startswith("p1") else "p2"
                slot_key = ident[:3]
                mon_name = ident.split(":")[-1].strip()
                target_dict = p1_slots if side == "p1" else p2_slots
                if slot_key in target_dict:
                    target_dict[slot_key].hp_pct = 0.0
                    target_dict[slot_key].fainted = True
                current_turn.kos.append(f"{side}:{mon_name}")
            elif tag == "-weather" and current_turn is not None and len(parts) >= 3:
                weather = parts[2]
                current_turn.weather = weather
                current_turn.weather_changed = True
            elif tag == "-fieldstart" and current_turn is not None and len(parts) >= 3:
                terrain = parts[2]
                current_turn.terrain = terrain
                current_turn.terrain_changed = True
            elif tag == "win" and len(parts) >= 3:
                winner = parts[2].strip()

        if current_turn is not None:
            current_turn.p1_slots = [s.clone() for s in p1_slots.values()]
            current_turn.p2_slots = [s.clone() for s in p2_slots.values()]
            turns.append(current_turn)

        return BattleHistory(
            match_id=match_id,
            p1_name=p1_name,
            p2_name=p2_name,
            winner=winner or p1_name,
            turns=turns,
        )
