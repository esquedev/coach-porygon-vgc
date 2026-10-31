#!/usr/bin/env python3
"""
Coach Porygon VGC — Regulation M-C Roster & Legality Validator
Validates team pastes or individual Pokemon sets against authoritative Showdown Champions mod data:
1. Item Legality & Mega Stone compatibility (`data/Regulation_MC_Items.csv` & `data/pokedex_cache.json`)
2. Item Clause & Species Clause
3. Species Legality, Official Abilities, & Grounded Typings (`data/MC_Available_Pokemon.csv` & `data/pokedex_cache.json`)
4. Move Legality, Learnset Verification, & Strict STAB vs Non-STAB Coverage vs Status classification
5. 66-SP Deterministic Budget & Level 50 Stat Calculation (`Base + SP + 75` / `Base + SP + 20`)
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
ITEMS_CSV_PATH = REPO_ROOT / "data" / "Regulation_MC_Items.csv"
POKEMON_CSV_PATH = REPO_ROOT / "data" / "MC_Available_Pokemon.csv"
CACHE_PATH = REPO_ROOT / "data" / "pokedex_cache.json"

sys.path.insert(0, str(REPO_ROOT / "engine"))
from sp_calculator import validate_and_calculate_sp, STAT_ORDER, ev_to_sp, MAX_SINGLE_STAT_SP
from turn_simulator import MOVE_DB, BASE_STATS_DB


def to_id(text: str) -> str:
    """Normalize string to lowercase alphanumeric identifier."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse_pokemon_block(block: str) -> Optional[Dict]:
    """Parse single Showdown Pokémon block into structured attributes dictionary."""
    lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
    if not lines:
        return None

    first_line = lines[0]
    item = ""
    if "@" in first_line:
        name_part, item_part = first_line.split("@", 1)
        item = item_part.strip()
    else:
        name_part = first_line.strip()

    name_part = re.sub(r"\s*\([MFmf]\)\s*$", "", name_part).strip()

    match_nick = re.match(r"^(.+?)\s*\((.+?)\)$", name_part)
    if match_nick:
        species = match_nick.group(2).strip()
        nickname = match_nick.group(1).strip()
    else:
        species = name_part.strip()
        nickname = species

    ability = ""
    nature = "Hardy"
    level = 50
    sp_spread = {k: 0 for k in STAT_ORDER}
    moves: List[str] = []

    stat_map = {
        "hp": "hp",
        "atk": "atk",
        "def": "def",
        "spa": "spa",
        "spd": "spd",
        "spe": "spe",
    }

    for line in lines[1:]:
        if line.startswith("Ability:"):
            ability = line.split(":", 1)[1].strip()
        elif line.startswith("Level:"):
            try:
                level = int(line.split(":", 1)[1].strip())
            except ValueError:
                level = 50
        elif line.startswith("SP:") or line.startswith("SPs:") or line.startswith("EVs:") or line.startswith("Stat Points:"):
            raw_evs = line.split(":", 1)[1].strip()
            tokens = raw_evs.split("/")
            for token in tokens:
                token = token.strip()
                m = re.match(r"^(\d+)\s+([A-Za-z]+)$", token)
                if m:
                    val = int(m.group(1))
                    # Bijective EV -> SP mapping if value exceeds single-stat SP cap (e.g., 252 -> 32, 28 -> 4)
                    if val > MAX_SINGLE_STAT_SP:
                        val = ev_to_sp(val)
                    stat_key = m.group(2).lower()
                    if stat_key in stat_map:
                        sp_spread[stat_map[stat_key]] = val
        elif line.endswith("Nature"):
            nature_word = line.split()[0].strip()
            nature = nature_word
        elif line.startswith("-") or line.startswith("–"):
            move = line.lstrip("-–").strip()
            if move:
                moves.append(move)

    return {
        "species": species,
        "nickname": nickname,
        "item": item,
        "ability": ability,
        "nature": nature,
        "level": level,
        "sp_spread": sp_spread,
        "moves": moves,
        "raw_block": "\n".join(lines),
    }


def parse_showdown_paste(paste_text: str) -> List[Dict]:
    """Split multi-line team export into individual Pokémon blocks."""
    raw_blocks = re.split(r"\n\s*\n", paste_text.strip())
    parsed_pokemon = []
    for b in raw_blocks:
        p = parse_pokemon_block(b)
        if p and p["species"]:
            parsed_pokemon.append(p)
    return parsed_pokemon


