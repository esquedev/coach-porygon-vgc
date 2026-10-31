#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Showdown Authentic Asset Deployment Pipeline
Deploys official Pokémon Showdown sprites, items, and mega stones into assets/,
preserving Porygon branding SVGs and ML classification tools.
"""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"
ITEMS_DIR = ASSETS_DIR / "items"
MEGASTONES_DIR = ASSETS_DIR / "megastones"
ICONS_DIR = ASSETS_DIR / "icons"

SPRITES_DIR.mkdir(parents=True, exist_ok=True)
ITEMS_DIR.mkdir(parents=True, exist_ok=True)
MEGASTONES_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)

def deploy_assets():
    """Copy extracted Showdown PNG assets into canonical repo assets directory."""
    print("=" * 65)
    print("DEPLOYING OFFICIAL POKÉMON SHOWDOWN ASSETS TO ASSETS DIRECTORY")
    print("=" * 65)

    # 1. Species Sprites
    src_species = REPO_ROOT / "scratch" / "test_species_sprites"
    sp_count = 0
    if src_species.exists():
        for png in src_species.glob("*.png"):
            dest = SPRITES_DIR / png.name
            shutil.copy2(png, dest)
            sp_count += 1
            # Add reverse mega alias: e.g. mega-metagross -> metagross-mega
            if png.stem.startswith("mega-"):
                rev = png.stem.replace("mega-", "") + "-mega.png"
                shutil.copy2(png, SPRITES_DIR / rev)
            elif png.stem.endswith("-mega"):
                rev = "mega-" + png.stem.replace("-mega", "") + ".png"
                shutil.copy2(png, SPRITES_DIR / rev)

    print(f"Deployed {sp_count} species sprites (+ aliases) to {SPRITES_DIR}")

    # 2. Hold Items & Berries
    src_items = REPO_ROOT / "scratch" / "test_extracted_items"
    it_count = 0
    if src_items.exists():
        for png in src_items.glob("*.png"):
            dest = ITEMS_DIR / png.name
            shutil.copy2(png, dest)
            it_count += 1

    print(f"Deployed {it_count} hold items & berries to {ITEMS_DIR}")

    # 3. Mega Stones
    src_megas = REPO_ROOT / "scratch" / "test_extracted_megas"
    mg_count = 0
    if src_megas.exists():
        for png in src_megas.glob("*.png"):
            dest = MEGASTONES_DIR / png.name
            shutil.copy2(png, dest)
            mg_count += 1

    print(f"Deployed {mg_count} mega stones to {MEGASTONES_DIR}")

    # Remove obsolete procedural SVGs from sprites/, items/, megastones/
    # while preserving icons/ (Porygon logos)
    svg_purged = 0
    for folder in [SPRITES_DIR, ITEMS_DIR, MEGASTONES_DIR]:
        for svg in folder.glob("*.svg"):
            svg.unlink()
            svg_purged += 1

    print(f"Purged {svg_purged} obsolete procedural SVG approximations.")
    print("Preserved branding SVGs in assets/icons/ and ML model in data/ml_asset_audit/.")
    print("Deployment complete!")

if __name__ == "__main__":
    deploy_assets()
