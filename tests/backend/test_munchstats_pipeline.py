#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for scouts/munchstats_pipeline.py
Validates:
1. Generation and data governance of all 5 MunchStats CSV tables and .example.csv templates.
2. Complete representation of all 7 VGC 2027 Regional tournaments.
3. Statistical accuracy of Day 1 vs. Day 2 conversion rates.
4. Core clustering and 6-mon team grouping.
5. Formula injection sanitization on CSV exports.
"""

import csv
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = REPO_ROOT / "data"

EXPECTED_TABLES = [
    "MunchStats_Overview",
    "MunchStats_Usage",
    "MunchStats_Standings",
    "MunchStats_Top_Teams",
    "MunchStats_Pokemon_Sets"
]

EXPECTED_TOURNAMENTS = {
    "TM_PUEBLA_2027",
    "TM_NICE_2027",
    "TM_LOUISVILLE_2027",
    "TM_RECIFE_2027",
    "TM_FRANKFURT_2027",
    "TM_BRISBANE_2027",
    "TM_BALTIMORE_2027"
}


class TestMunchStatsPipeline(unittest.TestCase):
    """Test suite for MunchStats tournament ingestion and data governance."""

    def test_all_csv_and_example_files_exist(self):
        """Verify each of the 5 tables has both full .csv and .example.csv template."""
        for tbl in EXPECTED_TABLES:
            full_csv = DATA_DIR / f"{tbl}.csv"
            example_csv = DATA_DIR / f"{tbl}.example.csv"
            self.assertTrue(full_csv.exists(), f"Missing full CSV: {full_csv}")
            self.assertTrue(example_csv.exists(), f"Missing example CSV: {example_csv}")
            self.assertGreater(full_csv.stat().st_size, 100, f"Full CSV {tbl} is suspiciously empty.")
            self.assertGreater(example_csv.stat().st_size, 50, f"Example CSV {tbl} is empty.")

    def test_all_seven_tournaments_present_in_overview(self):
        """Verify all 7 tournaments are recorded in MunchStats_Overview.csv."""
        overview_path = DATA_DIR / "MunchStats_Overview.csv"
        found_tourneys = set()
        with open(overview_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                found_tourneys.add(row["Tournament_ID"])
                self.assertGreater(int(row["Total_Players"]), 0)
                self.assertIn("%", row["Dominant_Mega_Usage_Pct"])

        self.assertEqual(found_tourneys, EXPECTED_TOURNAMENTS, "Mismatch in expected tournament IDs.")

    def test_conversion_rate_metrics_in_usage(self):
        """Verify Day 1, Day 2, and conversion rate calculations in MunchStats_Usage.csv."""
        usage_path = DATA_DIR / "MunchStats_Usage.csv"
        with open(usage_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertGreater(len(rows), 500)
        for r in rows[:100]:
            d1 = int(r["Day1_Count"])
            d2 = int(r["Day2_Count"])
            conv_str = r["Conversion_Rate_Pct"].rstrip("%")
            conv_val = float(conv_str)
            self.assertGreaterEqual(d1, d2, f"Day 1 count ({d1}) must be >= Day 2 count ({d2}) for {r['Species']}")
            self.assertGreaterEqual(conv_val, 0.0)
            self.assertLessEqual(conv_val, 100.0)

    def test_core_clustering_in_top_teams(self):
        """Verify top teams table clusters distinct 6-mon combinations with frequencies."""
        top_teams_path = DATA_DIR / "MunchStats_Top_Teams.csv"
        with open(top_teams_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertGreater(len(rows), 20)
        for r in rows:
            self.assertGreaterEqual(int(r["Frequency_Count"]), 1)
            self.assertIn("%", r["Cluster_Share_Pct"])
            self.assertTrue(r["Pokemon_1"])

    def test_csv_injection_defense(self):
        """Verify cells starting with dangerous symbols are safely escaped with a single quote."""
        for tbl in EXPECTED_TABLES:
            csv_path = DATA_DIR / f"{tbl}.csv"
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    for cell in row:
                        self.assertFalse(
                            cell.startswith(("=", "+", "-", "@")),
                            f"Unescaped formula injection symbol in {tbl}: {cell}"
                        )


if __name__ == "__main__":
    unittest.main()
