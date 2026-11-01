# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Simultaneous Game-Theoretic Nash Solver (engine/tactics/nash_solver.py)

Solves two-player zero-sum simultaneous VGC turn matrices via Primal-Dual Linear
Programming using the HiGHS simplex/interior-point solver (scipy.optimize.linprog).
Guarantees unexploitable Mixed Strategy Nash Equilibria (von Neumann Minimax Theorem)
and quantifies Player 1 Equity Loss (Delta Equity).
"""

from dataclasses import dataclass
import numpy as np

try:
    from scipy.optimize import linprog
    HAS_SCIPY = True
except ImportError:
    linprog = None
    HAS_SCIPY = False


@dataclass
class NashSolution:
    """Represents the solved mixed-strategy Nash equilibrium of a simultaneous turn."""

    p1_probs: np.ndarray
    p2_probs: np.ndarray
    game_value: float
    dominant_p1_idx: int
    dominant_p2_idx: int


class NashSolver:
    """
    Primal-Dual Linear Programming solver for simultaneous zero-sum matrix games.
    """

    def solve(self, payoff_matrix: np.ndarray) -> NashSolution:
        """
        Compute the exact Mixed Strategy Nash Equilibrium for a 2D payoff matrix.

        Args:
            payoff_matrix: 2D numpy array of shape (M, N) representing P1 payoffs.

        Returns:
            NashSolution containing normalized strategy vectors (p1_probs, p2_probs)
            and the von Neumann game value v*.

        Raises:
            ValueError: If payoff_matrix is not a non-empty 2D numeric array.
        """
        if not HAS_SCIPY or linprog is None:
            raise ImportError("scipy is required for NashSolver. Please install scipy>=1.10.0.")

        mat = np.asarray(payoff_matrix, dtype=np.float64)
        if mat.ndim != 2 or mat.shape[0] == 0 or mat.shape[1] == 0:
            raise ValueError("payoff_matrix must be a non-empty 2D numpy array.")

        m_rows, n_cols = mat.shape

        # Apply strictly positive shift A' = A + c > 0
        min_val = float(np.min(mat))
        shift_c = abs(min_val) + 2.0 if min_val <= 0.0 else 0.0
        shifted_a = mat + shift_c

        # 1. Primal LP for P1 (Row Player):
        # Minimize sum(x_i) subject to -A'^T x <= -1, x_i >= 0
        c_primal = np.ones(m_rows, dtype=np.float64)
        a_ub_primal = -shifted_a.T
        b_ub_primal = -np.ones(n_cols, dtype=np.float64)
        bounds_primal = [(0.0, None) for _ in range(m_rows)]

        res_p1 = linprog(
            c=c_primal,
            A_ub=a_ub_primal,
            b_ub=b_ub_primal,
            bounds=bounds_primal,
            method="highs",
        )
        if not res_p1.success or np.sum(res_p1.x) <= 0.0:
            p1_probs = np.ones(m_rows, dtype=np.float64) / m_rows
            v_shifted = float(np.mean(shifted_a))
        else:
            sum_x = float(np.sum(res_p1.x))
            v_shifted = 1.0 / sum_x
            p1_probs = np.clip(res_p1.x / sum_x, 0.0, 1.0)
            p1_probs /= float(np.sum(p1_probs))

        # 2. Dual LP for P2 (Column Player):
        # Maximize sum(y_j) <=> Minimize -sum(y_j) subject to A' y <= 1, y_j >= 0
        c_dual = -np.ones(n_cols, dtype=np.float64)
        a_ub_dual = shifted_a
        b_ub_dual = np.ones(m_rows, dtype=np.float64)
        bounds_dual = [(0.0, None) for _ in range(n_cols)]

        res_p2 = linprog(
            c=c_dual,
            A_ub=a_ub_dual,
            b_ub=b_ub_dual,
            bounds=bounds_dual,
            method="highs",
        )
        if not res_p2.success or np.sum(res_p2.x) <= 0.0:
            p2_probs = np.ones(n_cols, dtype=np.float64) / n_cols
        else:
            sum_y = float(np.sum(res_p2.x))
            p2_probs = np.clip(res_p2.x / sum_y, 0.0, 1.0)
            p2_probs /= float(np.sum(p2_probs))

        game_value = round(v_shifted - shift_c, 6)
        dom_p1 = int(np.argmax(p1_probs))
        dom_p2 = int(np.argmax(p2_probs))

        return NashSolution(
            p1_probs=np.round(p1_probs, 6),
            p2_probs=np.round(p2_probs, 6),
            game_value=game_value,
            dominant_p1_idx=dom_p1,
            dominant_p2_idx=dom_p2,
        )


def solve_simultaneous_nash(payoff_matrix: np.ndarray) -> NashSolution:
    """
    Solve the simultaneous zero-sum matrix game using HiGHS Linear Programming.

    Args:
        payoff_matrix: 2D payoff matrix for Player 1.

    Returns:
        NashSolution with mixed strategy distributions and game value v*.
    """
    solver = NashSolver()
    return solver.solve(payoff_matrix)


def compute_equity_loss(
    payoff_matrix: np.ndarray,
    player_action_idx: int,
    opponent_nash_probs: np.ndarray,
    game_value: float,
) -> float:
    """
    Calculate the exploitability Equity Loss (Delta Equity = v* - V_real) of an observed action.

    Args:
        payoff_matrix: 2D numpy array of shape (M, N).
        player_action_idx: Row index of the action actually executed by Player 1.
        opponent_nash_probs: Normalized Nash probability vector for Player 2.
        game_value: Optimal von Neumann game value v*.

    Returns:
        Non-negative float representing positional Win-Equity lost by deviating from Nash.

    Raises:
        IndexError: If player_action_idx is out of range for payoff_matrix.
    """
    mat = np.asarray(payoff_matrix, dtype=np.float64)
    if not (0 <= player_action_idx < mat.shape[0]):
        raise IndexError(
            f"player_action_idx {player_action_idx} out of bounds for matrix with {mat.shape[0]} rows."
        )

    q_vec = np.asarray(opponent_nash_probs, dtype=np.float64)
    real_expected_value = float(np.dot(mat[player_action_idx], q_vec))
    delta_equity = max(0.0, float(game_value) - real_expected_value)
    return round(delta_equity, 6)
