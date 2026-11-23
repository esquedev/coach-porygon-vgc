# -*- coding: utf-8 -*-
"""Coach Porygon VGC — Esports Turn Telemetry Extractor & CSV Logger.

Ingests raw Pokémon Showdown chat logs, extracts turn-by-turn state transitions,
damage dealt/taken, variance events (crits, flinches, misses), active slots,
and writes structured records to CSV with an open `comment` column for coach analysis.
Strictly adheres to `trainer_1` (POV) and `trainer_2` (Opponent) identifiers.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.parser.showdown_parser import (
    _load_duckdb_parser_catalogs,
    parse_showdown_chat_log,
)


@dataclass
class TurnTelemetryRecord:
    """Telemetry record for a single battle turn."""

    match_id: str
    timestamp: str
    turn: int
    trainer_1: str
    trainer_2: str
    trainer_1_active_1: str
    trainer_1_active_2: str
    trainer_2_active_1: str
    trainer_2_active_2: str
    trainer_1_moves: str
    trainer_2_moves: str
    damage_dealt_to_trainer_2: float
    damage_dealt_to_trainer_1: float
    faints_this_turn: str
    variance_events: str
    weather: str
    terrain: str
    field_conditions: str
    winner: str
    comment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for CSV writing."""
        return asdict(self)


def _generate_match_id(raw_log: str) -> str:
    """Generate a canonical `match-<12-hex>` SHA-256 fingerprint from the battle log.

    Always hashes the normalized battle log rather than scraping URLs such as
    ``Next: [Game 2 of 3](.../battle-...)``, which would otherwise mislabel the
    current game with the next game's Showdown room slug.

    Parameters:
        raw_log: Raw Pokémon Showdown battle log text.

    Returns:
        Deterministic 12-character hex match identifier prefixed with ``match-``.
    """
    cleaned = re.sub(r"\s+", "", raw_log)
    h = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]
    return f"match-{h}"


def _parse_nick_and_species(raw_mon: str) -> Tuple[str, str]:
    """Extract `(nickname, species)` from Showdown strings like `'Hazard (Charizard)'`."""
    cleaned = raw_mon.strip()
    m = re.match(r"^(.+?)\s*\((.+?)\)$", cleaned)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return cleaned, cleaned


def _base_species_key(species: str) -> str:
    """Return lowercase base species stripped of Mega and gender suffixes."""
    base = species.split("-Mega")[0].strip()
    base = re.sub(r"-[MF]$", "", base)
    return base.lower()


