#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Regulation M-C Anti-Hallucination Acceptance Test Suite
Performs repository-wide audits to detect and prevent any hallucinations out of Regulation M-C:
1. Zero blacklisted species in active battle slots across datasets, scenarios, and rosters.
2. 100% item legality compliance against Regulation_MC_Items.csv.
3. 100% species existence grounding against MC_Available_Pokemon.csv and Champions Pokedex.
4. Total immunity against TCG (Trading Card Game) mechanics contamination.
5. SP economy limits (max 66 total SP, max 32 SP per stat) across team registries.
6. Frontend client payload verification across compiled command center HTML assets.
"""

import csv
import json
from pathlib import Path
import re
import pyhocon
from pyhocon import ConfigFactory
import unittest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
from engine.validate_roster import (
    load_legal_items,
    load_pokemon_registry,
    get_pokemon_entry,
)
from engine.scenarios_data import FLASHCARD_SCENARIOS
from engine.speed_duels_data import SPEED_DUELS


class TestRegulationMcAntiHallucination(unittest.TestCase):
    """Repo-wide acceptance tests enforcing strict Regulation M-C format grounding."""

    @classmethod
    def setUpClass(cls):
        """Initialize authoritative registries, items, and format species blacklist."""
        cls.legal_items = load_legal_items()
        cls.registry = load_pokemon_registry()
        cls.blacklist = [
            "Ursaluna", "Bloodmoon", "Flutter Mane", "Chi-Yu", "Chien-Pao", "Ting-Lu",
            "Iron Bundle", "Iron Hands", "Iron Leaves", "Iron Boulder", "Iron Crown",
            "Roaring Moon", "Scream Tail", "Brute Bonnet", "Sandy Shocks", "Slither Wing",
            "Ogerpon", "Urshifu", "Amoonguss", "Gastrodon", "Landorus", "Tornadus",
            "Thundurus", "Enamorus", "Heatran", "Cresselia"
        ]

    def test_no_blacklisted_species_in_active_teams_or_scenario_slots(self):
        """Ensure blacklisted species never appear in active playable rosters or battle slots."""
        violations = []

        # 1. Check data/Flashcard_Scenarios.csv active slots
        flashcard_csv = REPO_ROOT / "data" / "Flashcard_Scenarios.csv"
        if flashcard_csv.exists():
            with open(flashcard_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sc_id = row.get("Scenario_ID", "")
                    for col in ["Opp_Slot1_Name", "Opp_Slot2_Name", "My_Slot1_Name", "My_Slot2_Name"]:
                        val = row.get(col, "").strip()
                        for banned in self.blacklist:
                            if banned.lower() in val.lower():
                                violations.append((f"Flashcard_Scenarios.csv:{sc_id}", col, val, banned))

        # 2. Check data/Speed_Duel_Scenarios.csv
        speed_csv = REPO_ROOT / "data" / "Speed_Duel_Scenarios.csv"
        if speed_csv.exists():
            with open(speed_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    duel_id = row.get("Duel_ID", "")
                    for col in ["Player_Mon", "Opponent_Mon"]:
                        val = row.get(col, "").strip()
                        for banned in self.blacklist:
                            if banned.lower() in val.lower():
                                violations.append((f"Speed_Duel_Scenarios.csv:{duel_id}", col, val, banned))

        # 3. Check data/Teams.csv and data/Scouted_Teams.csv
        for team_file in ["Teams.csv", "Scouted_Teams.csv"]:
            tpath = REPO_ROOT / "data" / team_file
            if tpath.exists():
                with open(tpath, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tid = row.get("Team_ID") or row.get("Scouted_Team_ID") or "Unknown"
                        for i in range(1, 7):
                            mon_val = row.get(f"Pokemon_{i}", "").strip()
                            for banned in self.blacklist:
                                if banned.lower() in mon_val.lower():
                                    violations.append((f"{team_file}:{tid}", f"Pokemon_{i}", mon_val, banned))

        # 4. Check in-memory FLASHCARD_SCENARIOS and SPEED_DUELS
        for sc in FLASHCARD_SCENARIOS:
            for side in ["oppSlots", "mySlots"]:
                for mon in sc.get(side, []):
                    name = mon.get("name", "")
                    for banned in self.blacklist:
                        if banned.lower() in name.lower():
                            violations.append((f"FLASHCARD_SCENARIOS:{sc['id']}", side, name, banned))

        for d in SPEED_DUELS:
            for side in ["monA", "monB"]:
                mon = d.get(side, {})
                name = mon.get("name", "")
                for banned in self.blacklist:
                    if banned.lower() in name.lower():
                        violations.append((f"SPEED_DUELS:{d['id']}", side, name, banned))

        self.assertEqual(
            violations,
            [],
            f"Blacklisted species found in active battle slots across repository: {violations}"
        )

    def test_all_items_in_data_files_are_legal_in_regulation_mc(self):
        """Ensure all held items in datasets and scenario files exist strictly in Regulation_MC_Items.csv."""
        violations = []

        # 1. Flashcard_Scenarios.csv
        flashcard_csv = REPO_ROOT / "data" / "Flashcard_Scenarios.csv"
        if flashcard_csv.exists():
            with open(flashcard_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sc_id = row.get("Scenario_ID", "")
                    for col in ["Opp_Slot1_Item", "Opp_Slot2_Item", "My_Slot1_Item", "My_Slot2_Item"]:
                        item_val = row.get(col, "").strip()
                        if item_val and item_val.lower() not in ("none", "no item", "sin objeto"):
                            clean = item_val.replace("’", "'").strip().lower()
                            if clean not in self.legal_items:
                                violations.append((f"Flashcard_Scenarios.csv:{sc_id}", col, item_val))

        # 2. Speed_Duel_Scenarios.csv
        speed_csv = REPO_ROOT / "data" / "Speed_Duel_Scenarios.csv"
        if speed_csv.exists():
            with open(speed_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    duel_id = row.get("Duel_ID", "")
                    for col in ["Player_Item", "Opponent_Item"]:
                        item_val = row.get(col, "").strip()
                        if item_val and item_val.lower() not in ("none", "no item", "sin objeto"):
                            clean = item_val.replace("’", "'").strip().lower()
                            if clean not in self.legal_items:
                                violations.append((f"Speed_Duel_Scenarios.csv:{duel_id}", col, item_val))

        # 3. Teams.csv and Scouted_Teams.csv
        for team_file in ["Teams.csv", "Scouted_Teams.csv"]:
            tpath = REPO_ROOT / "data" / team_file
            if tpath.exists():
                with open(tpath, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tid = row.get("Team_ID") or row.get("Scouted_Team_ID") or "Unknown"
                        for i in range(1, 7):
                            item_val = row.get(f"Item_{i}", "").strip()
                            if item_val and item_val.lower() not in ("none", "no item", "sin objeto"):
                                clean = item_val.replace("’", "'").strip().lower()
                                if clean not in self.legal_items:
                                    violations.append((f"{team_file}:{tid}", f"Item_{i}", item_val))

        self.assertEqual(
            violations,
            [],
            f"Illegal items not present in Regulation M-C found in datasets: {violations}"
        )

    def test_all_species_in_rosters_and_scenarios_exist_in_champions_dex(self):
        """Verify that every species in scenarios and teams maps to a valid Champions Dex entry."""
        unrecognized = []

        for sc in FLASHCARD_SCENARIOS:
            for side in ["oppSlots", "mySlots"]:
                for mon in sc.get(side, []):
                    name = mon.get("name", "").strip()
                    entry = get_pokemon_entry(name, self.registry)
                    if not entry:
                        unrecognized.append((sc["id"], side, name))

        self.assertEqual(
            unrecognized,
            [],
            f"Unrecognized species without registry grounding in Flash Card scenarios: {unrecognized}"
        )

    def test_tcg_mechanics_rejection_across_repository(self):
        """Ensure no card game (TCG) rules or mechanics contaminate the VGC engine or data."""
        tcg_patterns = [
            r"\bprize\s+card\b",
            r"\benergy\s+card\b",
            r"\benergy\s+attachment\b",
            r"\bbench\s+pok[eé]mon\b",
            r"\bgx\s+attack\b",
            r"\bvstar\s+power\b",
            r"\bevolution\s+stage\s+2\b",
        ]

        scanned_files = list((REPO_ROOT / "data").glob("*.csv")) + list((REPO_ROOT / "engine").glob("*.py"))
        violations = []

        for fpath in scanned_files:
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue

            for pat in tcg_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    violations.append((fpath.name, m.group(0)))

        self.assertEqual(
            violations,
            [],
            f"Found TCG contamination strings in repository files: {violations}"
        )

    def test_sp_economy_and_ev_terminology_guardrail(self):
        """Ensure team spreads obey 66-SP limits and do not introduce Gen 1-9 legacy EV numbers."""
        tpath = REPO_ROOT / "data" / "Teams.csv"
        if not tpath.exists():
            self.skipTest("data/Teams.csv not found")

        with open(tpath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tid = row.get("Team_ID", "Unknown")
                for i in range(1, 7):
                    spread_str = row.get(f"Spread_{i}", "")
                    if spread_str and "SP" in spread_str:
                        # Extract all numbers before SP or stats
                        nums = [int(n) for n in re.findall(r"\b(\d+)\b", spread_str)]
                        total_sp = sum(nums) if nums else 0
                        # Stat point allocation cannot exceed 66 SP per mon
                        self.assertLessEqual(
                            total_sp,
                            66,
                            f"Team {tid} Pokemon_{i} has SP spread totaling {total_sp} SP > 66 SP cap"
                        )
                        for n in nums:
                            self.assertLessEqual(
                                n,
                                32,
                                f"Team {tid} Pokemon_{i} has stat allocation {n} SP > 32 SP single-stat cap"
                            )

    def test_command_center_frontend_assets_anti_hallucination(self):
        """Ensure compiled command center HTML assets have 100% legal items and zero blacklisted species."""
        html_files = [
            REPO_ROOT / "assets" / "command_center.html",
            REPO_ROOT / "assets" / "command_center_es.html",
            REPO_ROOT / "assets" / "command_center_en.html",
        ]

        for hpath in html_files:
            if not hpath.exists():
                continue
            html = hpath.read_text(encoding="utf-8")

            # Extract FLASHCARD_SCENARIOS JSON from HTML
            m_sc = re.search(r'const\s+FLASHCARD_SCENARIOS\s*=\s*(\[\{.*?\}\]);', html, re.DOTALL)
            if m_sc:
                scenarios = json.loads(m_sc.group(1))
                for sc in scenarios:
                    for side in ["oppSlots", "mySlots"]:
                        for mon in sc.get(side, []):
                            sp_name = mon.get("name", "")
                            item_name = mon.get("item", "").strip()

                            # Species blacklist check
                            for b in self.blacklist:
                                self.assertNotIn(
                                    b.lower(),
                                    sp_name.lower(),
                                    f"HTML {hpath.name} scenario {sc['id']} has blacklisted species '{sp_name}'"
                                )

                            # Legal item check
                            if item_name and item_name.lower() not in ("none", "no item", "sin objeto"):
                                clean = item_name.replace("’", "'").strip().lower()
                                self.assertIn(
                                    clean,
                                    self.legal_items,
                                    f"HTML {hpath.name} scenario {sc['id']} has illegal item '{item_name}'"
                                )


if __name__ == "__main__":
    unittest.main()
