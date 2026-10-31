import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / "data" / "pokedex_cache.json"
ITEMS_CSV_PATH = REPO_ROOT / "data" / "Regulation_MC_Items.csv"
POKEMON_CSV_PATH = REPO_ROOT / "data" / "MC_Available_Pokemon.csv"

sys.path.insert(0, str(REPO_ROOT / "engine"))
from turn_simulator import BASE_STATS_DB, MOVE_DB


def to_id(text: str) -> str:
    """Convert arbitrary string into lowercase alphanumeric slug."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def sanitize_identifier(raw: Optional[str]) -> str:
    """Strips quotes, operators, and control characters to prevent query syntax breakout."""
    if not raw:
        return ""
    return re.sub(r"[^a-zA-Z0-9\-\s'\.\(\)]", "", raw).strip()[:64]


def load_cache() -> dict:
    """Load pokedex cache JSON from disk with fallback structure."""
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {"species": {}, "moves": {}, "items": {}, "abilities": {}, "mechanics": {}}


def _find_species_in_cache(clean_sp: str, cache: dict) -> Optional[dict]:
    """Locate species entry matching exact name, id, or alias in cache."""
    sp_map = cache.get("species", {})
    if clean_sp in sp_map:
        return sp_map[clean_sp]
    sid = to_id(clean_sp)
    for k, v in sp_map.items():
        if v.get("id") == sid or to_id(k) == sid:
            return v
        for alias in v.get("aliases", []):
            if to_id(alias) == sid:
                return v
    return None


def lookup_species(species: str) -> dict:
    """Perform 1-attempt cache-first resolution for Pokémon species."""
    clean_sp = sanitize_identifier(species)
    cache = load_cache()
    cached_entry = _find_species_in_cache(clean_sp, cache)
    if cached_entry:
        # Omit full 80-move learnset list from default species summary unless needed, or show count
        summary_data = {k: v for k, v in cached_entry.items() if k != "learnset"}
        summary_data["learnset_count"] = len(cached_entry.get("learnset", []))
        return {
            "status": "VERIFIED_CHAMPIONS_CACHE",
            "species": cached_entry["name"],
            "verified_types": cached_entry.get("types", []),
            "abilities": cached_entry.get("abilities", {}),
            "required_item": cached_entry.get("requiredItem"),
            "data": summary_data,
        }

    if clean_sp in BASE_STATS_DB:
        entry = BASE_STATS_DB[clean_sp]
        return {
            "status": "VERIFIED_ENGINE",
            "species": clean_sp,
            "verified_types": entry.get("types", []),
            "abilities": entry.get("abilities", {}),
            "data": {k: v for k, v in entry.items() if k != "learnset"},
        }

    query = (
        f'site:bulbapedia.bulbagarden.net/wiki/ "{clean_sp}" '
        f'"Base stats" "Pokemon Champions" -TCG -anime -"Trading Card Game" -card'
    )
    return {
        "status": "UNVERIFIED",
        "one_attempt_query": query,
        "failsafe_tag": f"[DATA_UNVERIFIED: Missing Base Stats for {clean_sp}]",
    }


def lookup_item(item_name: str) -> dict:
    """Check item legality against Regulation_MC_Items.csv and cache."""
    clean_item = sanitize_identifier(item_name).replace("’", "'").strip().lower()
    cache = load_cache()
    item_cache = cache.get("items", {})
    cached_item = None
    for k, v in item_cache.items():
        if k.lower() == clean_item or v.get("id") == to_id(clean_item):
            cached_item = v
            break

    if ITEMS_CSV_PATH.exists():
        with open(ITEMS_CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            try:
                next(reader)
            except StopIteration:
                pass
            for row in reader:
                for idx, category in [(0, "Hold Item"), (3, "Berry"), (6, "Mega Stone")]:
                    if len(row) > idx and row[idx].strip():
                        name = row[idx].replace("’", "'").strip()
                        if name.lower() == clean_item or to_id(name) == to_id(clean_item):
                            effect = row[idx + 1].strip() if len(row) > idx + 1 else ""
                            res = {
                                "status": "VERIFIED_LEGAL_ITEM",
                                "item": name,
                                "category": category,
                                "effect": effect,
                            }
                            if cached_item and cached_item.get("megaStone"):
                                res["mega_evolves"] = cached_item["megaStone"]
                            return res

    return {
        "status": "ILLEGAL_ITEM",
        "item": item_name,
        "message": f"[ILLEGAL ITEM]: '{item_name}' is NOT present in data/Regulation_MC_Items.csv (or is marked Past in Showdown Champions).",
    }


def lookup_ability(ability_name: str) -> dict:
    """Verify Pokémon ability against Champions format cache."""
    clean_ab = sanitize_identifier(ability_name)
    aid = to_id(clean_ab)
    cache = load_cache()
    for k, v in cache.get("abilities", {}).items():
        if k.lower() == clean_ab.lower() or v.get("id") == aid:
            res = {
                "status": "VERIFIED_CHAMPIONS_ABILITY",
                "ability": v["name"],
                "data": v,
            }
            new_abs = cache.get("mechanics", {}).get("newChampionsAbilities", {})
            if v["name"] in new_abs:
                res["champions_effect"] = new_abs[v["name"]]
            return res
    return {
        "status": "ILLEGAL_OR_UNKNOWN_ABILITY",
        "ability": clean_ab,
        "message": f"'{clean_ab}' is not found in legal Pokemon Champions abilities.",
    }


def lookup_move(species: Optional[str], move_name: str) -> dict:
    """Verify move base power, accuracy, category, and typing in database."""
    clean_move = sanitize_identifier(move_name)
    mid = to_id(clean_move)
    cache = load_cache()

    move_data = None
    for k, v in cache.get("moves", {}).items():
        if k.lower() == clean_move.lower() or v.get("id") == mid:
            move_data = v
            break
    if not move_data and clean_move in MOVE_DB:
        move_data = MOVE_DB[clean_move]

    if move_data:
        result = {
            "status": "VERIFIED_CHAMPIONS_MOVE",
            "move": move_data.get("name", clean_move),
            "data": move_data,
        }
        if species:
            sp_entry = _find_species_in_cache(sanitize_identifier(species), cache)
            if sp_entry:
                can_learn = mid in sp_entry.get("learnset", [])
                result["species"] = sp_entry["name"]
                result["species_types"] = sp_entry.get("types", [])
                result["legal_in_learnset"] = can_learn
                result["is_stab"] = (move_data.get("type") in sp_entry.get("types", [])) and (move_data.get("cat") != "Status")
        return result

    sp_str = sanitize_identifier(species) or "Pokemon"
    query = (
        f'site:wikidex.net OR site:bulbapedia.bulbagarden.net "{sp_str}" "{clean_move}" '
        f'"learnset" "Pokemon Champions" -TCG -anime -"Trading Card Game" -card'
    )
    return {
        "status": "UNVERIFIED",
        "one_attempt_query": query,
        "failsafe_tag": f"[DATA_UNVERIFIED: Missing Move Data for {sp_str}/{clean_move}]",
    }


def main():
    """CLI entry point for precision pokédex lookups."""
    parser = argparse.ArgumentParser(description="Cache-First Pokedex & Regulation M-C Legality Resolver")
    parser.add_argument("--species", type=str, help="Species name to verify")
    parser.add_argument("--move", type=str, help="Move name to verify (combine with --species to check learnset & STAB)")
    parser.add_argument("--item", type=str, help="Item name to verify legality")
    parser.add_argument("--ability", type=str, help="Ability name to verify legality and Champions mechanics")
    args = parser.parse_args()

    if args.item:
        print(json.dumps(lookup_item(args.item), indent=2))
    elif args.ability:
        print(json.dumps(lookup_ability(args.ability), indent=2))
    elif args.species and not args.move:
        print(json.dumps(lookup_species(args.species), indent=2))
    elif args.move:
        print(json.dumps(lookup_move(args.species, args.move), indent=2))


if __name__ == "__main__":
    main()
