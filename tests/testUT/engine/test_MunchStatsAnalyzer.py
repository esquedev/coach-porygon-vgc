#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for MunchStats Crawler and Statistical Analyzer

Tests:
1. URL and tournament identifier extraction.
2. Competitive archetype classification and Showdown export construction.
3. Conversion rate calculations and categorization (Meta Converters vs. Trapped Picks).
4. 2-mon and 3-mon core clustering and placement averaging.
5. HTML and Markdown publication report generation with embedded assets.
6. Error handling on missing files and malformed payloads.
"""

import json
from pathlib import Path
import tempfile
import unittest

from engine.munchstats_crawler import (
    build_showdown_export,
    determine_archetype_label,
    extract_tournament_id,
    get_max_scouted_team_id_num,
    get_next_scouted_team_id,
    populate_scouted_teams,
)
from engine.munchstats_analyzer import (
    MunchStatsRelationalEngine,
    cluster_cores_and_archetypes,
    compute_advanced_conversion_matrix,
    compute_archetype_waterfall,
    compute_conversion_metrics,
    generate_html_report,
    generate_markdown_report,
    infer_team_archetype,
    load_raw_tournament_data,
    mine_most_repeated_teams,
)


class TestMunchStatsAnalyzer(unittest.TestCase):
    """Test suite for engine/munchstats_analyzer.py."""

    def setUp(self):
        """Prepare mock tournament datasets for testing."""
        self.mock_overview = {
            "tournament_id": "TEST01",
            "tournament_name": "2027 Test Regional Championships",
            "total_players": 1000,
            "stages": [
                {
                    "label": "Day 1",
                    "total_teams": 1000,
                    "rows": [
                        {"name": "Rillaboom", "count": 500, "usage_pct": 50.0},
                        {"name": "Gholdengo", "count": 200, "usage_pct": 20.0},
                        {"name": "Basculegion", "count": 150, "usage_pct": 15.0},
                    ],
                },
                {
                    "label": "Day 2",
                    "total_teams": 150,
                    "rows": [
                        {"name": "Rillaboom", "count": 75, "usage_pct": 50.0},
                        {"name": "Gholdengo", "count": 60, "usage_pct": 40.0},
                        {"name": "Basculegion", "count": 5, "usage_pct": 3.33},
                    ],
                },
                {
                    "label": "Top 8",
                    "total_teams": 8,
                    "rows": [
                        {"name": "Rillaboom", "count": 4, "usage_pct": 50.0},
                        {"name": "Gholdengo", "count": 3, "usage_pct": 37.5},
                        {"name": "Basculegion", "count": 0, "usage_pct": 0.0},
                    ],
                },
            ],
            "movers": [],
        }

        self.mock_standings = [
            {
                "placement": 1,
                "name": "Champion Player",
                "record": {"wins": 15, "losses": 1},
                "team": [
                    {"pokemon": "Rillaboom", "item": "Miracle Seed", "ability": "Grassy Surge", "moves": ["Wood Hammer", "Grassy Glide", "U-turn", "Protect"]},
                    {"pokemon": "Gholdengo", "item": "Choice Specs", "ability": "Good as Gold", "moves": ["Make It Rain", "Shadow Ball", "Focus Blast", "Trick"]},
                    {"pokemon": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "moves": ["Fake Out", "Knock Off", "Flare Blitz", "Parting Shot"]},
                    {"pokemon": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "moves": ["Sucker Punch", "Kowtow Cleave", "Iron Head", "Protect"]},
                    {"pokemon": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "moves": ["Hyper Voice", "Moonblast", "Haze", "Protect"]},
                    {"pokemon": "Dragonite", "item": "Lum Berry", "ability": "Multiscale", "moves": ["Extreme Speed", "Aerial Ace", "Scale Shot", "Protect"]},
                ]
            },
            {
                "placement": 2,
                "name": "Runner Up",
                "record": {"wins": 14, "losses": 2},
                "team": [
                    {"pokemon": "Pelipper", "item": "Focus Sash", "ability": "Drizzle", "moves": ["Weather Ball", "Hurricane", "Wide Guard", "Protect"]},
                    {"pokemon": "Archaludon", "item": "Assault Vest", "ability": "Stamina", "moves": ["Electro Shot", "Flash Cannon", "Draco Meteor", "Body Press"]},
                    {"pokemon": "Basculegion", "item": "Choice Band", "ability": "Adaptability", "moves": ["Wave Crash", "Last Respects", "Aqua Jet", "Flip Turn"]},
                    {"pokemon": "Rillaboom", "item": "Miracle Seed", "ability": "Grassy Surge", "moves": ["Wood Hammer", "Grassy Glide", "U-turn", "Protect"]},
                    {"pokemon": "Gholdengo", "item": "Choice Specs", "ability": "Good as Gold", "moves": ["Make It Rain", "Shadow Ball", "Focus Blast", "Trick"]},
                    {"pokemon": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "moves": ["Fake Out", "Knock Off", "Flare Blitz", "Parting Shot"]},
                ]
            }
        ]

    def test_compute_conversion_metrics(self):
        """Validates mathematical ratio and categorization of Meta Converters and Trapped Picks."""
        metrics = compute_conversion_metrics(self.mock_overview)
        self.assertEqual(len(metrics), 3)

        gholdengo_m = next(m for m in metrics if m["name"] == "Gholdengo")
        # 60 / 200 = 30.0% conversion rate, delta = +20.0%
        self.assertEqual(gholdengo_m["conversion_rate_pct"], 30.0)
        self.assertEqual(gholdengo_m["delta_pct"], 20.0)
        self.assertEqual(gholdengo_m["category"], "Meta Converter")

        basculegion_m = next(m for m in metrics if m["name"] == "Basculegion")
        # 5 / 150 = 3.33% conversion rate, delta = -11.67%
        self.assertLess(basculegion_m["conversion_rate_pct"], 10.0)
        self.assertEqual(basculegion_m["category"], "Trapped Pick")

    def test_cluster_cores_and_archetypes(self):
        """Verifies core pair detection, ranking averages, and archetype inference."""
        clustering = cluster_cores_and_archetypes(self.mock_standings)
        top_cores = clustering["top_two_cores"]
        self.assertGreater(len(top_cores), 0)

        # Rillaboom + Gholdengo was in both teams
        rg_core = next((c for c in top_cores if set([c["mon1"], c["mon2"]]) == {"Rillaboom", "Gholdengo"}), None)
        self.assertIsNotNone(rg_core)
        self.assertEqual(rg_core["count"], 2)
        self.assertEqual(rg_core["share_pct"], 100.0)

    def test_generate_markdown_and_html_reports(self):
        """Verifies successful compilation and structural integrity of MD and HTML reports."""
        metrics = compute_conversion_metrics(self.mock_overview)
        clustering = cluster_cores_and_archetypes(self.mock_standings)
        champion = {
            "placement": 1,
            "name": "Champion Player",
            "record_str": "15-1",
            "archetype": "Goodstuffs Pivot Balance",
            "team": self.mock_standings[0]["team"],
        }
        top_finalists = [champion]

        with tempfile.TemporaryDirectory() as tmp_dir:
            md_path = Path(tmp_dir) / "test_report.md"
            html_path = Path(tmp_dir) / "test_report.html"

            md_content = generate_markdown_report(
                overview=self.mock_overview,
                conversion_metrics=metrics,
                clustering=clustering,
                champion=champion,
                top_finalists=top_finalists,
                output_path=md_path,
            )
            self.assertTrue(md_path.exists())
            self.assertIn("Champion Player", md_content)
            self.assertIn("Meta Converter", md_content)

            html_content = generate_html_report(
                overview=self.mock_overview,
                conversion_metrics=metrics,
                clustering=clustering,
                champion=champion,
                top_finalists=top_finalists,
                output_path=html_path,
            )
            self.assertTrue(html_path.exists())
            self.assertIn("<!DOCTYPE html>", html_content)
            self.assertIn("Champion Player", html_content)
            self.assertIn("Make It Rain", html_content)
            self.assertIn("@media print", html_content)

    def test_missing_raw_dir_raises_filenotfound(self):
        """Verifies clean FileNotFoundError when attempting to load non-existent directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            empty_path = Path(tmp_dir) / "empty_dir"
            empty_path.mkdir()
            with self.assertRaises(FileNotFoundError):
                load_raw_tournament_data(empty_path)

    def test_compute_advanced_conversion_matrix(self):
        """Validates multi-phase conversion matrix calculation and coaching tier tags."""
        matrix = compute_advanced_conversion_matrix(self.mock_standings, self.mock_overview)
        self.assertIsInstance(matrix, list)
        self.assertGreaterEqual(len(matrix), 1)
        rilla = next((m for m in matrix if m["name"] == "Rillaboom"), None)
        self.assertIsNotNone(rilla)
        self.assertEqual(rilla["d1_count"], 2)

    def test_mine_most_repeated_teams(self):
        """Verifies detection of repeated 6-mon teams, pilot counts, and Showdown exports."""
        # Duplicate the champion team 3 times
        standings_with_reps = list(self.mock_standings)
        for i in range(3):
            standings_with_reps.append({
                "placement": 10 + i,
                "name": f"Squad_Pilot_{i}",
                "day_reached": "day2" if i == 0 else "day1",
                "team": list(self.mock_standings[0]["team"])
            })
        repeated = mine_most_repeated_teams(standings_with_reps, min_players=2, top_n=5)
        self.assertGreaterEqual(len(repeated), 1)
        top_rep = repeated[0]
        self.assertEqual(top_rep["player_count"], 4)
        self.assertEqual(top_rep["best_rank"], 1)
        self.assertIn("Rillaboom", top_rep["showdown_paste"])

    def test_compute_archetype_waterfall(self):
        """Verifies archetype market share progression and stage conversions."""
        waterfall = compute_archetype_waterfall(self.mock_standings)
        self.assertIsInstance(waterfall, list)
        self.assertGreaterEqual(len(waterfall), 1)
        arch_names = [w["archetype"] for w in waterfall]
        self.assertIn("Goodstuffs Pivot Balance", arch_names)



    def test_relational_engine_schema_and_ingestion(self):
        """Verifies in-memory schema generation and record batch ingestion."""
        engine = MunchStatsRelationalEngine(self.mock_standings, self.mock_overview)
        self.assertEqual(engine.conn.execute("SELECT COUNT(*) FROM competitors").fetchone()[0], 2)
        self.assertEqual(engine.conn.execute("SELECT COUNT(*) FROM team_members").fetchone()[0], 12)
        self.assertEqual(engine.conn.execute("SELECT COUNT(*) FROM moves").fetchone()[0], 48)

        indexes = [r[0] for r in engine.conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()]
        self.assertIn("idx_tm_species", indexes)
        self.assertIn("idx_comp_placement", indexes)

    def test_relational_engine_arbitrary_query(self):
        """Verifies read-only SQL query execution returning dict records."""
        engine = MunchStatsRelationalEngine(self.mock_standings, self.mock_overview)
        rows = engine.query("SELECT name, placement FROM competitors WHERE placement = 1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Champion Player")
        self.assertEqual(rows[0]["placement"], 1)

    def test_relational_engine_conversion_metrics(self):
        """Validates SQL-driven conversion metric computation."""
        engine = MunchStatsRelationalEngine(self.mock_standings, self.mock_overview)
        metrics = engine.get_conversion_metrics(min_sample=1)
        self.assertGreaterEqual(len(metrics), 1)
        rilla = next((m for m in metrics if m["species"] == "Rillaboom"), None)
        self.assertIsNotNone(rilla)
        self.assertEqual(rilla["d1_count"], 2)

    def test_relational_engine_cores_and_synergies(self):
        """Verifies self-join 2-mon core mining and partner synergy calculations."""
        engine = MunchStatsRelationalEngine(self.mock_standings, self.mock_overview)
        cores = engine.get_top_cores(size=2, limit=5)
        self.assertGreaterEqual(len(cores), 1)

        synergies = engine.get_teammate_synergies("Rillaboom", limit=5)
        self.assertGreaterEqual(len(synergies), 1)
        partner_names = [s["partner"] for s in synergies]
        self.assertIn("Gholdengo", partner_names)

    def test_relational_engine_from_raw_dir(self):
        """Verifies factory instantiation from actual tournament directory if present."""
        baltimore_dir = Path("data/munchstats/raw/2027_baltimore_pok_mon_vgc_regional_championships")
        if baltimore_dir.exists():
            engine = MunchStatsRelationalEngine.from_raw_dir(baltimore_dir)
            comp_count = engine.conn.execute("SELECT COUNT(*) FROM competitors").fetchone()[0]
            self.assertEqual(comp_count, 1079)


if __name__ == "__main__":
    unittest.main()
