#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Acceptance Tests for Telemetry CLI Pipeline
"""

from pathlib import Path
import subprocess
import sys
import unittest
import pyhocon
from pyhocon import ConfigFactory

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())


class TestTelemetryPipeline(unittest.TestCase):
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
