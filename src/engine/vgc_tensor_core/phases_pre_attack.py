# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Phases 1–3 Pre-Attack Vectorized Synchronization Engine
===========================================================================

Implements the first three synchronization barriers of an official Pokémon VGC 4v4
Doubles turn (Regulation M-C) across a `[B1, B2]` joint action grid (`trainer_1` vs `trainer_2`)
using pure matrix/tensor operations:

1. **Optional Lead Entry Ability Pass (`resolve_lead_entry_abilities=True`)**:
   - Sorts all 4 initial active leads (`0: trainer_1_a`, `1: trainer_1_b`, `4: trainer_2_a`, `5: trainer_2_b`)
     by `TrickRoomSign * EffectiveSpeed` and fires their switch-in abilities (`Weather`, `Terrain`,
     `Intimidate -> Defiant/Competitive`, `Hospitality`) before Turn 1 choices execute.
2. **Phase 1 — Barrier 1: Voluntary Switches & Speed-Ordered Switch-In Abilities (`+6`)**:
   - Resets outgoing stat boosts (`8..14`) and volatile states (`58..66`) on switching active slots
     via Hadamard multiplication with `tables.switch_persist_mask`.
   - Swaps the active slot and bench slot in both Roster Tensor `P` (`[..., 8, 84]`) and Move Tensor
     `M_moves` (`[..., 8, 4, 56]`).
   - Sorts all newly switched-in slots by `TrickRoomSign * EffectiveSpeed` and fires their entry abilities.
3. **Phase 2 — Barrier 2: Mega Evolution & Instantaneous Speed/Type/Ability Recalibration (`+5.5`)**:
   - Identifies active slots choosing Mega Evolution (`choice_idx in 12..23`) that have
     `CAN_MEGA == 1.0`, `IS_MEGA == 0.0`, and `SIDE_MEGA_USED == 0.0`.
   - Transforms all 5 Level-50 stats (`STAT_ATK..STAT_SPE` <- `MEGA_ATK..MEGA_SPE`), updates secondary typing
     (`TYPE2_START..TYPE2_END` <- `MEGA_TYPE_START..MEGA_TYPE_END` when present), updates
     `ABILITY_ID` <- `MEGA_ABILITY_ID`, sets `IS_MEGA = 1.0`, `CAN_MEGA = 0.0`, and locks
     `TRAINER_1_MEGA_USED` / `TRAINER_2_MEGA_USED = 1.0`.
   - Sorts newly Mega-Evolved slots by their post-Mega `TrickRoomSign * EffectiveSpeed` and fires Mega
     entry abilities (`Charizard-Mega-Y` Drought, `Raichu-Mega-X` Electric Surge, `Manectric-Mega` /
     `Gyarados-Mega` Intimidate, etc.).
4. **Phase 3 — Barrier 3: Effective Speed, Priority Bracket & Per-Thread Spinning-Wheel Speed-Tie Sort**:
   - Computes Effective Speed $S_{\text{eff}}$ accounting for stat stage ratio, `Tailwind` ($2.0\times$),
     `Paralysis` ($0.5\times$), `Choice Scarf` ($1.5\times$), `Unburden` ($2.0\times$), and weather speed
     abilities (`Swift Swim`, `Chlorophyll`, `Sand Rush`, `Slush Rush` $2.0\times$).
   - Computes Effective Priority $p_{\text{eff}}$ accounting for Switch priority (`+6.0`),
     `Prankster` ($+1.0$ on Status moves), and `Grassy Glide` ($+1.0$ when Grounded in Grassy Terrain).
   - Detects exact intra-bracket speed ties (`speed_tie_alert [B1, B2]`) and generates both deterministic
     baseline `execution_order [B1, B2, 4]` and per-simulation-thread `execution_order_k [B1, B2, K, 4]`
     where every tied pair is resolved via a 50/50 Dual-Draw Spinning-Wheel coinflip per thread `k`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from .compiler import (
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
)
from .rng_engine import (
    RNGEventID,
    counter_uniform_0_100_numpy,
    counter_uniform_0_100_torch,
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
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_1_BENCH1,
    SLOT_TRAINER_1_BENCH2,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    SLOT_TRAINER_2_BENCH1,
    SLOT_TRAINER_2_BENCH2,
    TERRAIN_TO_IDX,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
)

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray


W_CLEAR: int = WEATHER_TO_IDX["clear"]      # 0
W_SUN: int = WEATHER_TO_IDX["sun"]          # 1
W_RAIN: int = WEATHER_TO_IDX["rain"]        # 2
W_SAND: int = WEATHER_TO_IDX["sand"]        # 3
W_SNOW: int = WEATHER_TO_IDX["snow"]        # 4

T_NONE: int = TERRAIN_TO_IDX["none"]          # 0
T_ELECTRIC: int = TERRAIN_TO_IDX["electric"]  # 1
T_GRASSY: int = TERRAIN_TO_IDX["grassy"]      # 2
T_PSYCHIC: int = TERRAIN_TO_IDX["psychic"]    # 3
T_MISTY: int = TERRAIN_TO_IDX["misty"]        # 4

ACTIVE_SLOTS: Tuple[int, int, int, int] = (
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
)
ACTIVE_SLOT_NAMES: Dict[int, str] = {
    SLOT_TRAINER_1_A: "trainer_1_a(Slot0)",
    SLOT_TRAINER_1_B: "trainer_1_b(Slot1)",
    SLOT_TRAINER_2_A: "trainer_2_a(Slot4)",
    SLOT_TRAINER_2_B: "trainer_2_b(Slot5)",
}


