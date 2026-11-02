"""Load and look up a generated Pokémon Showdown Pokédex snapshot.

This module owns species/form reference data only. Format legality belongs in
separate, versioned format data so one Pokédex can serve multiple formats.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POKEDEX_PATH = PROJECT_ROOT / "data" / "pokedex.json"


def _to_id(value: str) -> str:
    """Normalize a Showdown name or ID to its lowercase alphanumeric ID."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def load_pokedex(path: Path = POKEDEX_PATH) -> dict[str, dict[str, Any]]:
    """Load generated Pokédex entries, indexed by Showdown ID and display name.

    Original Showdown fields (including ``baseStats`` and form metadata) are
    preserved. The six base stats are also exposed as flattened keys for
    compatibility with the v2 stat calculation code.

    Returns an empty mapping when the generated snapshot is not present yet.
    Raises ``ValueError`` for a malformed snapshot rather than silently
    treating invalid data as an empty Pokédex.
    """
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as source:
        document = json.load(source)

    if not isinstance(document, dict) or not isinstance(document.get("species"), dict):
        raise ValueError(f"Invalid Pokédex file {path}: expected an object at 'species'.")

    index: dict[str, dict[str, Any]] = {}
    for species_id, raw_entry in document["species"].items():
        if not isinstance(raw_entry, dict):
            continue

        entry = dict(raw_entry)
        base_stats = entry.get("baseStats", {})
        if isinstance(base_stats, dict):
            entry.update(base_stats)

        entry["id"] = entry.get("id", species_id)
        index[_to_id(str(species_id))] = entry
        index[_to_id(str(entry.get("name", species_id)))] = entry

    return index


POKEDEX_DB = load_pokedex()


def get_species(species: str) -> dict[str, Any] | None:
    """Return a species/form by Showdown ID or display name, case-insensitively."""
    if not isinstance(species, str):
        return None
    return POKEDEX_DB.get(_to_id(species))


__all__ = ["POKEDEX_PATH", "POKEDEX_DB", "load_pokedex", "get_species"]
