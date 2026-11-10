# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Game-Theoretic Dominant Strategy (IEDS), Nash & QRE Solver
==============================================================================

Operates on the single-turn risk-resilient payoff matrices produced by
`VgcTensorStateMachine` (`mean_utility`, `cvar_10_utility`, `risk_adjusted_utility`,
`win_turn_prob`, `faint_prob`, `survival_prob`) for `trainer_1` vs `trainer_2`.

Implements:
1. **Human-Readable Joint Action Decoding (`decode_slot_choice`, `decode_joint_action`)**:
   Maps `(choice_a, choice_b)` indices in `0..25` back to exact Pokémon species,
   move names, Mega Evolution flags, target slots, and bench switches.
2. **Iterated Elimination of Dominated Strategies (`run_iterated_dominance_elimination`)**:
   Recursively prunes strictly (and $\\epsilon$-weakly) dominated joint actions for
   `trainer_1` (rows) and `trainer_2` (columns) before equilibrium solving.
3. **Zero-Sum Nash / Minimax Equilibrium Solver (`solve_zero_sum_nash`)**:
   Solves $\\max_{p \\in \\Delta_{B_1}} \\min_{q \\in \\Delta_{B_2}} p^\\top U q$ via exact Linear
   Programming (`scipy.optimize.linprog` HiGHS) with a pure-NumPy vectorized
   **Regret-Matching+ (RM+)** solver fallback.
4. **Logit Quantal Response Equilibrium Solver (`solve_quantal_response`)**:
   Models boundedly rational human opponents on Pokémon Showdown via temperature-scaled
   logit best responses.
5. **Unified Turn Equilibrium Evaluator (`solve_turn_equilibrium`)**:
   Synthesizes IEDS, Nash, QRE, and bad-luck CVaR_10 resilience into ranked
   `ActionRecommendation` objects for `trainer_1`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from engine.vgc_tensor_core.compiler import (
    CHOICE_BASE_ALLY_START,
    CHOICE_BASE_OPP_A_START,
    CHOICE_BASE_OPP_B_START,
    CHOICE_MEGA_ALLY_START,
    CHOICE_MEGA_OPP_A_START,
    CHOICE_MEGA_OPP_B_START,
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
    CompiledBattleState,
)
from engine.vgc_tensor_core.logic_engine import PrunedSideActionTensorMask
from engine.vgc_tensor_core.schema_and_tables import (
    HAS_TORCH,
    MoveIdx,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_1_BENCH1,
    SLOT_TRAINER_1_BENCH2,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    SLOT_TRAINER_2_BENCH1,
    SLOT_TRAINER_2_BENCH2,
    TargetType,
)
from engine.vgc_tensor_core.state_machine import StepResult

if HAS_TORCH:
    import torch

try:
    from scipy.optimize import linprog as _scipy_linprog
    HAS_SCIPY = True
except Exception:
    _scipy_linprog = None
    HAS_SCIPY = False


def _to_numpy(arr: Any) -> np.ndarray:
    """Convert a PyTorch Tensor or array-like into a contiguous float64/float32 NumPy ndarray."""
    if HAS_TORCH and isinstance(arr, torch.Tensor):
        return arr.detach().cpu().numpy()
    return np.asarray(arr)


# =============================================================================
# 1. HUMAN-READABLE JOINT ACTION DECODING (`trainer_1` & `trainer_2`)
# =============================================================================

