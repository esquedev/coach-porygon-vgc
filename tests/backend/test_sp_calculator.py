#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for 66-SP Calculator (engine/sp_calculator.py)
"""

import unittest

from engine.sp_calculator import validate_and_calculate_sp


class TestSpCalculator(unittest.TestCase):
    """Verifies Regulation M-C 66-SP allocation limits and Level 50 stat calculation."""
    def test_bijective_ev_sp_conversion(self):
        """Test exact conversion between Showdown EVs and Regulation M-C SPs."""
        from engine.sp_calculator import ev_to_sp, sp_to_ev

        # Edge cases & sequence: 0->0, 1->4, 2->12, 3->20, 4->28, 32->252
        expected_mappings = [
            (0, 0),
            (1, 4),
            (2, 12),
            (3, 20),
            (4, 28),
            (10, 76),
            (16, 124),
            (32, 252),
        ]
        for sp, ev in expected_mappings:
            self.assertEqual(sp_to_ev(sp), ev, f"sp_to_ev({sp}) should be {ev}")
            self.assertEqual(ev_to_sp(ev), sp, f"ev_to_sp({ev}) should be {sp}")


    def test_valid_66_sp_spread(self):
        """Test for valid 66 sp spread."""
        sp = {"hp": 22, "atk": 28, "def": 0, "spa": 0, "spd": 0, "spe": 16}
        is_valid, ver_str, stats = validate_and_calculate_sp("Garchomp", sp, nature="Adamant")
        self.assertTrue(is_valid)
        self.assertEqual(ver_str, "22 HP + 28 Atk + 0 Def + 0 SpA + 0 SpD + 16 Spe = 66 SP")
        self.assertGreater(stats["hp"], 100)
        self.assertGreater(stats["atk"], 150)

    def test_rejects_sp_overflow_67_sp(self):
        """Test for rejects sp overflow 67 sp."""
        sp = {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 3}
        is_valid, ver_str, stats = validate_and_calculate_sp("Garchomp", sp, nature="Jolly")
        self.assertFalse(is_valid)
        self.assertIn("Deviates from mandatory 66 SP", ver_str)

    def test_rejects_single_stat_over_32_sp(self):
        """Test for rejects single stat over 32 sp."""
        sp = {"hp": 34, "atk": 20, "def": 0, "spa": 0, "spd": 0, "spe": 12}
        is_valid, ver_str, stats = validate_and_calculate_sp("Garchomp", sp, nature="Jolly")
        self.assertFalse(is_valid)
        self.assertIn("exceeds the 32 SP single-stat hard cap", ver_str)

    def test_rejects_negative_sp(self):
        """Test for rejects negative sp."""
        sp = {"hp": -4, "atk": 32, "def": 10, "spa": 0, "spd": 0, "spe": 28}
        is_valid, ver_str, stats = validate_and_calculate_sp("Garchomp", sp, nature="Jolly")
        self.assertFalse(is_valid)
        self.assertIn("Negative SP detected", ver_str)


if __name__ == "__main__":
    unittest.main()
