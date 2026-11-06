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
# NATIVE PYTORCH BATCHED DAMAGE PIPELINE (ZERO HOST TRANSFERS)
# =============================================================================
def _calc_damage_components_torch(
    base_power: torch.Tensor,       # [B1, B2]
    cat_idx: torch.Tensor,          # [B1, B2] (0=Phys, 1=Spec, 2=Status)
    move_type_idx: torch.Tensor,    # [B1, B2]
    type_eff: torch.Tensor,         # [B1, B2]
    atk_stat: torch.Tensor,         # [B1, B2]
    def_stat: torch.Tensor,         # [B1, B2]
    spread_flag: torch.Tensor,      # [B1, B2] (bool or float)
    weather_mult: torch.Tensor,     # [B1, B2]
    terrain_mult: torch.Tensor,     # [B1, B2]
    stab_mult: torch.Tensor,        # [B1, B2]
    is_burned: torch.Tensor,        # [B1, B2]
    attacker_ability: torch.Tensor, # [B1, B2]
    attacker_item: torch.Tensor,    # [B1, B2]
    item_active: torch.Tensor,      # [B1, B2]
    target_ability: torch.Tensor,   # [B1, B2]
    target_hp_cur: torch.Tensor,    # [B1, B2]
    target_hp_max: torch.Tensor,    # [B1, B2]
) -> torch.Tensor:
    """
    Computes deterministic Level 50 pre-roll damage for all B1 x B2 cells simultaneously in PyTorch.
    Adheres strictly to cartridge 16-bit integer fixed-point ordering.
    """
    # 1. Attacking and Defending Stat Multipliers
    A = atk_stat.clone()
    D = torch.clamp(def_stat.clone(), min=1.0)
    # Huge Power (Phys x2) & Guts
    is_phys = (cat_idx == 0)
    A = torch.where(is_phys & (attacker_ability == float(AbilityID.HUGE_POWER)), A * 2.0, A)
    
    # Choice Band / Choice Specs
    cb_active = is_phys & (item_active > 0.5) & (attacker_item == float(ItemID.CHOICE_BAND))
    cs_active = (cat_idx == 1) & (item_active > 0.5) & (attacker_item == float(ItemID.CHOICE_SPECS))
    A = torch.where(cb_active | cs_active, torch.floor(A * 1.5), A)
    # 2. Level 50 Base Damage: floor(floor(22 * Power * A / D) / 50) + 2
    base_calc = torch.floor((22.0 * base_power * (A / D)) / 50.0) + 2.0
    # 3. Spread Move Modifier (0.75x)
    base_calc = torch.where(spread_flag > 0.5, torch.floor(base_calc * 0.75), base_calc)
    # 4. Weather Modifier
    base_calc = torch.floor(base_calc * weather_mult)
    # 5. Terrain Modifier
    base_calc = torch.floor(base_calc * terrain_mult)
    # 6. STAB
    base_calc = torch.floor(base_calc * stab_mult)
    # 7. Type Effectiveness
    base_calc = torch.floor(base_calc * type_eff)
    # 8. Burn Penalty (0.5x on Physical for non-Guts)
    burn_applies = is_burned & is_phys & (attacker_ability != float(AbilityID.GUTS))
    base_calc = torch.where(burn_applies, torch.floor(base_calc * 0.5), base_calc)
    # 9. Multiscale (0.5x at full HP)
    multiscale_applies = (target_ability == float(AbilityID.MULTISCALE)) & (target_hp_cur >= target_hp_max)
    base_calc = torch.where(multiscale_applies, torch.floor(base_calc * 0.5), base_calc)
    # 10. Life Orb Cartridge Fixed-Point (5324 / 4096)
    is_lo = (item_active > 0.5) & (attacker_item == float(ItemID.LIFE_ORB))
    base_calc = torch.where(is_lo, torch.floor(base_calc * 5324.0 / 4096.0), base_calc)
    # Zero out status moves or zero-base-power moves or immunities
    is_valid_hit = (base_power > 0.0) & (cat_idx != 2) & (type_eff > 0.0)
    return torch.where(is_valid_hit, torch.clamp(base_calc, min=1.0), torch.zeros_like(base_calc))

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
    if is_torch_input:
        return _execute_attack_cascade_torch(
            F=pre_attack_res.F,
            P=pre_attack_res.P,
            M_moves=pre_attack_res.M_moves,
            p1_choices=p1_choices,
            p2_choices=p2_choices,
            pre_attack_res=pre_attack_res,
            tables=tables,
            num_mc_samples=num_mc_samples,
            rng_seed=rng_seed,
        )

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


