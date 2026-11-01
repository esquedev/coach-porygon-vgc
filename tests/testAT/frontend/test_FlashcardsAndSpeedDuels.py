#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit & Acceptance Tests for Flash Cards & Speed Duels UX
Verifies:
1. All 42 Flash Card scenarios have clean, spoiler-free option labels before submission.
2. All items in Flash Card scenarios and Speed Duels are strictly legal in Regulation M-C.
3. Item Clause compliance across player and opponent slots in all Flash Card scenarios.
4. Zero blacklisted species appear in active battle slots across Flash Card scenarios.
5. All 25 Speed Duels have hidden speeds initially, valid calculatedSpe, and legal items.
6. Command center HTML contains native in-place destello animation (<animate attributeName="r">).
"""

import csv
from pathlib import Path
import re
import pyhocon
from pyhocon import ConfigFactory
import unittest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
from tests.test_constants import TEST_DATA_DIR
from engine.scenarios_data import FLASHCARD_SCENARIOS
from engine.speed_duels_data import SPEED_DUELS
from engine.validate_roster import load_legal_items


class TestFlashcardsAndSpeedDuels(unittest.TestCase):
    """Test suite for Flash Cards and Speed Duels spoiler-free and format-grounded user experience."""

    @classmethod
    def setUpClass(cls):
        """Load authoritative Regulation M-C legal items and species blacklist."""
        cls.legal_items = load_legal_items()
        cls.blacklist = [
            "Ursaluna", "Bloodmoon", "Flutter Mane", "Chi-Yu", "Chien-Pao", "Ting-Lu",
            "Iron Bundle", "Iron Hands", "Iron Leaves", "Iron Boulder", "Iron Crown",
            "Roaring Moon", "Scream Tail", "Brute Bonnet", "Sandy Shocks", "Slither Wing",
            "Ogerpon", "Urshifu", "Amoonguss", "Gastrodon", "Landorus", "Tornadus",
            "Thundurus", "Enamorus", "Heatran", "Cresselia"
        ]

    def test_all_flashcard_scenarios_have_no_spoilers_in_labels(self):
        """Ensure no Flash Card scenario option label exposes answers prior to answering."""
        spoilers = [
            'minimax', 'fuga táctica', 'fuga tactica', 'óptima', 'optima',
            '(pos-', '(tgt-', '(mec-', '(spd-',
            'control de velocidad seguro', 'inversión de velocidad'
        ]
        violations = []
        self.assertEqual(len(FLASHCARD_SCENARIOS), 42, "Expected exactly 42 Flash Card scenarios")

        for sc in FLASHCARD_SCENARIOS:
            options = sc.get("options", [])
            self.assertEqual(len(options), 4, f"{sc['id']} must have exactly 4 options")

            # Verify exactly one optimal option
            optimal_count = sum(1 for o in options if o.get("optimal") is True)
            self.assertEqual(optimal_count, 1, f"{sc['id']} must have exactly 1 optimal option")

            for opt in options:
                lbl = opt.get("label", "").lower()
                for sp in spoilers:
                    if sp in lbl:
                        violations.append((sc["id"], opt["id"], sp, opt.get("label")))

        self.assertEqual(violations, [], f"Found spoiler tokens in scenario labels: {violations}")

    def test_flashcard_scenarios_all_items_strictly_legal_in_regulation_mc(self):
        """Verify that every held item across all 42 Flash Card scenarios is strictly legal in Regulation M-C."""
        illegal_items = []
        for sc in FLASHCARD_SCENARIOS:
            for side in ["oppSlots", "mySlots"]:
                for mon in sc.get(side, []):
                    item = mon.get("item", "").strip()
                    if item and item.lower() not in ("none", "no item", "sin objeto"):
                        clean_item = item.replace("’", "'").strip().lower()
                        if clean_item not in self.legal_items:
                            illegal_items.append((sc["id"], side, mon.get("name"), item))

        self.assertEqual(
            illegal_items,
            [],
            f"Found items not present in Regulation M-C inside Flash Card scenarios: {illegal_items}"
        )

        # Also verify data/Flashcard_Scenarios.csv directly
        csv_path = TEST_DATA_DIR / "Flashcard_Scenarios.csv"
        self.assertTrue(csv_path.exists(), "Flashcard_Scenarios.csv must exist on disk")
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            csv_illegal = []
            for row in reader:
                sc_id = row.get("Scenario_ID", "")
                for col in ["Opp_Slot1_Item", "Opp_Slot2_Item", "My_Slot1_Item", "My_Slot2_Item"]:
                    val = row.get(col, "").strip()
                    if val and val.lower() not in ("none", "no item", "sin objeto"):
                        clean_val = val.replace("’", "'").strip().lower()
                        if clean_val not in self.legal_items:
                            csv_illegal.append((sc_id, col, val))

        self.assertEqual(csv_illegal, [], f"Found illegal items in Flashcard_Scenarios.csv: {csv_illegal}")

    def test_flashcard_scenarios_item_clause_compliance(self):
        """Ensure no side (player or opponent) violates Item Clause by equipping duplicate items."""
        item_clause_violations = []
        for sc in FLASHCARD_SCENARIOS:
            my_items = [
                m.get("item", "").strip().lower()
                for m in sc.get("mySlots", [])
                if m.get("item") and m.get("item").lower() not in ("none", "no item", "sin objeto")
            ]
            if len(my_items) != len(set(my_items)):
                item_clause_violations.append((sc["id"], "mySlots", my_items))

            opp_items = [
                m.get("item", "").strip().lower()
                for m in sc.get("oppSlots", [])
                if m.get("item") and m.get("item").lower() not in ("none", "no item", "sin objeto")
            ]
            if len(opp_items) != len(set(opp_items)):
                item_clause_violations.append((sc["id"], "oppSlots", opp_items))

        self.assertEqual(
            item_clause_violations,
            [],
            f"Found Item Clause violations in Flash Card scenarios: {item_clause_violations}"
        )

    def test_flashcard_scenarios_no_blacklisted_or_illegal_species(self):
        """Ensure no blacklisted species from Regulation M-C appears on board slots in Flash Card scenarios."""
        found_blacklisted = []
        for sc in FLASHCARD_SCENARIOS:
            for side in ["oppSlots", "mySlots"]:
                for mon in sc.get(side, []):
                    name = mon.get("name", "")
                    for banned in self.blacklist:
                        if banned.lower() in name.lower():
                            found_blacklisted.append((sc["id"], side, name, banned))

        self.assertEqual(
            found_blacklisted,
            [],
            f"Found blacklisted species in Flash Card active battle slots: {found_blacklisted}"
        )

    def test_speed_duels_initial_conditions_hide_raw_speed_numbers(self):
        """Ensure Speed Duel conditions do not display bare parenthetical speeds like '(169 Spe)'."""
        self.assertEqual(len(SPEED_DUELS), 25, "Expected exactly 25 Speed Duels")

        for d in SPEED_DUELS:
            self.assertIn(d["winner"], ["A", "B", "TIE"], f"{d['id']} winner must be A, B, or TIE")

            monA = d["monA"]
            monB = d["monB"]

            # Verify calculatedSpe is valid integer > 0
            self.assertIsInstance(monA.get("calculatedSpe"), int)
            self.assertGreater(monA.get("calculatedSpe"), 0)
            self.assertIsInstance(monB.get("calculatedSpe"), int)
            self.assertGreater(monB.get("calculatedSpe"), 0)

            # Condition should not leak the exact Spe number in parentheses
            self.assertNotRegex(monA.get("condition", ""), r"\(\d+\s*Spe\)", f"{d['id']} monA condition leaked speed")
            self.assertNotRegex(monB.get("condition", ""), r"\(\d+\s*Spe\)", f"{d['id']} monB condition leaked speed")

    def test_speed_duels_all_items_and_species_legal(self):
        """Ensure all held items and species featured in Speed Duels are legal in Regulation M-C."""
        for d in SPEED_DUELS:
            for mon_key in ["monA", "monB"]:
                mon = d[mon_key]
                species = mon.get("species", "")
                item = mon.get("item", "").strip()

                for banned in self.blacklist:
                    self.assertNotIn(
                        banned.lower(),
                        species.lower(),
                        f"{d['id']} {mon_key} features blacklisted species '{species}'"
                    )

                if item and item.lower() not in ("none", "no item", "sin objeto"):
                    clean_item = item.replace("’", "'").strip().lower()
                    self.assertIn(
                        clean_item,
                        self.legal_items,
                        f"{d['id']} {mon_key} has illegal item '{item}'"
                    )

    def test_equity_curve_inflection_destello_en_sitio(self):
        """Ensure turning point uses native in-place SVG animation without animate-ping displacement."""
        cc_html_path = REPO_ROOT / "assets" / "command_center.html"
        self.assertTrue(cc_html_path.exists(), "assets/command_center.html must exist")

        html = cc_html_path.read_text(encoding="utf-8")

        # Verify no animate-ping on SVG circle elements
        ping_circles = re.findall(r'<circle[^>]*animate-ping', html)
        self.assertEqual(len(ping_circles), 0, "Equity curve must not use animate-ping on SVG circles")

        # Verify presence of native SVG in-place pulse
        self.assertIn('attributeName="r"', html, "Equity curve must feature native radial pulse")
        self.assertIn('attributeName="opacity"', html, "Equity curve must feature opacity flash")

        # Verify initial speed display is hidden ???
        self.assertIn('id="speed-cond-a">⚡ Velocidad: <span class="text-amber-400 font-bold">???</span>', html)
        self.assertIn('id="speed-cond-b">⚡ Velocidad: <span class="text-amber-400 font-bold">???</span>', html)


if __name__ == "__main__":
    unittest.main()
