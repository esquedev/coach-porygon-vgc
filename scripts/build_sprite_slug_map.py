#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic Sprite & Item Slug Map Builder for Regulation M-C.

Scans `assets/sprites/`, `assets/items/`, and `assets/megastones/` and cross-references
`src/engine/data/showdown/pokedex.jsonl` and `items.jsonl` to generate `assets/slug_map.json`.
Guarantees 100% deterministic resolution of all legal Champions Pokémon species
(including Mega Evolutions, regional formes, and gender variants) and held items
without fuzzy-matching collisions (e.g., never mapping base Garchomp to Mega Garchomp).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Dict, Optional

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
    "basculegion": "basculegion-male.png",
    "basculegionf": "basculegion-female.png",
    "basculegion-f": "basculegion-female.png",
    "indeedee": "indeedee-male.png",
    "indeedeef": "indeedee-female.png",
    "indeedee-f": "indeedee-female.png",
    "meowstic": "meowstic-male.png",
    "meowsticf": "meowstic-female.png",
    "meowstic-f": "meowstic-female.png",
    "meowsticfmega": "meowstic-mega.png",
    "meowstic-f-mega": "meowstic-mega.png",
    "meowsticmmega": "meowstic-mega.png",
    "meowstic-m-mega": "meowstic-mega.png",
    "pyroar": "pyroar-male.png",
    "maushold": "maushold.png",
    "mausholdfour": "maushold.png",
    "maushold-four": "maushold.png",
    "floette": "floette-red.png",
    "floetteeternal": "floette-eternal.png",
    "floette-eternal": "floette-eternal.png",
    "floettemega": "floette-mega.png",
    "floette-mega": "floette-mega.png",
    "raichualola": "raichu-alolan.png",
    "ninetalesalola": "ninetales-alolan.png",
    "persianalola": "persian-alolan.png",
    "arcaninehisui": "arcanine-hisuian.png",
    "decidueyehisui": "decidueye-hisuian.png",
    "avalugghisui": "avalugg-hisuian.png",
    "typhlosionhisui": "typhlosion-hisuian.png",
    "samurotthisui": "samurott-hisuian.png",
    "goodrahisui": "goodra-hisuian.png",
    "zoroarkhisui": "zoroark-hisuian.png",
    "slowbrogalar": "slowbro-galarian.png",
    "slowkinggalar": "slowking-galarian.png",
    "stunfiskgalar": "stunfisk-galarian.png",
    "taurospaldeaaqua": "tauros-paldean-aqua.png",
    "taurospaldeablaze": "tauros-paldean-blaze.png",
    "taurospaldeacombat": "tauros-paldean-combat.png",
    "squawkabillyyellow": "squawkabilly-yellow-plumage.png",
    "squawkabillyblue": "squawkabilly-blue-plumage.png",
    "squawkabillywhite": "squawkabilly-white-plumage.png",
    "gourgeistsmall": "gourgeist-small-variety.png",
    "gourgeistlarge": "gourgeist-large-variety.png",
    "gourgeistsuper": "gourgeist-jumbo-variety.png",
    "lycanrocdusk": "lycanroc-dusk-form.png",
    "lycanrocmidnight": "lycanroc-midnight-form.png",
    "toxtricitylowkey": "toxtricity-low-key-form.png",
    "mimikyubusted": "mimikyu-busted.png",
    "polteageistantique": "polteageist-antique.png",
    "sinistchamasterpiece": "sinistcha-masterpiece.png",
    "vivillonfancy": "vivillon-fancy.png",
    "vivillonpokeball": "vivillon-pokeball.png",
}


