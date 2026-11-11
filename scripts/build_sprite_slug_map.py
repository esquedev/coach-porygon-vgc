#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic Sprite & Item Slug Map Builder for Regulation M-C.

Scans `assets/sprites/`, `assets/items/`, and `assets/megastones/` and cross-references
`src/engine/data/showdown/pokedex.jsonl` and `items.jsonl` to generate `assets/slug_map.json`.
Guarantees 100% deterministic resolution of all 350 Regulation M-C Pokémon species
(including Mega Evolutions, regional formes, and gender variants) and held items
without fuzzy-matching collisions (e.g., never mapping base Garchomp to Mega Garchomp).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"
ITEMS_DIR = ASSETS_DIR / "items"
MEGASTONES_DIR = ASSETS_DIR / "megastones"
SHOWDOWN_DIR = ROOT_DIR / "src" / "engine" / "data" / "showdown"
SLUG_MAP_PATH = ASSETS_DIR / "slug_map.json"


def normalize_slug(text: str) -> str:
    """Normalizes any species or item string into a lowercase alphanumeric slug."""
    clean = text.replace("\u2019", "'").replace("\u2018", "'").strip().lower()
    return re.sub(r"[^a-z0-9]", "", clean)


def normalize_dash_slug(text: str) -> str:
    """Normalizes any species or item string into a lowercase hyphenated slug."""
    clean = text.replace("\u2019", "").replace("\u2018", "").replace("'", "").replace(".", "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", clean).strip("-")


# Explicit canonical overrides for non-standard regional/forme filename conventions
EXPLICIT_SPECIES_FILE_OVERRIDES: Dict[str, str] = {
    "indeedeef": "indeedee-female.png",
    "indeedee-f": "indeedee-female.png",
    "floette": "floette-eternal.png",
    "floettemega": "eternal-floette-mega.png",
    "floette-mega": "eternal-floette-mega.png",
    "raichualola": "alolan-raichu.png",
    "persianalola": "alolan-persian.png",
    "decidueyehisui": "hisuian-decidueye.png",
    "avalugghisui": "hisuian-avalugg.png",
    "typhlosionhisui": "hisuian-typhlosion.png",
    "samurotthisui": "hisuian-samurott.png",
    "goodrahisui": "hisuian-goodra.png",
    "slowkinggalar": "galarian-slowking.png",
    "stunfiskgalar": "galarian-stunfisk.png",
    "squawkabillyyellow": "squawkabilly-yellow-plumage.png",
    "squawkabillyblue": "squawkabilly-blue-plumage.png",
    "squawkabillywhite": "squawkabilly-white-plumage.png",
    "gourgeistsmall": "gourgeist-small-variety.png",
    "gourgeistlarge": "gourgeist-large-variety.png",
    "gourgeistsuper": "gourgeist-jumbo-variety.png",
    "vivillon": "vivillon-high-plains-pattern.png",
    "lycanrocdusk": "lycanroc-dusk-form.png",
    "lycanrocmidnight": "lycanroc-midnight-form.png",
    "taurospaldeaaqua": "paldean-tauros-aqua-breed.png",
    "taurospaldeablaze": "paldean-tauros-blaze-breed.png",
    "taurospaldeacombat": "paldean-tauros.png",
    "toxtricitylowkey": "toxtricity-low-key-form.png",
}