def decode_slot_choice(
    compiled_state: CompiledBattleState,
    trainer_id: str,
    is_slot_a: bool,
    choice_idx: int,
) -> str:
    """Decode a single active slot choice index `0..25` into a human-readable VGC command.

    Args:
        compiled_state: Compiled battle state containing `slot_species`, `slot_move_names`,
            and `moves_tensor`.
        trainer_id: `'trainer_1'` or `'trainer_2'`.
        is_slot_a: True for Active Slot A, False for Active Slot B.
        choice_idx: Integer choice index in `0..25`.

    Returns:
        Readable string such as `"Charizard: Heat Wave (Spread) [MEGA]"` or
        `"Rillaboom: Switch -> Kingambit (Bench 2)"`.
    """
    c = int(choice_idx)
    if trainer_id == "trainer_1":
        actor_slot = SLOT_TRAINER_1_A if is_slot_a else SLOT_TRAINER_1_B
        partner_slot = SLOT_TRAINER_1_B if is_slot_a else SLOT_TRAINER_1_A
        opp_a_slot = SLOT_TRAINER_2_A
        opp_b_slot = SLOT_TRAINER_2_B
        bench1_slot = SLOT_TRAINER_1_BENCH1
        bench2_slot = SLOT_TRAINER_1_BENCH2
    elif trainer_id == "trainer_2":
        actor_slot = SLOT_TRAINER_2_A if is_slot_a else SLOT_TRAINER_2_B
        partner_slot = SLOT_TRAINER_2_B if is_slot_a else SLOT_TRAINER_2_A
        opp_a_slot = SLOT_TRAINER_1_A
        opp_b_slot = SLOT_TRAINER_1_B
        bench1_slot = SLOT_TRAINER_2_BENCH1
        bench2_slot = SLOT_TRAINER_2_BENCH2
    else:
        raise ValueError(f"Invalid trainer_id: {trainer_id!r}. Must be 'trainer_1' or 'trainer_2'.")

    species_list = compiled_state.slot_species
    actor_name = (
        species_list[actor_slot]
        if len(species_list) > actor_slot and species_list[actor_slot]
        else f"Slot{actor_slot}"
    )

    if c == CHOICE_SWITCH_BENCH1:
        b1_name = (
            species_list[bench1_slot]
            if len(species_list) > bench1_slot and species_list[bench1_slot]
            else "Bench 1"
        )
        return f"{actor_name}: Switch -> {b1_name}"

    if c == CHOICE_SWITCH_BENCH2:
        b2_name = (
            species_list[bench2_slot]
            if len(species_list) > bench2_slot and species_list[bench2_slot]
            else "Bench 2"
        )
        return f"{actor_name}: Switch -> {b2_name}"

    is_mega = 12 <= c < 24
    base_c = c - 12 if is_mega else c
    move_slot = base_c % 4
    target_bucket = base_c // 4  # 0: Opp A, 1: Opp B, 2: Ally Partner

    move_name = f"Move {move_slot + 1}"
    if (
        len(compiled_state.slot_move_names) > actor_slot
        and len(compiled_state.slot_move_names[actor_slot]) > move_slot
        and compiled_state.slot_move_names[actor_slot][move_slot]
    ):
        move_name = compiled_state.slot_move_names[actor_slot][move_slot]

    # Inspect target archetype from moves_tensor so spread/self/side moves are labeled cleanly
    moves_np = _to_numpy(compiled_state.moves_tensor)
    tgt_type = int(round(float(moves_np[actor_slot, move_slot, MoveIdx.TARGET_TYPE])))

    if tgt_type == int(TargetType.ALL_ADJACENT_FOES):
        target_label = "Spread Foes"
    elif tgt_type == int(TargetType.ALL_ADJACENT):
        target_label = "Spread All"
    elif tgt_type == int(TargetType.SELF):
        target_label = "Self"
    elif tgt_type == int(TargetType.ALLY_SIDE):
        target_label = "Ally Side"
    elif tgt_type == int(TargetType.GLOBAL_FIELD):
        target_label = "Field"
    else:
        if target_bucket == 0:
            t_sp = species_list[opp_a_slot] if len(species_list) > opp_a_slot else "Opp A"
            target_label = f"-> {t_sp} (Opp A)"
        elif target_bucket == 1:
            t_sp = species_list[opp_b_slot] if len(species_list) > opp_b_slot else "Opp B"
            target_label = f"-> {t_sp} (Opp B)"
        else:
            t_sp = species_list[partner_slot] if len(species_list) > partner_slot else "Partner"
            target_label = f"-> {t_sp} (Partner)"

    mega_tag = " [MEGA]" if is_mega else ""
    return f"{actor_name}: {move_name}{mega_tag} ({target_label})"


def decode_joint_action(
    compiled_state: CompiledBattleState,
    trainer_id: str,
    choice_pair: Sequence[int],
) -> str:
    """Decode a `(choice_a, choice_b)` pair into a combined VGC joint action description."""
    str_a = decode_slot_choice(compiled_state, trainer_id, is_slot_a=True, choice_idx=int(choice_pair[0]))
    str_b = decode_slot_choice(compiled_state, trainer_id, is_slot_a=False, choice_idx=int(choice_pair[1]))
    return f"{str_a}  ||  {str_b}"


# =============================================================================
# 2. ITERATED ELIMINATION OF DOMINATED STRATEGIES (IEDS)
# =============================================================================

@dataclass(frozen=True)
class DominatedActionRecord:
    """Record explaining why a specific action index was eliminated during IEDS."""

    trainer_id: str
    eliminated_idx: int
    dominated_by_idx: int
    round_eliminated: int
    worst_margin: float
    mean_margin: float


@dataclass(frozen=True)
class IEDSResult:
    """Result of Iterated Elimination of Dominated Strategies on a `[B1, B2]` payoff matrix.

    Attributes:
        trainer_1_surviving_indices: 1D int64 ndarray of surviving row indices in `0..B1-1`.
        trainer_2_surviving_indices: 1D int64 ndarray of surviving col indices in `0..B2-1`.
        reduced_payoff_matrix: 2D float64 ndarray of shape `[B1_surv, B2_surv]`.
        rounds_executed: Number of alternating row/column elimination rounds until convergence.
        eliminated_trainer_1: List of `DominatedActionRecord` for pruned `trainer_1` actions.
        eliminated_trainer_2: List of `DominatedActionRecord` for pruned `trainer_2` actions.
    """

    trainer_1_surviving_indices: np.ndarray
    trainer_2_surviving_indices: np.ndarray
    reduced_payoff_matrix: np.ndarray
    rounds_executed: int
    eliminated_trainer_1: List[DominatedActionRecord] = field(default_factory=list)
    eliminated_trainer_2: List[DominatedActionRecord] = field(default_factory=list)

    @property
    def num_trainer_1_surviving(self) -> int:
        """Number of surviving `trainer_1` joint actions."""
        return int(self.trainer_1_surviving_indices.shape[0])

    @property
    def num_trainer_2_surviving(self) -> int:
        """Number of surviving `trainer_2` joint actions."""
        return int(self.trainer_2_surviving_indices.shape[0])


