#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit & Acceptance Tests for Telemetry Logging (engine/telemetry.py)
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from engine.repositories import CsvDiagnosticsRepository, CsvMatchRepository
from engine.telemetry import (
    log_damage_calcs_to_csv,
    log_personal_match_to_csv,
    log_scouted_match_to_csv,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestTelemetryUnit(unittest.TestCase):
    """Unit tests for telemetry logging with isolated repositories."""

    def setUp(self):
        """Set up test fixtures and temporary files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.raw_path = Path(self.temp_dir.name) / "Raw_Matches.csv"
        self.diag_path = Path(self.temp_dir.name) / "Playstyle_Diagnostics.csv"
        self.match_repo = CsvMatchRepository(self.raw_path)
        self.diag_repo = CsvDiagnosticsRepository(self.diag_path)

    def tearDown(self):
        """Clean up test artifacts and restored states."""
        self.temp_dir.cleanup()

    def test_log_personal_match_clean(self):
        """Test for log personal match clean."""
        payload = {
            "teamId": "T24",
            "opponent": "ash_ketchum",
            "result": "Win",
            "turns": 4,
            "archetype": "Sun Hyper Offense"
        }
        res = log_personal_match_to_csv(payload, match_repo=self.match_repo, diag_repo=self.diag_repo)
        self.assertEqual(res["status"], "LOGGED_PERSONAL_MATCH")
        self.assertEqual(res["Match_ID"], 1)
        self.assertFalse(res["Playstyle_Diagnostics_Logged"])

    def test_log_personal_match_with_tactical_misplay(self):
        """Test for log personal match with tactical misplay."""
        payload = {
            "teamId": "T24",
            "opponent": "cynthia_vgc",
            "result": "Loss",
            "turns": 3,
            "misplayDomain": "Positioning",
            "misplayCode": "POS-01",
            "misplayTurn": "2",
            "deterministicFix": "Pivot with Protect first",
            "trap": "Autopilot",
            "vpLost": 2.0
        }
        res = log_personal_match_to_csv(payload, match_repo=self.match_repo, diag_repo=self.diag_repo)
        self.assertEqual(res["status"], "LOGGED_PERSONAL_MATCH")
        self.assertTrue(res["Playstyle_Diagnostics_Logged"])

        # Check diagnostics repo content
        diags = self.diag_repo.get_all_diagnostics()
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]["Mistake_Code"], "POS-01")
        self.assertEqual(diags[0]["Root_Cognitive_Trap"], "Autopilot")


class TestTelemetryAcceptance(unittest.TestCase):
    """Acceptance test running telemetry CLI end-to-end via subprocess."""

    def test_cli_help(self):
        """Test for cli help."""
        cmd = [sys.executable, str(REPO_ROOT / "engine" / "telemetry.py"), "--help"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("--mode", res.stdout)
        self.assertIn("--payload", res.stdout)


if __name__ == "__main__":
    unittest.main()
