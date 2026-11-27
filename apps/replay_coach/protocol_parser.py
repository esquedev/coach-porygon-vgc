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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.db_registry import get_registry
from engine.parser.models import (
    DamageObservation,
    HpTickObservation,
    ParsedBattle,
    ParsedPokemon,
    ParsedTeam,
    SpeedObservation,
)

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
    "hail": "Snow",  # Legacy Showdown replay compatibility
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


def _build_duckdb_name_lookups() -> Tuple[
    Dict[str, str],
    Dict[str, str],
    Dict[str, str],
    Dict[str, str],
    Dict[str, Dict[str, Any]],
]:
    """Build normalized-id -> canonical-name maps and move metadata from DuckDB `VGCDataRegistry`."""
    reg = get_registry()
    moves_map: Dict[str, str] = {}
    move_meta_map: Dict[str, Dict[str, Any]] = {}
    items_map: Dict[str, str] = {}
    abilities_map: Dict[str, str] = {}
    species_map: Dict[str, str] = {}

    for r in reg.query("SELECT id, name, priority, category, type, basePower, target, recoil FROM moves;"):
        m_name = str(r["name"])
        moves_map[_norm_id(str(r["id"]))] = m_name
        moves_map[_norm_id(m_name)] = m_name
        raw_recoil = r.get("recoil")
        recoil_frac: Optional[float] = None
        if isinstance(raw_recoil, (list, tuple)) and len(raw_recoil) == 2:
            try:
                num_r, den_r = float(raw_recoil[0]), float(raw_recoil[1])
                if den_r > 0:
                    recoil_frac = num_r / den_r
            except (TypeError, ValueError):
                pass
        move_meta_map[m_name] = {
            "priority": int(r.get("priority") or 0),
            "category": str(r.get("category") or "Status"),
            "type": str(r.get("type") or "Normal"),
            "basePower": int(r.get("basePower") or 0),
            "target": str(r.get("target") or "normal"),
            "recoil_frac": recoil_frac,
        }
    for r in reg.query("SELECT id, name FROM items;"):
        items_map[_norm_id(str(r["id"]))] = str(r["name"])
        items_map[_norm_id(str(r["name"]))] = str(r["name"])
    for r in reg.query("SELECT id, name FROM abilities;"):
        abilities_map[_norm_id(str(r["id"]))] = str(r["name"])
        abilities_map[_norm_id(str(r["name"]))] = str(r["name"])
    for r in reg.query("SELECT id, name FROM pokedex;"):
        species_map[_norm_id(str(r["id"]))] = str(r["name"])
        species_map[_norm_id(str(r["name"]))] = str(r["name"])
    return species_map, moves_map, items_map, abilities_map, move_meta_map


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
    speed_observations: List[SpeedObservation] = field(default_factory=list)
    damage_observations: List[DamageObservation] = field(default_factory=list)
    hp_tick_observations: List[HpTickObservation] = field(default_factory=list)
    trainer_1_showteam_ots: Dict[str, ParsedPokemon] = field(default_factory=dict)
    trainer_2_showteam_ots: Dict[str, ParsedPokemon] = field(default_factory=dict)
    game_index: int = 1
    raw_trainer_2_name: str = ""
    trainer_1_elo: Optional[int] = None
    trainer_2_elo: Optional[int] = None
    wire_game_number: Optional[int] = None
    is_anonymized_opponent: bool = False


def format_showdown_opponent_label(elo: Optional[int] = None) -> str:
    """Format a privacy-safe anonymized legend for Showdown ladder opponents."""
    if elo is not None and int(elo) > 0:
        return f"Showdown Opponent (Elo {int(elo)})"
    return "Showdown Opponent (Unrated)"


def extract_wire_game_number(raw_input: str) -> Optional[int]:
    """Extract the official Bo3 game number (`1`, `2`, `3`) from `|uhtml|bestof|` wire headers."""
    log_text, _ = extract_protocol_log(raw_input)
    m_bo = re.search(r"\|uhtml\|bestof\|[^\n]*?Game\s+(\d+)", log_text, flags=re.IGNORECASE)
    if not m_bo:
        m_bo = re.search(r"<strong>\s*Game\s+(\d+)\s*</strong>\s+of", log_text, flags=re.IGNORECASE)
    if m_bo:
        try:
            gnum = int(m_bo.group(1))
            if 1 <= gnum <= 9:
                return gnum
        except ValueError:
            pass
    return None