@dataclass(frozen=True)
class PreAttackPhaseResult:
    """Structured output of Phases 1–3 (`execute_pre_attack_phases`) across a `[B1, B2]` action grid.

    Attributes:
        F: Updated Field Tensor of shape `[B1, B2, 24]`.
        P: Updated 8-Slot Roster Tensor of shape `[B1, B2, 8, 84]`.
        M_moves: Updated 8-Slot Move Tensor of shape `[B1, B2, 8, 4, 56]`.
        effective_speeds: Effective Speed tensor for the 4 active slots `[B1, B2, 4]`
            ordered as `(trainer_1_a=0, trainer_1_b=1, trainer_2_a=4, trainer_2_b=5)`.
        effective_priorities: Effective Move/Action Priority tensor `[B1, B2, 4]`.
        jitter_applied: Representative tie-break jitter tensor `[B1, B2, 4]`.
        sort_scores: Composite turn-order sort keys `[B1, B2, 4]`.
        execution_order: Integer permutation tensor `[B1, B2, 4]` with values in `{0, 1, 2, 3}`
            (mapping to active slots `(0, 1, 4, 5)`) for representative timeline 0.
        switched_mask: Binary mask `[B1, B2, 4]` (`1.0` where active slot `k` voluntarily switched).
        mega_evolved_mask: Binary mask `[B1, B2, 4]` (`1.0` where active slot `k` Mega Evolved).
        speed_tie_alert: Binary mask `[B1, B2]` (`1.0` where at least two active slots shared
            identical priority and effective speed).
        speed_tie_notes: Human-readable list of speed tie alerts and tie-break resolutions.
    """

    F: TensorOrArray
    P: TensorOrArray
    M_moves: TensorOrArray
    effective_speeds: TensorOrArray
    effective_priorities: TensorOrArray
    jitter_applied: TensorOrArray
    sort_scores: TensorOrArray
    execution_order: TensorOrArray
    switched_mask: TensorOrArray
    mega_evolved_mask: TensorOrArray
    speed_tie_alert: TensorOrArray
    speed_tie_notes: List[str]


# =====================================================================
# 1. TENSOR HELPER UTILITIES (TORCH CUDA/CPU & NUMPY)
# =====================================================================

def _clone(x: TensorOrArray) -> TensorOrArray:
    if HAS_TORCH and isinstance(x, torch.Tensor):
        return x.clone()
    return np.array(x, copy=True)


def _clamp(x: TensorOrArray, min_val: float, max_val: float) -> TensorOrArray:
    if HAS_TORCH and isinstance(x, torch.Tensor):
        return torch.clamp(x, min=min_val, max=max_val)
    return np.clip(x, min_val, max_val).astype(np.float32)


def _floor(x: TensorOrArray) -> TensorOrArray:
    if HAS_TORCH and isinstance(x, torch.Tensor):
        return torch.floor(x)
    return np.floor(x).astype(np.float32)


def _matmul(a: TensorOrArray, b: TensorOrArray) -> TensorOrArray:
    if HAS_TORCH and isinstance(a, torch.Tensor):
        return torch.matmul(a, b)
    return np.matmul(a, b)


def _einsum(equation: str, *operands: TensorOrArray) -> TensorOrArray:
    if HAS_TORCH and isinstance(operands[0], torch.Tensor):
        return torch.einsum(equation, *operands)
    return np.einsum(equation, *operands)


def _argsort_desc(scores: TensorOrArray, axis: int = -1) -> TensorOrArray:
    if HAS_TORCH and isinstance(scores, torch.Tensor):
        return torch.argsort(scores, dim=axis, descending=True)
    return np.argsort(-scores, axis=axis)


# =====================================================================
# 2. VECTORIZED EFFECTIVE SPEED ENGINE
# =====================================================================

def compute_active_effective_speeds(
    F: TensorOrArray,
    P: TensorOrArray,
) -> TensorOrArray:
    """Compute exact Cartridge Level-50 Effective Speed $S_{\\text{eff}}$ for the 4 active slots
    (`0: trainer_1_a`, `1: trainer_1_b`, `4: trainer_2_a`, `5: trainer_2_b`) across `[..., 4]`.
    """
    active_indices = [SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_2_A, SLOT_TRAINER_2_B]
    P_act = P[..., active_indices, :]  # [..., 4, 84]

    base_spe = P_act[..., MonIdx.STAT_SPE]
    boost_spe = _clamp(P_act[..., MonIdx.BOOST_SPE], -6.0, 6.0)

    if HAS_TORCH and isinstance(P, torch.Tensor):
        two = torch.tensor(2.0, dtype=torch.float32, device=P.device)
        num = torch.maximum(two, two + boost_spe)
        den = torch.maximum(two, two - boost_spe)
    else:
        num = np.maximum(2.0, 2.0 + boost_spe)
        den = np.maximum(2.0, 2.0 - boost_spe)

    s1 = _floor(base_spe * (num / den))

    # Weather speed abilities: Swift Swim (Rain), Chlorophyll (Sun), Sand Rush (Sand), Slush Rush (Snow)
    abil_id = P_act[..., MonIdx.ABILITY_ID]
    w_sun = F[..., FieldIdx.WEATHER_START + W_SUN][..., None]
    w_rain = F[..., FieldIdx.WEATHER_START + W_RAIN][..., None]
    w_sand = F[..., FieldIdx.WEATHER_START + W_SAND][..., None]
    w_snow = F[..., FieldIdx.WEATHER_START + W_SNOW][..., None]

    is_chlorophyll = ((abil_id == float(AbilityID.CHLOROPHYLL)) * 1.0) * w_sun
    is_swift_swim = ((abil_id == float(AbilityID.SWIFT_SWIM)) * 1.0) * w_rain
    is_sand_rush = ((abil_id == float(AbilityID.SAND_RUSH)) * 1.0) * w_sand
    is_slush_rush = ((abil_id == float(AbilityID.SLUSH_RUSH)) * 1.0) * w_snow

    weather_spe_gate = _clamp(
        is_chlorophyll + is_swift_swim + is_sand_rush + is_slush_rush, 0.0, 1.0
    )
    unburden_gate = P_act[..., MonIdx.UNBURDEN_ACTIVE]
    m_abil = (1.0 + weather_spe_gate) * (1.0 + unburden_gate)
    s2 = _floor(s1 * m_abil)

    # Choice Scarf (1.5x when item_active == 1.0)
    item_active = P_act[..., MonIdx.ITEM_ACTIVE]
    is_scarf = ((P_act[..., MonIdx.ITEM_ID] == float(ItemID.CHOICE_SCARF)) * 1.0) * item_active
    m_item = 1.0 + 0.5 * is_scarf
    s3 = _floor(s2 * m_item)

    # Side Tailwind (Slots 0,1 use TRAINER_1_TAILWIND_TURNS; Slots 2,3 use TRAINER_2_TAILWIND_TURNS)
    t1_tw = (F[..., FieldIdx.TRAINER_1_TAILWIND_TURNS] > 0.0) * 1.0
    t2_tw = (F[..., FieldIdx.TRAINER_2_TAILWIND_TURNS] > 0.0) * 1.0
    if HAS_TORCH and isinstance(F, torch.Tensor):
        tw_vec = torch.stack([t1_tw, t1_tw, t2_tw, t2_tw], dim=-1)
    else:
        tw_vec = np.stack([t1_tw, t1_tw, t2_tw, t2_tw], axis=-1).astype(np.float32)

    m_tw = 1.0 + tw_vec
    s4 = _floor(s3 * m_tw)

    # Paralysis (0.5x when STATUS_PARALYZE == 1.0)
    is_para = P_act[..., MonIdx.STATUS_PARALYZE]
    m_para = 1.0 - 0.5 * is_para
    s_eff = _floor(s4 * m_para)

    return s_eff


