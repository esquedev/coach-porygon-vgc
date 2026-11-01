#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — PNG & Asset Inventory, Manifest Generator & Integrity Validator.

Part of Digital Design Team (Asset Curator) and Systems QA.
Verifies 100% coverage for Regulation M-C species, items, and mega stones in assets/,
enforces binary PNG chunk structural integrity (IHDR, IDAT, IEND, CRC-32), dimensions (128x128
for species sprites, 24x24 for items and megastones), RGBA alpha channel transparency,
SHA-256 cryptographic digests, pixel-level deduplication, and audits vector SVGs
against script injection and stored XSS vulnerabilities.
"""

from collections import defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET
import zlib

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
SPRITES_REG_MC_DIR = ASSETS_DIR / "sprites" / "Reg_M-C"
ITEMS_DIR = ASSETS_DIR / "items"
MEGASTONES_DIR = ASSETS_DIR / "megastones"
ICONS_DIR = ASSETS_DIR / "icons"
BANNERS_DIR = ASSETS_DIR / "banners"
MANIFEST_PATH = ASSETS_DIR / "png_manifest.json"

# Strict SVG Anti-XSS patterns
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

# Dimensions & Alpha Contracts
DIMENSION_CONTRACTS = {
    "sprites": (128, 128),
    "items": (24, 24),
    "megastones": (24, 24),
}


def slugify(text: str) -> str:
    """Canonical slug transformation for Pokémon species and item filenames."""
    clean = re.sub(r"\s*\([mf]\)\s*", "", str(text or ""), flags=re.I).strip().lower()
    clean = re.sub(r"[^a-z0-9]+", "-", clean)
    return clean.strip("-")


def get_canonical_species_name(raw_name: str) -> str:
    """Map filename slug or Showdown raw name to canonical species name."""
    name = raw_name.strip()
    if name.startswith("Mega "):
        return name.replace("Mega ", "") + "-Mega"
    return name


def validate_png_chunk_integrity(raw_bytes: bytes) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validate binary PNG structure without requiring third-party libraries.

    Verifies 8-byte magic header, sequential chunk layout (length, type, data, CRC-32),
    IHDR parameters (width, height, bit depth, color type), IDAT presence, and IEND termination.
    """
    if not raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "Invalid PNG magic header bytes", None

    offset = 8
    total_len = len(raw_bytes)
    chunks_seen: List[bytes] = []
    ihdr_info: Dict[str, Any] = {}
    has_trns = False
    idat_bytes_total = 0

    while offset < total_len:
        if offset + 8 > total_len:
            return False, f"Truncated chunk header at byte offset {offset}", None

        length = struct.unpack_from(">I", raw_bytes, offset)[0]
        chunk_type = raw_bytes[offset + 4: offset + 8]
        offset += 8

        if offset + length + 4 > total_len:
            return False, f"Truncated chunk payload for {chunk_type.decode('ascii', errors='replace')}", None

        chunk_data = raw_bytes[offset: offset + length]
        expected_crc = struct.unpack_from(">I", raw_bytes, offset + length)[0]
        offset += length + 4

        # Validate CRC-32: computed over chunk type + chunk data
        calc_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if calc_crc != expected_crc:
            return False, f"CRC-32 checksum mismatch on chunk {chunk_type.decode('ascii', errors='replace')}", None

        chunks_seen.append(chunk_type)

        if chunk_type == b"IHDR":
            if len(chunk_data) != 13:
                return False, f"Invalid IHDR chunk length: {len(chunk_data)} (expected 13)", None
            w, h, bit_depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", chunk_data)
            ihdr_info = {
                "width": w,
                "height": h,
                "bit_depth": bit_depth,
                "color_type": color_type,
                "compression_method": comp,
                "filter_method": filt,
                "interlace_method": interlace,
            }
        elif chunk_type == b"tRNS":
            has_trns = True
        elif chunk_type == b"IDAT":
            idat_bytes_total += len(chunk_data)
        elif chunk_type == b"IEND":
            # IEND must be the final chunk
            if offset != total_len:
                return False, f"Trailing bytes detected after IEND chunk ({total_len - offset} bytes)", None
            break

    if b"IHDR" not in chunks_seen:
        return False, "Missing mandatory IHDR chunk", None
    if b"IDAT" not in chunks_seen or idat_bytes_total == 0:
        return False, "Missing or empty IDAT raster data chunks", None
    if b"IEND" not in chunks_seen:
        return False, "Missing terminating IEND chunk", None

    color_type = ihdr_info.get("color_type", 0)
    # Alpha presence check:
    # 6 = Truecolor with Alpha (RGBA)
    # 4 = Grayscale with Alpha (LA)
    # 3 = Indexed color with tRNS chunk
    # 2 = Truecolor with tRNS chunk
    has_alpha = (color_type in (4, 6)) or (color_type in (2, 3) and has_trns)
    ihdr_info["has_alpha"] = has_alpha

    return True, "Valid PNG", ihdr_info


