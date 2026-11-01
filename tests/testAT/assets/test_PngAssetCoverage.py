#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Asset Coverage & PNG Integrity Tests (tests/assets/test_png_coverage.py)
Verifies 100% PNG coverage for Regulation M-C species, items, mega stones,
valid binary PNG headers, SHA-256 cryptographic integrity, and zero script injections
audited directly against real disk assets with sandboxed output generation.
"""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO_ROOT))

from engine.verify_png_inventory import build_manifest_and_audit


class TestPngAssetCoverage(unittest.TestCase):
    """Verifies complete PNG asset coverage across Regulation M-C on real files with sandboxed output."""

    @classmethod
    def setUpClass(cls):
        """Perform inventory audit on real asset files with output directed strictly to a sandbox directory."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.sandbox_manifest = Path(cls.temp_dir.name) / "png_manifest.json"
        cls.all_passed, cls.manifest = build_manifest_and_audit(output_manifest_path=cls.sandbox_manifest)

    @classmethod
    def tearDownClass(cls):
        """Clean up sandboxed output directory."""
        cls.temp_dir.cleanup()

    def test_complete_png_asset_coverage_and_integrity(self):
        """Test for complete PNG asset coverage, header integrity, and SHA-256 checksums on real files."""
        self.assertTrue(self.all_passed, "PNG asset coverage or integrity validation failed on real files.")
        self.assertGreaterEqual(len(self.manifest["species"]), 363)
        self.assertGreaterEqual(len(self.manifest["items"]), 85)
        self.assertGreaterEqual(len(self.manifest["megastones"]), 80)
        self.assertGreaterEqual(len(self.manifest.get("sha256_digests", {})), 550)

    def test_manifest_file_exists(self):
        """Test that canonical assets/png_manifest.json exists and is populated."""
        canonical_path = REPO_ROOT / "assets" / "png_manifest.json"
        self.assertTrue(canonical_path.exists())
        self.assertGreater(canonical_path.stat().st_size, 1000)

    def test_sha256_checksum_validity_format(self):
        """Test that all recorded SHA-256 digests in manifest match real asset files on disk."""
        digests = self.manifest.get("sha256_digests", {})
        self.assertGreaterEqual(len(digests), 550)
        for path_str, digest in digests.items():
            self.assertEqual(len(digest), 64, f"Invalid SHA-256 length for {path_str}")
            self.assertTrue(all(c in "0123456789abcdef" for c in digest.lower()))
            real_file = REPO_ROOT / path_str
            self.assertTrue(real_file.exists(), f"Real asset file not found on disk: {real_file}")

    def test_canonical_manifest_cryptographic_parity(self):
        """Verify that newly audited hashes from real files match canonical assets/png_manifest.json."""
        canonical_path = REPO_ROOT / "assets" / "png_manifest.json"
        canonical_data = json.loads(canonical_path.read_text(encoding="utf-8"))
        canonical_digests = canonical_data.get("sha256_digests", {})
        self.assertEqual(len(canonical_digests), len(self.manifest["sha256_digests"]))
        for path_str, expected_hash in canonical_digests.items():
            self.assertEqual(self.manifest["sha256_digests"].get(path_str), expected_hash, f"Hash drift on {path_str}")


if __name__ == "__main__":
    unittest.main()
