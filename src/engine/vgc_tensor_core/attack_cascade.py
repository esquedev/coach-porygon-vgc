# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Phase 4 Vectorized Discrete-RNG Attack Cascade Engine
=========================================================================

Executes the 4-actor sequential attack cascade across a `[B1, B2]` joint action grid
expanded across `K` parallel simulation threads (`[B1, B2, K, ...]`), where EVERY thread `k`
resolves all cartridge RNG events discretely on the fly via the Dual-Draw Spinning-Wheel
(`rng_engine.py`):

1. **Per-Thread Speed-Tie Resolution (`execution_order_k [B1, B2, K, 4]`)**:
   - When two active Pokémon share identical priority and effective speed, each thread `k`
     spins an independent 50/50 wheel to order them.
2. **Per-Thread Status Immobilization & Consecutive Protect Decay**:
   - Paralysis: 25% wheel to lose turn (`cant|par`).
   - Freeze: 20% wheel per turn to thaw (or 100% when using a thawing Fire move / Scald).
   - Sleep: 50% wake-up wheel after turn 1 of sleep (wakes on turn 3 at latest).
   - Consecutive Protect/Detect: `(1/3)^chain * 100%` wheel per thread.
3. **Per-Thread Move Accuracy Wheel (`MoveIdx.ACCURACY`)**:
   - Accounts for never-miss (`1.01`), `No Guard`, Rain sure-hit (`Thunder`, `Hurricane`,
     `Bleakwind Storm`), Snow sure-hit (`Blizzard`), and accuracy/evasion stat stages.
4. **Full Per-Hit Discrete Multi-Hit Loop (`MoveIdx.EXPECTED_HITS`)**:
   - Variable `2..5` hit moves spin the cartridge `35% / 35% / 15% / 15%` wheel (or `50% / 50%`
     for `4 / 5` hits with `Loaded Dice`, or `5` hits with `Skill Link`).
   - Each individual hit `h = 0..H_k - 1` independently spins:
     * **Critical Hit Wheel** (`Stage 0 = 4.167%`, `Stage 1 = 12.5%`, `Stage 2 = 50%`, `Stage 3+ = 100%`),
       ignoring negative attacker stages, positive defender stages, and screens on crits (`1.5x`).
     * **16-Step Cartridge Damage Roll Wheel** (`{85, 86, ..., 100} / 100.0`).
     * **Focus Sash / Sturdy 1-HP Clamp** per hit (Hit 1 consumes Focus Sash so Hit 2+ KOs!).
     * **Secondary Status & Flinch Wheels** (`MoveIdx.SEC_STATUS_CHANCE`, `MoveIdx.FLINCH_CHANCE`).