# =====================================================================
# 3. SPEED-ORDERED ENTRY ABILITY ENGINE (WEATHER, TERRAIN, INTIMIDATE)
# =====================================================================

def _execute_speed_sorted_entry_abilities(
    F: TensorOrArray,
    P: TensorOrArray,
    trigger_mask: TensorOrArray,
    tables: BilinearLookupTables,
) -> Tuple[TensorOrArray, TensorOrArray]:
    """Execute entry abilities (`Weather`, `Terrain`, `Intimidate -> Defiant/Competitive`, `Hospitality`)
    for any active slots (`0: trainer_1_a`, `1: trainer_1_b`, `2: trainer_2_a(slot 4)`, `3: trainer_2_b(slot 5)`)
    where `trigger_mask[..., k] == 1.0`, sorted by `TrickRoomSign * EffectiveSpeed`.
    """
    active_roster_slots = (SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_2_A, SLOT_TRAINER_2_B)
    eff_speeds = compute_active_effective_speeds(F, P)  # [..., 4]

    tr_active = (F[..., FieldIdx.TRICK_ROOM_TURNS] > 0.0) * 1.0
    tr_sign = (1.0 - 2.0 * tr_active)[..., None]  # [..., 1]

    alive_act = P[..., list(active_roster_slots), MonIdx.ALIVE_FLAG]
    active_trig = trigger_mask * alive_act

    if HAS_TORCH and isinstance(active_trig, torch.Tensor):
        if float(active_trig.max().item()) <= 0.0:
            return F, P
        slot_tie_offset = torch.tensor(
            [0.0004, 0.0003, 0.0002, 0.0001], dtype=torch.float32, device=P.device
        )
    else:
        if float(np.max(active_trig)) <= 0.0:
            return F, P
        slot_tie_offset = np.array([0.0004, 0.0003, 0.0002, 0.0001], dtype=np.float32)

    entry_scores = active_trig * 100000.0 + (tr_sign * eff_speeds) + slot_tie_offset
    entry_order = _argsort_desc(entry_scores, axis=-1)

    T_w = tables.t_set_weather
    T_t = tables.t_set_terrain

    for step_idx in range(4):
        actor_k = entry_order[..., step_idx]

        for k_idx, r_slot in enumerate(active_roster_slots):
            is_actor = ((actor_k == k_idx) * 1.0) * active_trig[..., k_idx]
            if HAS_TORCH and isinstance(is_actor, torch.Tensor):
                if float(is_actor.max().item()) <= 0.0:
                    continue
            else:
                if float(np.max(is_actor)) <= 0.0:
                    continue

            abil_id = P[..., r_slot, MonIdx.ABILITY_ID]

            # A. Weather-Setting Abilities (Drought, Drizzle, Sand Stream, Snow Warning)
            weather_ability_map = (
                (AbilityID.DROUGHT, W_SUN),
                (AbilityID.DRIZZLE, W_RAIN),
                (AbilityID.SAND_STREAM, W_SAND),
                (AbilityID.SNOW_WARNING, W_SNOW),
            )
            for target_abil, target_w_idx in weather_ability_map:
                has_w_abil = (abil_id == float(target_abil)) * 1.0
                already_w = F[..., FieldIdx.WEATHER_START + target_w_idx]
                fire_w = is_actor * has_w_abil * (1.0 - already_w)
                if HAS_TORCH and isinstance(fire_w, torch.Tensor):
                    if float(fire_w.max().item()) <= 0.0:
                        continue
                else:
                    if float(np.max(fire_w)) <= 0.0:
                        continue
                fire_w_exp = fire_w[..., None]

                w_old = F[..., FieldIdx.WEATHER_START:FieldIdx.WEATHER_END]
                w_overwritten = _matmul(w_old, T_w[target_w_idx])
                F[..., FieldIdx.WEATHER_START:FieldIdx.WEATHER_END] = (
                    (1.0 - fire_w_exp) * w_old + fire_w_exp * w_overwritten
                )
                F[..., FieldIdx.WEATHER_TURNS] = (
                    (1.0 - fire_w) * F[..., FieldIdx.WEATHER_TURNS] + fire_w * 5.0
                )

            # B. Terrain-Setting Abilities (Electric, Grassy, Psychic, Misty Surge)
            terrain_ability_map = (
                (AbilityID.ELECTRIC_SURGE, T_ELECTRIC),
                (AbilityID.GRASSY_SURGE, T_GRASSY),
                (AbilityID.PSYCHIC_SURGE, T_PSYCHIC),
                (AbilityID.MISTY_SURGE, T_MISTY),
            )
            for target_abil, target_t_idx in terrain_ability_map:
                has_t_abil = (abil_id == float(target_abil)) * 1.0
                already_t = F[..., FieldIdx.TERRAIN_START + target_t_idx]
                fire_t = is_actor * has_t_abil * (1.0 - already_t)
                if HAS_TORCH and isinstance(fire_t, torch.Tensor):
                    if float(fire_t.max().item()) <= 0.0:
                        continue
                else:
                    if float(np.max(fire_t)) <= 0.0:
                        continue
                fire_t_exp = fire_t[..., None]

                t_old = F[..., FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END]
                t_overwritten = _matmul(t_old, T_t[target_t_idx])
                F[..., FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END] = (
                    (1.0 - fire_t_exp) * t_old + fire_t_exp * t_overwritten
                )
                F[..., FieldIdx.TERRAIN_TURNS] = (
                    (1.0 - fire_t) * F[..., FieldIdx.TERRAIN_TURNS] + fire_t * 5.0
                )

            # C. Intimidate (-1 Atk to both opposing active slots + Defiant/Competitive)
            fire_intim = is_actor * ((abil_id == float(AbilityID.INTIMIDATE)) * 1.0)
            has_any_intim = (
                float(fire_intim.max().item()) > 0.0
                if (HAS_TORCH and isinstance(fire_intim, torch.Tensor))
                else float(np.max(fire_intim)) > 0.0
            )
            if has_any_intim:
                opp_slots = (
                    (SLOT_TRAINER_2_A, SLOT_TRAINER_2_B)
                    if r_slot in (SLOT_TRAINER_1_A, SLOT_TRAINER_1_B)
                    else (SLOT_TRAINER_1_A, SLOT_TRAINER_1_B)
                )

                for opp_slot in opp_slots:
                    opp_alive = P[..., opp_slot, MonIdx.ALIVE_FLAG]
                    opp_sub = (P[..., opp_slot, MonIdx.SUBSTITUTE_HP] > 0.0) * 1.0
                    opp_item_act = P[..., opp_slot, MonIdx.ITEM_ACTIVE]
                    opp_clear_amulet = (
                        (P[..., opp_slot, MonIdx.ITEM_ID] == float(ItemID.CLEAR_AMULET)) * 1.0
                    ) * opp_item_act
                    opp_abil = P[..., opp_slot, MonIdx.ABILITY_ID]
                    opp_abil_immune = _clamp(
                        ((opp_abil == float(AbilityID.INNER_FOCUS)) * 1.0)
                        + ((opp_abil == float(AbilityID.SCRAPPY)) * 1.0)
                        + ((opp_abil == float(AbilityID.GOOD_AS_GOLD)) * 1.0),
                        0.0,
                        1.0,
                    )

                    intim_lands = (
                        fire_intim
                        * opp_alive
                        * (1.0 - opp_sub)
                        * (1.0 - opp_clear_amulet)
                        * (1.0 - opp_abil_immune)
                    )

                    old_atk_boost = P[..., opp_slot, MonIdx.BOOST_ATK]
                    actually_lowered = intim_lands * ((old_atk_boost > -6.0) * 1.0)
                    new_atk_boost = _clamp(old_atk_boost - intim_lands * 1.0, -6.0, 6.0)

                    is_defiant = (opp_abil == float(AbilityID.DEFIANT)) * 1.0
                    new_atk_boost = _clamp(
                        new_atk_boost + actually_lowered * is_defiant * 2.0, -6.0, 6.0
                    )
                    P[..., opp_slot, MonIdx.BOOST_ATK] = new_atk_boost

                    is_competitive = (opp_abil == float(AbilityID.COMPETITIVE)) * 1.0
                    old_spa_boost = P[..., opp_slot, MonIdx.BOOST_SPA]
                    P[..., opp_slot, MonIdx.BOOST_SPA] = _clamp(
                        old_spa_boost + actually_lowered * is_competitive * 2.0, -6.0, 6.0
                    )

            # D. Hospitality (Heals ally active slot by floor(HP_MAX * 0.25))
            fire_hosp = is_actor * ((abil_id == float(AbilityID.HOSPITALITY)) * 1.0)
            has_any_hosp = (
                float(fire_hosp.max().item()) > 0.0
                if (HAS_TORCH and isinstance(fire_hosp, torch.Tensor))
                else float(np.max(fire_hosp)) > 0.0
            )
            if has_any_hosp:
                ally_slot = (
                    SLOT_TRAINER_1_B if r_slot == SLOT_TRAINER_1_A else
                    SLOT_TRAINER_1_A if r_slot == SLOT_TRAINER_1_B else
                    SLOT_TRAINER_2_B if r_slot == SLOT_TRAINER_2_A else
                    SLOT_TRAINER_2_A
                )
                ally_alive = P[..., ally_slot, MonIdx.ALIVE_FLAG]
                ally_hp_cur = P[..., ally_slot, MonIdx.HP_CUR]
                ally_hp_max = P[..., ally_slot, MonIdx.HP_MAX]
                heal_amt = _floor(ally_hp_max * 0.25) * fire_hosp * ally_alive
                P[..., ally_slot, MonIdx.HP_CUR] = _clamp(ally_hp_cur + heal_amt, 0.0, 9999.0)
                if HAS_TORCH and isinstance(P, torch.Tensor):
                    P[..., ally_slot, MonIdx.HP_CUR] = torch.minimum(
                        P[..., ally_slot, MonIdx.HP_CUR], ally_hp_max
                    )
                else:
                    P[..., ally_slot, MonIdx.HP_CUR] = np.minimum(
                        P[..., ally_slot, MonIdx.HP_CUR], ally_hp_max
                    )

    return F, P