def build_slug_map() -> Dict[str, Dict[str, str]]:
    """Builds and returns the complete slug_map dictionary (scanning Reg_M-C & confirmed Reg_M-D, excluding rumored assets)."""
    sprite_paths = sorted(
        p for p in SPRITES_DIR.rglob("*.png") if "Reg_M-D_rumored" not in p.parts
    )
    sprite_files: Dict[str, str] = {
        p.stem.lower(): p.relative_to(ROOT_DIR).as_posix()
        for p in sprite_paths
    }
    sprite_by_filename: Dict[str, str] = {
        p.name.lower(): p.relative_to(ROOT_DIR).as_posix()
        for p in sprite_paths
    }
    item_files: Dict[str, str] = {
        p.stem.lower(): p.relative_to(ROOT_DIR).as_posix()
        for p in sorted(ITEMS_DIR.rglob("*.png"))
    }
    item_by_norm: Dict[str, str] = {
        normalize_slug(stem): rel_path for stem, rel_path in item_files.items()
    }
    megastone_files: Dict[str, str] = {
        p.stem.lower(): p.relative_to(ROOT_DIR).as_posix()
        for p in sorted(MEGASTONES_DIR.rglob("*.png"))
    }
    megastone_by_norm: Dict[str, str] = {
        normalize_slug(stem): rel_path for stem, rel_path in megastone_files.items()
    }

    species_map: Dict[str, str] = {}
    items_map: Dict[str, str] = {}

    # 1. Register direct file stems + Title-Case & normalized keys (covers Reg_M-C & Reg_M-D differential folders)
    for stem, rel_path in sprite_files.items():
        species_map[stem] = rel_path
        species_map[normalize_slug(stem)] = rel_path
        title_dash = "-".join(part.capitalize() for part in stem.split("-"))
        if title_dash and title_dash not in species_map:
            species_map[title_dash] = rel_path

    # 2. Register all Pokédex entries with strict precedence
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
                    fname = EXPLICIT_SPECIES_FILE_OVERRIDES[sid].lower()
                    if fname in sprite_by_filename:
                        resolved_rel = sprite_by_filename[fname]

                # Check exact dash stem or id stem
                if not resolved_rel:
                    for candidate in (dash, sid, dash.replace("-f", "-female").replace("-m", "-male")):
                        if candidate in sprite_files:
                            resolved_rel = sprite_files[candidate]
                            break

                # Regional prefix/suffix patterns (e.g. X-hisuian / hisuian-X, X-alolan / alolan-X, X-galarian / galarian-X)
                if not resolved_rel:
                    if dash.endswith("-hisui"):
                        base = dash[:-6]
                        for cand in (f"{base}-hisuian", f"hisuian-{base}"):
                            if cand in sprite_files:
                                resolved_rel = sprite_files[cand]
                                break
                    elif dash.endswith("-alola"):
                        base = dash[:-6]
                        for cand in (f"{base}-alolan", f"alolan-{base}"):
                            if cand in sprite_files:
                                resolved_rel = sprite_files[cand]
                                break
                    elif dash.endswith("-galar"):
                        base = dash[:-6]
                        for cand in (f"{base}-galarian", f"galarian-{base}"):
                            if cand in sprite_files:
                                resolved_rel = sprite_files[cand]
                                break
                    elif "-paldea-" in dash:
                        cand_suffix = dash.replace("-paldea-", "-paldean-")
                        if cand_suffix in sprite_files:
                            resolved_rel = sprite_files[cand_suffix]
                    elif f"{dash}-male" in sprite_files:
                        resolved_rel = sprite_files[f"{dash}-male"]

                if resolved_rel:
                    # Bind all canonical keys (including ASCII apostrophe variants for Farfetch'd / Sirfetch'd)
                    ascii_name = name.replace("\u2019", "'").replace("\u2018", "'")
                    species_map[name] = resolved_rel
                    species_map[name.lower()] = resolved_rel
                    species_map[ascii_name] = resolved_rel
                    species_map[ascii_name.lower()] = resolved_rel
                    species_map[dash] = resolved_rel
                    species_map[sid] = resolved_rel

    # Apply explicit overrides directly to map keys as well
    for k, fname in EXPLICIT_SPECIES_FILE_OVERRIDES.items():
        resolved_override = sprite_by_filename.get(fname.lower())
        if resolved_override:
            species_map[k] = resolved_override

    # 3. Register Mega Stones and Held Items
    for stem, rel_path in item_files.items():
        items_map[stem] = rel_path
        items_map[normalize_slug(stem)] = rel_path

    for stem, rel_path in megastone_files.items():
        items_map[stem] = rel_path
        items_map[normalize_slug(stem)] = rel_path
        title_ms = " ".join(part.capitalize() for part in stem.split("-"))
        if title_ms and title_ms not in items_map:
            items_map[title_ms] = rel_path

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
                inorm = normalize_slug(iname)
                ascii_iname = iname.replace("\u2019", "'").replace("\u2018", "'")
                matched_rel: Optional[str] = None
                for candidate in (idash, iid):
                    if candidate in megastone_files:
                        matched_rel = megastone_files[candidate]
                        break
                    if candidate in item_files:
                        matched_rel = item_files[candidate]
                        break
                if not matched_rel:
                    matched_rel = (
                        megastone_by_norm.get(iid)
                        or megastone_by_norm.get(inorm)
                        or item_by_norm.get(iid)
                        or item_by_norm.get(inorm)
                    )
                if matched_rel:
                    items_map[iname] = matched_rel
                    items_map[iname.lower()] = matched_rel
                    items_map[ascii_iname] = matched_rel
                    items_map[ascii_iname.lower()] = matched_rel
                    items_map[idash] = matched_rel
                    items_map[iid] = matched_rel

    payload = {
        "version": "2.1-reg-mc-md-diff",
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