5. **Programmatic Stat Overrides & Stat Stage Deltas (`MoveIdx[53, 54]`, `MoveIdx[26..34]`)**:
   - `Body Press` (`OVERRIDE_OFF_STAT == 1.0`: user's Defense), `Foul Play` (`2.0`: target's Attack).
   - `Psyshock` / `Psystrike` / `Secret Sword` (`OVERRIDE_DEF_STAT == 1.0`: target's physical Defense).
   - Primary/self/secondary stat stage changes (`Close Combat`, `Make It Rain`, `Draco Meteor`,
     `Icy Wind`, `Snarl`, `Parting Shot`, `Swords Dance`, `Nasty Plot`, `Scale Shot`), respecting
     `Clear Amulet` and triggering reactive `Defiant` (`+2 Atk`) / `Competitive` (`+2 SpA`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

import numpy as np

from .compiler import (
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
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
    compute_per_thread_execution_orders,
)
from .rng_engine import (
    CARTRIDGE_16_ROLLS,
    RNGEventID,
    spin_wheel_crit_gate,
    spin_wheel_damage_rolls_16,
    spin_wheel_gate,
    spin_wheel_multihit_count,
)
from .schema_and_tables import (
    AbilityID,
    BilinearLookupTables,
    build_bilinear_lookup_tables,
    FIELD_DIM,
    FieldIdx,
    FieldOpID,
    HAS_TORCH,
    ItemID,
    MON_DIM,
    MOVE_DIM,
    MOVES_PER_MON,
    MonIdx,
    MoveIdx,
    OverrideDefStat,
    OverrideOffStat,
    ROSTER_SLOTS,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_1_BENCH1,
    SLOT_TRAINER_1_BENCH2,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    SLOT_TRAINER_2_BENCH1,
    SLOT_TRAINER_2_BENCH2,
    STATUS_TO_IDX,
    TYPE_TO_IDX,
    TargetType,
)

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray

# Backward-compatible alias for formatters
CARTRIDGE_ROLLS: Tuple[float, ...] = CARTRIDGE_16_ROLLS

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
    """Structured outcome of Phase 4 (Vectorized Discrete-RNG Attack Cascade).

    Attributes:
        F: Field tensor across `K` simulation threads `[B1, B2, K, 24]`.
        P: 8-Slot Roster tensor across `K` simulation threads `[B1, B2, K, 8, 84]`.
        M_moves: Move tensor across `K` simulation threads `[B1, B2, K, 8, 4, 56]`.
        mean_hp: Mean HP across all `K` simulations `[B1, B2, 8]`.
        faint_prob: Empirical faint probability across `K` simulations `[B1, B2, 8]`.
        roll_variance_alert: Binary mask `[B1, B2, 8]` (`1.0` where `0.0 < faint_prob < 1.0`).
        mean_damage_dealt: Average damage dealt by each active slot `[B1, B2, 4]`.
        hit_rate_observed: Empirical move connection rate per active slot `[B1, B2, 4]`.
        crit_rate_observed: Empirical critical hit rate per active slot `[B1, B2, 4]`.
        redirection_events: Human-readable notes detailing target redirections.
    """

    F: TensorOrArray
    P: TensorOrArray
    M_moves: TensorOrArray
    mean_hp: TensorOrArray
    faint_prob: TensorOrArray
    roll_variance_alert: TensorOrArray
    mean_damage_dealt: TensorOrArray
    hit_rate_observed: TensorOrArray
    crit_rate_observed: TensorOrArray
    redirection_events: List[str]


# =============================================================================
# 1. STAGE RATIO & TENSOR HELPERS
# =============================================================================

def _stage_ratio_torch(stage: "torch.Tensor") -> "torch.Tensor":
    """Compute exact stat stage multiplier `(max(2, 2+b) / max(2, 2-b))` for stages in `[-6, +6]`."""
    b = torch.clamp(torch.round(stage), min=-6.0, max=6.0)
    two = torch.tensor(2.0, dtype=torch.float32, device=stage.device)
    return torch.maximum(two, two + b) / torch.maximum(two, two - b)


def _acc_stage_ratio_torch(stage: "torch.Tensor") -> "torch.Tensor":
    """Compute exact accuracy/evasion stage multiplier `(max(3, 3+b) / max(3, 3-b))` for stages in `[-6, +6]`."""
    b = torch.clamp(torch.round(stage), min=-6.0, max=6.0)
    three = torch.tensor(3.0, dtype=torch.float32, device=stage.device)
    return torch.maximum(three, three + b) / torch.maximum(three, three - b)


def _stage_ratio_numpy(stage: np.ndarray) -> np.ndarray:
    b = np.clip(np.round(stage), -6.0, 6.0)
    return (np.maximum(2.0, 2.0 + b) / np.maximum(2.0, 2.0 - b)).astype(np.float32)


def _acc_stage_ratio_numpy(stage: np.ndarray) -> np.ndarray:
    b = np.clip(np.round(stage), -6.0, 6.0)
    return (np.maximum(3.0, 3.0 + b) / np.maximum(3.0, 3.0 - b)).astype(np.float32)


# =============================================================================
# 2. PYTORCH VECTORIZED DISCRETE-RNG ATTACK CASCADE (GPU / CPU)
# =============================================================================

def _execute_attack_cascade_torch(
    F: "torch.Tensor",             # [B1, B2, 24]
    P: "torch.Tensor",             # [B1, B2, 8, 84]
    M_moves: "torch.Tensor",       # [B1, B2, 8, 4, 56]
    trainer_1_choices: "torch.Tensor",
    trainer_2_choices: "torch.Tensor",
    pre_attack_res: PreAttackPhaseResult,
    tables: BilinearLookupTables,
    num_mc_samples: int = 16,
    rng_seed: int = 42,
) -> AttackCascadeResult:
    """Pure PyTorch vectorized execution of Phase 4 across `[B1, B2, K]` simulation threads."""
    device = P.device
    B1, B2 = P.shape[0], P.shape[1]
    K = int(max(1, num_mc_samples))
    seed = int(rng_seed if rng_seed is not None else 42)

    F_mc = F.unsqueeze(2).expand(B1, B2, K, FIELD_DIM).clone()
    P_mc = P.unsqueeze(2).expand(B1, B2, K, ROSTER_SLOTS, MON_DIM).clone()
    # Zero-copy view over M_moves unless a mid-turn pivot swaps bench/active move slots
    M_mc = M_moves.unsqueeze(2).expand(B1, B2, K, ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM)
    m_mc_is_cloned = False

    if trainer_1_choices.ndim == 2:
        t1_grid = trainer_1_choices.unsqueeze(1).expand(B1, B2, 2)
        t2_grid = trainer_2_choices.unsqueeze(0).expand(B1, B2, 2)
    else:
        t1_grid = trainer_1_choices
        t2_grid = trainer_2_choices

    # Choices per active slot (0, 1, 2, 3 -> trainer_1_a, trainer_1_b, trainer_2_a, trainer_2_b): [B1, B2, K, 4]
    choices_4 = torch.stack(
        [t1_grid[:, :, 0], t1_grid[:, :, 1], t2_grid[:, :, 0], t2_grid[:, :, 1]], dim=-1
    ).unsqueeze(2).expand(B1, B2, K, 4).long()

    switched_4 = pre_attack_res.switched_mask.to(device).unsqueeze(2).expand(B1, B2, K, 4)

    # Per-thread speed-tie execution order: [B1, B2, K, 4]
    exec_order_k = compute_per_thread_execution_orders(
        F_mc=F_mc,
        eff_speeds=pre_attack_res.effective_speeds.to(device),
        eff_priorities=pre_attack_res.effective_priorities.to(device),
        num_sim_threads=K,
        rng_seed=seed,
    )

    active_slot_lut = torch.tensor(ACTIVE_SLOTS, dtype=torch.long, device=device)
    type_chart = tables.m_type_chart.to(device)
    w_chart = tables.m_weather_mod.to(device)
    t_chart = tables.m_terrain_mod.to(device)

    # Side redirection trackers per thread: -1 if none, else slot index (0, 1, 4, 5)
    redir_t1 = torch.full((B1, B2, K), -1, dtype=torch.long, device=device)
    redir_t2 = torch.full((B1, B2, K), -1, dtype=torch.long, device=device)

    mean_damage_dealt = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    hits_landed_count = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    hits_attempted_count = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    crits_landed_count = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    redirection_notes: List[str] = []

    for step_idx in range(4):
        actor_act_idx = exec_order_k[:, :, :, step_idx].long()  # [B1, B2, K] in {0, 1, 2, 3}
        actor_slot = active_slot_lut[actor_act_idx]             # [B1, B2, K] in {0, 1, 4, 5}
        is_t1 = actor_act_idx < 2                               # [B1, B2, K]

        switched = torch.gather(switched_4, 3, actor_act_idx.unsqueeze(-1)).squeeze(-1) > 0.5
        choice_val = torch.gather(choices_4, 3, actor_act_idx.unsqueeze(-1)).squeeze(-1)
        is_switch_choice = (choice_val == CHOICE_SWITCH_BENCH1) | (choice_val == CHOICE_SWITCH_BENCH2)

        move_idx = (choice_val % 12) % 4
        target_code = ((choice_val % 12) // 4) % 3  # 0: Opp A, 1: Opp B, 2: Ally Partner

        # Gather actor Pokemon vector: [B1, B2, K, 84]
        act_slot_exp_mon = actor_slot.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
        p_actor = torch.gather(P_mc, 3, act_slot_exp_mon).squeeze(3)

        actor_hp = p_actor[:, :, :, MonIdx.HP_CUR]
        actor_flinched = p_actor[:, :, :, MonIdx.FLINCHED] > 0.5
        can_act = (actor_hp > 0.0) & (~actor_flinched) & (~switched) & (~is_switch_choice)

        if not torch.any(can_act):
            continue

        # Gather chosen move vector: [B1, B2, K, 56] without 4x move-slot expansion
        flat_slot_mv = (actor_slot * MOVES_PER_MON + move_idx).view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MOVE_DIM)
        if not m_mc_is_cloned:
            m_flat_base = M_moves.view(B1, B2, 1, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM).expand(
                B1, B2, K, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM
            )
            chosen_move = torch.gather(m_flat_base, 3, flat_slot_mv).squeeze(3)
        else:
            m_flat_mc = M_mc.view(B1, B2, K, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM)
            chosen_move = torch.gather(m_flat_mc, 3, flat_slot_mv).squeeze(3)

        move_type_idx = torch.argmax(chosen_move[:, :, :, MoveIdx.TYPE_START:MoveIdx.TYPE_END], dim=-1)
        cat_idx = torch.argmax(chosen_move[:, :, :, MoveIdx.CAT_START:MoveIdx.CAT_END], dim=-1)
        base_power = chosen_move[:, :, :, MoveIdx.BASE_POWER]
        w_sure = chosen_move[:, :, :, MoveIdx.WEATHER_SURE_HIT]

        # Dynamic Cloud Nine check across all active slots
        act_slots_idx = [SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_2_A, SLOT_TRAINER_2_B]
        ab_act = P_mc[:, :, :, act_slots_idx, MonIdx.ABILITY_ID]
        hp_act = P_mc[:, :, :, act_slots_idx, MonIdx.HP_CUR]
        cloud_nine_active = torch.any((hp_act > 0.0) & (ab_act == float(AbilityID.CLOUD_NINE)), dim=-1)

        w_raw = torch.argmax(F_mc[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END], dim=-1)
        w_idx = torch.where(cloud_nine_active, torch.zeros_like(w_raw), w_raw)

        # Dynamic Weather Ball adaptation (Channel 50 code == 1.0)
        is_weather_ball = w_sure == 1.0
        if torch.any(is_weather_ball):
            wb_type = torch.where(
                w_idx == W_SUN,
                torch.tensor(TYPE_TO_IDX["fire"], device=device),
                torch.where(
                    w_idx == W_RAIN,
                    torch.tensor(TYPE_TO_IDX["water"], device=device),
                    torch.where(
                        w_idx == W_SAND,
                        torch.tensor(TYPE_TO_IDX["rock"], device=device),
                        torch.where(
                            w_idx == W_SNOW,
                            torch.tensor(TYPE_TO_IDX["ice"], device=device),
                            torch.tensor(TYPE_TO_IDX["normal"], device=device),
                        ),
                    ),
                ),
            )
            wb_bp = torch.where(w_idx != W_CLEAR, torch.full_like(base_power, 100.0), torch.full_like(base_power, 50.0))
            move_type_idx = torch.where(is_weather_ball, wb_type, move_type_idx)
            base_power = torch.where(is_weather_ball, wb_bp, base_power)

        # Dynamic Two-Turn Charging Move Gates (Turn 1: deals 0 damage if must charge)
        is_solar_charge = (w_sure == 10.0) & (w_idx != W_SUN)
        is_electro_charge = (w_sure == 20.0) & (w_idx != W_RAIN)
        is_general_charge = (w_sure == 30.0)
        must_charge = is_solar_charge | is_electro_charge | is_general_charge
        base_power = torch.where(must_charge, torch.zeros_like(base_power), base_power)

        # Solar Beam / Blade base power halved in Rain, Sand, Snow when firing
        is_solar_halved = (w_sure == 10.0) & ((w_idx == W_RAIN) | (w_idx == W_SAND) | (w_idx == W_SNOW))
        base_power = torch.where(is_solar_halved & (~must_charge), base_power * 0.5, base_power)

        # ---------------------------------------------------------------------
        # A. DISCRETE STATUS IMMOBILIZATION GATES (SLEEP, FREEZE, PARALYSIS)
        # ---------------------------------------------------------------------
        # 1. Sleep wake check (50% wake-up wheel per turn)
        is_asleep = p_actor[:, :, :, MonIdx.STATUS_SLEEP] > 0.5
        if torch.any(is_asleep & can_act):
            wake_prob = torch.where(is_asleep & can_act, torch.full_like(actor_hp, 50.0), torch.zeros_like(actor_hp))
            woke_up = is_asleep & can_act & spin_wheel_gate(
                wake_prob, seed=seed, event_id=int(RNGEventID.SLEEP_WAKE), step_idx=step_idx
            )
            still_asleep = is_asleep & can_act & (~woke_up)
            if torch.any(woke_up):
                P_mc[:, :, :, :, MonIdx.STATUS_SLEEP].scatter_(
                    3, actor_slot.unsqueeze(-1), torch.where(woke_up, torch.zeros_like(actor_hp), p_actor[:, :, :, MonIdx.STATUS_SLEEP]).unsqueeze(-1)
                )
                P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY].scatter_(
                    3, actor_slot.unsqueeze(-1), torch.where(woke_up, torch.ones_like(actor_hp), p_actor[:, :, :, MonIdx.STATUS_HEALTHY]).unsqueeze(-1)
                )
            can_act = can_act & (~still_asleep)

        # 2. Freeze thaw check (20% per turn, or 100% if using a Fire move)
        is_frozen = p_actor[:, :, :, MonIdx.STATUS_FREEZE] > 0.5
        if torch.any(is_frozen & can_act):
            is_fire_move = move_type_idx == TYPE_TO_IDX["fire"]
            thaw_prob = torch.where(is_fire_move, torch.full_like(actor_hp, 100.0), torch.full_like(actor_hp, 20.0))
            thawed = is_frozen & can_act & spin_wheel_gate(
                thaw_prob, seed=seed, event_id=int(RNGEventID.FREEZE_THAW), step_idx=step_idx
            )
            still_frozen = is_frozen & can_act & (~thawed)
            if torch.any(thawed):
                P_mc[:, :, :, :, MonIdx.STATUS_FREEZE].scatter_(
                    3, actor_slot.unsqueeze(-1), torch.where(thawed, torch.zeros_like(actor_hp), p_actor[:, :, :, MonIdx.STATUS_FREEZE]).unsqueeze(-1)
                )
                P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY].scatter_(
                    3, actor_slot.unsqueeze(-1), torch.where(thawed, torch.ones_like(actor_hp), p_actor[:, :, :, MonIdx.STATUS_HEALTHY]).unsqueeze(-1)
                )
            can_act = can_act & (~still_frozen)

        # 3. Paralysis 25% full immobilization wheel
        is_para = p_actor[:, :, :, MonIdx.STATUS_PARALYZE] > 0.5
        if torch.any(is_para & can_act):
            para_thresh = torch.where(is_para & can_act, torch.full_like(actor_hp, 25.0), torch.zeros_like(actor_hp))
            full_para = spin_wheel_gate(
                para_thresh, seed=seed, event_id=int(RNGEventID.PARALYSIS_IMMOBILIZE), step_idx=step_idx
            )
            can_act = can_act & (~full_para)

        if not torch.any(can_act):
            continue

        # Record LAST_MOVE_IDX and Choice Item lock when acting
        P_mc[:, :, :, :, MonIdx.LAST_MOVE_IDX].scatter_(
            3,
            actor_slot.unsqueeze(-1),
            torch.where(can_act, move_idx.float(), p_actor[:, :, :, MonIdx.LAST_MOVE_IDX]).unsqueeze(-1),
        )
        act_item = p_actor[:, :, :, MonIdx.ITEM_ID]
        act_item_active = p_actor[:, :, :, MonIdx.ITEM_ACTIVE] > 0.5
        is_choice_item = act_item_active & (
            (act_item == float(ItemID.CHOICE_BAND))
            | (act_item == float(ItemID.CHOICE_SPECS))
            | (act_item == float(ItemID.CHOICE_SCARF))
        )
        if torch.any(is_choice_item & can_act):
            P_mc[:, :, :, :, MonIdx.CHOICE_LOCKED_MOVE].scatter_(
                3,
                actor_slot.unsqueeze(-1),
                torch.where(is_choice_item & can_act, move_idx.float(), p_actor[:, :, :, MonIdx.CHOICE_LOCKED_MOVE]).unsqueeze(-1),
            )

        # ---------------------------------------------------------------------
        # B. PROTECT / WIDE GUARD / QUICK GUARD & CONSECUTIVE PROTECT WHEEL
        # ---------------------------------------------------------------------
        protect_type = chosen_move[:, :, :, MoveIdx.PROTECT_TYPE]
        is_protect_move = can_act & (protect_type > 0.5)
        if torch.any(is_protect_move):
            prot_cnt = p_actor[:, :, :, MonIdx.PROTECT_COUNTER]
            # Standard Protect (1.0) decays by (1/3)^prot_cnt; Wide/Quick Guard (2.0, 3.0) do not decay in Gen 9
            prot_succ_pct = torch.where(
                protect_type == 1.0,
                torch.pow(torch.tensor(1.0 / 3.0, device=device), torch.clamp(prot_cnt, min=0.0, max=6.0)) * 100.0,
                torch.full_like(prot_cnt, 100.0),
            )
            prot_lands = is_protect_move & spin_wheel_gate(
                prot_succ_pct, seed=seed, event_id=int(RNGEventID.PROTECT_CHAIN), step_idx=step_idx
            )

            std_prot = prot_lands & (protect_type == 1.0)
            if torch.any(std_prot):
                cur_pa = torch.gather(P_mc[:, :, :, :, MonIdx.PROTECT_ACTIVE], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                P_mc[:, :, :, :, MonIdx.PROTECT_ACTIVE].scatter_(
                    3, actor_slot.unsqueeze(-1), torch.where(std_prot, torch.ones_like(cur_pa), cur_pa).unsqueeze(-1)
                )
                P_mc[:, :, :, :, MonIdx.PROTECT_COUNTER].scatter_(
                    3, actor_slot.unsqueeze(-1), torch.where(std_prot, prot_cnt + 1.0, prot_cnt).unsqueeze(-1)
                )

            wide_prot = prot_lands & (protect_type == 2.0)
            if torch.any(wide_prot):
                s_a = torch.where(is_t1, SLOT_TRAINER_1_A, SLOT_TRAINER_2_A)
                s_b = torch.where(is_t1, SLOT_TRAINER_1_B, SLOT_TRAINER_2_B)
                for s_slot in (s_a, s_b):
                    cur_wg = torch.gather(P_mc[:, :, :, :, MonIdx.WIDE_GUARD_ACTIVE], 3, s_slot.unsqueeze(-1)).squeeze(-1)
                    P_mc[:, :, :, :, MonIdx.WIDE_GUARD_ACTIVE].scatter_(
                        3, s_slot.unsqueeze(-1), torch.where(wide_prot, torch.ones_like(cur_wg), cur_wg).unsqueeze(-1)
                    )

            quick_prot = prot_lands & (protect_type == 3.0)
            if torch.any(quick_prot):
                s_a = torch.where(is_t1, SLOT_TRAINER_1_A, SLOT_TRAINER_2_A)
                s_b = torch.where(is_t1, SLOT_TRAINER_1_B, SLOT_TRAINER_2_B)
                for s_slot in (s_a, s_b):
                    cur_qg = torch.gather(P_mc[:, :, :, :, MonIdx.QUICK_GUARD_ACTIVE], 3, s_slot.unsqueeze(-1)).squeeze(-1)
                    P_mc[:, :, :, :, MonIdx.QUICK_GUARD_ACTIVE].scatter_(
                        3, s_slot.unsqueeze(-1), torch.where(quick_prot, torch.ones_like(cur_qg), cur_qg).unsqueeze(-1)
                    )

            can_act = can_act & (~is_protect_move)

        # ---------------------------------------------------------------------
        # C. FIELD / SIDE / REDIRECTION / HELPING HAND OPS (FieldOpID)
        # ---------------------------------------------------------------------
        field_op = torch.round(chosen_move[:, :, :, MoveIdx.FIELD_OP_ID]).long()
        has_field_op = can_act & (field_op > 0)
        if torch.any(has_field_op):
            # Weather moves (Sunny Day, Rain Dance, Sandstorm, Snowscape)
            for op_code, w_idx in (
                (int(FieldOpID.SET_SUN), W_SUN),
                (int(FieldOpID.SET_RAIN), W_RAIN),
                (int(FieldOpID.SET_SAND), W_SAND),
                (int(FieldOpID.SET_SNOW), W_SNOW),
            ):
                m_w = has_field_op & (field_op == op_code)
                if torch.any(m_w):
                    F_mc[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END] = torch.where(
                        m_w.unsqueeze(-1),
                        torch.zeros_like(F_mc[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END]),
                        F_mc[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END],
                    )
                    F_mc[:, :, :, FieldIdx.WEATHER_START + w_idx] = torch.where(
                        m_w, torch.ones_like(actor_hp), F_mc[:, :, :, FieldIdx.WEATHER_START + w_idx]
                    )
                    F_mc[:, :, :, FieldIdx.WEATHER_TURNS] = torch.where(
                        m_w, torch.full_like(actor_hp, 5.0), F_mc[:, :, :, FieldIdx.WEATHER_TURNS]
                    )

            # Terrain moves
            for op_code, tr_idx in (
                (int(FieldOpID.SET_ELECTRIC_TERRAIN), T_ELECTRIC),
                (int(FieldOpID.SET_GRASSY_TERRAIN), T_GRASSY),
                (int(FieldOpID.SET_PSYCHIC_TERRAIN), T_PSYCHIC),
                (int(FieldOpID.SET_MISTY_TERRAIN), T_MISTY),
            ):
                m_tr = has_field_op & (field_op == op_code)
                if torch.any(m_tr):
                    F_mc[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END] = torch.where(
                        m_tr.unsqueeze(-1),
                        torch.zeros_like(F_mc[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END]),
                        F_mc[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END],
                    )
                    F_mc[:, :, :, FieldIdx.TERRAIN_START + tr_idx] = torch.where(
                        m_tr, torch.ones_like(actor_hp), F_mc[:, :, :, FieldIdx.TERRAIN_START + tr_idx]
                    )
                    F_mc[:, :, :, FieldIdx.TERRAIN_TURNS] = torch.where(
                        m_tr, torch.full_like(actor_hp, 5.0), F_mc[:, :, :, FieldIdx.TERRAIN_TURNS]
                    )

            # Tailwind
            m_tw = has_field_op & (field_op == int(FieldOpID.TAILWIND))
            if torch.any(m_tw):
                F_mc[:, :, :, FieldIdx.TRAINER_1_TAILWIND_TURNS] = torch.where(
                    m_tw & is_t1, torch.full_like(actor_hp, 4.0), F_mc[:, :, :, FieldIdx.TRAINER_1_TAILWIND_TURNS]
                )
                F_mc[:, :, :, FieldIdx.TRAINER_2_TAILWIND_TURNS] = torch.where(
                    m_tw & (~is_t1), torch.full_like(actor_hp, 4.0), F_mc[:, :, :, FieldIdx.TRAINER_2_TAILWIND_TURNS]
                )

            # Trick Room (toggles 5 <-> 0)
            m_trm = has_field_op & (field_op == int(FieldOpID.TRICK_ROOM))
            if torch.any(m_trm):
                cur_trm = F_mc[:, :, :, FieldIdx.TRICK_ROOM_TURNS]
                new_trm = torch.where(cur_trm > 0.0, torch.zeros_like(cur_trm), torch.full_like(cur_trm, 5.0))
                F_mc[:, :, :, FieldIdx.TRICK_ROOM_TURNS] = torch.where(m_trm, new_trm, cur_trm)

            # Reflect, Light Screen, Aurora Veil
            for op_code, t1_fidx, t2_fidx in (
                (int(FieldOpID.REFLECT), FieldIdx.TRAINER_1_REFLECT_TURNS, FieldIdx.TRAINER_2_REFLECT_TURNS),
                (int(FieldOpID.LIGHT_SCREEN), FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS, FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS),
                (int(FieldOpID.AURORA_VEIL), FieldIdx.TRAINER_1_AURORA_VEIL_TURNS, FieldIdx.TRAINER_2_AURORA_VEIL_TURNS),
            ):
                m_sc = has_field_op & (field_op == op_code)
                if torch.any(m_sc):
                    F_mc[:, :, :, t1_fidx] = torch.where(m_sc & is_t1, torch.full_like(actor_hp, 5.0), F_mc[:, :, :, t1_fidx])
                    F_mc[:, :, :, t2_fidx] = torch.where(m_sc & (~is_t1), torch.full_like(actor_hp, 5.0), F_mc[:, :, :, t2_fidx])

            # Helping Hand (+50% boost to partner's damage this turn)
            m_hh = has_field_op & (field_op == int(FieldOpID.HELPING_HAND))
            if torch.any(m_hh):
                partner_s = torch.where(
                    is_t1,
                    torch.where(actor_slot == SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_1_A),
                    torch.where(actor_slot == SLOT_TRAINER_2_A, SLOT_TRAINER_2_B, SLOT_TRAINER_2_A),
                )
                cur_hh = torch.gather(P_mc[:, :, :, :, MonIdx.HELPING_HAND_MULT], 3, partner_s.unsqueeze(-1)).squeeze(-1)
                P_mc[:, :, :, :, MonIdx.HELPING_HAND_MULT].scatter_(
                    3, partner_s.unsqueeze(-1), torch.where(m_hh, cur_hh * 1.5, cur_hh).unsqueeze(-1)
                )

            # Follow Me / Rage Powder Redirection
            m_rd = has_field_op & (field_op == int(FieldOpID.FOLLOW_ME))
            if torch.any(m_rd):
                redir_t1 = torch.where(m_rd & is_t1, actor_slot, redir_t1)
                redir_t2 = torch.where(m_rd & (~is_t1), actor_slot, redir_t2)

        if not torch.any(can_act):
            continue

        # ---------------------------------------------------------------------
        # D. SELF-HEALING STATUS MOVES (RECOVER / ROOST / PROTECT / ETC.)
        # ---------------------------------------------------------------------
        recoil_pct = chosen_move[:, :, :, MoveIdx.RECOIL_PCT]
        target_type_code = torch.round(chosen_move[:, :, :, MoveIdx.TARGET_TYPE]).long()
        is_self_heal = can_act & (cat_idx == 2) & (recoil_pct < 0.0) & (target_type_code == int(TargetType.SELF))
        if torch.any(is_self_heal):
            cur_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            max_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            heal_val = torch.floor(max_a_hp * torch.abs(recoil_pct))
            new_a_hp = torch.clamp(cur_a_hp + torch.where(is_self_heal, heal_val, torch.zeros_like(heal_val)), max=max_a_hp)
            P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), new_a_hp.unsqueeze(-1))

        # ---------------------------------------------------------------------
        # E. SELF-TARGETING STAT BOOST MOVES (SWORDS DANCE / NASTY PLOT / TAIL GLOW)
        # ---------------------------------------------------------------------
        stat_self_flag = chosen_move[:, :, :, MoveIdx.STAT_DELTA_SELF] > 0.5
        stat_chance_pct = chosen_move[:, :, :, MoveIdx.STAT_DELTA_CHANCE] * 100.0
        is_self_status_boost = can_act & (cat_idx == 2) & stat_self_flag & (stat_chance_pct > 0.0)
        if torch.any(is_self_status_boost):
            for s_i in range(7):
                delta_v = chosen_move[:, :, :, MoveIdx.STAT_DELTA_START + s_i]
                if torch.any(is_self_status_boost & (delta_v != 0.0)):
                    cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                    new_b = torch.clamp(cur_b + torch.where(is_self_status_boost, delta_v, torch.zeros_like(delta_v)), min=-6.0, max=6.0)
                    P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(3, actor_slot.unsqueeze(-1), new_b.unsqueeze(-1))

        # ---------------------------------------------------------------------
        # F. TARGET RESOLUTION (SINGLE-TARGET, REDIRECTION, KO-XOR, SPREAD)
        # ---------------------------------------------------------------------
        opp_slot_a = torch.where(is_t1, SLOT_TRAINER_2_A, SLOT_TRAINER_1_A)
        opp_slot_b = torch.where(is_t1, SLOT_TRAINER_2_B, SLOT_TRAINER_1_B)
        partner_slot = torch.where(
            is_t1,
            torch.where(actor_slot == SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_1_A),
            torch.where(actor_slot == SLOT_TRAINER_2_A, SLOT_TRAINER_2_B, SLOT_TRAINER_2_A),
        )

        is_spread_foes = target_type_code == int(TargetType.ALL_ADJACENT_FOES)
        is_spread_all = target_type_code == int(TargetType.ALL_ADJACENT)
        is_spread = is_spread_foes | is_spread_all

        # Primary declared target for single-target moves
        decl_single = torch.where(
            target_code == 2,
            partner_slot,
            torch.where(target_code == 0, opp_slot_a, opp_slot_b),
        )
        other_foe = torch.where(decl_single == opp_slot_a, opp_slot_b, opp_slot_a)

        # Follow Me / Rage Powder redirection check (only redirects single-target foe moves)
        opp_redir_slot = torch.where(is_t1, redir_t2, redir_t1)
        has_opp_redir = (opp_redir_slot >= 0) & (target_code != 2) & (~is_spread)
        redir_clamped = torch.clamp(opp_redir_slot, min=0, max=7)
        redir_alive = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, redir_clamped.unsqueeze(-1)).squeeze(-1) > 0.0
        if torch.any(has_opp_redir & redir_alive):
            redirection_notes.append("Follow Me / Rage Powder redirection")
        single_tgt = torch.where(has_opp_redir & redir_alive, redir_clamped, decl_single)

        # KO Target Redirection XOR: if declared single foe fainted earlier in the turn, redirect to surviving partner
        single_tgt_alive = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, single_tgt.unsqueeze(-1)).squeeze(-1) > 0.0
        other_foe_alive = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, other_foe.unsqueeze(-1)).squeeze(-1) > 0.0
        is_ko_redir = (~single_tgt_alive) & (target_code != 2) & other_foe_alive & can_act
        if torch.any(is_ko_redir):
            redirection_notes.append("KO Target redirection XOR")
        single_tgt = torch.where(is_ko_redir, other_foe, single_tgt)

        # Build up to 3 target slots per step:
        # Pass 0: single_tgt (for single-target) or opp_slot_a (for spread)
        # Pass 1: opp_slot_b (for spread)
        # Pass 2: partner_slot (for ALL_ADJACENT spread like Earthquake/Discharge)
        target_passes = (
            (torch.where(is_spread, opp_slot_a, single_tgt), can_act & (target_type_code <= int(TargetType.ALL_ADJACENT)) & (target_type_code != int(TargetType.SELF))),
            (opp_slot_b, can_act & is_spread),
            (partner_slot, can_act & is_spread_all),
        )

        # Track whether the actor connected at least once (for self-stat drops like Close Combat / Make It Rain / Scale Shot)
        actor_connected_any = torch.zeros((B1, B2, K), dtype=torch.bool, device=device)

        for pass_idx, (tgt_slot, pass_mask) in enumerate(target_passes):
            if not torch.any(pass_mask):
                continue

            tgt_exp_mon = tgt_slot.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
            p_tgt = torch.gather(P_mc, 3, tgt_exp_mon).squeeze(3)
            tgt_hp = p_tgt[:, :, :, MonIdx.HP_CUR]
            tgt_alive = tgt_hp > 0.0

            # Protect / Wide Guard / Quick Guard checks
            tgt_prot = p_tgt[:, :, :, MonIdx.PROTECT_ACTIVE] > 0.5
            tgt_wg = is_spread & (p_tgt[:, :, :, MonIdx.WIDE_GUARD_ACTIVE] > 0.5)
            move_prio = chosen_move[:, :, :, MoveIdx.PRIORITY]
            tgt_qg = (move_prio > 0.0) & (p_tgt[:, :, :, MonIdx.QUICK_GUARD_ACTIVE] > 0.5) & (tgt_slot != partner_slot)
            is_guarded = tgt_prot | tgt_wg | tgt_qg

            valid_target = pass_mask & tgt_alive & (~is_guarded)
            if not torch.any(valid_target):
                continue

            # -----------------------------------------------------------------
            # G. POLLEN PUFF ALLY HEALING (+50% MAX HP WHEN TARGETING ALLY)
            # -----------------------------------------------------------------
            is_pollen_ally_heal = (
                valid_target
                & (tgt_slot == partner_slot)
                & (~is_spread)
                & (move_type_idx == TYPE_TO_IDX["bug"])
                & (torch.abs(base_power - 90.0) < 0.5)
                & (cat_idx == 1)
            )
            if torch.any(is_pollen_ally_heal):
                max_t_hp = p_tgt[:, :, :, MonIdx.HP_MAX]
                heal_pp = torch.floor(max_t_hp * 0.50)
                new_t_hp = torch.clamp(tgt_hp + torch.where(is_pollen_ally_heal, heal_pp, torch.zeros_like(heal_pp)), max=max_t_hp)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, tgt_slot.unsqueeze(-1), new_t_hp.unsqueeze(-1))
                valid_target = valid_target & (~is_pollen_ally_heal)

            if not torch.any(valid_target):
                continue

            # -----------------------------------------------------------------
            # H. ACCURACY SPINNING-WHEEL CHECK PER SIMULATION THREAD
            # -----------------------------------------------------------------
            raw_acc = chosen_move[:, :, :, MoveIdx.ACCURACY]
            att_ab = p_actor[:, :, :, MonIdx.ABILITY_ID]
            tgt_ab = p_tgt[:, :, :, MonIdx.ABILITY_ID]
            # Dynamic Cloud Nine check across all active slots
            ab_act = P_mc[:, :, :, act_slots_idx, MonIdx.ABILITY_ID]
            hp_act = P_mc[:, :, :, act_slots_idx, MonIdx.HP_CUR]
            cloud_nine_active = torch.any((hp_act > 0.0) & (ab_act == float(AbilityID.CLOUD_NINE)), dim=-1)
            w_raw = torch.argmax(F_mc[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END], dim=-1)
            w_idx = torch.where(cloud_nine_active, torch.zeros_like(w_raw), w_raw)

            sure_hit = (
                (raw_acc >= 1.005)
                | (att_ab == float(AbilityID.NO_GUARD))
                | (tgt_ab == float(AbilityID.NO_GUARD))
                | ((w_sure == 2.0) & (w_idx == W_RAIN))
                | ((w_sure == 4.0) & (w_idx == W_SNOW))
            )
            acc_eva_stage = torch.clamp(
                p_actor[:, :, :, MonIdx.BOOST_ACC] - p_tgt[:, :, :, MonIdx.BOOST_EVA], min=-6.0, max=6.0
            )
            eff_acc_pct = torch.where(
                sure_hit,
                torch.full_like(raw_acc, 100.0),
                torch.clamp(raw_acc * 100.0 * _acc_stage_ratio_torch(acc_eva_stage), min=0.0, max=100.0),
            )
            move_hits = valid_target & spin_wheel_gate(
                eff_acc_pct,
                seed=seed,
                event_id=int(RNGEventID.MOVE_ACCURACY),
                step_idx=step_idx * 4 + pass_idx,
            )

            # Track hit rate statistics on primary pass
            if pass_idx == 0:
                att_step = torch.mean(valid_target.float(), dim=-1)
                hit_step = torch.mean(move_hits.float(), dim=-1)
                act_idx_0 = exec_order_k[:, :, 0, step_idx].long()
                hits_attempted_count.scatter_add_(2, act_idx_0.unsqueeze(-1), att_step.unsqueeze(-1))
                hits_landed_count.scatter_add_(2, act_idx_0.unsqueeze(-1), hit_step.unsqueeze(-1))

            if not torch.any(move_hits):
                continue

            actor_connected_any = actor_connected_any | move_hits

            # -----------------------------------------------------------------
            # I. STATUS MOVE SECONDARY / PRIMARY EFFECTS ON TARGET
            # -----------------------------------------------------------------
            is_status_move = cat_idx == 2
            status_hits = move_hits & is_status_move
            if torch.any(status_hits):
                # Status infliction (Will-O-Wisp, Thunder Wave, Spore, Toxic, etc.)
                sec_chance_pct = chosen_move[:, :, :, MoveIdx.SEC_STATUS_CHANCE] * 100.0
                tgt_healthy = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, tgt_slot.unsqueeze(-1)).squeeze(-1) > 0.5
                st_lands = status_hits & tgt_healthy & spin_wheel_gate(
                    sec_chance_pct, seed=seed, event_id=int(RNGEventID.SECONDARY_STATUS), step_idx=step_idx * 4 + pass_idx
                )
                if torch.any(st_lands):
                    for st_i in range(7):
                        new_st_bit = chosen_move[:, :, :, MoveIdx.SEC_STATUS_START + st_i]
                        cur_st_bit = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_START + st_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.STATUS_START + st_i].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.where(st_lands, new_st_bit, cur_st_bit).unsqueeze(-1)
                        )

                # Target stat stage changes on status moves (Parting Shot, Charm, Scary Face, Fake Tears)
                tgt_stat_op = status_hits & (~stat_self_flag) & (stat_chance_pct > 0.0)
                if torch.any(tgt_stat_op):
                    tgt_clear_amulet = (
                        (p_tgt[:, :, :, MonIdx.ITEM_ACTIVE] > 0.5)
                        & (p_tgt[:, :, :, MonIdx.ITEM_ID] == float(ItemID.CLEAR_AMULET))
                    )
                    stat_lands = tgt_stat_op & (~tgt_clear_amulet) & spin_wheel_gate(
                        stat_chance_pct, seed=seed, event_id=int(RNGEventID.STAT_STAGE_PROC), step_idx=step_idx * 4 + pass_idx
                    )
                    if torch.any(stat_lands):
                        any_drop = torch.zeros_like(stat_lands)
                        for s_i in range(7):
                            delta_v = chosen_move[:, :, :, MoveIdx.STAT_DELTA_START + s_i]
                            if torch.any(stat_lands & (delta_v != 0.0)):
                                cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                                any_drop = any_drop | (stat_lands & (delta_v < 0.0) & (cur_b > -6.0))
                                new_b = torch.clamp(cur_b + torch.where(stat_lands, delta_v, torch.zeros_like(delta_v)), min=-6.0, max=6.0)
                                P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(3, tgt_slot.unsqueeze(-1), new_b.unsqueeze(-1))
                        # Defiant / Competitive on target
                        if torch.any(any_drop):
                            is_defiant = any_drop & (tgt_ab == float(AbilityID.DEFIANT))
                            if torch.any(is_defiant):
                                cur_a = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_ATK], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                                P_mc[:, :, :, :, MonIdx.BOOST_ATK].scatter_(
                                    3, tgt_slot.unsqueeze(-1), torch.clamp(cur_a + torch.where(is_defiant, torch.full_like(cur_a, 2.0), torch.zeros_like(cur_a)), -6.0, 6.0).unsqueeze(-1)
                                )
                            is_comp = any_drop & (tgt_ab == float(AbilityID.COMPETITIVE))
                            if torch.any(is_comp):
                                cur_sa = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_SPA], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                                P_mc[:, :, :, :, MonIdx.BOOST_SPA].scatter_(
                                    3, tgt_slot.unsqueeze(-1), torch.clamp(cur_sa + torch.where(is_comp, torch.full_like(cur_sa, 2.0), torch.zeros_like(cur_sa)), -6.0, 6.0).unsqueeze(-1)
                                )

            # -----------------------------------------------------------------
            # J. DAMAGING MOVE MULTI-HIT DISCRETE LOOP (CRIT + 16-ROLL PER HIT)
            # -----------------------------------------------------------------
            dmg_move_hits = move_hits & (~is_status_move) & (base_power > 0.0)
            if not torch.any(dmg_move_hits):
                continue

            # Type effectiveness
            t1_idx = torch.argmax(p_tgt[:, :, :, MonIdx.TYPE1_START:MonIdx.TYPE1_END], dim=-1)
            t2_idx = torch.argmax(p_tgt[:, :, :, MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1)
            has_t2 = torch.sum(p_tgt[:, :, :, MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1) > 0.5
            eff1 = type_chart[move_type_idx, t1_idx]
            eff2 = torch.where(has_t2, type_chart[move_type_idx, t2_idx], torch.ones_like(eff1))
            type_eff = eff1 * eff2

            # Scrappy bypasses Ghost immunity on Normal/Fighting
            is_scrappy = (att_ab == float(AbilityID.SCRAPPY)) & (
                (move_type_idx == TYPE_TO_IDX["normal"]) | (move_type_idx == TYPE_TO_IDX["fighting"])
            )
            if torch.any(is_scrappy):
                type_eff = torch.where(is_scrappy & (type_eff == 0.0), torch.ones_like(type_eff), type_eff)

            # Ground immunity on ungrounded targets (unless Gravity is active)
            grav_on = F_mc[:, :, :, FieldIdx.GRAVITY_TURNS] > 0.0
            tgt_grounded = (p_tgt[:, :, :, MonIdx.GROUNDED_FLAG] > 0.5) | grav_on
            type_eff = torch.where(
                (move_type_idx == TYPE_TO_IDX["ground"]) & (~tgt_grounded),
                torch.zeros_like(type_eff),
                type_eff,
            )

            dmg_move_hits = dmg_move_hits & (type_eff > 0.0)
            if not torch.any(dmg_move_hits):
                continue

            # Resolve discrete hit count per simulation thread (1..10)
            raw_exp_hits = chosen_move[:, :, :, MoveIdx.EXPECTED_HITS]
            exp_hits_code = torch.where(raw_exp_hits > 0.0, raw_exp_hits, torch.ones_like(raw_exp_hits))
            has_dice = (act_item_active & (act_item == float(ItemID.LOADED_DICE))).float()
            has_slink = (att_ab == float(AbilityID.SKILL_LINK)).float()
            hit_counts = spin_wheel_multihit_count(
                exp_hits_code, has_dice, has_slink, seed=seed, step_idx=step_idx * 4 + pass_idx
            )
            max_hits = int(torch.max(torch.where(dmg_move_hits, hit_counts, torch.ones_like(hit_counts))).item())

            # Offensive & Defensive Stat Overrides (Body Press, Foul Play, Psyshock/Psystrike/Secret Sword)
            off_ovr = torch.round(chosen_move[:, :, :, MoveIdx.OVERRIDE_OFF_STAT]).long()
            def_ovr = torch.round(chosen_move[:, :, :, MoveIdx.OVERRIDE_DEF_STAT]).long()
            is_phys = cat_idx == 0

            raw_atk_stat = torch.where(
                off_ovr == int(OverrideOffStat.USER_DEF),
                p_actor[:, :, :, MonIdx.STAT_DEF],
                torch.where(
                    off_ovr == int(OverrideOffStat.TARGET_ATK),
                    p_tgt[:, :, :, MonIdx.STAT_ATK],
                    torch.where(is_phys, p_actor[:, :, :, MonIdx.STAT_ATK], p_actor[:, :, :, MonIdx.STAT_SPA]),
                ),
            )
            raw_atk_stage = torch.where(
                off_ovr == int(OverrideOffStat.USER_DEF),
                p_actor[:, :, :, MonIdx.BOOST_DEF],
                torch.where(
                    off_ovr == int(OverrideOffStat.TARGET_ATK),
                    p_tgt[:, :, :, MonIdx.BOOST_ATK],
                    torch.where(is_phys, p_actor[:, :, :, MonIdx.BOOST_ATK], p_actor[:, :, :, MonIdx.BOOST_SPA]),
                ),
            )

            raw_def_stat = torch.where(
                def_ovr == int(OverrideDefStat.TARGET_DEF),
                p_tgt[:, :, :, MonIdx.STAT_DEF],
                torch.where(is_phys, p_tgt[:, :, :, MonIdx.STAT_DEF], p_tgt[:, :, :, MonIdx.STAT_SPD]),
            )
            raw_def_stage = torch.where(
                def_ovr == int(OverrideDefStat.TARGET_DEF),
                p_tgt[:, :, :, MonIdx.BOOST_DEF],
                torch.where(is_phys, p_tgt[:, :, :, MonIdx.BOOST_DEF], p_tgt[:, :, :, MonIdx.BOOST_SPD]),
            )

            # Weather, Terrain, STAB, Helping Hand
            weather_mult = w_chart[w_idx, move_type_idx]
            tr_idx = torch.argmax(F_mc[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END], dim=-1)
            att_grounded = (p_actor[:, :, :, MonIdx.GROUNDED_FLAG] > 0.5) | grav_on
            terrain_mult = torch.where(att_grounded, t_chart[tr_idx, move_type_idx], torch.ones_like(weather_mult))

            att_t1 = torch.argmax(p_actor[:, :, :, MonIdx.TYPE1_START:MonIdx.TYPE1_END], dim=-1)
            att_t2 = torch.argmax(p_actor[:, :, :, MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1)
            att_has_t2 = torch.sum(p_actor[:, :, :, MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1) > 0.5
            is_stab = (move_type_idx == att_t1) | (att_has_t2 & (move_type_idx == att_t2))
            stab_mult = torch.where(
                is_stab,
                torch.where(att_ab == float(AbilityID.ADAPTABILITY), torch.full_like(base_power, 2.0), torch.full_like(base_power, 1.5)),
                torch.ones_like(base_power),
            )
            hh_mult = torch.where(
                p_actor[:, :, :, MonIdx.HELPING_HAND_MULT] > 0.0,
                p_actor[:, :, :, MonIdx.HELPING_HAND_MULT],
                torch.ones_like(base_power),
            )

            # Crit stage calculation (base move stage + Scope Lens)
            crit_stage = chosen_move[:, :, :, MoveIdx.CRIT_STAGE] + torch.where(
                act_item_active & (act_item == float(ItemID.SCOPE_LENS)),
                torch.ones_like(base_power),
                torch.zeros_like(base_power),
            )

            # Screens on defending side (0.667x in Doubles, bypassed on crits)
            tgt_is_t1 = tgt_slot < 4
            refl_turns = torch.where(tgt_is_t1, F_mc[:, :, :, FieldIdx.TRAINER_1_REFLECT_TURNS], F_mc[:, :, :, FieldIdx.TRAINER_2_REFLECT_TURNS])
            lscr_turns = torch.where(tgt_is_t1, F_mc[:, :, :, FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS], F_mc[:, :, :, FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS])
            veil_turns = torch.where(tgt_is_t1, F_mc[:, :, :, FieldIdx.TRAINER_1_AURORA_VEIL_TURNS], F_mc[:, :, :, FieldIdx.TRAINER_2_AURORA_VEIL_TURNS])
            screen_active = (
                (is_phys & ((refl_turns > 0.0) | (veil_turns > 0.0)))
                | ((~is_phys) & ((lscr_turns > 0.0) | (veil_turns > 0.0)))
            )

            total_dmg_this_target = torch.zeros((B1, B2, K), dtype=torch.float32, device=device)

            for hit_idx in range(max_hits):
                cur_t_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                max_t_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                hit_active = dmg_move_hits & (hit_counts > hit_idx) & (cur_t_hp > 0.0)
                if not torch.any(hit_active):
                    break

                # 1. Critical Hit Spinning-Wheel per hit
                is_crit = hit_active & spin_wheel_crit_gate(
                    crit_stage, seed=seed, step_idx=step_idx * 4 + pass_idx, hit_idx=hit_idx
                )
                if pass_idx == 0 and hit_idx == 0:
                    crit_step = torch.mean(is_crit.float(), dim=-1)
                    act_idx_0 = exec_order_k[:, :, 0, step_idx].long()
                    crits_landed_count.scatter_add_(2, act_idx_0.unsqueeze(-1), crit_step.unsqueeze(-1))

                # Crits ignore negative attack stages and positive defense stages
                eff_atk_stage = torch.where(is_crit, torch.clamp(raw_atk_stage, min=0.0), raw_atk_stage)
                eff_def_stage = torch.where(is_crit, torch.clamp(raw_def_stage, max=0.0), raw_def_stage)

                A = raw_atk_stat * _stage_ratio_torch(eff_atk_stage)
                D = torch.clamp(raw_def_stat * _stage_ratio_torch(eff_def_stage), min=1.0)

                # Ability & Item modifiers on A and D
                A = torch.where(is_phys & (att_ab == float(AbilityID.HUGE_POWER)), A * 2.0, A)
                A = torch.where(
                    is_phys & (att_ab == float(AbilityID.GUTS)) & (p_actor[:, :, :, MonIdx.STATUS_HEALTHY] < 0.5),
                    A * 1.5,
                    A,
                )
                cb_on = is_phys & act_item_active & (act_item == float(ItemID.CHOICE_BAND))
                cs_on = (~is_phys) & act_item_active & (act_item == float(ItemID.CHOICE_SPECS))
                A = torch.where(cb_on | cs_on, torch.floor(A * 1.5), A)

                av_on = (~is_phys) & (def_ovr != int(OverrideDefStat.TARGET_DEF)) & (
                    (p_tgt[:, :, :, MonIdx.ITEM_ACTIVE] > 0.5)
                    & (p_tgt[:, :, :, MonIdx.ITEM_ID] == float(ItemID.ASSAULT_VEST))
                )
                D = torch.where(av_on, torch.floor(D * 1.5), D)

                # Base Level 50 Damage
                bp_eff = torch.floor(base_power * hh_mult)
                base_calc = torch.floor((22.0 * bp_eff * (A / D)) / 50.0) + 2.0

                # Spread (0.75x)
                base_calc = torch.where(is_spread, torch.floor(base_calc * 0.75), base_calc)
                # Weather & Terrain
                base_calc = torch.floor(base_calc * weather_mult)
                base_calc = torch.floor(base_calc * terrain_mult)
                # Critical Hit (1.5x)
                base_calc = torch.where(is_crit, torch.floor(base_calc * 1.5), base_calc)

                # 2. Discrete 16-Step Cartridge Roll [0.85..1.00] via Spinning-Wheel per hit
                roll_mult = spin_wheel_damage_rolls_16(
                    (B1, B2, K),
                    seed=seed,
                    step_idx=step_idx * 4 + pass_idx,
                    hit_idx=hit_idx,
                    is_torch=True,
                    device=device,
                )
                base_calc = torch.floor(base_calc * roll_mult)

                # STAB & Type Effectiveness
                base_calc = torch.floor(base_calc * stab_mult)
                base_calc = torch.floor(base_calc * type_eff)

                # Burn (0.5x on Physical unless Guts)
                is_burned = p_actor[:, :, :, MonIdx.STATUS_BURN] > 0.5
                base_calc = torch.where(
                    is_burned & is_phys & (att_ab != float(AbilityID.GUTS)),
                    torch.floor(base_calc * 0.5),
                    base_calc,
                )

                # Screens (2732/4096 ~ 0.667x in Doubles, bypassed on crit)
                base_calc = torch.where(
                    screen_active & (~is_crit),
                    torch.floor(base_calc * 2732.0 / 4096.0),
                    base_calc,
                )

                # Multiscale (0.5x at full HP)
                base_calc = torch.where(
                    (tgt_ab == float(AbilityID.MULTISCALE)) & (cur_t_hp >= max_t_hp),
                    torch.floor(base_calc * 0.5),
                    base_calc,
                )

                # Life Orb (5324/4096 ~ 1.3x)
                is_lo = act_item_active & (act_item == float(ItemID.LIFE_ORB))
                base_calc = torch.where(is_lo, torch.floor(base_calc * 5324.0 / 4096.0), base_calc)

                dmg_hit = torch.clamp(base_calc, min=1.0)

                # Focus Sash & Sturdy 1-HP Clamp (consumes Focus Sash so Hit 2+ KOs!)
                cur_t_item_act = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE], 3, tgt_slot.unsqueeze(-1)).squeeze(-1) > 0.5
                cur_t_item = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                sash_triggers = hit_active & (cur_t_hp >= max_t_hp) & (dmg_hit >= cur_t_hp) & cur_t_item_act & (cur_t_item == float(ItemID.FOCUS_SASH))
                sturdy_triggers = hit_active & (cur_t_hp >= max_t_hp) & (dmg_hit >= cur_t_hp) & (tgt_ab == float(AbilityID.STURDY))

                applied_dmg = torch.where(sash_triggers | sturdy_triggers, cur_t_hp - 1.0, dmg_hit)
                applied_dmg = torch.where(hit_active, applied_dmg, torch.zeros_like(applied_dmg))

                if torch.any(sash_triggers):
                    P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
                        3,
                        tgt_slot.unsqueeze(-1),
                        torch.where(sash_triggers, torch.zeros_like(cur_t_hp), cur_t_item_act.float()).unsqueeze(-1),
                    )

                new_t_hp = torch.clamp(cur_t_hp - applied_dmg, min=0.0)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, tgt_slot.unsqueeze(-1), new_t_hp.unsqueeze(-1))
                P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, tgt_slot.unsqueeze(-1), (new_t_hp > 0.0).float().unsqueeze(-1))

                total_dmg_this_target = total_dmg_this_target + applied_dmg

                # Beat Up into Ally Justified (+1 Atk per hit)
                is_justified_hit = hit_active & (tgt_slot == partner_slot) & (move_type_idx == TYPE_TO_IDX["dark"]) & (tgt_ab == float(AbilityID.JUSTIFIED)) & (new_t_hp > 0.0)
                if torch.any(is_justified_hit):
                    cur_ja = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_ATK], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                    P_mc[:, :, :, :, MonIdx.BOOST_ATK].scatter_(
                        3, tgt_slot.unsqueeze(-1), torch.clamp(cur_ja + torch.where(is_justified_hit, torch.ones_like(cur_ja), torch.zeros_like(cur_ja)), -6.0, 6.0).unsqueeze(-1)
                    )

            # Accumulate mean damage dealt by this actor slot
            step_mean_dmg = torch.mean(total_dmg_this_target, dim=-1)  # [B1, B2]
            act_idx_0 = exec_order_k[:, :, 0, step_idx].long()
            mean_damage_dealt.scatter_add_(2, act_idx_0.unsqueeze(-1), step_mean_dmg.unsqueeze(-1))

            # -----------------------------------------------------------------
            # K. RECOIL, DRAIN, SECONDARY STATUS, TARGET STAT DROPS & FLINCH
            # -----------------------------------------------------------------
            cur_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            max_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, actor_slot.unsqueeze(-1)).squeeze(-1)

            # Recoil (e.g. Flare Blitz, Wood Hammer, Wave Crash) or Drain (Drain Punch, Giga Drain)
            has_recoil = dmg_move_hits & (recoil_pct > 0.0) & (total_dmg_this_target > 0.0)
            if torch.any(has_recoil):
                rec_dmg = torch.clamp(torch.floor(total_dmg_this_target * recoil_pct), min=1.0)
                cur_a_hp = torch.clamp(cur_a_hp - torch.where(has_recoil, rec_dmg, torch.zeros_like(rec_dmg)), min=0.0)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), cur_a_hp.unsqueeze(-1))
                P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, actor_slot.unsqueeze(-1), (cur_a_hp > 0.0).float().unsqueeze(-1))

            has_drain = dmg_move_hits & (recoil_pct < 0.0) & (total_dmg_this_target > 0.0) & (cur_a_hp > 0.0)
            if torch.any(has_drain):
                drn_heal = torch.clamp(torch.floor(total_dmg_this_target * torch.abs(recoil_pct)), min=1.0)
                cur_a_hp = torch.clamp(cur_a_hp + torch.where(has_drain, drn_heal, torch.zeros_like(drn_heal)), max=max_a_hp)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), cur_a_hp.unsqueeze(-1))

            # Check surviving target for secondary effects (Shield Dust & Covert Cloak block opponent secondary effects)
            surv_t_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
            tgt_has_cloak = (
                (p_tgt[:, :, :, MonIdx.ITEM_ACTIVE] > 0.5)
                & (p_tgt[:, :, :, MonIdx.ITEM_ID] == float(ItemID.COVERT_CLOAK))
            )
            sec_blocked = (tgt_ab == float(AbilityID.SHIELD_DUST)) | tgt_has_cloak
            can_proc_sec = dmg_move_hits & (surv_t_hp > 0.0) & (~sec_blocked)

            # Secondary Status Wheel (Scald 30% burn, Thunderbolt 10% para, etc.)
            sec_st_pct = chosen_move[:, :, :, MoveIdx.SEC_STATUS_CHANCE] * 100.0
            if torch.any(can_proc_sec & (sec_st_pct > 0.0)):
                tgt_healthy = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, tgt_slot.unsqueeze(-1)).squeeze(-1) > 0.5
                sec_st_lands = can_proc_sec & tgt_healthy & spin_wheel_gate(
                    sec_st_pct, seed=seed, event_id=int(RNGEventID.SECONDARY_STATUS), step_idx=step_idx * 4 + pass_idx
                )
                if torch.any(sec_st_lands):
                    for st_i in range(7):
                        new_st_bit = chosen_move[:, :, :, MoveIdx.SEC_STATUS_START + st_i]
                        cur_st_bit = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_START + st_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.STATUS_START + st_i].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.where(sec_st_lands, new_st_bit, cur_st_bit).unsqueeze(-1)
                        )

            # Secondary Target Stat Drops (Icy Wind -1 Spe, Snarl -1 SpA, Mystical Fire -1 SpA, etc.)
            if torch.any(can_proc_sec & (~stat_self_flag) & (stat_chance_pct > 0.0)):
                tgt_clear_amulet = (
                    (p_tgt[:, :, :, MonIdx.ITEM_ACTIVE] > 0.5)
                    & (p_tgt[:, :, :, MonIdx.ITEM_ID] == float(ItemID.CLEAR_AMULET))
                )
                sec_stat_lands = can_proc_sec & (~tgt_clear_amulet) & spin_wheel_gate(
                    stat_chance_pct, seed=seed, event_id=int(RNGEventID.STAT_STAGE_PROC), step_idx=step_idx * 4 + pass_idx
                )
                if torch.any(sec_stat_lands):
                    any_drop = torch.zeros_like(sec_stat_lands)
                    for s_i in range(7):
                        delta_v = chosen_move[:, :, :, MoveIdx.STAT_DELTA_START + s_i]
                        if torch.any(sec_stat_lands & (delta_v != 0.0)):
                            cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                            any_drop = any_drop | (sec_stat_lands & (delta_v < 0.0) & (cur_b > -6.0))
                            new_b = torch.clamp(cur_b + torch.where(sec_stat_lands, delta_v, torch.zeros_like(delta_v)), min=-6.0, max=6.0)
                            P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(3, tgt_slot.unsqueeze(-1), new_b.unsqueeze(-1))
                    if torch.any(any_drop):
                        is_defiant = any_drop & (tgt_ab == float(AbilityID.DEFIANT))
                        if torch.any(is_defiant):
                            cur_a = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_ATK], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                            P_mc[:, :, :, :, MonIdx.BOOST_ATK].scatter_(
                                3, tgt_slot.unsqueeze(-1), torch.clamp(cur_a + torch.where(is_defiant, torch.full_like(cur_a, 2.0), torch.zeros_like(cur_a)), -6.0, 6.0).unsqueeze(-1)
                            )
                        is_comp = any_drop & (tgt_ab == float(AbilityID.COMPETITIVE))
                        if torch.any(is_comp):
                            cur_sa = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_SPA], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                            P_mc[:, :, :, :, MonIdx.BOOST_SPA].scatter_(
                                3, tgt_slot.unsqueeze(-1), torch.clamp(cur_sa + torch.where(is_comp, torch.full_like(cur_sa, 2.0), torch.zeros_like(cur_sa)), -6.0, 6.0).unsqueeze(-1)
                            )

            # Flinch Spinning-Wheel (Fake Out 100%, Rock Slide / Iron Head / Icicle Crash 30%)
            flinch_pct = chosen_move[:, :, :, MoveIdx.FLINCH_CHANCE] * 100.0
            can_flinch = can_proc_sec & (flinch_pct > 0.0) & (tgt_ab != float(AbilityID.INNER_FOCUS))
            if torch.any(can_flinch):
                flinch_lands = can_flinch & spin_wheel_gate(
                    flinch_pct, seed=seed, event_id=int(RNGEventID.FLINCH_PROC), step_idx=step_idx * 4 + pass_idx
                )
                if torch.any(flinch_lands):
                    cur_fl = torch.gather(P_mc[:, :, :, :, MonIdx.FLINCHED], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                    P_mc[:, :, :, :, MonIdx.FLINCHED].scatter_(
                        3, tgt_slot.unsqueeze(-1), torch.where(flinch_lands, torch.ones_like(cur_fl), cur_fl).unsqueeze(-1)
                    )

        # ---------------------------------------------------------------------
        # L. SELF STAT CHANGES ON DAMAGING MOVES & LIFE ORB RECOIL
        # ---------------------------------------------------------------------
        if torch.any(actor_connected_any):
            # Life Orb 10% recoil (once per move connection)
            cur_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            max_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            lo_recoil_mask = actor_connected_any & (cat_idx != 2) & act_item_active & (act_item == float(ItemID.LIFE_ORB)) & (cur_a_hp > 0.0)
            if torch.any(lo_recoil_mask):
                lo_dmg = torch.clamp(torch.floor(max_a_hp * 0.10), min=1.0)
                cur_a_hp = torch.clamp(cur_a_hp - torch.where(lo_recoil_mask, lo_dmg, torch.zeros_like(lo_dmg)), min=0.0)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), cur_a_hp.unsqueeze(-1))
                P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, actor_slot.unsqueeze(-1), (cur_a_hp > 0.0).float().unsqueeze(-1))

            # Self stat stage changes on damaging moves (Close Combat, Draco Meteor, Make It Rain, Scale Shot, Torch Song)
            self_dmg_stat_mask = actor_connected_any & (cat_idx != 2) & stat_self_flag & (stat_chance_pct > 0.0) & (cur_a_hp > 0.0)
            if torch.any(self_dmg_stat_mask):
                self_stat_lands = self_dmg_stat_mask & spin_wheel_gate(
                    stat_chance_pct, seed=seed, event_id=int(RNGEventID.STAT_STAGE_PROC), step_idx=step_idx * 4 + 3
                )
                if torch.any(self_stat_lands):
                    for s_i in range(7):
                        delta_v = chosen_move[:, :, :, MoveIdx.STAT_DELTA_START + s_i]
                        if torch.any(self_stat_lands & (delta_v != 0.0)):
                            cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                            new_b = torch.clamp(cur_b + torch.where(self_stat_lands, delta_v, torch.zeros_like(delta_v)), min=-6.0, max=6.0)
                            P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(3, actor_slot.unsqueeze(-1), new_b.unsqueeze(-1))

            # Mid-Turn Self-Pivot Moves (U-turn, Volt Switch, Flip Turn, Parting Shot)
            sw_mode = chosen_move[:, :, :, MoveIdx.SWITCH_MODE]
            is_pivot = actor_connected_any & (sw_mode == 1.0) & (cur_a_hp > 0.0)
            if torch.any(is_pivot):
                b1_slot = torch.where(is_t1, SLOT_TRAINER_1_BENCH1, SLOT_TRAINER_2_BENCH1)
                b2_slot = torch.where(is_t1, SLOT_TRAINER_1_BENCH2, SLOT_TRAINER_2_BENCH2)
                b1_alive = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, b1_slot.unsqueeze(-1)).squeeze(-1) > 0.0
                b2_alive = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, b2_slot.unsqueeze(-1)).squeeze(-1) > 0.0
                can_pivot = is_pivot & (b1_alive | b2_alive)
                if torch.any(can_pivot):
                    chosen_b = torch.where(b1_alive, b1_slot, b2_slot)
                    persist_mask = tables.switch_persist_mask.to(device).view(1, 1, 1, MON_DIM)

                    act_exp = actor_slot.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
                    bn_exp = chosen_b.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
                    p_act_cur = torch.gather(P_mc, 3, act_exp).squeeze(3) * persist_mask
                    p_bn_cur = torch.gather(P_mc, 3, bn_exp).squeeze(3)

                    piv_exp = can_pivot.unsqueeze(-1)
                    new_act_p = torch.where(piv_exp, p_bn_cur, torch.gather(P_mc, 3, act_exp).squeeze(3))
                    new_bn_p = torch.where(piv_exp, p_act_cur, p_bn_cur)
                    P_mc.scatter_(3, act_exp, new_act_p.unsqueeze(3))
                    P_mc.scatter_(3, bn_exp, new_bn_p.unsqueeze(3))

                    if not m_mc_is_cloned:
                        M_mc = M_mc.clone()
                        m_mc_is_cloned = True
                    act_m_exp = actor_slot.view(B1, B2, K, 1, 1, 1).expand(B1, B2, K, 1, MOVES_PER_MON, MOVE_DIM)
                    bn_m_exp = chosen_b.view(B1, B2, K, 1, 1, 1).expand(B1, B2, K, 1, MOVES_PER_MON, MOVE_DIM)
                    m_act_cur = torch.gather(M_mc, 3, act_m_exp).squeeze(3)
                    m_bn_cur = torch.gather(M_mc, 3, bn_m_exp).squeeze(3)
                    piv_m_exp = can_pivot.view(B1, B2, K, 1, 1)
                    M_mc.scatter_(3, act_m_exp, torch.where(piv_m_exp, m_bn_cur, m_act_cur).unsqueeze(3))
                    M_mc.scatter_(3, bn_m_exp, torch.where(piv_m_exp, m_act_cur, m_bn_cur).unsqueeze(3))

    # -------------------------------------------------------------------------
    # STATISTICAL AGGREGATION ACROSS ALL K SIMULATION THREADS
    # -------------------------------------------------------------------------
    hp_cur_all = P_mc[:, :, :, :, MonIdx.HP_CUR]  # [B1, B2, K, 8]
    mean_hp = torch.mean(hp_cur_all, dim=2)        # [B1, B2, 8]

    faint_mask = (hp_cur_all <= 0.0).float()
    faint_prob = torch.mean(faint_mask, dim=2)     # [B1, B2, 8]
    roll_variance_alert = ((faint_prob > 0.0) & (faint_prob < 1.0)).float()

    hit_rate_observed = torch.where(
        hits_attempted_count > 0.0,
        hits_landed_count / torch.clamp(hits_attempted_count, min=1e-6),
        torch.ones_like(hits_landed_count),
    )
    crit_rate_observed = torch.where(
        hits_landed_count > 0.0,
        crits_landed_count / torch.clamp(hits_landed_count, min=1e-6),
        torch.zeros_like(crits_landed_count),
    )

    return AttackCascadeResult(
        F=F_mc,
        P=P_mc,
        M_moves=M_mc,
        mean_hp=mean_hp,
        faint_prob=faint_prob,
        roll_variance_alert=roll_variance_alert,
        mean_damage_dealt=mean_damage_dealt,
        hit_rate_observed=hit_rate_observed,
        crit_rate_observed=crit_rate_observed,
        redirection_events=redirection_notes,
    )