def run_iterated_dominance_elimination(
    payoff_matrix: Any,
    dominance_Margin_eps: float = 0.0,
    eliminate_weakly_dominated: bool = True,
    max_rounds: int = 32,
) -> IEDSResult:
    """Perform Iterated Elimination of Strictly/Weakly Dominated Strategies (IEDS).

    In our zero-sum formulation, `payoff_matrix[i, j]` is the utility for `trainer_1`
    when `trainer_1` plays row `i` and `trainer_2` plays column `j` (`trainer_1` maximizes,
    `trainer_2` minimizes).

    - Row `i` (`trainer_1`) is dominated by row `i'` (`i' != i`) across surviving columns `J` if:
      * Strict (`eliminate_weakly_dominated=False`):
        $\\forall j \\in J,\\; U_{i', j} > U_{i, j} + \\epsilon$
      * Weak (`eliminate_weakly_dominated=True`):
        $\\forall j \\in J,\\; U_{i', j} \\ge U_{i, j} + \\epsilon$ and $\\exists j \\in J,\\; U_{i', j} > U_{i, j} + 10^{-7}$
    - Column `j` (`trainer_2`) is dominated by column `j'` (`j' != j`) across surviving rows `I` if:
      * Strict: $\\forall i \\in I,\\; U_{i, j'} < U_{i, j} - \\epsilon$
      * Weak: $\\forall i \\in I,\\; U_{i, j'} \\le U_{i, j} - \\epsilon$ and $\\exists i \\in I,\\; U_{i, j'} < U_{i, j} - 10^{-7}$

    Args:
        payoff_matrix: 2D tensor or ndarray of shape `[B1, B2]`.
        dominance_Margin_eps: Minimum dominance margin $\\epsilon \\ge 0$.
        eliminate_weakly_dominated: Whether to prune weakly dominated actions (with tie-break guard
            so identical rows/columns never mutually annihilate).
        max_rounds: Maximum number of alternating row-column pruning passes.

    Returns:
        `IEDSResult` containing the surviving strategy core and elimination audit trail.
    """
    U = np.asarray(_to_numpy(payoff_matrix), dtype=np.float64)
    if U.ndim != 2:
        raise ValueError(f"Expected 2D payoff_matrix [B1, B2], got shape {U.shape}.")

    B1, B2 = U.shape
    surv_r = np.arange(B1, dtype=np.int64)
    surv_c = np.arange(B2, dtype=np.int64)

    elim_t1: List[DominatedActionRecord] = []
    elim_t2: List[DominatedActionRecord] = []
    eps = float(dominance_Margin_eps)
    strict_tol = 1e-7

    rounds = 0
    for round_idx in range(1, max_rounds + 1):
        changed = False

        # --- Pass A: Eliminate dominated rows for trainer_1 (maximizer) ---
        if len(surv_r) > 1:
            U_sub = U[np.ix_(surv_r, surv_c)]  # [R, C]
            R = len(surv_r)
            keep_r_mask = np.ones(R, dtype=bool)

            # diff[i', i, j] = U_sub[i', j] - U_sub[i, j]
            for i in range(R):
                if not keep_r_mask[i]:
                    continue
                row_i = U_sub[i]  # [C]
                for i_prime in range(R):
                    if i_prime == i or not keep_r_mask[i_prime]:
                        continue
                    diff = U_sub[i_prime] - row_i
                    min_diff = float(np.min(diff))
                    max_diff = float(np.max(diff))
                    if eliminate_weakly_dominated:
                        is_dom = (min_diff >= eps - 1e-12) and (max_diff > strict_tol)
                    else:
                        is_dom = min_diff > eps + strict_tol

                    if is_dom:
                        keep_r_mask[i] = False
                        elim_t1.append(
                            DominatedActionRecord(
                                trainer_id="trainer_1",
                                eliminated_idx=int(surv_r[i]),
                                dominated_by_idx=int(surv_r[i_prime]),
                                round_eliminated=round_idx,
                                worst_margin=min_diff,
                                mean_margin=float(np.mean(diff)),
                            )
                        )
                        changed = True
                        break

            if not np.any(keep_r_mask):
                keep_r_mask[0] = True
            surv_r = surv_r[keep_r_mask]

        # --- Pass B: Eliminate dominated columns for trainer_2 (minimizer) ---
        if len(surv_c) > 1:
            U_sub = U[np.ix_(surv_r, surv_c)]  # [R, C]
            C = len(surv_c)
            keep_c_mask = np.ones(C, dtype=bool)

            for j in range(C):
                if not keep_c_mask[j]:
                    continue
                col_j = U_sub[:, j]  # [R]
                for j_prime in range(C):
                    if j_prime == j or not keep_c_mask[j_prime]:
                        continue
                    # trainer_2 wants smaller U, so j' dominates j if U[:, j'] <= U[:, j]
                    diff = col_j - U_sub[:, j_prime]
                    min_diff = float(np.min(diff))
                    max_diff = float(np.max(diff))
                    if eliminate_weakly_dominated:
                        is_dom = (min_diff >= eps - 1e-12) and (max_diff > strict_tol)
                    else:
                        is_dom = min_diff > eps + strict_tol

                    if is_dom:
                        keep_c_mask[j] = False
                        elim_t2.append(
                            DominatedActionRecord(
                                trainer_id="trainer_2",
                                eliminated_idx=int(surv_c[j]),
                                dominated_by_idx=int(surv_c[j_prime]),
                                round_eliminated=round_idx,
                                worst_margin=min_diff,
                                mean_margin=float(np.mean(diff)),
                            )
                        )
                        changed = True
                        break

            if not np.any(keep_c_mask):
                keep_c_mask[0] = True
            surv_c = surv_c[keep_c_mask]

        rounds = round_idx
        if not changed:
            break

    reduced_U = U[np.ix_(surv_r, surv_c)]
    return IEDSResult(
        trainer_1_surviving_indices=surv_r,
        trainer_2_surviving_indices=surv_c,
        reduced_payoff_matrix=reduced_U,
        rounds_executed=rounds,
        eliminated_trainer_1=elim_t1,
        eliminated_trainer_2=elim_t2,
    )


# =============================================================================
# 3. ZERO-SUM NASH / MINIMAX EQUILIBRIUM SOLVER (LP + REGRET-MATCHING+ FALLBACK)
# =============================================================================

