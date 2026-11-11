# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Phase 5 End-of-Turn, Statistical Risk Evaluator & Unified State Machine
===========================================================================================

Implements Phase 5 (End-of-Turn Resolution), the Per-Thread Board Utility & Downside-Risk
Statistical Aggregator (`Mean`, `Std`, `CVaR_10`, `P5`, `P95`, `KO%`, `Survival%`,
`RiskAdjustedUtility`), and the unified `VgcTensorStateMachine` for Pokémon VGC 4v4
Doubles (Regulation M-C).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from .attack_cascade import (
    AttackCascadeResult,
    execute_attack_cascade,
)
from .compiler import (
    CompiledBattleState,
)
from .logic_engine import (
    LogicalConstraintEngine,
    PrunedSideActionTensorMask,
)
from .phases_pre_attack import (
    ACTIVE_SLOT_NAMES,
    ACTIVE_SLOTS,
    PreAttackPhaseResult,
    T_ELECTRIC,
    T_GRASSY,
    T_MISTY,
    T_NONE,
    T_PSYCHIC,
    W_CLEAR,
    W_RAIN,
    W_SAND,
    W_SNOW,
    W_SUN,
    execute_pre_attack_phases,
)
from .schema_and_tables import (
    BilinearLookupTables,
    FIELD_DIM,
    FieldIdx,
    HAS_TORCH,
    ItemID,
    MON_DIM,
    MOVE_DIM,
    MOVES_PER_MON,
    MonIdx,
    ROSTER_SLOTS,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_1_BENCH1,
    SLOT_TRAINER_1_BENCH2,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    SLOT_TRAINER_2_BENCH1,
    SLOT_TRAINER_2_BENCH2,
    TYPE_TO_IDX,
    build_bilinear_lookup_tables,
)

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray


@dataclass(frozen=True)
class EndOfTurnResult:
    """Outcome of Phase 5 (End-of-Turn Resolution) across `[B1, B2, K]` simulation threads."""

    F: TensorOrArray
    P: TensorOrArray
    M_moves: TensorOrArray
    mean_hp: TensorOrArray
    faint_prob: TensorOrArray
    survival_prob: TensorOrArray
    trainer_1_fainted_count: TensorOrArray
    trainer_2_fainted_count: TensorOrArray
    is_terminal: TensorOrArray
    winner: TensorOrArray  # 0: Incomplete/Draw, 1: trainer_1, 2: trainer_2
    eot_events: List[str]


@dataclass(frozen=True)
class TurnSimulationStatistics:
    """Comprehensive statistical summary across `K` discrete 1-turn simulations per `(i, j)` joint pair.

    Attributes:
        num_simulations: Total number of discrete RNG repetitions `K` simulated per cell.
        risk_aversion_lambda: Weight $\\lambda \\in [0, 1]$ on worst-case tail `CVaR_10`
            in `risk_adjusted_utility = (1 - lambda) * mean_utility + lambda * cvar_10_utility`.
        mean_utility: Expected utility $\\mathbb{E}[U]$ (`[B1, B2]`).
        std_utility: Standard deviation of utility $\\text{Std}[U]$ (`[B1, B2]`).
        cvar_10_utility: Conditional Value at Risk $\\text{CVaR}_{0.10}[U]$ — average utility in
            the worst 10% bad-luck simulations (`[B1, B2]`).
        p5_utility: 5th percentile utility (`[B1, B2]`).
        p95_utility: 95th percentile utility (`[B1, B2]`).
        risk_adjusted_utility: Risk-resilient utility matrix (`[B1, B2]`) for game-theoretic solving.
        win_turn_prob: Empirical probability $P(U > 0)$ that `trainer_1` comes out ahead (`[B1, B2]`).
        faint_prob: Empirical KO probability per roster slot `[B1, B2, 8]`.
        survival_prob: Empirical survival probability per roster slot `[B1, B2, 8]`.
    """

    num_simulations: int
    risk_aversion_lambda: float
    mean_utility: TensorOrArray
    std_utility: TensorOrArray
    cvar_10_utility: TensorOrArray
    p5_utility: TensorOrArray
    p95_utility: TensorOrArray
    risk_adjusted_utility: TensorOrArray
    win_turn_prob: TensorOrArray
    faint_prob: TensorOrArray
    survival_prob: TensorOrArray


@dataclass(frozen=True)
class StepResult:
    """Comprehensive result of a full VGC turn step across `[B1, B2, K]`."""

    F: TensorOrArray
    P: TensorOrArray
    M_moves: TensorOrArray
    pre_attack: PreAttackPhaseResult
    attack_cascade: AttackCascadeResult
    end_of_turn: EndOfTurnResult
    stats: TurnSimulationStatistics
    mean_hp: TensorOrArray
    faint_prob: TensorOrArray
    survival_prob: TensorOrArray
    roll_variance_alert: TensorOrArray
    is_terminal: TensorOrArray
    winner: TensorOrArray


# =============================================================================
# 1. PHASE 5: VECTORIZED END-OF-TURN RESOLUTION (PYTORCH)
# =============================================================================

