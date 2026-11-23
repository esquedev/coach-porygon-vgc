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

    def test_sister_forms_and_base_forme_aliases(self) -> None:
        """Verify legal otherFormes and Showdown baseForme aliases resolve cleanly."""
        palafin_hero = self.registry.get_pokemon("Palafin-Hero")
        self.assertIsNotNone(palafin_hero)
        self.assertEqual(palafin_hero.get("atk"), 160)

        meowstic_f = self.registry.get_pokemon("Meowstic-F")
        self.assertIsNotNone(meowstic_f)

        maushold_four = self.registry.get_pokemon("Maushold-Four")
        self.assertIsNotNone(maushold_four)

        maushold_three = self.registry.get_pokemon("Maushold-Three")
        self.assertIsNotNone(maushold_three)
        self.assertEqual(maushold_three.get("id"), "maushold")

    def test_tournament_data_aggregations(self) -> None:
        """Verify tournament archives are accessible via SQL."""
        tourney_count = self.registry.query("SELECT COUNT(DISTINCT tournament_id) AS total FROM tournament_overview;")
        self.assertGreater(tourney_count[0]["total"], 0)

        standings_count = self.registry.query("SELECT COUNT(*) AS total FROM tournament_standings;")
        self.assertGreater(standings_count[0]["total"], 0)

    def test_champions_reg_mc_ndjson_integrity_and_joins(self) -> None:
        """Verify zero corrupted NDJSON objects, zero nonstandard leaks, and 100% tournament species joins."""
        import json
        from engine.vgc_tensor_core.compiler import ShowdownTensorCompiler
        from engine.vgc_tensor_core.schema_and_tables import MoveIdx

        showdown_dir = REPO_ROOT / "src" / "engine" / "data" / "showdown"
        for fn in (
            "pokedex.jsonl",
            "moves.jsonl",
            "items.jsonl",
            "abilities.jsonl",
            "conditions.jsonl",
            "learnsets.jsonl",
        ):
            for line in (showdown_dir / fn).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                for key, val in row.items():
                    if isinstance(val, str):
                        stripped = val.strip()
                        self.assertFalse(
                            stripped.startswith(("{", "[")),
                            msg=f"Corrupted stringified JS object in {fn} ({row.get('id')}.{key}): {val}",
                        )
                if fn == "moves.jsonl":
                    self.assertNotIn("zMove", row)
                    self.assertNotIn("maxMove", row)

        for tbl in ("moves", "items", "abilities"):
            cols = {c["column_name"] for c in self.registry.query(f"DESCRIBE {tbl};")}
            if "isNonstandard" in cols:
                nonstd = self.registry.query(
                    f"SELECT COUNT(*) AS cnt FROM {tbl} WHERE isNonstandard IS NOT NULL;"
                )[0]["cnt"]
                self.assertEqual(nonstd, 0, msg=f"Leaked isNonstandard rows in {tbl}")

        unmatched = self.registry.query(
            "SELECT DISTINCT species FROM tournament_team_slots WHERE species NOT IN (SELECT name FROM pokedex);"
        )
        self.assertEqual(unmatched, [], msg=f"Unmatched tournament species: {unmatched}")

        comp = ShowdownTensorCompiler(registry=self.registry, backend="numpy")
        dire_claw = comp.compile_move_vector("Dire Claw")
        self.assertEqual(float(dire_claw[MoveIdx.IS_CONTACT]), 1.0)
        alluring = comp.compile_move_vector("Alluring Voice")
        self.assertEqual(float(alluring[MoveIdx.IS_SOUND_MOVE]), 1.0)
        self.assertEqual(float(alluring[MoveIdx.BYPASS_SUB]), 1.0)


if __name__ == "__main__":
    unittest.main()
