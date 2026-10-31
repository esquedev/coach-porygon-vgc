#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Asset Coverage & Vector Integrity Tests (tests/assets/test_svg_coverage.py)
Verifies 100% SVG coverage for Regulation M-C species, items, mega stones,
valid XML syntax, SHA-256 cryptographic integrity, and zero embedded raster blobs.
"""

import json
import sys
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.verify_svg_inventory import build_manifest_and_audit


class TestSvgAssetCoverage(unittest.TestCase):
    """Verifies complete SVG vector asset coverage across Regulation M-C."""

    def test_complete_vector_asset_coverage_and_xml_validity(self):
        """Test for complete vector asset coverage, XML validity, and SHA-256 checksums."""
        all_passed, manifest = build_manifest_and_audit()
        self.assertTrue(all_passed, "SVG asset coverage or XML validation failed.")
        self.assertGreaterEqual(len(manifest["species"]), 363)
        self.assertGreaterEqual(len(manifest["items"]), 85)
        self.assertGreaterEqual(len(manifest["megastones"]), 80)
        self.assertGreaterEqual(len(manifest.get("sha256_digests", {})), 539)

    def test_manifest_file_exists(self):
        """Test for manifest file exists and is populated."""
        manifest_path = REPO_ROOT / "assets" / "svg_manifest.json"
        self.assertTrue(manifest_path.exists())
        self.assertGreater(manifest_path.stat().st_size, 1000)

    def test_sha256_checksum_validity_format(self):
        """Test that all recorded SHA-256 digests in manifest are valid 64-char hex strings."""
        manifest_path = REPO_ROOT / "assets" / "svg_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digests = manifest.get("sha256_digests", {})
        self.assertGreaterEqual(len(digests), 539)
        for path_str, digest in digests.items():
            self.assertEqual(len(digest), 64, f"Invalid SHA-256 length for {path_str}")
            self.assertTrue(all(c in "0123456789abcdef" for c in digest.lower()))


if __name__ == "__main__":
    unittest.main()