# Populate COMMON_MOVE_DATA from MOVE_DB (515 legal Champions moves) + case-insensitive lookup
COMMON_MOVE_DATA: Dict[str, Dict] = {}
MOVE_LOOKUP_BY_ID: Dict[str, Dict] = {}
for mv_name, mv_info in MOVE_DB.items():
    COMMON_MOVE_DATA[mv_name] = mv_info
    MOVE_LOOKUP_BY_ID[to_id(mv_name)] = {"name": mv_name, **mv_info}


def load_cache_data() -> Dict:
    """Load pokedex cache data containing verified typings and learnsets."""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"species": {}, "moves": {}, "items": {}, "abilities": {}}


def load_legal_items() -> Dict[str, str]:
    """Load strict set of legal items from Regulation_MC_Items.csv."""
    items_map = {}
    if not ITEMS_CSV_PATH.exists():
        return items_map

    with open(ITEMS_CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return items_map

        for row in reader:
            for col_idx in [0, 3, 6]:
                if len(row) > col_idx:
                    raw_item = row[col_idx].strip()
                    if raw_item:
                        clean_item = raw_item.replace("’", "'").strip()
                        items_map[clean_item.lower()] = clean_item

    return items_map


def load_pokemon_registry() -> Dict[str, Dict]:
    """Load canonical Regulation M-C Pokémon registry from MC_Available_Pokemon.csv."""
    registry = {}
    cache = load_cache_data()

    for sp_name, sp_info in cache.get("species", {}).items():
        entry = {
            "name": sp_name,
            "id": sp_info.get("id", to_id(sp_name)),
            "types": sp_info.get("types", []),
            "base_hp": int(sp_info.get("hp", 0)),
            "base_atk": int(sp_info.get("atk", 0)),
            "base_def": int(sp_info.get("def", 0)),
            "base_spa": int(sp_info.get("spa", 0)),
            "base_spd": int(sp_info.get("spd", 0)),
            "base_spe": int(sp_info.get("spe", 0)),
            "abilities": list(sp_info.get("abilities", {}).values()),
            "requiredItem": sp_info.get("requiredItem"),
            "learnset": set(sp_info.get("learnset", [])),
        }
        registry[sp_name.lower()] = entry
        registry[to_id(sp_name)] = entry
        for alias in sp_info.get("aliases", []):
            registry[alias.lower()] = entry
            registry[to_id(alias)] = entry

    if POKEMON_CSV_PATH.exists():
        with open(POKEMON_CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("Pokémon") or row.get("Pokemon") or "").strip()
                if not name:
                    continue
                types = [t.strip() for t in [row.get("Type 1", ""), row.get("Type 2", "")] if t and t.strip()]
                abilities = [
                    row.get("Ability 1", "").strip(),
                    row.get("Ability 2", "").strip(),
                    row.get("Hidden Ability", "").strip(),
                ]
                abilities = [a for a in abilities if a]
                existing = registry.get(name.lower()) or registry.get(to_id(name)) or {}
                entry = {
                    "name": name,
                    "id": existing.get("id", to_id(name)),
                    "types": types,
                    "base_hp": int(float(row.get("Base HP", 0))),
                    "base_atk": int(float(row.get("Base Attack", 0))),
                    "base_def": int(float(row.get("Base Defense", 0))),
                    "base_spa": int(float(row.get("Base Sp. Attack", 0))),
                    "base_spd": int(float(row.get("Base Sp. Defense", 0))),
                    "base_spe": int(float(row.get("Speed", 0))),
                    "abilities": abilities or existing.get("abilities", []),
                    "requiredItem": (row.get("Required Item") or "").strip() or existing.get("requiredItem"),
                    "learnset": existing.get("learnset", set()),
                }
                registry[name.lower()] = entry
                registry[to_id(name)] = entry

                if name.startswith("Mega "):
                    rest = name[5:].strip()
                    parts = rest.split(" ")
                    if len(parts) == 2 and parts[1] in ("X", "Y", "Z"):
                        alias1 = f"{parts[0]}-Mega-{parts[1]}".lower()
                        alias2 = f"{parts[0]}-Mega ({parts[1]})".lower()
                        registry[alias1] = entry
                        registry[alias2] = entry
                    else:
                        alias = f"{rest}-Mega".lower()
                        registry[alias] = entry

        # Standard Showdown gender/form aliases
        if "basculegion" in registry:
            registry["basculegion-m"] = registry["basculegion"]
            registry[to_id("basculegion-m")] = registry["basculegion"]
        if "basculegion (female)" in registry:
            registry["basculegion-f"] = registry["basculegion (female)"]
            registry[to_id("basculegion-f")] = registry["basculegion (female)"]
        if "indeedee (female)" in registry:
            registry["indeedee-f"] = registry["indeedee (female)"]
            registry[to_id("indeedee-f")] = registry["indeedee (female)"]
        if "wash rotom" in registry:
            registry["rotom-wash"] = registry["wash rotom"]
            registry[to_id("rotom-wash")] = registry["wash rotom"]
        if "heat rotom" in registry:
            registry["rotom-heat"] = registry["heat rotom"]
            registry[to_id("rotom-heat")] = registry["heat rotom"]
        if "mow rotom" in registry:
            registry["rotom-mow"] = registry["mow rotom"]
            registry[to_id("rotom-mow")] = registry["mow rotom"]
        if "frost rotom" in registry:
            registry["rotom-frost"] = registry["frost rotom"]
            registry[to_id("rotom-frost")] = registry["frost rotom"]
        if "fan rotom" in registry:
            registry["rotom-fan"] = registry["fan rotom"]
            registry[to_id("rotom-fan")] = registry["fan rotom"]

    return registry


def get_pokemon_entry(species_name: str, registry: Dict[str, Dict]) -> Optional[Dict]:
    """Match species name against registry resolving standard and regional aliases."""
    clean_key = species_name.replace("’", "'").strip().lower()
    if clean_key in registry:
        return registry[clean_key]
    sid = to_id(species_name)
    if sid in registry:
        return registry[sid]
    if clean_key.endswith("-m") and clean_key[:-2] in registry:
        return registry[clean_key[:-2]]
    if clean_key.endswith("-f") and f"{clean_key[:-2]} (female)" in registry:
        return registry[f"{clean_key[:-2]} (female)"]
    base_name = re.sub(r"-Mega-[XYZxyz]|-Mega", "", species_name, flags=re.IGNORECASE).strip().lower()
    if base_name in registry:
        return registry[base_name]
    return None


def get_pokemon_types(species_name: str, registry: Dict[str, Dict]) -> List[str]:
    """Determine primary and secondary elemental types for species."""
    entry = get_pokemon_entry(species_name, registry)
    return entry["types"] if entry else []


def classify_move(move_name: str, species_types: List[str], ability: str = "") -> Dict:
    """Classify move as STAB, Coverage, or Status based on user typing."""
    clean_move = move_name.strip()
    mid = to_id(clean_move)
    move_info = COMMON_MOVE_DATA.get(clean_move) or MOVE_LOOKUP_BY_ID.get(mid) or {"type": "Unknown", "cat": "Unknown", "power": 0}
    m_type = move_info["type"]
    m_cat = move_info["cat"]
    is_legal_move = (clean_move in COMMON_MOVE_DATA) or (mid in MOVE_LOOKUP_BY_ID)

    ab_low = ability.lower()
    if m_type == "Normal" and m_cat != "Status":
        if ab_low == "pixilate":
            m_type = "Fairy"
        elif ab_low == "aerilate":
            m_type = "Flying"
        elif ab_low == "refrigerate":
            m_type = "Ice"
        elif ab_low == "dragonize":
            m_type = "Dragon"

    is_stab = (m_type in species_types) and (m_cat != "Status")

    if m_cat == "Status":
        classification = "Status"
    elif is_stab:
        stab_mult = "2.0x Adaptability" if ab_low == "adaptability" else "1.5x"
        classification = f"STAB ({stab_mult})"
    else:
        classification = "Non-STAB Coverage (1.0x)"

    return {
        "move": clean_move,
        "id": mid,
        "type": m_type,
        "cat": m_cat,
        "power": move_info.get("power", 0),
        "is_stab": is_stab,
        "is_legal_move": is_legal_move,
        "classification": classification,
    }


def validate_roster(paste_text: str) -> Dict:
    """Execute complete 5-point Regulation M-C legality and stat allocation verification."""
    parsed_pokemon = parse_showdown_paste(paste_text)
    if not parsed_pokemon:
        return {"is_valid": False, "errors": ["[ERROR]: No valid Pokemon sets parsed from paste."], "slots": []}

    legal_items = load_legal_items()
    pokemon_registry = load_pokemon_registry()
    cache = load_cache_data()
    items_cache = {to_id(k): v for k, v in cache.get("items", {}).items()}

    errors = []
    warnings = []
    slots_report = []
    seen_items: Set[str] = set()
    seen_species: Set[str] = set()

    for idx, p in enumerate(parsed_pokemon, 1):
        sp_name = p["species"]
        item = p["item"]
        nature = p["nature"]
        ability = p["ability"]

        slot_errors = []
        slot_warnings = []

        p_entry = get_pokemon_entry(sp_name, pokemon_registry)
        types = p_entry["types"] if p_entry else []
        if not p_entry:
            slot_errors.append(f"Illegal or Unknown Species: '{sp_name}' is not in Regulation M-C (MC_Available_Pokemon.csv).")

        # Check if holding a Mega Stone that Mega Evolves this species!
        mega_entry = None
        if item:
            item_cache_info = items_cache.get(to_id(item))
            if item_cache_info and item_cache_info.get("megaStone"):
                mega_map = item_cache_info["megaStone"]
                base_sp_for_mega = list(mega_map.keys())[0]
                target_mega_name = list(mega_map.values())[0]
                if p_entry and to_id(base_sp_for_mega) not in (to_id(sp_name), to_id(p_entry["name"])):
                    slot_errors.append(
                        f"Incompatible Mega Stone: '{item}' Mega Evolves {base_sp_for_mega}, not {sp_name}."
                    )
                else:
                    mega_entry = get_pokemon_entry(target_mega_name, pokemon_registry)

        base_species_key = re.sub(r"-Mega-[XYZxyz]|-Mega|^Mega\s+", "", sp_name, flags=re.IGNORECASE).strip()
        base_species_key = re.sub(r"\s+[XYZxyz]$", "", base_species_key).strip().lower()
        if base_species_key in seen_species:
            slot_errors.append(f"Species Clause Violation: Duplicate species detected for '{sp_name}'.")
        seen_species.add(base_species_key)

        # Ability legality check
        if p_entry and ability:
            legal_abs = [a.lower() for a in p_entry.get("abilities", []) if a]
            if mega_entry:
                legal_abs.extend([a.lower() for a in mega_entry.get("abilities", []) if a])
            if legal_abs and ability.lower() not in legal_abs:
                slot_errors.append(
                    f"Illegal Ability: '{ability}' is not a legal ability for {sp_name} (Legal: {', '.join(p_entry.get('abilities', []))})."
                )

        if item:
            clean_item_key = item.replace("’", "'").strip().lower()
            if clean_item_key not in legal_items:
                slot_errors.append(
                    f"Illegal Item: '{item}' is NOT legal in Regulation M-C. Consult data/Regulation_MC_Items.csv."
                )
            else:
                official_item_name = legal_items[clean_item_key]
                if official_item_name in seen_items:
                    slot_errors.append(f"Item Clause Violation: Duplicate item detected ('{official_item_name}').")
                seen_items.add(official_item_name)
        else:
            slot_warnings.append(f"No Hold Item equipped on {sp_name}.")

        sp_ok, sp_vstr, final_stats = validate_and_calculate_sp(sp_name, p["sp_spread"], nature)
        if not sp_ok:
            slot_errors.append(sp_vstr)

        # Also compute Mega stats & types if holding a compatible Mega Stone and species is base form
        mega_summary = None
        if mega_entry and to_id(sp_name) != to_id(mega_entry["name"]):
            _, _, mega_stats = validate_and_calculate_sp(mega_entry["name"], p["sp_spread"], nature)
            mega_ab = mega_entry["abilities"][0] if mega_entry.get("abilities") else ""
            mega_summary = {
                "mega_species": mega_entry["name"],
                "mega_types": mega_entry["types"],
                "mega_ability": mega_ab,
                "mega_stats": mega_stats,
            }

        # Effective types and ability for move STAB classification (use Mega if Mega Stone equipped)
        active_types = mega_entry["types"] if mega_entry else types
        active_ability = (mega_entry["abilities"][0] if (mega_entry and mega_entry.get("abilities")) else ability)

        learnset = p_entry.get("learnset", set()) if p_entry else set()
        moves_breakdown = []
        for m in p["moves"]:
            m_class = classify_move(m, active_types, active_ability)
            if not m_class["is_legal_move"]:
                slot_errors.append(f"Illegal Move: '{m}' does not exist or is cut in Pokemon Champions.")
            elif learnset and m_class["id"] not in learnset:
                slot_errors.append(f"Illegal Learnset Move: {sp_name} cannot learn '{m}' in Pokemon Champions.")
            moves_breakdown.append(m_class)

        slot_data = {
            "slot": idx,
            "species": sp_name,
            "verified_types": types,
            "item": item,
            "ability": ability,
            "nature": nature,
            "sp_spread": p["sp_spread"],
            "verification_str": sp_vstr,
            "final_stats": final_stats,
            "mega_evolution": mega_summary,
            "moves": moves_breakdown,
            "errors": slot_errors,
            "warnings": slot_warnings,
        }
        slots_report.append(slot_data)

        if slot_errors:
            errors.extend([f"Slot {idx} ({sp_name}): {err}" for err in slot_errors])
        if slot_warnings:
            warnings.extend([f"Slot {idx} ({sp_name}): {warn}" for warn in slot_warnings])

    is_valid = len(errors) == 0

    return {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "slots": slots_report,
        "pokemon_count": len(parsed_pokemon),
    }


def main():
    """CLI entry point for roster validation."""
    parser = argparse.ArgumentParser(description="Regulation M-C Roster & Legality Validator")
    parser.add_argument("--file", type=str, help="Path to text file containing Showdown team paste")
    parser.add_argument("--paste", type=str, help="Inline Showdown team paste string")
    parser.add_argument("--json", action="store_true", help="Output full report as JSON")
    args = parser.parse_args()

    paste_content = ""
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"[ERROR]: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        paste_content = file_path.read_text(encoding="utf-8")
    elif args.paste:
        paste_content = args.paste
    else:
        if not sys.stdin.isatty():
            paste_content = sys.stdin.read()
        else:
            print("[INPUT REQUIRED]: Provide Showdown paste via --paste, --file, or stdin.", file=sys.stderr)
            sys.exit(1)

    result = validate_roster(paste_content)

    if args.json:
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["is_valid"] else 1)

    print("=" * 75)
    print("COACH PORYGON VGC — REGULATION M-C ROSTER LEGALITY AUDIT")
    print("=" * 75)
    print(f"Overall Status: {'[PASS - 100% LEGAL]' if result['is_valid'] else '[FAIL - ILLEGAL ELEMENTS DETECTED]'}")
    print(f"Total Pokemon Evaluated: {result['pokemon_count']}")
    print("-" * 75)

    for s in result["slots"]:
        types_str = "/".join(s["verified_types"]) if s["verified_types"] else "Unverified"
        print(f"Slot {s['slot']}: {s['species']} [{types_str}] @ {s['item'] or 'None'} | Ability: {s['ability']} ({s['nature']})")
        print(f"        SP: {s['verification_str']}")
        if s["final_stats"]:
            stats_str = ", ".join(f"{k.upper()}: {v}" for k, v in s["final_stats"].items())
            print(f"        Base Stats (Lv50): {stats_str}")
        if s.get("mega_evolution"):
            mg = s["mega_evolution"]
            m_types = "/".join(mg["mega_types"])
            m_stats = ", ".join(f"{k.upper()}: {v}" for k, v in mg["mega_stats"].items())
            print(f"        Mega Form: {mg['mega_species']} [{m_types}] | Ability: {mg['mega_ability']}")
            print(f"        Mega Stats (Lv50): {m_stats}")
        print("        Moves:")
        for m in s["moves"]:
            print(f"          - {m['move']}: {m['type']} ({m['cat']}, {m['power']} BP) -> {m['classification']}")
        if s["errors"]:
            for err in s["errors"]:
                print(f"        [CRITICAL ERROR]: {err}")
        if s["warnings"]:
            for warn in s["warnings"]:
                print(f"        [WARNING]: {warn}")
        print("-" * 75)

    if not result["is_valid"]:
        print(f"TOTAL CRITICAL ERRORS: {len(result['errors'])}")
        for err in result["errors"]:
            print(f"  * {err}")
        sys.exit(1)
    else:
        print("Verification Complete: All species, abilities, learnsets, typings, items, and 66-SP spreads are 100% compliant.")
        sys.exit(0)


if __name__ == "__main__":
    main()