def extract_turn_telemetry(
    raw_log: str,
    pov_trainer: Optional[str] = None,
    user_team_paste: Optional[str] = None,
) -> List[TurnTelemetryRecord]:
    """Parse a raw Showdown log and extract turn-by-turn telemetry records.

    Parameters:
        raw_log: Raw Pokémon Showdown battle chat log text.
        pov_trainer: Username of the POV trainer (trainer_1). If omitted, inferred.
        user_team_paste: Optional team paste for the POV trainer.

    Returns:
        List of TurnTelemetryRecord instances, one for each turn played.
    """
    battle = parse_showdown_chat_log(
        raw_log,
        pov_trainer=pov_trainer,
        user_team_paste=user_team_paste,
    )
    stone_to_mega, base_to_mega, _, _ = _load_duckdb_parser_catalogs()

    match_id = _generate_match_id(raw_log)
    iso_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    trainer_1_name = battle.trainer_1.trainer_name or "trainer_1"
    trainer_2_name = battle.trainer_2.trainer_name or "trainer_2"
    winner_name = battle.winner or "Ongoing"

    lines = [line.strip() for line in raw_log.splitlines() if line.strip()]

    # 2-Slot Active State Machine per side (TEL-02, TEL-03)
    t1_slots: List[str] = ["", ""]
    t2_slots: List[str] = ["", ""]
    t1_open_queue: List[int] = []
    t2_open_queue: List[int] = []
    t1_aliases: Dict[str, int] = {}
    t2_aliases: Dict[str, int] = {}
    t1_nick_to_spec: Dict[str, str] = {}
    t2_nick_to_spec: Dict[str, str] = {}
    t1_pending_stone: Dict[str, str] = {}
    t2_pending_stone: Dict[str, str] = {}

    for sp_key, pkm_obj in battle.trainer_1.pokemon_sets.items():
        t1_nick_to_spec[sp_key.lower()] = pkm_obj.species
        if pkm_obj.nickname:
            t1_nick_to_spec[pkm_obj.nickname.lower()] = pkm_obj.species
        if pkm_obj.mega_stone:
            t1_pending_stone[sp_key.lower()] = pkm_obj.mega_stone
            if pkm_obj.nickname:
                t1_pending_stone[pkm_obj.nickname.lower()] = pkm_obj.mega_stone

    for sp_key, pkm_obj in battle.trainer_2.pokemon_sets.items():
        t2_nick_to_spec[sp_key.lower()] = pkm_obj.species
        if pkm_obj.nickname:
            t2_nick_to_spec[pkm_obj.nickname.lower()] = pkm_obj.species
        if pkm_obj.mega_stone:
            t2_pending_stone[sp_key.lower()] = pkm_obj.mega_stone
            if pkm_obj.nickname:
                t2_pending_stone[pkm_obj.nickname.lower()] = pkm_obj.mega_stone

    def _register_slot_aliases(
        idx: int,
        nick: str,
        spec: str,
        aliases: Dict[str, int],
        nick_to_spec: Dict[str, str],
    ) -> None:
        nick_to_spec[nick.lower()] = spec
        nick_to_spec[spec.lower()] = spec
        aliases[nick.lower()] = idx
        aliases[spec.lower()] = idx
        aliases[spec.split("-Mega")[0].lower()] = idx
        aliases[_base_species_key(spec)] = idx

    def _find_slot_index(
        ident: str,
        slots: List[str],
        aliases: Dict[str, int],
        nick_to_spec: Dict[str, str],
    ) -> Optional[int]:
        nick, spec = _parse_nick_and_species(ident)
        candidates = [
            ident.strip().lower(),
            nick.lower(),
            spec.lower(),
            spec.split("-Mega")[0].lower(),
            _base_species_key(spec),
        ]
        if nick.lower() in nick_to_spec:
            mapped_sp = nick_to_spec[nick.lower()]
            candidates.extend([
                mapped_sp.lower(),
                mapped_sp.split("-Mega")[0].lower(),
                _base_species_key(mapped_sp),
            ])
        for cand in candidates:
            if cand in aliases:
                idx = aliases[cand]
                if 0 <= idx < 2 and slots[idx]:
                    # Verify slot still holds this family or alias
                    cur = slots[idx]
                    if (
                        cur.lower() == cand
                        or cur.split("-Mega")[0].lower() == cand
                        or _base_species_key(cur) == cand
                        or aliases.get(nick.lower()) == idx
                    ):
                        return idx
        for idx in (0, 1):
            cur = slots[idx]
            if not cur:
                continue
            if (
                cur.lower() in candidates
                or cur.split("-Mega")[0].lower() in candidates
                or _base_species_key(cur) in candidates
            ):
                return idx
        return None

    def _vacate_slot(
        ident: str,
        slots: List[str],
        open_queue: List[int],
        aliases: Dict[str, int],
        nick_to_spec: Dict[str, str],
        clear_immediately: bool = False,
    ) -> Optional[int]:
        idx = _find_slot_index(ident, slots, aliases, nick_to_spec)
        if idx is not None:
            if idx not in open_queue:
                open_queue.append(idx)
            if clear_immediately:
                slots[idx] = ""
        return idx

    def _assign_slot(
        raw_mon: str,
        slots: List[str],
        open_queue: List[int],
        aliases: Dict[str, int],
        nick_to_spec: Dict[str, str],
    ) -> str:
        nick, spec = _parse_nick_and_species(raw_mon)
        # Check if already occupying a slot (e.g. duplicate Turn 0 lead initialization)
        existing_idx = _find_slot_index(raw_mon, slots, aliases, nick_to_spec)
        if existing_idx is not None and existing_idx not in open_queue:
            slots[existing_idx] = spec
            _register_slot_aliases(existing_idx, nick, spec, aliases, nick_to_spec)
            return spec

        if open_queue:
            idx = open_queue.pop(0)
        elif not slots[0]:
            idx = 0
        elif not slots[1]:
            idx = 1
        else:
            idx = 0

        # Purge stale aliases pointing to idx
        for k_al, v_idx in list(aliases.items()):
            if v_idx == idx:
                del aliases[k_al]

        slots[idx] = spec
        _register_slot_aliases(idx, nick, spec, aliases, nick_to_spec)
        return spec

    # Initialize leads from parsed battle if available
    if battle.trainer_1.leads:
        for lead_sp in battle.trainer_1.leads[:2]:
            _assign_slot(lead_sp, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec)
    if battle.trainer_2.leads:
        for lead_sp in battle.trainer_2.leads[:2]:
            _assign_slot(lead_sp, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec)

    current_turn = 0
    turn_data: Dict[int, Dict[str, Any]] = {}

    cur_weather = "None"
    cur_terrain = "None"
    t1_tailwind = False
    t2_tailwind = False
    trick_room = False
    t1_screens: Set[str] = set()
    t2_screens: Set[str] = set()
    t1_hazards: Set[str] = set()
    t2_hazards: Set[str] = set()

    def _snapshot_field_conditions() -> List[str]:
        conds: List[str] = []
        if t1_tailwind:
            conds.append("T1_Tailwind")
        if t2_tailwind:
            conds.append("T2_Tailwind")
        if trick_room:
            conds.append("Trick_Room")
        if t1_screens:
            conds.append(f"T1_{'+'.join(sorted(t1_screens))}")
        if t2_screens:
            conds.append(f"T2_{'+'.join(sorted(t2_screens))}")
        if t1_hazards:
            conds.append(f"T1_{'+'.join(sorted(t1_hazards))}")
        if t2_hazards:
            conds.append(f"T2_{'+'.join(sorted(t2_hazards))}")
        return conds

    def get_turn_entry(t_num: int) -> Dict[str, Any]:
        if t_num not in turn_data:
            turn_data[t_num] = {
                "t1_active_1": t1_slots[0],
                "t1_active_2": t1_slots[1],
                "t2_active_1": t2_slots[0],
                "t2_active_2": t2_slots[1],
                "t1_moves": [],
                "t2_moves": [],
                "dmg_to_t2": 0.0,
                "dmg_to_t1": 0.0,
                "faints": [],
                "variance": [],
                "weather": cur_weather,
                "terrain": cur_terrain,
                "field_conditions": _snapshot_field_conditions(),
            }
        return turn_data[t_num]

    last_active_attacker: Optional[str] = None
    last_attacker_is_t2: Optional[bool] = None
    last_move_name: Optional[str] = None
    vanished_mons: Set[Tuple[bool, str]] = set()
    fake_out_targets_this_turn: Set[Tuple[bool, str]] = set()

    for line in lines:
        # Turn marker
        m_turn = re.match(r"^Turn\s+(\d+)", line)
        if m_turn:
            current_turn = int(m_turn.group(1))
            t1_open_queue.clear()
            t2_open_queue.clear()
            fake_out_targets_this_turn.clear()
            if not t1_slots[0] and t1_slots[1]:
                t1_slots[0], t1_slots[1] = t1_slots[1], ""
                for k_a, v_a in list(t1_aliases.items()):
                    if v_a == 1:
                        t1_aliases[k_a] = 0
            if not t2_slots[0] and t2_slots[1]:
                t2_slots[0], t2_slots[1] = t2_slots[1], ""
                for k_a, v_a in list(t2_aliases.items()):
                    if v_a == 1:
                        t2_aliases[k_a] = 0
            last_active_attacker = None
            last_attacker_is_t2 = None
            last_move_name = None
            entry = get_turn_entry(current_turn)
            entry["t1_active_1"] = t1_slots[0]
            entry["t1_active_2"] = t1_slots[1]
            entry["t2_active_1"] = t2_slots[0]
            entry["t2_active_2"] = t2_slots[1]
            entry["weather"] = cur_weather
            entry["terrain"] = cur_terrain
            entry["field_conditions"] = _snapshot_field_conditions()
            continue

        if current_turn == 0:
            m_go = re.match(r"^Go!\s+(.+?)!", line)
            if m_go:
                _assign_slot(m_go.group(1), t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec)

            m_sent = re.match(r"^(.+?)\s+sent out\s+(.+?)!", line)
            if m_sent:
                trainer_p = m_sent.group(1).strip().replace("☆", "").replace("★", "").strip()
                if trainer_p.lower() == trainer_1_name.lower():
                    _assign_slot(m_sent.group(2), t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec)
                else:
                    _assign_slot(m_sent.group(2), t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec)

        entry = get_turn_entry(current_turn if current_turn > 0 else 1)
        has_combat_actions = bool(entry["t1_moves"] or entry["t2_moves"])
        is_post_combat_faint_replacement = bool(entry["faints"]) and has_combat_actions

        # Weather / Terrain announcements & expirations (TEL-05, TEL-06)
        if "The sunlight turned harsh" in line:
            cur_weather = "Sun"
            if not is_post_combat_faint_replacement:
                entry["weather"] = cur_weather
        elif "started to rain" in line or "Rain continues" in line:
            cur_weather = "Rain"
            if not is_post_combat_faint_replacement:
                entry["weather"] = cur_weather
        elif "sandstorm kicked up" in line:
            cur_weather = "Sand"
            if not is_post_combat_faint_replacement:
                entry["weather"] = cur_weather
        elif "started to snow" in line or "Snow continues" in line or "started to hail" in line:
            cur_weather = "Snow"
            if not is_post_combat_faint_replacement:
                entry["weather"] = cur_weather
        elif (
            "sunlight faded" in line
            or "The rain stopped" in line
            or "The sandstorm subsided" in line
            or "The snow stopped" in line
            or "The hail stopped" in line
        ):
            cur_weather = "None"
            if not has_combat_actions:
                entry["weather"] = "None"
        elif "Grass grew to cover the battlefield" in line or "Grassy Surge]" in line:
            cur_terrain = "Grassy"
            if not is_post_combat_faint_replacement:
                entry["terrain"] = cur_terrain
        elif (
            "surged across the battlefield" in line
            or "electric current ran across the battlefield" in line
            or "Electric Surge]" in line
        ):
            cur_terrain = "Electric"
            if not is_post_combat_faint_replacement:
                entry["terrain"] = cur_terrain
        elif "Mist swirled" in line:
            cur_terrain = "Misty"
            if not is_post_combat_faint_replacement:
                entry["terrain"] = cur_terrain
        elif "weirdness" in line or "became weird" in line or "Psychic Surge]" in line:
            cur_terrain = "Psychic"
            if not is_post_combat_faint_replacement:
                entry["terrain"] = cur_terrain
        elif "disappeared from the battlefield" in line:
            cur_terrain = "None"
            if not has_combat_actions:
                entry["terrain"] = "None"

        # Field Conditions (TEL-04)
        low_line = line.lower()
        field_changed = False
        is_expiration_change = False

        if "tailwind blew from behind your team" in low_line or f"tailwind blew from behind {trainer_1_name.lower()}" in low_line:
            t1_tailwind = True
            field_changed = True
        elif "tailwind blew from behind the opposing team" in low_line or f"tailwind blew from behind {trainer_2_name.lower()}" in low_line:
            t2_tailwind = True
            field_changed = True
        elif "tailwind petered out" in low_line:
            is_expiration_change = True
            if "opposing" in low_line or trainer_2_name.lower() in low_line:
                t2_tailwind = False
            elif "your team" in low_line or trainer_1_name.lower() in low_line:
                t1_tailwind = False
            else:
                t1_tailwind = False
                t2_tailwind = False
        elif "twisted the dimensions" in low_line:
            trick_room = not trick_room
            field_changed = True
        elif "twisted dimensions returned to normal" in low_line:
            trick_room = False
            is_expiration_change = True
        elif "light screen" in low_line and ("rose" in low_line or "made" in low_line):
            if "opposing" in low_line:
                t2_screens.add("Light_Screen")
            else:
                t1_screens.add("Light_Screen")
            field_changed = True
        elif "reflect" in low_line and ("rose" in low_line or "made" in low_line):
            if "opposing" in low_line:
                t2_screens.add("Reflect")
            else:
                t1_screens.add("Reflect")
            field_changed = True
        elif "aurora veil" in low_line and ("rose" in low_line or "made" in low_line):
            if "opposing" in low_line:
                t2_screens.add("Aurora_Veil")
            else:
                t1_screens.add("Aurora_Veil")
            field_changed = True
        elif "wore off" in low_line:
            is_expiration_change = True
            target_screens = t2_screens if "opposing" in low_line else t1_screens
            if "light screen" in low_line:
                target_screens.discard("Light_Screen")
            if "reflect" in low_line:
                target_screens.discard("Reflect")
            if "aurora veil" in low_line:
                target_screens.discard("Aurora_Veil")
        elif "poison spikes were scattered" in low_line:
            if "opposing" in low_line:
                t2_hazards.add("Toxic_Spikes")
            else:
                t1_hazards.add("Toxic_Spikes")
            field_changed = True
        elif "spikes were scattered" in low_line:
            if "opposing" in low_line:
                t2_hazards.add("Spikes")
            else:
                t1_hazards.add("Spikes")
            field_changed = True
        elif "pointed stones float" in low_line:
            if "opposing" in low_line:
                t2_hazards.add("Stealth_Rock")
            else:
                t1_hazards.add("Stealth_Rock")
            field_changed = True
        elif "sticky web" in low_line and ("lay" in low_line or "caught" not in low_line):
            if "opposing" in low_line:
                t2_hazards.add("Sticky_Web")
            else:
                t1_hazards.add("Sticky_Web")
            field_changed = True
        elif "disappeared from around" in low_line:
            target_hazards = t2_hazards if "opposing" in low_line else t1_hazards
            if "poison spikes" in low_line:
                target_hazards.discard("Toxic_Spikes")
            elif "spikes" in low_line:
                target_hazards.discard("Spikes")
            elif "pointed stones" in low_line:
                target_hazards.discard("Stealth_Rock")
            elif "sticky web" in low_line:
                target_hazards.discard("Sticky_Web")
            field_changed = True

        if field_changed and not is_post_combat_faint_replacement:
            entry["field_conditions"] = _snapshot_field_conditions()
        elif is_expiration_change and not has_combat_actions:
            entry["field_conditions"] = _snapshot_field_conditions()

        # Key Stone reaction (for canonical Mega species resolution via DuckDB)
        m_stone = re.search(r"^(?:The opposing\s+)?(.+?)'s\s+(.+?)\s+is reacting to the Key Stone!", line)
        if m_stone:
            s_nick = m_stone.group(1).strip()
            s_item = m_stone.group(2).strip()
            if line.startswith("The opposing "):
                t2_pending_stone[s_nick.lower()] = s_item
            else:
                t1_pending_stone[s_nick.lower()] = s_item

        # Track explicit withdrawals, pivot returns, and forced ejects (TEL-02)
        m_withdrew = re.match(r"^(.+?)\s+withdrew\s+(.+?)!", line)
        if m_withdrew:
            tr_w = m_withdrew.group(1).strip().replace("☆", "").replace("★", "").strip()
            mon_w = m_withdrew.group(2).strip()
            if tr_w.lower() == trainer_1_name.lower():
                _vacate_slot(mon_w, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec, clear_immediately=False)
            else:
                _vacate_slot(mon_w, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec, clear_immediately=False)
            continue

        m_comeback = re.match(r"^(.+?),\s+come back!", line)
        if m_comeback:
            _vacate_slot(
                m_comeback.group(1).strip(),
                t1_slots,
                t1_open_queue,
                t1_aliases,
                t1_nick_to_spec,
                clear_immediately=False,
            )
            continue

        m_wentback = re.match(r"^(?:The opposing\s+)?(.+?)\s+went back to\s+(.+?)!", line)
        if m_wentback:
            mon_wb = m_wentback.group(1).strip()
            tr_wb = m_wentback.group(2).strip().replace("☆", "").replace("★", "").strip()
            if line.startswith("The opposing ") or tr_wb.lower() == trainer_2_name.lower():
                _vacate_slot(mon_wb, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec, clear_immediately=False)
            else:
                _vacate_slot(mon_wb, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec, clear_immediately=False)
            continue

        m_eject = re.match(r"^(?:The opposing\s+)?(.+?)\s+is switched out with the\s+.+?!", line)
        if m_eject:
            mon_ej = m_eject.group(1).strip()
            if line.startswith("The opposing "):
                _vacate_slot(mon_ej, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec, clear_immediately=False)
            else:
                _vacate_slot(mon_ej, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec, clear_immediately=False)
            continue

        m_redcard = re.search(
            r"^(?:The opposing\s+)?(.+?)\s+held up its\s+Red Card\s+against\s+(the opposing\s+)?(.+?)!",
            line,
        )
        if m_redcard:
            victim_is_t2 = bool(m_redcard.group(2))
            victim_mon = m_redcard.group(3).strip()
            if victim_is_t2:
                _vacate_slot(victim_mon, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec, clear_immediately=False)
            else:
                _vacate_slot(victim_mon, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec, clear_immediately=False)
            continue

        m_emexit = re.match(r"^\[(?:The opposing\s+)?(.+?)'s\s+Emergency Exit\]", line)
        if m_emexit:
            mon_em = m_emexit.group(1).strip()
            if line.startswith("[The opposing "):
                _vacate_slot(mon_em, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec, clear_immediately=False)
            else:
                _vacate_slot(mon_em, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec, clear_immediately=False)
            continue

        # Switches during battle
        m_switch = re.match(r"^(.+?)\s+sent out\s+(.+?)!", line)
        if m_switch and current_turn > 0:
            trainer_p = m_switch.group(1).strip().replace("☆", "").replace("★", "").strip()
            raw_mon = m_switch.group(2).strip()
            is_t1 = trainer_p.lower() == trainer_1_name.lower()
            if is_t1:
                spec = _assign_slot(raw_mon, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec)
                entry["t1_moves"].append(f"Switch -> {spec}")
            else:
                spec = _assign_slot(raw_mon, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec)
                entry["t2_moves"].append(f"Switch -> {spec}")
            continue

        m_go_mid = re.match(r"^Go!\s+(.+?)!", line)
        if m_go_mid and current_turn > 0:
            spec = _assign_slot(m_go_mid.group(1).strip(), t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec)
            entry["t1_moves"].append(f"Switch -> {spec}")
            continue

        m_drag = re.match(r"^(?:The opposing\s+)?(.+?)\s+was dragged out!", line)
        if m_drag and current_turn > 0:
            raw_mon = m_drag.group(1).strip()
            _, spec_d = _parse_nick_and_species(raw_mon)
            is_t2_drag = line.startswith("The opposing ") or (
                spec_d not in battle.trainer_1.team_preview
                and spec_d not in battle.trainer_1.pokemon_sets
                and (spec_d in battle.trainer_2.team_preview or spec_d in battle.trainer_2.pokemon_sets)
            )
            if is_t2_drag:
                _assign_slot(raw_mon, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec)
            else:
                _assign_slot(raw_mon, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec)
            continue

        # Semi-invulnerable two-turn charge tracking (TEL-08)
        m_van = re.match(
            r"^(?:The opposing\s+)?(.+?)\s+(?:vanished instantly|flew up high|dug a hole|bounced up|hid underwater)!",
            line,
        )
        if m_van:
            v_nick = m_van.group(1).strip().lower()
            v_is_t2 = line.startswith("The opposing ")
            vanished_mons.add((v_is_t2, v_nick))
            continue

        # Move execution
        m_move = re.search(r"^(?:The opposing\s+)?(.+?)\s+used\s+(.+?)!", line)
        if m_move:
            mon_nick = m_move.group(1).strip()
            mv_name = m_move.group(2).strip()
            is_opp = line.startswith("The opposing ")
            last_attacker_is_t2 = is_opp
            last_active_attacker = mon_nick
            last_move_name = mv_name
            vanished_mons.discard((is_opp, mon_nick.lower()))
            if is_opp:
                entry["t2_moves"].append(f"{mon_nick}: {mv_name}")
            else:
                entry["t1_moves"].append(f"{mon_nick}: {mv_name}")
            continue

        # Damage observations (TEL-07: exclude same-side self-cost & friendly-fire moves)
        m_dmg = re.search(r"\((?:The opposing\s+)?(.+?)\s+lost\s+(\d+(?:\.\d+)?)%\s+of its health!\)", line)
        if m_dmg:
            target_mon = m_dmg.group(1).strip()
            pct_lost = float(m_dmg.group(2))
            is_opp_target = "The opposing " in line
            if last_move_name == "Fake Out":
                fake_out_targets_this_turn.add((is_opp_target, target_mon.lower()))
            if last_attacker_is_t2 is not None and is_opp_target == last_attacker_is_t2:
                # Same-side damage (e.g. Substitute cost or friendly-fire Feint into partner)
                continue
            if is_opp_target:
                entry["dmg_to_t2"] += pct_lost
            else:
                entry["dmg_to_t1"] += pct_lost
            continue

        # Faints (TEL-02 FIFO open-slot queue + TEL-03 immediate slot clearing)
        m_faint = re.search(r"^(?:The opposing\s+)?(.+?)\s+fainted!", line)
        if m_faint:
            fainted_mon = m_faint.group(1).strip()
            is_opp_faint = line.startswith("The opposing ")
            team_label = "trainer_2" if is_opp_faint else "trainer_1"
            vanished_mons.discard((is_opp_faint, fainted_mon.lower()))
            if is_opp_faint:
                _vacate_slot(fainted_mon, t2_slots, t2_open_queue, t2_aliases, t2_nick_to_spec, clear_immediately=True)
            else:
                _vacate_slot(fainted_mon, t1_slots, t1_open_queue, t1_aliases, t1_nick_to_spec, clear_immediately=True)
            entry["faints"].append(f"{team_label}: {fainted_mon}")
            continue

        # RNG Variance & Tactical Triggers (TEL-08)
        if "A critical hit" in line:
            entry["variance"].append("Critical Hit")
        elif "flinched" in line:
            m_flinch = re.search(r"^(?:The opposing\s+)?(.+?)\s+flinched", line)
            target = m_flinch.group(1).strip() if m_flinch else "target"
            is_opp_fl = line.startswith("The opposing ") or ("'s " in target)
            clean_target = target.split("'s ")[-1].strip()
            if (
                last_move_name == "Fake Out"
                or (is_opp_fl, clean_target.lower()) in fake_out_targets_this_turn
                or (not is_opp_fl, clean_target.lower()) in fake_out_targets_this_turn
            ):
                entry["variance"].append(f"Fake Out Flinch on {target}")
            else:
                entry["variance"].append(f"Flinch on {target}")
        elif "paralyzed! It may be unable to move!" in line or "is paralyzed! It can't move!" in line:
            entry["variance"].append("Paralysis")
        elif "is frozen solid!" in line:
            entry["variance"].append("Frozen Solid")
        elif "avoided the attack!" in line or "missed!" in line:
            m_avoid = re.match(r"^(?:The opposing\s+)?(.+?)\s+avoided the attack!", line)
            if m_avoid:
                av_is_t2 = line.startswith("The opposing ")
                av_nick = m_avoid.group(1).strip().lower()
                if (av_is_t2, av_nick) in vanished_mons:
                    continue
            entry["variance"].append("Attack Missed")
        elif "Mega Evolved" in line:
            m_mega = re.search(r"^(?:The opposing\s+)?(.+?)\s+(?:has\s+)?Mega Evolved into (?:Mega\s+)?(.+?)!", line)
            if m_mega:
                m_nick = m_mega.group(1).strip()
                m_into = m_mega.group(2).strip()
                is_opp_m = line.startswith("The opposing ")
                entry["variance"].append(f"Mega Evolution ({m_into})")
                # Update active slot to canonical DuckDB Mega species if known
                slots_m = t2_slots if is_opp_m else t1_slots
                aliases_m = t2_aliases if is_opp_m else t1_aliases
                n2s_m = t2_nick_to_spec if is_opp_m else t1_nick_to_spec
                pstone_m = t2_pending_stone if is_opp_m else t1_pending_stone
                idx_m = _find_slot_index(m_nick, slots_m, aliases_m, n2s_m)
                if idx_m is not None:
                    base_sp = _base_species_key(slots_m[idx_m] or m_into)
                    stone_name = (
                        pstone_m.get(m_nick.lower())
                        or pstone_m.get(base_sp)
                        or ""
                    ).lower()
                    canon_mega = stone_to_mega.get(stone_name) or base_to_mega.get(base_sp)
                    if canon_mega:
                        slots_m[idx_m] = canon_mega
                        _register_slot_aliases(idx_m, m_nick, canon_mega, aliases_m, n2s_m)
            else:
                entry["variance"].append("Mega Evolution")
        elif "White Herb" in line and ("restored" in line or "activated" in line):
            m_wh = re.search(r"^(?:The opposing\s+)?(.+?)(?:'s\s+White Herb|\s+restored its status using its White Herb)", line)
            mon = m_wh.group(1).strip() if m_wh else "target"
            entry["variance"].append(f"White Herb on {mon}")
        elif "Focus Sash" in line and "hung on" in line:
            m_sash = re.search(r"^(?:The opposing\s+)?(.+?)\s+hung on using its Focus Sash", line)
            mon = m_sash.group(1).strip() if m_sash else "target"
            entry["variance"].append(f"Focus Sash on {mon}")
        elif "Intimidate" in line and ("cuts" in line or "lowered" in line):
            m_intim = re.search(r"^(?:The opposing\s+)?(.+?)'s\s+Intimidate", line)
            mon = m_intim.group(1).strip() if m_intim else "target"
            entry["variance"].append(f"Intimidate by {mon}")
        elif "Defiant" in line and "sharply raised" in line:
            entry["variance"].append("Defiant +2 Atk")
        elif "Stamina" in line and "raised" in line:
            entry["variance"].append("Stamina +1 Def")
        elif "became the center of attention!" in line:
            m_redir = re.search(r"^(?:The opposing\s+)?(.+?)\s+became the center of attention", line)
            mon = m_redir.group(1).strip() if m_redir else "target"
            entry["variance"].append(f"Redirection ({mon})")

    # Build final TurnTelemetryRecord list sorted by turn
    records: List[TurnTelemetryRecord] = []
    max_turns = max(turn_data.keys()) if turn_data else 0

    for t_idx in range(1, max_turns + 1):
        if t_idx not in turn_data:
            continue
        d = turn_data[t_idx]
        conds = d.get("field_conditions") or []

        records.append(
            TurnTelemetryRecord(
                match_id=match_id,
                timestamp=iso_now,
                turn=t_idx,
                trainer_1=trainer_1_name,
                trainer_2=trainer_2_name,
                trainer_1_active_1=d["t1_active_1"],
                trainer_1_active_2=d["t1_active_2"],
                trainer_2_active_1=d["t2_active_1"],
                trainer_2_active_2=d["t2_active_2"],
                trainer_1_moves="; ".join(d["t1_moves"]) if d["t1_moves"] else "None",
                trainer_2_moves="; ".join(d["t2_moves"]) if d["t2_moves"] else "None",
                damage_dealt_to_trainer_2=round(d["dmg_to_t2"], 1),
                damage_dealt_to_trainer_1=round(d["dmg_to_t1"], 1),
                faints_this_turn="; ".join(d["faints"]) if d["faints"] else "None",
                variance_events="; ".join(d["variance"]) if d["variance"] else "None",
                weather=d["weather"],
                terrain=d["terrain"],
                field_conditions="; ".join(conds) if conds else "Neutral",
                winner=winner_name,
                comment="",
            )
        )

    return records


