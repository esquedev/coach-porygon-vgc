# -*- coding: utf-8 -*-
"""Integration tests for in-memory DuckDB VGC data registry (`engine.db_registry`)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.db_registry import VGCDataRegistry, get_registry


class TestDBRegistry(unittest.TestCase):
    """Verify DuckDB views, entity lookups, and tournament statistics."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = get_registry()

    def test_registered_database_views(self) -> None:
        """Verify all essential Showdown and Munchstats views are mounted."""
        expected_views = {
            "pokedex",
            "moves",
            "items",
            "abilities",
            "learnsets",
            "conditions",
            "tournament_standings",
            "tournament_usage",
            "tournament_overview",
        }
        tables = self.registry.query("SHOW TABLES;")
        active_views = {row["name"] for row in tables}
        for view in expected_views:
            self.assertIn(view, active_views, msg=f"Missing DuckDB view: {view}")

    def test_showdown_entity_lookups(self) -> None:
        """Verify querying Pokémon, moves, and conditions."""
        # 1. Pokemon lookup
        charizard = self.registry.get_pokemon("Charizard")
        self.assertIsNotNone(charizard)
        self.assertEqual(charizard.get("name"), "Charizard")
        self.assertIn("Fire", charizard.get("types", []))

        # 2. Move lookup
        hw = self.registry.get_move("Heat Wave")
        self.assertIsNotNone(hw)
        self.assertEqual(hw.get("name"), "Heat Wave")
        self.assertEqual(hw.get("type"), "Fire")
        self.assertEqual(hw.get("basePower"), 95)

        # 3. Condition lookup
        cond = self.registry.get_condition("sunnyday")
        self.assertIsNotNone(cond)

    def test_tournament_data_aggregations(self) -> None:
        """Verify tournament archives are accessible via SQL."""
        tourney_count = self.registry.query("SELECT COUNT(DISTINCT tournament_id) AS total FROM tournament_overview;")
        self.assertGreater(tourney_count[0]["total"], 0)

        standings_count = self.registry.query("SELECT COUNT(*) AS total FROM tournament_standings;")
        self.assertGreater(standings_count[0]["total"], 0)


if __name__ == "__main__":
    unittest.main()
