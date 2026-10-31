#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for engine/report_generator.py
Validates:
1. Palette availability and token integrity (rotom-wash, rayquaza-shiny, porygon).
2. Deterministic HTML generation for Team Audits and Match Breakdowns.
3. Print/PDF CSS optimizations and page-break rules.
4. Headless PDF compilation and fallback resilience.
"""

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.report_generator import (
    THEMES,
    build_base_css,
    export_pdf,
    find_browser_executable,
    generate_match_breakdown_html,
    generate_sample_team_audit,
    generate_team_audit_html,
)


class TestReportGenerator(unittest.TestCase):
    """Test suite for deterministic multi-theme report generation."""

    def test_theme_palettes_completeness(self):
        """Verify all three requested themes exist with required styling attributes."""
        expected_themes = ["rotom-wash", "rayquaza-shiny", "porygon"]
        for theme_key in expected_themes:
            self.assertIn(theme_key, THEMES, f"Missing theme: {theme_key}")
            palette = THEMES[theme_key]
            for req_key in [
                "bg", "card_bg", "card_border", "text_primary", "text_muted",
                "accent_primary", "accent_secondary", "stat_hp", "banner_gradient"
            ]:
                self.assertIn(req_key, palette, f"Theme {theme_key} missing key {req_key}")

    def test_css_generation_and_print_optimizations(self):
        """Verify CSS contains necessary print-color-adjust and page-break properties."""
        for theme in ["rotom-wash", "rayquaza-shiny", "porygon"]:
            css = build_base_css(theme)
            self.assertIn("-webkit-print-color-adjust: exact", css)
            self.assertIn("page-break-inside: avoid", css)
            self.assertIn("@page", css)
            self.assertIn(THEMES[theme]["bg"], css)

    def test_team_audit_html_structure(self):
        """Verify generated Team Audit HTML contains all relevant sections, 66-SP tracking, and legal disclaimers."""
        sample_team = {
            "team_id": "T01",
            "name": "Test Balanced Core",
            "archetype": "Balance",
            "trainer": "brightvgc",
            "members": [
                {
                    "species": "Charizard-Mega-Y",
                    "item": "Charizardite Y",
                    "ability": "Drought",
                    "nature": "Timid",
                    "moves": ["Heat Wave", "Solar Beam", "Protect", "Weather Ball"],
                    "sp": {"hp": 12, "atk": 0, "def": 4, "spa": 24, "spd": 4, "spe": 22},
                    "stats_lv50": {"hp": 155, "atk": 111, "def": 99, "spa": 204, "spd": 136, "spe": 158}
                }
            ]
        }
        html = generate_team_audit_html(sample_team, theme="rotom-wash")
        self.assertIn("ROSTER AUDIT • T01", html)
        self.assertIn("Charizard-Mega-Y", html)
        self.assertIn("66 SP", html)
        self.assertIn("Made by", html)
        self.assertIn("berightvgc", html)
        self.assertIn("Powered by", html)
        self.assertIn("Gemini", html)
        self.assertIn("fair use", html)

    def test_match_breakdown_html_structure(self):
        """Verify Match Breakdown HTML includes turning points and mistake taxonomy."""
        match_data = {
            "match_id": "M-TEST-001",
            "user_trainer": "aws_secret",
            "opponent": "Opponent_Trainer",
            "result": "WIN",
            "vp_delta": "+3.5 VP",
            "turning_point_turn": 3,
            "mistake_code": "POS-01",
            "cognitive_driver": "Tunnel_Vision",
            "turns_log": [
                {"turn": 1, "action_user": "Protect Charizard", "action_opp": "Fake Out", "vp": "+0.5", "notes": "Safe positioning"},
                {"turn": 3, "action_user": "Heat Wave double KO", "action_opp": "Protect fail", "vp": "+3.0", "notes": "Turning point executed"}
            ]
        }
        html = generate_match_breakdown_html(match_data, theme="rayquaza-shiny")
        self.assertIn("MATCH AUDIT • M-TEST-001", html)
        self.assertIn("POS-01", html)
        self.assertIn("Tunnel_Vision", html)
        self.assertIn("TURNING POINT", html)
        self.assertIn("+3.5 VP", html)

    def test_pdf_export_execution(self):
        """Verify export_pdf produces HTML and attempts PDF export with positive status."""
        res = generate_sample_team_audit(theme="rotom-wash")
        self.assertTrue(res["success"])
        self.assertTrue(Path(res["html_path"]).exists())
        if res.get("pdf_path"):
            pdf_path = Path(res["pdf_path"])
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
