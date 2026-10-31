#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Complete Mega Sprites & Showdown Alias Harmonizer
Ensures all 83 Regulation M-C Mega Evolution Pokémon and regional/form variants
have authentic official Pokémon Showdown PNG sprites covering every possible
hyphenation and naming permutation (e.g. Charizard-Mega-Y, Mega-Charizard-Y,
Charizard-Megay, Charizard-Y-Mega, etc.).
"""

import csv
import re
import shutil
import sys
from pathlib import Path
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SPRITES_DIR = REPO_ROOT / "assets" / "sprites"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def slugify(text: str) -> str:
    """Canonical slug transformation."""
    clean = re.sub(r"\s*\([mf]\)\s*", "", str(text or ""), flags=re.I).strip().lower()
    clean = re.sub(r"[^a-z0-9]+", "-", clean)
    return clean.strip("-")


def download_if_missing(url: str, dest: Path) -> bool:
    """Download a file from URL if dest does not exist."""
    if dest.exists() and dest.stat().st_size > 100:
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200 and len(r.content) > 100:
            dest.write_bytes(r.content)
            print(f"[DOWNLOADED] {url} -> {dest.name}")
            return True
    except Exception as e:
        print(f"[WARN] Could not download {url}: {e}")
    return False


def copy_alias(src_path: Path, dst_name: str) -> bool:
    """Copies src_path to dst_name if dst does not exist or has different size."""
    dst_path = SPRITES_DIR / dst_name
    if not dst_path.exists() or dst_path.stat().st_size != src_path.stat().st_size:
        shutil.copyfile(src_path, dst_path)
        return True
    return False


def main():
    """Download missing mega sprites and harmonize all naming aliases across Regulation M-C."""
    SPRITES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Ensure Diancie Mega is downloaded from Showdown
    diancie_dest = SPRITES_DIR / "diancie-mega.png"
    download_if_missing("https://play.pokemonshowdown.com/sprites/gen5/diancie-mega.png", diancie_dest)
    if diancie_dest.exists():
        for alias in ["mega-diancie.png", "dianciemega.png", "megadiancie.png"]:
            copy_alias(diancie_dest, alias)

    # 2. Harmonize Farfetch'd & Sirfetch'd
    if (SPRITES_DIR / "farfetch-d.png").exists():
        copy_alias(SPRITES_DIR / "farfetch-d.png", "farfetchd.png")
    if (SPRITES_DIR / "sirfetch-d.png").exists():
        copy_alias(SPRITES_DIR / "sirfetch-d.png", "sirfetchd.png")

    # 3. Read all 83 Megas from MC_Available_Pokemon.csv
    with open(REPO_ROOT / "data" / "MC_Available_Pokemon.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        species_rows = [r[0].strip() for r in reader if r and r[0].strip()]

    megas = [s for s in species_rows if "mega" in s.lower()]
    print(f"Processing {len(megas)} Regulation M-C Megas...")

    total_created = 0
    for m in megas:
        slug = slugify(m)
        # Find canonical source file
        source_file = None
        # Try direct
        if (SPRITES_DIR / f"{slug}.png").exists():
            source_file = SPRITES_DIR / f"{slug}.png"
        elif slug.startswith("mega-"):
            base = slug[5:]
            if (SPRITES_DIR / f"{base}-mega.png").exists():
                source_file = SPRITES_DIR / f"{base}-mega.png"
            elif base.endswith("-x") or base.endswith("-y") or base.endswith("-z"):
                b = base[:-2]
                s = base[-1]
                for cand in [f"{b}-{s}-mega.png", f"{b}-mega-{s}.png", f"{b}-mega{s}.png", f"mega-{b}-{s}.png"]:
                    if (SPRITES_DIR / cand).exists():
                        source_file = SPRITES_DIR / cand
                        break

        if not source_file:
            print(f"[MISSING SOURCE] {m} ({slug})")
            continue

        # Now generate comprehensive aliases for this Mega:
        aliases_to_create = set()

        # If slug is "mega-foo"
        if slug.startswith("mega-"):
            base = slug[5:]
            aliases_to_create.add(f"{slug}.png")
            aliases_to_create.add(f"{slug.replace('-', '')}.png")
            aliases_to_create.add(f"{base}-mega.png")
            aliases_to_create.add(f"{base}mega.png")
            aliases_to_create.add(f"mega{base}.png")

            # Check suffix -x, -y, -z
            if base.endswith("-x") or base.endswith("-y") or base.endswith("-z"):
                b = base[:-2]
                s = base[-1]
                aliases_to_create.add(f"{b}-mega-{s}.png")
                aliases_to_create.add(f"{b}-mega{s}.png")
                aliases_to_create.add(f"{b}-{s}-mega.png")
                aliases_to_create.add(f"mega-{b}-{s}.png")
                aliases_to_create.add(f"mega-{b}{s}.png")
                aliases_to_create.add(f"{b}mega{s}.png")
                aliases_to_create.add(f"mega{b}{s}.png")
                aliases_to_create.add(f"{b}{s}mega.png")

        for alias in aliases_to_create:
            if copy_alias(source_file, alias):
                total_created += 1

    print(f"[OK] Harmonized Mega sprites: created/verified {total_created} alias files.")

    # 4. Harmonize Rotom forms
    rotom_forms = ["wash", "heat", "frost", "mow", "fan"]
    for rf in rotom_forms:
        src = None
        for cand in [f"rotom-{rf}.png", f"{rf}-rotom.png"]:
            if (SPRITES_DIR / cand).exists():
                src = SPRITES_DIR / cand
                break
        if src:
            copy_alias(src, f"rotom-{rf}.png")
            copy_alias(src, f"{rf}-rotom.png")
            copy_alias(src, f"rotom{rf}.png")
            copy_alias(src, f"{rf}rotom.png")

    # 5. Harmonize Regional forms
    regionals = [
        ("alolan-ninetales", "ninetales-alola"),
        ("hisuian-arcanine", "arcanine-hisui"),
        ("hisuian-zoroark", "zoroark-hisui"),
        ("galarian-slowbro", "slowbro-galar"),
        ("galarian-weezing", "weezing-galar"),
        ("paldean-tauros", "tauros-paldea"),
    ]
    for r1, r2 in regionals:
        src = None
        for cand in [f"{r1}.png", f"{r2}.png"]:
            if (SPRITES_DIR / cand).exists():
                src = SPRITES_DIR / cand
                break
        if src:
            copy_alias(src, f"{r1}.png")
            copy_alias(src, f"{r2}.png")
            copy_alias(src, f"{r1.replace('-', '')}.png")
            copy_alias(src, f"{r2.replace('-', '')}.png")

    # 6. Eternal Floette
    src_floette = None
    for cand in ["floette-eternal.png", "eternal-floette.png", "floette-eternal-mega.png", "mega-eternal-floette.png", "eternal-floette-mega.png"]:
        if (SPRITES_DIR / cand).exists():
            src_floette = SPRITES_DIR / cand
            break
    if src_floette:
        for alias in ["floette-eternal.png", "eternal-floette.png", "floetteeternal.png", "eternalfloette.png", "mega-eternal-floette.png", "eternal-floette-mega.png", "floette-eternal-mega.png"]:
            copy_alias(src_floette, alias)


if __name__ == "__main__":
    main()
