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
    AbilityID,
    BilinearLookupTables,
    FieldIdx,
    HAS_TORCH,
    ItemID,
    MonIdx,
    ROSTER_SLOTS,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    TYPE_TO_IDX,
    build_bilinear_lookup_tables,
)

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray


class AnalysisCancelledError(RuntimeError):
    """Raised when a running tensor simulation is cancelled cleanly via `cancel_event`."""


def _compute_safe_thread_budget(device: Any) -> int:
    """Compute a safe per-chunk thread budget `(B1 * B2 * K_chunk)` for any GPU VRAM or CPU."""
    if HAS_TORCH and isinstance(device, torch.device) and device.type == "cuda":
        try:
            free_bytes, _total_bytes = torch.cuda.mem_get_info(device)
            free_gb = free_bytes / (1024.0 ** 3)
            if free_gb >= 10.0:
                return 220000
            if free_gb >= 6.0:
                return 135000
            if free_gb >= 3.0:
                return 90000
            if free_gb >= 1.6:
                return 45000
            return 22500
        except Exception:
            return 65536
    return 65536


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
    P: "torch.Tensor",             # [B1, B2, K, 8, 87]
    M_moves: "torch.Tensor",       # [B1, B2, K, 8, 4, 59]
    tables: BilinearLookupTables,
    auto_promote: bool = False,
    extra_volatiles: Optional[Dict[str, "torch.Tensor"]] = None,
) -> EndOfTurnResult:
    """Pure PyTorch implementation of Phase 5 (End-of-Turn resolution + bench promotions)."""
    F = F.clone()
    P = P.clone()
    if auto_promote:
        M_moves = M_moves.clone()

    device = P.device
    B1, B2, K = P.shape[0], P.shape[1], P.shape[2]
    active_slot_tensor = torch.tensor(ACTIVE_SLOTS, dtype=torch.long, device=device)

    active_hp_cur = P[:, :, :, active_slot_tensor, MonIdx.HP_CUR]
    active_hp_max = P[:, :, :, active_slot_tensor, MonIdx.HP_MAX]
    active_alive = active_hp_cur > 0.0

    # 1. Weather residual damage & weather EoT healing/cures
    #    - Sandstorm: 1/16 max HP to non-Rock/Ground/Steel without Overcoat/Sand Force/Sand Veil/Sand Rush
    #    - Sun: Solar Power & Dry Skin lose 1/8 max HP
    #    - Rain: Dry Skin heals 1/8 max HP, Rain Dish heals 1/16 max HP, Hydration cures primary status
    #    - Snow: Ice Body heals 1/16 max HP
    active_abil = P[:, :, :, active_slot_tensor, MonIdx.ABILITY_ID]
    cloud_nine_active = torch.any(active_alive & (active_abil == float(AbilityID.CLOUD_NINE)), dim=-1, keepdim=True)
    is_sand = (F[:, :, :, FieldIdx.WEATHER_START + W_SAND] > 0.5).unsqueeze(-1) & (~cloud_nine_active)
    is_sun = (F[:, :, :, FieldIdx.WEATHER_START + W_SUN] > 0.5).unsqueeze(-1) & (~cloud_nine_active)
    is_rain = (F[:, :, :, FieldIdx.WEATHER_START + W_RAIN] > 0.5).unsqueeze(-1) & (~cloud_nine_active)
    is_snow = (F[:, :, :, FieldIdx.WEATHER_START + W_SNOW] > 0.5).unsqueeze(-1) & (~cloud_nine_active)
    t1 = torch.argmax(P[:, :, :, active_slot_tensor, MonIdx.TYPE1_START:MonIdx.TYPE1_END], dim=-1)
    t2 = torch.argmax(P[:, :, :, active_slot_tensor, MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1)
    has_t2 = torch.sum(P[:, :, :, active_slot_tensor, MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1) > 0.5

    rock_idx, ground_idx, steel_idx = TYPE_TO_IDX["rock"], TYPE_TO_IDX["ground"], TYPE_TO_IDX["steel"]
    sand_immune_types = (
        (t1 == rock_idx) | (t1 == ground_idx) | (t1 == steel_idx)
        | (has_t2 & ((t2 == rock_idx) | (t2 == ground_idx) | (t2 == steel_idx)))
    )
    sand_immune_abil = (
        (active_abil == float(AbilityID.OVERCOAT))
        | (active_abil == float(AbilityID.SAND_FORCE))
        | (active_abil == float(AbilityID.SAND_VEIL))
        | (active_abil == float(AbilityID.SAND_RUSH))
    )
    is_sand_immune = sand_immune_types | sand_immune_abil

    sand_chip = torch.where(
        is_sand & active_alive & (~is_sand_immune),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    sun_chip = torch.where(
        is_sun & active_alive & ((active_abil == float(AbilityID.SOLAR_POWER)) | (active_abil == float(AbilityID.DRY_SKIN))),
        torch.clamp(torch.floor(active_hp_max / 8.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    rain_dry_skin_heal = torch.where(
        is_rain & active_alive & (active_hp_cur < active_hp_max) & (active_abil == float(AbilityID.DRY_SKIN)),
        torch.clamp(torch.floor(active_hp_max / 8.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    rain_dish_heal = torch.where(
        is_rain & active_alive & (active_hp_cur < active_hp_max) & (active_abil == float(AbilityID.RAIN_DISH)),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    ice_body_heal = torch.where(
        is_snow & active_alive & (active_hp_cur < active_hp_max) & (active_abil == float(AbilityID.ICE_BODY)),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )
    active_hp_cur = torch.minimum(
        torch.clamp(
            active_hp_cur - sand_chip - sun_chip + rain_dry_skin_heal + rain_dish_heal + ice_body_heal,
            min=0.0,
        ),
        active_hp_max,
    )

    # Hydration: cures primary status conditions at End-of-Turn in active Rain
    hydration_cure = is_rain & (active_hp_cur > 0.0) & (active_abil == float(AbilityID.HYDRATION)) & (
        P[:, :, :, active_slot_tensor, MonIdx.STATUS_HEALTHY] < 0.5
    )
    if torch.any(hydration_cure):
        for st_i in range(7):
            tgt_bit = torch.ones_like(active_hp_cur) if st_i == 0 else torch.zeros_like(active_hp_cur)
            cur_bit = P[:, :, :, active_slot_tensor, MonIdx.STATUS_START + st_i]
            P[:, :, :, active_slot_tensor, MonIdx.STATUS_START + st_i] = torch.where(hydration_cure, tgt_bit, cur_bit)
        cur_tox = P[:, :, :, active_slot_tensor, MonIdx.TOXIC_COUNTER]
        P[:, :, :, active_slot_tensor, MonIdx.TOXIC_COUNTER] = torch.where(hydration_cure, torch.zeros_like(cur_tox), cur_tox)

    # 2. Terrain & Item Healing (Grassy Terrain +1/16 grounded, Leftovers +1/16)
    is_grassy = (F[:, :, :, FieldIdx.TERRAIN_START + T_GRASSY] > 0.5).unsqueeze(-1)
    is_grounded = P[:, :, :, active_slot_tensor, MonIdx.GROUNDED_FLAG] > 0.5
    grassy_heal = torch.where(
        is_grassy & is_grounded & (active_hp_cur > 0.0) & (active_hp_cur < active_hp_max),
        torch.clamp(torch.floor(active_hp_max / 16.0), min=1.0),
        torch.zeros_like(active_hp_cur),
    )

    item_act = P[:, :, :, active_slot_tensor, MonIdx.ITEM_ACTIVE] > 0.5
    item_id = P[:, :, :, active_slot_tensor, MonIdx.ITEM_ID]
    has_lefties = item_act & (item_id == float(ItemID.LEFTOVERS))
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

    # 3.5 Turn-Level Volatile EoT Residuals (Salt Cure, Leech Seed)
    if extra_volatiles:
        salt_cured_8 = extra_volatiles.get("salt_cured")
        if salt_cured_8 is not None:
            sc_act = salt_cured_8[:, :, :, active_slot_tensor] > 0.5
            water_idx, steel_idx = TYPE_TO_IDX["water"], TYPE_TO_IDX["steel"]
            is_water_or_steel = (
                (t1 == water_idx) | (t1 == steel_idx)
                | (has_t2 & ((t2 == water_idx) | (t2 == steel_idx)))
            )
            sc_div = torch.where(is_water_or_steel, torch.full_like(active_hp_max, 4.0), torch.full_like(active_hp_max, 8.0))
            sc_chip = torch.where(
                sc_act & (active_hp_cur > 0.0),
                torch.clamp(torch.floor(active_hp_max / sc_div), min=1.0),
                torch.zeros_like(active_hp_cur),
            )
            active_hp_cur = torch.clamp(active_hp_cur - sc_chip, min=0.0)

        P[:, :, :, active_slot_tensor, MonIdx.HP_CUR] = active_hp_cur
        P[:, :, :, active_slot_tensor, MonIdx.ALIVE_FLAG] = (active_hp_cur > 0.0).float()

        leech_src_8 = extra_volatiles.get("leech_seed_src")
        if leech_src_8 is not None:
            for act_slot in ACTIVE_SLOTS:
                ls_src = leech_src_8[:, :, :, act_slot]
                s_hp = P[:, :, :, act_slot, MonIdx.HP_CUR]
                s_max = P[:, :, :, act_slot, MonIdx.HP_MAX]
                ls_active = (ls_src > 0.5) & (s_hp > 0.0)
                if torch.any(ls_active):
                    ls_drain = torch.where(
                        ls_active,
                        torch.minimum(s_hp, torch.clamp(torch.floor(s_max / 8.0), min=1.0)),
                        torch.zeros_like(s_hp),
                    )
                    new_s_hp = torch.clamp(s_hp - ls_drain, min=0.0)
                    P[:, :, :, act_slot, MonIdx.HP_CUR] = new_s_hp
                    P[:, :, :, act_slot, MonIdx.ALIVE_FLAG] = (new_s_hp > 0.0).float()

                    src_idx = torch.clamp(torch.round(ls_src).long() - 1, min=0, max=7)
                    src_hp = torch.gather(P[:, :, :, :, MonIdx.HP_CUR], 3, src_idx.unsqueeze(-1)).squeeze(-1)
                    src_max = torch.gather(P[:, :, :, :, MonIdx.HP_MAX], 3, src_idx.unsqueeze(-1)).squeeze(-1)
                    src_heals = ls_active & (src_hp > 0.0)
                    new_src_hp = torch.minimum(
                        src_hp + torch.where(src_heals, ls_drain, torch.zeros_like(ls_drain)),
                        src_max,
                    )
                    P[:, :, :, :, MonIdx.HP_CUR].scatter_(3, src_idx.unsqueeze(-1), new_src_hp.unsqueeze(-1))
            active_hp_cur = P[:, :, :, active_slot_tensor, MonIdx.HP_CUR]
    else:
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
    # Keep newly triggered MUST_RECHARGE for surviving active mons; clear on fainted slots
    cur_rech_eot = P[:, :, :, active_slot_tensor, MonIdx.MUST_RECHARGE]
    P[:, :, :, active_slot_tensor, MonIdx.MUST_RECHARGE] = torch.where(
        active_hp_cur > 0.0, cur_rech_eot, torch.zeros_like(cur_rech_eot)
    )
    # Throat Chop counter decrement & fainted cleanup for 2-turn persistent states
    P[:, :, :, active_slot_tensor, MonIdx.THROAT_CHOP_TURNS] = torch.where(
        active_hp_cur > 0.0,
        torch.clamp(P[:, :, :, active_slot_tensor, MonIdx.THROAT_CHOP_TURNS] - 1.0, min=0.0),
        torch.zeros_like(active_hp_cur),
    )
    for _two_turn_idx in (
        MonIdx.LAST_MOVE_FAILED,
        MonIdx.CHARGED_MOVE_IDX,
        MonIdx.SEMI_INVULN,
        MonIdx.GLAIVE_RUSH_VULN,
        MonIdx.CHARGE_ACTIVE,
    ):
        cur_tt = P[:, :, :, active_slot_tensor, _two_turn_idx]
        P[:, :, :, active_slot_tensor, _two_turn_idx] = torch.where(
            active_hp_cur > 0.0, cur_tt, torch.zeros_like(cur_tt)
        )

    # Persistent Yawn progression: 2.0 -> Sleep at EoT (unless blocked by Electric/Misty Terrain or statused), 1.0 -> 2.0
    cur_yawn_eot = P[:, :, :, active_slot_tensor, MonIdx.YAWN_ACTIVE]
    yawn_sleeps = (
        (active_hp_cur > 0.0)
        & (cur_yawn_eot >= 1.9)
        & (P[:, :, :, active_slot_tensor, MonIdx.STATUS_HEALTHY] > 0.5)
    )
    if torch.any(yawn_sleeps):
        elec_or_misty_eot = (
            (F[:, :, :, FieldIdx.TERRAIN_START + T_ELECTRIC] > 0.5)
            | (F[:, :, :, FieldIdx.TERRAIN_START + T_MISTY] > 0.5)
        ).unsqueeze(-1)
        grav_eot = (F[:, :, :, FieldIdx.GRAVITY_TURNS] > 0.0).unsqueeze(-1)
        act_gr_eot = (P[:, :, :, active_slot_tensor, MonIdx.GROUNDED_FLAG] > 0.5) | grav_eot
        sun_eot = (F[:, :, :, FieldIdx.WEATHER_START + W_SUN] > 0.5).unsqueeze(-1)
        lg_eot = (active_abil == float(AbilityID.LEAF_GUARD)) & sun_eot
        yawn_lands = yawn_sleeps & (~(act_gr_eot & elec_or_misty_eot)) & (~lg_eot)
        if torch.any(yawn_lands):
            P[:, :, :, active_slot_tensor, MonIdx.STATUS_HEALTHY] = torch.where(
                yawn_lands, torch.zeros_like(active_hp_cur), P[:, :, :, active_slot_tensor, MonIdx.STATUS_HEALTHY]
            )
            P[:, :, :, active_slot_tensor, MonIdx.STATUS_SLEEP] = torch.where(
                yawn_lands, torch.ones_like(active_hp_cur), P[:, :, :, active_slot_tensor, MonIdx.STATUS_SLEEP]
            )
            # Immediate Chesto / Lum Berry wake-up
            act_it_eot = P[:, :, :, active_slot_tensor, MonIdx.ITEM_ID]
            act_it_on = P[:, :, :, active_slot_tensor, MonIdx.ITEM_ACTIVE] > 0.5
            berry_wakes = yawn_lands & act_it_on & (
                (act_it_eot == float(ItemID.CHESTO_BERRY)) | (act_it_eot == float(ItemID.LUM_BERRY))
            )
            if torch.any(berry_wakes):
                P[:, :, :, active_slot_tensor, MonIdx.STATUS_SLEEP] = torch.where(
                    berry_wakes, torch.zeros_like(active_hp_cur), P[:, :, :, active_slot_tensor, MonIdx.STATUS_SLEEP]
                )
                P[:, :, :, active_slot_tensor, MonIdx.STATUS_HEALTHY] = torch.where(
                    berry_wakes, torch.ones_like(active_hp_cur), P[:, :, :, active_slot_tensor, MonIdx.STATUS_HEALTHY]
                )
                P[:, :, :, active_slot_tensor, MonIdx.ITEM_ACTIVE] = torch.where(
                    berry_wakes, torch.zeros_like(active_hp_cur), P[:, :, :, active_slot_tensor, MonIdx.ITEM_ACTIVE]
                )
                unb_yw = berry_wakes & (active_abil == float(AbilityID.UNBURDEN))
                P[:, :, :, active_slot_tensor, MonIdx.UNBURDEN_ACTIVE] = torch.where(
                    unb_yw, torch.ones_like(active_hp_cur), P[:, :, :, active_slot_tensor, MonIdx.UNBURDEN_ACTIVE]
                )
    next_yawn_eot = torch.where(
        active_hp_cur <= 0.0,
        torch.zeros_like(cur_yawn_eot),
        torch.where(
            cur_yawn_eot >= 1.9,
            torch.zeros_like(cur_yawn_eot),
            torch.where(cur_yawn_eot >= 0.9, torch.full_like(cur_yawn_eot, 2.0), torch.zeros_like(cur_yawn_eot)),
        ),
    )
    P[:, :, :, active_slot_tensor, MonIdx.YAWN_ACTIVE] = next_yawn_eot

    act_turns = P[:, :, :, active_slot_tensor, MonIdx.ACTIVE_TURNS]
    P[:, :, :, active_slot_tensor, MonIdx.ACTIVE_TURNS] = torch.where(
        active_hp_cur > 0.0, act_turns + 1.0, act_turns
    )

    # Speed Boost (+1 Spe at End of Turn for alive active Pokémon)
    has_speed_boost = (active_hp_cur > 0.0) & (active_abil == float(AbilityID.SPEED_BOOST))
    if torch.any(has_speed_boost):
        cur_spe_b = P[:, :, :, active_slot_tensor, MonIdx.BOOST_SPE]
        P[:, :, :, active_slot_tensor, MonIdx.BOOST_SPE] = torch.clamp(
            cur_spe_b + torch.where(has_speed_boost, torch.ones_like(cur_spe_b), torch.zeros_like(cur_spe_b)),
            min=-6.0,
            max=6.0,
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
    extra_volatiles: Optional[Dict[str, TensorOrArray]] = None,
) -> EndOfTurnResult:
    """Execute Phase 5 (End-of-Turn resolution) across `[B1, B2, K]` simulation threads."""
    do_promote = auto_promote or (replacement_choices is not None)
    is_torch = HAS_TORCH and isinstance(P_cascade, torch.Tensor)
    if is_torch:
        ev_t = None
        if extra_volatiles:
            ev_t = {
                k: (v if isinstance(v, torch.Tensor) else torch.from_numpy(np.asarray(v, dtype=np.float32)).to(P_cascade.device))
                for k, v in extra_volatiles.items()
            }
        return _execute_end_of_turn_torch(
            F_cascade, P_cascade, M_cascade, tables, auto_promote=do_promote, extra_volatiles=ev_t
        )

    if HAS_TORCH:
        dev = torch.device("cpu")
        tables_t = build_bilinear_lookup_tables(device=dev)
        ev_t = None
        if extra_volatiles:
            ev_t = {
                k: (v.detach().cpu() if isinstance(v, torch.Tensor) else torch.from_numpy(np.asarray(v, dtype=np.float32)))
                for k, v in extra_volatiles.items()
            }
        res_t = _execute_end_of_turn_torch(
            torch.from_numpy(np.asarray(F_cascade, dtype=np.float32)),
            torch.from_numpy(np.asarray(P_cascade, dtype=np.float32)),
            torch.from_numpy(np.asarray(M_cascade, dtype=np.float32)),
            tables_t,
            auto_promote=do_promote,
            extra_volatiles=ev_t,
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

from .victory_equity import (
    EQUITY_ENGINE_VERSION,
    VictoryEquityBreakdown,
    VictoryEquityWeights,
    compute_victory_equity_torch,
)

def compute_per_thread_board_utility_torch(
    F_eot: "torch.Tensor",  # [B1, B2, K, 26]
    P_eot: "torch.Tensor",  # [B1, B2, K, 8, 96]
    extra_volatiles: Optional[Dict[str, "torch.Tensor"]] = None,
    M_moves: Optional["torch.Tensor"] = None,
    tables: Optional[BilinearLookupTables] = None,
    weights: Optional[VictoryEquityWeights] = None,
) -> "torch.Tensor":
    """Evaluate exact 8-pillar scalar Victory Equity $U_{b_1, b_2, k}$ for `trainer_1` vs `trainer_2`."""
    return compute_victory_equity_torch(
        F_eot=F_eot,
        P_eot=P_eot,
        M_moves=M_moves,
        tables=tables,
        extra_volatiles=extra_volatiles,
        weights=weights,
        return_breakdown=False,
    )


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
# 3. UNIFIED VGC TENSOR STATE MACHINE (2D TILING + CHUNKED K=1000+ SIMULATIONS)
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
        equity_weights: Optional[Any] = None,
    ) -> None:
        """Initialize state machine with pre-allocated Bilinear Lookup Tables, Logic Pruner, and Equity Weights."""
        from .victory_equity import VictoryEquityWeights

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
        self.equity_weights: VictoryEquityWeights = (
            equity_weights if isinstance(equity_weights, VictoryEquityWeights) else VictoryEquityWeights.load_or_default()
        )

    def _step_single_tile(
        self,
        F: TensorOrArray,
        P: TensorOrArray,
        M_moves: TensorOrArray,
        trainer_1_choices: TensorOrArray,
        trainer_2_choices: TensorOrArray,
        num_mc_samples: int,
        replacement_choices: Optional[TensorOrArray],
        rng_seed: int,
        risk_aversion_lambda: float,
        max_sim_chunk_size: int,
        resolve_lead_entry_abilities: bool = False,
        _timings_accum: Optional[Dict[str, float]] = None,
        cancel_event: Optional[Any] = None,
        chunk_callback: Optional[Any] = None,
    ) -> StepResult:
        """Execute a single `(tb1, tb2)` tile across `num_mc_samples` discrete RNG threads."""
        import time as _time

        if cancel_event is not None and cancel_event.is_set():
            raise AnalysisCancelledError("Simulation cancelled before tile start.")

        lam = float(risk_aversion_lambda)
        seed_base = int(rng_seed)
        K_total = int(max(1, num_mc_samples))
        is_torch_in = HAS_TORCH and isinstance(P, torch.Tensor)

        _t0 = _time.perf_counter() if _timings_accum is not None else 0.0
        pre_attack_res = execute_pre_attack_phases(
            F_init=F,
            P_init=P,
            M_moves_init=M_moves,
            trainer_1_choices=trainer_1_choices,
            trainer_2_choices=trainer_2_choices,
            tables=self.tables,
            rng_seed=seed_base,
            resolve_lead_entry_abilities=resolve_lead_entry_abilities,
        )
        if _timings_accum is not None:
            _t1 = _time.perf_counter()
            _timings_accum["pre_attack_s"] = _timings_accum.get("pre_attack_s", 0.0) + (_t1 - _t0)

        B1, B2 = pre_attack_res.P.shape[0], pre_attack_res.P.shape[1]
        dev_obj = P.device if is_torch_in else None
        max_threads_per_chunk = _compute_safe_thread_budget(dev_obj)
        effective_chunk_size = max(1, min(int(max_sim_chunk_size), max_threads_per_chunk // max(1, B1 * B2)))

        if K_total <= effective_chunk_size:
            if cancel_event is not None and cancel_event.is_set():
                raise AnalysisCancelledError("Simulation cancelled before attack cascade.")
            _ta0 = _time.perf_counter() if _timings_accum is not None else 0.0
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
            if _timings_accum is not None:
                _ta1 = _time.perf_counter()
                _timings_accum["attack_s"] = _timings_accum.get("attack_s", 0.0) + (_ta1 - _ta0)
            eot_res = execute_end_of_turn(
                F_cascade=attack_res.F,
                P_cascade=attack_res.P,
                M_cascade=attack_res.M_moves,
                tables=self.tables,
                replacement_choices=replacement_choices,
                extra_volatiles=attack_res.extra_volatiles,
            )

            if is_torch_in:
                u_k = compute_per_thread_board_utility_torch(
                    eot_res.F,
                    eot_res.P,
                    extra_volatiles=attack_res.extra_volatiles,
                    M_moves=eot_res.M_moves,
                    tables=self.tables,
                    weights=self.equity_weights,
                )
                stats = aggregate_simulation_statistics_torch(u_k, eot_res.faint_prob, lam)
            else:
                ev_t = (
                    {k: torch.from_numpy(np.asarray(v, dtype=np.float32)) for k, v in attack_res.extra_volatiles.items()}
                    if attack_res.extra_volatiles
                    else None
                )
                u_k_t = compute_per_thread_board_utility_torch(
                    torch.from_numpy(eot_res.F),
                    torch.from_numpy(eot_res.P),
                    extra_volatiles=ev_t,
                    M_moves=torch.from_numpy(eot_res.M_moves),
                    tables=self.tables,
                    weights=self.equity_weights,
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
            if _timings_accum is not None:
                _te1 = _time.perf_counter()
                _timings_accum["eot_s"] = _timings_accum.get("eot_s", 0.0) + (_te1 - _ta1)

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
        total_chunks = max(1, (K_total + effective_chunk_size - 1) // effective_chunk_size)
        while remaining > 0:
            if cancel_event is not None and cancel_event.is_set():
                raise AnalysisCancelledError("Simulation cancelled during Monte Carlo chunking.")
            k_chunk = min(effective_chunk_size, remaining)
            weight = float(k_chunk) / float(K_total)
            chunk_seed = seed_base + chunk_idx * 100003

            _tc0 = _time.perf_counter() if _timings_accum is not None else 0.0
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
            if _timings_accum is not None:
                _tc1 = _time.perf_counter()
                _timings_accum["attack_s"] = _timings_accum.get("attack_s", 0.0) + (_tc1 - _tc0)
            eot_c = execute_end_of_turn(
                F_cascade=att_c.F,
                P_cascade=att_c.P,
                M_cascade=att_c.M_moves,
                tables=self.tables,
                replacement_choices=replacement_choices,
                extra_volatiles=att_c.extra_volatiles,
            )
            if _timings_accum is not None:
                _tc2 = _time.perf_counter()
                _timings_accum["eot_s"] = _timings_accum.get("eot_s", 0.0) + (_tc2 - _tc1)

            f_t = eot_c.F if is_torch_in else torch.from_numpy(eot_c.F)
            p_t = eot_c.P if is_torch_in else torch.from_numpy(eot_c.P)
            m_t = eot_c.M_moves if is_torch_in else torch.from_numpy(eot_c.M_moves)
            ev_c = (
                att_c.extra_volatiles
                if is_torch_in
                else (
                    {k: torch.from_numpy(np.asarray(v, dtype=np.float32)) for k, v in att_c.extra_volatiles.items()}
                    if att_c.extra_volatiles
                    else None
                )
            )
            u_c = compute_per_thread_board_utility_torch(
                f_t,
                p_t,
                extra_volatiles=ev_c,
                M_moves=m_t,
                tables=self.tables,
                weights=getattr(self, "equity_weights", None),
            )
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

            if first_attack_res is None:
                first_attack_res = att_c
                first_eot_res = eot_c
            else:
                del att_c, eot_c

            remaining -= k_chunk
            chunk_idx += 1
            if chunk_callback is not None:
                chunk_callback(chunk_idx, total_chunks, K_total - remaining, K_total)

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
        tile_size: Optional[int] = None,
        resolve_lead_entry_abilities: bool = False,
        progress_callback: Optional[Any] = None,
        cancel_event: Optional[Any] = None,
        **kwargs: Any,
    ) -> StepResult:
        """Execute a single VGC Doubles turn across `[B1, B2]` action pairs and `num_mc_samples` discrete RNG threads.

        Supports automatic **2D Tiling over `(B1, B2)`** so arbitrarily large unpruned strategy grids
        (up to `676 x 676`) execute in bounded `O(1)` memory on both GPU and CPU while preserving
        exact bit-for-bit mathematical equivalence with full-matrix execution!
        """
        if trainer_1_choices is None or trainer_2_choices is None:
            raise ValueError("Both trainer_1_choices and trainer_2_choices must be provided.")
        if cancel_event is not None and cancel_event.is_set():
            raise AnalysisCancelledError("Simulation cancelled before step start.")

        lam = self.risk_aversion_lambda if risk_aversion_lambda is None else float(risk_aversion_lambda)
        seed_base = int(rng_seed if rng_seed is not None else 42)
        K_total = int(max(1, num_mc_samples))
        is_torch_in = HAS_TORCH and isinstance(P, torch.Tensor)

        B1 = int(trainer_1_choices.shape[0])
        B2 = int(trainer_2_choices.shape[0] if trainer_2_choices.ndim == 2 else trainer_2_choices.shape[1])

        # Adaptive tile_size scaled by device AND K_total so every tile completes rapidly (<1s)
        # with bounded VRAM/RAM and frequent progress/cancellation checkpoints.
        if tile_size is None:
            is_cuda = is_torch_in and P.is_cuda
            if is_cuda:
                if K_total >= 512:
                    eff_tile = 16
                elif K_total >= 256:
                    eff_tile = 24
                else:
                    eff_tile = 32
            else:
                if K_total >= 256:
                    eff_tile = 8
                elif K_total >= 128:
                    eff_tile = 12
                else:
                    eff_tile = 16
        else:
            eff_tile = max(1, int(tile_size))

        timings_accum: Optional[Dict[str, float]] = {} if progress_callback is not None else None

        def _count_pre_stats(pre_res: Any) -> Tuple[int, int, int]:
            sw = pre_res.switched_mask
            mg = pre_res.mega_evolved_mask
            st = pre_res.speed_tie_alert
            if HAS_TORCH and isinstance(sw, torch.Tensor):
                sw_c = int((sw > 0.5).any(dim=-1).sum().item())
                mg_c = int((mg > 0.5).any(dim=-1).sum().item())
                st_c = int((st > 0.5).sum().item())
            else:
                sw_c = int(np.sum(np.any(np.asarray(sw) > 0.5, axis=-1)))
                mg_c = int(np.sum(np.any(np.asarray(mg) > 0.5, axis=-1)))
                st_c = int(np.sum(np.asarray(st) > 0.5))
            return sw_c, mg_c, st_c

        # If the matrix fits inside a single tile (or input F/P/M_moves are already 3D/4D expanded), run directly
        if (B1 <= eff_tile and B2 <= eff_tile) or P.ndim > 2 or trainer_1_choices.ndim != 2 or trainer_2_choices.ndim != 2:
            tot_cells_s = B1 * B2
            tot_traj_s = tot_cells_s * K_total

            def _single_chunk_cb(c_idx: int, c_tot: int, k_done: int, k_all: int) -> None:
                if progress_callback is not None and c_tot > 1:
                    progress_callback(
                        {
                            "event": "tile_progress",
                            "tile": 1,
                            "total_tiles": 1,
                            "chunk": c_idx,
                            "total_chunks": c_tot,
                            "cells_done": tot_cells_s,
                            "total_cells": tot_cells_s,
                            "trajectories_done": tot_cells_s * k_done,
                            "total_trajectories": tot_traj_s,
                        }
                    )

            res_single = self._step_single_tile(
                F=F,
                P=P,
                M_moves=M_moves,
                trainer_1_choices=trainer_1_choices,
                trainer_2_choices=trainer_2_choices,
                num_mc_samples=K_total,
                replacement_choices=replacement_choices,
                rng_seed=seed_base,
                risk_aversion_lambda=lam,
                max_sim_chunk_size=max_sim_chunk_size,
                resolve_lead_entry_abilities=resolve_lead_entry_abilities,
                _timings_accum=timings_accum,
                cancel_event=cancel_event,
                chunk_callback=_single_chunk_cb if progress_callback is not None else None,
            )
            if progress_callback is not None and timings_accum is not None:
                sw_c, mg_c, st_c = _count_pre_stats(res_single.pre_attack)
                progress_callback(
                    {
                        "event": "tile_progress",
                        "tile": 1,
                        "total_tiles": 1,
                        "cells_done": tot_cells_s,
                        "total_cells": tot_cells_s,
                        "trajectories_done": tot_traj_s,
                        "total_trajectories": tot_traj_s,
                    }
                )
                progress_callback(
                    {
                        "event": "phases_summary",
                        "pre_attack_s": timings_accum.get("pre_attack_s", 0.01),
                        "attack_s": timings_accum.get("attack_s", 0.01),
                        "eot_s": timings_accum.get("eot_s", 0.01),
                        "switch_cells": sw_c,
                        "mega_cells": mg_c,
                        "speed_tie_cells": st_c,
                        "total_tiles": 1,
                        "total_cells": tot_cells_s,
                        "total_trajectories": tot_traj_s,
                    }
                )
            return res_single

        # 2D Tiling across (B1, B2) with exact global RNG coordinate context
        from .rng_engine import rng_tile_context

        dev = P.device if is_torch_in else torch.device("cpu")
        mean_u_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        std_u_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        cvar_10_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        p5_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        p95_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        risk_adj_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        win_prob_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)

        mean_hp_mat = torch.zeros((B1, B2, ROSTER_SLOTS), dtype=torch.float32, device=dev)
        faint_prob_mat = torch.zeros((B1, B2, ROSTER_SLOTS), dtype=torch.float32, device=dev)
        surv_prob_mat = torch.zeros((B1, B2, ROSTER_SLOTS), dtype=torch.float32, device=dev)
        roll_var_mat = torch.zeros((B1, B2, ROSTER_SLOTS), dtype=torch.float32, device=dev)
        mean_dmg_mat = torch.zeros((B1, B2, 4), dtype=torch.float32, device=dev)
        hit_rate_mat = torch.zeros((B1, B2, 4), dtype=torch.float32, device=dev)
        crit_rate_mat = torch.zeros((B1, B2, 4), dtype=torch.float32, device=dev)
        t1_faints_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        t2_faints_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        is_term_mat = torch.zeros((B1, B2), dtype=torch.float32, device=dev)
        winner_mat = torch.zeros((B1, B2), dtype=torch.int32, device=dev)

        first_tile_res: Optional[StepResult] = None
        n_tiles_i = (B1 + eff_tile - 1) // eff_tile
        n_tiles_j = (B2 + eff_tile - 1) // eff_tile
        total_tiles = max(1, n_tiles_i * n_tiles_j)
        total_cells = B1 * B2
        total_trajectories = total_cells * K_total
        tile_counter = 0
        cells_done = 0
        switch_cells_total = 0
        mega_cells_total = 0
        speed_tie_cells_total = 0

        for i0 in range(0, B1, eff_tile):
            i1 = min(B1, i0 + eff_tile)
            t1_sub = trainer_1_choices[i0:i1]
            for j0 in range(0, B2, eff_tile):
                if cancel_event is not None and cancel_event.is_set():
                    raise AnalysisCancelledError("Simulation cancelled between 2D tiles.")
                j1 = min(B2, j0 + eff_tile)
                t2_sub = trainer_2_choices[j0:j1]
                tile_cells = (i1 - i0) * (j1 - j0)
                cur_tile_num = tile_counter + 1
                base_traj = cells_done * K_total

                def _tile_chunk_cb(
                    c_idx: int,
                    c_tot: int,
                    k_done: int,
                    k_all: int,
                    _tn: int = cur_tile_num,
                    _bt: int = base_traj,
                    _tc: int = tile_cells,
                ) -> None:
                    if progress_callback is not None and c_tot > 1:
                        progress_callback(
                            {
                                "event": "tile_progress",
                                "tile": _tn,
                                "total_tiles": total_tiles,
                                "chunk": c_idx,
                                "total_chunks": c_tot,
                                "cells_done": cells_done,
                                "total_cells": total_cells,
                                "trajectories_done": _bt + _tc * k_done,
                                "total_trajectories": total_trajectories,
                            }
                        )

                with rng_tile_context(i0, j0, B1, B2):
                    tile_res = self._step_single_tile(
                        F=F,
                        P=P,
                        M_moves=M_moves,
                        trainer_1_choices=t1_sub,
                        trainer_2_choices=t2_sub,
                        num_mc_samples=K_total,
                        replacement_choices=replacement_choices,
                        rng_seed=seed_base,
                        risk_aversion_lambda=lam,
                        max_sim_chunk_size=max_sim_chunk_size,
                        resolve_lead_entry_abilities=resolve_lead_entry_abilities,
                        _timings_accum=timings_accum,
                        cancel_event=cancel_event,
                        chunk_callback=_tile_chunk_cb if progress_callback is not None else None,
                    )

                if first_tile_res is None:
                    first_tile_res = tile_res

                if progress_callback is not None:
                    tile_counter += 1
                    cells_done += tile_cells
                    sw_c, mg_c, st_c = _count_pre_stats(tile_res.pre_attack)
                    switch_cells_total += sw_c
                    mega_cells_total += mg_c
                    speed_tie_cells_total += st_c
                    progress_callback(
                        {
                            "event": "tile_progress",
                            "tile": tile_counter,
                            "total_tiles": total_tiles,
                            "cells_done": cells_done,
                            "total_cells": total_cells,
                            "trajectories_done": cells_done * K_total,
                            "total_trajectories": total_trajectories,
                        }
                    )

                if is_torch_in:
                    mean_u_mat[i0:i1, j0:j1] = tile_res.stats.mean_utility
                    std_u_mat[i0:i1, j0:j1] = tile_res.stats.std_utility
                    cvar_10_mat[i0:i1, j0:j1] = tile_res.stats.cvar_10_utility
                    p5_mat[i0:i1, j0:j1] = tile_res.stats.p5_utility
                    p95_mat[i0:i1, j0:j1] = tile_res.stats.p95_utility
                    risk_adj_mat[i0:i1, j0:j1] = tile_res.stats.risk_adjusted_utility
                    win_prob_mat[i0:i1, j0:j1] = tile_res.stats.win_turn_prob
                    mean_hp_mat[i0:i1, j0:j1] = tile_res.mean_hp
                    faint_prob_mat[i0:i1, j0:j1] = tile_res.faint_prob
                    surv_prob_mat[i0:i1, j0:j1] = tile_res.survival_prob
                    roll_var_mat[i0:i1, j0:j1] = tile_res.roll_variance_alert
                    mean_dmg_mat[i0:i1, j0:j1] = tile_res.attack_cascade.mean_damage_dealt
                    hit_rate_mat[i0:i1, j0:j1] = tile_res.attack_cascade.hit_rate_observed
                    crit_rate_mat[i0:i1, j0:j1] = tile_res.attack_cascade.crit_rate_observed
                    t1_faints_mat[i0:i1, j0:j1] = tile_res.end_of_turn.trainer_1_fainted_count
                    t2_faints_mat[i0:i1, j0:j1] = tile_res.end_of_turn.trainer_2_fainted_count
                    is_term_mat[i0:i1, j0:j1] = tile_res.is_terminal
                    winner_mat[i0:i1, j0:j1] = tile_res.winner
                else:
                    mean_u_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.stats.mean_utility)
                    std_u_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.stats.std_utility)
                    cvar_10_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.stats.cvar_10_utility)
                    p5_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.stats.p5_utility)
                    p95_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.stats.p95_utility)
                    risk_adj_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.stats.risk_adjusted_utility)
                    win_prob_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.stats.win_turn_prob)
                    mean_hp_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.mean_hp)
                    faint_prob_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.faint_prob)
                    surv_prob_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.survival_prob)
                    roll_var_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.roll_variance_alert)
                    mean_dmg_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.attack_cascade.mean_damage_dealt)
                    hit_rate_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.attack_cascade.hit_rate_observed)
                    crit_rate_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.attack_cascade.crit_rate_observed)
                    t1_faints_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.end_of_turn.trainer_1_fainted_count)
                    t2_faints_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.end_of_turn.trainer_2_fainted_count)
                    is_term_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.is_terminal)
                    winner_mat[i0:i1, j0:j1] = torch.from_numpy(tile_res.winner)

        assert first_tile_res is not None
        if progress_callback is not None and timings_accum is not None:
            progress_callback(
                {
                    "event": "phases_summary",
                    "pre_attack_s": timings_accum.get("pre_attack_s", 0.01),
                    "attack_s": timings_accum.get("attack_s", 0.01),
                    "eot_s": timings_accum.get("eot_s", 0.01),
                    "switch_cells": switch_cells_total,
                    "mega_cells": mega_cells_total,
                    "speed_tie_cells": speed_tie_cells_total,
                    "total_tiles": total_tiles,
                    "total_cells": total_cells,
                    "total_trajectories": total_trajectories,
                }
            )
        if is_torch_in:
            stats = TurnSimulationStatistics(
                num_simulations=K_total,
                risk_aversion_lambda=lam,
                mean_utility=mean_u_mat,
                std_utility=std_u_mat,
                cvar_10_utility=cvar_10_mat,
                p5_utility=p5_mat,
                p95_utility=p95_mat,
                risk_adjusted_utility=risk_adj_mat,
                win_turn_prob=win_prob_mat,
                faint_prob=faint_prob_mat,
                survival_prob=surv_prob_mat,
            )
            agg_attack = AttackCascadeResult(
                F=first_tile_res.attack_cascade.F,
                P=first_tile_res.attack_cascade.P,
                M_moves=first_tile_res.attack_cascade.M_moves,
                mean_hp=mean_hp_mat,
                faint_prob=faint_prob_mat,
                roll_variance_alert=roll_var_mat,
                mean_damage_dealt=mean_dmg_mat,
                hit_rate_observed=hit_rate_mat,
                crit_rate_observed=crit_rate_mat,
                redirection_events=first_tile_res.attack_cascade.redirection_events,
            )
            agg_eot = EndOfTurnResult(
                F=first_tile_res.end_of_turn.F,
                P=first_tile_res.end_of_turn.P,
                M_moves=first_tile_res.end_of_turn.M_moves,
                mean_hp=mean_hp_mat,
                faint_prob=faint_prob_mat,
                survival_prob=surv_prob_mat,
                trainer_1_fainted_count=t1_faints_mat,
                trainer_2_fainted_count=t2_faints_mat,
                is_terminal=is_term_mat,
                winner=winner_mat,
                eot_events=first_tile_res.end_of_turn.eot_events,
            )
            return StepResult(
                F=first_tile_res.F,
                P=first_tile_res.P,
                M_moves=first_tile_res.M_moves,
                pre_attack=first_tile_res.pre_attack,
                attack_cascade=agg_attack,
                end_of_turn=agg_eot,
                stats=stats,
                mean_hp=mean_hp_mat,
                faint_prob=faint_prob_mat,
                survival_prob=surv_prob_mat,
                roll_variance_alert=roll_var_mat,
                is_terminal=is_term_mat,
                winner=winner_mat,
            )

        stats_np = TurnSimulationStatistics(
            num_simulations=K_total,
            risk_aversion_lambda=lam,
            mean_utility=mean_u_mat.numpy(),
            std_utility=std_u_mat.numpy(),
            cvar_10_utility=cvar_10_mat.numpy(),
            p5_utility=p5_mat.numpy(),
            p95_utility=p95_mat.numpy(),
            risk_adjusted_utility=risk_adj_mat.numpy(),
            win_turn_prob=win_prob_mat.numpy(),
            faint_prob=faint_prob_mat.numpy(),
            survival_prob=surv_prob_mat.numpy(),
        )
        agg_attack_np = AttackCascadeResult(
            F=first_tile_res.attack_cascade.F,
            P=first_tile_res.attack_cascade.P,
            M_moves=first_tile_res.attack_cascade.M_moves,
            mean_hp=mean_hp_mat.numpy(),
            faint_prob=faint_prob_mat.numpy(),
            roll_variance_alert=roll_var_mat.numpy(),
            mean_damage_dealt=mean_dmg_mat.numpy(),
            hit_rate_observed=hit_rate_mat.numpy(),
            crit_rate_observed=crit_rate_mat.numpy(),
            redirection_events=first_tile_res.attack_cascade.redirection_events,
        )
        agg_eot_np = EndOfTurnResult(
            F=first_tile_res.end_of_turn.F,
            P=first_tile_res.end_of_turn.P,
            M_moves=first_tile_res.end_of_turn.M_moves,
            mean_hp=mean_hp_mat.numpy(),
            faint_prob=faint_prob_mat.numpy(),
            survival_prob=surv_prob_mat.numpy(),
            trainer_1_fainted_count=t1_faints_mat.numpy(),
            trainer_2_fainted_count=t2_faints_mat.numpy(),
            is_terminal=is_term_mat.numpy(),
            winner=winner_mat.numpy(),
            eot_events=first_tile_res.end_of_turn.eot_events,
        )
        return StepResult(
            F=first_tile_res.F,
            P=first_tile_res.P,
            M_moves=first_tile_res.M_moves,
            pre_attack=first_tile_res.pre_attack,
            attack_cascade=agg_attack_np,
            end_of_turn=agg_eot_np,
            stats=stats_np,
            mean_hp=mean_hp_mat.numpy(),
            faint_prob=faint_prob_mat.numpy(),
            survival_prob=surv_prob_mat.numpy(),
            roll_variance_alert=roll_var_mat.numpy(),
            is_terminal=is_term_mat.numpy(),
            winner=winner_mat.numpy(),
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
        # min_prior_threshold is permanently locked to 0.0 (no heuristic pruning)
        mask_t1 = self.logic_engine.prune_side_26x26_tensor_actions(
            compiled_state, trainer_id="trainer_1", min_prior_threshold=0.0
        )
        mask_t2 = self.logic_engine.prune_side_26x26_tensor_actions(
            compiled_state, trainer_id="trainer_2", min_prior_threshold=0.0
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
