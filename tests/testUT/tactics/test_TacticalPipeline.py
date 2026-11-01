# -*- coding: utf-8 -*-
"""
Unit tests for TacticalPipeline (engine/tactics/tactical_pipeline.py).
Verifies isolated pipeline execution, taxonomy classification, and serialization.
"""

from pathlib import Path
import unittest

try:
    import scipy
    import torch
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

from engine.db import UnifiedCoachDatabase
from engine.tactics.tactical_pipeline import TacticalPipeline, audit_showdown_log


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


@unittest.skipUnless(HAS_DEPS, "scipy and torch are required for TestTacticalPipeline")
class TestTacticalPipeline(unittest.TestCase):
    """Unit test suite for TacticalPipeline."""

    def setUp(self) -> None:
        """Initialize in-memory database and TacticalPipeline."""
        self.db = UnifiedCoachDatabase()
        self.pipeline = TacticalPipeline(db=self.db)
        self.raw_log = SAMPLE_LOG_PATH.read_text(encoding="utf-8")

    def tearDown(self) -> None:
        """Close in-memory SQLite connection."""
        self.db.close()

    def test_run_audit_in_memory_without_disk_persistence(self) -> None:
        """Verify run_audit executes all stages and returns valid TacticalAuditResult."""
        res = self.pipeline.run_audit(self.raw_log, auto_persist=False)
        self.assertEqual(res.turning_point_turn, 3)
        self.assertEqual(len(res.payoff_matrix), 5)
        self.assertEqual(len(res.payoff_matrix[0]), 5)
        self.assertAlmostEqual(sum(res.p1_nash_probs), 1.0, places=3)
        self.assertAlmostEqual(sum(res.p2_nash_probs), 1.0, places=3)
        self.assertIn(
            res.mistake_code,
            {"POS-01", "POS-02", "POS-03", "TGT-01", "TGT-02", "TGT-03", "MEC-01", "MEC-02", "SPD-01", "SPD-02"},
        )
        self.assertIn(
            res.cognitive_driver,
            {"Tunnel_Vision", "Greed", "Autopilot", "Tilt", "Format_Divergence"},
        )

    def test_audit_showdown_log_to_dict_schema(self) -> None:
        """Verify TacticalAuditResult.to_dict() produces complete JSONL dictionary."""
        res = audit_showdown_log(self.raw_log, auto_persist=False, db=self.db)
        payload = res.to_dict()
        self.assertEqual(payload["turn"], 3)
        self.assertEqual(payload["p1_name"], "aws_secret")
        self.assertEqual(payload["p2_name"], "DarKgoD16")


if __name__ == "__main__":
    unittest.main()