@dataclass(frozen=True)
class ZeroSumNashResult:
    """Solution of the two-player zero-sum game $\\max_p \\min_q p^\\top U q$.

    Attributes:
        trainer_1_strategy: 1D float64 probability vector `[B1]` ($\\sum_i p_i = 1$).
        trainer_2_strategy: 1D float64 probability vector `[B2]` ($\\sum_j q_j = 1$).
        game_value: Equilibrium game value $v^* = p^{*\\top} U q^*$.
        pure_maximin_value: Pure-strategy security level $\\max_i \\min_j U_{i, j}$ for `trainer_1`.
        pure_minimax_value: Pure-strategy ceiling $\\min_j \\max_i U_{i, j}$ for `trainer_2`.
        pure_maximin_idx: Row index $i$ achieving `pure_maximin_value`.
        pure_minimax_idx: Column index $j$ achieving `pure_minimax_value`.
        exploitability_gap: Dual gap $\\max_i (U q^*)_i - \\min_j (p^{*\\top} U)_j \\ge 0$.
        solver_used: `'scipy_highs_lp'`, `'pure_saddle_point'`, or `'regret_matching_plus'`.
    """

    trainer_1_strategy: np.ndarray
    trainer_2_strategy: np.ndarray
    game_value: float
    pure_maximin_value: float
    pure_minimax_value: float
    pure_maximin_idx: int
    pure_minimax_idx: int
    exploitability_gap: float
    solver_used: str


def _solve_zero_sum_rm_plus(
    U: np.ndarray,
    num_iterations: int = 2500,
) -> Tuple[np.ndarray, np.ndarray]:
    """Solve a zero-sum matrix game `U` (`[R, C]`) via vectorized Regret-Matching+ (Tammelin 2014).

    Uses linear averaging of strategy profiles ($t$-weighted), achieving $O(1/T)$ convergence.
    """
    R, C = U.shape
    regret_r = np.zeros(R, dtype=np.float64)
    regret_c = np.zeros(C, dtype=np.float64)

    p_sum = np.zeros(R, dtype=np.float64)
    q_sum = np.zeros(C, dtype=np.float64)

    p = np.full(R, 1.0 / float(R), dtype=np.float64)
    q = np.full(C, 1.0 / float(C), dtype=np.float64)

    for t in range(1, num_iterations + 1):
        # Row player (trainer_1 maximizes): utility vector u_r = U @ q
        u_r = U @ q
        ev_r = float(np.dot(p, u_r))
        regret_r = np.maximum(0.0, regret_r + (u_r - ev_r))
        s_r = float(np.sum(regret_r))
        if s_r > 1e-15:
            p = regret_r / s_r
        else:
            p = np.full(R, 1.0 / float(R), dtype=np.float64)

        # Column player (trainer_2 minimizes): loss vector u_c = p^T @ U
        u_c = p @ U
        ev_c = float(np.dot(u_c, q))
        regret_c = np.maximum(0.0, regret_c + (ev_c - u_c))
        s_c = float(np.sum(regret_c))
        if s_c > 1e-15:
            q = regret_c / s_c
        else:
            q = np.full(C, 1.0 / float(C), dtype=np.float64)

        weight = float(t)
        p_sum += weight * p
        q_sum += weight * q

    p_avg = p_sum / max(1e-15, float(np.sum(p_sum)))
    q_avg = q_sum / max(1e-15, float(np.sum(q_sum)))
    return p_avg, q_avg


