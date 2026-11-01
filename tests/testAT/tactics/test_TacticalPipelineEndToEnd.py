# -*- coding: utf-8 -*-
"""
End-to-End Acceptance Test Suite for the Game-Theoretic Tactical Pipeline
(tests/testAT/tactics/test_TacticalPipelineEndToEnd.py).

Verifies full orchestration across sample_showdown_mc_log.txt, atomic .jsonl
persistence, SQLite (:memory:) relational indexing, and main.py CLI execution.
"""

import json
from pathlib import Path
import tempfile
import unittest

try:
    import scipy
    import torch
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

from engine.db import UnifiedCoachDatabase
from engine.tactics.tactical_pipeline import audit_showdown_log
import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


@unittest.skipUnless(HAS_DEPS, "scipy and torch are required for TestTacticalPipelineEndToEnd")
class TestTacticalPipelineEndToEnd(unittest.TestCase):
    """End-to-end acceptance test suite for the Game-Theoretic VGC AGI pipeline."""

    def test_end_to_end_pipeline_jsonl_and_sqlite_indexing(self) -> None:
        """Execute full pipeline over sample_showdown_mc_log.txt and verify SQL + JSONL."""
        raw_log = SAMPLE_LOG_PATH.read_text(encoding="utf-8")
        db = UnifiedCoachDatabase()

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_jsonl = Path(tmpdir) / "tactical_audits.jsonl"
            result = audit_showdown_log(
                raw_log,
                auto_persist=True,
                db=db,
                jsonl_path=temp_jsonl,
            )

            self.assertEqual(result.turning_point_turn, 3)
            self.assertTrue(temp_jsonl.exists())

            lines = temp_jsonl.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            persisted = json.loads(lines[0])
            self.assertEqual(persisted["audit_id"], result.audit_id)

            # Query via UnifiedCoachDatabase SQL join
            sql_rows = db.query(
                """
                SELECT a.audit_id, a.turn, a.mistake_code, d.cognitive_driver, m.winner
                FROM tactical_audits a
                JOIN diagnostics d ON a.match_id = d.match_id AND a.turn = d.turn
                JOIN matches m ON a.match_id = m.match_id
                WHERE a.audit_id = ?
                """,
                (result.audit_id,),
            )
            self.assertEqual(len(sql_rows), 1)
            self.assertEqual(sql_rows[0]["turn"], 3)
            self.assertEqual(sql_rows[0]["winner"], "aws_secret")

        db.close()

    def test_cli_main_demo_mode_execution(self) -> None:
        """Verify main.py --demo --no-persist runs cleanly and returns exit code 0."""
        exit_code = cli_main.main(["--demo", "--no-persist"])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
