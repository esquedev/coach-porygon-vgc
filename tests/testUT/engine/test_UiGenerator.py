#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for UI Generator (engine/ui_generator.py)
Validates live telemetry loading, Pokedex database ingestion, Victory Point curve
trajectories, prompt filtering, and SVG compatibility stubs.
"""

from pathlib import Path
import unittest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())

from engine.ui_generator import (
    compute_vp_curve_for_match,
    load_live_telemetry,
    load_pokedex_db,
    write_svg_assets,
)
from engine.ui_server import execute_prompt_crawl_and_dump


class TestUiGenerator(unittest.TestCase):
    """Unit tests for UI generator and telemetry snapshot engine."""

    def test_load_live_telemetry_structure(self):
        """Verify load_live_telemetry populates all required high-level dashboard keys."""
        data = load_live_telemetry()
        self.assertIsInstance(data, dict)
        self.assertIn("total_matches", data)
        self.assertIn("total_calcs", data)
        self.assertIn("teams", data)
        self.assertIn("pokedex", data)
        self.assertIn("raw_matches", data)
        self.assertIn("diagnostics", data)
        self.assertIn("munchstats_overview", data)
        self.assertGreater(data["total_matches"], 0)
        self.assertGreater(data["total_calcs"], 0)
        self.assertGreater(len(data["pokedex"]), 100)

    def test_load_pokedex_db(self):
        """Verify load_pokedex_db accurately parses Regulation M-C species and stat bounds."""
        pokedex = load_pokedex_db()
        self.assertIsInstance(pokedex, dict)
        self.assertGreaterEqual(len(pokedex), 300)

        # Test sample canonical format staple: Charizard
        self.assertIn("charizard", pokedex)
        char = pokedex["charizard"]
        self.assertEqual(char["name"], "Charizard")
        self.assertIn("Fire", char["types"])
        self.assertIn("Flying", char["types"])
        self.assertGreater(char["hp"], 0)
        self.assertGreater(char["spe"], 0)

        # Test Mega Evolution with required megastone: Mega Charizard Y
        self.assertIn("megacharizardy", pokedex)
        mega_y = pokedex["megacharizardy"]
        self.assertEqual(mega_y["req_item"], "Charizardite Y")

    def test_compute_vp_curve_for_match_win(self):
        """Verify compute_vp_curve_for_match generates a valid winning Victory Point curve."""
        match_data = {
            "Match_ID": "1",
            "Result": "Win",
            "Turns": "4",
            "First_Blood_Side": "user",
            "Misplay_Type": "None",
            "Key_RNG_Event": "None"
        }
        pts, tp_turn, tp_desc = compute_vp_curve_for_match(match_data, {})
        self.assertIsInstance(pts, list)
        self.assertEqual(len(pts), 5)  # Turn 0 + 4 turns
        self.assertEqual(pts[-1], 4.0)  # Terminal winning VP
        self.assertIsInstance(tp_turn, int)
        self.assertIsInstance(tp_desc, str)

    def test_compute_vp_curve_for_match_loss_with_misplay(self):
        """Verify compute_vp_curve_for_match reflects negative inflection on tactical misplay."""
        match_data = {
            "Match_ID": "2",
            "Result": "Loss",
            "Turns": "5",
            "First_Blood_Side": "opponent",
            "Misplay_Type": "Turn 2: POS-01 Dry Hard Switch",
            "Key_RNG_Event": "None"
        }
        diags = {
            "2": {"Turn_Occurred": "2", "Mistake_Code": "POS-01"}
        }
        pts, tp_turn, tp_desc = compute_vp_curve_for_match(match_data, diags)
        self.assertEqual(pts[-1], -4.0)  # Terminal losing VP
        self.assertEqual(tp_turn, 2)
        self.assertIn("Turno 2", tp_desc)
        # All VP values must respect the [-4.2, 4.2] engine boundary
        for pt in pts:
            self.assertGreaterEqual(pt, -4.2)
            self.assertLessEqual(pt, 4.2)

    def test_crawl_prompt_filtering(self):
        """Verify prompt dumper safely handles and filters tournament crawl parameters."""
        res = execute_prompt_crawl_and_dump("Nice", export_csv=False)
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("status"), "OK")
        self.assertIn("matched_teams_count", res)
        self.assertGreater(res["matched_teams_count"], 0)

    def test_write_svg_assets_backward_compatibility(self):
        """Verify write_svg_assets functions as a clean non-destructive stub."""
        res = write_svg_assets()
        self.assertIsInstance(res, dict)
        self.assertEqual(len(res), 0)


if __name__ == "__main__":
    unittest.main()
