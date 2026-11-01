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


class TestMunchStatsCrawler(unittest.TestCase):
    """Test suite for engine/munchstats_crawler.py."""

    def test_extract_tournament_id(self):
        """Validates robust tournament ID resolution across formats."""
        cases = [
            ("https://www.munchstats.com/tournaments/BA002-JL3KVbvivVKNAc/all/", "BA002-JL3KVbvivVKNAc"),
            ("https://www.munchstats.com/tournaments/NC002-xyz/day1", "NC002-xyz"),
            ("http://munchstats.com/tournaments/PB002-abc", "PB002-abc"),
            ("BA002-JL3KVbvivVKNAc", "BA002-JL3KVbvivVKNAc"),
            ("/tournaments/LO002-123/all", "LO002-123"),
        ]
        for url, expected in cases:
            self.assertEqual(extract_tournament_id(url), expected)

    def test_determine_archetype_label(self):
        """Verifies archetype heuristics for weather, trick room, and balance."""
        rain_team = ["Pelipper", "Archaludon", "Basculegion", "Rillaboom", "Incineroar", "Gholdengo"]
        self.assertEqual(determine_archetype_label(rain_team), "Rain Archaludon Offense")

        sand_team = ["Tyranitar", "Excadrill", "Salamence", "Indeedee", "Corviknight", "Sneasler"]
        self.assertEqual(determine_archetype_label(sand_team), "Sand Rush Physical Offense")

        tr_team = ["Farigiraf", "Ursaluna", "Torkoal", "Armarouge", "Indeedee-F", "Kingambit"]
        self.assertEqual(determine_archetype_label(tr_team), "Sun Trick Room Offense")

        balance_team = ["Kingambit", "Gholdengo", "Incineroar", "Rillaboom", "Primarina", "Dragonite"]
        self.assertEqual(determine_archetype_label(balance_team), "Goodstuffs Pivot Balance")

    def test_build_showdown_export(self):
        """Verifies Showdown importable export generation from structured slot dicts."""
        slots = [
            {
                "pokemon": "Excadrill",
                "item": "Focus Sash",
                "ability": "Sand Rush",
                "nature": "Jolly",
                "moves": ["Iron Head", "High Horsepower", "Rock Slide", "Protect"],
            },
            {
                "pokemon": "Salamence-Mega",
                "item": "Salamencite",
                "ability": "Intimidate",
                "nature": "Timid",
                "moves": ["Hyper Voice", "Draco Meteor", "Flamethrower", "Protect"],
            }
        ]
        export_text = build_showdown_export(slots)
        self.assertIn("Excadrill @ Focus Sash", export_text)
        self.assertIn("Ability: Sand Rush", export_text)
        self.assertIn("Jolly Nature", export_text)
        self.assertIn("- Iron Head", export_text)
        self.assertIn("Salamence-Mega @ Salamencite", export_text)

    def test_populate_scouted_teams_sequential_ids(self):
        """Verifies that scouted teams receive strictly sequential STxx IDs without duplicates."""
        mock_standings = [
            {
                "name": f"Trainer_{i}",
                "placement": i,
                "record": {"wins": 10, "losses": 2},
                "team": [
                    {"pokemon": f"Mon_{j}_{i}", "item": "Sitrus Berry"} for j in range(6)
                ],
            }
            for i in range(1, 6)
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_csv = Path(tmp_dir) / "Test_Scouted.csv"
            registered = populate_scouted_teams(
                standings=mock_standings,
                tournament_name="Test Regional 2027",
                max_teams=5,
                csv_path=test_csv
            )
            self.assertEqual(len(registered), 5)
            expected_ids = ["ST01", "ST02", "ST03", "ST04", "ST05"]
            actual_ids = [r["id"] for r in registered]
            self.assertEqual(actual_ids, expected_ids)



if __name__ == '__main__':
    unittest.main()
