#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for SOLID Repository Layer (engine/repositories.py)
"""

from pathlib import Path
import tempfile
import unittest

from engine.repositories import (
    CsvMatchRepository,
    CsvTeamRepository,
    InMemoryMatchRepository,
    sanitize_csv_cell,
)


class TestRepositorySanitization(unittest.TestCase):
    """Tests formula injection (CWE-1236) prevention in sanitize_csv_cell."""

    def test_dangerous_prefixes_are_quoted(self):
        """Test for dangerous prefixes are quoted."""
        self.assertEqual(sanitize_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(sanitize_csv_cell("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(sanitize_csv_cell("-calc.exe"), "'-calc.exe")
        self.assertEqual(sanitize_csv_cell("+cmd.exe"), "'+cmd.exe")
        self.assertEqual(sanitize_csv_cell("\tmalicious"), "'\tmalicious")

    def test_legitimate_numeric_values_are_preserved(self):
        """Test for legitimate numeric values are preserved."""
        self.assertEqual(sanitize_csv_cell(-18.0), -18.0)
        self.assertEqual(sanitize_csv_cell("+2 SpA"), "+2 SpA")
        self.assertEqual(sanitize_csv_cell("-1 boost"), "-1 boost")
        self.assertEqual(sanitize_csv_cell("-14.5"), "-14.5")
        self.assertEqual(sanitize_csv_cell("Garchomp"), "Garchomp")
        self.assertEqual(sanitize_csv_cell(""), "")
        self.assertEqual(sanitize_csv_cell(None), "")


class TestInMemoryMatchRepository(unittest.TestCase):
    """Tests Liskov substitution with InMemoryMatchRepository."""

    def setUp(self):
        """Set up test fixtures and temporary files."""
        self.repo = InMemoryMatchRepository()

    def test_log_and_retrieve_matches(self):
        """Test for log and retrieve matches."""
        self.assertEqual(self.repo.get_next_id(), 1.0)
        rec1 = self.repo.log_match({"Result": "Win", "Turns": 4})
        self.assertEqual(rec1["Match_ID"], 1.0)
        self.assertEqual(self.repo.get_next_id(), 2.0)

        rec2 = self.repo.log_match({"Result": "Loss", "Turns": 6})
        self.assertEqual(rec2["Match_ID"], 2.0)

        all_matches = self.repo.get_all_matches()
        self.assertEqual(len(all_matches), 2)
        self.assertEqual(all_matches[0]["Result"], "Win")


class TestCsvMatchRepository(unittest.TestCase):
    """Tests file persistence in CsvMatchRepository using temporary files."""

    def setUp(self):
        """Set up test fixtures and temporary files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temp_dir.name) / "test_raw_matches.csv"
        self.repo = CsvMatchRepository(self.csv_path)

    def tearDown(self):
        """Clean up test artifacts and restored states."""
        self.temp_dir.cleanup()

    def test_creates_file_with_headers_and_logs(self):
        """Test for creates file with headers and logs."""
        self.assertEqual(self.repo.get_next_id(), 1.0)
        self.repo.log_match({
            "Team_ID": "T24",
            "Opponent": "tester_vgc",
            "Result": "Win",
            "Turns": 5
        })

        self.assertTrue(self.csv_path.exists())
        self.assertEqual(self.repo.get_next_id(), 2.0)

        records = self.repo.get_all_matches()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Team_ID"], "T24")
        self.assertEqual(records[0]["Result"], "Win")


class TestCsvTeamRepository(unittest.TestCase):
    """Tests registration and sequential ID derivation in CsvTeamRepository."""

    def setUp(self):
        """Set up test fixtures and temporary files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temp_dir.name) / "test_teams.csv"
        self.repo = CsvTeamRepository(self.csv_path)

    def tearDown(self):
        """Clean up test artifacts and restored states."""
        self.temp_dir.cleanup()

    def test_sequential_team_id_generation(self):
        """Test for sequential team id generation."""
        self.assertEqual(self.repo.get_next_team_id(), "T01")
        self.repo.register_team({
            "Team_ID": "T01",
            "Team_Name": "Sun Offense",
            "Date_Registered": "2026-10-30",
            "Status": "Active"
        })
        self.assertEqual(self.repo.get_next_team_id(), "T02")


if __name__ == "__main__":
    unittest.main()
