# -*- coding: utf-8 -*-
"""Selective 2-Ply Lookahead on Strict-IEDS Survivors (Regulation M-C).

Expands only the surviving Strict-IEDS strategic core `[Surv_1 x Surv_2]` of Turn 1
one additional ply forward (Turn + 2) using the vectorized `VgcTensorStateMachine`.
Captures tactical multi-turn value invisible to 1-ply heuristics — such as Protect
stalls on the final turn of Trick Room / Tailwind, setup sweep continuations
(`Swords Dance` / `Nasty Plot` / `Calm Mind`), and clean 2-turn KO sequences —
while keeping wall-clock overhead bounded on both CUDA GPUs and CPUs.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, List, Optional, Sequence

import numpy as np

from engine.solver.game_theory import solve_zero_sum_nash
from engine.vgc_tensor_core.compiler import CompiledBattleState
from engine.vgc_tensor_core.schema_and_tables import HAS_TORCH
from engine.vgc_tensor_core.state_machine import (
    AnalysisCancelledError,
    VgcTensorStateMachine,
    compute_per_thread_board_utility_torch,
    execute_end_of_turn,
)

if HAS_TORCH:
    import torch
else:
    torch = None  # type: ignore


@dataclass(frozen=True)
class TwoPlyLookaheadResult:
    """Output of selective 2-Ply lookahead over the Strict-IEDS surviving core.

    Attributes:
        U_blended: Blended `[B1, B2]` utility matrix where evaluated Strict-IEDS
            cells combine Ply-1 utility `(1 - gamma) * U_ply1` with Ply-2 Nash
            continuation value `gamma * V_ply2`.
        V_ply2_core: Raw `[len(eval_t1_indices), len(eval_t2_indices)]` matrix of
            Ply-2 zero-sum Nash equilibrium continuation values.
        eval_t1_indices: Original `trainer_1` row indices expanded to Ply 2.
        eval_t2_indices: Original `trainer_2` column indices expanded to Ply 2.
        gamma: Continuation weight in `[0, 1]`.
        cells_evaluated: Total number of `(i, j)` Ply-1 cells rolled forward.
        elapsed_s: Wall-clock runtime in seconds.
    """

    U_blended: np.ndarray
    V_ply2_core: np.ndarray
    eval_t1_indices: List[int]
    eval_t2_indices: List[int]
    gamma: float
    cells_evaluated: int
    elapsed_s: float


def _select_top_core_indices(
    U_risk: np.ndarray,
    surv_1: Sequence[int],
    surv_2: Sequence[int],
    max_core_dim: int,
) -> tuple[List[int], List[int]]:
    """Select up to `max_core_dim` highest-leverage surviving indices per trainer."""
    s1 = [int(i) for i in surv_1]
    s2 = [int(j) for j in surv_2]
    if not s1 or not s2:
        return s1, s2

    sub = U_risk[np.ix_(s1, s2)]
    if len(s1) > max_core_dim:
        # Rank trainer_1 rows by average security + expected value against surviving foes
        row_scores = 0.5 * sub.mean(axis=1) + 0.5 * sub.min(axis=1)
        top_r = np.argsort(-row_scores)[:max_core_dim]
        s1 = [s1[int(idx)] for idx in top_r]
        sub = U_risk[np.ix_(s1, s2)]
    if len(s2) > max_core_dim:
        # Rank trainer_2 columns by best counterplay (lowest payoff for trainer_1)
        col_scores = 0.5 * sub.mean(axis=0) + 0.5 * sub.max(axis=0)
        top_c = np.argsort(col_scores)[:max_core_dim]
        s2 = [s2[int(idx)] for idx in top_c]

    return s1, s2


def _top_prior_choices(
    mask_res: Any,
    max_actions: int,
    device: Any,
) -> Any:
    """Keep up to `max_actions` legal Ply-2 choices ranked by tactical prior matrix."""
    coords = mask_res.pruned_choices
    n_valid = int(coords.shape[0])
    if n_valid <= max_actions:
        return coords
    priors = mask_res.prior_matrix_26x26
    if HAS_TORCH and isinstance(coords, torch.Tensor):
        c_np = coords.detach().cpu().numpy()
        p_np = priors.detach().cpu().numpy()
        scores = np.array([float(p_np[int(r[0]), int(r[1])]) for r in c_np], dtype=np.float32)
        top_idx = np.argsort(-scores)[:max_actions]
        return torch.tensor(c_np[top_idx], dtype=torch.long, device=device)
    c_np = np.asarray(coords)
    p_np = np.asarray(priors)
    scores = np.array([float(p_np[int(r[0]), int(r[1])]) for r in c_np], dtype=np.float32)
    top_idx = np.argsort(-scores)[:max_actions]
    return c_np[top_idx]


def evaluate_two_ply_on_ieds_core(
    sm: VgcTensorStateMachine,
    comp: CompiledBattleState,
    c1_np: np.ndarray,
    c2_np: np.ndarray,
    U_risk_ply1: np.ndarray,
    surv_1_indices: Sequence[int],
    surv_2_indices: Sequence[int],
    gamma: float = 0.35,
    max_core_dim: int = 6,
    k_ply1_branch: int = 4,
    k_ply2: int = 16,
    max_ply2_actions: int = 8,
    rng_seed: int = 42,
    cancel_event: Optional[threading.Event] = None,
) -> TwoPlyLookaheadResult:
    """Execute selective 2-Ply Nash lookahead on the Strict-IEDS surviving submatrix.

    Args:
        sm: Active `VgcTensorStateMachine` (CUDA GPU or CPU).
        comp: Compiled Turn-1 `CompiledBattleState`.
        c1_np: `[B1, 2]` array of legal `trainer_1` choice pairs.
        c2_np: `[B2, 2]` array of legal `trainer_2` choice pairs.
        U_risk_ply1: `[B1, B2]` Turn-1 risk-adjusted utility matrix.
        surv_1_indices: Row indices surviving Strict IEDS for `trainer_1`.
        surv_2_indices: Column indices surviving Strict IEDS for `trainer_2`.
        gamma: Weight on Ply-2 continuation value (`0.35` default).
        max_core_dim: Maximum surviving strategies per side expanded to Ply 2.
        k_ply1_branch: Representative Turn-1 trajectories sampled to pick median EoT board.
        k_ply2: Discrete RNG threads per Ply-2 matchup cell.
        max_ply2_actions: Maximum prior-ranked Ply-2 choices evaluated per side.
        rng_seed: Deterministic SplitMix64 seed base.
        cancel_event: Optional `threading.Event` checked between expanded cells.

    Returns:
        `TwoPlyLookaheadResult` containing the blended payoff matrix and timing metrics.
    """
    t0 = time.perf_counter()
    U_blended = np.array(U_risk_ply1, dtype=np.float64, copy=True)
    eval_1, eval_2 = _select_top_core_indices(U_risk_ply1, surv_1_indices, surv_2_indices, max_core_dim)

    if not eval_1 or not eval_2 or not HAS_TORCH:
        return TwoPlyLookaheadResult(
            U_blended=U_blended,
            V_ply2_core=np.zeros((len(eval_1), len(eval_2)), dtype=np.float64),
            eval_t1_indices=eval_1,
            eval_t2_indices=eval_2,
            gamma=float(gamma),
            cells_evaluated=0,
            elapsed_s=round(time.perf_counter() - t0, 4),
        )

    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelledError("2-Ply lookahead cancelled before Ply-1 branch generation.")

    dev = sm.device
    c1_core_t = torch.tensor(c1_np[eval_1], dtype=torch.long, device=dev)
    c2_core_t = torch.tensor(c2_np[eval_2], dtype=torch.long, device=dev)

    # 1. Generate post-Turn-1 EoT states across the surviving core with auto-promoted bench replacements
    with torch.inference_mode():
        step1_core = sm.step(
            comp.field_tensor,
            comp.roster_tensor,
            comp.moves_tensor,
            c1_core_t,
            c2_core_t,
            num_mc_samples=max(1, int(k_ply1_branch)),
            rng_seed=int(rng_seed) + 7771,
            tile_size=max(len(eval_1), len(eval_2), 8),
            cancel_event=cancel_event,
        )
        eot1_prom = execute_end_of_turn(
            F_cascade=step1_core.attack_cascade.F,
            P_cascade=step1_core.attack_cascade.P,
            M_cascade=step1_core.attack_cascade.M_moves,
            tables=sm.tables,
            auto_promote=True,
            extra_volatiles=step1_core.attack_cascade.extra_volatiles,
        )
        u_branch = compute_per_thread_board_utility_torch(
            eot1_prom.F,
            eot1_prom.P,
            extra_volatiles=step1_core.attack_cascade.extra_volatiles,
        )  # [C1, C2, K_branch]
        k_b = int(u_branch.shape[-1])
        med_pos = k_b // 2
        order_k = torch.argsort(u_branch, dim=-1)
        med_k_idx = order_k[:, :, med_pos]  # [C1, C2]

        V_ply2_core = np.zeros((len(eval_1), len(eval_2)), dtype=np.float64)
        cells_done = 0

        for ci, orig_i in enumerate(eval_1):
            for cj, orig_j in enumerate(eval_2):
                if cancel_event is not None and cancel_event.is_set():
                    raise AnalysisCancelledError("2-Ply lookahead cancelled during Ply-2 rollouts.")

                k_rep = int(med_k_idx[ci, cj].item())
                if float(eot1_prom.is_terminal[ci, cj].item()) > 0.5:
                    win_code = int(eot1_prom.winner[ci, cj].item())
                    v2 = 4.0 if win_code == 1 else (-4.0 if win_code == 2 else 0.0)
                else:
                    f_ply2 = eot1_prom.F[ci, cj, k_rep]
                    roster_ply2 = eot1_prom.P[ci, cj, k_rep]
                    moves_ply2 = eot1_prom.M_moves[ci, cj, k_rep]

                    comp2 = CompiledBattleState(
                        field_tensor=f_ply2,
                        roster_tensor=roster_ply2,
                        moves_tensor=moves_ply2,
                        backend="torch",
                        device=dev,
                        slot_species=comp.slot_species,
                        slot_move_names=comp.slot_move_names,
                    )
                    mask2_t1 = sm.logic_engine.prune_side_26x26_tensor_actions(
                        comp2, trainer_id="trainer_1", min_prior_threshold=0.0
                    )
                    mask2_t2 = sm.logic_engine.prune_side_26x26_tensor_actions(
                        comp2, trainer_id="trainer_2", min_prior_threshold=0.0
                    )
                    ch2_t1 = _top_prior_choices(mask2_t1, max_ply2_actions, dev)
                    ch2_t2 = _top_prior_choices(mask2_t2, max_ply2_actions, dev)

                    res2 = sm.step(
                        f_ply2,
                        roster_ply2,
                        moves_ply2,
                        ch2_t1,
                        ch2_t2,
                        num_mc_samples=max(4, int(k_ply2)),
                        rng_seed=int(rng_seed) + 99100 + ci * 97 + cj * 13,
                        tile_size=max(int(ch2_t1.shape[0]), int(ch2_t2.shape[0]), 8),
                        cancel_event=cancel_event,
                    )
                    u2_mat = res2.stats.risk_adjusted_utility.detach().cpu().numpy().astype(np.float64)
                    v2 = float(solve_zero_sum_nash(u2_mat).game_value)

                V_ply2_core[ci, cj] = v2
                U_blended[orig_i, orig_j] = (1.0 - float(gamma)) * float(U_risk_ply1[orig_i, orig_j]) + float(gamma) * v2
                cells_done += 1

    return TwoPlyLookaheadResult(
        U_blended=U_blended,
        V_ply2_core=V_ply2_core,
        eval_t1_indices=eval_1,
        eval_t2_indices=eval_2,
        gamma=float(gamma),
        cells_evaluated=cells_done,
        elapsed_s=round(time.perf_counter() - t0, 4),
    )