CSV_COLUMNS: List[str] = [
    "match_id",
    "timestamp",
    "turn",
    "trainer_1",
    "trainer_2",
    "trainer_1_active_1",
    "trainer_1_active_2",
    "trainer_2_active_1",
    "trainer_2_active_2",
    "trainer_1_moves",
    "trainer_2_moves",
    "damage_dealt_to_trainer_2",
    "damage_dealt_to_trainer_1",
    "faints_this_turn",
    "variance_events",
    "weather",
    "terrain",
    "field_conditions",
    "winner",
    "comment",
]


def save_telemetry_to_csv(
    records: List[TurnTelemetryRecord],
    csv_path: str | Path = "data/telemetry/battles_telemetry.csv",
    append: bool = True,
) -> Path:
    """Save or append turn telemetry records to a target CSV file."""
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = path.exists() and path.stat().st_size > 0
    mode = "a" if append and file_exists else "w"

    with open(path, mode=mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists or mode == "w":
            writer.writeheader()
        for r in records:
            writer.writerow(r.to_dict())

    return path


def update_telemetry_comment(
    csv_path: str | Path,
    match_id: str,
    turn: int,
    comment: str,
) -> bool:
    """Update or inject a comment for a specific turn in an existing CSV file."""
    path = Path(csv_path)
    if not path.is_file():
        return False

    rows: List[Dict[str, Any]] = []
    updated = False

    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("match_id") == match_id and int(row.get("turn", 0)) == int(turn):
                row["comment"] = comment
                updated = True
            rows.append(row)

    if updated:
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    return updated


def batch_update_comments(
    csv_path: str | Path,
    match_id: str,
    comments_by_turn: Dict[int, str],
) -> int:
    """Batch update comments for multiple turns belonging to a match_id."""
    path = Path(csv_path)
    if not path.is_file():
        return 0

    rows: List[Dict[str, Any]] = []
    update_count = 0

    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("match_id") == match_id:
                t_num = int(row.get("turn", 0))
                if t_num in comments_by_turn:
                    row["comment"] = comments_by_turn[t_num]
                    update_count += 1
            rows.append(row)

    if update_count > 0:
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    return update_count