def anonymize_showdown_log_text(
    raw_log: str,
    opp_wire: str,
    raw_opp_name: str,
    anon_label: str,
) -> str:
    """Scrub opponent Showdown nickname from wire player/chat/timer/uhtml/win/HTML lines without mutating battle tags."""
    if not raw_log or not raw_opp_name or raw_opp_name == anon_label:
        return raw_log
    opp_lower = raw_opp_name.strip().lower()
    opp_slug = _norm_id(raw_opp_name)
    pat = re.compile(re.escape(raw_opp_name), flags=re.IGNORECASE)
    pat_slug = re.compile(re.escape(opp_slug), flags=re.IGNORECASE) if opp_slug else None
    out_lines: List[str] = []
    for ln in raw_log.splitlines():
        if ln.startswith("|"):
            toks = ln.split("|")
            cmd = toks[1] if len(toks) > 1 else ""
            if cmd == "player" and len(toks) >= 4 and toks[2].strip() == opp_wire and toks[3].strip():
                toks[3] = anon_label
                out_lines.append("|".join(toks))
                continue
            if cmd == "win" and len(toks) >= 3 and toks[2].strip().lower() == opp_lower:
                toks[2] = anon_label
                out_lines.append("|".join(toks))
                continue
            if cmd in ("j", "l", "n", "J", "L", "N") and len(toks) >= 3 and opp_lower in toks[2].lower():
                toks[2] = f"☆{anon_label}"
                out_lines.append("|".join(toks))
                continue
            if cmd in ("c", "c:") and len(toks) >= 4:
                speaker_idx = 3 if cmd == "c:" else 2
                if speaker_idx < len(toks) and opp_lower in toks[speaker_idx].lower():
                    toks[speaker_idx] = f"☆{anon_label}"
                    out_lines.append("|".join(toks))
                    continue
            if cmd in ("", "raw", "uhtml", "uhtmlchange", "html", "inactive", "inactiveoff", "message") and len(toks) >= 3:
                for idx in range(2, len(toks)):
                    if opp_lower in toks[idx].lower():
                        toks[idx] = pat.sub(anon_label, toks[idx])
                out_lines.append("|".join(toks))
                continue
        elif opp_lower in ln.lower() or (opp_slug and f"/users/{opp_slug}" in ln.lower()):
            cleaned = pat.sub(anon_label, ln)
            if pat_slug is not None and "/users/" in cleaned.lower():
                cleaned = re.sub(rf"/users/{re.escape(opp_slug)}", "/users/showdown-opponent", cleaned, flags=re.IGNORECASE)
            out_lines.append(cleaned)
            continue
        out_lines.append(ln)
    return "\n".join(out_lines)


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


def extract_replay_sort_key(raw_input: str, filename: str = "") -> Tuple[int, int, int, str, int, str]:
    """Compute a deterministic chronological sort key `(bestof_game, first_ts, replay_num, base_stem, dup_num, filename)`.

    Solves Chrome's duplicate download naming inversion where `foo (1).html` (Game 2)
    sorts lexicographically before `foo.html` (Game 1) because ASCII space < '.'.
    """
    log_text, replay_id = extract_protocol_log(raw_input)

    # 1. Explicit Bo3 game number (`|uhtml|bestof|<h2><strong>Game 2</strong> ...`)
    bestof_game = 99
    m_bo = re.search(r"\|uhtml\|bestof\|[^\n]*?Game\s+(\d+)", log_text, flags=re.IGNORECASE)
    if not m_bo:
        m_bo = re.search(r"<strong>\s*Game\s+(\d+)\s*</strong>\s+of", log_text, flags=re.IGNORECASE)
    if m_bo:
        try:
            bestof_game = int(m_bo.group(1))
        except ValueError:
            pass

    # 2. Earliest Unix battle timestamp (`|t:|1795683873`)
    first_ts = 10**12
    m_ts = re.search(r"\|t:\|(\d{9,})", log_text)
    if m_ts:
        try:
            first_ts = int(m_ts.group(1))
        except ValueError:
            pass

    # 3. Monotonic numeric Showdown room ID (`gen9...-2719701193-...`)
    replay_num = 10**12
    m_rid = re.search(r"-(\d{6,})(?:-|$)", replay_id or "")
    if m_rid:
        try:
            replay_num = int(m_rid.group(1))
        except ValueError:
            pass

    # 4. Filename Chrome-duplicate-safe fallback (`foo.html` -> dup 0, `foo (1).html` -> dup 1)
    fname = str(filename or "").strip()
    stem = re.sub(r"\.(html?|log|txt)$", "", fname, flags=re.IGNORECASE)
    m_dup = re.search(r"\s*\((\d+)\)$", stem)
    if m_dup:
        dup_num = int(m_dup.group(1))
        base_stem = stem[: m_dup.start()].strip().lower()
    else:
        dup_num = 0
        base_stem = stem.strip().lower()

    return (bestof_game, first_ts, replay_num, base_stem, dup_num, fname.lower())


