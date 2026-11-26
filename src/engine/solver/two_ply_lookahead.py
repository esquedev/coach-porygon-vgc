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
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from engine.solver.game_theory import solve_zero_sum_nash
from engine.vgc_tensor_core.compiler import CompiledBattleState
from engine.vgc_tensor_core.schema_and_tables import (
    FieldOpID,
    HAS_TORCH,
    MOVES_PER_MON,
    MonIdx,
    MoveIdx,
    TYPE_TO_IDX,
)
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


def _inject_two_turn_primed_candidates(
    comp: CompiledBattleState,
    choices_np: np.ndarray,
    U_risk: np.ndarray,
    selected: List[int],
    is_trainer_1: bool,
    max_primed_inject: int = 2,
) -> List[int]:
    """Reserve up to `max_primed_inject` Turn-1 slots for high-value 2-turn primed plays
    (intentional ally-immunity Stomping Tantrum priming, 2-turn charge moves, Charge, or setup)
    that might otherwise be eliminated by 1-ply Strict IEDS before Ply-2 Nash can evaluate them.
    """
    if max_primed_inject <= 0 or choices_np.shape[0] == 0:
        return selected

    p_np = comp.roster_tensor.detach().cpu().numpy() if (HAS_TORCH and isinstance(comp.roster_tensor, torch.Tensor)) else np.asarray(comp.roster_tensor)
    m_np = comp.moves_tensor.detach().cpu().numpy() if (HAS_TORCH and isinstance(comp.moves_tensor, torch.Tensor)) else np.asarray(comp.moves_tensor)
    act_slots = (0, 1) if is_trainer_1 else (4, 5)

    # Identify which active slots hold 2-turn payoff or setup moves
    primed_slots: Dict[int, str] = {}
    for local_i, r_slot in enumerate(act_slots):
        if p_np[r_slot, MonIdx.HP_CUR] <= 0.0:
            continue
        fops = [int(round(float(m_np[r_slot, k, MoveIdx.FIELD_OP_ID]))) for k in range(MOVES_PER_MON)]
        wsures = [float(m_np[r_slot, k, MoveIdx.WEATHER_SURE_HIT]) for k in range(MOVES_PER_MON)]
        has_setup = any(
            m_np[r_slot, k, MoveIdx.CAT_STATUS] > 0.5
            and m_np[r_slot, k, MoveIdx.STAT_DELTA_SELF] > 0.5
            and float(np.sum(np.maximum(0.0, m_np[r_slot, k, MoveIdx.STAT_DELTA_ATK:MoveIdx.STAT_DELTA_SPE + 1]))) >= 2.0
            for k in range(MOVES_PER_MON)
        )
        if int(FieldOpID.STOMPING_TANTRUM) in fops:
            primed_slots[local_i] = "tantrum"
        elif int(FieldOpID.CHARGE) in fops or int(FieldOpID.PHANTOM_FORCE) in fops or any(w in (10.0, 20.0, 30.0) for w in wsures) or has_setup:
            primed_slots[local_i] = "charge_or_setup"

    if not primed_slots:
        return selected

    # Compute baseline row/col security-expected scores
    if is_trainer_1:
        scores = 0.5 * U_risk.mean(axis=1) + 0.5 * U_risk.min(axis=1)
        best_score = float(np.max(scores))
    else:
        scores = -(0.5 * U_risk.mean(axis=0) + 0.5 * U_risk.max(axis=0))
        best_score = float(np.max(scores))

    selected_set = set(selected)
    primed_cands: List[tuple[float, int]] = []
    for idx in range(choices_np.shape[0]):
        if idx in selected_set:
            continue
        # Only protect candidates that don't catastrophically lose on Turn 1
        if float(scores[idx]) < best_score - 0.85:
            continue
        is_primed_action = False
        for local_i, mode in primed_slots.items():
            c_val = int(choices_np[idx, local_i])
            if c_val >= 24:
                continue
            r_slot = act_slots[local_i]
            m_idx = (c_val % 12) % 4
            tgt_b = ((c_val % 12) // 4) % 3
            m_vec = m_np[r_slot, m_idx]
            fop_c = int(round(float(m_vec[MoveIdx.FIELD_OP_ID])))
            ws_c = float(m_vec[MoveIdx.WEATHER_SURE_HIT])
            if mode == "tantrum" and tgt_b == 2 and m_vec[MoveIdx.BASE_POWER] > 0.0:
                # Ally-target attack by a Stomping Tantrum / Temper Flare user (intentional ally-immunity priming!)
                is_primed_action = True
                break
            if fop_c in (int(FieldOpID.CHARGE), int(FieldOpID.PHANTOM_FORCE)) or ws_c in (10.0, 20.0, 30.0):
                is_primed_action = True
                break
            if (
                m_vec[MoveIdx.CAT_STATUS] > 0.5
                and m_vec[MoveIdx.STAT_DELTA_SELF] > 0.5
                and float(np.sum(np.maximum(0.0, m_vec[MoveIdx.STAT_DELTA_ATK:MoveIdx.STAT_DELTA_SPE + 1]))) >= 2.0
            ):
                is_primed_action = True
                break
        if is_primed_action:
            primed_cands.append((float(scores[idx]), idx))

    if not primed_cands:
        return selected

    primed_cands.sort(key=lambda x: -x[0])
    out = list(selected)
    for _, cand_idx in primed_cands[:max_primed_inject]:
        out.append(cand_idx)
    return out


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
    max_primed_inject: int = 2,
) -> TwoPlyLookaheadResult:
    """Execute selective 2-Ply Nash lookahead on the Strict-IEDS surviving submatrix
    plus up to `max_primed_inject` reserved 2-turn primed candidate plays per side.
    """
    t0 = time.perf_counter()
    U_blended = np.array(U_risk_ply1, dtype=np.float64, copy=True)
    eval_1, eval_2 = _select_top_core_indices(U_risk_ply1, surv_1_indices, surv_2_indices, max_core_dim)
    eval_1 = _inject_two_turn_primed_candidates(comp, c1_np, U_risk_ply1, eval_1, True, max_primed_inject)
    eval_2 = _inject_two_turn_primed_candidates(comp, c2_np, U_risk_ply1, eval_2, False, max_primed_inject)

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
            M_moves=eot1_prom.M_moves,
            tables=sm.tables,
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