def _solve_zero_sum_lp_scipy(U: np.ndarray) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Solve exact zero-sum game `U` (`[R, C]`) using `scipy.optimize.linprog(method='highs')`."""
    if not HAS_SCIPY or _scipy_linprog is None:
        return None

    R, C = U.shape
    # Primal LP for trainer_1: maximize v  <=>  minimize -v
    # Variables: x = [p_0, ..., p_{R-1}, v] of length R + 1
    # Constraints: for each col j: sum_i p_i U_{i, j} >= v  <=>  -sum_i p_i U_{i, j} + v <= 0
    c_obj = np.zeros(R + 1, dtype=np.float64)
    c_obj[-1] = -1.0

    A_ub = np.hstack([-U.T, np.ones((C, 1), dtype=np.float64)])
    b_ub = np.zeros(C, dtype=np.float64)

    A_eq = np.zeros((1, R + 1), dtype=np.float64)
    A_eq[0, :R] = 1.0
    b_eq = np.array([1.0], dtype=np.float64)

    bounds = [(0.0, 1.0) for _ in range(R)] + [(None, None)]

    res_p = _scipy_linprog(
        c=c_obj,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not res_p.success or res_p.x is None:
        return None

    p_star = np.clip(res_p.x[:R], 0.0, 1.0)
    p_sum = float(np.sum(p_star))
    if p_sum <= 0.0:
        return None
    p_star /= p_sum

    # Dual LP for trainer_2: minimize w
    # Variables: y = [q_0, ..., q_{C-1}, w] of length C + 1
    # Constraints: for each row i: sum_j U_{i, j} q_j <= w  <=>  sum_j U_{i, j} q_j - w <= 0
    c_dual = np.zeros(C + 1, dtype=np.float64)
    c_dual[-1] = 1.0

    A_ub_d = np.hstack([U, -np.ones((R, 1), dtype=np.float64)])
    b_ub_d = np.zeros(R, dtype=np.float64)

    A_eq_d = np.zeros((1, C + 1), dtype=np.float64)
    A_eq_d[0, :C] = 1.0
    b_eq_d = np.array([1.0], dtype=np.float64)

    bounds_d = [(0.0, 1.0) for _ in range(C)] + [(None, None)]

    res_q = _scipy_linprog(
        c=c_dual,
        A_ub=A_ub_d,
        b_ub=b_ub_d,
        A_eq=A_eq_d,
        b_eq=b_eq_d,
        bounds=bounds_d,
        method="highs",
    )
    if not res_q.success or res_q.x is None:
        return None

    q_star = np.clip(res_q.x[:C], 0.0, 1.0)
    q_sum = float(np.sum(q_star))
    if q_sum <= 0.0:
        return None
    q_star /= q_sum

    return p_star, q_star


def solve_zero_sum_nash(
    payoff_matrix: Any,
    use_ieds_prepass: bool = True,
    rm_iterations: int = 2500,
) -> ZeroSumNashResult:
    """Compute the exact Two-Player Zero-Sum Nash / Minimax Equilibrium on `payoff_matrix`.

    Automatically checks for a pure-strategy saddle point first ($O(B_1 B_2)$), then
    optionally reduces the matrix via strict IEDS, solves via HiGHS LP or Regret-Matching+,
    and lifts the equilibrium strategies back to the full `[B1]` and `[B2]` action spaces.
    """
    U = np.asarray(_to_numpy(payoff_matrix), dtype=np.float64)
    if U.ndim != 2:
        raise ValueError(f"Expected 2D payoff_matrix [B1, B2], got shape {U.shape}.")

    B1, B2 = U.shape
    row_mins = np.min(U, axis=1)  # [B1]
    col_maxs = np.max(U, axis=0)  # [B2]

    maximin_idx = int(np.argmax(row_mins))
    minimax_idx = int(np.argmin(col_maxs))
    pure_maximin_val = float(row_mins[maximin_idx])
    pure_minimax_val = float(col_maxs[minimax_idx])

    # 1. Fast Path: Pure-Strategy Saddle Point exists when max_i min_j U == min_j max_i U
    if abs(pure_minimax_val - pure_maximin_val) <= 1e-7:
        p_full = np.zeros(B1, dtype=np.float64)
        q_full = np.zeros(B2, dtype=np.float64)
        p_full[maximin_idx] = 1.0
        q_full[minimax_idx] = 1.0
        return ZeroSumNashResult(
            trainer_1_strategy=p_full,
            trainer_2_strategy=q_full,
            game_value=0.5 * (pure_maximin_val + pure_minimax_val),
            pure_maximin_value=pure_maximin_val,
            pure_minimax_value=pure_minimax_val,
            pure_maximin_idx=maximin_idx,
            pure_minimax_idx=minimax_idx,
            exploitability_gap=abs(pure_minimax_val - pure_maximin_val),
            solver_used="pure_saddle_point",
        )

    # 2. Optional IEDS pre-reduction
    if use_ieds_prepass and (B1 > 2 or B2 > 2):
        ieds = run_iterated_dominance_elimination(U, eliminate_weakly_dominated=False)
        surv_r = ieds.trainer_1_surviving_indices
        surv_c = ieds.trainer_2_surviving_indices
        U_sub = ieds.reduced_payoff_matrix
    else:
        surv_r = np.arange(B1, dtype=np.int64)
        surv_c = np.arange(B2, dtype=np.int64)
        U_sub = U

    # 3. Try exact HiGHS LP first; fall back to vectorized Regret-Matching+
    lp_sol = _solve_zero_sum_lp_scipy(U_sub)
    if lp_sol is not None:
        p_sub, q_sub = lp_sol
        solver_name = "scipy_highs_lp"
    else:
        p_sub, q_sub = _solve_zero_sum_rm_plus(U_sub, num_iterations=rm_iterations)
        solver_name = "regret_matching_plus"

    # Zero out tiny numerical noise (< 1e-6) and re-normalize
    p_sub = np.where(p_sub < 1e-6, 0.0, p_sub)
    p_sub /= max(1e-15, float(np.sum(p_sub)))
    q_sub = np.where(q_sub < 1e-6, 0.0, q_sub)
    q_sub /= max(1e-15, float(np.sum(q_sub)))

    p_full = np.zeros(B1, dtype=np.float64)
    q_full = np.zeros(B2, dtype=np.float64)
    p_full[surv_r] = p_sub
    q_full[surv_c] = q_sub

    ev_t1 = U @ q_full
    ev_t2 = p_full @ U
    game_val = float(p_full @ ev_t1)
    gap = max(0.0, float(np.max(ev_t1) - np.min(ev_t2)))

    return ZeroSumNashResult(
        trainer_1_strategy=p_full,
        trainer_2_strategy=q_full,
        game_value=game_val,
        pure_maximin_value=pure_maximin_val,
        pure_minimax_value=pure_minimax_val,
        pure_maximin_idx=maximin_idx,
        pure_minimax_idx=minimax_idx,
        exploitability_gap=gap,
        solver_used=solver_name,
    )


# =============================================================================
# 4. LOGIT QUANTAL RESPONSE EQUILIBRIUM (QRE) FOR REALISTIC HUMAN OPPONENTS
# =============================================================================

@dataclass(frozen=True)
class QuantalResponseResult:
    """Solution of Logit Quantal Response Equilibrium (McKelvey & Palfrey 1995)."""

    trainer_1_strategy: np.ndarray
    trainer_2_strategy: np.ndarray
    expected_value: float
    rationality_beta: float
    iterations_run: int


def _stable_softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable 1D softmax."""
    z = x - np.max(x)
    e = np.exp(np.clip(z, -80.0, 0.0))
    return e / max(1e-15, float(np.sum(e)))


