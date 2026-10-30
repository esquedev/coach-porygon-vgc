import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / "data" / "pokedex_cache.json"

sys.path.insert(0, str(REPO_ROOT / "engine"))
from turn_simulator import BASE_STATS_DB, MOVE_DB


def sanitize_identifier(raw: Optional[str]) -> str:
    """Strips quotes, operators, and control characters to prevent query syntax breakout."""
    if not raw:
        return ""
    return re.sub(r"[^a-zA-Z0-9\-\s'\.]", "", raw).strip()[:64]


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {"species": {}, "moves": {}, "mechanics": {}}


def lookup_species(species: str) -> dict:
    clean_sp = sanitize_identifier(species)
    if clean_sp in BASE_STATS_DB:
        return {"status": "VERIFIED_ENGINE", "species": clean_sp, "data": BASE_STATS_DB[clean_sp]}
    cache = load_cache()
    if clean_sp in cache.get("species", {}):
        return {"status": "VERIFIED_CACHE", "species": clean_sp, "data": cache["species"][clean_sp]}

    query = (
        f'site:bulbapedia.bulbagarden.net/wiki/ "{clean_sp}" '
        f'"Base stats" "Pokemon Champions" -TCG -anime -"Trading Card Game" -card'
    )
    return {
        "status": "UNVERIFIED",
        "one_attempt_query": query,
        "failsafe_tag": f"[DATA_UNVERIFIED: Missing Base Stats for {clean_sp}]"
    }


def lookup_move(species: Optional[str], move_name: str) -> dict:
    clean_move = sanitize_identifier(move_name)
    if clean_move in MOVE_DB:
        return {"status": "VERIFIED_ENGINE", "move": clean_move, "data": MOVE_DB[clean_move]}
    cache = load_cache()
    if clean_move in cache.get("moves", {}):
        return {"status": "VERIFIED_CACHE", "move": clean_move, "data": cache["moves"][clean_move]}

    sp_str = sanitize_identifier(species) or "Pokemon"
    query = (
        f'site:wikidex.net OR site:bulbapedia.bulbagarden.net "{sp_str}" "{clean_move}" '
        f'"learnset" "Pokemon Champions" -TCG -anime -"Trading Card Game" -card'
    )
    return {
        "status": "UNVERIFIED",
        "one_attempt_query": query,
        "failsafe_tag": f"[DATA_UNVERIFIED: Missing Move Data for {sp_str}/{clean_move}]"
    }


def main():
    parser = argparse.ArgumentParser(description="Cache-First Pokedex & Regulation M-C Legality Resolver")
    parser.add_argument("--species", type=str, help="Species name to verify")
    parser.add_argument("--move", type=str, help="Move name to verify")
    args = parser.parse_args()

    if args.species and not args.move:
        print(json.dumps(lookup_species(args.species), indent=2))
    elif args.move:
        print(json.dumps(lookup_move(args.species, args.move), indent=2))


if __name__ == "__main__":
    main()
