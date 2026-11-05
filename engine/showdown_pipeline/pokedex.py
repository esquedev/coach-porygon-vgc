# engine/pokedex.py
"""Load and look up a generated Pokémon Showdown Pokédex snapshot."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

# Resolve directly relative to this file's directory (engine/)
ENGINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ENGINE_DIR.parent

# Candidate locations in priority order
_CANDIDATE_PATHS = [
    ENGINE_DIR / "data" / "showdown" / "pokedex.json",
    REPO_ROOT / "engine" / "data" / "showdown" / "pokedex.json",
]

POKEDEX_PATH = next((p for p in _CANDIDATE_PATHS if p.exists()), _CANDIDATE_PATHS[0])


def _to_id(value: str) -> str:
    """Normalize a Showdown name or ID to lowercase alphanumeric."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def load_pokedex(path: Path = POKEDEX_PATH) -> dict[str, dict[str, Any]]:
    """Load Showdown Pokédex entries indexed by ID and display name."""
    target_path = next((p for p in _CANDIDATE_PATHS if p.exists()), path)
    if not target_path.exists():
        print(f"[ERROR]: Pokédex file not found. Looked at: {[str(p) for p in _CANDIDATE_PATHS]}")
        return {}

    with target_path.open("r", encoding="utf-8") as source:
        document = json.load(source)

    if not isinstance(document, dict):
        raise ValueError(f"Invalid Pokédex file {target_path}: expected a JSON object.")

    # Support flat Showdown export { "bulbasaur": {...} } or nested { "species": {...} }
    species_dict = (
        document.get("species")
        if isinstance(document.get("species"), dict)
        else document
    )

    index: dict[str, dict[str, Any]] = {}
    for species_id, raw_entry in species_dict.items():
        if not isinstance(raw_entry, dict):
            continue

        entry = dict(raw_entry)
        base_stats = entry.get("baseStats", {})
        if isinstance(base_stats, dict):
            entry.update(base_stats)

        entry["id"] = entry.get("id", species_id)
        index[_to_id(str(species_id))] = entry
        if "name" in entry:
            index[_to_id(str(entry["name"]))] = entry

    return index


POKEDEX_DB = load_pokedex()


def get_species(species: str) -> dict[str, Any] | None:
    """Return a species entry by Showdown ID or display name, case-insensitively."""
    if not isinstance(species, str):
        return None
    return POKEDEX_DB.get(_to_id(species))


__all__ = ["POKEDEX_PATH", "POKEDEX_DB", "load_pokedex", "get_species"]