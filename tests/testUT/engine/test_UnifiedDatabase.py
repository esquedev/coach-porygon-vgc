# -*- coding: utf-8 -*-
"""
Unit tests for UnifiedCoachDatabase (engine/db.py).
Verifies in-memory SQLite schema creation, batch JSONL ingestion, atomic JSONL
persistence, SQL query aggregations, and error boundary handling.
"""

import json
from pathlib import Path
import tempfile
import unittest

from engine.db import UnifiedCoachDatabase


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_JSONL = REPO_ROOT / "tests" / "data" / "tactical_audits.jsonl"


class TestUnifiedDatabase(unittest.TestCase):
    """Unit test suite for UnifiedCoachDatabase."""

    def setUp(self) -> None:
        """Create a fresh in-memory database instance before each test."""
        self.db = UnifiedCoachDatabase()

    def tearDown(self) -> None:
        """Close the in-memory SQLite connection after each test."""
        self.db.close()

    def test_schema_initialization_and_empty_tables(self) -> None:
        """Verify all four canonical tables exist and are initially empty."""
        for table in ("matches", "tactical_audits", "diagnostics", "munchstats_meta"):
            rows = self.db.query(f"SELECT COUNT(*) AS cnt FROM {table}")
            self.assertEqual(rows[0]["cnt"], 0)

    def test_ingest_jsonl_fixture_and_relational_join(self) -> None:
        """Verify batch ingestion of tactical_audits.jsonl and relational JOIN queries."""
        count = self.db.ingest_jsonl(FIXTURE_JSONL)
        self.assertEqual(count, 2)

        audits = self.db.query(
            """
            SELECT a.audit_id, a.match_id, a.turn, a.equity_loss, a.mistake_code,
                   m.p1_name, m.p2_name, m.winner
            FROM tactical_audits a
            JOIN matches m ON a.match_id = m.match_id
            WHERE a.equity_loss > ?
            ORDER BY a.turn ASC
            """,
            (0.20,),
        )
        self.assertEqual(len(audits), 2)
        self.assertEqual(audits[0]["match_id"], "MC-001")
        self.assertEqual(audits[0]["mistake_code"], "POS-02")
        self.assertEqual(audits[1]["mistake_code"], "TGT-01")

    def test_append_audit_record_atomic_persistence(self) -> None:
        """Verify append_audit_record writes a single JSON line to disk and indexes in RAM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_jsonl = Path(tmpdir) / "custom_audits.jsonl"
            sample_record = {
                "match_id": "MC-999",
                "p1_name": "aws_secret",
                "p2_name": "TestOpponent",
                "winner": "aws_secret",
                "total_turns": 6,
                "turn": 3,
                "impact_score": 85.0,
                "p1_active": ["Charizard", "Kingambit"],
                "p2_active": ["Sinistcha", "Floette-Eternal"],
                "observed_action": "Heat Wave + Iron Head",
                "optimal_nash_action": "Spread / Area Move",
                "game_value": 0.55,
                "equity_loss": 0.12,
                "mistake_code": "TGT-01",
                "cognitive_driver": "Tunnel_Vision",
                "payoff_matrix": [[0.5, 0.2], [0.1, 0.4]],
                "p1_nash_probs": [0.7, 0.3],
                "p2_nash_probs": [0.4, 0.6],
            }

            audit_id = self.db.append_audit_record(sample_record, target_path=temp_jsonl)
            self.assertEqual(audit_id, "AUD-MC-999-T3")
            self.assertTrue(temp_jsonl.exists())

            lines = temp_jsonl.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            loaded = json.loads(lines[0])
            self.assertEqual(loaded["audit_id"], "AUD-MC-999-T3")

            rows = self.db.query(
                "SELECT * FROM tactical_audits WHERE audit_id = ?", (audit_id,)
            )
            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0]["equity_loss"], 0.12)

    def test_munchstats_meta_upsert_and_validation(self) -> None:
        """Verify metagame prior insertion and validation bounds."""
        self.db.upsert_munchstats_meta(
            species="Charizard-Mega-Y",
            usage_rate=0.42,
            top_item="Charizardite Y",
            top_ability="Drought",
            sample_size=250,
        )
        rows = self.db.query(
            "SELECT * FROM munchstats_meta WHERE species = ?", ("Charizard-Mega-Y",)
        )
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["usage_rate"], 0.42)

        with self.assertRaises(ValueError):
            self.db.upsert_munchstats_meta("Charizard", usage_rate=1.5)

    def test_error_handling_on_invalid_queries_and_files(self) -> None:
        """Verify appropriate ValueError and FileNotFoundError exceptions."""
        with self.assertRaises(FileNotFoundError):
            self.db.ingest_jsonl(REPO_ROOT / "tests" / "data" / "nonexistent_file.jsonl")

        with self.assertRaises(ValueError):
            self.db.query("DROP TABLE matches")

        with self.assertRaises(ValueError):
            self.db.append_audit_record({})


if __name__ == "__main__":
    unittest.main()
