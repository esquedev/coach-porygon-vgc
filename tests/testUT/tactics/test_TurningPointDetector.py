# -*- coding: utf-8 -*-
"""
Unit tests for TurningPointDetector (engine/tactics/turning_point_detector.py).
Verifies heuristic scoring and ensures Turn 3 is isolated on sample_showdown_mc_log.txt.
"""

from pathlib import Path
import unittest

from engine.tactics.showdown_parser import BattleHistory, ShowdownParser
from engine.tactics.turning_point_detector import (
    TurningPointDetector,
    detect_turning_point,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


class TestTurningPointDetector(unittest.TestCase):
    """Unit test suite for TurningPointDetector."""

    def setUp(self) -> None:
        """Initialize parser, detector, and parsed sample battle history."""
        self.parser = ShowdownParser()
        self.detector = TurningPointDetector()
        raw_log = SAMPLE_LOG_PATH.read_text(encoding="utf-8")
        self.history = self.parser.parse(raw_log)

    def test_detect_turning_point_selects_turn_3_on_fixture(self) -> None:
        """Ensure the turning point selected on sample_showdown_mc_log.txt is exactly Turn 3."""
        result = detect_turning_point(self.history)
        self.assertEqual(result.turn_number, 3)
        self.assertGreaterEqual(result.impact_score, 85.0)
        self.assertTrue(len(result.reasons) >= 3)

    def test_all_turns_scored_and_endgame_discounted(self) -> None:
        """Verify every turn in the history receives a deterministic impact score."""
        result = self.detector.detect(self.history)
        self.assertEqual(len(result.turn_scores), len(self.history.turns))
        self.assertGreater(result.turn_scores[3], result.turn_scores[1])
        self.assertGreater(result.turn_scores[3], result.turn_scores[6])

    def test_empty_battle_history_raises_value_error(self) -> None:
        """Verify empty BattleHistory raises ValueError."""
        empty_history = BattleHistory(match_id="EMPTY", p1_name="A", p2_name="B", turns=[])
        with self.assertRaises(ValueError):
            detect_turning_point(empty_history)


if __name__ == "__main__":
    unittest.main()