def solve_quantal_response(
    payoff_matrix: Any,
    rationality_beta: float = 4.0,
    max_iterations: int = 120,
    damping: float = 0.35,
    tol: float = 1e-7,
) -> QuantalResponseResult:
    """Compute the Logit Quantal Response Equilibrium (QRE) for boundedly rational players.

    Models human VGC players who strongly prefer higher-utility moves (governed by
    inverse temperature $\\beta > 0$) without playing a brittle deterministic argmax:
    $$q_j \\propto \\exp\\!\\left(-\\beta \\sum_i p_i U_{i, j}\\right), \\qquad
      p_i \\propto \\exp\\!\\left(+\\beta \\sum_j U_{i, j} q_j\\right)$$
    """
    U = np.asarray(_to_numpy(payoff_matrix), dtype=np.float64)
    B1, B2 = U.shape
    beta = max(0.01, float(rationality_beta))

    p = np.full(B1, 1.0 / float(B1), dtype=np.float64)
    q = np.full(B2, 1.0 / float(B2), dtype=np.float64)

    it_done = 0
    for it in range(1, max_iterations + 1):
        # Opponent trainer_2 minimizes U -> logit on -beta * (p^T U)
        q_target = _stable_softmax(-beta * (p @ U))
        q_next = (1.0 - damping) * q + damping * q_target

        # Player trainer_1 maximizes U -> logit on +beta * (U q_next)
        p_target = _stable_softmax(+beta * (U @ q_next))
        p_next = (1.0 - damping) * p + damping * p_target

        diff = max(float(np.max(np.abs(p_next - p))), float(np.max(np.abs(q_next - q))))
        p, q = p_next, q_next
        it_done = it
        if diff < tol:
            break

    ev = float(p @ U @ q)
    return QuantalResponseResult(
        trainer_1_strategy=p,
        trainer_2_strategy=q,
        expected_value=ev,
        rationality_beta=beta,
        iterations_run=it_done,
    )


# =============================================================================
# 5. UNIFIED TURN EQUILIBRIUM & DOMINANT STRATEGY EVALUATOR
# =============================================================================

@dataclass(frozen=True)
class ActionRecommendation:
    """Ranked strategic evaluation of a single `trainer_1` joint action `(choice_a, choice_b)`.

    Attributes:
        action_index: Row index `i` in `mask_trainer_1.pruned_choices` (`0..B1-1`).
        choice_pair: Tuple `(choice_a, choice_b)` in `0..25`.
        description: Human-readable move/switch description for Active Slot A and Slot B.
        survived_ieds: True if this action was NOT eliminated during IEDS.
        nash_probability: Equilibrium mixture weight $p^*_i \\in [0, 1]$ in the Zero-Sum Nash profile.
        qre_probability: Mixture weight $p^{\\text{QRE}}_i \\in [0, 1]$ in the Human QRE profile.
        expected_risk_utility_vs_nash: Expected risk-adjusted utility against $q^*$.
        expected_risk_utility_vs_qre: Expected risk-adjusted utility against $q^{\\text{QRE}}$.
        expected_mean_utility_vs_nash: Expected mean board utility $\\mathbb{E}[U]$ against $q^*$.
        expected_cvar_10_vs_nash: Expected worst-10% bad-luck utility $\\text{CVaR}_{0.10}[U]$ against $q^*$.
        worst_case_counter_utility: Security floor $\\min_j U^{\\text{risk}}_{i, j}$ against `trainer_2`'s
            hardest counter-play.
        worst_case_counter_description: Human-readable description of `trainer_2`'s best counter-play $j^*$.
        win_turn_prob_vs_nash: Empirical probability $P(U > 0)$ of winning the turn against $q^*$.
        composite_score: Overall ranking score blending Nash security, QRE human exploit, and CVaR_10 floor.
    """

    action_index: int
    choice_pair: Tuple[int, int]
    description: str
    survived_ieds: bool
    nash_probability: float
    qre_probability: float
    expected_risk_utility_vs_nash: float
    expected_risk_utility_vs_qre: float
    expected_mean_utility_vs_nash: float
    expected_cvar_10_vs_nash: float
    worst_case_counter_utility: float
    worst_case_counter_description: str
    win_turn_prob_vs_nash: float
    composite_score: float


@dataclass(frozen=True)
class TurnEquilibriumResult:
    """Complete game-theoretic solution for a single VGC Doubles turn."""

    ieds: IEDSResult
    nash: ZeroSumNashResult
    qre: QuantalResponseResult
    recommendations: List[ActionRecommendation]
    top_opponent_actions: List[Tuple[int, Tuple[int, int], str, float, float]]

    @property
    def best_recommendation(self) -> ActionRecommendation:
        """Return the #1 ranked risk-resilient dominant strategy recommendation for `trainer_1`."""
        return self.recommendations[0]


