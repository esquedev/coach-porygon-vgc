#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit & Acceptance Tests for Rotom-Wash SVG Logo & ML Classifier
Validates:
1. Rotom-Wash SVG file integrity, valid XML structure, and viewBox standard.
2. Complete absence of uncanny procedural template markers (0 creepy eye, 0 generic torso).
3. Exact Showdown ground-truth palette alignment (orange plasma #ff5d22 / #e07020, hydro cyan #0ea5e9 / #38bdf8).
4. Machine Learning AssetQualityClassifier acceptance score >= 99.5%.
"""

import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.asset_classifier import AssetQualityClassifier, SVGFeatureExtractor
from engine.generate_rotom_wash_svg import (
    generate_rotom_wash_svg,
    evaluate_rotom_wash_quality,
    OUTPUT_SVG,
    SHOWDOWN_REF
)


class TestRotomWashSVGQuality(unittest.TestCase):
    """Rigorous unit & acceptance test suite for the Rotom-Wash logo asset."""

    @classmethod
    def setUpClass(cls):
        """Ensure the SVG is generated prior to testing."""
        generate_rotom_wash_svg()

    def test_rotom_wash_svg_file_integrity_and_viewbox(self):
        """Verify the SVG file exists, is well-formed XML, and has standard 120x120 viewBox."""
        self.assertTrue(OUTPUT_SVG.exists(), f"Missing Rotom-Wash SVG at {OUTPUT_SVG}")
        content = OUTPUT_SVG.read_text(encoding="utf-8")
        self.assertIn('viewBox="0 0 120 120"', content)
        self.assertIn('xmlns="http://www.w3.org/2000/svg"', content)

        # Parse XML tree to verify structural validity
        try:
            root = ET.fromstring(content)
            self.assertEqual(root.tag.split("}")[-1], "svg")
        except ET.ParseError as e:
            self.fail(f"Rotom-Wash SVG is not valid XML: {e}")

    def test_rotom_wash_svg_zero_procedural_penalties(self):
        """Verify the asset has zero creepy eyes, zero mannequin torso, and zero procedural penalties."""
        ref_png = SHOWDOWN_REF if SHOWDOWN_REF.exists() else None
        features = SVGFeatureExtractor.extract(OUTPUT_SVG, ref_png, category="sprite")

        self.assertEqual(features["has_creepy_eye"], 0.0, "Found creepy eye procedural marker in Rotom-Wash logo")
        self.assertEqual(features["has_generic_torso"], 0.0, "Found generic torso procedural marker in Rotom-Wash logo")
        self.assertEqual(features["has_generic_berry"], 0.0)
        self.assertEqual(features["has_generic_mega"], 0.0)
        self.assertEqual(features["has_text_fallback"], 0.0)
        self.assertEqual(features["is_primitive_blob"], 0.0)
        self.assertEqual(features["procedural_penalty"], 0.0)
        self.assertEqual(features["unmatched_primary"], 0.0)

    def test_rotom_wash_svg_palette_alignment_with_showdown(self):
        """Verify primary color aligns perfectly with Showdown reference sprite."""
        ref_png = SHOWDOWN_REF if SHOWDOWN_REF.exists() else None
        features = SVGFeatureExtractor.extract(OUTPUT_SVG, ref_png, category="sprite")

        # Color distance must be extremely low (near 0)
        self.assertLessEqual(features["primary_color_dist"], 15.0, "Primary color distance too high against Showdown sprite")
        self.assertGreaterEqual(features["distinct_colors"], 6.0, "Expected at least 6 distinct colors for rich shading")

        # Key theme colors present in SVG
        content = OUTPUT_SVG.read_text(encoding="utf-8").lower()
        self.assertTrue("#ff5d22" in content or "#e07020" in content, "Missing Rotom orange plasma color")
        self.assertTrue("#0ea5e9" in content or "#38bdf8" in content, "Missing Rotom hydro cyan color")

    def test_rotom_wash_svg_ml_acceptance_score_exceeds_99_5_percent(self):
        """Verify that AssetQualityClassifier outputs >= 99.5% acceptance probability."""
        score = evaluate_rotom_wash_quality()
        self.assertGreaterEqual(
            score, 0.995,
            f"Rotom-Wash SVG acceptance score {score*100:.2f}% did not meet mandatory 99.5% threshold"
        )


if __name__ == "__main__":
    unittest.main()