# =====================================================================
# 4. BARRIER 1: VOLUNTARY SWITCHES (+6) & SWITCH-IN ABILITIES
# =====================================================================

def execute_barrier1_switches(
    F: TensorOrArray,
    P: TensorOrArray,
    M_moves: TensorOrArray,
    trainer_1_choices: TensorOrArray,
    trainer_2_choices: TensorOrArray,
    tables: BilinearLookupTables,
) -> Tuple[TensorOrArray, TensorOrArray, TensorOrArray, TensorOrArray]:
    """Execute Phase 1 (Barrier 1: Voluntary Switches at Priority `+6` + Speed-Sorted Entry Abilities)
    across the `[B1, B2]` joint action grid.
    """
    c_t1a = trainer_1_choices[:, None, 0] if trainer_1_choices.ndim == 2 else trainer_1_choices[:, :, 0]
    c_t1b = trainer_1_choices[:, None, 1] if trainer_1_choices.ndim == 2 else trainer_1_choices[:, :, 1]
    c_t2a = trainer_2_choices[None, :, 0] if trainer_2_choices.ndim == 2 else trainer_2_choices[:, :, 0]
    c_t2b = trainer_2_choices[None, :, 1] if trainer_2_choices.ndim == 2 else trainer_2_choices[:, :, 1]

    B1 = P.shape[0]
    B2 = P.shape[1]

    if HAS_TORCH and isinstance(P, torch.Tensor):
        c_t1a = c_t1a.expand(B1, B2)
        c_t1b = c_t1b.expand(B1, B2)
        c_t2a = c_t2a.expand(B1, B2)
        c_t2b = c_t2b.expand(B1, B2)
    else:
        c_t1a = np.broadcast_to(c_t1a, (B1, B2))
        c_t1b = np.broadcast_to(c_t1b, (B1, B2))
        c_t2a = np.broadcast_to(c_t2a, (B1, B2))
        c_t2b = np.broadcast_to(c_t2b, (B1, B2))

    switch_specs = (
        (SLOT_TRAINER_1_A, SLOT_TRAINER_1_BENCH1, c_t1a, CHOICE_SWITCH_BENCH1),
        (SLOT_TRAINER_1_A, SLOT_TRAINER_1_BENCH2, c_t1a, CHOICE_SWITCH_BENCH2),
        (SLOT_TRAINER_1_B, SLOT_TRAINER_1_BENCH1, c_t1b, CHOICE_SWITCH_BENCH1),
        (SLOT_TRAINER_1_B, SLOT_TRAINER_1_BENCH2, c_t1b, CHOICE_SWITCH_BENCH2),
        (SLOT_TRAINER_2_A, SLOT_TRAINER_2_BENCH1, c_t2a, CHOICE_SWITCH_BENCH1),
        (SLOT_TRAINER_2_A, SLOT_TRAINER_2_BENCH2, c_t2a, CHOICE_SWITCH_BENCH2),
        (SLOT_TRAINER_2_B, SLOT_TRAINER_2_BENCH1, c_t2b, CHOICE_SWITCH_BENCH1),
        (SLOT_TRAINER_2_B, SLOT_TRAINER_2_BENCH2, c_t2b, CHOICE_SWITCH_BENCH2),
    )

    persist_mask = tables.switch_persist_mask  # [84]

    for act_slot, bench_slot, c_grid, target_c in switch_specs:
        sw_gate = (
            ((c_grid == target_c) * 1.0)
            * P[..., act_slot, MonIdx.ALIVE_FLAG]
            * P[..., bench_slot, MonIdx.ALIVE_FLAG]
        )
        if HAS_TORCH and isinstance(sw_gate, torch.Tensor):
            if float(sw_gate.max().item()) <= 0.0:
                continue
        else:
            if float(np.max(sw_gate)) <= 0.0:
                continue

        sw_gate_mon = sw_gate[..., None]
        effective_persist = (1.0 - sw_gate_mon) + sw_gate_mon * persist_mask
        P[..., act_slot, :] = P[..., act_slot, :] * effective_persist

        P[..., act_slot, MonIdx.UNBURDEN_ACTIVE] = P[..., act_slot, MonIdx.UNBURDEN_ACTIVE] * (1.0 - sw_gate)
        P[..., act_slot, MonIdx.CHOICE_LOCKED_MOVE] = (
            P[..., act_slot, MonIdx.CHOICE_LOCKED_MOVE] * (1.0 - sw_gate) + (-1.0) * sw_gate
        )

        p_act = P[..., act_slot, :].clone() if (HAS_TORCH and isinstance(P, torch.Tensor)) else P[..., act_slot, :].copy()
        p_bench = P[..., bench_slot, :].clone() if (HAS_TORCH and isinstance(P, torch.Tensor)) else P[..., bench_slot, :].copy()
        P[..., act_slot, :] = (1.0 - sw_gate_mon) * p_act + sw_gate_mon * p_bench
        P[..., bench_slot, :] = (1.0 - sw_gate_mon) * p_bench + sw_gate_mon * p_act

        sw_gate_m2 = sw_gate[..., None, None]
        m_act = M_moves[..., act_slot, :, :].clone() if (HAS_TORCH and isinstance(M_moves, torch.Tensor)) else M_moves[..., act_slot, :, :].copy()
        m_bench = M_moves[..., bench_slot, :, :].clone() if (HAS_TORCH and isinstance(M_moves, torch.Tensor)) else M_moves[..., bench_slot, :, :].copy()
        M_moves[..., act_slot, :, :] = (1.0 - sw_gate_m2) * m_act + sw_gate_m2 * m_bench
        M_moves[..., bench_slot, :, :] = (1.0 - sw_gate_m2) * m_bench + sw_gate_m2 * m_act

        P[..., act_slot, MonIdx.ACTIVE_TURNS] = P[..., act_slot, MonIdx.ACTIVE_TURNS] * (1.0 - sw_gate)

    sw_t1a = (((c_t1a == CHOICE_SWITCH_BENCH1) | (c_t1a == CHOICE_SWITCH_BENCH2)) * 1.0)
    sw_t1b = (((c_t1b == CHOICE_SWITCH_BENCH1) | (c_t1b == CHOICE_SWITCH_BENCH2)) * 1.0)
    sw_t2a = (((c_t2a == CHOICE_SWITCH_BENCH1) | (c_t2a == CHOICE_SWITCH_BENCH2)) * 1.0)
    sw_t2b = (((c_t2b == CHOICE_SWITCH_BENCH1) | (c_t2b == CHOICE_SWITCH_BENCH2)) * 1.0)

    if HAS_TORCH and isinstance(P, torch.Tensor):
        switched_mask = torch.stack([sw_t1a, sw_t1b, sw_t2a, sw_t2b], dim=-1)
    else:
        switched_mask = np.stack([sw_t1a, sw_t1b, sw_t2a, sw_t2b], axis=-1).astype(np.float32)

    F, P = _execute_speed_sorted_entry_abilities(F, P, switched_mask, tables)

    return F, P, M_moves, switched_mask