def sort_replay_entries(entries: Sequence[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[int]]:
    """Sort 1..N replay dicts into true sequential Bo3 order (`Game 1 -> Game 2 -> Game 3`)."""
    indexed = [
        (extract_replay_sort_key(str(it.get("raw_input") or ""), str(it.get("filename") or "")), idx, it)
        for idx, it in enumerate(entries)
    ]
    indexed.sort(key=lambda tup: (tup[0], tup[1]))
    sorted_items = [tup[2] for tup in indexed]
    orig_order = [tup[1] for tup in indexed]
    return sorted_items, orig_order


def assign_bo3_game_numbers(entries: Sequence[Dict[str, str]]) -> List[int]:
    """Assign true Game #s (`1`, `2`, `3`) preserving wire `|uhtml|bestof| Game N` when unique.

    If a user uploads only Game 2 and Game 3 of a Bo3, this returns `[2, 3]` rather than
    mislabeling them `[1, 2]`. Falls back cleanly to sequential `1..N` if wire headers are
    missing or duplicated (e.g., repeated single-game samples).
    """
    n = len(entries)
    if n == 0:
        return []
    wire_nums = [extract_wire_game_number(str(it.get("raw_input") or "")) for it in entries]
    if all(w is not None for w in wire_nums) and len(set(wire_nums)) == n:
        return [int(w) for w in wire_nums if w is not None]
    # Hybrid: if some have unique wire numbers and others lack them, fill gaps deterministically
    assigned: List[int] = []
    used: set[int] = set()
    for idx, w in enumerate(wire_nums, 1):
        if w is not None and w not in used:
            assigned.append(int(w))
            used.add(int(w))
        else:
            cand = idx
            while cand in used:
                cand += 1
            assigned.append(cand)
            used.add(cand)
    return assigned


def _parse_hp_detailed(hp_token: str) -> Tuple[float, bool, Optional[int], Optional[int]]:
    """Parse Showdown HP string -> `(hp_pct, fainted, cur_hp_exact, max_hp_exact)`.

    When Showdown logs exact integer HP (e.g., `94/167`, `175/175`), returns `(pct, fainted, 94, 167)`.
    When Showdown logs percentage HP (e.g., `32/100`), returns `(32.0, False, None, None)`.
    """
    clean = (hp_token or "").strip()
    if not clean:
        return 100.0, False, None, None
    parts = clean.split()
    first = parts[0]
    if first == "0" or (len(parts) > 1 and parts[1].lower() == "fnt"):
        return 0.0, True, 0, None
    if "/" in first:
        num_s, den_s = first.split("/", 1)
        try:
            num_i, den_i = int(float(num_s)), int(float(den_s))
            if den_i <= 0:
                return 0.0, True, 0, None
            pct = max(0.0, min(100.0, (num_i / den_i) * 100.0))
            if den_i != 100:
                return pct, num_i <= 0, num_i, den_i
            return pct, num_i <= 0, None, None
        except ValueError:
            pass
    return 100.0, False, None, None


def format_evless_ots_paste(mons: Sequence[ParsedPokemon] | Dict[str, ParsedPokemon]) -> str:
    """Format a sequence/dict of `ParsedPokemon` into a clean Champions EV-less OTS Showdown paste."""
    items = list(mons.values()) if isinstance(mons, dict) else list(mons)
    blocks: List[str] = []
    seen: set[str] = set()
    for mon in items:
        sp = mon.base_species or mon.species.split("-Mega")[0]
        key = _norm_id(sp)
        if key in seen:
            continue
        seen.add(key)
        item = mon.initial_item or mon.item
        header = f"{sp} @ {item}" if item else sp
        lines = [header, f"Ability: {mon.ability or 'None'}", f"Level: {mon.level or 50}"]
        if mon.nature:
            lines.append(f"{mon.nature} Nature")
        for mv in (mon.moves or [])[:4]:
            lines.append(f"- {mv}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks).strip()


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
                initial_item=item,
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
    game_index: int = 1,
    anonymize_opponent: bool = False,
) -> ParsedReplay:
    """Parse an official Showdown `.html` or pipe-protocol replay into per-turn snapshots
    and lossless empirical Speed, Damage, and HP-tick observations for Bo1/Bo3 SP inference.

    Merges exact 66-SP spreads (and fallback items/moves) from the OTS Database
    while preserving exact replay `|showteam|` items/moves/natures and exact turn-by-turn
    HP, boosts, weather, Trick Room, Protect chains, and `active_turns`.
    """
    log_text, replay_id = extract_protocol_log(raw_input)
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    wire_game_num = extract_wire_game_number(log_text)

    species_map, moves_map, items_map, abilities_map, move_meta_map = _build_duckdb_name_lookups()

    wire_players: Dict[str, str] = {}
    wire_elos: Dict[str, Optional[int]] = {}
    raw_rating_by_name: Dict[str, int] = {}
    format_name = "[Gen 9 Champions] VGC 2026 Reg M-C (Bo3)"
    winner: Optional[str] = None

    # Pass 1: identify player names, Elo ratings & format
    for ln in lines:
        if not ln.startswith("|"):
            continue
        toks = ln.split("|")
        cmd = toks[1] if len(toks) > 1 else ""
        if cmd == "player" and len(toks) >= 4 and toks[3].strip():
            side_tok = toks[2].strip()
            wire_players[side_tok] = toks[3].strip()
            if len(toks) >= 6 and toks[5].strip().isdigit():
                elo_val = int(toks[5].strip())
                if elo_val > 0:
                    wire_elos[side_tok] = elo_val
        elif cmd == "raw" and len(toks) >= 3 and "rating:" in toks[2].lower():
            m_rat = re.search(r"([A-Za-z0-9_\-\.\s]+?)'s rating:\s*(\d{3,4})", toks[2], flags=re.IGNORECASE)
            if m_rat:
                raw_rating_by_name[m_rat.group(1).strip().lower()] = int(m_rat.group(2))
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

    t1_raw_name = wire_players.get(pov_wire, "trainer_1")
    t2_raw_name = wire_players.get(opp_wire, "trainer_2")
    t1_elo = wire_elos.get(pov_wire) or raw_rating_by_name.get(t1_raw_name.lower())
    t2_elo = wire_elos.get(opp_wire) or raw_rating_by_name.get(t2_raw_name.lower())

    t2_display_name = format_showdown_opponent_label(t2_elo) if anonymize_opponent else t2_raw_name
    if anonymize_opponent and winner and winner.strip().lower() == t2_raw_name.strip().lower():
        winner = t2_display_name

    def wire_to_trainer(w: str) -> str:
        return "trainer_1" if w == pov_wire else "trainer_2"

    team_1 = ParsedTeam(trainer_name=t1_raw_name)
    team_2 = ParsedTeam(trainer_name=t2_display_name)
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

    # Lossless empirical telemetry accumulators for Zero-AI 66-SP constraint solving
    speed_observations: List[SpeedObservation] = []
    damage_observations: List[DamageObservation] = []
    hp_tick_observations: List[HpTickObservation] = []
    showteam_ots: Dict[str, Dict[str, ParsedPokemon]] = {"trainer_1": {}, "trainer_2": {}}
    hp_exact_by_mon: Dict[Tuple[str, str], Tuple[int, int]] = {}  # (tid, base_sp_key) -> (cur_hp, max_hp)
    helping_hand_slots: set[Tuple[str, str]] = set()
    cur_turn_num: int = 0

    # Turn-level speed & move context trackers
    turn_speed_entries: List[Dict[str, Any]] = []
    turn_speed_invalidated: bool = False
    switchin_ability_entries: List[Dict[str, Any]] = []
    in_lead_entry_window: bool = False
    current_move_ctx: Optional[Dict[str, Any]] = None
    last_damage_by_attacker: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _effective_move_priority(mon: Optional[ParsedPokemon], move_name: str, cur_terrain: Optional[str]) -> int:
        meta = move_meta_map.get(move_name) or {}
        prio = int(meta.get("priority", 0))
        if mon is None:
            return prio
        cat = str(meta.get("category") or "Status")
        mtype = str(meta.get("type") or "Normal")
        ab = (mon.ability or "").strip()
        if ab == "Prankster" and cat == "Status":
            prio += 1
        elif ab == "Gale Wings" and mtype == "Flying" and mon.current_hp_pct >= 99.9:
            prio += 1
        elif ab == "Triage" and move_name in {
            "Absorb", "Drain Punch", "Draining Kiss", "Floral Healing", "Giga Drain",
            "Heal Order", "Heal Pulse", "Healing Wish", "Horn Leech", "Leech Life",
            "Lunar Blessing", "Mega Drain", "Milk Drink", "Moonlight", "Morning Sun",
            "Oblivion Wing", "Parabolic Charge", "Purify", "Recover", "Rest", "Roost",
            "Shore Up", "Slack Off", "Soft-Boiled", "Strength Sap", "Swallow",
            "Synthesis", "Wish",
        }:
            prio += 3
        elif move_name == "Grassy Glide" and cur_terrain == "Grassy":
            prio += 1
        return prio

    def _record_ability_entry(tid: str, sl: str, sp: str, label: str) -> None:
        if not in_lead_entry_window:
            return
        mon = teams[tid].get_pokemon(sp)
        if mon is None:
            return
        entry = {
            "tid": tid,
            "sl": sl,
            "species": mon.species,
            "base_species": mon.base_species or mon.species.split("-Mega")[0],
            "is_mega": mon.is_mega,
            "spe_stage": int(mon.boosts.get("spe", 0)),
            "unburden": bool(mon.unburden_active),
            "item": mon.item,
            "ability": mon.ability,
            "status": mon.status,
            "label": label,
            "weather": weather,
            "terrain": terrain,
            "tw_t1": tailwind_turns["trainer_1"] > 0,
            "tw_t2": tailwind_turns["trainer_2"] > 0,
            "tr": trick_room_turns > 0,
        }
        # Compare against earlier opposite-trainer simultaneous switch-in ability triggers
        for prev in switchin_ability_entries:
            if prev["tid"] != tid:
                speed_observations.append(
                    SpeedObservation(
                        faster_mon=prev["species"],
                        slower_mon=entry["species"],
                        turn=cur_turn_num,
                        priority=0,
                        faster_move=f"[Entry: {prev['label']}]",
                        slower_move=f"[Entry: {entry['label']}]",
                        weather=prev["weather"],
                        terrain=prev["terrain"],
                        tailwind_active_faster=prev["tw_t1"] if prev["tid"] == "trainer_1" else prev["tw_t2"],
                        tailwind_active_slower=entry["tw_t1"] if entry["tid"] == "trainer_1" else entry["tw_t2"],
                        trick_room_active=prev["tr"],
                        notes="Turn-0 simultaneous switch-in ability speed order",
                        faster_trainer=prev["tid"],
                        slower_trainer=tid,
                        source="switch_in_ability",
                        faster_is_mega=prev["is_mega"],
                        slower_is_mega=entry["is_mega"],
                        faster_spe_stage=prev["spe_stage"],
                        slower_spe_stage=entry["spe_stage"],
                        faster_unburden=prev["unburden"],
                        slower_unburden=entry["unburden"],
                        faster_item=prev["item"],
                        slower_item=entry["item"],
                        faster_ability=prev["ability"],
                        slower_ability=entry["ability"],
                        faster_status=prev["status"],
                        slower_status=entry["status"],
                        game_index=game_index,
                    )
                )
        switchin_ability_entries.append(entry)

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
            if not existing.initial_item and (db_mon.initial_item or db_mon.item):
                existing.initial_item = db_mon.initial_item or db_mon.item
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
                showteam_ots[tid][_norm_id(pm.base_species or pm.species)] = copy.deepcopy(pm)
                existing = ensure_pokemon(tid, pm.species)
                # Replay |showteam| is authoritative for actual items/moves/ability/nature
                if pm.item:
                    existing.item = pm.item
                    existing.initial_item = pm.item
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
            in_lead_entry_window = True
            switchin_ability_entries.clear()

        elif cmd == "turn" and len(toks) >= 3:
            t_num = int(toks[2].strip())
            cur_turn_num = t_num
            in_upkeep_phase = False
            in_lead_entry_window = False
            switchin_ability_entries.clear()
            turn_speed_entries.clear()
            turn_speed_invalidated = False
            helping_hand_slots.clear()
            current_move_ctx = None
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
            hp_pct, fainted, hp_cur_ex, hp_max_ex = _parse_hp_detailed(toks[4])
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
                    prev_mon.unburden_active = False
                    prev_mon.must_recharge = False

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
            mon.unburden_active = False
            mon.must_recharge = False
            mon.boosts = {k: 0 for k in mon.boosts}
            if hp_cur_ex is not None and hp_max_ex is not None:
                hp_exact_by_mon[(tid, _norm_id(mon.base_species or mon.species))] = (hp_cur_ex, hp_max_ex)
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
                # Update Mega Evolution ability immediately from DuckDB pokedex!
                dex_row = get_registry().get_pokemon(new_sp)
                if dex_row and isinstance(dex_row.get("abilities"), dict):
                    mega_ab = dex_row["abilities"].get("0")
                    if mega_ab:
                        mon.ability = str(mega_ab)
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

        elif cmd == "-ability" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            ab_name = _canonical_db_name(toks[3].strip(), abilities_map)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None and ab_name:
                mon.ability = ab_name
                _record_ability_entry(tid, sl, mon.species, ab_name)

        elif cmd == "-singleturn" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            eff = toks[3].strip().lower()
            if "helping hand" in eff:
                helping_hand_slots.add((tid, sl))

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
            extra_tags = " ".join(toks[5:]) if len(toks) > 5 else ""
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
                mon.must_recharge = False
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

            # 1. Empirical same-priority Speed observation (skip After You / Quash / Instruct / Dancer)
            is_forced_order_move = move_name in ("After You", "Quash", "Instruct") or "[from] ability: Dancer" in extra_tags
            if is_forced_order_move:
                turn_speed_invalidated = True
            elif mon is not None and not turn_speed_invalidated and "[still]" not in extra_tags:
                eff_prio = _effective_move_priority(mon, move_name, terrain)
                cur_entry = {
                    "tid": tid,
                    "sl": sl,
                    "species": mon.species,
                    "move": move_name,
                    "priority": eff_prio,
                    "is_mega": mon.is_mega,
                    "spe_stage": int(mon.boosts.get("spe", 0)),
                    "unburden": bool(mon.unburden_active),
                    "item": mon.item,
                    "ability": mon.ability,
                    "status": mon.status,
                    "weather": weather,
                    "terrain": terrain,
                    "tw_t1": tailwind_turns["trainer_1"] > 0,
                    "tw_t2": tailwind_turns["trainer_2"] > 0,
                    "tr": trick_room_turns > 0,
                }
                for prev in turn_speed_entries:
                    if prev["tid"] != tid and prev["priority"] == eff_prio:
                        # Only compare if Trick Room & Tailwind & Weather did not change between the two moves
                        if (
                            prev["tr"] == cur_entry["tr"]
                            and prev["tw_t1"] == cur_entry["tw_t1"]
                            and prev["tw_t2"] == cur_entry["tw_t2"]
                            and prev["weather"] == cur_entry["weather"]
                            and prev["terrain"] == cur_entry["terrain"]
                        ):
                            speed_observations.append(
                                SpeedObservation(
                                    faster_mon=prev["species"],
                                    slower_mon=cur_entry["species"],
                                    turn=cur_turn_num,
                                    priority=eff_prio,
                                    faster_move=prev["move"],
                                    slower_move=move_name,
                                    weather=cur_entry["weather"],
                                    terrain=cur_entry["terrain"],
                                    tailwind_active_faster=prev["tw_t1"] if prev["tid"] == "trainer_1" else prev["tw_t2"],
                                    tailwind_active_slower=cur_entry["tw_t1"] if tid == "trainer_1" else cur_entry["tw_t2"],
                                    trick_room_active=cur_entry["tr"],
                                    notes=f"G{game_index} T{cur_turn_num} prio {eff_prio}",
                                    faster_trainer=prev["tid"],
                                    slower_trainer=tid,
                                    source="turn_order",
                                    faster_is_mega=prev["is_mega"],
                                    slower_is_mega=cur_entry["is_mega"],
                                    faster_spe_stage=prev["spe_stage"],
                                    slower_spe_stage=cur_entry["spe_stage"],
                                    faster_unburden=prev["unburden"],
                                    slower_unburden=cur_entry["unburden"],
                                    faster_item=prev["item"],
                                    slower_item=cur_entry["item"],
                                    faster_ability=prev["ability"],
                                    slower_ability=cur_entry["ability"],
                                    faster_status=prev["status"],
                                    slower_status=cur_entry["status"],
                                    game_index=game_index,
                                )
                            )
                turn_speed_entries.append(cur_entry)

            # 2. Initialize active move context for empirical DamageObservation capture
            m_meta = move_meta_map.get(move_name) or {}
            m_target = str(m_meta.get("target") or "normal")
            is_spread_move = m_target in ("allAdjacentFoes", "allAdjacent")
            spread_multi = False
            if is_spread_move:
                spread_match = re.search(r"\[spread\]\s*([^\|\n]+)", extra_tags)
                if spread_match:
                    spread_targets = [x.strip() for x in spread_match.group(1).split(",") if x.strip()]
                    spread_multi = len(spread_targets) >= 2
                else:
                    # Fallback to live target count on the field
                    opp_tid_c = "trainer_2" if tid == "trainer_1" else "trainer_1"
                    alive_cnt = 0
                    for s_l in ("a", "b"):
                        o_sp = active_by_slot[opp_tid_c][s_l]
                        if o_sp:
                            o_m = teams[opp_tid_c].get_pokemon(o_sp)
                            if o_m is not None and not o_m.fainted:
                                alive_cnt += 1
                    if m_target == "allAdjacent":
                        p_sl = "b" if sl == "a" else "a"
                        p_sp = active_by_slot[tid][p_sl]
                        if p_sp:
                            p_m = teams[tid].get_pokemon(p_sp)
                            if p_m is not None and not p_m.fainted:
                                alive_cnt += 1
                    spread_multi = alive_cnt >= 2

            current_move_ctx = {
                "attacker_tid": tid,
                "attacker_sl": sl,
                "attacker_sp": mon.species if mon is not None else actor_sp,
                "attacker_is_mega": bool(mon.is_mega) if mon is not None else False,
                "attacker_item": mon.item if mon is not None else None,
                "attacker_ability": mon.ability if mon is not None else None,
                "attacker_burned": (mon.status == "brn") if mon is not None else False,
                "attacker_hp_pct": float(mon.current_hp_pct) if mon is not None else 100.0,
                "attacker_boosts": dict(mon.boosts) if mon is not None else {},
                "move_name": move_name,
                "move_cat": str(m_meta.get("category") or "Status"),
                "move_recoil_frac": m_meta.get("recoil_frac"),
                "is_spread_multi_target": spread_multi,
                "helping_hand": (tid, sl) in helping_hand_slots,
                "weather": weather,
                "terrain": terrain,
                "pending_crits": set(),
                "pending_eff": {},
                "obs_by_target": {},
                "boosts_include_charge_spa": False,
                "is_charge_turn": "[still]" in extra_tags,
            }

        elif cmd == "-mustrecharge" and len(toks) >= 3:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                mon.must_recharge = True

        elif cmd == "cant" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            reason = toks[3].strip()
            actor_sp = active_by_slot[tid][sl] or nick
            mon_cant = teams[tid].get_pokemon(actor_sp)
            if reason.lower() == "recharge":
                if mon_cant is not None:
                    mon_cant.must_recharge = False
                set_slot_action(
                    tid,
                    sl,
                    RecordedSlotAction(
                        actor_species=actor_sp,
                        kind="recharge",
                        flinched_or_blocked=True,
                        summary=f"{actor_sp}: Recharge (forced)",
                    ),
                )
            else:
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

        elif cmd in ("-supereffective", "-resisted") and len(toks) >= 3:
            if current_move_ctx is not None:
                wire_s, sl, _ = _extract_slot_ident(toks[2])
                tid = wire_to_trainer(wire_s)
                current_move_ctx["pending_eff"][(tid, sl)] = (
                    "super_effective" if cmd == "-supereffective" else "resisted"
                )

        elif cmd in ("-damage", "-heal") and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            hp_pct, fainted, hp_cur_ex, hp_max_ex = _parse_hp_detailed(toks[3])
            status = _parse_status_token(toks[3])
            from_tag = " ".join(toks[4:]).lower() if len(toks) > 4 else ""
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                prev_pct = float(mon.current_hp_pct)
                mon_key = (tid, _norm_id(mon.base_species or mon.species))
                prev_exact = hp_exact_by_mon.get(mon_key)
                if prev_exact is not None and hp_max_ex is None and fainted:
                    hp_max_ex = prev_exact[1]
                    hp_cur_ex = 0
                exact_delta: Optional[int] = None
                if prev_exact is not None and hp_cur_ex is not None:
                    exact_delta = max(0, prev_exact[0] - hp_cur_ex)
                if hp_cur_ex is not None and hp_max_ex is not None:
                    hp_exact_by_mon[mon_key] = (hp_cur_ex, hp_max_ex)
                elif hp_cur_ex == 0 and prev_exact is not None:
                    hp_exact_by_mon[mon_key] = (0, prev_exact[1])

                # 1. Capture non-attack HP tick observations (Recoil, Sitrus, Leftovers, Life Orb, Burn, Sand)
                if "[from]" in from_tag:
                    if cmd == "-damage" and "recoil" in from_tag:
                        last_atk = last_damage_by_attacker.get((tid, sl))
                        src_exact = last_atk.get("exact_hp") if last_atk else None
                        rec_frac = last_atk.get("recoil_frac") if last_atk else (1.0 / 3.0)
                        hp_tick_observations.append(
                            HpTickObservation(
                                trainer=tid,
                                species=mon.species,
                                turn=cur_turn_num,
                                kind="recoil",
                                hp_pct_before=prev_pct,
                                hp_pct_after=hp_pct,
                                source_damage_hp_exact=src_exact,
                                recoil_fraction=rec_frac,
                                game_index=game_index,
                            )
                        )
                    elif cmd == "-heal" and "sitrus berry" in from_tag:
                        hp_tick_observations.append(
                            HpTickObservation(
                                trainer=tid,
                                species=mon.species,
                                turn=cur_turn_num,
                                kind="sitrus",
                                hp_pct_before=prev_pct,
                                hp_pct_after=hp_pct,
                                game_index=game_index,
                            )
                        )
                    elif cmd == "-heal" and "leftovers" in from_tag:
                        hp_tick_observations.append(
                            HpTickObservation(
                                trainer=tid,
                                species=mon.species,
                                turn=cur_turn_num,
                                kind="leftovers",
                                hp_pct_before=prev_pct,
                                hp_pct_after=hp_pct,
                                game_index=game_index,
                            )
                        )
                    elif cmd == "-heal" and "grassy terrain" in from_tag:
                        hp_tick_observations.append(
                            HpTickObservation(
                                trainer=tid,
                                species=mon.species,
                                turn=cur_turn_num,
                                kind="grassy",
                                hp_pct_before=prev_pct,
                                hp_pct_after=hp_pct,
                                game_index=game_index,
                            )
                        )
                    elif cmd == "-damage" and "life orb" in from_tag:
                        hp_tick_observations.append(
                            HpTickObservation(
                                trainer=tid,
                                species=mon.species,
                                turn=cur_turn_num,
                                kind="life_orb",
                                hp_pct_before=prev_pct,
                                hp_pct_after=hp_pct,
                                game_index=game_index,
                            )
                        )
                    elif cmd == "-damage" and ("brn" in from_tag or "sandstorm" in from_tag):
                        hp_tick_observations.append(
                            HpTickObservation(
                                trainer=tid,
                                species=mon.species,
                                turn=cur_turn_num,
                                kind="burn" if "brn" in from_tag else "sand",
                                hp_pct_before=prev_pct,
                                hp_pct_after=hp_pct,
                                game_index=game_index,
                            )
                        )

                # 2. Capture direct move DamageObservation (opposite trainer hit, non-[from] passive chip)
                elif (
                    cmd == "-damage"
                    and current_move_ctx is not None
                    and not current_move_ctx["is_charge_turn"]
                    and current_move_ctx["move_cat"] in ("Physical", "Special")
                    and current_move_ctx["attacker_tid"] != tid
                ):
                    atk_tid = current_move_ctx["attacker_tid"]
                    atk_sl = current_move_ctx["attacker_sl"]
                    is_phys_m = current_move_ctx["move_cat"] == "Physical"
                    infiltrator = current_move_ctx["attacker_ability"] == "Infiltrator"
                    scr_on = (not infiltrator) and (
                        (is_phys_m and (reflect_turns[tid] > 0 or aurora_veil_turns[tid] > 0))
                        or ((not is_phys_m) and (light_screen_turns[tid] > 0 or aurora_veil_turns[tid] > 0))
                    )
                    ally_sl = "b" if sl == "a" else "a"
                    ally_sp = active_by_slot[tid][ally_sl]
                    ally_mon = teams[tid].get_pokemon(ally_sp) if ally_sp else None
                    fg_on = (
                        ally_mon is not None
                        and not ally_mon.fainted
                        and ally_mon.ability == "Friend Guard"
                        and current_move_ctx["attacker_ability"] != "Mold Breaker"
                    )
                    tgt_key = (tid, sl)
                    is_crit_hit = tgt_key in current_move_ctx["pending_crits"]
                    existing_obs: Optional[DamageObservation] = current_move_ctx["obs_by_target"].get(tgt_key)
                    if existing_obs is not None:
                        # Multi-hit move (Dual Wingbeat, Scale Shot, Population Bomb, etc.)
                        existing_obs.hits += 1
                        existing_obs.hp_pct_after = hp_pct
                        existing_obs.damage_pct = max(0.0, existing_obs.hp_pct_before - hp_pct)
                        existing_obs.is_ohko = existing_obs.is_ohko or fainted
                        existing_obs.is_crit = existing_obs.is_crit or is_crit_hit
                        if exact_delta is not None and existing_obs.damage_hp_exact is not None:
                            existing_obs.damage_hp_exact += exact_delta
                    else:
                        new_obs = DamageObservation(
                            attacker=current_move_ctx["attacker_sp"],
                            defender=mon.species,
                            move=current_move_ctx["move_name"],
                            damage_pct=max(0.0, prev_pct - hp_pct),
                            turn=cur_turn_num,
                            weather=current_move_ctx["weather"],
                            terrain=current_move_ctx["terrain"],
                            attacker_boosts=dict(current_move_ctx["attacker_boosts"]),
                            defender_boosts=dict(mon.boosts),
                            is_crit=is_crit_hit,
                            effectiveness=current_move_ctx["pending_eff"].get(tgt_key),
                            hits=1,
                            attacker_trainer=atk_tid,
                            defender_trainer=tid,
                            damage_hp_exact=exact_delta,
                            defender_max_hp_exact=hp_max_ex,
                            hp_pct_before=prev_pct,
                            hp_pct_after=hp_pct,
                            is_ohko=fainted,
                            focus_sash_or_sturdy=False,
                            is_spread_multi_target=bool(current_move_ctx["is_spread_multi_target"]),
                            helping_hand=bool(current_move_ctx["helping_hand"]),
                            friend_guard=fg_on,
                            screen_active=scr_on,
                            attacker_burned=bool(current_move_ctx["attacker_burned"]),
                            attacker_is_mega=bool(current_move_ctx["attacker_is_mega"]),
                            defender_is_mega=bool(mon.is_mega),
                            attacker_item=current_move_ctx["attacker_item"],
                            defender_item=mon.item,
                            attacker_ability=current_move_ctx["attacker_ability"],
                            defender_ability=mon.ability,
                            attacker_hp_pct=float(current_move_ctx["attacker_hp_pct"]),
                            boosts_include_charge_spa=bool(current_move_ctx["boosts_include_charge_spa"]),
                            game_index=game_index,
                        )
                        damage_observations.append(new_obs)
                        current_move_ctx["obs_by_target"][tgt_key] = new_obs
                        if exact_delta is not None:
                            last_damage_by_attacker[(atk_tid, atk_sl)] = {
                                "exact_hp": exact_delta,
                                "recoil_frac": current_move_ctx["move_recoil_frac"],
                            }

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
                mon.must_recharge = False
            if cur_turn_snap is not None:
                cur_turn_snap.events.faints.append({"trainer": tid, "species": sp})

        elif cmd == "-enditem" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            ended_item = _canonical_db_name(toks[3].strip(), items_map)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                if ended_item == "Focus Sash" and current_move_ctx is not None:
                    obs_hit = current_move_ctx["obs_by_target"].get((tid, sl))
                    if obs_hit is not None:
                        obs_hit.focus_sash_or_sturdy = True
                if mon.ability == "Unburden":
                    mon.unburden_active = True
                    turn_speed_invalidated = True
                mon.item = None

        elif cmd == "-activate" and len(toks) >= 4:
            wire_s, sl, _ = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            if "sturdy" in toks[3].lower() and current_move_ctx is not None:
                obs_hit = current_move_ctx["obs_by_target"].get((tid, sl))
                if obs_hit is not None:
                    obs_hit.focus_sash_or_sturdy = True

        elif cmd in ("-boost", "-unboost") and len(toks) >= 5:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            stat_k = toks[3].strip().lower()
            delta = int(toks[4].strip()) * (1 if cmd == "-boost" else -1)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None and stat_k in mon.boosts:
                mon.boosts[stat_k] = max(-6, min(6, mon.boosts[stat_k] + delta))
                if stat_k == "spe" and not in_lead_entry_window:
                    turn_speed_invalidated = True
                # If Electro Shot / Meteor Beam boosts SpA right before hitting, keep current_move_ctx in sync!
                if (
                    current_move_ctx is not None
                    and current_move_ctx["attacker_tid"] == tid
                    and current_move_ctx["attacker_sl"] == sl
                    and current_move_ctx["move_name"] in ("Electro Shot", "Meteor Beam")
                    and stat_k == "spa"
                    and not current_move_ctx["obs_by_target"]
                ):
                    current_move_ctx["attacker_boosts"]["spa"] = mon.boosts["spa"]
                    current_move_ctx["boosts_include_charge_spa"] = True

        elif cmd == "-status" and len(toks) >= 4:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick_to_species[tid].get(nick.lower(), nick)
            mon = teams[tid].get_pokemon(sp)
            if mon is not None:
                st_code = toks[3].strip().lower()
                mon.status = st_code
                if st_code == "par":
                    turn_speed_invalidated = True

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
                # Check if weather came from a Turn-0 lead switch-in ability (`[of] pXa: Name`)
                of_tok = next((t for t in toks[3:] if "[of]" in t), "")
                ab_tok = next((t for t in toks[3:] if "[from] ability:" in t.lower()), "")
                if in_lead_entry_window and of_tok and ab_tok:
                    of_ident = of_tok.split("[of]", 1)[1].strip()
                    w_s, w_sl, w_nick = _extract_slot_ident(of_ident)
                    w_tid = wire_to_trainer(w_s)
                    w_sp = active_by_slot[w_tid][w_sl] or nick_to_species[w_tid].get(w_nick.lower(), w_nick)
                    ab_lbl = ab_tok.split("ability:", 1)[1].strip()
                    _record_ability_entry(w_tid, w_sl, w_sp, ab_lbl)
                weather = mapped
                weather_turns = 5 if mapped else 0
                if not in_lead_entry_window:
                    turn_speed_invalidated = True
                if cur_turn_snap is not None and mapped:
                    cur_turn_snap.events.weather_changes.append(mapped)

        elif cmd == "-fieldstart" and len(toks) >= 3:
            eff = toks[2].lower()
            of_tok = next((t for t in toks[3:] if "[of]" in t), "")
            ab_tok = next((t for t in toks[3:] if "[from] ability:" in t.lower()), "")
            if in_lead_entry_window and of_tok and ab_tok:
                of_ident = of_tok.split("[of]", 1)[1].strip()
                f_s, f_sl, f_nick = _extract_slot_ident(of_ident)
                f_tid = wire_to_trainer(f_s)
                f_sp = active_by_slot[f_tid][f_sl] or nick_to_species[f_tid].get(f_nick.lower(), f_nick)
                ab_lbl = ab_tok.split("ability:", 1)[1].strip()
                _record_ability_entry(f_tid, f_sl, f_sp, ab_lbl)
            if "trick room" in eff:
                trick_room_turns = 5
                turn_speed_invalidated = True
            else:
                for k, v in _TERRAIN_MAP.items():
                    if k in _norm_id(eff):
                        terrain = v
                        terrain_turns = 5
                        if not in_lead_entry_window:
                            turn_speed_invalidated = True

        elif cmd == "-fieldend" and len(toks) >= 3:
            eff = toks[2].lower()
            if "trick room" in eff:
                trick_room_turns = 0
                turn_speed_invalidated = True
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
                turn_speed_invalidated = True
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
                turn_speed_invalidated = True
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
            if current_move_ctx is not None:
                current_move_ctx["pending_crits"].add((tid, sl))

        elif cmd == "-miss" and len(toks) >= 3 and cur_turn_snap is not None:
            wire_s, sl, nick = _extract_slot_ident(toks[2])
            tid = wire_to_trainer(wire_s)
            sp = active_by_slot[tid][sl] or nick
            cur_turn_snap.events.misses.append({"actor_trainer": tid, "actor_species": sp})

        elif cmd == "upkeep":
            in_upkeep_phase = True
            current_move_ctx = None
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
    if turns:
        turns[-1].battle_state.speed_observations = list(speed_observations)
        turns[-1].battle_state.damage_observations = list(damage_observations)
        turns[-1].battle_state.hp_tick_observations = list(hp_tick_observations)

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
        speed_observations=speed_observations,
        damage_observations=damage_observations,
        hp_tick_observations=hp_tick_observations,
        trainer_1_showteam_ots=showteam_ots["trainer_1"],
        trainer_2_showteam_ots=showteam_ots["trainer_2"],
        game_index=game_index,
        raw_trainer_2_name=t2_raw_name,
        trainer_1_elo=t1_elo,
        trainer_2_elo=t2_elo,
        wire_game_number=wire_game_num,
        is_anonymized_opponent=bool(anonymize_opponent),
    )