def validate_image_with_pil(path: Path) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Perform deep verification of image raster with Pillow if available.

    Verifies header and fully decompresses IDAT zlib payload.
    """
    if not HAS_PIL:
        return True, "PIL not installed; skipped deep raster verification", None

    try:
        with Image.open(path) as img:
            img.verify()
        # Re-open for actual decompression and pixel reading
        with Image.open(path) as img:
            img.load()
            mode = img.mode
            size = img.size
            has_alpha = "A" in mode or "transparency" in img.info or mode == "P"
            # Uncompressed pixel SHA-256 for duplicate detection
            raw_rgba = img.convert("RGBA").tobytes()
            pixel_digest = hashlib.sha256(raw_rgba).hexdigest()

            return True, "Valid", {
                "width": size[0],
                "height": size[1],
                "mode": mode,
                "has_alpha": has_alpha,
                "pixel_digest": pixel_digest,
            }
    except Exception as exc:
        return False, f"Pillow decompression error: {exc}", None


def resolve_species_png(raw_name: str) -> Optional[Path]:
    """
    Resolve a Regulation M-C species or specialized form to its curated sprite.

    Prioritizes specialized form sprites (e.g. Midnight Lycanroc, Low-Key Toxtricity,
    Combat Paldean Tauros, Florges colors, Alcremie swirls, Vivillon patterns)
    BEFORE generic base species fallbacks.
    """
    canon = get_canonical_species_name(raw_name)
    slug = slugify(canon)
    slug_raw = slugify(raw_name)

    candidates: List[str] = []

    # 1. Specialized Form Mapping (Must precede base name stripping)
    if "tauros" in slug:
        if "aqua" in slug:
            candidates.extend(["tauros-paldean-aqua.png", "tauros-aqua.png"])
        elif "blaze" in slug:
            candidates.extend(["tauros-paldean-blaze.png", "tauros-blaze.png"])
        elif "combat" in slug or slug == "paldean-tauros":
            candidates.extend(["tauros-paldean-combat.png", "tauros-combat.png"])
        elif slug == "tauros":
            candidates.extend(["tauros.png"])

    if "lycanroc" in slug:
        if "midnight" in slug:
            candidates.extend(["lycanroc-midnight.png"])
        elif "dusk" in slug:
            candidates.extend(["lycanroc-dusk.png"])
        elif "midday" in slug or slug == "lycanroc":
            candidates.extend(["lycanroc.png"])

    if "toxtricity" in slug:
        if "low-key" in slug or "lowkey" in slug:
            candidates.extend(["toxtricity-low-key.png"])
        elif "amped" in slug or slug == "toxtricity":
            candidates.extend(["toxtricity.png"])

    if "florges" in slug:
        for col in ["blue", "orange", "white", "yellow"]:
            if col in slug:
                candidates.extend([f"florges-{col}.png"])
        if "red" in slug or slug == "florges":
            candidates.extend(["florges.png"])

    if "squawkabilly" in slug:
        for col in ["blue", "white", "yellow"]:
            if col in slug:
                candidates.extend([f"squawkabilly-{col}.png"])
        if "green" in slug or slug == "squawkabilly":
            candidates.extend(["squawkabilly.png"])

    if "gourgeist" in slug:
        if "small" in slug:
            candidates.extend(["gourgeist-small.png"])
        elif "large" in slug:
            candidates.extend(["gourgeist-large.png"])
        elif "jumbo" in slug or "super" in slug:
            candidates.extend(["gourgeist-super.png"])
        elif slug == "gourgeist":
            candidates.extend(["gourgeist.png"])

    if "furfrou" in slug:
        for trim in ["dandy", "debutante", "diamond", "heart", "kabuki", "la-reine", "matron", "pharaoh", "star"]:
            if trim in slug or trim.replace("-", "") in slug:
                candidates.extend([f"furfrou-{trim}.png"])
        if slug == "furfrou":
            candidates.extend(["furfrou.png"])

    if "alcremie" in slug:
        alcremie_sub_map = {
            "ruby-cream": "alcremie_01.png",
            "matcha-cream": "alcremie_02.png",
            "mint-cream": "alcremie_03.png",
            "lemon-cream": "alcremie_04.png",
            "salted-cream": "alcremie_05.png",
            "ruby-swirl": "alcremie_06.png",
            "caramel-swirl": "alcremie_07.png",
            "rainbow-swirl": "alcremie_08.png",
        }
        for sub_k, sub_f in alcremie_sub_map.items():
            if sub_k in slug:
                candidates.append(sub_f)
        if slug == "alcremie":
            candidates.append("alcremie.png")

    if "vivillon" in slug:
        if "high-plains" in slug or "highplains" in slug:
            candidates.extend(["vivillon_07.png", "vivillon.png"])
        elif slug == "vivillon":
            candidates.append("vivillon.png")

    if "meowstic" in slug:
        if "female" in slug or slug.endswith("-f") or "meowstic-f" in slug:
            candidates.extend(["meowstic-female-mega.png", "meowstic-female.png"] if "mega" in slug else ["meowstic-female.png"])
        elif "male" in slug or slug.endswith("-m") or "meowstic-m" in slug:
            candidates.extend(["meowstic-male-mega.png", "meowstic-male.png"] if "mega" in slug else ["meowstic-male.png"])
        elif "mega" in slug:
            candidates.extend(["meowstic-mega.png"])
        else:
            candidates.extend(["meowstic-male.png", "meowstic-female.png"])

    if "floette" in slug:
        if "eternal" in slug:
            if "mega" in slug:
                candidates.extend(["floette-mega.png", "floette-eternal-mega.png"])
            else:
                candidates.extend(["floette-eternal.png"])

    # 2. Standard exact candidates
    candidates.extend([
        f"{slug}.png",
        f"{slug_raw}.png",
        f"{slug.replace('-', '')}.png",
    ])

    # Rotom appliances
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
    if slug in ["basculegion", "indeedee", "pyroar"]:
        candidates.extend([f"{slug}-male.png", f"{slug}-female.png"])

    # Specific known names
    if "farfetch" in slug:
        candidates.extend(["farfetchd.png", "farfetchd-galar.png", "farfetchd-galarian.png"])
    if "mr-mime" in slug or "mrmime" in slug:
        candidates.extend(["mr-mime.png", "mrmime.png", "mr-mime-galar.png", "mrmime-galar.png", "mr-mime-galarian.png"])

    # Fallback stripping of parentheses as last resort
    base_no_paren = re.sub(r"\s*\([^)]*\)", "", raw_name).strip()
    base_slug = slugify(base_no_paren)
    candidates.extend([f"{base_slug}.png", f"{base_slug.replace('-', '')}.png"])

    for c in candidates:
        cand_p = SPRITES_REG_MC_DIR / c
        if cand_p.exists():
            return cand_p
    return None


def build_manifest_and_audit(
    output_manifest_path: Optional[Path] = None,
    write_manifest: bool = True,
    strict_mode: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Perform complete PNG chunk, dimension, alpha, SHA-256 integrity, deduplication, and anti-XSS audit.

    Generates png_manifest.json with full cryptographic inventory and deterministic metadata.
    """
    manifest: Dict[str, Any] = {
        "version": "2.0",
        "description": "Coach Porygon VGC Unified Asset Manifest (Regulation M-C)",
        "species": {},
        "items": {},
        "megastones": {},
        "sha256_digests": {},
        "metadata": {
            "total_species_audited": 0,
            "total_items_audited": 0,
            "total_megas_audited": 0,
            "total_curated_assets": 0,
            "corrupt_assets_count": 0,
            "dimension_violations_count": 0,
            "alpha_missing_count": 0,
            "exact_duplicate_groups_count": 0,
            "pixel_duplicate_groups_count": 0,
            "xss_injections_count": 0,
            "xml_errors_count": 0,
        }
    }

    # 1. Audit Species (Regulation M-C)
    species_file = REPO_ROOT / "data" / "MC_Available_Pokemon.csv"
    species_rows: List[str] = []
    missing_species: List[Tuple[str, str]] = []

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
    items_seen: Set[str] = set()
    megas_seen: Set[str] = set()
    missing_items: List[Tuple[str, str]] = []
    missing_megas: List[Tuple[str, str]] = []

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

    # 3. Collect all Curated Disk Assets
    curated_assets: List[Path] = []
    if SPRITES_REG_MC_DIR.exists():
        curated_assets.extend(SPRITES_REG_MC_DIR.glob("*.png"))
    if ITEMS_DIR.exists():
        curated_assets.extend(ITEMS_DIR.glob("*.png"))
    if MEGASTONES_DIR.exists():
        curated_assets.extend(MEGASTONES_DIR.glob("*.png"))
    if ICONS_DIR.exists():
        curated_assets.extend(ICONS_DIR.glob("*.png"))
        curated_assets.extend(ICONS_DIR.glob("*.svg"))

    # 4. Rigorous Binary Chunk, Dimension, Alpha, Deduplication, Anti-XSS Verification
    corrupt_assets: List[Tuple[str, str]] = []
    dimension_violations: List[Tuple[str, Tuple[int, int], Tuple[int, int]]] = []
    alpha_missing: List[str] = []
    xml_errors: List[Tuple[str, str]] = []
    script_injections: List[str] = []

    exact_hash_map: Dict[str, List[str]] = defaultdict(list)
    pixel_hash_map: Dict[str, List[str]] = defaultdict(list)

    for asset_path in sorted(curated_assets):
        raw_bytes = asset_path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        rel_key = asset_path.relative_to(REPO_ROOT).as_posix()
        manifest["sha256_digests"][rel_key] = digest
        exact_hash_map[digest].append(rel_key)

        suffix = asset_path.suffix.lower()

        if suffix == ".svg":
            content = raw_bytes.decode("utf-8", errors="replace")
            content_lower = content.lower()

            if any(pat in content_lower for pat in DANGEROUS_SVG_PATTERNS):
                script_injections.append(rel_key)

            try:
                ET.fromstring(content)
            except Exception as exc:
                xml_errors.append((rel_key, str(exc)))

        elif suffix == ".png":
            # 4a. Binary chunk and CRC-32 validation
            ok_chunk, msg_chunk, ihdr_info = validate_png_chunk_integrity(raw_bytes)
            if not ok_chunk:
                corrupt_assets.append((rel_key, msg_chunk))
                continue

            # 4b. Deep verification with PIL if present
            ok_pil, msg_pil, pil_info = validate_image_with_pil(asset_path)
            if not ok_pil:
                corrupt_assets.append((rel_key, msg_pil))
                continue

            width = pil_info["width"] if pil_info else ihdr_info["width"]
            height = pil_info["height"] if pil_info else ihdr_info["height"]
            has_alpha = pil_info["has_alpha"] if pil_info else ihdr_info.get("has_alpha", False)

            if pil_info and "pixel_digest" in pil_info:
                pixel_hash_map[pil_info["pixel_digest"]].append(rel_key)

            # 4c. Dimension contract enforcement
            expected_dim: Optional[Tuple[int, int]] = None
            if "sprites/Reg_M-C" in rel_key:
                expected_dim = DIMENSION_CONTRACTS["sprites"]
            elif "assets/items" in rel_key:
                expected_dim = DIMENSION_CONTRACTS["items"]
            elif "assets/megastones" in rel_key:
                expected_dim = DIMENSION_CONTRACTS["megastones"]

            if expected_dim and (width, height) != expected_dim:
                dimension_violations.append((rel_key, (width, height), expected_dim))

            # 4d. Alpha channel transparency check
            if not has_alpha:
                alpha_missing.append(rel_key)

    # 5. Duplicate Detection Analysis
    exact_duplicates = {h: paths for h, paths in exact_hash_map.items() if len(paths) > 1}
    pixel_duplicates = {h: paths for h, paths in pixel_hash_map.items() if len(paths) > 1}

    # 6. Populate Manifest Metadata
    manifest["metadata"]["total_species_audited"] = len(species_rows)
    manifest["metadata"]["total_items_audited"] = len(items_seen)
    manifest["metadata"]["total_megas_audited"] = len(megas_seen)
    manifest["metadata"]["total_curated_assets"] = len(curated_assets)
    manifest["metadata"]["corrupt_assets_count"] = len(corrupt_assets)
    manifest["metadata"]["dimension_violations_count"] = len(dimension_violations)
    manifest["metadata"]["alpha_missing_count"] = len(alpha_missing)
    manifest["metadata"]["exact_duplicate_groups_count"] = len(exact_duplicates)
    manifest["metadata"]["pixel_duplicate_groups_count"] = len(pixel_duplicates)
    manifest["metadata"]["xss_injections_count"] = len(script_injections)
    manifest["metadata"]["xml_errors_count"] = len(xml_errors)

    # Write Manifest deterministically
    out_path = Path(output_manifest_path) if output_manifest_path else MANIFEST_PATH
    if write_manifest:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        manifest_display = str(out_path.relative_to(REPO_ROOT))
    except ValueError:
        manifest_display = str(out_path)

    print("=" * 70)
    print("COACH PORYGON VGC — DIGITAL DESIGN ASSET CURATOR & PNG INTEGRITY AUDIT")
    print("=" * 70)
    print(f"Total Species Audited:      {len(species_rows)} (Missing: {len(missing_species)})")
    print(f"Total Items Audited:        {len(items_seen)} (Missing: {len(missing_items)})")
    print(f"Total Mega Stones Audited:  {len(megas_seen)} (Missing: {len(missing_megas)})")
    print(f"Total Assets Verified:      {len(curated_assets)} curated files on disk.")
    print(f"PNG Chunk & CRC Integrity:  {len(corrupt_assets)} Corrupt PNGs (Target: 0).")
    print(f"Dimension Contracts:        {len(dimension_violations)} Violations (Target: 0).")
    print(f"Alpha Channel Transparency: {len(alpha_missing)} Missing Alpha (Target: 0).")
    print(f"Exact Duplicate Assets:     {len(exact_duplicates)} Duplicate Groups (Target: 0).")
    print(f"Pixel-Level Duplicates:     {len(pixel_duplicates)} Duplicate Groups (Target: 0).")
    print(f"Well-formed XML Checks:     {len(xml_errors)} XML Errors (Target: 0).")
    print(f"Anti-XSS Vector Checks:     {len(script_injections)} Script Injections (Target: 0).")
    print(f"SHA-256 Digest Inventory:   {len(manifest['sha256_digests'])} / {len(curated_assets)} Cryptographic Hashes.")
    print(f"Manifest Generated:         {manifest_display}")
    print("=" * 70)

    if missing_species:
        print(f"[MISSING SPECIES]: {missing_species[:5]}")
    if missing_items:
        print(f"[MISSING ITEMS]: {missing_items[:5]}")
    if missing_megas:
        print(f"[MISSING MEGAS]: {missing_megas[:5]}")
    if corrupt_assets:
        print(f"[CORRUPT ASSETS]: {corrupt_assets[:5]}")
    if dimension_violations:
        print(f"[DIMENSION VIOLATIONS]: {dimension_violations[:5]}")
    if alpha_missing:
        print(f"[MISSING ALPHA]: {alpha_missing[:5]}")
    if exact_duplicates:
        print(f"[EXACT DUPLICATES]: {list(exact_duplicates.items())[:3]}")
    if pixel_duplicates:
        print(f"[PIXEL DUPLICATES]: {list(pixel_duplicates.items())[:3]}")
    if xml_errors:
        print(f"[XML ERRORS]: {xml_errors[:5]}")
    if script_injections:
        print(f"[SCRIPT INJECTIONS]: {script_injections[:5]}")

    all_passed = (
        len(missing_species) == 0 and
        len(missing_items) == 0 and
        len(missing_megas) == 0 and
        len(xml_errors) == 0 and
        len(corrupt_assets) == 0 and
        len(script_injections) == 0 and
        len(manifest["sha256_digests"]) == len(curated_assets)
    )

    if strict_mode:
        all_passed = all_passed and (
            len(dimension_violations) == 0 and
            len(alpha_missing) == 0 and
            len(exact_duplicates) == 0 and
            len(pixel_duplicates) == 0
        )

    return all_passed, manifest


def main():
    """CLI entry point for running verification audit on real assets with sandboxed output."""
    import argparse
    parser = argparse.ArgumentParser(description="Verify PNG and SVG asset inventory against Regulation M-C rules.")
    parser.add_argument("--output", "-o", type=str, default=str(MANIFEST_PATH), help="Destination path for generated manifest.")
    parser.add_argument("--no-write", action="store_true", help="Skip writing manifest to disk.")
    parser.add_argument("--strict", action="store_true", help="Enforce strict zero tolerance for dimension or alpha violations.")
    args = parser.parse_args()

    passed, _ = build_manifest_and_audit(
        output_manifest_path=Path(args.output),
        write_manifest=not args.no_write,
        strict_mode=args.strict
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