# =====================================================================
# 5. BARRIER 2: MEGA EVOLUTION (+5.5) & INSTANTANEOUS SPEED RECALIBRATION
# =====================================================================

def execute_barrier2_mega_evolution(
    F: TensorOrArray,
    P: TensorOrArray,
    trainer_1_choices: TensorOrArray,
    trainer_2_choices: TensorOrArray,
    tables: BilinearLookupTables,
) -> Tuple[TensorOrArray, TensorOrArray, TensorOrArray]:
    """Execute Phase 2 (Barrier 2: Mega Evolution at Priority `+5.5`, Instantaneous Regulation M-C
    5-Stat Transformation, Secondary Type Transformation, and Speed-Sorted Mega Entry Abilities).
    """
    B1 = P.shape[0]
    B2 = P.shape[1]

    c_t1a = trainer_1_choices[:, None, 0] if trainer_1_choices.ndim == 2 else trainer_1_choices[:, :, 0]
    c_t1b = trainer_1_choices[:, None, 1] if trainer_1_choices.ndim == 2 else trainer_1_choices[:, :, 1]
    c_t2a = trainer_2_choices[None, :, 0] if trainer_2_choices.ndim == 2 else trainer_2_choices[:, :, 0]
    c_t2b = trainer_2_choices[None, :, 1] if trainer_2_choices.ndim == 2 else trainer_2_choices[:, :, 1]

    if HAS_TORCH and isinstance(P, torch.Tensor):
        c_t1a = c_t1a.expand(B1, B2)
        c_t1b = c_t1b.expand(B1, B2)
        c_t2a = c_t2a.expand(B1, B2)
        c_t2b = c_t2b.expand(B1, B2)
    else:
        c_t1a = np.broadcast_to(c_t1a, (B1, B2))
        c_t1b = np.broadcast_to(c_t1b, (B1, B2))
        c_t2a = np.broadcast_to(c_t2a, (B1, B2))
        c_t2b = np.broadcast_to(c_t2b, (B1, B2))

    slot_specs = (
        (0, SLOT_TRAINER_1_A, c_t1a, FieldIdx.TRAINER_1_MEGA_USED),
        (1, SLOT_TRAINER_1_B, c_t1b, FieldIdx.TRAINER_1_MEGA_USED),
        (2, SLOT_TRAINER_2_A, c_t2a, FieldIdx.TRAINER_2_MEGA_USED),
        (3, SLOT_TRAINER_2_B, c_t2b, FieldIdx.TRAINER_2_MEGA_USED),
    )

    mega_masks = []
    for _, r_slot, c_grid, side_mega_idx in slot_specs:
        wants_mega = ((c_grid >= 12) & (c_grid <= 23)) * 1.0
        alive = P[..., r_slot, MonIdx.ALIVE_FLAG]
        can_mega = P[..., r_slot, MonIdx.CAN_MEGA]
        not_mega = 1.0 - P[..., r_slot, MonIdx.IS_MEGA]
        side_avail = 1.0 - F[..., side_mega_idx]

        m_gate = wants_mega * alive * can_mega * not_mega * side_avail
        m_gate_exp = m_gate[..., None]

        # Transform all 5 active stats (ATK, DEF, SPA, SPD, SPE) -> MEGA_ATK..MEGA_SPE (78..82)
        base_stats = P[..., r_slot, MonIdx.STAT_ATK:MonIdx.STAT_SPE + 1]
        mega_stats = P[..., r_slot, MonIdx.MEGA_ATK:MonIdx.MEGA_SPE + 1]
        P[..., r_slot, MonIdx.STAT_ATK:MonIdx.STAT_SPE + 1] = (
            (1.0 - m_gate_exp) * base_stats + m_gate_exp * mega_stats
        )

        # Transform Ability ID -> MEGA_ABILITY_ID (83)
        base_abil = P[..., r_slot, MonIdx.ABILITY_ID]
        mega_abil = P[..., r_slot, MonIdx.MEGA_ABILITY_ID]
        P[..., r_slot, MonIdx.ABILITY_ID] = (1.0 - m_gate) * base_abil + m_gate * mega_abil

        # Update IS_MEGA, CAN_MEGA, and SIDE_MEGA_USED
        P[..., r_slot, MonIdx.IS_MEGA] = _clamp(P[..., r_slot, MonIdx.IS_MEGA] + m_gate, 0.0, 1.0)
        P[..., r_slot, MonIdx.CAN_MEGA] = P[..., r_slot, MonIdx.CAN_MEGA] * (1.0 - m_gate)
        F[..., side_mega_idx] = _clamp(F[..., side_mega_idx] + m_gate, 0.0, 1.0)

        mega_masks.append(m_gate)

    if HAS_TORCH and isinstance(P, torch.Tensor):
        mega_evolved_mask = torch.stack(mega_masks, dim=-1)
    else:
        mega_evolved_mask = np.stack(mega_masks, axis=-1).astype(np.float32)

    F, P = _execute_speed_sorted_entry_abilities(F, P, mega_evolved_mask, tables)

    return F, P, mega_evolved_mask


