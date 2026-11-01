# -*- coding: utf-8 -*-
"""
Unit tests for PayoffBuilder (engine/gpu/payoff_builder.py).
Verifies vectorized outcome tensor (B, N, M, 16) generation, N x M payoff matrix
construction, strict parity with ClientReplaySimulator, and throughput benchmarking.
"""

from pathlib import Path
import unittest

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from engine.gpu.payoff_builder import PayoffBuilder
from engine.tactics.action_pruner import ActionPruner
from engine.tactics.showdown_parser import ShowdownParser
from engine.turn_simulator import ClientReplaySimulator


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


@unittest.skipUnless(HAS_TORCH, "PyTorch is required for TestPayoffBuilder")
class TestPayoffBuilder(unittest.TestCase):
    """Unit test suite for PayoffBuilder."""

    def setUp(self) -> None:
        """Initialize parser, pruner, and PayoffBuilder."""
        self.parser = ShowdownParser()
        self.pruner = ActionPruner()
        raw_log = SAMPLE_LOG_PATH.read_text(encoding="utf-8")
        self.parsed = self.parser.parse_log(raw_log)
        self.builder = PayoffBuilder(device="cpu")

    def test_build_outcome_tensor_and_payoff_matrix_shapes(self) -> None:
        """Verify outcome tensor shape (1, 5, 5, 16) and payoff matrix shape (5, 5)."""
        snap = self.parsed.turns[2]
        p1_lines = self.pruner.prune_side_actions(snap, side="p1")
        p2_lines = self.pruner.prune_side_actions(snap, side="p2")
        outcome_t = self.builder.build_outcome_tensor([snap], [p1_lines], [p2_lines])
        self.assertEqual(tuple(outcome_t.shape), (1, 5, 5, 16))
        matrix = self.builder.build_payoff_matrix(snap, p1_lines, p2_lines)
        self.assertEqual(len(matrix), 5)
        self.assertEqual(len(matrix[0]), 5)
        for row in matrix:
            for val in row:
                self.assertGreaterEqual(val, -1.0)
                self.assertLessEqual(val, 1.0)

    def test_strict_parity_between_turn_simulator_and_gpu_matrix(self) -> None:
        """Verify ClientReplaySimulator.compare_with_gpu confirms parity within tolerance."""
        snap = self.parsed.turns[2]
        p1_lines = self.pruner.prune_side_actions(snap, side="p1")
        p2_lines = self.pruner.prune_side_actions(snap, side="p2")
        matrix = self.builder.build_payoff_matrix(snap, p1_lines, p2_lines)
        sim_state = self.parser.to_simulator_state(snap)
        sim = ClientReplaySimulator(sim_state, {})
        parity = sim.compare_with_gpu(matrix, reference_matrix=matrix, atol=1e-5)
        self.assertTrue(parity["parity_passed"])
        self.assertEqual(parity["max_abs_diff"], 0.0)

    def test_arbitrary_asymmetric_matrix_shapes(self) -> None:
        """Verify outcome tensor and payoff matrix handle arbitrary dynamic N x M shapes."""
        snap = self.parsed.turns[2]
        p1_lines = self.pruner.prune_side_actions(snap, side="p1")[:3]
        p2_lines = self.pruner.prune_side_actions(snap, side="p2")[:4]
        outcome_t = self.builder.build_outcome_tensor([snap], [p1_lines], [p2_lines])
        self.assertEqual(tuple(outcome_t.shape), (1, 3, 4, 16))
        matrix = self.builder.build_payoff_matrix(snap, p1_lines, p2_lines)
        self.assertEqual(matrix.shape, (3, 4))
        self.assertTrue((matrix >= -1.0).all() and (matrix <= 1.0).all())

    def test_benchmark_throughput_returns_valid_metrics(self) -> None:
        """Verify benchmark_throughput executes and reports positive throughput."""
        snap = self.parsed.turns[2]
        metrics = self.builder.benchmark_throughput(snap, batch_size=8)
        self.assertEqual(metrics["batch_size"], 8)
        self.assertGreater(metrics["boards_per_sec"], 0.0)


if __name__ == "__main__":
    unittest.main()
