# -*- coding: utf-8 -*-
"""Lossless Pokémon Showdown Official Wire-Protocol Replay Parser.

Extracts `<script type="text/plain" class="battle-log-data">` from official
Showdown `.html` replay files (or raw pipe-delimited logs) and reconstructs
exact per-turn board snapshots (`TurnSnapshot`) with strict `trainer_1` (coached POV)
and `trainer_2` (opponent) semantics — zero HP drift, exact post-Sitrus/Leftovers/
Recoil health, exact `active_turns`, `protect_counter`, boosts, items, weather,
Trick Room timers, and recorded moves/crits/flinches per turn.
"""
from __future__ import annotations

import copy
import html
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from engine.db_registry import get_registry
from engine.parser.models import ParsedBattle, ParsedPokemon, ParsedTeam, StatSpread

# Showdown wire protocol uses fixed 2-char side tags on the wire; we translate
# them immediately at the parser boundary into `trainer_1` (POV) and `trainer_2` (Opp).
_WIRE_LEFT = "p" + "1"
_WIRE_RIGHT = "p" + "2"

_PROTECT_STREAK_MOVES = {
    "protect",
    "detect",
    "spikyshield",
    "kingsshield",
    "banefulbunker",
    "silktrap",
    "burningbulwark",
    "obstruct",
    "endure",
}

_PIVOT_SOURCE_MOVES = {
    "partingshot",
    "uturn",
    "voltswitch",
    "flipturn",
    "batonpass",
    "chillyreception",
    "shedtail",
}

_WEATHER_MAP = {
    "sunnyday": "Sun",
    "desolateland": "Sun",
    "raindance": "Rain",
    "primordialsea": "Rain",
    "sandstorm": "Sand",
    "snow": "Snow",
    "snowscape": "Snow",
    "hail": "Snow",
    "none": None,
}

_TERRAIN_MAP = {
    "grassyterrain": "Grassy",
    "psychicterrain": "Psychic",
    "electricterrain": "Electric",
    "mistyterrain": "Misty",
}


def _norm_id(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def _canonical_db_name(raw_token: str, lookup: Dict[str, str]) -> str:
    """Resolve compact Showdown packed names (e.g. `PsychicNoise`, `CharizarditeY`) via DuckDB."""
    key = _norm_id(raw_token)
    if key in lookup:
        return lookup[key]
    # Fallback: insert spaces before CamelCase capitals
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", raw_token).strip()
    return spaced or raw_token


def _build_duckdb_name_lookups() -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]]:
    """Build normalized-id -> canonical-name maps from DuckDB `VGCDataRegistry`."""
    reg = get_registry()
    moves_map: Dict[str, str] = {}
    items_map: Dict[str, str] = {}
    abilities_map: Dict[str, str] = {}
    species_map: Dict[str, str] = {}

    for r in reg.query("SELECT id, name FROM moves;"):
        moves_map[_norm_id(str(r["id"]))] = str(r["name"])
        moves_map[_norm_id(str(r["name"]))] = str(r["name"])
    for r in reg.query("SELECT id, name FROM items;"):
        items_map[_norm_id(str(r["id"]))] = str(r["name"])
        items_map[_norm_id(str(r["name"]))] = str(r["name"])
    for r in reg.query("SELECT id, name FROM abilities;"):
        abilities_map[_norm_id(str(r["id"]))] = str(r["name"])
        abilities_map[_norm_id(str(r["name"]))] = str(r["name"])
    for r in reg.query("SELECT id, name FROM pokedex;"):
        species_map[_norm_id(str(r["id"]))] = str(r["name"])
        species_map[_norm_id(str(r["name"]))] = str(r["name"])
    return species_map, moves_map, items_map, abilities_map