# =====================================================================
# 6. BARRIER 3: PRIORITY BRACKET, EFFECTIVE SPEED & SPINNING-WHEEL TIE SORT
# =====================================================================

def execute_barrier3_turn_order_sort(
    F: TensorOrArray,
    P: TensorOrArray,
    M_moves: TensorOrArray,
    trainer_1_choices: TensorOrArray,
    trainer_2_choices: TensorOrArray,
    rng_seed: int = 42,
) -> Tuple[TensorOrArray, TensorOrArray, TensorOrArray, TensorOrArray, TensorOrArray, TensorOrArray, List[str]]:
    """Execute Phase 3 (Barrier 3: Effective Priority + Effective Speed + Spinning-Wheel Tie-Break Jitter
    + `Speed_Tie_Alert` Detection) across the `[B1, B2]` joint action grid.
    """
    B1 = P.shape[0]
    B2 = P.shape[1]

    c_t1a = trainer_1_choices[:, None, 0] if trainer_1_choices.ndim == 2 else trainer_1_choices[:, :, 0]
    c_t1b = trainer_1_choices[:, None, 1] if trainer_1_choices.ndim == 2 else trainer_1_choices[:, :, 1]
    c_t2a = trainer_2_choices[None, :, 0] if trainer_2_choices.ndim == 2 else trainer_2_choices[:, :, 0]
    c_t2b = trainer_2_choices[None, :, 1] if trainer_2_choices.ndim == 2 else trainer_2_choices[:, :, 1]

    if HAS_TORCH and isinstance(P, torch.Tensor):
        c_t1a = c_t1a.expand(B1, B2)
        c_t1b = c_t1b.expand(B1, B2)
        c_t2a = c_t2a.expand(B1, B2)
        c_t2b = c_t2b.expand(B1, B2)
        choices_grid = torch.stack([c_t1a, c_t1b, c_t2a, c_t2b], dim=-1)
    else:
        c_t1a = np.broadcast_to(c_t1a, (B1, B2))
        c_t1b = np.broadcast_to(c_t1b, (B1, B2))
        c_t2a = np.broadcast_to(c_t2a, (B1, B2))
        c_t2b = np.broadcast_to(c_t2b, (B1, B2))
        choices_grid = np.stack([c_t1a, c_t1b, c_t2a, c_t2b], axis=-1)

    eff_speeds = compute_active_effective_speeds(F, P)  # [B1, B2, 4]

    active_roster_slots = (SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_2_A, SLOT_TRAINER_2_B)
    prio_list = []

    t_grassy = F[..., FieldIdx.TERRAIN_START + T_GRASSY]

    for k_idx, r_slot in enumerate(active_roster_slots):
        c_slot = choices_grid[..., k_idx]
        is_sw = ((c_slot >= CHOICE_SWITCH_BENCH1) * 1.0)
        move_idx = (c_slot % 12) % 4

        slot_moves = M_moves[..., r_slot, :, :]  # [B1, B2, 4, 56]
        if HAS_TORCH and isinstance(P, torch.Tensor):
            m_oh = torch.nn.functional.one_hot(move_idx.long(), num_classes=4).to(torch.float32)
        else:
            m_oh = np.eye(4, dtype=np.float32)[move_idx.astype(np.int64)]

        sel_move = _einsum("...m,...mf->...f", m_oh, slot_moves)

        base_prio = sel_move[..., MoveIdx.PRIORITY]
        is_status = sel_move[..., MoveIdx.CAT_STATUS]
        is_grassy_glide = sel_move[..., MoveIdx.GRASSY_PRIO_BOOST]

        abil_id = P[..., r_slot, MonIdx.ABILITY_ID]
        is_prankster = (abil_id == float(AbilityID.PRANKSTER)) * 1.0
        grounded = P[..., r_slot, MonIdx.GROUNDED_FLAG]

        move_prio = (
            base_prio
            + is_prankster * is_status * 1.0
            + is_grassy_glide * t_grassy * grounded * 1.0
        )
        eff_p = is_sw * 6.0 + (1.0 - is_sw) * move_prio
        prio_list.append(eff_p)

    if HAS_TORCH and isinstance(P, torch.Tensor):
        eff_priorities = torch.stack(prio_list, dim=-1)
    else:
        eff_priorities = np.stack(prio_list, axis=-1).astype(np.float32)

    alive_act = P[..., list(active_roster_slots), MonIdx.ALIVE_FLAG]
    not_sw_act = ((choices_grid < CHOICE_SWITCH_BENCH1) * 1.0) * alive_act

    # Use Counter-Based Spinning-Wheel Jitter in [-0.01, +0.01] for timeline 0
    w_start = counter_uniform_0_100_numpy(
        (B1, B2, 4), rng_seed, int(RNGEventID.SPEED_TIE_JITTER), step_idx=0, sub_draw=0
    )
    dart = counter_uniform_0_100_numpy(
        (B1, B2, 4), rng_seed, int(RNGEventID.SPEED_TIE_JITTER), step_idx=0, sub_draw=1
    )
    cyclic_u = np.mod(dart - w_start + 100.0, 100.0) / 100.0  # [0.0, 1.0)
    raw_jitter = ((cyclic_u * 0.02) - 0.01).astype(np.float32)

    if HAS_TORCH and isinstance(P, torch.Tensor):
        jitter_tensor = torch.from_numpy(raw_jitter).to(P.device)
        speed_tie_alert = torch.zeros((B1, B2), dtype=torch.float32, device=P.device)
    else:
        jitter_tensor = raw_jitter
        speed_tie_alert = np.zeros((B1, B2), dtype=np.float32)

    speed_tie_notes: List[str] = []
    slot_labels = (
        "trainer_1_a(Slot0)",
        "trainer_1_b(Slot1)",
        "trainer_2_a(Slot4)",
        "trainer_2_b(Slot5)",
    )

    for i in range(4):
        for j in range(i + 1, 4):
            pair_active = not_sw_act[..., i] * not_sw_act[..., j]
            same_prio = (eff_priorities[..., i] == eff_priorities[..., j]) * 1.0
            same_speed = (eff_speeds[..., i] == eff_speeds[..., j]) * 1.0
            pair_tie = pair_active * same_prio * same_speed
            speed_tie_alert = _clamp(speed_tie_alert + pair_tie, 0.0, 1.0)

            if len(speed_tie_notes) < 8:
                if HAS_TORCH and isinstance(pair_tie, torch.Tensor):
                    tie_coords = torch.nonzero(pair_tie > 0.5, as_tuple=False).detach().cpu().numpy()
                else:
                    tie_coords = np.argwhere(pair_tie > 0.5)

                for coord in tie_coords:
                    if len(speed_tie_notes) >= 8:
                        break
                    r_idx, c_idx = int(coord[0]), int(coord[1])
                    spd_val = float(
                        eff_speeds[r_idx, c_idx, i].item()
                        if hasattr(eff_speeds[r_idx, c_idx, i], "item")
                        else eff_speeds[r_idx, c_idx, i]
                    )
                    prio_val = float(
                        eff_priorities[r_idx, c_idx, i].item()
                        if hasattr(eff_priorities[r_idx, c_idx, i], "item")
                        else eff_priorities[r_idx, c_idx, i]
                    )
                    jit_i = float(raw_jitter[r_idx, c_idx, i])
                    jit_j = float(raw_jitter[r_idx, c_idx, j])
                    winner = slot_labels[i] if jit_i > jit_j else slot_labels[j]
                    note = (
                        f"[SPEED_TIE_ALERT cell=({r_idx},{c_idx})] {slot_labels[i]} vs {slot_labels[j]} "
                        f"tied at Priority={prio_val:+.0f}, EffectiveSpeed={spd_val:.0f} | "
                        f"Spinning-Wheel Jitter ({slot_labels[i]}={jit_i:+.4f}, {slot_labels[j]}={jit_j:+.4f}) "
                        f"-> {winner} wins tie-break (50/50 coinflip per simulation thread)"
                    )
                    speed_tie_notes.append(note)

    tr_active = (F[..., FieldIdx.TRICK_ROOM_TURNS] > 0.0) * 1.0
    tr_sign = (1.0 - 2.0 * tr_active)[..., None]  # [B1, B2, 1]

    sort_scores = (eff_priorities * 10000.0) + (tr_sign * eff_speeds) + jitter_tensor
    execution_order = _argsort_desc(sort_scores, axis=-1)

    return (
        eff_speeds,
        eff_priorities,
        jitter_tensor,
        sort_scores,
        execution_order,
        speed_tie_alert,
        speed_tie_notes,
    )