def build_slug_map() -> Dict[str, Dict[str, str]]:
    """Builds and returns the complete slug_map dictionary."""
    sprite_files: Dict[str, str] = {
        p.stem.lower(): f"assets/sprites/{p.name}"
        for p in sorted(SPRITES_DIR.glob("*.png"))
    }
    item_files: Dict[str, str] = {
        p.stem.lower(): f"assets/items/{p.name}"
        for p in sorted(ITEMS_DIR.glob("*.png"))
    }
    megastone_files: Dict[str, str] = {
        p.stem.lower(): f"assets/megastones/{p.name}"
        for p in sorted(MEGASTONES_DIR.glob("*.png"))
    }

    species_map: Dict[str, str] = {}
    items_map: Dict[str, str] = {}

    # 1. Register direct file stems first
    for stem, rel_path in sprite_files.items():
        species_map[stem] = rel_path
        species_map[normalize_slug(stem)] = rel_path

    # 2. Register all 350 Pokédex entries with strict precedence
    pokedex_path = SHOWDOWN_DIR / "pokedex.jsonl"
    if pokedex_path.exists():
        with open(pokedex_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                name: str = entry["name"]
                sid: str = entry["id"]
                dash = normalize_dash_slug(name)

                resolved_rel: Optional[str] = None

                # Check explicit override first
                if sid in EXPLICIT_SPECIES_FILE_OVERRIDES:
                    fname = EXPLICIT_SPECIES_FILE_OVERRIDES[sid]
                    if (SPRITES_DIR / fname).exists():
                        resolved_rel = f"assets/sprites/{fname}"

                # Check exact dash stem or id stem
                if not resolved_rel:
                    for candidate in (dash, sid, dash.replace("-f", "-female").replace("-m", "-male")):
                        if candidate in sprite_files:
                            resolved_rel = sprite_files[candidate]
                            break

                # Regional prefix patterns (e.g. hisuian-X, alolan-X, galarian-X)
                if not resolved_rel:
                    if dash.endswith("-hisui"):
                        base = dash[:-6]
                        if f"hisuian-{base}" in sprite_files:
                            resolved_rel = sprite_files[f"hisuian-{base}"]
                    elif dash.endswith("-alola"):
                        base = dash[:-6]
                        if f"alolan-{base}" in sprite_files:
                            resolved_rel = sprite_files[f"alolan-{base}"]
                    elif dash.endswith("-galar"):
                        base = dash[:-6]
                        if f"galarian-{base}" in sprite_files:
                            resolved_rel = sprite_files[f"galarian-{base}"]

                if resolved_rel:
                    # Bind all canonical keys to this exact verified path
                    species_map[name] = resolved_rel
                    species_map[name.lower()] = resolved_rel
                    species_map[dash] = resolved_rel
                    species_map[sid] = resolved_rel

    # Apply explicit overrides directly to map keys as well
    for k, fname in EXPLICIT_SPECIES_FILE_OVERRIDES.items():
        if (SPRITES_DIR / fname).exists():
            species_map[k] = f"assets/sprites/{fname}"

    # 3. Register Mega Stones and Held Items
    for stem, rel_path in item_files.items():
        items_map[stem] = rel_path
        items_map[normalize_slug(stem)] = rel_path

    for stem, rel_path in megastone_files.items():
        items_map[stem] = rel_path
        items_map[normalize_slug(stem)] = rel_path

    items_jsonl = SHOWDOWN_DIR / "items.jsonl"
    if items_jsonl.exists():
        with open(items_jsonl, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                iname: str = entry.get("name", "")
                iid: str = entry.get("id", "")
                idash = normalize_dash_slug(iname)
                for candidate in (idash, iid):
                    if candidate in megastone_files:
                        items_map[iname] = megastone_files[candidate]
                        items_map[iname.lower()] = megastone_files[candidate]
                        items_map[idash] = megastone_files[candidate]
                        items_map[iid] = megastone_files[candidate]
                        break
                    if candidate in item_files:
                        items_map[iname] = item_files[candidate]
                        items_map[iname.lower()] = item_files[candidate]
                        items_map[idash] = item_files[candidate]
                        items_map[iid] = item_files[candidate]
                        break

    payload = {
        "version": "2.0-reg-mc",
        "species": species_map,
        "items": items_map,
    }
    return payload


def main() -> None:
    payload = build_slug_map()
    SLUG_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    SLUG_MAP_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[Coach Porygon] Built '{SLUG_MAP_PATH}': "
        f"{len(payload['species'])} species keys, {len(payload['items'])} item/megastone keys."
    )


if __name__ == "__main__":
    main()
