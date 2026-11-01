# -*- coding: utf-8 -*-
"""Coach Porygon VGC — Unit Tests for PNG Inventory & Asset Integrity Engine.

Validates:
1. Binary PNG chunk layout, CRC-32 integrity, IHDR parameters, and IDAT decompression.
2. Robust failure on corrupt magic headers, truncated chunks, and CRC mismatches.
3. Form-specific sprite resolution hierarchy (Lycanroc, Toxtricity, Tauros, Florges, etc.).
4. Strict asset audit contracts (zero dimension violations, zero missing alpha, zero duplicates).
"""

from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from engine.verify_png_inventory import (
    build_manifest_and_audit,
    get_canonical_species_name,
    resolve_species_png,
    slugify,
    validate_png_chunk_integrity,
)


def make_minimal_valid_png_bytes(width: int = 1, height: int = 1, with_alpha: bool = True) -> bytes:
    """Construct minimal structurally valid PNG binary bytes with valid chunk CRCs."""
    signature = b"\x89PNG\r\n\x1a\n"
    # Color type: 6 = RGBA (with alpha), 2 = RGB (no alpha)
    color_type = 6 if with_alpha else 2
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # 1 scanline: filter byte (0) + uncompressed pixel bytes
    channels = 4 if with_alpha else 3
    scanline = b"\x00" + (b"\xff" * (width * channels))
    compressed = zlib.compress(scanline)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat_chunk = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    return signature + ihdr_chunk + idat_chunk + iend_chunk


class TestVerifyPngInventory(unittest.TestCase):
    """Unit tests for the PNG verification and asset curation pipeline."""

    def test_minimal_png_chunk_validation_success(self):
        """Verify that a syntactically correct PNG byte sequence passes chunk validation."""
        valid_png = make_minimal_valid_png_bytes(128, 128, with_alpha=True)
        ok, msg, info = validate_png_chunk_integrity(valid_png)
        self.assertTrue(ok)
        self.assertEqual(msg, "Valid PNG")
        self.assertIsNotNone(info)
        self.assertEqual(info["width"], 128)
        self.assertEqual(info["height"], 128)
        self.assertTrue(info["has_alpha"])

    def test_corrupt_png_magic_header_rejected(self):
        """Verify rejection of bytes that do not start with the 8-byte PNG signature."""
        corrupt_magic = b"GIF89a\x00\x00\x00\x00"
        ok, msg, info = validate_png_chunk_integrity(corrupt_magic)
        self.assertFalse(ok)
        self.assertIn("magic header", msg.lower())
        self.assertIsNone(info)

    def test_corrupt_chunk_crc_rejected(self):
        """Verify detection of CRC-32 checksum mismatch in chunk data."""
        valid_png = bytearray(make_minimal_valid_png_bytes(24, 24, with_alpha=True))
        # Tamper with an IHDR data byte without updating CRC
        valid_png[16] ^= 0xFF
        ok, msg, info = validate_png_chunk_integrity(bytes(valid_png))
        self.assertFalse(ok)
        self.assertIn("crc-32", msg.lower())
        self.assertIsNone(info)

    def test_truncated_png_chunk_rejected(self):
        """Verify detection of truncated chunk payload."""
        valid_png = make_minimal_valid_png_bytes(24, 24, with_alpha=True)
        truncated = valid_png[:20]  # Cut off mid-IHDR
        ok, msg, info = validate_png_chunk_integrity(truncated)
        self.assertFalse(ok)
        self.assertIn("truncated", msg.lower())
        self.assertIsNone(info)

    def test_missing_idat_chunk_rejected(self):
        """Verify rejection when IDAT chunk is absent."""
        signature = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 16, 16, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

        no_idat = signature + ihdr_chunk + iend_chunk
        ok, msg, info = validate_png_chunk_integrity(no_idat)
        self.assertFalse(ok)
        self.assertIn("idat", msg.lower())

    def test_slugify_and_canonical_mapping(self):
        """Verify deterministic slugification and canonical name transformations."""
        self.assertEqual(slugify("Charizard-Mega-Y"), "charizard-mega-y")
        self.assertEqual(slugify("Meowstic (M)"), "meowstic")
        self.assertEqual(slugify("Farfetch’d"), "farfetch-d")
        self.assertEqual(get_canonical_species_name("Mega Charizard Y"), "Charizard Y-Mega")
        self.assertEqual(get_canonical_species_name("Pikachu"), "Pikachu")

    def test_form_resolution_specialized_hierarchies(self):
        """Verify that specialized form sprites are prioritized over generic base fallbacks."""
        # Midnight Lycanroc
        p_lyc_mid = resolve_species_png("Lycanroc (Midnight Form)")
        self.assertIsNotNone(p_lyc_mid)
        self.assertEqual(p_lyc_mid.name, "lycanroc-midnight.png")

        # Low-Key Toxtricity
        p_tox_low = resolve_species_png("Toxtricity (Low-Key Form)")
        self.assertIsNotNone(p_tox_low)
        self.assertEqual(p_tox_low.name, "toxtricity-low-key.png")

        # Paldean Tauros
        p_tauros_combat = resolve_species_png("Paldean Tauros")
        self.assertIsNotNone(p_tauros_combat)
        self.assertEqual(p_tauros_combat.name, "tauros-paldean-combat.png")

        # Florges Blue Flower
        p_florges_blue = resolve_species_png("Florges (Blue Flower)")
        self.assertIsNotNone(p_florges_blue)
        self.assertEqual(p_florges_blue.name, "florges-blue.png")

        # Furfrou Dandy Trim
        p_furfrou_dandy = resolve_species_png("Furfrou (Dandy Trim)")
        self.assertIsNotNone(p_furfrou_dandy)
        self.assertEqual(p_furfrou_dandy.name, "furfrou-dandy.png")

    def test_strict_mode_repo_assets_audit(self):
        """Verify full repository assets pass strict validation with zero errors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_manifest = Path(tmp_dir) / "test_manifest.json"
            passed, manifest = build_manifest_and_audit(
                output_manifest_path=temp_manifest,
                write_manifest=True,
                strict_mode=True
            )
            self.assertTrue(passed, "Asset audit failed in strict mode")
            metadata = manifest.get("metadata", {})
            self.assertEqual(metadata.get("corrupt_assets_count"), 0)
            self.assertEqual(metadata.get("dimension_violations_count"), 0)
            self.assertEqual(metadata.get("alpha_missing_count"), 0)
            self.assertEqual(metadata.get("exact_duplicate_groups_count"), 0)
            self.assertEqual(metadata.get("pixel_duplicate_groups_count"), 0)
            self.assertEqual(metadata.get("xss_injections_count"), 0)
            self.assertEqual(metadata.get("xml_errors_count"), 0)


if __name__ == "__main__":
    unittest.main()