def compute_per_thread_execution_orders(
    F_mc: TensorOrArray,
    eff_speeds: TensorOrArray,
    eff_priorities: TensorOrArray,
    num_sim_threads: int,
    rng_seed: int = 42,
) -> TensorOrArray:
    """Compute `[B1, B2, K, 4]` turn-order permutations where every simulation thread `k in 0..K-1`
    spins an independent 50/50 wheel to break exact intra-bracket speed ties!
    """
    B1, B2 = eff_speeds.shape[0], eff_speeds.shape[1]
    K = num_sim_threads

    if HAS_TORCH and isinstance(eff_speeds, torch.Tensor):
        dev = eff_speeds.device
        tr_active = (F_mc[:, :, :, FieldIdx.TRICK_ROOM_TURNS] > 0.0).float()
        tr_sign = (1.0 - 2.0 * tr_active).unsqueeze(-1)  # [B1, B2, K, 1]

        w_start = counter_uniform_0_100_torch(
            (B1, B2, K, 4), dev, rng_seed, int(RNGEventID.SPEED_TIE_JITTER), step_idx=1, sub_draw=0
        )
        dart = counter_uniform_0_100_torch(
            (B1, B2, K, 4), dev, rng_seed, int(RNGEventID.SPEED_TIE_JITTER), step_idx=1, sub_draw=1
        )
        cyclic_u = torch.remainder(dart - w_start + 100.0, 100.0) / 100.0
        jitter_k = (cyclic_u * 0.02) - 0.01

        prio_k = eff_priorities.unsqueeze(2).expand(B1, B2, K, 4)
        spe_k = eff_speeds.unsqueeze(2).expand(B1, B2, K, 4)
        scores_k = (prio_k * 10000.0) + (tr_sign * spe_k) + jitter_k
        return torch.argsort(scores_k, dim=-1, descending=True)

    tr_active = (F_mc[:, :, :, FieldIdx.TRICK_ROOM_TURNS] > 0.0).astype(np.float32)
    tr_sign = (1.0 - 2.0 * tr_active)[..., None]  # [B1, B2, K, 1]

    w_start = counter_uniform_0_100_numpy(
        (B1, B2, K, 4), rng_seed, int(RNGEventID.SPEED_TIE_JITTER), step_idx=1, sub_draw=0
    )
    dart = counter_uniform_0_100_numpy(
        (B1, B2, K, 4), rng_seed, int(RNGEventID.SPEED_TIE_JITTER), step_idx=1, sub_draw=1
    )
    cyclic_u = np.mod(dart - w_start + 100.0, 100.0) / 100.0
    jitter_k = ((cyclic_u * 0.02) - 0.01).astype(np.float32)

    prio_k = np.broadcast_to(eff_priorities[:, :, None, :], (B1, B2, K, 4))
    spe_k = np.broadcast_to(eff_speeds[:, :, None, :], (B1, B2, K, 4))
    scores_k = (prio_k * 10000.0) + (tr_sign * spe_k) + jitter_k
    return np.argsort(-scores_k, axis=-1)


