# -*- coding: utf-8 -*-
"""
Unit tests for ActionPruner (engine/tactics/action_pruner.py).
Verifies combinatorial reduction from 81 joint actions to Top-5 canonical VGC
strategies and deterministic execution via ClientReplaySimulator.
"""

from pathlib import Path
import unittest

from engine.tactics.action_pruner import ActionPruner
from engine.tactics.showdown_parser import ShowdownParser


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


class TestActionPruner(unittest.TestCase):
    """Unit test suite for ActionPruner."""

    def setUp(self) -> None:
        """Initialize parser, pruner, and Turn 3 snapshot from fixture."""
        self.parser = ShowdownParser()
        self.pruner = ActionPruner()
        history = self.parser.parse(SAMPLE_LOG_PATH.read_text(encoding="utf-8"))
        self.turn_3_snapshot = history.turns[2]

    def test_prune_side_actions_returns_five_canonical_lines(self) -> None:
        """Verify pruning reduces joint action space to exactly 5 canonical VGC categories."""
        p1_lines = self.pruner.prune_side_actions(self.turn_3_snapshot, side="p1")
        p2_lines = self.pruner.prune_side_actions(self.turn_3_snapshot, side="p2")

        self.assertEqual(len(p1_lines), 5)
        self.assertEqual(len(p2_lines), 5)

        expected_categories = [
            "Double Offensive Focus",
            "Attack + Defensive Protect",
            "Spread / Area Move",
            "Speed Control / Redirection / Status",
            "Strategic Pivot / Switch",
        ]
        self.assertEqual([line.category for line in p1_lines], expected_categories)
        self.assertEqual([line.category for line in p2_lines], expected_categories)

    def test_simulate_joint_outcome_with_turn_simulator(self) -> None:
        """Verify simulate_joint_outcome invokes ClientReplaySimulator deterministically."""
        p1_lines = self.pruner.prune_side_actions(self.turn_3_snapshot, side="p1")
        p2_lines = self.pruner.prune_side_actions(self.turn_3_snapshot, side="p2")

        post_state, replay_text = self.pruner.simulate_joint_outcome(
            self.turn_3_snapshot, p1_lines[2], p2_lines[3]
        )
        self.assertIn("slots", post_state)
        self.assertIn("p1a", post_state["slots"])
        self.assertIn("Turn", replay_text)

    def test_invalid_side_raises_value_error(self) -> None:
        """Verify invalid side identifier raises ValueError."""
        with self.assertRaises(ValueError):
            self.pruner.prune_side_actions(self.turn_3_snapshot, side="p3")


if __name__ == "__main__":
    unittest.main()
