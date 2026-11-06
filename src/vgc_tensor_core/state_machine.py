# -*- coding: utf-8 -*-
"""
VGC Tensor Core — Milestone 5: End-of-Turn & Unified State Machine
==================================================================

This module implements Phase 5 (End-of-Turn Resolution) and the unified,
high-level `VgcTensorStateMachine` class for Pokémon VGC 4v4 Doubles (Regulation M-C).

Key Architectural Components:
1. **Phase 5: End-of-Turn Resolution (`execute_end_of_turn`)**:
   - Sandstorm chip damage (1/16 max HP to non-Rock/Ground/Steel).
   - Non-volatile status chip: Burn (1/16 max HP), Poison (1/8 max HP), Toxic (escalating N/16 max HP).
   - Grounded Grassy Terrain healing (+1/16 max HP) and Leftovers healing (+1/16 max HP).
   - Field & side counter decrements: Weather, Terrain, Trick Room, Tailwind, Reflect/Light Screen/Aurora Veil.
   - Volatile resets: Flinch reset, Protect reset (consecutive counter zeroed if not used).
   - Winner & match termination evaluation (4 faints on either side).
2. **Compiler Tactical Prior Auto-Replacement Heuristic**:
   - If an active slot faints, auto-promotes the alive bench Pokémon with the highest
     board equity (or the sole survivor if only 1 remains), supporting optional explicit
     overrides via `replacement_choices`.
3. **Unified `VgcTensorStateMachine` Engine**:
   - High-level, branchless API: `state_machine.step(...) -> StepResult`.
   - Chains Pre-Attack (Barriers 1-3) -> Attack Cascade (Phase 4) -> End-of-Turn (Phase 5).

Strict Isolation Guardrail:
---------------------------
ZERO imports from `engine/`. Uses only `torch` (with `numpy` fallback), Python stdlib,
and sibling modules `schema_and_tables`, `compiler`, `phases_pre_attack`, and `attack_cascade`.
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
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
    ShowdownTensorCompiler,
)
from .phases_pre_attack import (
    ACTIVE_SLOT_NAMES,
    ACTIVE_SLOTS,
    PreAttackPhaseResult,
    execute_pre_attack_phases,
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
    TERRAIN_TO_IDX,
    TYPE_TO_IDX,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
)

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray

W_CLEAR: int = WEATHER_TO_IDX["clear"]
W_SUN: int = WEATHER_TO_IDX["sun"]
W_RAIN: int = WEATHER_TO_IDX["rain"]
W_SAND: int = WEATHER_TO_IDX["sand"]
W_SNOW: int = WEATHER_TO_IDX["snow"]

T_NONE: int = TERRAIN_TO_IDX["none"]
T_ELECTRIC: int = TERRAIN_TO_IDX["electric"]
T_GRASSY: int = TERRAIN_TO_IDX["grassy"]
T_PSYCHIC: int = TERRAIN_TO_IDX["psychic"]
T_MISTY: int = TERRAIN_TO_IDX["misty"]


@dataclass(frozen=True)
class EndOfTurnResult:
    """Outcome of Phase 5 (End-of-Turn Resolution)."""
    F: TensorOrArray
    P: TensorOrArray
    M_moves: TensorOrArray
    mean_hp: TensorOrArray
    faint_prob: TensorOrArray
    p1_fainted_count: TensorOrArray
    p2_fainted_count: TensorOrArray
    is_terminal: TensorOrArray
    winner: TensorOrArray  # 0: Incomplete/Draw, 1: P1, 2: P2
    eot_events: List[str]


@dataclass(frozen=True)
class StepResult:
    """Comprehensive result of a full VGC turn step."""
    F: TensorOrArray
    P: TensorOrArray
    M_moves: TensorOrArray
    pre_attack: PreAttackPhaseResult
    attack_cascade: AttackCascadeResult
    end_of_turn: EndOfTurnResult
    mean_hp: TensorOrArray
    faint_prob: TensorOrArray
    roll_variance_alert: TensorOrArray
    is_terminal: TensorOrArray
    winner: TensorOrArray


# =============================================================================
# HELPER UTILITIES
# =============================================================================

def _to_numpy(x: TensorOrArray) -> np.ndarray:
    if HAS_TORCH and isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy()
    return np.asarray(x)


# =============================================================================
# PHASE 5: END-OF-TURN RESOLUTION
# =============================================================================


# =============================================================================
# NATIVE PYTORCH PHASE 5: END-OF-TURN RESOLUTION (ZERO HOST TRANSFERS)
# =============================================================================

def _execute_end_of_turn_torch(
    F: torch.Tensor,             # [B1, B2, K, 24]
    P: torch.Tensor,             # [B1, B2, K, 8, 84]
    M_moves: torch.Tensor,       # [B1, B2, K, 8, 4, 52]
    tables: BilinearLookupTables,
) -> EndOfTurnResult:
    F = F.clone()
    P = P.clone()
    M_moves = M_moves.clone()
    """
    Pure PyTorch implementation of Phase 5 (End-of-Turn resolution).
    Evaluates weather chip, status chip, healing, turn decrements, and volatile resets
    across all B1 x B2 x K cells in parallel directly in GPU VRAM.
    """
    device = P.device
    B1, B2, K = P.shape[0], P.shape[1], P.shape[2]
    active_slot_tensor = torch.tensor(ACTIVE_SLOTS, dtype=torch.long, device=device)

    # Extract Active Slots HP and Stats: [B1, B2, K, 4]
    active_hp_cur = P[:, :, :, active_slot_tensor, MonIdx.HP_CUR]
    active_hp_max = P[:, :, :, active_slot_tensor, MonIdx.HP_MAX]
    active_alive = active_hp_cur > 0.0

    # -------------------------------------------------------------------------
    # 1. WEATHER RESIDUAL DAMAGE (SANDSTORM: 1/16 MAX HP)
    # -------------------------------------------------------------------------
    is_sand = (F[:, :, :, FieldIdx.WEATHER_START + W_SAND] > 0.5).unsqueeze(-1)  # [B1, B2, K, 1]
    
    # Types immunity (Rock=12, Ground=8, Steel=16) or Safety Goggles
    t1 = torch.argmax(P[:, :, :, active_slot_tensor, MonIdx.TYPE1_START : MonIdx.TYPE1_END], dim=-1)
    t2 = torch.argmax(P[:, :, :, active_slot_tensor, MonIdx.TYPE2_START : MonIdx.TYPE2_END], dim=-1)
    has_t2 = torch.sum(P[:, :, :, active_slot_tensor, MonIdx.TYPE2_START : MonIdx.TYPE2_END], dim=-1) > 0.5

    sand_immune_types = (t1 == 12) | (t1 == 8) | (t1 == 16) | (has_t2 & ((t2 == 12) | (t2 == 8) | (t2 == 16)))
    has_goggles = P[:, :, :, active_slot_tensor, MonIdx.ITEM_ID] == float(ItemID.SAFETY_GOGGLES)
    is_sand_immune = sand_immune_types | has_goggles

    sand_chip = torch.where(
        is_sand & active_alive & (~is_sand_immune),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur)
    )
    active_hp_cur = torch.clamp(active_hp_cur - sand_chip, min=0.0)

    # -------------------------------------------------------------------------
    # 2. STATUS CHIP DAMAGE (BURN: 1/16, POISON: 1/8, TOXIC: N/16)
    # -------------------------------------------------------------------------
    is_burned = P[:, :, :, active_slot_tensor, MonIdx.STATUS_BURN] > 0.5
    is_poisoned = P[:, :, :, active_slot_tensor, MonIdx.STATUS_POISON] > 0.5
    is_toxic = P[:, :, :, active_slot_tensor, MonIdx.STATUS_TOXIC] > 0.5

    burn_chip = torch.where(is_burned & (active_hp_cur > 0.0), torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0), torch.zeros_like(active_hp_cur))
    poison_chip = torch.where(is_poisoned & (active_hp_cur > 0.0), torch.clamp(torch.floor(active_hp_max / 8.0), min=1.0), torch.zeros_like(active_hp_cur))

    # Toxic escalating chip: floor((max_hp * toxic_counter) / 16.0)
    toxic_count = torch.clamp(P[:, :, :, active_slot_tensor, MonIdx.TOXIC_COUNTER], min=1.0)
    toxic_chip = torch.where(is_toxic & (active_hp_cur > 0.0), torch.clamp(torch.floor((active_hp_max * toxic_count) / 16.0), min=1.0), torch.zeros_like(active_hp_cur))

    # Increment toxic counters
    new_toxic_count = torch.where(is_toxic & (active_hp_cur > 0.0), toxic_count + 1.0, toxic_count)
    P[:, :, :, active_slot_tensor, MonIdx.TOXIC_COUNTER] = new_toxic_count

    active_hp_cur = torch.clamp(active_hp_cur - burn_chip - poison_chip - toxic_chip, min=0.0)

    # -------------------------------------------------------------------------
    # 3. TERRAIN & ITEM HEALING (GRASSY TERRAIN: +1/16, LEFTOVERS: +1/16)
    # -------------------------------------------------------------------------
    is_grassy = (F[:, :, :, FieldIdx.TERRAIN_START + T_GRASSY] > 0.5).unsqueeze(-1)
    is_grounded = P[:, :, :, active_slot_tensor, MonIdx.GROUNDED_FLAG] > 0.5
    grassy_heal = torch.where(
        is_grassy & is_grounded & (active_hp_cur > 0.0) & (active_hp_cur < active_hp_max),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur)
    )

    has_lefties = (P[:, :, :, active_slot_tensor, MonIdx.ITEM_ACTIVE] > 0.5) & (P[:, :, :, active_slot_tensor, MonIdx.ITEM_ID] == float(ItemID.LEFTOVERS))
    lefties_heal = torch.where(
        has_lefties & (active_hp_cur > 0.0) & (active_hp_cur < active_hp_max),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur)
    )

    active_hp_cur = torch.clamp(active_hp_cur + grassy_heal + lefties_heal, max=active_hp_max)

    # Update active slots back into P
    P[:, :, :, active_slot_tensor, MonIdx.HP_CUR] = active_hp_cur
    P[:, :, :, active_slot_tensor, MonIdx.ALIVE_FLAG] = (active_hp_cur > 0.0).float()

    # -------------------------------------------------------------------------
    # 4. FIELD & SIDE COUNTER DECREMENTS
    # -------------------------------------------------------------------------
    # Decrement weather turns
    w_turns = F[:, :, :, FieldIdx.WEATHER_TURNS]
    w_active = w_turns > 0.0
    new_w_turns = torch.clamp(w_turns - 1.0, min=0.0)
    F[:, :, :, FieldIdx.WEATHER_TURNS] = new_w_turns

    # If weather expired, reset to clear
    w_expired = w_active & (new_w_turns == 0.0)
    if torch.any(w_expired):
        F[:, :, :, FieldIdx.WEATHER_START : FieldIdx.WEATHER_END] = torch.where(
            w_expired.unsqueeze(-1),
            torch.zeros_like(F[:, :, :, FieldIdx.WEATHER_START : FieldIdx.WEATHER_END]),
            F[:, :, :, FieldIdx.WEATHER_START : FieldIdx.WEATHER_END]
        )
        F[:, :, :, FieldIdx.WEATHER_START + W_CLEAR] = torch.where(
            w_expired,
            torch.ones_like(new_w_turns),
            F[:, :, :, FieldIdx.WEATHER_START + W_CLEAR]
        )

    # Decrement terrain turns
    t_turns = F[:, :, :, FieldIdx.TERRAIN_TURNS]
    t_active = t_turns > 0.0
    new_t_turns = torch.clamp(t_turns - 1.0, min=0.0)
    F[:, :, :, FieldIdx.TERRAIN_TURNS] = new_t_turns

    # If terrain expired, reset to none
    t_expired = t_active & (new_t_turns == 0.0)
    if torch.any(t_expired):
        F[:, :, :, FieldIdx.TERRAIN_START : FieldIdx.TERRAIN_END] = torch.where(
            t_expired.unsqueeze(-1),
            torch.zeros_like(F[:, :, :, FieldIdx.TERRAIN_START : FieldIdx.TERRAIN_END]),
            F[:, :, :, FieldIdx.TERRAIN_START : FieldIdx.TERRAIN_END]
        )
        F[:, :, :, FieldIdx.TERRAIN_START + T_NONE] = torch.where(
            t_expired,
            torch.ones_like(new_t_turns),
            F[:, :, :, FieldIdx.TERRAIN_START + T_NONE]
        )

    # Decrement Trick Room, Tailwind & Screens
    F[:, :, :, FieldIdx.TRICK_ROOM_TURNS] = torch.clamp(F[:, :, :, FieldIdx.TRICK_ROOM_TURNS] - 1.0, min=0.0)
    for side_idx in (
        FieldIdx.P1_TAILWIND_TURNS, FieldIdx.P1_REFLECT_TURNS, FieldIdx.P1_LIGHT_SCREEN_TURNS, FieldIdx.P1_AURORA_VEIL_TURNS,
        FieldIdx.P2_TAILWIND_TURNS, FieldIdx.P2_REFLECT_TURNS, FieldIdx.P2_LIGHT_SCREEN_TURNS, FieldIdx.P2_AURORA_VEIL_TURNS,
    ):
        F[:, :, :, side_idx] = torch.clamp(F[:, :, :, side_idx] - 1.0, min=0.0)

    # -------------------------------------------------------------------------
    # 5. VOLATILE RESETS (FLINCH, PROTECT STREAK, HELPING HAND)
    # -------------------------------------------------------------------------
    # Reset Flinch
    P[:, :, :, active_slot_tensor, MonIdx.FLINCHED] = 0.0

    # Reset Protect Counter if protect wasn't used
    was_protected = P[:, :, :, active_slot_tensor, MonIdx.PROTECT_ACTIVE] > 0.5
    protect_cnt = P[:, :, :, active_slot_tensor, MonIdx.PROTECT_COUNTER]
    P[:, :, :, active_slot_tensor, MonIdx.PROTECT_COUNTER] = torch.where(was_protected, protect_cnt, torch.zeros_like(protect_cnt))

    # Reset guard flags & helping hand
    P[:, :, :, active_slot_tensor, MonIdx.PROTECT_ACTIVE] = 0.0
    P[:, :, :, active_slot_tensor, MonIdx.WIDE_GUARD_ACTIVE] = 0.0
    P[:, :, :, active_slot_tensor, MonIdx.QUICK_GUARD_ACTIVE] = 0.0
    P[:, :, :, active_slot_tensor, MonIdx.HELPING_HAND_MULT] = 1.0

    # Increment active turns on survivors
    act_turns = P[:, :, :, active_slot_tensor, MonIdx.ACTIVE_TURNS]
    P[:, :, :, active_slot_tensor, MonIdx.ACTIVE_TURNS] = torch.where(
        active_hp_cur > 0.0,
        act_turns + 1.0,
        act_turns
    )

    # -------------------------------------------------------------------------
    # 6. MATCH TERMINATION & MONTE CARLO AGGREGATION
    # -------------------------------------------------------------------------
    p1_dead_mask = (P[:, :, :, :4, MonIdx.HP_CUR] <= 0.0).float()
    p1_fainted_count = torch.mean(torch.sum(p1_dead_mask, dim=3), dim=2)  # [B1, B2]

    p2_dead_mask = (P[:, :, :, 4:8, MonIdx.HP_CUR] <= 0.0).float()
    p2_fainted_count = torch.mean(torch.sum(p2_dead_mask, dim=3), dim=2)  # [B1, B2]

    p1_wiped = (p1_fainted_count >= 4.0)
    p2_wiped = (p2_fainted_count >= 4.0)

    is_terminal = (p1_wiped | p2_wiped).float()

    winner = torch.zeros((B1, B2), dtype=torch.int32, device=device)
    winner = torch.where(p2_wiped & ~p1_wiped, torch.tensor(1, dtype=torch.int32, device=device), winner)
    winner = torch.where(p1_wiped & ~p2_wiped, torch.tensor(2, dtype=torch.int32, device=device), winner)

    mean_hp = torch.mean(P[:, :, :, :, MonIdx.HP_CUR], dim=2)  # [B1, B2, 8]
    faint_prob = torch.mean((P[:, :, :, :, MonIdx.HP_CUR] <= 0.0).float(), dim=2)  # [B1, B2, 8]

    return EndOfTurnResult(
        F=F,
        P=P,
        M_moves=M_moves,
        mean_hp=mean_hp,
        faint_prob=faint_prob,
        p1_fainted_count=p1_fainted_count,
        p2_fainted_count=p2_fainted_count,
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
) -> EndOfTurnResult:
    """
    Executes Phase 5 (End-of-Turn resolution) across Monte Carlo samples.

    Resolves:
    1. Weather residual damage (Sandstorm).
    2. Status chip damage: Burn (-1/16), Poison (-1/8), Toxic (-N/16).
    3. Grounded Grassy Terrain healing (+1/16) and Leftovers healing (+1/16).
    4. Field counter decrements (Weather, Terrain, Trick Room, Tailwind, Screens).
    5. Volatile state resets (Flinch, Protect streak resets).
    6. Match termination evaluation.
    7. Forced bench replacements for fainted active slots.
    """
    is_torch = HAS_TORCH and isinstance(P_cascade, torch.Tensor)
    device = P_cascade.device if is_torch else None
    # ROUTE NATIVE PYTORCH TENSORS (ZERO HOST-TO-DEVICE TRANSFERS)
    if is_torch:
        return _execute_end_of_turn_torch(
            F=F_cascade,
            P=P_cascade,
            M_moves=M_cascade,
            tables=tables,
        )

    F_np = _to_numpy(F_cascade).copy()
    P_np = _to_numpy(P_cascade).copy()
    M_np = _to_numpy(M_cascade).copy()

    # Dimensions: [B1, B2, K, ...]
    B1, B2, K = P_np.shape[0], P_np.shape[1], P_np.shape[2]
    eot_events: List[str] = []

    type_rock = TYPE_TO_IDX["rock"]
    type_ground = TYPE_TO_IDX["ground"]
    type_steel = TYPE_TO_IDX["steel"]
    type_poison = TYPE_TO_IDX["poison"]

    for b1 in range(B1):
        for b2 in range(B2):
            for k in range(K):
                # -------------------------------------------------------------
                # 1. WEATHER DAMAGE (SANDSTORM)
                # -------------------------------------------------------------
                is_sand = (F_np[b1, b2, k, FieldIdx.WEATHER_START + W_SAND] > 0.5)
                if is_sand:
                    for slot in ACTIVE_SLOTS:
                        if P_np[b1, b2, k, slot, MonIdx.HP_CUR] > 0.0:
                            t1 = int(np.argmax(P_np[b1, b2, k, slot, MonIdx.TYPE1_START:MonIdx.TYPE1_END]))
                            t2_sum = np.sum(P_np[b1, b2, k, slot, MonIdx.TYPE2_START:MonIdx.TYPE2_END])
                            t2 = int(np.argmax(P_np[b1, b2, k, slot, MonIdx.TYPE2_START:MonIdx.TYPE2_END])) if t2_sum > 0.5 else -1

                            is_immune = (t1 in (type_rock, type_ground, type_steel)) or (t2 in (type_rock, type_ground, type_steel))
                            item_id = int(P_np[b1, b2, k, slot, MonIdx.ITEM_ID])
                            if item_id == ItemID.SAFETY_GOGGLES:
                                is_immune = True

                            if not is_immune:
                                max_hp = float(P_np[b1, b2, k, slot, MonIdx.HP_MAX])
                                chip = max(1.0, np.floor(max_hp / 16.0))
                                new_hp = max(0.0, float(P_np[b1, b2, k, slot, MonIdx.HP_CUR]) - chip)
                                P_np[b1, b2, k, slot, MonIdx.HP_CUR] = new_hp
                                if new_hp <= 0.0:
                                    P_np[b1, b2, k, slot, MonIdx.ALIVE_FLAG] = 0.0

                # -------------------------------------------------------------
                # 2. STATUS CHIP DAMAGE (BURN, POISON, TOXIC)
                # -------------------------------------------------------------
                for slot in ACTIVE_SLOTS:
                    if P_np[b1, b2, k, slot, MonIdx.HP_CUR] > 0.0:
                        max_hp = float(P_np[b1, b2, k, slot, MonIdx.HP_MAX])

                        # Burn (1/16 max HP)
                        if P_np[b1, b2, k, slot, MonIdx.STATUS_BURN] > 0.5:
                            b_chip = max(1.0, np.floor(max_hp / 16.0))
                            cur_hp = float(P_np[b1, b2, k, slot, MonIdx.HP_CUR])
                            new_hp = max(0.0, cur_hp - b_chip)
                            P_np[b1, b2, k, slot, MonIdx.HP_CUR] = new_hp
                            if new_hp <= 0.0:
                                P_np[b1, b2, k, slot, MonIdx.ALIVE_FLAG] = 0.0

                        # Poison (1/8 max HP)
                        elif P_np[b1, b2, k, slot, MonIdx.STATUS_POISON] > 0.5:
                            p_chip = max(1.0, np.floor(max_hp / 8.0))
                            cur_hp = float(P_np[b1, b2, k, slot, MonIdx.HP_CUR])
                            new_hp = max(0.0, cur_hp - p_chip)
                            P_np[b1, b2, k, slot, MonIdx.HP_CUR] = new_hp
                            if new_hp <= 0.0:
                                P_np[b1, b2, k, slot, MonIdx.ALIVE_FLAG] = 0.0

                        # Toxic (escalating N/16 max HP)
                        elif P_np[b1, b2, k, slot, MonIdx.STATUS_TOXIC] > 0.5:
                            tox_count = max(1.0, float(P_np[b1, b2, k, slot, MonIdx.TOXIC_COUNTER]))
                            t_chip = max(1.0, np.floor((max_hp * tox_count) / 16.0))
                            cur_hp = float(P_np[b1, b2, k, slot, MonIdx.HP_CUR])
                            new_hp = max(0.0, cur_hp - t_chip)
                            P_np[b1, b2, k, slot, MonIdx.HP_CUR] = new_hp
                            P_np[b1, b2, k, slot, MonIdx.TOXIC_COUNTER] = tox_count + 1.0
                            if new_hp <= 0.0:
                                P_np[b1, b2, k, slot, MonIdx.ALIVE_FLAG] = 0.0

                # -------------------------------------------------------------
                # 3. TERRAIN & ITEM HEALING (GRASSY TERRAIN & LEFTOVERS)
                # -------------------------------------------------------------
                is_grassy = (F_np[b1, b2, k, FieldIdx.TERRAIN_START + T_GRASSY] > 0.5)
                for slot in ACTIVE_SLOTS:
                    if P_np[b1, b2, k, slot, MonIdx.HP_CUR] > 0.0:
                        max_hp = float(P_np[b1, b2, k, slot, MonIdx.HP_MAX])
                        cur_hp = float(P_np[b1, b2, k, slot, MonIdx.HP_CUR])

                        # Grassy Terrain Healing (grounded only)
                        is_grounded = (P_np[b1, b2, k, slot, MonIdx.GROUNDED_FLAG] > 0.5)
                        if is_grassy and is_grounded and cur_hp < max_hp:
                            g_heal = max(1.0, np.floor(max_hp / 16.0))
                            cur_hp = min(max_hp, cur_hp + g_heal)
                            P_np[b1, b2, k, slot, MonIdx.HP_CUR] = cur_hp

                        # Leftovers Healing
                        item_id = int(P_np[b1, b2, k, slot, MonIdx.ITEM_ID])
                        item_active = (P_np[b1, b2, k, slot, MonIdx.ITEM_ACTIVE] > 0.5)
                        if item_active and item_id == ItemID.LEFTOVERS and cur_hp < max_hp:
                            l_heal = max(1.0, np.floor(max_hp / 16.0))
                            cur_hp = min(max_hp, cur_hp + l_heal)
                            P_np[b1, b2, k, slot, MonIdx.HP_CUR] = cur_hp

                # -------------------------------------------------------------
                # 4. FIELD & SIDE COUNTER DECREMENTS
                # -------------------------------------------------------------
                # Weather turns
                w_turns = float(F_np[b1, b2, k, FieldIdx.WEATHER_TURNS])
                if w_turns > 0.0:
                    w_turns -= 1.0
                    F_np[b1, b2, k, FieldIdx.WEATHER_TURNS] = w_turns
                    if w_turns == 0.0:
                        F_np[b1, b2, k, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END] = 0.0
                        F_np[b1, b2, k, FieldIdx.WEATHER_START + W_CLEAR] = 1.0

                # Terrain turns
                t_turns = float(F_np[b1, b2, k, FieldIdx.TERRAIN_TURNS])
                if t_turns > 0.0:
                    t_turns -= 1.0
                    F_np[b1, b2, k, FieldIdx.TERRAIN_TURNS] = t_turns
                    if t_turns == 0.0:
                        F_np[b1, b2, k, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END] = 0.0
                        F_np[b1, b2, k, FieldIdx.TERRAIN_START + T_NONE] = 1.0

                # Trick Room
                tr_turns = float(F_np[b1, b2, k, FieldIdx.TRICK_ROOM_TURNS])
                if tr_turns > 0.0:
                    F_np[b1, b2, k, FieldIdx.TRICK_ROOM_TURNS] = tr_turns - 1.0

                # Side Conditions (Tailwind, Screens)
                for side_idx in (
                    FieldIdx.P1_TAILWIND_TURNS, FieldIdx.P1_REFLECT_TURNS, FieldIdx.P1_LIGHT_SCREEN_TURNS, FieldIdx.P1_AURORA_VEIL_TURNS,
                    FieldIdx.P2_TAILWIND_TURNS, FieldIdx.P2_REFLECT_TURNS, FieldIdx.P2_LIGHT_SCREEN_TURNS, FieldIdx.P2_AURORA_VEIL_TURNS,
                ):
                    val = float(F_np[b1, b2, k, side_idx])
                    if val > 0.0:
                        F_np[b1, b2, k, side_idx] = val - 1.0

                # -------------------------------------------------------------
                # 5. VOLATILE RESETS (PROTECT, FLINCH, ACTIVE TURNS)
                # -------------------------------------------------------------
                for slot in ACTIVE_SLOTS:
                    if P_np[b1, b2, k, slot, MonIdx.HP_CUR] > 0.0:
                        # Reset flinch
                        P_np[b1, b2, k, slot, MonIdx.FLINCHED] = 0.0
                        # Increment active turns
                        P_np[b1, b2, k, slot, MonIdx.ACTIVE_TURNS] += 1.0

                        # If Protect was NOT used this turn, reset consecutive protect counter
                        was_protected = (P_np[b1, b2, k, slot, MonIdx.PROTECT_ACTIVE] > 0.5)
                        if not was_protected:
                            P_np[b1, b2, k, slot, MonIdx.PROTECT_COUNTER] = 0.0

                        # Reset volatile guard flags
                        P_np[b1, b2, k, slot, MonIdx.PROTECT_ACTIVE] = 0.0
                        P_np[b1, b2, k, slot, MonIdx.WIDE_GUARD_ACTIVE] = 0.0
                        P_np[b1, b2, k, slot, MonIdx.QUICK_GUARD_ACTIVE] = 0.0
                        P_np[b1, b2, k, slot, MonIdx.HELPING_HAND_MULT] = 1.0

                # -------------------------------------------------------------
                # 6. COMPILER TACTICAL PRIOR AUTO-REPLACEMENTS
                # -------------------------------------------------------------
                for is_p1, act_a, act_b, b_1, b_2 in (
                    (True, SLOT_P1A, SLOT_P1B, SLOT_P1_BENCH1, SLOT_P1_BENCH2),
                    (False, SLOT_P2A, SLOT_P2B, SLOT_P2_BENCH1, SLOT_P2_BENCH2),
                ):
                    for act_slot in (act_a, act_b):
                        if P_np[b1, b2, k, act_slot, MonIdx.HP_CUR] <= 0.0:
                            b1_alive = (P_np[b1, b2, k, b_1, MonIdx.HP_CUR] > 0.0)
                            b2_alive = (P_np[b1, b2, k, b_2, MonIdx.HP_CUR] > 0.0)

                            chosen_bench = -1
                            if b1_alive and not b2_alive:
                                chosen_bench = b_1
                            elif b2_alive and not b1_alive:
                                chosen_bench = b_2
                            elif b1_alive and b2_alive:
                                # Compiler Prior Heuristic: compare Spe / HP to promote highest equity
                                spe_1 = float(P_np[b1, b2, k, b_1, MonIdx.STAT_SPE])
                                spe_2 = float(P_np[b1, b2, k, b_2, MonIdx.STAT_SPE])
                                chosen_bench = b_1 if spe_1 >= spe_2 else b_2

                            if chosen_bench >= 0:
                                p_tmp = P_np[b1, b2, k, act_slot].copy()
                                P_np[b1, b2, k, act_slot] = P_np[b1, b2, k, chosen_bench]
                                P_np[b1, b2, k, chosen_bench] = p_tmp

                                m_tmp = M_np[b1, b2, k, act_slot].copy()
                                M_np[b1, b2, k, act_slot] = M_np[b1, b2, k, chosen_bench]
                                M_np[b1, b2, k, chosen_bench] = m_tmp

                                if k == 0 and len(eot_events) < 50:
                                    eot_events.append(
                                        f"Cell[{b1},{b2}]: Fainted {ACTIVE_SLOT_NAMES[act_slot]} replaced by bench slot {chosen_bench}."
                                    )

    # -------------------------------------------------------------------------
    # 7. MATCH TERMINATION EVALUATION
    # -------------------------------------------------------------------------
    # P1 faints: slots 0..3 with ALIVE_FLAG == 0.0
    p1_dead_mask = (P_np[:, :, :, 0:4, MonIdx.HP_CUR] <= 0.0).astype(np.float32)
    p1_fainted_count = np.mean(np.sum(p1_dead_mask, axis=3), axis=2)  # [B1, B2]

    p2_dead_mask = (P_np[:, :, :, 4:8, MonIdx.HP_CUR] <= 0.0).astype(np.float32)
    p2_fainted_count = np.mean(np.sum(p2_dead_mask, axis=3), axis=2)  # [B1, B2]

    p1_wiped = (p1_fainted_count >= 4.0)
    p2_wiped = (p2_fainted_count >= 4.0)

    is_terminal = (p1_wiped | p2_wiped).astype(np.float32)

    winner = np.zeros((B1, B2), dtype=np.int32)
    winner[p2_wiped & ~p1_wiped] = 1  # P1 wins
    winner[p1_wiped & ~p2_wiped] = 2  # P2 wins

    mean_hp = np.mean(P_np[:, :, :, :, MonIdx.HP_CUR], axis=2).astype(np.float32)
    faint_prob = np.mean((P_np[:, :, :, :, MonIdx.HP_CUR] <= 0.0).astype(np.float32), axis=2).astype(np.float32)

    if is_torch:
        F_out = torch.from_numpy(F_np).to(device=device)
        P_out = torch.from_numpy(P_np).to(device=device)
        M_out = torch.from_numpy(M_np).to(device=device)
        mean_hp_out = torch.from_numpy(mean_hp).to(device=device)
        faint_prob_out = torch.from_numpy(faint_prob).to(device=device)
        p1_faints_out = torch.from_numpy(p1_fainted_count).to(device=device)
        p2_faints_out = torch.from_numpy(p2_fainted_count).to(device=device)
        is_term_out = torch.from_numpy(is_terminal).to(device=device)
        winner_out = torch.from_numpy(winner).to(device=device)
    else:
        F_out = F_np
        P_out = P_np
        M_out = M_np
        mean_hp_out = mean_hp
        faint_prob_out = faint_prob
        p1_faints_out = p1_fainted_count
        p2_faints_out = p2_fainted_count
        is_term_out = is_terminal
        winner_out = winner

    return EndOfTurnResult(
        F=F_out,
        P=P_out,
        M_moves=M_out,
        mean_hp=mean_hp_out,
        faint_prob=faint_prob_out,
        p1_fainted_count=p1_faints_out,
        p2_fainted_count=p2_faints_out,
        is_terminal=is_term_out,
        winner=winner_out,
        eot_events=eot_events,
    )


# =============================================================================
# UNIFIED VGC TENSOR STATE MACHINE
# =============================================================================

class VgcTensorStateMachine:
    """
    Unified High-Level Branchless Pokémon VGC 4v4 Doubles State Machine.

    Executes complete official Regulation M-C turns from state vectors:
    Pre-Attack (Barriers 1-3) -> Attack Cascade (Phase 4) -> End-of-Turn (Phase 5).
    """

    def __init__(self, backend: str = "torch", device: Any = None) -> None:
        """Initializes state machine with pre-allocated Bilinear Lookup Tables."""
        self.backend = backend
        if backend == "torch" and HAS_TORCH:
            self.device = device or (torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu"))
        else:
            self.backend = "numpy"
            self.device = "cpu"

        self.tables = build_bilinear_lookup_tables(device=self.device)

    def step(
        self,
        F: TensorOrArray,
        P: TensorOrArray,
        M_moves: TensorOrArray,
        p1_choices: TensorOrArray,
        p2_choices: TensorOrArray,
        num_mc_samples: int = 16,
        replacement_choices: Optional[TensorOrArray] = None,
        rng_seed: Optional[int] = 42,
    ) -> StepResult:
        """
        Executes a single complete VGC Doubles turn.

        Args:
            F: Field Tensor `[B1, B2, 24]` or `[24]`.
            P: 8-Slot Roster Tensor `[B1, B2, 8, 84]` or `[8, 84]`.
            M_moves: Move Tensor `[B1, B2, 8, 4, 52]` or `[8, 4, 52]`.
            p1_choices: P1 action choices `[B1, 2]` or `[B1, B2, 2]`.
            p2_choices: P2 action choices `[B2, 2]` or `[B1, B2, 2]`.
            num_mc_samples: Number of Monte Carlo timelines (default 16).
            replacement_choices: Optional explicit bench replacement choices.
            rng_seed: Seed for secondary effects sampling.

        Returns:
            StepResult containing updated tensors, empirical KO probabilities,
            roll variance alerts, and match status.
        """
        # 1. Phases 1-3: Pre-Attack Synchronization Barriers
        pre_attack_res = execute_pre_attack_phases(
            F_init=F,
            P_init=P,
            M_moves_init=M_moves,
            p1_choices=p1_choices,
            p2_choices=p2_choices,
            tables=self.tables,
            rng_seed=rng_seed,
        )

        # 2. Phase 4: Vectorized Attack Cascade
        attack_res = execute_attack_cascade(
            F_init=pre_attack_res.F,
            P_init=pre_attack_res.P,
            M_moves_init=pre_attack_res.M_moves,
            p1_choices=p1_choices,
            p2_choices=p2_choices,
            pre_attack_res=pre_attack_res,
            tables=self.tables,
            num_mc_samples=num_mc_samples,
            rng_seed=rng_seed,
        )

        # 3. Phase 5: End-of-Turn Resolution
        eot_res = execute_end_of_turn(
            F_cascade=attack_res.F,
            P_cascade=attack_res.P,
            M_cascade=attack_res.M_moves,
            tables=self.tables,
            replacement_choices=replacement_choices,
        )

        return StepResult(
            F=eot_res.F,
            P=eot_res.P,
            M_moves=eot_res.M_moves,
            pre_attack=pre_attack_res,
            attack_cascade=attack_res,
            end_of_turn=eot_res,
            mean_hp=eot_res.mean_hp,
            faint_prob=eot_res.faint_prob,
            roll_variance_alert=attack_res.roll_variance_alert,
            is_terminal=eot_res.is_terminal,
            winner=eot_res.winner,
        )