# =====================================================================
# 7. UNIFIED PRE-ATTACK PHASES ENTRYPOINT (BARRIERS 1–3)
# =====================================================================

def execute_pre_attack_phases(
    F_init: TensorOrArray,
    P_init: TensorOrArray,
    M_moves_init: TensorOrArray,
    trainer_1_choices: TensorOrArray,
    trainer_2_choices: TensorOrArray,
    tables: Optional[BilinearLookupTables] = None,
    rng_seed: int = 42,
    resolve_lead_entry_abilities: bool = False,
) -> PreAttackPhaseResult:
    """Execute Phases 1, 2, and 3 (Voluntary Switches -> Mega Evolution -> Speed/Priority Turn-Order Sort)
    across a `[B1, B2]` joint action grid (`trainer_1` vs `trainer_2`).
    """
    is_torch = HAS_TORCH and isinstance(P_init, torch.Tensor)
    if tables is None:
        dev = P_init.device if is_torch else "cpu"
        tables = build_bilinear_lookup_tables(device=dev)

    B1 = int(trainer_1_choices.shape[0])
    B2 = int(trainer_2_choices.shape[0] if trainer_2_choices.ndim == 2 else trainer_2_choices.shape[1])

    if F_init.ndim == 1:
        if is_torch:
            F = F_init[None, None, :].expand(B1, B2, FIELD_DIM).clone()
        else:
            F = np.broadcast_to(F_init[None, None, :], (B1, B2, FIELD_DIM)).copy()
    else:
        F = _clone(F_init)

    if P_init.ndim == 2:
        if is_torch:
            P = P_init[None, None, :, :].expand(B1, B2, ROSTER_SLOTS, MON_DIM).clone()
        else:
            P = np.broadcast_to(P_init[None, None, :, :], (B1, B2, ROSTER_SLOTS, MON_DIM)).copy()
    else:
        P = _clone(P_init)

    if M_moves_init.ndim == 3:
        if is_torch:
            M_moves = M_moves_init[None, None, :, :, :].expand(
                B1, B2, ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM
            ).clone()
        else:
            M_moves = np.broadcast_to(
                M_moves_init[None, None, :, :, :], (B1, B2, ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM)
            ).copy()
    else:
        M_moves = _clone(M_moves_init)

    if resolve_lead_entry_abilities:
        if is_torch:
            lead_trig = torch.ones((B1, B2, 4), dtype=torch.float32, device=P.device)
        else:
            lead_trig = np.ones((B1, B2, 4), dtype=np.float32)
        F, P = _execute_speed_sorted_entry_abilities(F, P, lead_trig, tables)

    F, P, M_moves, switched_mask = execute_barrier1_switches(
        F, P, M_moves, trainer_1_choices, trainer_2_choices, tables
    )

    F, P, mega_evolved_mask = execute_barrier2_mega_evolution(
        F, P, trainer_1_choices, trainer_2_choices, tables
    )

    (
        eff_speeds,
        eff_priorities,
        jitter_applied,
        sort_scores,
        execution_order,
        speed_tie_alert,
        speed_tie_notes,
    ) = execute_barrier3_turn_order_sort(
        F, P, M_moves, trainer_1_choices, trainer_2_choices, rng_seed=rng_seed
    )

    return PreAttackPhaseResult(
        F=F,
        P=P,
        M_moves=M_moves,
        effective_speeds=eff_speeds,
        effective_priorities=eff_priorities,
        jitter_applied=jitter_applied,
        sort_scores=sort_scores,
        execution_order=execution_order,
        switched_mask=switched_mask,
        mega_evolved_mask=mega_evolved_mask,
        speed_tie_alert=speed_tie_alert,
        speed_tie_notes=speed_tie_notes,
    )