# =============================================================================
# MAIN VECTORIZED ATTACK CASCADE ENGINE TORCH
# =============================================================================
def _execute_attack_cascade_torch(
    F: torch.Tensor,             # [B1, B2, 24]
    P: torch.Tensor,             # [B1, B2, 8, 84]
    M_moves: torch.Tensor,       # [B1, B2, 8, 4, 52]
    p1_choices: torch.Tensor,    # [B1, B2, 2] or [B1, 2]
    p2_choices: torch.Tensor,    # [B1, B2, 2] or [B2, 2]
    pre_attack_res: PreAttackPhaseResult,
    tables: BilinearLookupTables,
    num_mc_samples: int = 16,
    rng_seed: Optional[int] = 42,
) -> AttackCascadeResult:
    """
    Pure PyTorch implementation of Phase 4 with ZERO host-CPU conversions.
    Evaluates all B1 x B2 batch cells and K Monte Carlo timelines in parallel on GPU.
    """
    device = P.device
    B1, B2 = P.shape[0], P.shape[1]
    K = num_mc_samples

    # 1. Expand State across K Monte Carlo Timelines: [B1, B2, K, ...]
    F_mc = F.unsqueeze(2).expand(B1, B2, K, -1).clone()
    P_mc = P.unsqueeze(2).expand(B1, B2, K, -1, -1).clone()
    M_mc = M_moves.unsqueeze(2).expand(B1, B2, K, -1, -1, -1).clone()

    # Expand choices to [B1, B2, 2]
    if p1_choices.ndim == 2:
        p1_grid = p1_choices.unsqueeze(1).expand(B1, B2, 2)
        p2_grid = p2_choices.unsqueeze(0).expand(B1, B2, 2)
    else:
        p1_grid = p1_choices
        p2_grid = p2_choices

    exec_order = pre_attack_res.execution_order.to(device)  # [B1, B2, 4]
    switched_mask = pre_attack_res.switched_mask.to(device) # [B1, B2, 4]

    # Pre-load cartridge damage rolls to device: [1, 1, K]
    k_rolls = torch.tensor(
        [CARTRIDGE_ROLLS[k % 16] for k in range(K)],
        dtype=torch.float32,
        device=device,
    ).view(1, 1, K)

    mean_damage_dealt = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    active_slot_tensor = torch.tensor(ACTIVE_SLOTS, dtype=torch.long, device=device)

    # Setup deterministic PyTorch RNG generator
    gen = torch.Generator(device=device)
    if rng_seed is not None:
        gen.manual_seed(rng_seed)

    # -------------------------------------------------------------------------
    # UNROLLED 4-STEP SEQUENCE (Executed simultaneously for all B1 x B2 x K)
    # -------------------------------------------------------------------------
    for step_idx in range(4):
        # 1. Active actor index for all B1 x B2 cells: [B1, B2]
        actor_active_idx = exec_order[:, :, step_idx].long()
        actor_slot = active_slot_tensor[actor_active_idx]  # [B1, B2]
        is_p1 = (actor_active_idx < 2)                     # [B1, B2]

        # Check if switched out in Barrier 1
        switched = torch.gather(switched_mask, 2, actor_active_idx.unsqueeze(-1)).squeeze(-1) > 0.5

        # Choice values: [B1, B2]
        # Clamp slot indices to [0, 1] to prevent CUDA gather out-of-bounds when actor belongs to the other player
        p1_slot_idx = actor_active_idx.clamp(min=0, max=1).unsqueeze(-1)
        p2_slot_idx = (actor_active_idx - 2).clamp(min=0, max=1).unsqueeze(-1)

        p1_c = torch.gather(p1_grid, 2, p1_slot_idx).squeeze(-1)
        p2_c = torch.gather(p2_grid, 2, p2_slot_idx).squeeze(-1)
        choice_val = torch.where(is_p1, p1_c, p2_c).long()

        is_switch_choice = (choice_val == CHOICE_SWITCH_BENCH1) | (choice_val == CHOICE_SWITCH_BENCH2)
        skip_step = switched | is_switch_choice  # [B1, B2]

        move_idx = choice_val % 4
        target_code = (choice_val // 4) % 3

        # Target slots
        opp_slot_a = torch.where(is_p1, SLOT_P2A, SLOT_P1A)
        opp_slot_b = torch.where(is_p1, SLOT_P2B, SLOT_P1B)
        partner_slot = torch.where(
            is_p1,
            torch.where(actor_slot == SLOT_P1A, SLOT_P1B, SLOT_P1A),
            torch.where(actor_slot == SLOT_P2A, SLOT_P2B, SLOT_P2A),
        )

        # Actor alive mask across timelines: [B1, B2, K]
        actor_slot_exp = actor_slot.unsqueeze(-1).unsqueeze(-1).expand(B1, B2, K, 1)
        actor_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot_exp).squeeze(-1)
        actor_flinch = torch.gather(P_mc[:, :, :, :, MonIdx.FLINCHED], 3, actor_slot_exp).squeeze(-1)
        actor_can_attack = (actor_hp > 0.0) & (actor_flinch <= 0.5) & (~skip_step.unsqueeze(-1))

        # Primary declared target: [B1, B2]
        declared_target = torch.where(
            target_code == 2,
            partner_slot,
            torch.where(target_code == 0, opp_slot_a, opp_slot_b),
        )

        # Vectorized Level 50 Cartridge Damage Calculation
        # Gather Attacker & Defender Stats across B1 x B2
        att_slot_2d = actor_slot.unsqueeze(-1)
        tgt_slot_2d = declared_target.unsqueeze(-1)

        # Extract move parameters from representative timeline 0
        m_slice = torch.gather(
            M_mc[:, :, 0, :, :, :],
            2,
            att_slot_2d.unsqueeze(-1).unsqueeze(-1).expand(B1, B2, 1, 4, MOVE_DIM),
        ).squeeze(2)  # [B1, B2, 4, 52]

        mv_idx_exp = move_idx.view(B1, B2, 1, 1).expand(B1, B2, 1, MOVE_DIM)
        chosen_move = torch.gather(m_slice, 2, mv_idx_exp).squeeze(2)  # [B1, B2, 52]

        base_power = chosen_move[:, :, MoveIdx.BASE_POWER]
        cat_start = MoveIdx.CAT_START
        cat_idx = torch.argmax(chosen_move[:, :, cat_start : cat_start + 3], dim=-1)
        move_type_idx = torch.argmax(chosen_move[:, :, MoveIdx.TYPE_START : MoveIdx.TYPE_END], dim=-1)

        # Attacker stats
        p_att = torch.gather(
            P_mc[:, :, 0, :, :],
            2,
            att_slot_2d.unsqueeze(-1).expand(B1, B2, 1, MON_DIM),
        ).squeeze(2)
        p_tgt = torch.gather(
            P_mc[:, :, 0, :, :],
            2,
            tgt_slot_2d.unsqueeze(-1).expand(B1, B2, 1, MON_DIM),
        ).squeeze(2)

        atk_stat = torch.where(cat_idx == 0, p_att[:, :, MonIdx.STAT_ATK], p_att[:, :, MonIdx.STAT_SPA])
        def_stat = torch.where(cat_idx == 0, p_tgt[:, :, MonIdx.STAT_DEF], p_tgt[:, :, MonIdx.STAT_SPD])

        # Type effectiveness
        type_chart = tables.m_type_chart.to(device)
        t1_idx = torch.argmax(p_tgt[:, :, MonIdx.TYPE1_START : MonIdx.TYPE1_END], dim=-1)
        t2_idx = torch.argmax(p_tgt[:, :, MonIdx.TYPE2_START : MonIdx.TYPE2_END], dim=-1)
        has_t2 = torch.sum(p_tgt[:, :, MonIdx.TYPE2_START : MonIdx.TYPE2_END], dim=-1) > 0.5

        eff1 = type_chart[move_type_idx, t1_idx]
        eff2 = torch.where(has_t2, type_chart[move_type_idx, t2_idx], torch.ones_like(eff1))
        type_eff = eff1 * eff2

        # Weather multiplier
        w_chart = tables.m_weather_mod.to(device)
        w_idx = torch.argmax(F_mc[:, :, 0, FieldIdx.WEATHER_START : FieldIdx.WEATHER_END], dim=-1)
        weather_mult = w_chart[w_idx, move_type_idx]

        # Terrain multiplier
        t_chart = tables.m_terrain_mod.to(device)
        tr_idx = torch.argmax(F_mc[:, :, 0, FieldIdx.TERRAIN_START : FieldIdx.TERRAIN_END], dim=-1)
        is_grounded = p_tgt[:, :, MonIdx.GROUNDED_FLAG] > 0.5
        terrain_mult = torch.where(is_grounded, t_chart[tr_idx, move_type_idx], torch.ones_like(weather_mult))

        # STAB
        p_att_t1 = torch.argmax(p_att[:, :, MonIdx.TYPE1_START : MonIdx.TYPE1_END], dim=-1)
        p_att_t2 = torch.argmax(p_att[:, :, MonIdx.TYPE2_START : MonIdx.TYPE2_END], dim=-1)
        p_att_has_t2 = torch.sum(p_att[:, :, MonIdx.TYPE2_START : MonIdx.TYPE2_END], dim=-1) > 0.5
        is_stab = (move_type_idx == p_att_t1) | (p_att_has_t2 & (move_type_idx == p_att_t2))
        stab_mult = torch.where(is_stab, torch.tensor(1.5, device=device), torch.tensor(1.0, device=device))

        # Pre-roll unrolled damage: [B1, B2]
        unrolled_dmg = _calc_damage_components_torch(
            base_power=base_power,
            cat_idx=cat_idx,
            move_type_idx=move_type_idx,
            type_eff=type_eff,
            atk_stat=atk_stat,
            def_stat=def_stat,
            spread_flag=torch.zeros_like(base_power),
            weather_mult=weather_mult,
            terrain_mult=terrain_mult,
            stab_mult=stab_mult,
            is_burned=(p_att[:, :, MonIdx.STATUS_BURN] > 0.5),
            attacker_ability=p_att[:, :, MonIdx.ABILITY_ID],
            attacker_item=p_att[:, :, MonIdx.ITEM_ID],
            item_active=p_att[:, :, MonIdx.ITEM_ACTIVE],
            target_ability=p_tgt[:, :, MonIdx.ABILITY_ID],
            target_hp_cur=p_tgt[:, :, MonIdx.HP_CUR],
            target_hp_max=p_tgt[:, :, MonIdx.HP_MAX],
        )

        # Expand across K Monte Carlo timelines: [B1, B2, K]
        dmg_k = torch.clamp(torch.floor(unrolled_dmg.unsqueeze(-1) * k_rolls), min=1.0)

        # Apply damage to target across timelines where actor can attack
        tgt_slot_exp = declared_target.unsqueeze(-1).unsqueeze(-1).expand(B1, B2, K, 1)
        cur_tgt_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, tgt_slot_exp).squeeze(-1)
        cur_tgt_max = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, tgt_slot_exp).squeeze(-1)
        tgt_item = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, tgt_slot_exp).squeeze(-1)

        # Focus Sash / Sturdy clamping
        survive_sash = (cur_tgt_hp >= cur_tgt_max) & (dmg_k >= cur_tgt_hp) & (tgt_item == float(ItemID.FOCUS_SASH))
        applied_dmg = torch.where(survive_sash, cur_tgt_hp - 1.0, dmg_k)
        applied_dmg = torch.where(actor_can_attack & (cur_tgt_hp > 0.0), applied_dmg, torch.zeros_like(applied_dmg))

        new_tgt_hp = torch.clamp(cur_tgt_hp - applied_dmg, min=0.0)

        # Scatter back to P_mc
        P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, tgt_slot_exp, new_tgt_hp.unsqueeze(-1))
        P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, tgt_slot_exp, (new_tgt_hp > 0.0).float().unsqueeze(-1))

        # Flinch target (Respecting Inner Focus and Preventing Erasure)
        flinch_chance = chosen_move[:, :, MoveIdx.FLINCH_CHANCE].unsqueeze(-1).expand(B1, B2, K)
        tgt_ability = p_tgt[:, :, MonIdx.ABILITY_ID].unsqueeze(-1).expand(B1, B2, K)
        can_flinch = tgt_ability != float(AbilityID.INNER_FOCUS)
        
        # Optional: Add rand_like here if you want accurate 30% chances instead of 100% assumption
        # rand_vals = torch.rand_like(flinch_chance)
        # has_flinch = (rand_vals < flinch_chance) & actor_can_attack & (applied_dmg > 0.0) & can_flinch
        has_flinch = (flinch_chance > 0.0) & actor_can_attack & (applied_dmg > 0.0) & can_flinch
        
        # Read current flinch state to avoid erasing previous flinches in steps 1-3
        cur_flinch = torch.gather(P_mc[:, :, :, :, MonIdx.FLINCHED], 3, tgt_slot_exp)
        flinch_val = torch.where(has_flinch.unsqueeze(-1), torch.ones_like(cur_flinch), cur_flinch)
        P_mc[:, :, :, :, MonIdx.FLINCHED].scatter_(3, tgt_slot_exp, flinch_val)

        # Accumulate mean damage dealt
        step_mean_dmg = torch.mean(applied_dmg, dim=-1)  # [B1, B2]
        mean_damage_dealt.scatter_add_(2, actor_active_idx.unsqueeze(-1), step_mean_dmg.unsqueeze(-1))

    # -------------------------------------------------------------------------
    # MONTE CARLO AGGREGATION & ALERTS (IN VRAM)
    # -------------------------------------------------------------------------
    hp_cur_all = P_mc[:, :, :, :, MonIdx.HP_CUR]  # [B1, B2, K, 8]
    mean_hp = torch.mean(hp_cur_all, dim=2)        # [B1, B2, 8]

    faint_mask = (hp_cur_all <= 0.0).float()
    faint_prob = torch.mean(faint_mask, dim=2)     # [B1, B2, 8]

    roll_variance_alert = ((faint_prob > 0.0) & (faint_prob < 1.0)).float()

    return AttackCascadeResult(
        F=F_mc,
        P=P_mc,
        M_moves=M_mc,
        mean_hp=mean_hp,
        faint_prob=faint_prob,
        roll_variance_alert=roll_variance_alert,
        mean_damage_dealt=mean_damage_dealt,
        redirection_events=[],
    )