def _execute_end_of_turn_torch(
    F: "torch.Tensor",             # [B1, B2, K, 24]
    P: "torch.Tensor",             # [B1, B2, K, 8, 84]
    M_moves: "torch.Tensor",       # [B1, B2, K, 8, 4, 56]
    tables: BilinearLookupTables,
    auto_promote: bool = False,
) -> EndOfTurnResult:
    """Pure PyTorch implementation of Phase 5 (End-of-Turn resolution + bench promotions)."""
    F = F.clone()
    P = P.clone()
    M_moves = M_moves.clone()

    device = P.device
    B1, B2, K = P.shape[0], P.shape[1], P.shape[2]
    active_slot_tensor = torch.tensor(ACTIVE_SLOTS, dtype=torch.long, device=device)

    active_hp_cur = P[:, :, :, active_slot_tensor, MonIdx.HP_CUR]
    active_hp_max = P[:, :, :, active_slot_tensor, MonIdx.HP_MAX]
    active_alive = active_hp_cur > 0.0

    # 1. Weather residual damage (Sandstorm: 1/16 max HP to non-Rock/Ground/Steel without Safety Goggles)
    is_sand = (F[:, :, :, FieldIdx.WEATHER_START + W_SAND] > 0.5).unsqueeze(-1)
    t1 = torch.argmax(P[:, :, :, active_slot_tensor, MonIdx.TYPE1_START:MonIdx.TYPE1_END], dim=-1)
    t2 = torch.argmax(P[:, :, :, active_slot_tensor, MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1)
    has_t2 = torch.sum(P[:, :, :, active_slot_tensor, MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1) > 0.5

    rock_idx, ground_idx, steel_idx = TYPE_TO_IDX["rock"], TYPE_TO_IDX["ground"], TYPE_TO_IDX["steel"]
    sand_immune_types = (
        (t1 == rock_idx) | (t1 == ground_idx) | (t1 == steel_idx)
        | (has_t2 & ((t2 == rock_idx) | (t2 == ground_idx) | (t2 == steel_idx)))
    )
    has_goggles = (
        (P[:, :, :, active_slot_tensor, MonIdx.ITEM_ACTIVE] > 0.5)
        & (P[:, :, :, active_slot_tensor, MonIdx.ITEM_ID] == float(ItemID.SAFETY_GOGGLES))
    )
    is_sand_immune = sand_immune_types | has_goggles

    sand_chip = torch.where(
        is_sand & active_alive & (~is_sand_immune),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    active_hp_cur = torch.clamp(active_hp_cur - sand_chip, min=0.0)

    # 2.Terrain & Item Healing (Grassy Terrain +1/16 grounded, Leftovers +1/16, Black Sludge +1/16 Poison)
    is_grassy = (F[:, :, :, FieldIdx.TERRAIN_START + T_GRASSY] > 0.5).unsqueeze(-1)
    is_grounded = P[:, :, :, active_slot_tensor, MonIdx.GROUNDED_FLAG] > 0.5
    grassy_heal = torch.where(
        is_grassy & is_grounded & (active_hp_cur > 0.0) & (active_hp_cur < active_hp_max),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )

    item_act = P[:, :, :, active_slot_tensor, MonIdx.ITEM_ACTIVE] > 0.5
    item_id = P[:, :, :, active_slot_tensor, MonIdx.ITEM_ID]
    has_lefties = item_act & (
        (item_id == float(ItemID.LEFTOVERS)) | (item_id == float(ItemID.BLACK_SLUDGE))
    )
    lefties_heal = torch.where(
        has_lefties & (active_hp_cur > 0.0) & (active_hp_cur < active_hp_max),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    active_hp_cur = torch.clamp(active_hp_cur + grassy_heal + lefties_heal, max=active_hp_max)

    # 3. Status Chip Damage (Burn: 1/16, Poison: 1/8, Toxic: N/16) & Salt Cure / Leech Seed
    is_burned = P[:, :, :, active_slot_tensor, MonIdx.STATUS_BURN] > 0.5
    is_poisoned = P[:, :, :, active_slot_tensor, MonIdx.STATUS_POISON] > 0.5
    is_toxic = P[:, :, :, active_slot_tensor, MonIdx.STATUS_TOXIC] > 0.5

    burn_chip = torch.where(
        is_burned & (active_hp_cur > 0.0),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    poison_chip = torch.where(
        is_poisoned & (active_hp_cur > 0.0),
        torch.clamp(torch.floor(active_hp_max / 8.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )

    toxic_count = torch.clamp(P[:, :, :, active_slot_tensor, MonIdx.TOXIC_COUNTER], min=1.0)
    toxic_chip = torch.where(
        is_toxic & (active_hp_cur > 0.0),
        torch.clamp(torch.floor((active_hp_max * toxic_count) / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    new_toxic_count = torch.where(is_toxic & (active_hp_cur > 0.0), toxic_count + 1.0, toxic_count)
    P[:, :, :, active_slot_tensor, MonIdx.TOXIC_COUNTER] = new_toxic_count

    active_hp_cur = torch.clamp(
        active_hp_cur - burn_chip - poison_chip - toxic_chip, min=0.0
    )

    P[:, :, :, active_slot_tensor, MonIdx.HP_CUR] = active_hp_cur
    P[:, :, :, active_slot_tensor, MonIdx.ALIVE_FLAG] = (active_hp_cur > 0.0).float()

    # 4. Field & Side Counter Decrements
    w_turns = F[:, :, :, FieldIdx.WEATHER_TURNS]
    w_active = w_turns > 0.0
    new_w_turns = torch.clamp(w_turns - 1.0, min=0.0)
    F[:, :, :, FieldIdx.WEATHER_TURNS] = new_w_turns
    w_expired = w_active & (new_w_turns == 0.0)
    if torch.any(w_expired):
        F[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END] = torch.where(
            w_expired.unsqueeze(-1),
            torch.zeros_like(F[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END]),
            F[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END],
        )
        F[:, :, :, FieldIdx.WEATHER_START + W_CLEAR] = torch.where(
            w_expired, torch.ones_like(new_w_turns), F[:, :, :, FieldIdx.WEATHER_START + W_CLEAR]
        )

    t_turns = F[:, :, :, FieldIdx.TERRAIN_TURNS]
    t_active = t_turns > 0.0
    new_t_turns = torch.clamp(t_turns - 1.0, min=0.0)
    F[:, :, :, FieldIdx.TERRAIN_TURNS] = new_t_turns
    t_expired = t_active & (new_t_turns == 0.0)
    if torch.any(t_expired):
        F[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END] = torch.where(
            t_expired.unsqueeze(-1),
            torch.zeros_like(F[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END]),
            F[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END],
        )
        F[:, :, :, FieldIdx.TERRAIN_START + T_NONE] = torch.where(
            t_expired, torch.ones_like(new_t_turns), F[:, :, :, FieldIdx.TERRAIN_START + T_NONE]
        )

    F[:, :, :, FieldIdx.TRICK_ROOM_TURNS] = torch.clamp(F[:, :, :, FieldIdx.TRICK_ROOM_TURNS] - 1.0, min=0.0)
    F[:, :, :, FieldIdx.GRAVITY_TURNS] = torch.clamp(F[:, :, :, FieldIdx.GRAVITY_TURNS] - 1.0, min=0.0)

    for side_idx in (
        FieldIdx.TRAINER_1_TAILWIND_TURNS,
        FieldIdx.TRAINER_1_REFLECT_TURNS,
        FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS,
        FieldIdx.TRAINER_1_AURORA_VEIL_TURNS,
        FieldIdx.TRAINER_2_TAILWIND_TURNS,
        FieldIdx.TRAINER_2_REFLECT_TURNS,
        FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS,
        FieldIdx.TRAINER_2_AURORA_VEIL_TURNS,
    ):
        F[:, :, :, side_idx] = torch.clamp(F[:, :, :, side_idx] - 1.0, min=0.0)

    # 5. Volatile Resets (Flinch, Protect streak, Helping Hand, Taunt, Encore)
    P[:, :, :, active_slot_tensor, MonIdx.FLINCHED] = 0.0
    was_protected = P[:, :, :, active_slot_tensor, MonIdx.PROTECT_ACTIVE] > 0.5
    protect_cnt = P[:, :, :, active_slot_tensor, MonIdx.PROTECT_COUNTER]
    P[:, :, :, active_slot_tensor, MonIdx.PROTECT_COUNTER] = torch.where(
        was_protected, protect_cnt, torch.zeros_like(protect_cnt)
    )
    P[:, :, :, active_slot_tensor, MonIdx.PROTECT_ACTIVE] = 0.0
    P[:, :, :, active_slot_tensor, MonIdx.WIDE_GUARD_ACTIVE] = 0.0
    P[:, :, :, active_slot_tensor, MonIdx.QUICK_GUARD_ACTIVE] = 0.0
    P[:, :, :, active_slot_tensor, MonIdx.HELPING_HAND_MULT] = 1.0
    P[:, :, :, active_slot_tensor, MonIdx.TAUNT_TURNS] = torch.clamp(
        P[:, :, :, active_slot_tensor, MonIdx.TAUNT_TURNS] - 1.0, min=0.0
    )
    P[:, :, :, active_slot_tensor, MonIdx.ENCORE_TURNS] = torch.clamp(
        P[:, :, :, active_slot_tensor, MonIdx.ENCORE_TURNS] - 1.0, min=0.0
    )

    act_turns = P[:, :, :, active_slot_tensor, MonIdx.ACTIVE_TURNS]
    P[:, :, :, active_slot_tensor, MonIdx.ACTIVE_TURNS] = torch.where(
        active_hp_cur > 0.0, act_turns + 1.0, act_turns
    )

    # 5.5 Auto-promotion of alive bench Pokémon into fainted active slots
    if auto_promote:
        for act_s, (b1_s, b2_s) in [
            (0, (2, 3)),
            (1, (2, 3)),
            (4, (6, 7)),
            (5, (6, 7)),
        ]:
            act_dead = P[:, :, :, act_s, MonIdx.HP_CUR] <= 0.0
            b1_alive = P[:, :, :, b1_s, MonIdx.HP_CUR] > 0.0
            b2_alive = P[:, :, :, b2_s, MonIdx.HP_CUR] > 0.0

            promote_b1 = act_dead & b1_alive
            promote_b2 = act_dead & (~b1_alive) & b2_alive

            for prom_mask, bn_s in ((promote_b1, b1_s), (promote_b2, b2_s)):
                if torch.any(prom_mask):
                    act_p = P[:, :, :, act_s, :].clone()
                    bn_p = P[:, :, :, bn_s, :].clone()
                    P[:, :, :, act_s, :] = torch.where(prom_mask.unsqueeze(-1), bn_p, P[:, :, :, act_s, :])
                    P[:, :, :, bn_s, :] = torch.where(prom_mask.unsqueeze(-1), act_p, P[:, :, :, bn_s, :])
                    P[:, :, :, act_s, MonIdx.ACTIVE_TURNS] = torch.where(
                        prom_mask, torch.zeros_like(P[:, :, :, act_s, MonIdx.ACTIVE_TURNS]), P[:, :, :, act_s, MonIdx.ACTIVE_TURNS]
                    )
                    act_m = M_moves[:, :, :, act_s, :, :].clone()
                    bn_m = M_moves[:, :, :, bn_s, :, :].clone()
                    M_moves[:, :, :, act_s, :, :] = torch.where(prom_mask.unsqueeze(-1).unsqueeze(-1), bn_m, M_moves[:, :, :, act_s, :, :])
                    M_moves[:, :, :, bn_s, :, :] = torch.where(prom_mask.unsqueeze(-1).unsqueeze(-1), act_m, M_moves[:, :, :, bn_s, :, :])

    # 6. Match Termination & Empirical Survival / Faint Aggregation
    t1_dead_mask = (P[:, :, :, 0:4, MonIdx.HP_CUR] <= 0.0).float()
    trainer_1_fainted_count = torch.mean(torch.sum(t1_dead_mask, dim=3), dim=2)  # [B1, B2]

    t2_dead_mask = (P[:, :, :, 4:8, MonIdx.HP_CUR] <= 0.0).float()
    trainer_2_fainted_count = torch.mean(torch.sum(t2_dead_mask, dim=3), dim=2)  # [B1, B2]

    t1_wiped = trainer_1_fainted_count >= 4.0
    t2_wiped = trainer_2_fainted_count >= 4.0
    is_terminal = (t1_wiped | t2_wiped).float()

    winner = torch.zeros((B1, B2), dtype=torch.int32, device=device)
    winner = torch.where(t2_wiped & (~t1_wiped), torch.tensor(1, dtype=torch.int32, device=device), winner)
    winner = torch.where(t1_wiped & (~t2_wiped), torch.tensor(2, dtype=torch.int32, device=device), winner)

    mean_hp = torch.mean(P[:, :, :, :, MonIdx.HP_CUR], dim=2)  # [B1, B2, 8]
    faint_prob = torch.mean((P[:, :, :, :, MonIdx.HP_CUR] <= 0.0).float(), dim=2)  # [B1, B2, 8]
    survival_prob = 1.0 - faint_prob

    return EndOfTurnResult(
        F=F,
        P=P,
        M_moves=M_moves,
        mean_hp=mean_hp,
        faint_prob=faint_prob,
        survival_prob=survival_prob,
        trainer_1_fainted_count=trainer_1_fainted_count,
        trainer_2_fainted_count=trainer_2_fainted_count,
        is_terminal=is_terminal,
        winner=winner,
        eot_events=[],
    )


def execute_end_of_turn(
    F_cascade: TensorOrArray,
    P_cascade: TensorOrArray,
    M_cascade: TensorOrArray,
    tables: BilinearLookupTables,
    replacement_choices: Optional[TensorOrArray] = None,
    auto_promote: bool = False,
) -> EndOfTurnResult:
    """Execute Phase 5 (End-of-Turn resolution) across `[B1, B2, K]` simulation threads."""
    do_promote = auto_promote or (replacement_choices is not None)
    is_torch = HAS_TORCH and isinstance(P_cascade, torch.Tensor)
    if is_torch:
        return _execute_end_of_turn_torch(
            F_cascade, P_cascade, M_cascade, tables, auto_promote=do_promote
        )

    if HAS_TORCH:
        dev = torch.device("cpu")
        tables_t = build_bilinear_lookup_tables(device=dev)
        res_t = _execute_end_of_turn_torch(
            torch.from_numpy(np.asarray(F_cascade, dtype=np.float32)),
            torch.from_numpy(np.asarray(P_cascade, dtype=np.float32)),
            torch.from_numpy(np.asarray(M_cascade, dtype=np.float32)),
            tables_t,
            auto_promote=do_promote,
        )
        return EndOfTurnResult(
            F=res_t.F.numpy(),
            P=res_t.P.numpy(),
            M_moves=res_t.M_moves.numpy(),
            mean_hp=res_t.mean_hp.numpy(),
            faint_prob=res_t.faint_prob.numpy(),
            survival_prob=res_t.survival_prob.numpy(),
            trainer_1_fainted_count=res_t.trainer_1_fainted_count.numpy(),
            trainer_2_fainted_count=res_t.trainer_2_fainted_count.numpy(),
            is_terminal=res_t.is_terminal.numpy(),
            winner=res_t.winner.numpy(),
            eot_events=res_t.eot_events,
        )
    raise RuntimeError("PyTorch is required for vectorized tensor execution.")


# =============================================================================
# 2. PER-THREAD BOARD EVALUATOR & RISK-ADJUSTED STATISTICAL AGGREGATOR
# =============================================================================

def compute_per_thread_board_utility_torch(
    F_eot: "torch.Tensor",  # [B1, B2, K, 24]
    P_eot: "torch.Tensor",  # [B1, B2, K, 8, 84]
) -> "torch.Tensor":
    """Evaluate exact scalar board utility $U_{b_1, b_2, k}$ for `trainer_1` vs `trainer_2`
    inside every individual discrete simulation thread `k in 0..K-1`.

    Components of $U_{b_1, b_2, k}$:
    1. **HP Fraction Differential**:
       $\\sum_{s \\in \\{0..3\\}} \\frac{\\text{HP}_{\\text{cur}, s}}{\\text{HP}_{\\text{max}, s}} - \\sum_{s \\in \\{4..7\\}} \\frac{\\text{HP}_{\\text{cur}, s}}{\\text{HP}_{\\text{max}, s}}$
    2. **Alive Count Differential ($0.75$ per surviving Pokémon)**:
       $0.75 \\times (N_{\\text{alive}, \\text{trainer\\_1}} - N_{\\text{alive}, \\text{trainer\\_2}})$
    3. **Terminal Wipe Bonus ($\\pm 2.0$)**:
       $+2.0$ if all 4 `trainer_2` Pokémon fainted; $-2.0$ if all 4 `trainer_1` Pokémon fainted.
    4. **Active Stat Stage & Status Differential**:
       $+0.12$ per net offensive/speed boost stage on alive active slots; $+0.20$ per statused opposing mon.
    5. **Side Speed Control / Screens Differential**:
       $+0.25$ for active Tailwind / Screens advantage.
    """
    hp_cur = P_eot[:, :, :, :, MonIdx.HP_CUR]
    hp_max = torch.clamp(P_eot[:, :, :, :, MonIdx.HP_MAX], min=1.0)
    hp_frac = torch.clamp(hp_cur / hp_max, min=0.0, max=1.0)
    alive = (hp_cur > 0.0).float()

    t1_hp_sum = torch.sum(hp_frac[:, :, :, 0:4], dim=-1)
    t2_hp_sum = torch.sum(hp_frac[:, :, :, 4:8], dim=-1)
    hp_diff = t1_hp_sum - t2_hp_sum

    t1_alive_sum = torch.sum(alive[:, :, :, 0:4], dim=-1)
    t2_alive_sum = torch.sum(alive[:, :, :, 4:8], dim=-1)
    alive_diff = 0.75 * (t1_alive_sum - t2_alive_sum)

    win_bonus = torch.where(t2_alive_sum <= 0.0, torch.full_like(hp_diff, 2.0), torch.zeros_like(hp_diff))
    loss_penalty = torch.where(t1_alive_sum <= 0.0, torch.full_like(hp_diff, 2.0), torch.zeros_like(hp_diff))

    # Active stat boosts (Atk, Def, SpA, SpD, Spe) weighted on alive active slots
    boost_weights = torch.tensor([0.10, 0.06, 0.10, 0.06, 0.12], dtype=torch.float32, device=P_eot.device)
    boosts_5 = P_eot[:, :, :, :, MonIdx.BOOST_ATK:MonIdx.BOOST_SPE + 1]  # [B1, B2, K, 8, 5]
    weighted_boosts = torch.sum(boosts_5 * boost_weights, dim=-1) * alive
    t1_boost_score = weighted_boosts[:, :, :, SLOT_TRAINER_1_A] + weighted_boosts[:, :, :, SLOT_TRAINER_1_B]
    t2_boost_score = weighted_boosts[:, :, :, SLOT_TRAINER_2_A] + weighted_boosts[:, :, :, SLOT_TRAINER_2_B]
    boost_diff = t1_boost_score - t2_boost_score

    # Non-healthy status penalty on alive mons
    statused = (1.0 - P_eot[:, :, :, :, MonIdx.STATUS_HEALTHY]) * alive
    t1_statused = torch.sum(statused[:, :, :, 0:4], dim=-1)
    t2_statused = torch.sum(statused[:, :, :, 4:8], dim=-1)
    status_diff = 0.20 * (t2_statused - t1_statused)

    # Tailwind & Screens advantage
    t1_tw = (F_eot[:, :, :, FieldIdx.TRAINER_1_TAILWIND_TURNS] > 0.0).float()
    t2_tw = (F_eot[:, :, :, FieldIdx.TRAINER_2_TAILWIND_TURNS] > 0.0).float()
    t1_scr = (
        (F_eot[:, :, :, FieldIdx.TRAINER_1_REFLECT_TURNS] > 0.0)
        | (F_eot[:, :, :, FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS] > 0.0)
        | (F_eot[:, :, :, FieldIdx.TRAINER_1_AURORA_VEIL_TURNS] > 0.0)
    ).float()
    t2_scr = (
        (F_eot[:, :, :, FieldIdx.TRAINER_2_REFLECT_TURNS] > 0.0)
        | (F_eot[:, :, :, FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS] > 0.0)
        | (F_eot[:, :, :, FieldIdx.TRAINER_2_AURORA_VEIL_TURNS] > 0.0)
    ).float()
    field_diff = 0.25 * (t1_tw - t2_tw) + 0.15 * (t1_scr - t2_scr)

    return hp_diff + alive_diff + win_bonus - loss_penalty + boost_diff + status_diff + field_diff


def aggregate_simulation_statistics_torch(
    utility_k: "torch.Tensor",     # [B1, B2, K]
    faint_prob: "torch.Tensor",    # [B1, B2, 8]
    risk_aversion_lambda: float = 0.25,
) -> TurnSimulationStatistics:
    """Aggregate `K` discrete simulation utilities into `Mean`, `Std`, `CVaR_10`, `P5`, `P95`,
    `WinTurnProb`, and `RiskAdjustedUtility`.
    """
    K = int(utility_k.shape[-1])
    lam = float(np.clip(risk_aversion_lambda, 0.0, 1.0))

    mean_u = torch.mean(utility_k, dim=-1)
    std_u = torch.std(utility_k, dim=-1, unbiased=False) if K > 1 else torch.zeros_like(mean_u)

    # Sort utility ascending along K to extract exact worst-10% CVaR_10 and P5 / P95 quantiles
    sorted_u, _ = torch.sort(utility_k, dim=-1, descending=False)
    tail_10_count = max(1, int(round(0.10 * K)))
    cvar_10_u = torch.mean(sorted_u[:, :, :tail_10_count], dim=-1)

    idx_p5 = int(np.clip(int(np.floor(0.05 * (K - 1))), 0, K - 1))
    idx_p95 = int(np.clip(int(np.ceil(0.95 * (K - 1))), 0, K - 1))
    p5_u = sorted_u[:, :, idx_p5]
    p95_u = sorted_u[:, :, idx_p95]

    risk_adj_u = (1.0 - lam) * mean_u + lam * cvar_10_u
    win_turn_prob = torch.mean((utility_k > 0.0).float(), dim=-1)
    survival_prob = 1.0 - faint_prob

    return TurnSimulationStatistics(
        num_simulations=K,
        risk_aversion_lambda=lam,
        mean_utility=mean_u,
        std_utility=std_u,
        cvar_10_utility=cvar_10_u,
        p5_utility=p5_u,
        p95_utility=p95_u,
        risk_adjusted_utility=risk_adj_u,
        win_turn_prob=win_turn_prob,
        faint_prob=faint_prob,
        survival_prob=survival_prob,
    )


# =============================================================================
# 3. UNIFIED VGC TENSOR STATE MACHINE (SUPPORTS CHUNKED K=1000+ SIMULATIONS)
# =============================================================================

class VgcTensorStateMachine:
    """Unified High-Level Pokémon VGC 4v4 Doubles State Machine & Multi-Simulation Evaluator.

    Executes complete official Regulation M-C turns across `[B1, B2]` legal joint action pairs
    and `K` parallel discrete-RNG simulation threads:
    Pre-Attack (Barriers 1-3) -> Discrete-RNG Attack Cascade (Phase 4) -> End-of-Turn (Phase 5)
    -> Statistical & Downside-Risk Aggregation (`Mean`, `CVaR_10`, `P5`, `P95`, `RiskAdjustedUtility`).
    """

    def __init__(
        self,
        backend: str = "torch",
        device: Any = None,
        risk_aversion_lambda: float = 0.25,
    ) -> None:
        """Initialize state machine with pre-allocated Bilinear Lookup Tables and Logic Pruner."""
        self.backend = backend
        self.risk_aversion_lambda = float(risk_aversion_lambda)
        if backend == "torch" and HAS_TORCH:
            self.device = device or (
                torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
            )
        else:
            self.backend = "numpy"
            self.device = "cpu"

        self.tables = build_bilinear_lookup_tables(device=self.device)
        self.logic_engine = LogicalConstraintEngine(tables=self.tables)

    def step(
        self,
        F: TensorOrArray,
        P: TensorOrArray,
        M_moves: TensorOrArray,
        trainer_1_choices: Optional[TensorOrArray] = None,
        trainer_2_choices: Optional[TensorOrArray] = None,
        num_mc_samples: int = 256,
        replacement_choices: Optional[TensorOrArray] = None,
        rng_seed: Optional[int] = 42,
        risk_aversion_lambda: Optional[float] = None,
        max_sim_chunk_size: int = 512,
        **kwargs: Any,
    ) -> StepResult:
        """Execute a single VGC Doubles turn across `[B1, B2]` action pairs and `num_mc_samples` discrete RNG threads.

        Automatically chunks execution when `num_mc_samples > max_sim_chunk_size` so you can run
        thousands of simulations (`1024`, `2048`, `4096+`) per joint action pair with bounded VRAM!
        """
        if trainer_1_choices is None:
            trainer_1_choices = kwargs.get("p1_choices")
        if trainer_2_choices is None:
            trainer_2_choices = kwargs.get("p2_choices")
        if trainer_1_choices is None or trainer_2_choices is None:
            raise ValueError("Both trainer_1_choices and trainer_2_choices must be provided.")

        lam = self.risk_aversion_lambda if risk_aversion_lambda is None else float(risk_aversion_lambda)
        seed_base = int(rng_seed if rng_seed is not None else 42)
        K_total = int(max(1, num_mc_samples))
        is_torch_in = HAS_TORCH and isinstance(P, torch.Tensor)

        # 1. Phases 1-3: Pre-Attack Synchronization Barriers (Deterministic given choices, except tie-break order)
        pre_attack_res = execute_pre_attack_phases(
            F_init=F,
            P_init=P,
            M_moves_init=M_moves,
            trainer_1_choices=trainer_1_choices,
            trainer_2_choices=trainer_2_choices,
            tables=self.tables,
            rng_seed=seed_base,
        )

        B1, B2 = pre_attack_res.P.shape[0], pre_attack_res.P.shape[1]
        # Bound total simultaneous simulation threads (B1 * B2 * k_chunk <= 16,384) to cap peak RAM/VRAM
        max_threads_per_chunk = 16384
        effective_chunk_size = max(1, min(int(max_sim_chunk_size), max_threads_per_chunk // max(1, B1 * B2)))

        # If K_total fits in a single chunk, run directly
        if K_total <= effective_chunk_size:
            attack_res = execute_attack_cascade(
                F_init=pre_attack_res.F,
                P_init=pre_attack_res.P,
                M_moves_init=pre_attack_res.M_moves,
                trainer_1_choices=trainer_1_choices,
                trainer_2_choices=trainer_2_choices,
                pre_attack_res=pre_attack_res,
                tables=self.tables,
                num_mc_samples=K_total,
                rng_seed=seed_base,
            )
            eot_res = execute_end_of_turn(
                F_cascade=attack_res.F,
                P_cascade=attack_res.P,
                M_cascade=attack_res.M_moves,
                tables=self.tables,
                replacement_choices=replacement_choices,
            )

            if is_torch_in:
                u_k = compute_per_thread_board_utility_torch(eot_res.F, eot_res.P)
                stats = aggregate_simulation_statistics_torch(u_k, eot_res.faint_prob, lam)
            else:
                u_k_t = compute_per_thread_board_utility_torch(
                    torch.from_numpy(eot_res.F), torch.from_numpy(eot_res.P)
                )
                stats_t = aggregate_simulation_statistics_torch(
                    u_k_t, torch.from_numpy(eot_res.faint_prob), lam
                )
                stats = TurnSimulationStatistics(
                    num_simulations=K_total,
                    risk_aversion_lambda=lam,
                    mean_utility=stats_t.mean_utility.numpy(),
                    std_utility=stats_t.std_utility.numpy(),
                    cvar_10_utility=stats_t.cvar_10_utility.numpy(),
                    p5_utility=stats_t.p5_utility.numpy(),
                    p95_utility=stats_t.p95_utility.numpy(),
                    risk_adjusted_utility=stats_t.risk_adjusted_utility.numpy(),
                    win_turn_prob=stats_t.win_turn_prob.numpy(),
                    faint_prob=eot_res.faint_prob,
                    survival_prob=eot_res.survival_prob,
                )

            return StepResult(
                F=eot_res.F,
                P=eot_res.P,
                M_moves=eot_res.M_moves,
                pre_attack=pre_attack_res,
                attack_cascade=attack_res,
                end_of_turn=eot_res,
                stats=stats,
                mean_hp=eot_res.mean_hp,
                faint_prob=eot_res.faint_prob,
                survival_prob=eot_res.survival_prob,
                roll_variance_alert=attack_res.roll_variance_alert,
                is_terminal=eot_res.is_terminal,
                winner=eot_res.winner,
            )

        # Multi-chunk execution for large K_total (e.g., 1024..10000+ simulations)
        utilities_chunks = []
        mean_hp_accum = None
        faint_prob_accum = None
        t1_faints_accum = None
        t2_faints_accum = None
        mean_dmg_accum = None
        hit_rate_accum = None
        crit_rate_accum = None
        first_attack_res = None
        first_eot_res = None

        remaining = K_total
        chunk_idx = 0
        while remaining > 0:
            k_chunk = min(effective_chunk_size, remaining)
            weight = float(k_chunk) / float(K_total)
            chunk_seed = seed_base + chunk_idx * 100003

            att_c = execute_attack_cascade(
                F_init=pre_attack_res.F,
                P_init=pre_attack_res.P,
                M_moves_init=pre_attack_res.M_moves,
                trainer_1_choices=trainer_1_choices,
                trainer_2_choices=trainer_2_choices,
                pre_attack_res=pre_attack_res,
                tables=self.tables,
                num_mc_samples=k_chunk,
                rng_seed=chunk_seed,
            )
            eot_c = execute_end_of_turn(
                F_cascade=att_c.F,
                P_cascade=att_c.P,
                M_cascade=att_c.M_moves,
                tables=self.tables,
                replacement_choices=replacement_choices,
            )

            if first_attack_res is None:
                first_attack_res = att_c
                first_eot_res = eot_c

            f_t = eot_c.F if is_torch_in else torch.from_numpy(eot_c.F)
            p_t = eot_c.P if is_torch_in else torch.from_numpy(eot_c.P)
            u_c = compute_per_thread_board_utility_torch(f_t, p_t)
            utilities_chunks.append(u_c)

            if mean_hp_accum is None:
                mean_hp_accum = eot_c.mean_hp * weight
                faint_prob_accum = eot_c.faint_prob * weight
                t1_faints_accum = eot_c.trainer_1_fainted_count * weight
                t2_faints_accum = eot_c.trainer_2_fainted_count * weight
                mean_dmg_accum = att_c.mean_damage_dealt * weight
                hit_rate_accum = att_c.hit_rate_observed * weight
                crit_rate_accum = att_c.crit_rate_observed * weight
            else:
                mean_hp_accum = mean_hp_accum + eot_c.mean_hp * weight
                faint_prob_accum = faint_prob_accum + eot_c.faint_prob * weight
                t1_faints_accum = t1_faints_accum + eot_c.trainer_1_fainted_count * weight
                t2_faints_accum = t2_faints_accum + eot_c.trainer_2_fainted_count * weight
                mean_dmg_accum = mean_dmg_accum + att_c.mean_damage_dealt * weight
                hit_rate_accum = hit_rate_accum + att_c.hit_rate_observed * weight
                crit_rate_accum = crit_rate_accum + att_c.crit_rate_observed * weight

            remaining -= k_chunk
            chunk_idx += 1

        u_all_t = torch.cat(utilities_chunks, dim=-1)  # [B1, B2, K_total]
        fp_t = faint_prob_accum if is_torch_in else torch.from_numpy(faint_prob_accum)
        stats_t = aggregate_simulation_statistics_torch(u_all_t, fp_t, lam)

        if is_torch_in:
            roll_var = ((faint_prob_accum > 0.0) & (faint_prob_accum < 1.0)).float()
            surv_prob = 1.0 - faint_prob_accum
            stats = stats_t
        else:
            roll_var = ((faint_prob_accum > 0.0) & (faint_prob_accum < 1.0)).astype(np.float32)
            surv_prob = 1.0 - faint_prob_accum
            stats = TurnSimulationStatistics(
                num_simulations=K_total,
                risk_aversion_lambda=lam,
                mean_utility=stats_t.mean_utility.numpy(),
                std_utility=stats_t.std_utility.numpy(),
                cvar_10_utility=stats_t.cvar_10_utility.numpy(),
                p5_utility=stats_t.p5_utility.numpy(),
                p95_utility=stats_t.p95_utility.numpy(),
                risk_adjusted_utility=stats_t.risk_adjusted_utility.numpy(),
                win_turn_prob=stats_t.win_turn_prob.numpy(),
                faint_prob=faint_prob_accum,
                survival_prob=surv_prob,
            )

        agg_attack_res = AttackCascadeResult(
            F=first_attack_res.F,
            P=first_attack_res.P,
            M_moves=first_attack_res.M_moves,
            mean_hp=mean_hp_accum,
            faint_prob=faint_prob_accum,
            roll_variance_alert=roll_var,
            mean_damage_dealt=mean_dmg_accum,
            hit_rate_observed=hit_rate_accum,
            crit_rate_observed=crit_rate_accum,
            redirection_events=first_attack_res.redirection_events,
        )
        agg_eot_res = EndOfTurnResult(
            F=first_eot_res.F,
            P=first_eot_res.P,
            M_moves=first_eot_res.M_moves,
            mean_hp=mean_hp_accum,
            faint_prob=faint_prob_accum,
            survival_prob=surv_prob,
            trainer_1_fainted_count=t1_faints_accum,
            trainer_2_fainted_count=t2_faints_accum,
            is_terminal=first_eot_res.is_terminal,
            winner=first_eot_res.winner,
            eot_events=first_eot_res.eot_events,
        )

        return StepResult(
            F=agg_eot_res.F,
            P=agg_eot_res.P,
            M_moves=agg_eot_res.M_moves,
            pre_attack=pre_attack_res,
            attack_cascade=agg_attack_res,
            end_of_turn=agg_eot_res,
            stats=stats,
            mean_hp=mean_hp_accum,
            faint_prob=faint_prob_accum,
            survival_prob=surv_prob,
            roll_variance_alert=roll_var,
            is_terminal=agg_eot_res.is_terminal,
            winner=agg_eot_res.winner,
        )

    def simulate_pruned_turn(
        self,
        compiled_state: CompiledBattleState,
        num_simulations: int = 1024,
        min_prior_threshold: float = 0.0,
        rng_seed: int = 42,
        risk_aversion_lambda: Optional[float] = None,
        max_sim_chunk_size: int = 256,
    ) -> Tuple[PrunedSideActionTensorMask, PrunedSideActionTensorMask, StepResult]:
        """Prune `trainer_1` and `trainer_2`'s `26x26` action spaces via `LogicalConstraintEngine`
        down to `[B1_valid, 2]` and `[B2_valid, 2]`, and simulate the `[B1_valid, B2_valid]`
        matchup matrix across `num_simulations` discrete RNG repetitions!
        """
        mask_t1 = self.logic_engine.prune_side_26x26_tensor_actions(
            compiled_state, trainer_id="trainer_1", min_prior_threshold=min_prior_threshold
        )
        mask_t2 = self.logic_engine.prune_side_26x26_tensor_actions(
            compiled_state, trainer_id="trainer_2", min_prior_threshold=min_prior_threshold
        )

        step_res = self.step(
            F=compiled_state.field_tensor,
            P=compiled_state.roster_tensor,
            M_moves=compiled_state.moves_tensor,
            trainer_1_choices=mask_t1.pruned_choices,
            trainer_2_choices=mask_t2.pruned_choices,
            num_mc_samples=num_simulations,
            rng_seed=rng_seed,
            risk_aversion_lambda=risk_aversion_lambda,
            max_sim_chunk_size=max_sim_chunk_size,
        )
        return mask_t1, mask_t2, step_res
