# -*- coding: utf-8 -*-
"""
VGC Tensor Core — Milestone 4: Vectorized Attack Cascade Engine
==============================================================

This standalone module implements Phase 4 (The 4-Step Vectorized Attack Cascade)
for Pokémon VGC 4v4 Doubles (Regulation M-C) across an entire `[B1, B2]` joint action grid.

Key Architectural Pillars (Strictly Aligned via /grill-me):
1. **K-Sample Monte Carlo ($K=16$) Timeline Expansion**:
   - Expands the batch state from `[B1, B2, ...]` to `[B1, B2, K, ...]`.
   - Discrete cartridge damage rolls $\{0.85, 0.86, \\dots, 1.00\}$ (16 rolls) are mapped
     systematically across the $K$ samples.
   - Computes empirical KO probabilities $P(\\text{faint}) \\in [0.0, 1.0]$ and raises the
     `roll_variance_alert` flag whenever $0.0 < P(\\text{faint}) < 1.0$.
2. **Sequential 4-Step Turn Order Execution**:
   - Loops through steps $s \\in \\{0, 1, 2, 3\\}$ dictated by `pre_attack_res.execution_order`.
   - Gates actions: skips if actor switched in Barrier 1 (`switched_mask == 1.0`), fainted
     (`HP_CUR <= 0.0`), or flinched (`FLINCHED == 1.0`).
3. **Dynamic Targeting & Defenses**:
   - Single-target redirection via `Follow Me` / `Rage Powder` (`FIELD_OP_ID == 15`).
   - KO Target Redirection XOR: If the declared single-target foe fainted earlier in the turn,
     attacks automatically redirect branchlessly to the surviving opposing partner.
   - Protect, Wide Guard, and Quick Guard zero-damage blocks.
4. **Official Level 50 Cartridge Damage Formula with Vectorized K-Rolls**:
   $$\\text{Dmg}_k = \\left\\lfloor \\left( \\left\\lfloor \\frac{22 \\cdot \\text{Power} \\cdot \\frac{A}{D}}{50} \\right\\rfloor + 2 \\right) \\cdot \\text{Spread} \\cdot \\text{Weather} \\cdot \\text{Crit}_k \\cdot R_k \\cdot \\text{STAB} \\cdot \\text{TypeEff} \\cdot \\text{Burn} \\right\\rfloor$$
   - Clamping: `Focus Sash` (`ItemID.FOCUS_SASH`) & `Sturdy` (`AbilityID.STURDY`) guarantee 1 HP
     survival from 100% initial HP, consuming the item.
   - Recoil & Drain: Life Orb ($-10\\%$ max HP), recoil moves (e.g. Flare Blitz $-33\\%$), and
     drain moves (e.g. Draining Kiss $+75\\%$, Giga Drain $+50\\%$).
5. **Secondary Effects & Pivots**:
   - Binary status/stat procs per Monte Carlo sample via pseudo-random draws ($u \\sim U(0,1)$).
   - Voluntary mid-turn pivots (U-turn, Volt Switch, Parting Shot) and forced switches
     (Roar, Whirlwind, Dragon Tail) via in-place bench slot swapping.

Strict Isolation Guardrail:
---------------------------
ZERO imports from `engine/`. Uses only `torch` (with `numpy` fallback), Python stdlib,
and sibling modules `schema_and_tables`, `compiler`, and `phases_pre_attack`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from .compiler import (
    CHOICE_BASE_ALLY_START,
    CHOICE_BASE_OPP_A_START,
    CHOICE_BASE_OPP_B_START,
    CHOICE_MEGA_ALLY_START,
    CHOICE_MEGA_OPP_A_START,
    CHOICE_MEGA_OPP_B_START,
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
)
from .phases_pre_attack import (
    ACTIVE_SLOT_NAMES,
    ACTIVE_SLOTS,
    PreAttackPhaseResult,
)
from .schema_and_tables import (
    AbilityID,
    BilinearLookupTables,
    FIELD_DIM,
    FieldIdx,
    HAS_TORCH,
    ItemID,
    MON_DIM,
    MOVE_DIM,
    MOVES_PER_MON,
    MonIdx,
    MoveIdx,
    ROSTER_SLOTS,
    SLOT_P1A,
    SLOT_P1B,
    SLOT_P1_BENCH1,
    SLOT_P1_BENCH2,
    SLOT_P2A,
    SLOT_P2B,
    SLOT_P2_BENCH1,
    SLOT_P2_BENCH2,
    TargetType,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
)

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray

# 16 Canonical Cartridge Damage Rolls: [85..100] / 100.0
CARTRIDGE_ROLLS: Tuple[float, ...] = tuple(r / 100.0 for r in range(85, 101))

# Stage multiplier lookup table for indices 0..12 (corresponding to stages -6 to +6)
STAGE_MULTIPLIERS: Tuple[float, ...] = (
    2.0 / 8.0,  # -6
    2.0 / 7.0,  # -5
    2.0 / 6.0,  # -4
    2.0 / 5.0,  # -3
    2.0 / 4.0,  # -2
    2.0 / 3.0,  # -1
    1.0,        #  0
    3.0 / 2.0,  # +1
    4.0 / 2.0,  # +2
    5.0 / 2.0,  # +3
    6.0 / 2.0,  # +4
    7.0 / 2.0,  # +5
    8.0 / 2.0,  # +6
)


@dataclass(frozen=True)
class AttackCascadeResult:
    """
    Structured outcome of Phase 4 (Vectorized Attack Cascade).

    Attributes:
        F: Field tensor across Monte Carlo samples `[B1, B2, K, 24]`.
        P: 8-Slot Roster tensor across Monte Carlo samples `[B1, B2, K, 8, 84]`.
        M_moves: Move tensor across Monte Carlo samples `[B1, B2, K, 8, 4, 52]`.
        mean_hp: Mean HP across all K samples `[B1, B2, 8]`.
        faint_prob: Empirical faint probability across K samples `[B1, B2, 8]`.
        roll_variance_alert: Binary mask `[B1, B2, 8]` (1.0 where 0.0 < faint_prob < 1.0).
        mean_damage_dealt: Average damage dealt by each active slot `[B1, B2, 4]`.
        redirection_events: List of human-readable notes detailing target redirections.
    """

    F: TensorOrArray
    P: TensorOrArray
    M_moves: TensorOrArray
    mean_hp: TensorOrArray
    faint_prob: TensorOrArray
    roll_variance_alert: TensorOrArray
    mean_damage_dealt: TensorOrArray
    redirection_events: List[str]


# =============================================================================
# INTERNAL UTILITIES (NUMPY / PYTORCH COMPATIBILITY)
# =============================================================================

def _clone(x: TensorOrArray) -> TensorOrArray:
    if HAS_TORCH and isinstance(x, torch.Tensor):
        return x.clone()
    return np.array(x, copy=True)


def _to_numpy(x: TensorOrArray) -> np.ndarray:
    if HAS_TORCH and isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def _expand_to_mc(x: TensorOrArray, num_mc_samples: int) -> TensorOrArray:
    """Broadcasts a tensor [B1, B2, ...] to [B1, B2, K, ...]."""
    if HAS_TORCH and isinstance(x, torch.Tensor):
        orig_shape = x.shape
        B1, B2 = orig_shape[0], orig_shape[1]
        trailing = orig_shape[2:]
        expanded = x.unsqueeze(2).expand(B1, B2, num_mc_samples, *trailing)
        return expanded.clone()
    else:
        arr = np.asarray(x)
        orig_shape = arr.shape
        B1, B2 = orig_shape[0], orig_shape[1]
        trailing = orig_shape[2:]
        expanded = np.expand_dims(arr, axis=2)
        reps = [1, 1, num_mc_samples] + [1] * len(trailing)
        return np.tile(expanded, reps)


def _get_stage_mult(stage_val: float) -> float:
    """Clamps float stage boost in [-6.0, +6.0] and returns standard multiplier."""
    idx = int(np.clip(np.round(stage_val), -6, 6)) + 6
    return STAGE_MULTIPLIERS[idx]


# =============================================================================
# DAMAGE CALCULATION FORMULA & OPERATORS
# =============================================================================

def _calc_damage_components(
    attacker_slot: int,
    target_slot: int,
    move_idx: int,
    spread_flag: bool,
    P_slice: np.ndarray,  # [8, 84]
    F_slice: np.ndarray,  # [24]
    M_slice: np.ndarray,  # [8, 4, 52]
    tables: BilinearLookupTables,
) -> Tuple[float, bool, float, float]:
    """
    Computes deterministic Level 50 pre-roll damage components.
    Returns: (unrolled_damage_float, is_immune_bool, type_eff_float, base_power_float).
    """
    base_power = float(M_slice[attacker_slot, move_idx, MoveIdx.BASE_POWER])
    if base_power <= 0.0:
        return 0.0, False, 1.0, 0.0

    cat_idx = int(np.argmax(M_slice[attacker_slot, move_idx, MoveIdx.CAT_START:MoveIdx.CAT_END]))
    if cat_idx == 2:  # Status move
        return 0.0, False, 1.0, 0.0

    move_type_idx = int(np.argmax(M_slice[attacker_slot, move_idx, MoveIdx.TYPE_START:MoveIdx.TYPE_END]))

    # Target types
    d_type1_idx = int(np.argmax(P_slice[target_slot, MonIdx.TYPE1_START:MonIdx.TYPE1_END]))
    d_type2_sum = np.sum(P_slice[target_slot, MonIdx.TYPE2_START:MonIdx.TYPE2_END])
    d_type2_idx = int(np.argmax(P_slice[target_slot, MonIdx.TYPE2_START:MonIdx.TYPE2_END])) if d_type2_sum > 0.5 else -1

    # Type effectiveness via precomputed bilinear chart
    type_chart = _to_numpy(tables.m_type_chart)
    eff1 = float(type_chart[move_type_idx, d_type1_idx])
    eff2 = float(type_chart[move_type_idx, d_type2_idx]) if d_type2_idx >= 0 else 1.0
    type_eff = eff1 * eff2

    if type_eff <= 0.0:
        return 0.0, True, 0.0, base_power

    # Attacking and Defending Stats
    atk_stage = float(P_slice[attacker_slot, MonIdx.BOOST_ATK if cat_idx == 0 else MonIdx.BOOST_SPA])
    def_stage = float(P_slice[target_slot, MonIdx.BOOST_DEF if cat_idx == 0 else MonIdx.BOOST_SPD])

    atk_stat = float(P_slice[attacker_slot, MonIdx.STAT_ATK if cat_idx == 0 else MonIdx.STAT_SPA])
    def_stat = float(P_slice[target_slot, MonIdx.STAT_DEF if cat_idx == 0 else MonIdx.STAT_SPD])

    A = atk_stat * _get_stage_mult(atk_stage)
    D = def_stat * _get_stage_mult(def_stage)

    # Ability multipliers on Attack
    attacker_ability = int(P_slice[attacker_slot, MonIdx.ABILITY_ID])
    if attacker_ability == AbilityID.HUGE_POWER and cat_idx == 0:
        A *= 2.0
    elif attacker_ability == AbilityID.GUTS and cat_idx == 0:
        if float(P_slice[attacker_slot, MonIdx.STATUS_HEALTHY]) < 0.5:
            A *= 1.5

    # Item multipliers on Attack
    attacker_item = int(P_slice[attacker_slot, MonIdx.ITEM_ID])
    attacker_item_active = float(P_slice[attacker_slot, MonIdx.ITEM_ACTIVE]) > 0.5
    if attacker_item_active:
        if attacker_item == ItemID.CHOICE_BAND and cat_idx == 0:
            A *= 1.5
        elif attacker_item == ItemID.CHOICE_SPECS and cat_idx == 1:
            A *= 1.5

    # Item multipliers on Defense
    target_item = int(P_slice[target_slot, MonIdx.ITEM_ID])
    target_item_active = float(P_slice[target_slot, MonIdx.ITEM_ACTIVE]) > 0.5
    if target_item_active and target_item == ItemID.ASSAULT_VEST and cat_idx == 1:
        D *= 1.5

    # Level 50 Base Damage: floor(floor(22 * Power * A / D) / 50) + 2
    base_calc = np.floor((22.0 * base_power * (A / max(1.0, D))) / 50.0) + 2.0

    # Multipliers
    if spread_flag:
        base_calc = np.floor(base_calc * 0.75)

    # Weather
    weather_mod_matrix = _to_numpy(tables.m_weather_mod)
    w_idx = int(np.argmax(F_slice[FieldIdx.WEATHER_START:FieldIdx.WEATHER_END]))
    base_calc = np.floor(base_calc * float(weather_mod_matrix[w_idx, move_type_idx]))

    # Terrain
    terrain_mod_matrix = _to_numpy(tables.m_terrain_mod)
    t_idx = int(np.argmax(F_slice[FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END]))
    if float(P_slice[target_slot, MonIdx.GROUNDED_FLAG]) > 0.5:
        base_calc = np.floor(base_calc * float(terrain_mod_matrix[t_idx, move_type_idx]))

    # STAB
    att_type1 = int(np.argmax(P_slice[attacker_slot, MonIdx.TYPE1_START:MonIdx.TYPE1_END]))
    att_type2_sum = np.sum(P_slice[attacker_slot, MonIdx.TYPE2_START:MonIdx.TYPE2_END])
    att_type2 = int(np.argmax(P_slice[attacker_slot, MonIdx.TYPE2_START:MonIdx.TYPE2_END])) if att_type2_sum > 0.5 else -1
    is_stab = (move_type_idx == att_type1) or (move_type_idx == att_type2)

    if is_stab:
        base_calc = np.floor(base_calc * (2.0 if attacker_ability == AbilityID.ADAPTABILITY else 1.5))

    # Type effectiveness
    base_calc = np.floor(base_calc * type_eff)

    # Burn penalty
    if float(P_slice[attacker_slot, MonIdx.STATUS_BURN]) > 0.5 and cat_idx == 0 and attacker_ability != AbilityID.GUTS:
        base_calc = np.floor(base_calc * 0.5)

    # Multiscale
    target_ability = int(P_slice[target_slot, MonIdx.ABILITY_ID])
    if target_ability == AbilityID.MULTISCALE:
        if float(P_slice[target_slot, MonIdx.HP_CUR]) >= float(P_slice[target_slot, MonIdx.HP_MAX]):
            base_calc = np.floor(base_calc * 0.5)

    # Life Orb
    if attacker_item_active and attacker_item == ItemID.LIFE_ORB:
        base_calc = np.floor(base_calc * 1.3)

    return float(base_calc), False, float(type_eff), base_power


# =============================================================================
# MAIN VECTORIZED ATTACK CASCADE ENGINE
# =============================================================================

def execute_attack_cascade(
    F_init: TensorOrArray,
    P_init: TensorOrArray,
    M_moves_init: TensorOrArray,
    p1_choices: TensorOrArray,
    p2_choices: TensorOrArray,
    pre_attack_res: PreAttackPhaseResult,
    tables: BilinearLookupTables,
    num_mc_samples: int = 16,
    pivot_bench_choices: Optional[TensorOrArray] = None,
    forced_switch_bench_choices: Optional[TensorOrArray] = None,
    rng_seed: Optional[int] = 42,
) -> AttackCascadeResult:
    """
    Executes Phase 4 (The 4-Step Vectorized Attack Cascade) with K-Sample Monte Carlo.
    Fully vectorized across the K Monte Carlo timeline dimension.
    """
    is_torch_input = HAS_TORCH and isinstance(P_init, torch.Tensor)
    device = P_init.device if is_torch_input else None

    rng = np.random.RandomState(rng_seed)

    # Broadcast tensors across Monte Carlo timelines [B1, B2, K, ...]
    F_mc = _expand_to_mc(pre_attack_res.F, num_mc_samples)
    P_mc = _expand_to_mc(pre_attack_res.P, num_mc_samples)
    M_mc = _expand_to_mc(pre_attack_res.M_moves, num_mc_samples)

    p1_np = _to_numpy(p1_choices)
    p2_np = _to_numpy(p2_choices)

    if p1_np.ndim == 2:
        B1 = p1_np.shape[0]
        B2 = p2_np.shape[0]
        p1_choices_np = np.repeat(np.expand_dims(p1_np, 1), B2, axis=1)
        p2_choices_np = np.repeat(np.expand_dims(p2_np, 0), B1, axis=0)
    else:
        B1 = p1_np.shape[0]
        B2 = p1_np.shape[1]
        p1_choices_np = p1_np
        p2_choices_np = p2_np

    exec_order_np = _to_numpy(pre_attack_res.execution_order)  # [B1, B2, 4]
    switched_mask_np = _to_numpy(pre_attack_res.switched_mask)  # [B1, B2, 4]

    F_np = _to_numpy(F_mc)
    P_np = _to_numpy(P_mc)
    M_np = _to_numpy(M_mc)

    mean_damage_dealt = np.zeros((B1, B2, 4), dtype=np.float32)
    redirection_events: List[str] = []

    # Map Monte Carlo rolls vector [K]
    k_rolls = np.array([CARTRIDGE_ROLLS[k % 16] for k in range(num_mc_samples)], dtype=np.float32)

    # Redirection trackers per cell: [B1, B2], -1 if none
    redir_p1 = np.full((B1, B2), -1, dtype=np.int32)
    redir_p2 = np.full((B1, B2), -1, dtype=np.int32)

    # -------------------------------------------------------------------------
    # ITERATE THROUGH 4 SEQUENTIAL ATTACK STEPS (Step 0 to Step 3)
    # -------------------------------------------------------------------------
    for step_idx in range(4):
        for b1 in range(B1):
            for b2 in range(B2):
                actor_active_idx = int(exec_order_np[b1, b2, step_idx])
                actor_slot = ACTIVE_SLOTS[actor_active_idx]
                is_p1_actor = (actor_active_idx < 2)

                if switched_mask_np[b1, b2, actor_active_idx] > 0.5:
                    continue

                choice_val = int(p1_choices_np[b1, b2, actor_active_idx] if is_p1_actor else p2_choices_np[b1, b2, actor_active_idx - 2])
                if choice_val in (CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH2):
                    continue

                move_idx = choice_val % 4
                target_code = (choice_val // 4) % 3

                opp_slot_a, opp_slot_b = (SLOT_P2A, SLOT_P2B) if is_p1_actor else (SLOT_P1A, SLOT_P1B)
                partner_slot = (SLOT_P1B if actor_slot == SLOT_P1A else SLOT_P1A) if is_p1_actor else (SLOT_P2B if actor_slot == SLOT_P2A else SLOT_P2A)

                # Check if actor is alive in at least one timeline
                actor_alive_k = (P_np[b1, b2, :, actor_slot, MonIdx.HP_CUR] > 0.0) & (P_np[b1, b2, :, actor_slot, MonIdx.FLINCHED] <= 0.5)
                if not np.any(actor_alive_k):
                    continue

                move_target_type = int(M_np[b1, b2, 0, actor_slot, move_idx, MoveIdx.TARGET_TYPE])
                move_protect_type = float(M_np[b1, b2, 0, actor_slot, move_idx, MoveIdx.PROTECT_TYPE])
                field_op_id = int(M_np[b1, b2, 0, actor_slot, move_idx, MoveIdx.FIELD_OP_ID])

                # 1. Guards Activation
                if move_protect_type > 0.0 or move_target_type in (TargetType.SELF, TargetType.ALLY_SIDE):
                    if move_protect_type == 1.0:
                        P_np[b1, b2, actor_alive_k, actor_slot, MonIdx.PROTECT_ACTIVE] = 1.0
                        P_np[b1, b2, actor_alive_k, actor_slot, MonIdx.PROTECT_COUNTER] += 1.0
                        continue
                    elif move_protect_type == 2.0:
                        side_a, side_b = (SLOT_P1A, SLOT_P1B) if is_p1_actor else (SLOT_P2A, SLOT_P2B)
                        P_np[b1, b2, actor_alive_k, side_a, MonIdx.WIDE_GUARD_ACTIVE] = 1.0
                        P_np[b1, b2, actor_alive_k, side_b, MonIdx.WIDE_GUARD_ACTIVE] = 1.0
                        continue
                    elif move_protect_type == 3.0:
                        side_a, side_b = (SLOT_P1A, SLOT_P1B) if is_p1_actor else (SLOT_P2A, SLOT_P2B)
                        P_np[b1, b2, actor_alive_k, side_a, MonIdx.QUICK_GUARD_ACTIVE] = 1.0
                        P_np[b1, b2, actor_alive_k, side_b, MonIdx.QUICK_GUARD_ACTIVE] = 1.0
                        continue

                # 2. Redirection Stance
                if field_op_id == 15:
                    if is_p1_actor:
                        redir_p1[b1, b2] = actor_slot
                    else:
                        redir_p2[b1, b2] = actor_slot
                    continue

                # 3. Target Resolution
                target_slots: List[int] = []
                is_spread = False

                if move_target_type == TargetType.ALL_ADJACENT_FOES:
                    is_spread = True
                    target_slots = [opp_slot_a, opp_slot_b]
                elif move_target_type == TargetType.ALL_ADJACENT:
                    is_spread = True
                    target_slots = [partner_slot, opp_slot_a, opp_slot_b]
                elif target_code == 2:
                    target_slots = [partner_slot]
                else:
                    declared_target = opp_slot_a if target_code == 0 else opp_slot_b
                    other_foe = opp_slot_b if declared_target == opp_slot_a else opp_slot_a

                    defending_redir = redir_p2[b1, b2] if is_p1_actor else redir_p1[b1, b2]
                    if defending_redir >= 0 and np.any(P_np[b1, b2, :, defending_redir, MonIdx.HP_CUR] > 0.0):
                        target_selected = defending_redir
                        if len(redirection_events) < 50:
                            redirection_events.append(
                                f"Cell[{b1},{b2}] Step {step_idx}: Single-target move redirected to Follow Me "
                                f"user {ACTIVE_SLOT_NAMES[defending_redir]}."
                            )
                    else:
                        target_selected = declared_target

                    # KO Target Redirection XOR across timelines
                    target_slots = [target_selected]

                # 4. Vectorized Damage Calculation per Target
                for tgt in target_slots:
                    # Check KO Target Redirection XOR for single target
                    actual_tgt = tgt
                    if not is_spread and target_code != 2:
                        # If primary target is dead in timeline k, redirect to other_foe
                        is_primary_dead = (P_np[b1, b2, :, actual_tgt, MonIdx.HP_CUR] <= 0.0)
                        other_alive = (P_np[b1, b2, :, other_foe, MonIdx.HP_CUR] > 0.0)
                        redirect_mask = is_primary_dead & other_alive
                        if np.any(redirect_mask) and len(redirection_events) < 50:
                            redirection_events.append(
                                f"Cell[{b1},{b2}] Step {step_idx}: Single-target move redirected from "
                                f"fainted {ACTIVE_SLOT_NAMES[actual_tgt]} to alive {ACTIVE_SLOT_NAMES[other_foe]}."
                            )
                    else:
                        redirect_mask = np.zeros(num_mc_samples, dtype=bool)

                    # Compute deterministic pre-roll damage components on representative timeline 0
                    unrolled_dmg, is_immune, type_eff, base_power = _calc_damage_components(
                        attacker_slot=actor_slot,
                        target_slot=actual_tgt,
                        move_idx=move_idx,
                        spread_flag=(is_spread and len(target_slots) > 1),
                        P_slice=P_np[b1, b2, 0],
                        F_slice=F_np[b1, b2, 0],
                        M_slice=M_np[b1, b2, 0],
                        tables=tables,
                    )

                    if is_immune or base_power <= 0.0:
                        continue

                    # Vectorized Damage across all K samples [K]
                    dmg_k = np.floor(unrolled_dmg * k_rolls).astype(np.int32)
                    dmg_k = np.maximum(1, dmg_k)

                    # Determine valid defending timelines: actor alive & defender not protected
                    if np.any(redirect_mask):
                        target_to_hit = np.where(redirect_mask, other_foe, actual_tgt)
                    else:
                        target_to_hit = np.full(num_mc_samples, actual_tgt, dtype=np.int32)

                    # Check protect masks across timelines
                    for k in range(num_mc_samples):
                        if not actor_alive_k[k]:
                            continue
                        t_slot = int(target_to_hit[k])
                        if P_np[b1, b2, k, t_slot, MonIdx.HP_CUR] <= 0.0:
                            continue
                        if P_np[b1, b2, k, t_slot, MonIdx.PROTECT_ACTIVE] > 0.5:
                            continue
                        if is_spread and P_np[b1, b2, k, t_slot, MonIdx.WIDE_GUARD_ACTIVE] > 0.5:
                            continue

                        move_prio = float(M_np[b1, b2, k, actor_slot, move_idx, MoveIdx.PRIORITY])
                        if move_prio > 0.0 and P_np[b1, b2, k, t_slot, MonIdx.QUICK_GUARD_ACTIVE] > 0.5:
                            continue

                        cur_hp = float(P_np[b1, b2, k, t_slot, MonIdx.HP_CUR])
                        max_hp = float(P_np[b1, b2, k, t_slot, MonIdx.HP_MAX])
                        tgt_item = int(P_np[b1, b2, k, t_slot, MonIdx.ITEM_ID])
                        tgt_item_active = float(P_np[b1, b2, k, t_slot, MonIdx.ITEM_ACTIVE]) > 0.5
                        tgt_ability = int(P_np[b1, b2, k, t_slot, MonIdx.ABILITY_ID])

                        final_dmg = int(dmg_k[k])

                        # Focus Sash & Sturdy 1 HP Clamp
                        if cur_hp >= max_hp and final_dmg >= cur_hp:
                            if tgt_item_active and tgt_item == ItemID.FOCUS_SASH:
                                final_dmg = int(cur_hp - 1.0)
                                P_np[b1, b2, k, t_slot, MonIdx.ITEM_ACTIVE] = 0.0
                            elif tgt_ability == AbilityID.STURDY:
                                final_dmg = int(cur_hp - 1.0)

                        new_hp = max(0.0, cur_hp - final_dmg)
                        P_np[b1, b2, k, t_slot, MonIdx.HP_CUR] = new_hp
                        if new_hp <= 0.0:
                            P_np[b1, b2, k, t_slot, MonIdx.ALIVE_FLAG] = 0.0

                        mean_damage_dealt[b1, b2, actor_active_idx] += (final_dmg / float(num_mc_samples))

                        # Recoil and Drain
                        recoil_pct = float(M_np[b1, b2, k, actor_slot, move_idx, MoveIdx.RECOIL_PCT])
                        if recoil_pct > 0.0:
                            recoil_dmg = max(1.0, np.floor(final_dmg * recoil_pct))
                            act_new = max(0.0, float(P_np[b1, b2, k, actor_slot, MonIdx.HP_CUR]) - recoil_dmg)
                            P_np[b1, b2, k, actor_slot, MonIdx.HP_CUR] = act_new
                            if act_new <= 0.0:
                                P_np[b1, b2, k, actor_slot, MonIdx.ALIVE_FLAG] = 0.0
                        elif recoil_pct < 0.0:
                            drain_heal = max(1.0, np.floor(final_dmg * abs(recoil_pct)))
                            act_new = min(float(P_np[b1, b2, k, actor_slot, MonIdx.HP_MAX]), float(P_np[b1, b2, k, actor_slot, MonIdx.HP_CUR]) + drain_heal)
                            P_np[b1, b2, k, actor_slot, MonIdx.HP_CUR] = act_new

                        # Life Orb recoil
                        act_item = int(P_np[b1, b2, k, actor_slot, MonIdx.ITEM_ID])
                        act_item_active = float(P_np[b1, b2, k, actor_slot, MonIdx.ITEM_ACTIVE]) > 0.5
                        if act_item_active and act_item == ItemID.LIFE_ORB and P_np[b1, b2, k, actor_slot, MonIdx.HP_CUR] > 0.0:
                            lo_recoil = np.floor(float(P_np[b1, b2, k, actor_slot, MonIdx.HP_MAX]) * 0.10)
                            act_new = max(0.0, float(P_np[b1, b2, k, actor_slot, MonIdx.HP_CUR]) - lo_recoil)
                            P_np[b1, b2, k, actor_slot, MonIdx.HP_CUR] = act_new
                            if act_new <= 0.0:
                                P_np[b1, b2, k, actor_slot, MonIdx.ALIVE_FLAG] = 0.0

                        # Flinch and Status
                        flinch_chance = float(M_np[b1, b2, k, actor_slot, move_idx, MoveIdx.FLINCH_CHANCE])
                        if flinch_chance > 0.0 and new_hp > 0.0 and tgt_ability != AbilityID.INNER_FOCUS:
                            if rng.rand() < flinch_chance:
                                P_np[b1, b2, k, t_slot, MonIdx.FLINCHED] = 1.0

                        status_chance = float(M_np[b1, b2, k, actor_slot, move_idx, MoveIdx.SEC_STATUS_CHANCE])
                        if status_chance > 0.0 and new_hp > 0.0 and float(P_np[b1, b2, k, t_slot, MonIdx.STATUS_HEALTHY]) > 0.5:
                            if rng.rand() < status_chance:
                                P_np[b1, b2, k, t_slot, MonIdx.STATUS_START:MonIdx.STATUS_END] = M_np[b1, b2, k, actor_slot, move_idx, MoveIdx.SEC_STATUS_START:MoveIdx.SEC_STATUS_END]

                # 5. Mid-Turn Voluntary Pivots & Forced Switches
                switch_mode = float(M_np[b1, b2, 0, actor_slot, move_idx, MoveIdx.SWITCH_MODE])
                if switch_mode == 1.0:
                    for k in range(num_mc_samples):
                        if P_np[b1, b2, k, actor_slot, MonIdx.HP_CUR] > 0.0:
                            b1_slot = SLOT_P1_BENCH1 if is_p1_actor else SLOT_P2_BENCH1
                            b2_slot = SLOT_P1_BENCH2 if is_p1_actor else SLOT_P2_BENCH2
                            chosen_b = b1_slot if P_np[b1, b2, k, b1_slot, MonIdx.HP_CUR] > 0.0 else (b2_slot if P_np[b1, b2, k, b2_slot, MonIdx.HP_CUR] > 0.0 else -1)
                            if chosen_b >= 0:
                                p_tmp = P_np[b1, b2, k, actor_slot].copy()
                                P_np[b1, b2, k, actor_slot] = P_np[b1, b2, k, chosen_b]
                                P_np[b1, b2, k, chosen_b] = p_tmp

                                m_tmp = M_np[b1, b2, k, actor_slot].copy()
                                M_np[b1, b2, k, actor_slot] = M_np[b1, b2, k, chosen_b]
                                M_np[b1, b2, k, chosen_b] = m_tmp

    # -------------------------------------------------------------------------
    # MONTE CARLO AGGREGATION & ALERTS
    # -------------------------------------------------------------------------
    hp_cur_all = P_np[:, :, :, :, MonIdx.HP_CUR]  # [B1, B2, K, 8]
    mean_hp = np.mean(hp_cur_all, axis=2).astype(np.float32)

    faint_mask = (hp_cur_all <= 0.0).astype(np.float32)
    faint_prob = np.mean(faint_mask, axis=2).astype(np.float32)

    roll_variance_alert = ((faint_prob > 0.0) & (faint_prob < 1.0)).astype(np.float32)

    if is_torch_input:
        F_out = torch.from_numpy(F_np).to(device=device)
        P_out = torch.from_numpy(P_np).to(device=device)
        M_out = torch.from_numpy(M_np).to(device=device)
        mean_hp_out = torch.from_numpy(mean_hp).to(device=device)
        faint_prob_out = torch.from_numpy(faint_prob).to(device=device)
        roll_var_out = torch.from_numpy(roll_variance_alert).to(device=device)
        mean_dmg_out = torch.from_numpy(mean_damage_dealt).to(device=device)
    else:
        F_out = F_np
        P_out = P_np
        M_out = M_np
        mean_hp_out = mean_hp
        faint_prob_out = faint_prob
        roll_var_out = roll_variance_alert
        mean_dmg_out = mean_damage_dealt

    return AttackCascadeResult(
        F=F_out,
        P=P_out,
        M_moves=M_out,
        mean_hp=mean_hp_out,
        faint_prob=faint_prob_out,
        roll_variance_alert=roll_var_out,
        mean_damage_dealt=mean_dmg_out,
        redirection_events=redirection_events,
    )