# =============================================================================
# 3. UNIFIED ENTRYPOINT (SUPPORTS TORCH & NUMPY SEAMLESSLY)
# =============================================================================

def execute_attack_cascade(
    F_init: TensorOrArray,
    P_init: TensorOrArray,
    M_moves_init: TensorOrArray,
    trainer_1_choices: TensorOrArray,
    trainer_2_choices: TensorOrArray,
    pre_attack_res: PreAttackPhaseResult,
    tables: BilinearLookupTables,
    num_mc_samples: int = 16,
    pivot_bench_choices: Optional[TensorOrArray] = None,
    forced_switch_bench_choices: Optional[TensorOrArray] = None,
    rng_seed: Optional[int] = 42,
) -> AttackCascadeResult:
    """Execute Phase 4 (Vectorized Discrete-RNG Attack Cascade) across `K = num_mc_samples` simulation threads."""
    is_torch_input = HAS_TORCH and isinstance(P_init, torch.Tensor)
    seed_val = int(rng_seed if rng_seed is not None else 42)

    if is_torch_input:
        if not isinstance(trainer_1_choices, torch.Tensor):
            trainer_1_choices = torch.from_numpy(np.asarray(trainer_1_choices, dtype=np.int64)).to(P_init.device)
        if not isinstance(trainer_2_choices, torch.Tensor):
            trainer_2_choices = torch.from_numpy(np.asarray(trainer_2_choices, dtype=np.int64)).to(P_init.device)
        return _execute_attack_cascade_torch(
            F=pre_attack_res.F,
            P=pre_attack_res.P,
            M_moves=pre_attack_res.M_moves,
            trainer_1_choices=trainer_1_choices,
            trainer_2_choices=trainer_2_choices,
            pre_attack_res=pre_attack_res,
            tables=tables,
            num_mc_samples=num_mc_samples,
            rng_seed=seed_val,
        )

    # If NumPy input is provided and PyTorch is available, execute on PyTorch CPU and convert back
    if HAS_TORCH:
        dev = torch.device("cpu")
        tables_t = build_bilinear_lookup_tables(device=dev)
        pre_t = PreAttackPhaseResult(
            F=torch.from_numpy(np.asarray(pre_attack_res.F, dtype=np.float32)),
            P=torch.from_numpy(np.asarray(pre_attack_res.P, dtype=np.float32)),
            M_moves=torch.from_numpy(np.asarray(pre_attack_res.M_moves, dtype=np.float32)),
            effective_speeds=torch.from_numpy(np.asarray(pre_attack_res.effective_speeds, dtype=np.float32)),
            effective_priorities=torch.from_numpy(np.asarray(pre_attack_res.effective_priorities, dtype=np.float32)),
            jitter_applied=torch.from_numpy(np.asarray(pre_attack_res.jitter_applied, dtype=np.float32)),
            sort_scores=torch.from_numpy(np.asarray(pre_attack_res.sort_scores, dtype=np.float32)),
            execution_order=torch.from_numpy(np.asarray(pre_attack_res.execution_order, dtype=np.int64)),
            switched_mask=torch.from_numpy(np.asarray(pre_attack_res.switched_mask, dtype=np.float32)),
            mega_evolved_mask=torch.from_numpy(np.asarray(pre_attack_res.mega_evolved_mask, dtype=np.float32)),
            speed_tie_alert=torch.from_numpy(np.asarray(pre_attack_res.speed_tie_alert, dtype=np.float32)),
            speed_tie_notes=pre_attack_res.speed_tie_notes,
        )
        res_t = _execute_attack_cascade_torch(
            F=pre_t.F,
            P=pre_t.P,
            M_moves=pre_t.M_moves,
            trainer_1_choices=torch.from_numpy(np.asarray(trainer_1_choices, dtype=np.int64)),
            trainer_2_choices=torch.from_numpy(np.asarray(trainer_2_choices, dtype=np.int64)),
            pre_attack_res=pre_t,
            tables=tables_t,
            num_mc_samples=num_mc_samples,
            rng_seed=seed_val,
        )
        return AttackCascadeResult(
            F=res_t.F.numpy(),
            P=res_t.P.numpy(),
            M_moves=res_t.M_moves.numpy(),
            mean_hp=res_t.mean_hp.numpy(),
            faint_prob=res_t.faint_prob.numpy(),
            roll_variance_alert=res_t.roll_variance_alert.numpy(),
            mean_damage_dealt=res_t.mean_damage_dealt.numpy(),
            hit_rate_observed=res_t.hit_rate_observed.numpy(),
            crit_rate_observed=res_t.crit_rate_observed.numpy(),
            redirection_events=res_t.redirection_events,
        )

    raise RuntimeError("PyTorch is required for vectorized tensor execution.")
