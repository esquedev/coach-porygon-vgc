# -*- coding: utf-8 -*-
"""
Unit tests for NashSolver (engine/tactics/nash_solver.py).
Validates von Neumann's Minimax Theorem on pure and mixed zero-sum games,
translation invariance under constant shifts, and Delta Equity loss calculation.
"""

import unittest
import numpy as np

try:
    import scipy
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from engine.tactics.nash_solver import (
    NashSolver,
    compute_equity_loss,
    solve_simultaneous_nash,
)


@unittest.skipUnless(HAS_SCIPY, "scipy is required for TestNashSolver")
class TestNashSolver(unittest.TestCase):
    """Unit test suite for NashSolver."""

    def setUp(self) -> None:
        """Initialize NashSolver instance."""
        self.solver = NashSolver()

    def test_matching_pennies_mixed_equilibrium(self) -> None:
        """Verify 2x2 Matching Pennies yields [0.5, 0.5] mixed equilibrium and v* = 0.0."""
        payoff = np.array([[1.0, -1.0], [-1.0, 1.0]])
        sol = solve_simultaneous_nash(payoff)

        np.testing.assert_allclose(sol.p1_probs, [0.5, 0.5], atol=1e-4)
        np.testing.assert_allclose(sol.p2_probs, [0.5, 0.5], atol=1e-4)
        self.assertAlmostEqual(sol.game_value, 0.0, places=4)

    def test_rock_paper_scissors_uniform_nash(self) -> None:
        """Verify 3x3 Rock-Paper-Scissors yields [1/3, 1/3, 1/3] and v* = 0.0."""
        rps = np.array(
            [
                [0.0, -1.0, 1.0],
                [1.0, 0.0, -1.0],
                [-1.0, 1.0, 0.0],
            ]
        )
        sol = self.solver.solve(rps)
        np.testing.assert_allclose(sol.p1_probs, [1 / 3, 1 / 3, 1 / 3], atol=1e-4)
        np.testing.assert_allclose(sol.p2_probs, [1 / 3, 1 / 3, 1 / 3], atol=1e-4)
        self.assertAlmostEqual(sol.game_value, 0.0, places=4)

    def test_translation_invariance_and_pure_saddle_point(self) -> None:
        """Verify constant shift A + k shifts game_value by k while preserving probabilities."""
        base_matrix = np.array(
            [
                [0.4, 0.2, 0.5],
                [0.1, -0.3, 0.0],
                [-0.2, -0.5, -0.1],
            ]
        )
        sol_base = solve_simultaneous_nash(base_matrix)
        sol_shifted = solve_simultaneous_nash(base_matrix + 5.0)

        np.testing.assert_allclose(sol_base.p1_probs, sol_shifted.p1_probs, atol=1e-4)
        np.testing.assert_allclose(sol_base.p2_probs, sol_shifted.p2_probs, atol=1e-4)
        self.assertAlmostEqual(sol_shifted.game_value - sol_base.game_value, 5.0, places=4)

    def test_compute_equity_loss_for_suboptimal_action(self) -> None:
        """Verify compute_equity_loss returns 0.0 for optimal play and > 0 for dominated play."""
        matrix = np.array(
            [
                [0.50, 0.50],
                [-0.20, -0.20],
            ]
        )
        sol = solve_simultaneous_nash(matrix)
        loss_optimal = compute_equity_loss(matrix, 0, sol.p2_probs, sol.game_value)
        loss_suboptimal = compute_equity_loss(matrix, 1, sol.p2_probs, sol.game_value)

        self.assertAlmostEqual(loss_optimal, 0.0, places=4)
        self.assertAlmostEqual(loss_suboptimal, 0.70, places=4)

    def test_invalid_inputs_raise_errors(self) -> None:
        """Verify invalid matrix shapes and out-of-range action indices raise exceptions."""
        with self.assertRaises(ValueError):
            solve_simultaneous_nash(np.array([1.0, 2.0]))

        matrix = np.eye(2)
        with self.assertRaises(IndexError):
            compute_equity_loss(matrix, 5, np.array([0.5, 0.5]), 0.5)


if __name__ == "__main__":
    unittest.main()
