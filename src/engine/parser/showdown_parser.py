# -*- coding: utf-8 -*-
"""Universal Pokémon Showdown Battle & Team Parser under Regulation M-C.

Parses Pokémon Showdown client chat logs (both Bo1 spectator/chat logs and Bo3 OTS logs)
and raw Showdown team paste exports.
Enforces strict trainer_1 (POV/User) and trainer_2 (Opponent) identifiers.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    DamageObservation,
    ParsedBattle,
    ParsedPokemon,
    ParsedTeam,
    SpeedObservation,
    StatSpread,
)

# ---------------------------------------------------------------------------
# Move Priorities Database & Built-in Fallbacks
# ---------------------------------------------------------------------------

DEFAULT_MOVE_PRIORITIES: Dict[str, int] = {
    # +5
    "Helping Hand": 5,
    # +4
    "Protect": 4,
    "Detect": 4,
    "Magic Coat": 4,
    "Snatch": 4,
    "King's Shield": 4,
    "Spiky Shield": 4,
    "Baneful Bunker": 4,
    "Obstruct": 4,
    "Silk Trap": 4,
    "Burning Bulwark": 4,
    # +3
    "Fake Out": 3,
    "Quick Guard": 3,
    "Wide Guard": 3,
    "Crafty Shield": 3,
    # +2
    "Extreme Speed": 2,
    "Feint": 2,
    "Follow Me": 2,
    "Rage Powder": 2,
    "First Impression": 2,
    "Ally Switch": 2,
    # +1
    "Aqua Jet": 1,
    "Bullet Punch": 1,
    "Ice Shard": 1,
    "Mach Punch": 1,
    "Shadow Sneak": 1,
    "Sucker Punch": 1,
    "Vacuum Wave": 1,
    "Accelerock": 1,
    "Water Shuriken": 1,
    "Baby-Doll Eyes": 1,
    # -1
    "Vital Throw": -1,
    # -3
    "Focus Punch": -3,
    # -4
    "Avalanche": -4,
    "Revenge": -4,
    # -5
    "Counter": -5,
    "Mirror Coat": -5,
    # -6
    "Circle Throw": -6,
    "Dragon Tail": -6,
    "Roar": -6,
    "Whirlwind": -6,
    "Teleport": -6,
    # -7
    "Trick Room": -7,
}

_CACHED_MOVE_PRIORITIES: Optional[Dict[str, int]] = None


def _load_move_priorities() -> Dict[str, int]:
    """Load move priorities from the in-memory DuckDB `moves` view via `VGCDataRegistry`."""
    global _CACHED_MOVE_PRIORITIES
    if _CACHED_MOVE_PRIORITIES is not None:
        return _CACHED_MOVE_PRIORITIES

    priorities = dict(DEFAULT_MOVE_PRIORITIES)
    try:
        from engine.db_registry import get_registry

        rows = get_registry().query("SELECT name, priority FROM moves;")
        for row in rows:
            name = row.get("name")
            prio = row.get("priority", 0)
            if name:
                priorities[str(name)] = int(prio or 0)
    except Exception:
        pass

    _CACHED_MOVE_PRIORITIES = priorities
    return _CACHED_MOVE_PRIORITIES


def get_move_priority(
    move_name: str,
    terrain: Optional[str] = None,
    ability: Optional[str] = None,
    is_status: bool = False,
) -> int:
    """Calculate effective move priority under active battlefield conditions.

    Handles special rules:
    - Grassy Glide receives +1 priority under Grassy Terrain.
    - Prankster grants +1 priority to status moves.
    """
    priorities = _load_move_priorities()
    base_priority = priorities.get(move_name, 0)

    # Grassy Glide in Grassy Terrain
    if move_name == "Grassy Glide" and terrain == "Grassy":
        return base_priority + 1

    # Prankster modifier for status moves
    if ability == "Prankster" and is_status:
        return base_priority + 1

    return base_priority


# ---------------------------------------------------------------------------
# Showdown Team Paste Parser
# ---------------------------------------------------------------------------


def parse_showdown_paste(paste_text: str) -> Dict[str, ParsedPokemon]:
    """Parse a Showdown team export block into a dictionary of ParsedPokemon.

    Supports Regulation M-C Stat Points (EV line <= 32 SPs) and standard cartridge EVs.
    Handles both blank-line-separated blocks and continuous Open Team Sheet lines.
    Keys are canonical species names.
    """
    pokemon_dict: Dict[str, ParsedPokemon] = {}
    lines = [line.strip() for line in paste_text.splitlines() if line.strip()]
    if not lines:
        return pokemon_dict

    # Identify starting line indices of each Pokemon entry
    set_start_indices: List[int] = []
    skip_prefixes = (
        "-",
        "*",
        "Ability:",
        "Level:",
        "EVs:",
        "IVs:",
        "Shiny:",
        "Tera Type:",
        "Open team sheet",
        "Format:",
        "Rated battle",
        "Species Clause",
        "Item Clause",
    )

    for i, line in enumerate(lines):
        if line.startswith(skip_prefixes) or line.endswith("Nature"):
            continue
        if "@" in line:
            set_start_indices.append(i)
        elif i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line.startswith(("Ability:", "Level:", "EVs:", "IVs:", "-", "*")) or next_line.endswith("Nature"):
                set_start_indices.append(i)

    if not set_start_indices and lines:
        # Fallback: assume first line is header if not empty
        set_start_indices = [0]

    for idx, start_i in enumerate(set_start_indices):
        end_i = set_start_indices[idx + 1] if idx + 1 < len(set_start_indices) else len(lines)
        block_lines = lines[start_i:end_i]
        if not block_lines:
            continue

        header = block_lines[0]
        if header.startswith(skip_prefixes):
            continue

        # Header format: Species (Gender) @ Item OR Nickname (Species) (Gender) @ Item
        item: Optional[str] = None
        if "@" in header:
            mon_part, item_part = header.split("@", 1)
            item = item_part.strip()
        else:
            mon_part = header

        mon_part = mon_part.strip()

        # Check trailing gender: (M) or (F)
        gender: Optional[str] = None
        gender_match = re.search(r"\(([MF])\)$", mon_part)
        if gender_match:
            gender = gender_match.group(1)
            mon_part = mon_part[:gender_match.start()].strip()

        # Check for Nickname (Species)
        species_match = re.search(r"\((.+?)\)$", mon_part)
        if species_match:
            nickname = mon_part[:species_match.start()].strip()
            species = species_match.group(1).strip()
        else:
            nickname = None
            species = mon_part.strip()

        ability: Optional[str] = None
        nature: Optional[str] = None
        level = 50
        spread_dict: Dict[str, int] = {}
        iv_dict: Dict[str, int] = {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31}
        moves: List[str] = []

        for line in block_lines[1:]:
            if line.startswith("Ability:"):
                ability = line.split(":", 1)[1].strip()
            elif line.startswith("Level:"):
                try:
                    level = int(line.split(":", 1)[1].strip())
                except ValueError:
                    level = 50
            elif line.startswith("EVs:"):
                # e.g. "EVs: 2 HP / 12 Def / 28 SpA / 24 Spe"
                parts = line.split(":", 1)[1].split("/")
                for part in parts:
                    m = re.search(r"(\d+)\s*([A-Za-z]+)", part)
                    if m:
                        val = int(m.group(1))
                        stat_name = m.group(2).lower()
                        if stat_name in ("hp", "atk", "def", "spa", "spd", "spe"):
                            spread_dict[stat_name] = val
            elif line.startswith("IVs:"):
                # e.g. "IVs: 0 Atk"
                parts = line.split(":", 1)[1].split("/")
                for part in parts:
                    m = re.search(r"(\d+)\s*([A-Za-z]+)", part)
                    if m:
                        val = int(m.group(1))
                        stat_name = m.group(2).lower()
                        if stat_name in iv_dict:
                            iv_dict[stat_name] = val
            elif line.endswith("Nature"):
                nature = line.split()[0].strip()
            elif line.startswith(("-", "*")):
                move_name = line.lstrip("-* ").strip()
                moves.append(move_name)

        # Mega Stone detection
        is_mega = False
        mega_stone = None
        if item and (item.endswith("ite") or item.endswith("ite X") or item.endswith("ite Y") or "ite" in item):
            mega_stone = item

        spread = StatSpread.from_evs_or_sp(spread_dict)

        parsed_mon = ParsedPokemon(
            species=species,
            base_species=species.split("-Mega")[0] if "-Mega" in species else species,
            nickname=nickname,
            item=item,
            ability=ability,
            nature=nature,
            level=level,
            gender=gender,
            spread=spread,
            ivs=iv_dict,
            moves=moves,
            is_mega=is_mega,
            mega_stone=mega_stone,
        )
        pokemon_dict[species] = parsed_mon
        if nickname:
            pokemon_dict[nickname] = parsed_mon

    return pokemon_dict


# ---------------------------------------------------------------------------
# Showdown Chat Log Parser (Bo1 & Bo3)
# ---------------------------------------------------------------------------


def _clean_trainer_name(raw: str) -> str:
    """Clean trainer display name by stripping symbols and excess whitespace."""
    return re.sub(r"^[☆★]+", "", raw).strip()


def parse_showdown_chat_log(
    log_text: str,
    pov_trainer: Optional[str] = None,
    user_team_paste: Optional[str] = None,
    format_hint: str = "auto",
) -> ParsedBattle:
    """Parse a client Showdown chat log into a fully typed ParsedBattle model.

    Args:
        log_text: Complete text copy-pasted from Showdown spectator or client chat.
        pov_trainer: Display name of the user / POV player. Mapped to trainer_1.
                     If omitted, the first joined trainer is designated trainer_1.
        user_team_paste: Optional team export paste for trainer_1 to ensure 100% exact stats.
        format_hint: Format override or 'auto' to detect from header.

    Returns:
        ParsedBattle instance containing trainer_1, trainer_2, turns, and empirical telemetry.
    """
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]

    battle = ParsedBattle()
    detected_trainers: List[str] = []

    # 1. Format and Bo3 Detection
    for line in lines:
        if "Game " in line and "best-of-3" in line:
            battle.is_bo3 = True
            m = re.search(r"Game\s+(\d+)\s+of", line)
            if m:
                battle.game_number = int(m.group(1))
        if line.startswith("[Gen 9") or "Reg M-C" in line:
            battle.format = line

    # 2. Extract Trainer Names
    for line in lines:
        # Match '☆TrainerA and ☆TrainerB joined'
        m = re.search(r"^(?:☆|★)?(.+?)\s+and\s+(?:☆|★)?(.+?)\s+joined", line)
        if m:
            detected_trainers = [_clean_trainer_name(m.group(1)), _clean_trainer_name(m.group(2))]
            break
        # Match 'Battle started between TrainerA and TrainerB!'
        m2 = re.search(r"^Battle started between\s+(.+?)\s+and\s+(.+?)!", line)
        if m2:
            detected_trainers = [_clean_trainer_name(m2.group(1)), _clean_trainer_name(m2.group(2))]
            break

    if not detected_trainers:
        # Fallback to '<Trainer>'s team:' pattern
        for line in lines:
            m3 = re.search(r"^(.+?)'s team:", line)
            if m3:
                name = _clean_trainer_name(m3.group(1))
                if name not in detected_trainers:
                    detected_trainers.append(name)
            if len(detected_trainers) == 2:
                break

    # Determine trainer_1 (POV) and trainer_2 (Opponent)
    if detected_trainers:
        if pov_trainer:
            clean_pov = _clean_trainer_name(pov_trainer).lower()
            if len(detected_trainers) >= 2 and detected_trainers[1].lower() == clean_pov:
                trainer_1_name = detected_trainers[1]
                trainer_2_name = detected_trainers[0]
            else:
                trainer_1_name = detected_trainers[0]
                trainer_2_name = detected_trainers[1] if len(detected_trainers) > 1 else "trainer_2"
        else:
            trainer_1_name = detected_trainers[0]
            trainer_2_name = detected_trainers[1] if len(detected_trainers) > 1 else "trainer_2"
    else:
        trainer_1_name = _clean_trainer_name(pov_trainer) if pov_trainer else "trainer_1"
        trainer_2_name = "trainer_2"

    battle.trainer_1 = ParsedTeam(trainer_name=trainer_1_name)
    battle.trainer_2 = ParsedTeam(trainer_name=trainer_2_name)

    # 3. Extract Team Preview (6 Pokémon)
    for i, line in enumerate(lines):
        m = re.search(r"^(.+?)'s team:\s*(.*)", line)
        if m:
            raw_trainer = _clean_trainer_name(m.group(1))
            roster_str = m.group(2).strip()
            if not roster_str and i + 1 < len(lines):
                roster_str = lines[i + 1]
            mons = [p.strip() for p in roster_str.split("/") if p.strip()]
            target_team = (
                battle.trainer_1 if raw_trainer.lower() == battle.trainer_1.trainer_name.lower() else battle.trainer_2
            )
            target_team.team_preview = mons
            # Also create placeholder ParsedPokemon entries
            for mon in mons:
                if mon not in target_team.pokemon_sets:
                    target_team.pokemon_sets[mon] = ParsedPokemon(
                        species=mon,
                        base_species=mon.split("-Mega")[0] if "-Mega" in mon else mon,
                    )

    # 4. Extract Open Team Sheets (Bo3)
    ots_chunks: Dict[str, List[str]] = {}
    current_ots_trainer: Optional[str] = None
    for line in lines:
        if line.startswith("Open team sheet for"):
            raw_name = line.replace("Open team sheet for", "").strip()
            current_ots_trainer = _clean_trainer_name(raw_name)
            ots_chunks[current_ots_trainer] = []
        elif current_ots_trainer:
            if line.startswith(("Battle timer", "Battle started", "Format:", "Rated battle")):
                current_ots_trainer = None
            else:
                ots_chunks[current_ots_trainer].append(line)

    for trainer_name, chunk_lines in ots_chunks.items():
        chunk_text = "\n".join(chunk_lines)
        parsed_sets = parse_showdown_paste(chunk_text)
        target_team = (
            battle.trainer_1 if trainer_name.lower() == battle.trainer_1.trainer_name.lower() else battle.trainer_2
        )
        target_team.pokemon_sets.update(parsed_sets)

    # 5. Overlay user_team_paste onto trainer_1
    if user_team_paste:
        exact_user_sets = parse_showdown_paste(user_team_paste)
        battle.trainer_1.pokemon_sets.update(exact_user_sets)
        if not battle.trainer_1.team_preview:
            battle.trainer_1.team_preview = list(exact_user_sets.keys())

    # 6. Parse Battle Events & Telemetry
    current_turn = 0
    weather: Optional[str] = None
    terrain: Optional[str] = None
    trainer_1_tailwind = False
    trainer_2_tailwind = False
    trick_room = False

    # Active mons and boosts: identifier -> dict
    trainer_1_active: Set[str] = set()
    trainer_2_active: Set[str] = set()
    boosts: Dict[str, Dict[str, int]] = {}

    # Turn action queue for speed inference
    turn_actions: List[Dict[str, Any]] = []
    last_move_used: Optional[Dict[str, Any]] = None
    pending_switch_out_mon: Optional[str] = None
    protect_moves = {
        "Protect",
        "Detect",
        "Spiky Shield",
        "King's Shield",
        "Baneful Bunker",
        "Silk Trap",
        "Burning Bulwark",
        "Wide Guard",
        "Quick Guard",
    }
    pivot_moves = {"Flip Turn", "U-turn", "Volt Switch", "Parting Shot", "Baton Pass", "Chilly Reception", "Shed Tail"}

    # Name mapping: nickname / display name -> canonical species
    name_to_species: Dict[str, str] = {}
    name_to_trainer: Dict[str, str] = {}

    def register_pokemon(display_name: str, species_name: str, trainer_id: str) -> None:
        name_to_species[display_name] = species_name
        name_to_species[species_name] = species_name
        name_to_trainer[display_name] = trainer_id
        name_to_trainer[species_name] = trainer_id
        if display_name not in boosts:
            boosts[display_name] = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
        target_team = battle.trainer_1 if trainer_id == "trainer_1" else battle.trainer_2
        pkm = target_team.get_pokemon(species_name)
        if pkm and display_name != species_name:
            pkm.nickname = display_name

    # Helper to add to battle roster
    def mark_brought(species_name: str, trainer_team: ParsedTeam) -> None:
        if species_name not in trainer_team.battle_roster and len(trainer_team.battle_roster) < 4:
            trainer_team.battle_roster.append(species_name)
        pkm = trainer_team.get_pokemon(species_name)
        if pkm:
            pkm.revealed_in_battle = True

    def remove_from_active(mon_identifier: str, trainer_team: ParsedTeam) -> None:
        pkm = trainer_team.get_pokemon(mon_identifier)
        canonical = pkm.base_species or pkm.species if pkm else mon_identifier
        for existing in list(trainer_team.active_slots):
            existing_pkm = trainer_team.get_pokemon(existing)
            if (
                existing.lower() == mon_identifier.lower()
                or existing.lower() == canonical.lower()
                or (existing_pkm and existing_pkm == pkm)
            ):
                trainer_team.active_slots.remove(existing)
        if pkm:
            pkm.active_turns = 0
            pkm.used_protect_last_turn = False
            pkm.last_move_used = None
            pkm.boosts = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
        if mon_identifier in boosts:
            boosts[mon_identifier] = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}

    def add_to_active(species_name: str, trainer_team: ParsedTeam) -> None:
        nonlocal pending_switch_out_mon
        pkm = trainer_team.get_pokemon(species_name)
        slot_key = pkm.base_species or pkm.species if pkm else species_name
        if slot_key not in trainer_team.active_slots:
            if len(trainer_team.active_slots) >= 2 and pending_switch_out_mon:
                remove_from_active(pending_switch_out_mon, trainer_team)
                pending_switch_out_mon = None
            if len(trainer_team.active_slots) < 2:
                trainer_team.active_slots.append(slot_key)
        if pkm:
            pkm.active_turns = 0 if current_turn == 0 else 1
            pkm.used_protect_last_turn = False
            pkm.last_move_used = None

    for line in lines:
        # --- Turn Marker ---
        turn_match = re.match(r"^Turn\s+(\d+)", line)
        if turn_match:
            current_turn = int(turn_match.group(1))
            battle.turns_played = max(battle.turns_played, current_turn)
            for team in (battle.trainer_1, battle.trainer_2):
                for active_key in team.active_slots:
                    pkm = team.get_pokemon(active_key)
                    if pkm:
                        pkm.used_protect_last_turn = bool(pkm.last_move_used in protect_moves)
                        pkm.active_turns = pkm.active_turns + 1 if current_turn > 1 or pkm.active_turns == 0 else 1
            turn_actions.clear()
            last_move_used = None
            pending_switch_out_mon = None
            continue

        # --- Explicit Switch-Out Lines ---
        withdrew_match = re.match(r"^(.+?)\s+withdrew\s+(.+?)!", line)
        if withdrew_match:
            trainer_part = _clean_trainer_name(withdrew_match.group(1))
            mon_part = withdrew_match.group(2).strip()
            target_team = (
                battle.trainer_1
                if trainer_part.lower() == battle.trainer_1.trainer_name.lower()
                else battle.trainer_2
            )
            remove_from_active(mon_part, target_team)
            continue

        comeback_match = re.match(r"^(.+?),\s+come back!", line)
        if comeback_match:
            mon_part = comeback_match.group(1).strip()
            remove_from_active(mon_part, battle.trainer_1)
            continue

        # --- Leads and Switch-ins ---
        # Perspective 1: 'Go! Charizard!' or 'Go! Arcanine (Arcanine-Hisui)!'
        go_match = re.match(r"^Go!\s+(.+?)!", line)
        if go_match:
            content = go_match.group(1).strip()
            m_nick = re.match(r"^(.+?)\s*\((.+?)\)", content)
            if m_nick:
                nick = m_nick.group(1).strip()
                spec = m_nick.group(2).strip()
            else:
                nick = content
                spec = content
            register_pokemon(nick, spec, "trainer_1")
            mark_brought(spec, battle.trainer_1)
            add_to_active(spec, battle.trainer_1)
            trainer_1_active.add(nick)
            if current_turn == 0 and len(battle.trainer_1.leads) < 2:
                battle.trainer_1.leads = battle.trainer_1.leads + (spec,)
            continue

        # '<Trainer> sent out <Mon>!'
        sent_match = re.match(r"^(.+?)\s+sent out\s+(.+?)!", line)
        if sent_match:
            trainer_part = _clean_trainer_name(sent_match.group(1))
            mon_part = sent_match.group(2).strip()
            m_nick = re.match(r"^(.+?)\s*\((.+?)\)", mon_part)
            if m_nick:
                nick = m_nick.group(1).strip()
                spec = m_nick.group(2).strip()
            else:
                nick = mon_part
                spec = mon_part

            target_team = (
                battle.trainer_1
                if trainer_part.lower() == battle.trainer_1.trainer_name.lower()
                else battle.trainer_2
            )
            trainer_id = "trainer_1" if target_team == battle.trainer_1 else "trainer_2"
            register_pokemon(nick, spec, trainer_id)
            mark_brought(spec, target_team)
            add_to_active(spec, target_team)

            if trainer_id == "trainer_1":
                trainer_1_active.add(nick)
                if current_turn == 0 and len(battle.trainer_1.leads) < 2:
                    battle.trainer_1.leads = battle.trainer_1.leads + (spec,)
            else:
                trainer_2_active.add(nick)
                if current_turn == 0 and len(battle.trainer_2.leads) < 2:
                    battle.trainer_2.leads = battle.trainer_2.leads + (spec,)
            continue

        # '<Mon> was dragged out!'
        drag_match = re.match(r"^(.+?)\s+was dragged out!", line)
        if drag_match:
            mon_name = drag_match.group(1).strip()
            # Determine which team this mon belongs to
            if mon_name in battle.trainer_1.team_preview or mon_name in battle.trainer_1.pokemon_sets:
                register_pokemon(mon_name, mon_name, "trainer_1")
                mark_brought(mon_name, battle.trainer_1)
                add_to_active(mon_name, battle.trainer_1)
                trainer_1_active.add(mon_name)
            else:
                register_pokemon(mon_name, mon_name, "trainer_2")
                mark_brought(mon_name, battle.trainer_2)
                add_to_active(mon_name, battle.trainer_2)
                trainer_2_active.add(mon_name)
            continue

        # --- Mega Evolution ---
        mega_match = re.search(r"^(?:The opposing\s+)?(.+?)\s+has Mega Evolved into\s+(.+?)!", line)
        if mega_match:
            mon_nick = mega_match.group(1).strip()
            mega_species = mega_match.group(2).strip()
            is_opposing = line.startswith("The opposing ")
            target_team = battle.trainer_2 if is_opposing else battle.trainer_1
            pkm = target_team.get_pokemon(mon_nick)
            if pkm:
                pkm.is_mega = True
                pkm.species = mega_species
            continue

        # Mega Stone activation
        stone_match = re.search(r"^(?:The opposing\s+)?(.+?)'s\s+(.+?)\s+is reacting to the Key Stone!", line)
        if stone_match:
            mon_nick = stone_match.group(1).strip()
            stone = stone_match.group(2).strip()
            is_opposing = line.startswith("The opposing ")
            target_team = battle.trainer_2 if is_opposing else battle.trainer_1
            pkm = target_team.get_pokemon(mon_nick)
            if pkm:
                pkm.mega_stone = stone
                pkm.item = stone
            continue

        # --- Ability Announcements ---
        # e.g. '[The opposing Rillaboom's Grassy Surge]' or '[Charizard's Drought]'
        ab_match = re.search(r"^\[(?:The opposing\s+)?(.+?)'s\s+(.+?)\]", line)
        if ab_match:
            mon_nick = ab_match.group(1).strip()
            ability_name = ab_match.group(2).strip()
            is_opposing = line.startswith("[The opposing ")
            target_team = battle.trainer_2 if is_opposing else battle.trainer_1
            pkm = target_team.get_pokemon(mon_nick)
            if pkm:
                pkm.ability = ability_name

            # Check weather / terrain setters
            if ability_name == "Drought":
                weather = "Sun"
            elif ability_name == "Drizzle":
                weather = "Rain"
            elif ability_name == "Sand Stream":
                weather = "Sand"
            elif ability_name == "Snow Warning":
                weather = "Snow"
            elif ability_name == "Grassy Surge":
                terrain = "Grassy"
            elif ability_name == "Electric Surge":
                terrain = "Electric"
            elif ability_name == "Psychic Surge":
                terrain = "Psychic"
            elif ability_name == "Misty Surge":
                terrain = "Misty"
            continue

        # --- Weather & Terrain Text Lines ---
        if "The sunlight turned harsh" in line:
            weather = "Sun"
        elif "started to rain" in line or "Rain continues" in line:
            weather = "Rain"
        elif "sandstorm kicked up" in line:
            weather = "Sand"
        elif "Grass grew to cover the battlefield" in line:
            terrain = "Grassy"
        elif "surged across the battlefield" in line:
            terrain = "Electric"
        elif "Mist swirled" in line:
            terrain = "Misty"

        # --- Field Modifiers: Tailwind & Trick Room ---
        if "Tailwind blew from behind your team" in line:
            trainer_1_tailwind = True
        elif "Tailwind blew from behind the opposing team" in line:
            trainer_2_tailwind = True
        elif "twisted the dimensions" in line:
            trick_room = not trick_room

        # --- Stat Stage Changes ---
        # e.g. "The opposing Starmie's evasiveness rose sharply!"
        stat_boost_match = re.search(
            r"^(?:The opposing\s+)?(.+?)'s\s+(Attack|Defense|Sp\. Atk|Sp\. Def|Speed|evasiveness|accuracy)\s+(rose sharply|rose|fell sharply|fell)!",
            line,
        )
        if stat_boost_match:
            mon_nick = stat_boost_match.group(1).strip()
            stat_raw = stat_boost_match.group(2).strip().lower()
            direction = stat_boost_match.group(3).strip()
            is_opposing_boost = line.startswith("The opposing ")
            target_boost_team = battle.trainer_2 if is_opposing_boost else battle.trainer_1

            stat_key = {
                "attack": "atk",
                "defense": "def",
                "sp. atk": "spa",
                "sp. def": "spd",
                "speed": "spe",
                "evasiveness": "evasion",
                "accuracy": "accuracy",
            }.get(stat_raw, "atk")

            delta = 2 if "sharply" in direction else 1
            if "fell" in direction:
                delta = -delta

            if mon_nick not in boosts:
                boosts[mon_nick] = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
            boosts[mon_nick][stat_key] = max(-6, min(6, boosts[mon_nick][stat_key] + delta))
            pkm_boost = target_boost_team.get_pokemon(mon_nick)
            if pkm_boost:
                pkm_boost.boosts[stat_key] = boosts[mon_nick][stat_key]
            continue

        # --- Move Execution ---
        # e.g. "Arcanine used Flare Blitz!" or "The opposing Rillaboom used Grassy Glide!"
        move_match = re.search(r"^(?:The opposing\s+)?(.+?)\s+used\s+(.+?)!", line)
        if move_match:
            mon_nick = move_match.group(1).strip()
            move_name = move_match.group(2).strip()
            is_opposing = line.startswith("The opposing ")
            trainer_id = "trainer_2" if is_opposing else "trainer_1"
            target_team = battle.trainer_2 if is_opposing else battle.trainer_1

            pkm = target_team.get_pokemon(mon_nick)
            if pkm:
                if move_name not in pkm.moves:
                    pkm.moves.append(move_name)
                pkm.last_move_used = move_name
            if move_name in pivot_moves:
                pending_switch_out_mon = mon_nick

            ability_val = pkm.ability if pkm else None
            # Check status category for prankster
            is_status_move = move_name in ("Protect", "Minimize", "Swords Dance", "Tailwind", "Parting Shot", "Will-O-Wisp", "Thunder Wave", "Hypnosis", "Coil")
            prio = get_move_priority(move_name, terrain=terrain, ability=ability_val, is_status=is_status_move)

            # Record empirical SpeedObservation if previous move this turn had SAME priority
            for prev in turn_actions:
                if prev["priority"] == prio and prev["attacker"] != mon_nick:
                    # Previous executed before current in the same priority bracket!
                    faster_team_id = prev["trainer"]
                    slower_team_id = trainer_id
                    obs = SpeedObservation(
                        faster_mon=prev["attacker"],
                        slower_mon=mon_nick,
                        turn=current_turn,
                        priority=prio,
                        faster_move=prev["move"],
                        slower_move=move_name,
                        weather=weather,
                        terrain=terrain,
                        tailwind_active_faster=(trainer_1_tailwind if faster_team_id == "trainer_1" else trainer_2_tailwind),
                        tailwind_active_slower=(trainer_1_tailwind if slower_team_id == "trainer_1" else trainer_2_tailwind),
                        trick_room_active=trick_room,
                        notes="Speed tie or faster stat",
                    )
                    battle.speed_observations.append(obs)

            current_action = {
                "attacker": mon_nick,
                "move": move_name,
                "priority": prio,
                "trainer": trainer_id,
            }
            turn_actions.append(current_action)
            last_move_used = current_action
            continue

        # --- Damage Observations ---
        # e.g. "(The opposing Starmie lost 97% of its health!)" or "(Arcanine lost 75% of its health!)"
        dmg_match = re.search(r"^\((?:The opposing\s+)?(.+?)\s+lost\s+(\d+)% of its health!\)", line)
        if dmg_match and last_move_used:
            def_nick = dmg_match.group(1).strip()
            dmg_pct = float(dmg_match.group(2))
            is_opposing_def = "(The opposing " in line
            target_def_team = battle.trainer_2 if is_opposing_def else battle.trainer_1
            pkm_def = target_def_team.get_pokemon(def_nick)
            if pkm_def:
                pkm_def.current_hp_pct = max(0.0, pkm_def.current_hp_pct - dmg_pct)

            attacker_mon = last_move_used["attacker"]
            dmg_obs = DamageObservation(
                attacker=attacker_mon,
                defender=def_nick,
                move=last_move_used["move"],
                damage_pct=dmg_pct,
                turn=current_turn,
                weather=weather,
                terrain=terrain,
                attacker_boosts=dict(boosts.get(attacker_mon, {})),
                defender_boosts=dict(boosts.get(def_nick, {})),
            )
            battle.damage_observations.append(dmg_obs)
            continue

        # --- Faints ---
        faint_match = re.search(r"^(?:The opposing\s+)?(.+?)\s+fainted!", line)
        if faint_match:
            faint_nick = faint_match.group(1).strip()
            is_opposing = line.startswith("The opposing ")
            target_team = battle.trainer_2 if is_opposing else battle.trainer_1
            pkm = target_team.get_pokemon(faint_nick)
            if pkm:
                pkm.fainted = True
                pkm.current_hp_pct = 0.0
            remove_from_active(faint_nick, target_team)
            if faint_nick in trainer_1_active:
                trainer_1_active.remove(faint_nick)
            if faint_nick in trainer_2_active:
                trainer_2_active.remove(faint_nick)
            continue

        # --- Item Triggers (Red Card, Leftovers, etc.) ---
        item_match = re.search(r"^(?:The opposing\s+)?(.+?)\s+held up its\s+(.+?)\s+against\s+(.+?)!", line)
        if item_match:
            mon_nick = item_match.group(1).strip()
            item_revealed = item_match.group(2).strip()
            victim_raw = item_match.group(3).replace("the opposing ", "").strip()
            is_opposing = line.startswith("The opposing ")
            target_team = battle.trainer_2 if is_opposing else battle.trainer_1
            pkm = target_team.get_pokemon(mon_nick)
            if pkm and not pkm.item:
                pkm.item = item_revealed
            if item_revealed == "Red Card":
                pending_switch_out_mon = victim_raw
            continue

        # --- Forfeit and Winner Resolution ---
        if "forfeited." in line:
            battle.forfeit = True
            forfeit_trainer = _clean_trainer_name(line.split("forfeited.")[0])
            if forfeit_trainer.lower() == battle.trainer_1.trainer_name.lower():
                battle.winner = battle.trainer_2.trainer_name
            else:
                battle.winner = battle.trainer_1.trainer_name

        win_match = re.search(r"^(.+?)\s+won the battle!", line)
        if win_match:
            battle.winner = _clean_trainer_name(win_match.group(1))

        # --- Ratings Tracking ---
        rating_match = re.search(r"^(.+?)'s rating:\s*(\d+)\s*→\s*(\d+)", line)
        if rating_match:
            r_trainer = _clean_trainer_name(rating_match.group(1))
            pre_r = int(rating_match.group(2))
            post_r = int(rating_match.group(3))
            if r_trainer.lower() == battle.trainer_1.trainer_name.lower():
                battle.trainer_1_rating = (pre_r, post_r)
            elif r_trainer.lower() == battle.trainer_2.trainer_name.lower():
                battle.trainer_2_rating = (pre_r, post_r)

    battle.weather = weather
    battle.terrain = terrain
    battle.trainer_1_tailwind = trainer_1_tailwind
    battle.trainer_2_tailwind = trainer_2_tailwind
    battle.trick_room = trick_room
    return battle