def solve_turn_equilibrium(
    compiled_state: CompiledBattleState,
    mask_trainer_1: PrunedSideActionTensorMask,
    mask_trainer_2: PrunedSideActionTensorMask,
    step_result: StepResult,
    rationality_beta: float = 4.0,
    eliminate_weakly_dominated: bool = True,
    top_k: int = 10,
) -> TurnEquilibriumResult:
    """Run IEDS + Zero-Sum Nash + Logit QRE on a simulated turn's risk-adjusted payoff matrix.

    Ranks `trainer_1`'s legal joint actions so the top recommendation is both:
    - **Game-theoretically unexploitable** against smart `trainer_2` counter-play, and
    - **Resilient to bad cartridge RNG** (incorporating the `CVaR_10` worst-10% bad-luck tail).
    """
    u_risk = np.asarray(_to_numpy(step_result.stats.risk_adjusted_utility), dtype=np.float64)
    u_mean = np.asarray(_to_numpy(step_result.stats.mean_utility), dtype=np.float64)
    u_cvar = np.asarray(_to_numpy(step_result.stats.cvar_10_utility), dtype=np.float64)
    u_win = np.asarray(_to_numpy(step_result.stats.win_turn_prob), dtype=np.float64)

    t1_choices_np = np.asarray(_to_numpy(mask_trainer_1.pruned_choices), dtype=np.int64)
    t2_choices_np = np.asarray(_to_numpy(mask_trainer_2.pruned_choices), dtype=np.int64)

    B1, B2 = u_risk.shape

    # 1. Run IEDS on the risk-adjusted payoff matrix
    ieds_res = run_iterated_dominance_elimination(
        u_risk,
        eliminate_weakly_dominated=eliminate_weakly_dominated,
    )
    surv_set_t1 = set(int(x) for x in ieds_res.trainer_1_surviving_indices)

    # 2. Solve Zero-Sum Nash Equilibrium on the risk-adjusted payoff matrix
    nash_res = solve_zero_sum_nash(u_risk, use_ieds_prepass=True)

    # 3. Solve Logit Quantal Response Equilibrium (bounded-rationality human opponent model)
    qre_res = solve_quantal_response(u_risk, rationality_beta=rationality_beta)

    q_nash = nash_res.trainer_2_strategy
    q_qre = qre_res.trainer_2_strategy

    # Pre-decode trainer_2 joint actions
    t2_descriptions = [
        decode_joint_action(compiled_state, "trainer_2", t2_choices_np[j])
        for j in range(B2)
    ]

    # Expected vectors per trainer_1 row i
    ev_risk_nash = u_risk @ q_nash
    ev_risk_qre = u_risk @ q_qre
    ev_mean_nash = u_mean @ q_nash
    ev_cvar_nash = u_cvar @ q_nash
    ev_win_nash = u_win @ q_nash

    recommendations: List[ActionRecommendation] = []
    for i in range(B1):
        pair_i = (int(t1_choices_np[i, 0]), int(t1_choices_np[i, 1]))
        desc_i = decode_joint_action(compiled_state, "trainer_1", pair_i)
        survived = i in surv_set_t1

        worst_j = int(np.argmin(u_risk[i]))
        worst_val = float(u_risk[i, worst_j])
        worst_desc = t2_descriptions[worst_j]

        p_n = float(nash_res.trainer_1_strategy[i])
        p_q = float(qre_res.trainer_1_strategy[i])

        # Composite ranking score:
        # 55% Expected Risk-Adjusted Utility vs Nash + 30% Expected Risk-Adjusted Utility vs QRE
        # + 15% Worst-Case Security Floor + bonus for surviving IEDS and Nash support
        comp = (
            0.55 * float(ev_risk_nash[i])
            + 0.30 * float(ev_risk_qre[i])
            + 0.15 * worst_val
            + 0.25 * p_n
            + (0.05 if survived else -0.25)
        )

        recommendations.append(
            ActionRecommendation(
                action_index=i,
                choice_pair=pair_i,
                description=desc_i,
                survived_ieds=survived,
                nash_probability=p_n,
                qre_probability=p_q,
                expected_risk_utility_vs_nash=float(ev_risk_nash[i]),
                expected_risk_utility_vs_qre=float(ev_risk_qre[i]),
                expected_mean_utility_vs_nash=float(ev_mean_nash[i]),
                expected_cvar_10_vs_nash=float(ev_cvar_nash[i]),
                worst_case_counter_utility=worst_val,
                worst_case_counter_description=worst_desc,
                win_turn_prob_vs_nash=float(ev_win_nash[i]),
                composite_score=comp,
            )
        )

    recommendations.sort(key=lambda r: r.composite_score, reverse=True)

    # Top opponent actions sorted by combined Nash + QRE likelihood
    opp_ranked_indices = np.argsort(-(0.5 * q_nash + 0.5 * q_qre))
    top_opp: List[Tuple[int, Tuple[int, int], str, float, float]] = []
    for j in opp_ranked_indices[: max(1, min(top_k, B2))]:
        j_int = int(j)
        pair_j = (int(t2_choices_np[j_int, 0]), int(t2_choices_np[j_int, 1]))
        top_opp.append(
            (j_int, pair_j, t2_descriptions[j_int], float(q_nash[j_int]), float(q_qre[j_int]))
        )

    return TurnEquilibriumResult(
        ieds=ieds_res,
        nash=nash_res,
        qre=qre_res,
        recommendations=recommendations[: max(1, min(top_k, B1))] if top_k > 0 else recommendations,
        top_opponent_actions=top_opp,
    )


