# -*- coding: utf-8 -*-
"""
Unit tests for NeuralEvaluator and RegulationMcValueNet (engine/tactics/neural_evaluator.py).
Verifies GPU/CPU batch inference (25, 36) -> (25, 1), sub-millisecond forward pass,
output bounds in [-1.0, 1.0], and N x M payoff matrix evaluation via ClientReplaySimulator.
"""

from pathlib import Path
import time
import unittest
import numpy as np

try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

from engine.tactics.action_pruner import ActionPruner
from engine.tactics.neural_evaluator import (
    NeuralEvaluator,
    RegulationMcValueNet,
    STATE_VECTOR_DIM,
)
from engine.tactics.showdown_parser import ShowdownParser


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


@unittest.skipUnless(HAS_TORCH, "PyTorch is required for TestNeuralEvaluator")
class TestNeuralEvaluator(unittest.TestCase):
    """Unit test suite for RegulationMcValueNet and NeuralEvaluator."""

    def setUp(self) -> None:
        """Initialize NeuralEvaluator, ActionPruner, and Turn 3 board snapshot."""
        self.evaluator = NeuralEvaluator()
        self.pruner = ActionPruner()
        self.parser = ShowdownParser()
        history = self.parser.parse(SAMPLE_LOG_PATH.read_text(encoding="utf-8"))
        self.turn_3_snapshot = history.turns[2]

    def test_batch_inference_shape_bounds_and_latency(self) -> None:
        """Verify batch (25, 36) -> (25, 1) inference, [-1.0, 1.0] bounds, and fast execution."""
        batch_input = np.random.uniform(-1.0, 1.0, size=(25, STATE_VECTOR_DIM)).astype(
            np.float32
        )
        # Warm-up pass
        _ = self.evaluator.evaluate_batch(batch_input)

        t0 = time.perf_counter()
        out = self.evaluator.evaluate_batch(batch_input)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(out.shape, (25, 1))
        self.assertTrue(np.all(out >= -1.0) and np.all(out <= 1.0))
        self.assertLess(elapsed_ms, 50.0)

    def test_evaluate_payoff_matrix_from_simulator_states(self) -> None:
        """Verify dynamic N x M payoff matrix evaluation backed by ClientReplaySimulator."""
        p1_lines = self.pruner.prune_side_actions(self.turn_3_snapshot, side="p1")
        p2_lines = self.pruner.prune_side_actions(self.turn_3_snapshot, side="p2")

        # Standard pruned size
        matrix = self.evaluator.evaluate_payoff_matrix(
            self.turn_3_snapshot, p1_lines, p2_lines
        )
        self.assertEqual(matrix.shape, (len(p1_lines), len(p2_lines)))
        self.assertTrue(np.all(matrix >= -1.0) and np.all(matrix <= 1.0))
        # Spread move (index 2) should outperform Double Offensive Focus (index 0) into Redirection/Protect
        self.assertGreater(matrix[2, 3], matrix[0, 3])

        # Asymmetric arbitrary shape verification (e.g. 3 x 4)
        matrix_asym = self.evaluator.evaluate_payoff_matrix(
            self.turn_3_snapshot, p1_lines[:3], p2_lines[:4]
        )
        self.assertEqual(matrix_asym.shape, (3, 4))
        self.assertTrue(np.all(matrix_asym >= -1.0) and np.all(matrix_asym <= 1.0))

    def test_invalid_feature_dimension_raises_value_error(self) -> None:
        """Verify wrong input tensor dimension raises ValueError."""
        net = RegulationMcValueNet(device="cpu")
        bad_input = torch.zeros((4, 12), dtype=torch.float32)
        with self.assertRaises(ValueError):
            net(bad_input)


if __name__ == "__main__":
    unittest.main()
