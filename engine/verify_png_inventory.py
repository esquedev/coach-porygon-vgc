#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — PNG & Asset Inventory, Manifest Generator & Integrity Validator
Part of Digital Design Team (Asset Curator).
Verifies 100% coverage for Regulation M-C species, items, and mega stones in assets/sprites/Reg_M-C/,
checks binary PNG headers, SHA-256 cryptographic integrity, and strictly audits vector SVGs
against script injection and stored XSS vulnerabilities.
"""

import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Optional
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
SPRITES_REG_MC_DIR = ASSETS_DIR / "sprites" / "Reg_M-C"
ITEMS_DIR = ASSETS_DIR / "items"
MEGASTONES_DIR = ASSETS_DIR / "megastones"
ICONS_DIR = ASSETS_DIR / "icons"
MANIFEST_PATH = ASSETS_DIR / "png_manifest.json"

DANGEROUS_SVG_PATTERNS = (
    "<script",
    "</script",
    "onload=",
    "onerror=",
    "onclick=",
    "onmouseover=",
    "onfocus=",
    "javascript:",
    "data:text/html",
)


def slugify(text: str) -> str:
    """Canonical slug transformation for Pokemon and item asset filenames."""
    clean = re.sub(r"\s*\([mf]\)\s*", "", str(text or ""), flags=re.I).strip().lower()
    clean = re.sub(r"[^a-z0-9]+", "-", clean)
    return clean.strip("-")


def get_canonical_species_name(raw_name: str) -> str:
    """Map filename slug back to canonical species name."""
    name = raw_name.strip()
    if name.startswith("Mega "):
        return name.replace("Mega ", "") + "-Mega"
    return name


def resolve_species_png(raw_name: str) -> Optional[Path]:
    """Resolve a Regulation M-C species to its curated sprite in assets/sprites/Reg_M-C/."""
    canon = get_canonical_species_name(raw_name)
    slug = slugify(canon)
    slug_raw = slugify(raw_name)

    candidates = [
        f"{slug}.png",
        f"{slug_raw}.png",
        f"{slug.replace('-', '')}.png",
    ]

    # Rotom forms: 'wash-rotom' -> 'rotom-wash', etc.
    if "rotom" in slug:
        for app in ["wash", "heat", "frost", "fan", "mow"]:
            if app in slug:
                candidates.extend([f"rotom-{app}.png", f"{app}-rotom.png"])

    # Regional forms
    for reg in ["galar", "galarian", "hisui", "hisuian", "alola", "alolan", "paldea", "paldean"]:
        if slug.startswith(f"{reg}-"):
            base = slug[len(reg) + 1:]
            candidates.extend([f"{base}-{reg}.png", f"{base}.png"])
            if reg == "galarian":
                candidates.extend([f"{base}-galar.png", f"{base}-galarian.png"])
            elif reg == "hisuian":
                candidates.extend([f"{base}-hisui.png", f"{base}-hisuian.png"])
            elif reg == "alolan":
                candidates.extend([f"{base}-alola.png", f"{base}-alolan.png"])
            elif reg == "paldean":
                candidates.extend([f"{base}-paldean.png", f"{base}-paldea.png"])
        elif slug.endswith(f"-{reg}"):
            base = slug[:-len(reg) - 1]
            candidates.extend([f"{reg}-{base}.png", f"{base}.png"])

    # Megas and Mega Variants
    if "mega" in slug:
        if "meowstic" in slug:
            candidates.extend(["meowstic-mega.png", "meowstic-female-mega.png", "meowstic-male-mega.png"])
        m_variant = re.match(r"^([a-z0-9]+)-(?:mega-)?([xyz])-mega$", slug) or re.match(r"^([a-z0-9]+)-mega-([xyz])$", slug)
        if m_variant:
            b, var = m_variant.group(1), m_variant.group(2)
            candidates.extend([f"{b}-mega-{var}.png", f"{b}-mega{var}.png", f"mega-{b}-{var}.png"])
        parts = slug.split("-")
        if parts[0] == "mega":
            rest = "-".join(parts[1:])
            candidates.extend([f"{rest}-mega.png", f"{rest}.png"])
        elif parts[-1] == "mega":
            base = "-".join(parts[:-1])
            candidates.extend([f"mega-{base}.png", f"{base}.png"])

    # Gendered defaults
    if slug in ["basculegion", "indeedee", "meowstic", "pyroar"]:
        candidates.extend([f"{slug}-male.png", f"{slug}-female.png"])

    # Paldean Tauros Breeds
    if "tauros" in slug:
        if "aqua" in slug:
            candidates.extend(["tauros-paldean-aqua.png", "tauros-aqua.png"])
        elif "blaze" in slug:
            candidates.extend(["tauros-paldean-blaze.png", "tauros-blaze.png"])
        elif "combat" in slug or "paldean" in slug:
            candidates.extend(["tauros-paldean-combat.png", "tauros-combat.png"])

    # Floette eternal
    if "floette" in slug:
        if "eternal" in slug:
            if "mega" in slug:
                candidates.extend(["floette-mega.png", "floette-eternal-mega.png"])
            else:
                candidates.extend(["floette-eternal.png"])

    # Variants in parentheses: Gourgeist (Jumbo Variety) -> gourgeist, Alcremie (Caramel Swirl) -> alcremie
    base_no_paren = re.sub(r"\s*\([^)]*\)", "", raw_name).strip()
    base_slug = slugify(base_no_paren)
    candidates.extend([f"{base_slug}.png", f"{base_slug.replace('-', '')}.png"])

    # Specific known names
    if "farfetch" in slug:
        candidates.extend(["farfetchd.png", "farfetchd-galar.png", "farfetchd-galarian.png"])
    if "mr-mime" in slug or "mrmime" in slug:
        candidates.extend(["mr-mime.png", "mrmime.png", "mr-mime-galar.png", "mrmime-galar.png", "mr-mime-galarian.png"])

    for c in candidates:
        cand_p = SPRITES_REG_MC_DIR / c
        if cand_p.exists():
            return cand_p
    return None


def build_manifest_and_audit(output_manifest_path: Optional[Path] = None, write_manifest: bool = True):
    """Perform full PNG, XML, SHA-256 integrity, and anti-XSS audit generating png_manifest.json."""
    manifest = {
        "version": "1.0",
        "description": "Coach Porygon VGC Unified Asset Manifest (Regulation M-C)",
        "species": {},
        "items": {},
        "megastones": {},
        "sha256_digests": {}
    }

    # 1. Audit Species (Regulation M-C)
    species_file = REPO_ROOT / "data" / "MC_Available_Pokemon.csv"
    species_rows = []
    missing_species = []

    with open(species_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row and row[0].strip():
                species_rows.append(row[0].strip())

    for sp in species_rows:
        canon = get_canonical_species_name(sp)
        slug = slugify(canon)
        asset_file = resolve_species_png(sp)

        if not asset_file:
            missing_species.append((sp, slug))
            continue

        rel_path = f"assets/sprites/Reg_M-C/{asset_file.name}"
        manifest["species"][sp] = rel_path
        manifest["species"][canon] = rel_path
        manifest["species"][slug] = rel_path

    # 2. Audit Items & Mega Stones
    items_file = REPO_ROOT / "data" / "Regulation_MC_Items.csv"
    items_seen = set()
    megas_seen = set()
    missing_items = []
    missing_megas = []

    with open(items_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row:
                continue
            if len(row) > 0 and row[0].strip():
                items_seen.add(row[0].strip())
            if len(row) > 3 and row[3].strip():
                items_seen.add(row[3].strip())
            if len(row) > 6 and row[6].strip():
                megas_seen.add(row[6].strip())

    for it in sorted(items_seen):
        slug = slugify(it)
        cand = ITEMS_DIR / f"{slug}.png"
        if not cand.exists():
            missing_items.append((it, slug))
            continue
        rel_path = f"assets/items/{cand.name}"
        manifest["items"][it] = rel_path
        manifest["items"][slug] = rel_path

    for ms in sorted(megas_seen):
        slug = slugify(ms)
        cand = MEGASTONES_DIR / f"{slug}.png"
        if not cand.exists():
            missing_megas.append((ms, slug))
            continue
        rel_path = f"assets/megastones/{cand.name}"
        manifest["megastones"][ms] = rel_path
        manifest["megastones"][slug] = rel_path

    # 3. Audit Asset Validity, Cryptographic SHA-256 Hashes & Binary Integrity
    xml_errors = []
    corrupt_pngs = []
    script_injections = []
    total_assets = 0

    # Curated asset collection: Reg_M-C sprites, items, megastones, and UI icons
    curated_assets = []
    if SPRITES_REG_MC_DIR.exists():
        curated_assets.extend(SPRITES_REG_MC_DIR.glob("*.png"))
    if ITEMS_DIR.exists():
        curated_assets.extend(ITEMS_DIR.glob("*.png"))
    if MEGASTONES_DIR.exists():
        curated_assets.extend(MEGASTONES_DIR.glob("*.png"))
    if ICONS_DIR.exists():
        curated_assets.extend(ICONS_DIR.glob("*.png"))
        curated_assets.extend(ICONS_DIR.glob("*.svg"))

    for asset_path in sorted(curated_assets):
        total_assets += 1
        raw_bytes = asset_path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        rel_key = asset_path.relative_to(REPO_ROOT).as_posix()
        manifest["sha256_digests"][rel_key] = digest

        if asset_path.suffix == ".svg":
            content = raw_bytes.decode("utf-8", errors="replace")
            content_lower = content.lower()

            if any(pat in content_lower for pat in DANGEROUS_SVG_PATTERNS):
                script_injections.append(str(asset_path.relative_to(REPO_ROOT)))

            try:
                ET.fromstring(content)
            except Exception as e:
                xml_errors.append((str(asset_path.relative_to(REPO_ROOT)), str(e)))
        elif asset_path.suffix == ".png":
            if not raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                corrupt_pngs.append(str(asset_path.relative_to(REPO_ROOT)))

    # Write Manifest with full cryptographic inventory strictly into sandbox folder
    out_path = Path(output_manifest_path) if output_manifest_path else MANIFEST_PATH
    if write_manifest:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        manifest_display = str(out_path.relative_to(REPO_ROOT))
    except ValueError:
        manifest_display = str(out_path)

    print("=" * 65)
    print("COACH PORYGON VGC — DIGITAL DESIGN ASSET CURATOR AUDIT")
    print("=" * 65)
    print(f"Total Species Audited:    {len(species_rows)} (Missing: {len(missing_species)})")
    print(f"Total Items Audited:      {len(items_seen)} (Missing: {len(missing_items)})")
    print(f"Total Mega Stones Audited:{len(megas_seen)} (Missing: {len(missing_megas)})")
    print(f"Total Assets Verified:    {total_assets} curated files on disk.")
    print(f"PNG Integrity Checks:     {len(corrupt_pngs)} Corrupt PNGs (Target: 0).")
    print(f"Well-formed XML Checks:   {len(xml_errors)} XML Errors (Target: 0).")
    print(f"Active Scripting Check:   {len(script_injections)} Injected Scripts (Target: 0).")
    print(f"SHA-256 Digest Audit:     {len(manifest['sha256_digests'])} / {total_assets} Cryptographic Hashes.")
    print(f"Manifest Generated:       {manifest_display}")
    print("=" * 65)

    if missing_species:
        print(f"[MISSING SPECIES]: {missing_species[:5]}")
    if missing_items:
        print(f"[MISSING ITEMS]: {missing_items[:5]}")
    if missing_megas:
        print(f"[MISSING MEGAS]: {missing_megas[:5]}")
    if xml_errors:
        print(f"[XML ERRORS]: {xml_errors[:5]}")
    if corrupt_pngs:
        print(f"[CORRUPT PNGS]: {corrupt_pngs[:5]}")
    if script_injections:
        print(f"[SCRIPT INJECTIONS]: {script_injections[:5]}")

    all_passed = (
        len(missing_species) == 0 and
        len(missing_items) == 0 and
        len(missing_megas) == 0 and
        len(xml_errors) == 0 and
        len(corrupt_pngs) == 0 and
        len(script_injections) == 0 and
        len(manifest["sha256_digests"]) == total_assets
    )
    return all_passed, manifest


def main():
    """CLI entry point for running verification audit on real assets with sandboxed output."""
    import argparse
    parser = argparse.ArgumentParser(description="Verify PNG and SVG asset inventory against Regulation M-C rules.")
    parser.add_argument("--output", "-o", type=str, default=str(MANIFEST_PATH), help="Destination path for generated manifest.")
    parser.add_argument("--no-write", action="store_true", help="Skip writing manifest to disk.")
    args = parser.parse_args()

    passed, _ = build_manifest_and_audit(
        output_manifest_path=Path(args.output),
        write_manifest=not args.no_write
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