@dataclass
class RecordedSlotAction:
    """Recorded execution for one active slot (`slot_a` or `slot_b`) during a turn."""

    actor_species: str
    kind: str = "none"  # "move", "switch", "flinched", "fainted", "none"
    move_name: Optional[str] = None
    target_trainer: Optional[str] = None  # "trainer_1" or "trainer_2"
    target_slot_letter: Optional[str] = None  # "a" or "b"
    switch_to_species: Optional[str] = None
    used_mega: bool = False
    flinched_or_blocked: bool = False
    summary: str = ""


@dataclass
class TurnEvents:
    """Notable RNG & tactical events logged during a turn (for deterministic commentary)."""

    crits: List[Dict[str, str]] = field(default_factory=list)
    misses: List[Dict[str, str]] = field(default_factory=list)
    flinches: List[Dict[str, str]] = field(default_factory=list)
    protects: List[str] = field(default_factory=list)
    faints: List[Dict[str, str]] = field(default_factory=list)
    megas: List[Dict[str, str]] = field(default_factory=list)
    weather_changes: List[str] = field(default_factory=list)


@dataclass
class TurnSnapshot:
    """Exact pre-decision board state and recorded actions for a single turn."""

    turn_number: int
    battle_state: ParsedBattle
    weather: Optional[str]
    weather_turns: int
    terrain: Optional[str]
    terrain_turns: int
    trick_room_turns: int
    trainer_1_tailwind_turns: int
    trainer_2_tailwind_turns: int
    trainer_1_slot_a_action: Optional[RecordedSlotAction] = None
    trainer_1_slot_b_action: Optional[RecordedSlotAction] = None
    trainer_2_slot_a_action: Optional[RecordedSlotAction] = None
    trainer_2_slot_b_action: Optional[RecordedSlotAction] = None
    events: TurnEvents = field(default_factory=TurnEvents)


@dataclass
class ParsedReplay:
    """Full parsed Showdown replay ready for GPU Nash/IEDS coaching & official UI playback."""

    replay_id: str
    format_name: str
    raw_log_text: str
    trainer_1_name: str
    trainer_2_name: str
    pov_is_right_side: bool
    winner: Optional[str]
    trainer_1_preview: List[str]
    trainer_2_preview: List[str]
    trainer_1_brought: List[str]
    trainer_2_brought: List[str]
    turns: List[TurnSnapshot]