def format_equilibrium_coach_report(
    eq_result: TurnEquilibriumResult,
    num_simulations: int,
    verbosity: str = "coach",
    max_recommendations: int = 5,
) -> str:
    """Format a strategic report from `TurnEquilibriumResult` at the requested detail level.

    Args:
        eq_result: Solved `TurnEquilibriumResult`.
        num_simulations: Count of Monte Carlo RNG iterations evaluated per cell.
        verbosity: Detail level:
            - `'coach'` (default): Plain English summary for players.
            - `'standard'`: Tactical metrics and probabilities.
            - `'scientific'`: Mathematical audit of IEDS, Nash LP, QRE logit, and CVaR_10.
        max_recommendations: Max number of top recommendations to show.
    """
    v = str(verbosity or "coach").lower().strip()
    if v in ("simple", "brief", "casual", "player"):
        v = "coach"
    elif v in ("nerd", "full", "audit", "deep", "verbose"):
        v = "scientific"
    elif v not in ("coach", "standard", "scientific"):
        v = "coach"

    best = eq_result.best_recommendation

    if v == "coach":
        lines: List[str] = []
        lines.append("=" * 88)
        lines.append("COACH PORYGON VGC — TURN COACH ADVICE (MATCH PLAY)")
        lines.append("=" * 88)
        lines.append("🎯 RECOMMENDED PLAY FOR THIS TURN:")
        lines.append(f"   👉 {best.description}")
        lines.append("")
        lines.append("💡 WHY THIS PLAY:")
        lines.append(f"   • Win Probability: You have a {best.win_turn_prob_vs_nash * 100.0:.1f}% chance of winning this turn.")
        lines.append(f"   • Game-Theoretic Optimal: Our solver gives this play {best.nash_probability * 100.0:.1f}% unexploitable weight.")
        lines.append(f"   • Expected Average Score: {best.expected_mean_utility_vs_nash:+.3f} utility.")
        lines.append("")
        lines.append("⚠️ WHAT COULD GO WRONG (THE RISK):")
        lines.append(f"   • Hardest Opponent Counter: {best.worst_case_counter_description}")
        lines.append(
            f"   • Bad-Luck Floor (Worst 10% RNG): {best.expected_cvar_10_vs_nash:+.3f} utility "
            f"(even with misses or low damage rolls, this play protects your downside)."
        )
        lines.append("")
        if eq_result.top_opponent_actions:
            lines.append("🔮 OPPONENT'S MOST LIKELY MOVE:")
            for rank, (_, _, desc_j, q_n, q_q) in enumerate(eq_result.top_opponent_actions[:2], start=1):
                prob = max(q_n, q_q) * 100.0
                lines.append(f"   {rank}. (~{prob:.1f}% likelihood): {desc_j}")
            lines.append("")
        if len(eq_result.recommendations) > 1:
            lines.append("🔄 BACKUP OPTIONS:")
            for rank, rec in enumerate(eq_result.recommendations[1:max_recommendations], start=2):
                lines.append(
                    f"   #{rank} {rec.description} (Win: {rec.win_turn_prob_vs_nash * 100.0:.1f}%, Score: {rec.expected_risk_utility_vs_nash:+.3f})"
                )
            lines.append("")
        lines.append(f"⚙️ CALCULATION AUDIT: Simulated across {num_simulations} discrete dice rolls per matchup cell.")
        lines.append("   (Tip: Run with --verbosity scientific to view full mathematical derivation and damage rolls).")
        lines.append("=" * 88)
        return "\n".join(lines)

    lines = []
    lines.append("=" * 92)
    lines.append(
        f"COACH PORYGON VGC — GAME-THEORETIC & BAD-LUCK RESILIENT TURN ADVISOR (K={num_simulations} sims)"
    )
    lines.append("=" * 92)
    lines.append(
        f"IEDS Dominance Pruning : trainer_1 {eq_result.ieds.num_trainer_1_surviving} surviving "
        f"({len(eq_result.ieds.eliminated_trainer_1)} dominated pruned) | "
        f"trainer_2 {eq_result.ieds.num_trainer_2_surviving} surviving "
        f"({len(eq_result.ieds.eliminated_trainer_2)} dominated pruned) "
        f"in {eq_result.ieds.rounds_executed} round(s)"
    )
    lines.append(
        f"Zero-Sum Nash Value    : {eq_result.nash.game_value:+.4f} "
        f"(Pure Maximin={eq_result.nash.pure_maximin_value:+.4f}, "
        f"Pure Minimax={eq_result.nash.pure_minimax_value:+.4f}, "
        f"Solver={eq_result.nash.solver_used})"
    )
    lines.append(
        f"Human QRE Value (b={eq_result.qre.rationality_beta:.1f}): {eq_result.qre.expected_value:+.4f}"
    )

    if v == "scientific":
        lines.append("-" * 92)
        lines.append("MATHEMATICAL & PROCESS AUDIT:")
        lines.append("  • Downside Risk Metric (CVaR_10): Conditional Value at Risk in worst 10% simulation timelines.")
        lines.append("  • Optimization Objective: U_risk = 0.75 * Mean + 0.25 * CVaR_10")
        lines.append(f"  • Nash Equilibrium Gap: {eq_result.nash.exploitability_gap:.6f} via {eq_result.nash.solver_used}")
        lines.append(f"  • QRE Behavioral Temperature: beta={eq_result.qre.rationality_beta:.1f} ({eq_result.qre.iterations_run} fixed-point iterations)")

    lines.append("-" * 92)
    lines.append("TOP RECOMMENDED JOINT ACTIONS FOR TRAINER_1 (RANKED BY RISK-RESILIENT EQUILIBRIUM VALUE):")
    for rank, rec in enumerate(eq_result.recommendations[:max_recommendations], start=1):
        lines.append(
            f"  #{rank} [{rec.choice_pair[0]:2d}, {rec.choice_pair[1]:2d}] {rec.description}"
        )
        lines.append(
            f"      RiskEV(Nash)={rec.expected_risk_utility_vs_nash:+.3f} | "
            f"MeanEV={rec.expected_mean_utility_vs_nash:+.3f} | "
            f"BadLuckFloor(CVaR10)={rec.expected_cvar_10_vs_nash:+.3f} | "
            f"WinTurn%={rec.win_turn_prob_vs_nash * 100.0:5.1f}% | "
            f"NashMix={rec.nash_probability * 100.0:4.1f}% | "
            f"QREMix={rec.qre_probability * 100.0:4.1f}%"
        )
        lines.append(
            f"      Hardest Counter ({rec.worst_case_counter_utility:+.3f}): {rec.worst_case_counter_description}"
        )
    lines.append("-" * 92)
    lines.append("MOST LIKELY OPPONENT (TRAINER_2) COUNTER-PLAYS:")
    for rank, (j_idx, pair_j, desc_j, q_n, q_q) in enumerate(eq_result.top_opponent_actions[:3], start=1):
        lines.append(
            f"  #{rank} [{pair_j[0]:2d}, {pair_j[1]:2d}] (Nash={q_n * 100.0:4.1f}%, QRE={q_q * 100.0:4.1f}%): {desc_j}"
        )
    lines.append("=" * 92)
    return "\n".join(lines)