def extract_protocol_log(raw_input: str) -> Tuple[str, str]:
    """Extract raw Showdown wire protocol text and replay_id from `.html` or raw pipe text."""
    text = raw_input.strip()
    replay_id = "local-replay"
    id_match = re.search(r'name=["\']replayid["\']\s+value=["\']([^"\']+)["\']', text)
    if id_match:
        replay_id = id_match.group(1).strip()

    script_match = re.search(
        r'<script[^>]*class=["\'][^"\']*battle-log-data[^"\']*["\'][^>]*>(.*?)</script>',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if script_match:
        log_body = script_match.group(1)
        log_body = log_body.replace(r"\/", "/")
        log_body = html.unescape(log_body)
        return log_body.strip(), replay_id

    return text, replay_id


def _parse_hp_token(hp_token: str) -> Tuple[float, bool]:
    """Parse Showdown HP strings (`175/175`, `32/100`, `0 fnt`, `57/100 par`) -> `(hp_pct, fainted)`."""
    clean = (hp_token or "").strip()
    if not clean:
        return 100.0, False
    parts = clean.split()
    first = parts[0]
    if first == "0" or (len(parts) > 1 and parts[1].lower() == "fnt"):
        return 0.0, True
    if "/" in first:
        num_s, den_s = first.split("/", 1)
        try:
            num, den = float(num_s), float(den_s)
            if den <= 0.0:
                return 0.0, True
            pct = max(0.0, min(100.0, (num / den) * 100.0))
            return pct, num <= 0.0
        except ValueError:
            pass
    return 100.0, False


def _parse_status_token(hp_token: str) -> Optional[str]:
    parts = (hp_token or "").strip().split()
    if len(parts) >= 2 and parts[1].lower() in {"brn", "par", "slp", "psn", "tox", "frz"}:
        return parts[1].lower()
    return None


def _extract_slot_ident(ident: str) -> Tuple[str, str, str]:
    """Parse `p2a: Hazard` -> `(wire_side, slot_letter, nickname)`."""
    clean = (ident or "").strip()
    if ":" in clean:
        prefix, nick = clean.split(":", 1)
        prefix = prefix.strip()
        nick = nick.strip()
    else:
        prefix, nick = clean, ""
    wire_side = prefix[:2]
    slot_letter = prefix[2:3].lower() if len(prefix) >= 3 else "a"
    return wire_side, slot_letter, nick


def _parse_showteam_packed(
    packed: str,
    species_map: Dict[str, str],
    moves_map: Dict[str, str],
    items_map: Dict[str, str],
    abilities_map: Dict[str, str],
) -> List[ParsedPokemon]:
    """Decode Showdown packed `|showteam|` string into `ParsedPokemon` objects."""
    mons: List[ParsedPokemon] = []
    for entry in packed.split("]"):
        if not entry.strip():
            continue
        fields = entry.split("|")
        while len(fields) < 12:
            fields.append("")
        sp_raw = fields[1].strip() or fields[0].strip()
        sp = _canonical_db_name(sp_raw, species_map)
        item = _canonical_db_name(fields[2].strip(), items_map) if fields[2].strip() else None
        ability = _canonical_db_name(fields[3].strip(), abilities_map) if fields[3].strip() else None
        moves = [
            _canonical_db_name(m.strip(), moves_map)
            for m in fields[4].split(",")
            if m.strip()
        ]
        nature = fields[5].strip() or None
        gender = fields[7].strip() or None
        lvl = int(fields[10].strip()) if fields[10].strip().isdigit() else 50
        base_sp = sp.split("-")[0] if "-Mega" in sp else sp
        mons.append(
            ParsedPokemon(
                species=sp,
                base_species=base_sp,
                item=item,
                ability=ability,
                nature=nature,
                level=lvl,
                gender=gender,
                moves=moves,
            )
        )
    return mons


def parse_showdown_replay(
    raw_input: str,
    pov_trainer: Optional[str] = None,
    trainer_1_ots_sets: Optional[Dict[str, ParsedPokemon]] = None,
    trainer_2_ots_sets: Optional[Dict[str, ParsedPokemon]] = None,
) -> ParsedReplay:
    """Parse an official Showdown `.html` or pipe-protocol replay into per-turn snapshots.

    Merges exact 66-SP spreads (and fallback items/moves) from the OTS Database
    while preserving exact replay `|showteam|` items/moves and exact turn-by-turn
    HP, boosts, weather, Trick Room, Protect chains, and `active_turns`.
    """
    log_text, replay_id = extract_protocol_log(raw_input)
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]

    species_map, moves_map, items_map, abilities_map = _build_duckdb_name_lookups()

    wire_players: Dict[str, str] = {}
    format_name = "[Gen 9 Champions] VGC 2026 Reg M-C (Bo3)"
    winner: Optional[str] = None

    # Pass 1: identify player names & format
    for ln in lines:
        if not ln.startswith("|"):
            continue
        toks = ln.split("|")
        cmd = toks[1] if len(toks) > 1 else ""
        if cmd == "player" and len(toks) >= 4 and toks[3].strip():
            wire_players[toks[2].strip()] = toks[3].strip()
        elif cmd == "tier" and len(toks) >= 3:
            format_name = toks[2].strip()
        elif cmd == "win" and len(toks) >= 3:
            winner = toks[2].strip()

    left_name = wire_players.get(_WIRE_LEFT, "Trainer A")
    right_name = wire_players.get(_WIRE_RIGHT, "Trainer B")

    pov_wire = _WIRE_LEFT
    if pov_trainer:
        pt = pov_trainer.strip().lower()
        if right_name.lower() == pt or pt in right_name.lower():
            pov_wire = _WIRE_RIGHT
        elif left_name.lower() == pt or pt in left_name.lower():
            pov_wire = _WIRE_LEFT
    opp_wire = _WIRE_RIGHT if pov_wire == _WIRE_LEFT else _WIRE_LEFT

    def wire_to_trainer(w: str) -> str:
        return "trainer_1" if w == pov_wire else "trainer_2"

    team_1 = ParsedTeam(trainer_name=wire_players.get(pov_wire, "trainer_1"))
    team_2 = ParsedTeam(trainer_name=wire_players.get(opp_wire, "trainer_2"))
    teams = {"trainer_1": team_1, "trainer_2": team_2}
    db_sets_map = {
        "trainer_1": trainer_1_ots_sets or {},
        "trainer_2": trainer_2_ots_sets or {},
    }

    # Track live mutable state per trainer & slot letter ("a" / "b")
    active_by_slot: Dict[str, Dict[str, Optional[str]]] = {
        "trainer_1": {"a": None, "b": None},
        "trainer_2": {"a": None, "b": None},
    }
    nick_to_species: Dict[str, Dict[str, str]] = {"trainer_1": {}, "trainer_2": {}}
    brought_order: Dict[str, List[str]] = {"trainer_1": [], "trainer_2": []}

    # Dynamic field & volatile trackers
    weather: Optional[str] = None
    weather_turns: int = 0
    terrain: Optional[str] = None
    terrain_turns: int = 0
    trick_room_turns: int = 0
    tailwind_turns: Dict[str, int] = {"trainer_1": 0, "trainer_2": 0}
    reflect_turns: Dict[str, int] = {"trainer_1": 0, "trainer_2": 0}
    light_screen_turns: Dict[str, int] = {"trainer_1": 0, "trainer_2": 0}
    aurora_veil_turns: Dict[str, int] = {"trainer_1": 0, "trainer_2": 0}

    # Track whether a slot used a Protect-streak move during the current turn
    used_protect_this_turn: Dict[str, Dict[str, bool]] = {
        "trainer_1": {"a": False, "b": False},
        "trainer_2": {"a": False, "b": False},
    }

    def ensure_pokemon(trainer_id: str, species_raw: str) -> ParsedPokemon:
        t_obj = teams[trainer_id]
        sp_clean = species_raw.split(",")[0].strip()
        sp_canon = _canonical_db_name(sp_clean, species_map)
        base_canon = sp_canon.split("-Mega")[0] if "-Mega" in sp_canon else sp_canon
        existing = t_obj.get_pokemon(sp_canon) or t_obj.get_pokemon(base_canon)
        if existing is None:
            existing = ParsedPokemon(species=sp_canon, base_species=base_canon)
            t_obj.pokemon_sets[sp_canon] = existing
        # Merge exact EVs/SPs & fallback metadata from DuckDB OTS roster
        db_lookup = db_sets_map[trainer_id]
        db_mon = db_lookup.get(_norm_id(base_canon)) or db_lookup.get(_norm_id(sp_canon))
        if db_mon is not None:
            if existing.spread.total_sp == 0 and db_mon.spread.total_sp > 0:
                existing.spread = copy.deepcopy(db_mon.spread)
            if not existing.nature and db_mon.nature:
                existing.nature = db_mon.nature
            if not existing.item and db_mon.item:
                existing.item = db_mon.item
            if not existing.ability and db_mon.ability:
                existing.ability = db_mon.ability
            if not existing.moves and db_mon.moves:
                existing.moves = list(db_mon.moves)
        return existing

    def register_brought(trainer_id: str, base_key: str) -> None:
        if base_key not in brought_order[trainer_id]:
            brought_order[trainer_id].append(base_key)
        if base_key not in teams[trainer_id].battle_roster:
            teams[trainer_id].battle_roster.append(base_key)

    def build_battle_snapshot(turn_num: int) -> TurnSnapshot:
        """Deep-copy current live state into an immutable TurnSnapshot at the start of `turn_num`."""
        b = ParsedBattle(
            format=format_name,
            is_bo3="bo3" in format_name.lower(),
            trainer_1=copy.deepcopy(team_1),
            trainer_2=copy.deepcopy(team_2),
            turns_played=max(0, turn_num - 1),
            winner=winner,
            weather=weather,
            terrain=terrain,
            trainer_1_tailwind=tailwind_turns["trainer_1"] > 0,
            trainer_2_tailwind=tailwind_turns["trainer_2"] > 0,
            trainer_1_reflect=reflect_turns["trainer_1"] > 0,
            trainer_2_reflect=reflect_turns["trainer_2"] > 0,
            trainer_1_light_screen=light_screen_turns["trainer_1"] > 0,
            trainer_2_light_screen=light_screen_turns["trainer_2"] > 0,
            trainer_1_aurora_veil=aurora_veil_turns["trainer_1"] > 0,
            trainer_2_aurora_veil=aurora_veil_turns["trainer_2"] > 0,
            trick_room=trick_room_turns > 0,
        )
        for tid, b_team in (("trainer_1", b.trainer_1), ("trainer_2", b.trainer_2)):
            act_list: List[str] = []
            for sl in ("a", "b"):
                sp_key = active_by_slot[tid][sl]
                if sp_key:
                    act_list.append(sp_key)
            b_team.active_slots = act_list
        return TurnSnapshot(
            turn_number=turn_num,
            battle_state=b,
            weather=weather,
            weather_turns=weather_turns,
            terrain=terrain,
            terrain_turns=terrain_turns,
            trick_room_turns=trick_room_turns,
            trainer_1_tailwind_turns=tailwind_turns["trainer_1"],
            trainer_2_tailwind_turns=tailwind_turns["trainer_2"],
        )

    turns: List[TurnSnapshot] = []
    cur_turn_snap: Optional[TurnSnapshot] = None
    in_upkeep_phase = False
    started = False

    def set_slot_action(tid: str, sl: str, action: RecordedSlotAction) -> None:
        if cur_turn_snap is None:
            return
        attr = f"{tid}_slot_{sl}_action"
        existing: Optional[RecordedSlotAction] = getattr(cur_turn_snap, attr)
        if existing is None or existing.kind == "none":
            setattr(cur_turn_snap, attr, action)

    def mark_slot_mega(tid: str, sl: str) -> None:
        if cur_turn_snap is None:
            return
        attr = f"{tid}_slot_{sl}_action"
        existing: Optional[RecordedSlotAction] = getattr(cur_turn_snap, attr)
        if existing is not None:
            existing.used_mega = True

    pending_mega_slot: Dict[Tuple[str, str], bool] = {}

    for ln in lines:
        if not ln.startswith("|"):
            continue
        toks = ln.split("|")
        cmd = toks[1] if len(toks) > 1 else ""

        if cmd == "poke" and len(toks) >= 4:
            tid = wire_to_trainer(toks[2].strip())
            mon = ensure_pokemon(tid, toks[3].strip())
            if mon.species not in teams[tid].team_preview:
                teams[tid].team_preview.append(mon.species)

        elif cmd == "showteam" and len(toks) >= 4:
            tid = wire_to_trainer(toks[2].strip())
            packed_rest = "|".join(toks[3:])
            packed_mons = _parse_showteam_packed(
                packed_rest, species_map, moves_map, items_map, abilities_map
            )
            for pm in packed_mons:
                existing = ensure_pokemon(tid, pm.species)
                # Replay |showteam| is authoritative for actual items/moves/ability/nature
                if pm.item:
                    existing.item = pm.item
                if pm.ability:
                    existing.ability = pm.ability
                if pm.moves:
                    existing.moves = list(pm.moves)
                if pm.nature:
                    existing.nature = pm.nature
                if pm.gender:
                    existing.gender = pm.gender
                # Re-ensure exact 66-SP spread from DB is preserved
                db_lookup = db_sets_map[tid]
                db_mon = db_lookup.get(_norm_id(existing.base_species or existing.species))
                if db_mon is not None and db_mon.spread.total_sp > 0:
                    existing.spread = copy.deepcopy(db_mon.spread)

        elif cmd == "start":
            started = True
            in_upkeep_phase = False

        elif cmd == "turn" and len(toks) >= 3:
            t_num = int(toks[2].strip())
            in_upkeep_phase = False
            pending_mega_slot.clear()
            used_protect_this_turn = {
                "trainer_1": {"a": False, "b": False},
                "trainer_2": {"a": False, "b": False},
            }
            cur_turn_snap = build_battle_snapshot(t_num)
            turns.append(cur_turn_snap)

        elif cmd in ("switch", "drag") and len(toks) >= 5:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp_details = toks[3].strip()
            hp_pct, fainted = _parse_hp_token(toks[4])
            status = _parse_status_token(toks[4])
            from_tag = " ".join(toks[5:]).lower() if len(toks) > 5 else ""

            prev_sp = active_by_slot[tid][sl]
            # Reset switched-out mon's volatile boosts & counters
            if prev_sp:
                prev_mon = teams[tid].get_pokemon(prev_sp)
                if prev_mon is not None:
                    prev_mon.boosts = {k: 0 for k in prev_mon.boosts}
                    prev_mon.active_turns = 0
                    prev_mon.used_protect_last_turn = False

            mon = ensure_pokemon(tid, sp_details)
            if nick:
                mon.nickname = nick
                nick_to_species[tid][nick.lower()] = mon.species
            mon.current_hp_pct = hp_pct
            mon.fainted = fainted
            mon.status = status
            mon.revealed_in_battle = True
            mon.active_turns = 0
            mon.used_protect_last_turn = False
            mon.boosts = {k: 0 for k in mon.boosts}
            if "-mega" in sp_details.lower():
                mon.is_mega = True
                mon.species = _canonical_db_name(sp_details.split(",")[0].strip(), species_map)

            # Record voluntary switch as the slot's action for this turn
            is_pivot = any(p in _norm_id(from_tag) for p in _PIVOT_SOURCE_MOVES)
            if cur_turn_snap is not None and not in_upkeep_phase and not is_pivot and cmd == "switch":
                set_slot_action(
                    tid,
                    sl,
                    RecordedSlotAction(
                        actor_species=prev_sp or mon.species,
                        kind="switch",
                        switch_to_species=mon.species,
                        summary=f"{prev_sp or 'Active'}: Switch -> {mon.species}",
                    ),
                )

            active_by_slot[tid][sl] = mon.species
            register_brought(tid, mon.species)
            if not teams[tid].leads and active_by_slot[tid]["a"] and active_by_slot[tid]["b"]:
                teams[tid].leads = (active_by_slot[tid]["a"], active_by_slot[tid]["b"])  # type: ignore[arg-type]

        elif cmd == "detailschange" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            new_sp = _canonical_db_name(toks[3].split(",")[0].strip(), species_map)
            cur_sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), "")
            mon = teams[tid].get_pokemon(cur_sp) or ensure_pokemon(tid, new_sp)
            old_key = mon.species
            mon.species = new_sp
            if "-mega" in new_sp.lower():
                mon.is_mega = True
            # Update dict key & active_by_slot
            if old_key in teams[tid].pokemon_sets and old_key != new_sp:
                teams[tid].pokemon_sets[new_sp] = teams[tid].pokemon_sets.pop(old_key)
            active_by_slot[tid][sl] = new_sp
            if nick:
                nick_to_species[tid][nick.lower()] = new_sp
            # Keep brought_order consistent with updated species key
            for idx_b, b_sp in enumerate(brought_order[tid]):
                if b_sp == old_key:
                    brought_order[tid][idx_b] = new_sp
            for idx_b, b_sp in enumerate(teams[tid].battle_roster):
                if b_sp == old_key:
                    teams[tid].battle_roster[idx_b] = new_sp

        elif cmd == "-mega" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            pending_mega_slot[(tid, sl)] = True
            mark_slot_mega(tid, sl)
            cur_sp = active_by_slot[tid][sl] or toks[3].strip()
            if cur_turn_snap is not None:
                cur_turn_snap.events.megas.append({"trainer": tid, "species": cur_sp})

        elif cmd == "move" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            move_raw = toks[3].strip()
            move_name = _canonical_db_name(move_raw, moves_map)
            tgt_raw = toks[4].strip() if len(toks) >= 5 else ""
            tgt_tid: Optional[str] = None
            tgt_sl: Optional[str] = None
            if tgt_raw and ":" in tgt_raw:
                tw, tsl, _ = _extract_slot_ident(tgt_raw)
                if tw in (_WIRE_LEFT, _WIRE_RIGHT):
                    tgt_tid = wire_to_trainer(tw)
                    tgt_sl = tsl
            actor_sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(actor_sp)
            if mon is not None:
                mon.last_move_used = move_name
                if move_name not in mon.moves:
                    mon.moves.append(move_name)
            used_mega = pending_mega_slot.pop((tid, sl), False)
            if _norm_id(move_name) in _PROTECT_STREAK_MOVES:
                used_protect_this_turn[tid][sl] = True
                if cur_turn_snap is not None:
                    cur_turn_snap.events.protects.append(f"{tid}:{actor_sp}")
            set_slot_action(
                tid,
                sl,
                RecordedSlotAction(
                    actor_species=actor_sp,
                    kind="move",
                    move_name=move_name,
                    target_trainer=tgt_tid,
                    target_slot_letter=tgt_sl,
                    used_mega=used_mega,
                    summary=f"{actor_sp}: {move_name}{' [MEGA]' if used_mega else ''}",
                ),
            )

        elif cmd == "cant" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            reason = toks[3].strip()
            actor_sp = active_by_slot[tid][sl] or nick
            set_slot_action(
                tid,
                sl,
                RecordedSlotAction(
                    actor_species=actor_sp,
                    kind="flinched",
                    flinched_or_blocked=True,
                    summary=f"{actor_sp}: Blocked ({reason})",
                ),
            )
            if cur_turn_snap is not None:
                cur_turn_snap.events.flinches.append({"trainer": tid, "species": actor_sp, "reason": reason})

        elif cmd in ("-damage", "-heal") and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            hp_pct, fainted = _parse_hp_token(toks[3])
            status = _parse_status_token(toks[3])
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                mon.current_hp_pct = hp_pct
                mon.fainted = fainted
                if status:
                    mon.status = status

        elif cmd == "faint" and len(toks) >= 3:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                mon.current_hp_pct = 0.0
                mon.fainted = True
            if cur_turn_snap is not None:
                cur_turn_snap.events.faints.append({"trainer": tid, "species": sp})

        elif cmd == "-enditem" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                mon.item = None

        elif cmd in ("-boost", "-unboost") and len(toks) >= 5:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            stat_k = toks[3].strip().lower()
            delta = int(toks[4].strip()) * (1 if cmd == "-boost" else -1)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None and stat_k in mon.boosts:
                mon.boosts[stat_k] = max(-6, min(6, mon.boosts[stat_k] + delta))

        elif cmd == "-status" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                mon.status = toks[3].strip().lower()

        elif cmd == "-curestatus" and len(toks) >= 3:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                mon.status = None

        elif cmd == "-weather" and len(toks) >= 3:
            w_raw = toks[2].strip()
            is_upkeep = any("[upkeep]" in t.lower() for t in toks[3:])
            mapped = _WEATHER_MAP.get(_norm_id(w_raw))
            if not is_upkeep:
                weather = mapped
                weather_turns = 5 if mapped else 0
                if cur_turn_snap is not None and mapped:
                    cur_turn_snap.events.weather_changes.append(mapped)

        elif cmd == "-fieldstart" and len(toks) >= 3:
            eff = toks[2].lower()
            if "trick room" in eff:
                trick_room_turns = 5
            else:
                for k, v in _TERRAIN_MAP.items():
                    if k in _norm_id(eff):
                        terrain = v
                        terrain_turns = 5

        elif cmd == "-fieldend" and len(toks) >= 3:
            eff = toks[2].lower()
            if "trick room" in eff:
                trick_room_turns = 0
            else:
                for k in _TERRAIN_MAP:
                    if k in _norm_id(eff):
                        terrain = None
                        terrain_turns = 0

        elif cmd == "-sidestart" and len(toks) >= 4:
            tid = wire_to_trainer(toks[2].strip()[:2])
            eff = _norm_id(toks[3])
            if "tailwind" in eff:
                tailwind_turns[tid] = 4
            elif "reflect" in eff:
                reflect_turns[tid] = 5
            elif "lightscreen" in eff:
                light_screen_turns[tid] = 5
            elif "auroraveil" in eff:
                aurora_veil_turns[tid] = 5

        elif cmd == "-sideend" and len(toks) >= 4:
            tid = wire_to_trainer(toks[2].strip()[:2])
            eff = _norm_id(toks[3])
            if "tailwind" in eff:
                tailwind_turns[tid] = 0
            elif "reflect" in eff:
                reflect_turns[tid] = 0
            elif "lightscreen" in eff:
                light_screen_turns[tid] = 0
            elif "auroraveil" in eff:
                aurora_veil_turns[tid] = 0

        elif cmd == "-crit" and len(toks) >= 3 and cur_turn_snap is not None:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick
            cur_turn_snap.events.crits.append({"target_trainer": tid, "target_species": sp})

        elif cmd == "-miss" and len(toks) >= 3 and cur_turn_snap is not None:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick
            cur_turn_snap.events.misses.append({"actor_trainer": tid, "actor_species": sp})

        elif cmd == "upkeep":
            in_upkeep_phase = True
            # Decrement field timers & update active_turns + protect streak at End-of-Turn
            if weather_turns > 0:
                weather_turns -= 1
                if weather_turns == 0:
                    weather = None
            if terrain_turns > 0:
                terrain_turns -= 1
                if terrain_turns == 0:
                    terrain = None
            if trick_room_turns > 0:
                trick_room_turns -= 1
            for tid in ("trainer_1", "trainer_2"):
                if tailwind_turns[tid] > 0:
                    tailwind_turns[tid] -= 1
                if reflect_turns[tid] > 0:
                    reflect_turns[tid] -= 1
                if light_screen_turns[tid] > 0:
                    light_screen_turns[tid] -= 1
                if aurora_veil_turns[tid] > 0:
                    aurora_veil_turns[tid] -= 1
                for sl in ("a", "b"):
                    sp = active_by_slot[tid][sl]
                    if sp:
                        mon = teams[tid].get_pokemon(sp)
                        if mon is not None and not mon.fainted:
                            mon.active_turns += 1
                            mon.used_protect_last_turn = used_protect_this_turn[tid][sl]

    # Backfill full brought 4-mon battle_roster into every turn snapshot so Turn 1..N
    # have exact ground-truth benches (since we are reviewing a completed replay!).
    for snap in turns:
        snap.battle_state.trainer_1.battle_roster = list(brought_order["trainer_1"])
        snap.battle_state.trainer_2.battle_roster = list(brought_order["trainer_2"])

    return ParsedReplay(
        replay_id=replay_id,
        format_name=format_name,
        raw_log_text=log_text,
        trainer_1_name=team_1.trainer_name,
        trainer_2_name=team_2.trainer_name,
        pov_is_right_side=(pov_wire == _WIRE_RIGHT),
        winner=winner,
        trainer_1_preview=list(team_1.team_preview),
        trainer_2_preview=list(team_2.team_preview),
        trainer_1_brought=list(brought_order["trainer_1"]),
        trainer_2_brought=list(brought_order["trainer_2"]),
        turns=turns,
    )
