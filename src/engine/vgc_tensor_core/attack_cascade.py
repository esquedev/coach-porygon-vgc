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
   - Accounts for never-miss (`1.01`), `No Guard`, Rain sure-hit (`Thunder`, `Hurricane`),
     Snow sure-hit (`Blizzard`), and accuracy/evasion stat stages.
4. **Full Per-Hit Discrete Multi-Hit Loop (`MoveIdx.EXPECTED_HITS`)**:
   - Variable `2..5` hit moves spin the cartridge `35% / 35% / 15% / 15%` wheel (or `5` hits
     with `Skill Link`).
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
     `Clear Body` / `White Smoke` and triggering reactive `Defiant` (`+2 Atk`) / `Competitive` (`+2 SpA`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from .compiler import (
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
)
from .phases_pre_attack import (
    ACTIVE_SLOTS,
    PreAttackPhaseResult,
    T_ELECTRIC,
    T_GRASSY,
    T_MISTY,
    T_PSYCHIC,
    W_CLEAR,
    W_RAIN,
    W_SAND,
    W_SNOW,
    W_SUN,
    compute_active_effective_speeds,
    compute_per_thread_execution_orders,
)
from .rng_engine import (
    CARTRIDGE_16_ROLLS,
    RNGEventID,
    counter_uniform_0_100_torch,
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
    RESIST_BERRY_TO_TYPE_IDX,
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
        P: 8-Slot Roster tensor across `K` simulation threads `[B1, B2, K, 8, 87]`.
        M_moves: Move tensor across `K` simulation threads `[B1, B2, K, 8, 4, 59]`.
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
    extra_volatiles: Optional[Dict[str, TensorOrArray]] = None


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


def _check_white_herb_and_unburden_torch(
    P_mc: "torch.Tensor",
    slot_idx: "torch.Tensor",
) -> None:
    """Trigger White Herb (restoring any negative stat stages to 0.0) and Unburden on `slot_idx`."""
    hp_cur = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    item_act = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1) > 0.5
    item_id = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    abil_id = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)

    has_wh = (hp_cur > 0.0) & item_act & (item_id == float(ItemID.WHITE_HERB))
    if not torch.any(has_wh):
        return

    any_neg = torch.zeros_like(has_wh)
    for b_i in range(7):
        cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + b_i], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
        any_neg = any_neg | (cur_b < 0.0)

    wh_fires = has_wh & any_neg
    if not torch.any(wh_fires):
        return

    for b_i in range(7):
        cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + b_i], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
        restored = torch.where(wh_fires & (cur_b < 0.0), torch.zeros_like(cur_b), cur_b)
        P_mc[:, :, :, :, MonIdx.BOOST_START + b_i].scatter_(3, slot_idx.unsqueeze(-1), restored.unsqueeze(-1))

    P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
        3,
        slot_idx.unsqueeze(-1),
        torch.where(wh_fires, torch.zeros_like(hp_cur), item_act.float()).unsqueeze(-1),
    )
    is_unb = wh_fires & (abil_id == float(AbilityID.UNBURDEN))
    if torch.any(is_unb):
        cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
        P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
            3,
            slot_idx.unsqueeze(-1),
            torch.where(is_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1),
        )


def _is_side_unnerved_torch(
    P_mc: "torch.Tensor",
    slot_idx: "torch.Tensor",
) -> "torch.Tensor":
    """Return True where an opposing alive active Pokémon has Unnerve (blocking Berry triggers)."""
    t1_slots = [SLOT_TRAINER_1_A, SLOT_TRAINER_1_B]
    t2_slots = [SLOT_TRAINER_2_A, SLOT_TRAINER_2_B]
    t2_unnerve = torch.any(
        (P_mc[:, :, :, t2_slots, MonIdx.HP_CUR] > 0.0)
        & (P_mc[:, :, :, t2_slots, MonIdx.ABILITY_ID] == float(AbilityID.UNNERVE)),
        dim=-1,
    )
    t1_unnerve = torch.any(
        (P_mc[:, :, :, t1_slots, MonIdx.HP_CUR] > 0.0)
        & (P_mc[:, :, :, t1_slots, MonIdx.ABILITY_ID] == float(AbilityID.UNNERVE)),
        dim=-1,
    )
    return torch.where(slot_idx < 4, t2_unnerve, t1_unnerve)


def _check_sitrus_berry_and_unburden_torch(
    P_mc: "torch.Tensor",
    slot_idx: "torch.Tensor",
    blocked_mask: Optional["torch.Tensor"] = None,
) -> None:
    """Trigger Sitrus Berry (+25% max HP when 0 < HP <= 50% max HP) and Unburden on `slot_idx`."""
    hp_cur = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    hp_max = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    item_act = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1) > 0.5
    item_id = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    abil_id = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)

    sitrus_fires = (
        (hp_cur > 0.0)
        & (hp_cur <= torch.floor(hp_max * 0.50))
        & item_act
        & (item_id == float(ItemID.SITRUS_BERRY))
    )
    if blocked_mask is not None:
        sitrus_fires = sitrus_fires & (~blocked_mask)
    if not torch.any(sitrus_fires):
        return

    heal_amt = torch.clamp(torch.floor(hp_max * 0.25), min=1.0)
    new_hp = torch.minimum(hp_cur + torch.where(sitrus_fires, heal_amt, torch.zeros_like(heal_amt)), hp_max)
    P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, slot_idx.unsqueeze(-1), new_hp.unsqueeze(-1))
    P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
        3,
        slot_idx.unsqueeze(-1),
        torch.where(sitrus_fires, torch.zeros_like(hp_cur), item_act.float()).unsqueeze(-1),
    )
    is_unb = sitrus_fires & (abil_id == float(AbilityID.UNBURDEN))
    if torch.any(is_unb):
        cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
        P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
            3,
            slot_idx.unsqueeze(-1),
            torch.where(is_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1),
        )


def _check_lum_berry_and_unburden_torch(
    P_mc: "torch.Tensor",
    slot_idx: "torch.Tensor",
    blocked_mask: Optional["torch.Tensor"] = None,
) -> None:
    """Trigger Lum Berry (curing any primary status condition) and Unburden on `slot_idx`."""
    hp_cur = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    healthy = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, slot_idx.unsqueeze(-1)).squeeze(-1) > 0.5
    item_act = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1) > 0.5
    item_id = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    abil_id = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)

    lum_fires = (hp_cur > 0.0) & (~healthy) & item_act & (item_id == float(ItemID.LUM_BERRY))
    if blocked_mask is not None:
        lum_fires = lum_fires & (~blocked_mask)
    if not torch.any(lum_fires):
        return

    for st_i in range(7):
        target_bit = torch.ones_like(hp_cur) if st_i == 0 else torch.zeros_like(hp_cur)
        cur_bit = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_START + st_i], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
        P_mc[:, :, :, :, MonIdx.STATUS_START + st_i].scatter_(
            3, slot_idx.unsqueeze(-1), torch.where(lum_fires, target_bit, cur_bit).unsqueeze(-1)
        )
    P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
        3,
        slot_idx.unsqueeze(-1),
        torch.where(lum_fires, torch.zeros_like(hp_cur), item_act.float()).unsqueeze(-1),
    )
    is_unb = lum_fires & (abil_id == float(AbilityID.UNBURDEN))
    if torch.any(is_unb):
        cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
        P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
            3,
            slot_idx.unsqueeze(-1),
            torch.where(is_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1),
        )


def _check_chesto_berry_and_unburden_torch(
    P_mc: "torch.Tensor",
    slot_idx: "torch.Tensor",
    blocked_mask: Optional["torch.Tensor"] = None,
) -> None:
    """Trigger Chesto Berry (curing Sleep) and Unburden on `slot_idx`."""
    hp_cur = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    asleep = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_SLEEP], 3, slot_idx.unsqueeze(-1)).squeeze(-1) > 0.5
    item_act = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1) > 0.5
    item_id = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    abil_id = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)

    chesto_fires = (hp_cur > 0.0) & asleep & item_act & (item_id == float(ItemID.CHESTO_BERRY))
    if blocked_mask is not None:
        chesto_fires = chesto_fires & (~blocked_mask)
    if not torch.any(chesto_fires):
        return

    P_mc[:, :, :, :, MonIdx.STATUS_SLEEP].scatter_(
        3,
        slot_idx.unsqueeze(-1),
        torch.where(chesto_fires, torch.zeros_like(hp_cur), asleep.float()).unsqueeze(-1),
    )
    cur_h = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY].scatter_(
        3,
        slot_idx.unsqueeze(-1),
        torch.where(chesto_fires, torch.ones_like(hp_cur), cur_h).unsqueeze(-1),
    )
    P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
        3,
        slot_idx.unsqueeze(-1),
        torch.where(chesto_fires, torch.zeros_like(hp_cur), item_act.float()).unsqueeze(-1),
    )
    is_unb = chesto_fires & (abil_id == float(AbilityID.UNBURDEN))
    if torch.any(is_unb):
        cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
        P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
            3,
            slot_idx.unsqueeze(-1),
            torch.where(is_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1),
        )


def _check_mental_herb_and_unburden_torch(
    P_mc: "torch.Tensor",
    slot_idx: "torch.Tensor",
) -> None:
    """Trigger Mental Herb (curing Taunt and Encore) and Unburden on `slot_idx`."""
    hp_cur = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    taunt_t = torch.gather(P_mc[:, :, :, :, MonIdx.TAUNT_TURNS], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    encore_t = torch.gather(P_mc[:, :, :, :, MonIdx.ENCORE_TURNS], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    item_act = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1) > 0.5
    item_id = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
    abil_id = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, slot_idx.unsqueeze(-1)).squeeze(-1)

    mh_fires = (hp_cur > 0.0) & item_act & (item_id == float(ItemID.MENTAL_HERB)) & ((taunt_t > 0.0) | (encore_t > 0.0))
    if not torch.any(mh_fires):
        return

    P_mc[:, :, :, :, MonIdx.TAUNT_TURNS].scatter_(
        3, slot_idx.unsqueeze(-1), torch.where(mh_fires, torch.zeros_like(taunt_t), taunt_t).unsqueeze(-1)
    )
    P_mc[:, :, :, :, MonIdx.ENCORE_TURNS].scatter_(
        3, slot_idx.unsqueeze(-1), torch.where(mh_fires, torch.zeros_like(encore_t), encore_t).unsqueeze(-1)
    )
    P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
        3, slot_idx.unsqueeze(-1), torch.where(mh_fires, torch.zeros_like(hp_cur), item_act.float()).unsqueeze(-1)
    )
    is_unb = mh_fires & (abil_id == float(AbilityID.UNBURDEN))
    if torch.any(is_unb):
        cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, slot_idx.unsqueeze(-1)).squeeze(-1)
        P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
            3, slot_idx.unsqueeze(-1), torch.where(is_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1)
        )


@dataclass(frozen=True)
class _RosterFeatureFlags:
    """Static roster feature summary computed once on CPU before the 4-actor cascade loop.

    Eliminates redundant GPU->CPU `torch.any()` pipeline sync stalls for mechanics absent from the 8-slot roster.
    """

    has_cloud_nine: bool
    has_fairy_aura: bool
    has_white_herb: bool
    has_sitrus_berry: bool
    has_lum_berry: bool
    has_mental_herb: bool
    has_air_balloon: bool
    has_rocky_helmet: bool
    has_resist_berry: bool
    has_focus_sash: bool
    has_life_orb: bool
    has_choice_item: bool
    has_stamina: bool
    has_contact_punish: bool
    has_poison_touch: bool
    has_lightning_rod: bool
    has_unnerve: bool
    has_damp: bool
    has_chesto_berry: bool
    has_shell_bell: bool
    has_eject_red_card: bool
    has_berserk: bool
    has_innards_out: bool
    has_eelevate: bool
    has_spicy_spray: bool
    has_justified: bool
    has_thermal_exchange: bool
    has_protean: bool
    has_mega_sol: bool


def _build_roster_feature_flags(P: "torch.Tensor") -> _RosterFeatureFlags:
    """Inspect the 8 roster slots of `P[0, 0]` once on CPU to build static presence flags."""
    p0 = P[0, 0].detach().cpu().numpy()  # [8, MON_DIM]
    ab_set = set(np.round(p0[:, MonIdx.ABILITY_ID]).astype(int).tolist()) | set(
        np.round(p0[:, MonIdx.MEGA_ABILITY_ID]).astype(int).tolist()
    )
    it_set = set(np.round(p0[:, MonIdx.ITEM_ID]).astype(int).tolist())
    resist_berry_ids = {int(k) for k in RESIST_BERRY_TO_TYPE_IDX.keys()}

    return _RosterFeatureFlags(
        has_cloud_nine=int(AbilityID.CLOUD_NINE) in ab_set,
        has_fairy_aura=int(AbilityID.FAIRY_AURA) in ab_set,
        has_white_herb=int(ItemID.WHITE_HERB) in it_set,
        has_sitrus_berry=int(ItemID.SITRUS_BERRY) in it_set,
        has_lum_berry=int(ItemID.LUM_BERRY) in it_set,
        has_mental_herb=int(ItemID.MENTAL_HERB) in it_set,
        has_air_balloon=int(ItemID.AIR_BALLOON) in it_set,
        has_rocky_helmet=int(ItemID.ROCKY_HELMET) in it_set,
        has_resist_berry=bool(it_set & resist_berry_ids),
        has_focus_sash=int(ItemID.FOCUS_SASH) in it_set,
        has_life_orb=int(ItemID.LIFE_ORB) in it_set,
        has_choice_item=int(ItemID.CHOICE_SCARF) in it_set,
        has_stamina=int(AbilityID.STAMINA) in ab_set,
        has_contact_punish=(
            int(AbilityID.ROUGH_SKIN) in ab_set
            or int(AbilityID.FLAME_BODY) in ab_set
            or int(ItemID.ROCKY_HELMET) in it_set
        ),
        has_poison_touch=int(AbilityID.POISON_TOUCH) in ab_set,
        has_lightning_rod=int(AbilityID.LIGHTNING_ROD) in ab_set,
        has_unnerve=int(AbilityID.UNNERVE) in ab_set,
        has_damp=int(AbilityID.DAMP) in ab_set,
        has_chesto_berry=int(ItemID.CHESTO_BERRY) in it_set,
        has_shell_bell=int(ItemID.SHELL_BELL) in it_set,
        has_eject_red_card=(int(ItemID.EJECT_BUTTON) in it_set or int(ItemID.RED_CARD) in it_set),
        has_berserk=int(AbilityID.BERSERK) in ab_set,
        has_innards_out=int(AbilityID.INNARDS_OUT) in ab_set,
        has_eelevate=int(AbilityID.EELEVATE) in ab_set,
        has_spicy_spray=int(AbilityID.SPICY_SPRAY) in ab_set,
        has_justified=int(AbilityID.JUSTIFIED) in ab_set,
        has_thermal_exchange=int(AbilityID.THERMAL_EXCHANGE) in ab_set,
        has_protean=int(AbilityID.PROTEAN) in ab_set,
        has_mega_sol=int(AbilityID.MEGA_SOL) in ab_set,
    )


# =============================================================================
# 2. PYTORCH VECTORIZED DISCRETE-RNG ATTACK CASCADE (GPU / CPU)
# =============================================================================

def _execute_attack_cascade_torch(
    F: "torch.Tensor",             # [B1, B2, 24]
    P: "torch.Tensor",             # [B1, B2, 8, 87]
    M_moves: "torch.Tensor",       # [B1, B2, 8, 4, 59]
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
    flags = _build_roster_feature_flags(P)

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

    # Per-thread initial speed-tie execution order & dynamic turn-order state: [B1, B2, K, 4]
    exec_order_k = compute_per_thread_execution_orders(
        F_mc=F_mc,
        eff_speeds=pre_attack_res.effective_speeds.to(device),
        eff_priorities=pre_attack_res.effective_priorities.to(device),
        num_sim_threads=K,
        rng_seed=seed,
    )
    prio_k = pre_attack_res.effective_priorities.to(device).unsqueeze(2).expand(B1, B2, K, 4)
    w_start_tie = counter_uniform_0_100_torch(
        (B1, B2, K, 4), device, seed, int(RNGEventID.SPEED_TIE_JITTER), step_idx=1, sub_draw=0
    )
    dart_tie = counter_uniform_0_100_torch(
        (B1, B2, K, 4), device, seed, int(RNGEventID.SPEED_TIE_JITTER), step_idx=1, sub_draw=1
    )
    jitter_k = (torch.remainder(dart_tie - w_start_tie + 100.0, 100.0) / 100.0) * 0.02 - 0.01
    acted_mask_k = torch.zeros((B1, B2, K, 4), dtype=torch.bool, device=device)

    active_slot_lut = torch.tensor(ACTIVE_SLOTS, dtype=torch.long, device=device)
    type_chart = tables.m_type_chart.to(device)
    w_chart = tables.m_weather_mod.to(device)
    t_chart = tables.m_terrain_mod.to(device)
    berry_lut = tables.resist_berry_type_lut.to(device)

    # Side redirection trackers per thread: -1 if none, else slot index (0, 1, 4, 5)
    redir_t1 = torch.full((B1, B2, K), -1, dtype=torch.long, device=device)
    redir_t2 = torch.full((B1, B2, K), -1, dtype=torch.long, device=device)

    mean_damage_dealt = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    hits_landed_count = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    hits_attempted_count = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    crits_landed_count = torch.zeros((B1, B2, 4), dtype=torch.float32, device=device)
    redirection_notes: List[str] = []
    extra_volatiles_dict: Dict[str, "torch.Tensor"] = {}

    def _get_ev(key: str) -> "torch.Tensor":
        t = extra_volatiles_dict.get(key)
        if t is None:
            t = torch.zeros((B1, B2, K, ROSTER_SLOTS), dtype=torch.float32, device=device)
            extra_volatiles_dict[key] = t
        return t

    # Track slots that started this turn locked in forced recharge (to clear ONLY them after the turn)
    started_recharging = P_mc[:, :, :, :, MonIdx.MUST_RECHARGE] > 0.5

    for step_idx in range(4):
        if step_idx == 0:
            actor_act_idx = exec_order_k[:, :, :, 0].long()  # [B1, B2, K] in {0, 1, 2, 3}
        else:
            # Dynamically recompute effective speed & Trick Room order for remaining un-acted slots
            cur_spe_k = compute_active_effective_speeds(F_mc, P_mc)  # [B1, B2, K, 4]
            tr_act_k = (F_mc[:, :, :, FieldIdx.TRICK_ROOM_TURNS] > 0.0).float().unsqueeze(-1)
            tr_sign_k = 1.0 - 2.0 * tr_act_k
            dyn_scores_k = torch.where(
                acted_mask_k,
                torch.full_like(cur_spe_k, -1e9),
                (prio_k * 10000.0) + (tr_sign_k * cur_spe_k) + jitter_k,
            )
            actor_act_idx = torch.argmax(dyn_scores_k, dim=-1).long()

        acted_mask_k.scatter_(3, actor_act_idx.unsqueeze(-1), True)
        actor_slot = active_slot_lut[actor_act_idx]             # [B1, B2, K] in {0, 1, 4, 5}
        is_t1 = actor_act_idx < 2                               # [B1, B2, K]

        switched = torch.gather(switched_4, 3, actor_act_idx.unsqueeze(-1)).squeeze(-1) > 0.5
        choice_val = torch.gather(choices_4, 3, actor_act_idx.unsqueeze(-1)).squeeze(-1)
        is_switch_choice = (choice_val == CHOICE_SWITCH_BENCH1) | (choice_val == CHOICE_SWITCH_BENCH2)

        move_idx = (choice_val % 12) % 4
        target_code = ((choice_val % 12) // 4) % 3  # 0: Opp A, 1: Opp B, 2: Ally Partner

        if flags.has_mental_herb:
            _check_mental_herb_and_unburden_torch(P_mc, actor_slot)

        # Gather actor Pokemon vector: [B1, B2, K, 87]
        act_slot_exp_mon = actor_slot.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
        p_actor = torch.gather(P_mc, 3, act_slot_exp_mon).squeeze(3)

        actor_hp = p_actor[:, :, :, MonIdx.HP_CUR]
        actor_flinched = p_actor[:, :, :, MonIdx.FLINCHED] > 0.5
        actor_recharging = p_actor[:, :, :, MonIdx.MUST_RECHARGE] > 0.5
        can_act = (actor_hp > 0.0) & (~actor_flinched) & (~actor_recharging) & (~switched) & (~is_switch_choice)

        if not torch.any(can_act):
            continue

        # Gather chosen move vector: [B1, B2, K, 59] without 4x move-slot expansion
        flat_slot_mv = (actor_slot * MOVES_PER_MON + move_idx).view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MOVE_DIM)
        if not m_mc_is_cloned:
            m_flat_base = M_moves.view(B1, B2, 1, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM).expand(
                B1, B2, K, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM
            )
            chosen_move = torch.gather(m_flat_base, 3, flat_slot_mv).squeeze(3)
        else:
            m_flat_mc = M_mc.view(B1, B2, K, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM)
            chosen_move = torch.gather(m_flat_mc, 3, flat_slot_mv).squeeze(3)

        # Turn-1 Only Move Gate (Fake Out / First Impression fail if ACTIVE_TURNS > 0)
        is_first_turn_move = (chosen_move[:, :, :, MoveIdx.FIRST_TURN_ONLY] > 0.5) | (
            torch.round(chosen_move[:, :, :, MoveIdx.FIELD_OP_ID]).long() == int(FieldOpID.FAKE_OUT)
        )
        can_act = can_act & ((~is_first_turn_move) | (p_actor[:, :, :, MonIdx.ACTIVE_TURNS] <= 0.0))
        if not torch.any(can_act):
            continue

        move_type_idx = torch.argmax(chosen_move[:, :, :, MoveIdx.TYPE_START:MoveIdx.TYPE_END], dim=-1)
        cat_idx = torch.argmax(chosen_move[:, :, :, MoveIdx.CAT_START:MoveIdx.CAT_END], dim=-1)
        base_power = chosen_move[:, :, :, MoveIdx.BASE_POWER]
        w_sure = chosen_move[:, :, :, MoveIdx.WEATHER_SURE_HIT]
        att_ab = p_actor[:, :, :, MonIdx.ABILITY_ID]

        # Dynamic Cloud Nine check across all active slots
        act_slots_idx = [SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_2_A, SLOT_TRAINER_2_B]
        w_raw = torch.argmax(F_mc[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END], dim=-1)
        if flags.has_cloud_nine:
            ab_act = P_mc[:, :, :, act_slots_idx, MonIdx.ABILITY_ID]
            hp_act = P_mc[:, :, :, act_slots_idx, MonIdx.HP_CUR]
            cloud_nine_active = torch.any((hp_act > 0.0) & (ab_act == float(AbilityID.CLOUD_NINE)), dim=-1)
            w_idx = torch.where(cloud_nine_active, torch.zeros_like(w_raw), w_raw)
        else:
            w_idx = w_raw

        # Mega Sol: holder treats active weather as Sun for its own moves (Weather Ball, Solar Beam, Synthesis, damage)
        if flags.has_mega_sol:
            w_idx_actor = torch.where(
                att_ab == float(AbilityID.MEGA_SOL),
                torch.full_like(w_idx, W_SUN),
                w_idx,
            )
        else:
            w_idx_actor = w_idx

        # Dynamic Weather Ball adaptation (Channel 50 code == 1.0)
        is_weather_ball = w_sure == 1.0
        if torch.any(is_weather_ball):
            wb_type = torch.where(
                w_idx_actor == W_SUN,
                torch.tensor(TYPE_TO_IDX["fire"], device=device),
                torch.where(
                    w_idx_actor == W_RAIN,
                    torch.tensor(TYPE_TO_IDX["water"], device=device),
                    torch.where(
                        w_idx_actor == W_SAND,
                        torch.tensor(TYPE_TO_IDX["rock"], device=device),
                        torch.where(
                            w_idx_actor == W_SNOW,
                            torch.tensor(TYPE_TO_IDX["ice"], device=device),
                            torch.tensor(TYPE_TO_IDX["normal"], device=device),
                        ),
                    ),
                ),
            )
            wb_bp = torch.where(w_idx_actor != W_CLEAR, torch.full_like(base_power, 100.0), torch.full_like(base_power, 50.0))
            move_type_idx = torch.where(is_weather_ball, wb_type, move_type_idx)
            base_power = torch.where(is_weather_ball, wb_bp, base_power)

        # Liquid Voice (Sound moves become Water-type)
        is_liquid_voice = (att_ab == float(AbilityID.LIQUID_VOICE)) & (chosen_move[:, :, :, MoveIdx.IS_SOUND_MOVE] > 0.5)
        move_type_idx = torch.where(
            is_liquid_voice,
            torch.tensor(TYPE_TO_IDX["water"], dtype=move_type_idx.dtype, device=device),
            move_type_idx,
        )

        # Aerilate, Pixilate, Refrigerate, Dragonize (Normal moves become Flying/Fairy/Ice/Dragon + 1.2x BP)
        is_normal_move = (move_type_idx == TYPE_TO_IDX["normal"]) & (~is_weather_ball) & (~is_liquid_voice)
        is_aerilate = is_normal_move & (att_ab == float(AbilityID.AERILATE))
        is_pixilate = is_normal_move & (att_ab == float(AbilityID.PIXILATE))
        is_refrigerate = is_normal_move & (att_ab == float(AbilityID.REFRIGERATE))
        is_dragonize = is_normal_move & (att_ab == float(AbilityID.DRAGONIZE))
        is_ate_boost = (is_aerilate | is_pixilate | is_refrigerate | is_dragonize) & (cat_idx != 2)
        move_type_idx = torch.where(
            is_aerilate,
            torch.tensor(TYPE_TO_IDX["flying"], dtype=move_type_idx.dtype, device=device),
            torch.where(
                is_pixilate,
                torch.tensor(TYPE_TO_IDX["fairy"], dtype=move_type_idx.dtype, device=device),
                torch.where(
                    is_refrigerate,
                    torch.tensor(TYPE_TO_IDX["ice"], dtype=move_type_idx.dtype, device=device),
                    torch.where(
                        is_dragonize,
                        torch.tensor(TYPE_TO_IDX["dragon"], dtype=move_type_idx.dtype, device=device),
                        move_type_idx,
                    ),
                ),
            ),
        )
        base_power = torch.where(is_ate_boost, torch.floor(base_power * 4915.0 / 4096.0), base_power)

        # Dynamic Two-Turn Charging Move Gates (Turn 1: deals 0 damage if must charge)
        is_solar_charge = (w_sure == 10.0) & (w_idx_actor != W_SUN)
        is_electro_charge = (w_sure == 20.0) & (w_idx_actor != W_RAIN)
        is_general_charge = (w_sure == 30.0)
        must_charge = is_solar_charge | is_electro_charge | is_general_charge
        base_power = torch.where(must_charge, torch.zeros_like(base_power), base_power)

        # Solar Beam / Blade base power halved in Rain, Sand, Snow when firing
        is_solar_halved = (w_sure == 10.0) & ((w_idx_actor == W_RAIN) | (w_idx_actor == W_SAND) | (w_idx_actor == W_SNOW))
        base_power = torch.where(is_solar_halved & (~must_charge), base_power * 0.5, base_power)

        # Electro Shot in Rain grants +1 SpA (-1 SpA if Contrary) immediately BEFORE calculating damage
        is_electro_rain_boost = can_act & (w_sure == 20.0) & (w_idx_actor == W_RAIN) & (~must_charge)
        if torch.any(is_electro_rain_boost):
            cur_spa_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_SPA], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            el_sign = torch.where(att_ab == float(AbilityID.CONTRARY), -torch.ones_like(cur_spa_b), torch.ones_like(cur_spa_b))
            new_spa_b = torch.clamp(
                cur_spa_b + torch.where(is_electro_rain_boost, el_sign, torch.zeros_like(cur_spa_b)),
                min=-6.0,
                max=6.0,
            )
            P_mc[:, :, :, :, MonIdx.BOOST_SPA].scatter_(3, actor_slot.unsqueeze(-1), new_spa_b.unsqueeze(-1))
            p_actor = torch.gather(P_mc, 3, act_slot_exp_mon).squeeze(3)

        # ---------------------------------------------------------------------
        # A. DISCRETE STATUS IMMOBILIZATION GATES (SLEEP, FREEZE, PARALYSIS)
        # ---------------------------------------------------------------------
        # Chesto Berry / Lum Berry cure Sleep before Sleep roll (unless Unnerved)
        if flags.has_chesto_berry or flags.has_lum_berry:
            act_unnerved = _is_side_unnerved_torch(P_mc, actor_slot) if flags.has_unnerve else None
            if flags.has_chesto_berry:
                _check_chesto_berry_and_unburden_torch(P_mc, actor_slot, blocked_mask=act_unnerved)
            if flags.has_lum_berry:
                _check_lum_berry_and_unburden_torch(P_mc, actor_slot, blocked_mask=act_unnerved)
            p_actor = torch.gather(P_mc, 3, act_slot_exp_mon).squeeze(3)

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

        # Protean: actor changes its typing to match the chosen move type (grants STAB!)
        if flags.has_protean:
            is_protean = can_act & (att_ab == float(AbilityID.PROTEAN))
            if torch.any(is_protean):
                prot_t1 = torch.nn.functional.one_hot(move_type_idx, num_classes=18).to(torch.float32)
                act_slot_t1 = actor_slot.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, 18)
                cur_t1 = torch.gather(P_mc[:, :, :, :, MonIdx.TYPE1_START:MonIdx.TYPE1_END], 3, act_slot_t1).squeeze(3)
                cur_t2 = torch.gather(P_mc[:, :, :, :, MonIdx.TYPE2_START:MonIdx.TYPE2_END], 3, act_slot_t1).squeeze(3)
                P_mc[:, :, :, :, MonIdx.TYPE1_START:MonIdx.TYPE1_END].scatter_(
                    3, act_slot_t1, torch.where(is_protean.unsqueeze(-1), prot_t1, cur_t1).unsqueeze(3)
                )
                P_mc[:, :, :, :, MonIdx.TYPE2_START:MonIdx.TYPE2_END].scatter_(
                    3, act_slot_t1, torch.where(is_protean.unsqueeze(-1), torch.zeros_like(cur_t2), cur_t2).unsqueeze(3)
                )
                p_actor = torch.gather(P_mc, 3, act_slot_exp_mon).squeeze(3)

        # Damp suppresses Explosion / Self-Destruct / Misty Explosion while any alive active mon has Damp
        field_op_pre = torch.round(chosen_move[:, :, :, MoveIdx.FIELD_OP_ID]).long()
        is_explosion_move = field_op_pre == int(FieldOpID.EXPLOSION)
        if flags.has_damp and torch.any(can_act & is_explosion_move):
            damp_active = torch.any(
                (P_mc[:, :, :, act_slots_idx, MonIdx.HP_CUR] > 0.0)
                & (P_mc[:, :, :, act_slots_idx, MonIdx.ABILITY_ID] == float(AbilityID.DAMP)),
                dim=-1,
            )
            can_act = can_act & (~(is_explosion_move & damp_active))
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
        if flags.has_choice_item:
            is_choice_item = act_item_active & (act_item == float(ItemID.CHOICE_SCARF))
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
            for op_code, w_set_idx in (
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
                    F_mc[:, :, :, FieldIdx.WEATHER_START + w_set_idx] = torch.where(
                        m_w, torch.ones_like(actor_hp), F_mc[:, :, :, FieldIdx.WEATHER_START + w_set_idx]
                    )
                    F_mc[:, :, :, FieldIdx.WEATHER_TURNS] = torch.where(
                        m_w, torch.full_like(actor_hp, 5.0), F_mc[:, :, :, FieldIdx.WEATHER_TURNS]
                    )

            # Terrain moves (8 turns with Terrain Extender, 5 turns otherwise)
            has_terrain_ext = act_item_active & (act_item == float(ItemID.TERRAIN_EXTENDER))
            terr_turns_val = torch.where(has_terrain_ext, torch.full_like(actor_hp, 8.0), torch.full_like(actor_hp, 5.0))
            for op_code, tr_set_idx in (
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
                    F_mc[:, :, :, FieldIdx.TERRAIN_START + tr_set_idx] = torch.where(
                        m_tr, torch.ones_like(actor_hp), F_mc[:, :, :, FieldIdx.TERRAIN_START + tr_set_idx]
                    )
                    F_mc[:, :, :, FieldIdx.TERRAIN_TURNS] = torch.where(
                        m_tr, terr_turns_val, F_mc[:, :, :, FieldIdx.TERRAIN_TURNS]
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

            # Gravity (sets GRAVITY_TURNS = 5.0)
            m_grav = has_field_op & (field_op == int(FieldOpID.GRAVITY))
            if torch.any(m_grav):
                F_mc[:, :, :, FieldIdx.GRAVITY_TURNS] = torch.where(
                    m_grav, torch.full_like(actor_hp, 5.0), F_mc[:, :, :, FieldIdx.GRAVITY_TURNS]
                )

            # Haze status move (resets all active stat stages to 0.0)
            m_haze = has_field_op & (field_op == int(FieldOpID.HAZE)) & (cat_idx == 2)
            if torch.any(m_haze):
                for act_s in act_slots_idx:
                    P_mc[:, :, :, act_s, MonIdx.BOOST_START:MonIdx.BOOST_END] = torch.where(
                        m_haze.unsqueeze(-1),
                        torch.zeros_like(P_mc[:, :, :, act_s, MonIdx.BOOST_START:MonIdx.BOOST_END]),
                        P_mc[:, :, :, act_s, MonIdx.BOOST_START:MonIdx.BOOST_END],
                    )
                p_actor = torch.gather(P_mc, 3, act_slot_exp_mon).squeeze(3)

            # Reflect, Light Screen, Aurora Veil (8 turns with Light Clay, 5 turns otherwise;
            # Aurora Veil strictly requires active Snow and no Cloud Nine)
            has_light_clay = act_item_active & (act_item == float(ItemID.LIGHT_CLAY))
            scr_turns_val = torch.where(has_light_clay, torch.full_like(actor_hp, 8.0), torch.full_like(actor_hp, 5.0))
            for op_code, t1_fidx, t2_fidx in (
                (int(FieldOpID.REFLECT), FieldIdx.TRAINER_1_REFLECT_TURNS, FieldIdx.TRAINER_2_REFLECT_TURNS),
                (int(FieldOpID.LIGHT_SCREEN), FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS, FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS),
                (int(FieldOpID.AURORA_VEIL), FieldIdx.TRAINER_1_AURORA_VEIL_TURNS, FieldIdx.TRAINER_2_AURORA_VEIL_TURNS),
            ):
                m_sc = has_field_op & (field_op == op_code)
                if op_code == int(FieldOpID.AURORA_VEIL):
                    m_sc = m_sc & (w_idx == W_SNOW)
                if torch.any(m_sc):
                    F_mc[:, :, :, t1_fidx] = torch.where(m_sc & is_t1, scr_turns_val, F_mc[:, :, :, t1_fidx])
                    F_mc[:, :, :, t2_fidx] = torch.where(m_sc & (~is_t1), scr_turns_val, F_mc[:, :, :, t2_fidx])

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

            # Perish Song (applies 3-turn Perish counter to all alive non-Soundproof active mons)
            m_perish = has_field_op & (field_op == int(FieldOpID.PERISH_SONG))
            if torch.any(m_perish):
                ps_buf = _get_ev("perish_song")
                att_mb = att_ab == float(AbilityID.MOLD_BREAKER)
                for act_s in act_slots_idx:
                    s_alive_ps = P_mc[:, :, :, act_s, MonIdx.HP_CUR] > 0.0
                    s_soundproof = (P_mc[:, :, :, act_s, MonIdx.ABILITY_ID] == float(AbilityID.SOUNDPROOF)) & (~att_mb)
                    applies_ps = m_perish & s_alive_ps & (~s_soundproof) & (ps_buf[:, :, :, act_s] <= 0.0)
                    ps_buf[:, :, :, act_s] = torch.where(applies_ps, torch.full_like(actor_hp, 3.0), ps_buf[:, :, :, act_s])

        if not torch.any(can_act):
            continue

        # ---------------------------------------------------------------------
        # D. SELF-HEALING STATUS MOVES (RECOVER / ROOST / PROTECT / ETC.)
        # ---------------------------------------------------------------------
        recoil_pct = chosen_move[:, :, :, MoveIdx.RECOIL_PCT]
        target_type_code = torch.round(chosen_move[:, :, :, MoveIdx.TARGET_TYPE]).long()

        # Expanding Force in Psychic Terrain (when attacker is grounded): 80 -> 120 BP and becomes ALL_ADJACENT_FOES
        tr_idx_now = torch.argmax(F_mc[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END], dim=-1)
        grav_on_now = F_mc[:, :, :, FieldIdx.GRAVITY_TURNS] > 0.0
        att_grounded_now = (p_actor[:, :, :, MonIdx.GROUNDED_FLAG] > 0.5) | grav_on_now
        is_exp_force_psy = (
            (tr_idx_now == T_PSYCHIC)
            & att_grounded_now
            & (move_type_idx == TYPE_TO_IDX["psychic"])
            & (cat_idx == 1)
            & (torch.abs(base_power - 80.0) < 0.5)
            & (target_type_code == int(TargetType.SINGLE_FOE))
        )
        if torch.any(is_exp_force_psy):
            base_power = torch.where(is_exp_force_psy, torch.full_like(base_power, 120.0), base_power)
            target_type_code = torch.where(
                is_exp_force_psy,
                torch.full_like(target_type_code, int(TargetType.ALL_ADJACENT_FOES)),
                target_type_code,
            )

        is_self_heal = can_act & (cat_idx == 2) & (recoil_pct < 0.0) & (target_type_code == int(TargetType.SELF))
        if torch.any(is_self_heal):
            cur_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            max_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            eff_heal_pct = torch.abs(recoil_pct)
            # Weather-scaling recovery (Synthesis / Morning Sun / Moonlight: 2/3 Sun/Mega Sol, 1/2 Clear, 1/4 Rain/Sand/Snow)
            is_w_heal = w_sure == 5.0
            if torch.any(is_self_heal & is_w_heal):
                w_heal_frac = torch.where(
                    w_idx_actor == W_SUN,
                    torch.full_like(eff_heal_pct, 2.0 / 3.0),
                    torch.where(
                        w_idx_actor == W_CLEAR,
                        torch.full_like(eff_heal_pct, 0.50),
                        torch.full_like(eff_heal_pct, 0.25),
                    ),
                )
                eff_heal_pct = torch.where(is_w_heal, w_heal_frac, eff_heal_pct)
            heal_val = torch.clamp(torch.floor(max_a_hp * eff_heal_pct), min=1.0)
            new_a_hp = torch.clamp(cur_a_hp + torch.where(is_self_heal, heal_val, torch.zeros_like(heal_val)), max=max_a_hp)
            P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), new_a_hp.unsqueeze(-1))

        # ---------------------------------------------------------------------
        # E. SELF-TARGETING STAT BOOST MOVES (SWORDS DANCE / NASTY PLOT / TAIL GLOW)
        # ---------------------------------------------------------------------
        stat_self_flag = chosen_move[:, :, :, MoveIdx.STAT_DELTA_SELF] > 0.5
        stat_chance_pct = chosen_move[:, :, :, MoveIdx.STAT_DELTA_CHANCE] * 100.0
        is_self_status_boost = can_act & (cat_idx == 2) & stat_self_flag & (stat_chance_pct > 0.0)
        if torch.any(is_self_status_boost):
            self_contrary = att_ab == float(AbilityID.CONTRARY)
            for s_i in range(7):
                delta_v = chosen_move[:, :, :, MoveIdx.STAT_DELTA_START + s_i]
                if torch.any(is_self_status_boost & (delta_v != 0.0)):
                    eff_dv = torch.where(self_contrary, -delta_v, delta_v)
                    cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                    new_b = torch.clamp(cur_b + torch.where(is_self_status_boost, eff_dv, torch.zeros_like(eff_dv)), min=-6.0, max=6.0)
                    P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(3, actor_slot.unsqueeze(-1), new_b.unsqueeze(-1))
            if flags.has_white_herb:
                _check_white_herb_and_unburden_torch(P_mc, actor_slot)
            p_actor = torch.gather(P_mc, 3, act_slot_exp_mon).squeeze(3)

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

        # Follow Me / Rage Powder redirection check (only redirects single-target foe moves; bypassed by Stalwart)
        is_stalwart = att_ab == float(AbilityID.STALWART)
        opp_redir_slot = torch.where(is_t1, redir_t2, redir_t1)
        has_opp_redir = (opp_redir_slot >= 0) & (target_code != 2) & (~is_spread) & (~is_stalwart)
        redir_clamped = torch.clamp(opp_redir_slot, min=0, max=7)
        redir_alive = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, redir_clamped.unsqueeze(-1)).squeeze(-1) > 0.0
        if torch.any(has_opp_redir & redir_alive):
            redirection_notes.append("Follow Me / Rage Powder redirection")
        single_tgt = torch.where(has_opp_redir & redir_alive, redir_clamped, decl_single)

        # Lightning Rod redirection for single-target Electric moves (when not already redirected by Follow Me; bypassed by Stalwart)
        if flags.has_lightning_rod:
            is_st_elec = (
                can_act
                & (~is_spread)
                & (~is_stalwart)
                & (target_type_code == int(TargetType.SINGLE_FOE))
                & (move_type_idx == TYPE_TO_IDX["electric"])
                & (~(has_opp_redir & redir_alive))
            )
            if torch.any(is_st_elec):
                for cand_s in (opp_slot_a, opp_slot_b, partner_slot):
                    c_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, cand_s.unsqueeze(-1)).squeeze(-1)
                    c_ab = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, cand_s.unsqueeze(-1)).squeeze(-1)
                    lr_pulls = is_st_elec & (cand_s != actor_slot) & (c_hp > 0.0) & (c_ab == float(AbilityID.LIGHTNING_ROD))
                    if torch.any(lr_pulls):
                        redirection_notes.append("Lightning Rod redirection")
                        single_tgt = torch.where(lr_pulls, cand_s, single_tgt)
                        is_st_elec = is_st_elec & (~lr_pulls)

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
        opp_a_alive_now = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, opp_slot_a.unsqueeze(-1)).squeeze(-1) > 0.0
        opp_b_alive_now = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, opp_slot_b.unsqueeze(-1)).squeeze(-1) > 0.0
        partner_alive_now = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, partner_slot.unsqueeze(-1)).squeeze(-1) > 0.0
        num_spread_targets_alive = (
            opp_a_alive_now.long()
            + opp_b_alive_now.long()
            + torch.where(is_spread_all, partner_alive_now.long(), torch.zeros_like(opp_a_alive_now.long()))
        )
        # Spread 0.75x multiplier applies only when > 1 target in the spread domain is alive at execution time
        spread_mult_active = is_spread & (num_spread_targets_alive > 1)

        target_passes = (
            (torch.where(is_spread, opp_slot_a, single_tgt), can_act & (target_type_code <= int(TargetType.ALL_ADJACENT)) & (target_type_code != int(TargetType.SELF))),
            (opp_slot_b, can_act & is_spread),
            (partner_slot, can_act & is_spread_all),
        )

        # Track whether the actor connected at least once (for self-stat drops like Close Combat / Make It Rain / Scale Shot)
        actor_connected_any = torch.zeros((B1, B2, K), dtype=torch.bool, device=device)
        user_has_mold_breaker = att_ab == float(AbilityID.MOLD_BREAKER)

        # Compute effective move priority for Quick Guard / Armor Tail / Psychic Terrain checks
        base_move_prio = chosen_move[:, :, :, MoveIdx.PRIORITY]
        eff_move_prio = base_move_prio + torch.where(
            (att_ab == float(AbilityID.PRANKSTER)) & (cat_idx == 2),
            torch.ones_like(base_move_prio),
            torch.where(
                (att_ab == float(AbilityID.GALE_WINGS))
                & (move_type_idx == TYPE_TO_IDX["flying"])
                & (p_actor[:, :, :, MonIdx.HP_CUR] >= p_actor[:, :, :, MonIdx.HP_MAX]),
                torch.ones_like(base_move_prio),
                torch.where(
                    (chosen_move[:, :, :, MoveIdx.GRASSY_PRIO_BOOST] > 0.5)
                    & (tr_idx_now == T_GRASSY)
                    & att_grounded_now,
                    torch.ones_like(base_move_prio),
                    torch.zeros_like(base_move_prio),
                ),
            ),
        )

        # Precompute Sheer Force eligibility for this move
        has_sheer_force_effect = (
            (chosen_move[:, :, :, MoveIdx.SEC_STATUS_CHANCE] > 0.0)
            | (chosen_move[:, :, :, MoveIdx.FLINCH_CHANCE] > 0.0)
            | (
                (chosen_move[:, :, :, MoveIdx.STAT_DELTA_CHANCE] > 0.0)
                & (chosen_move[:, :, :, MoveIdx.STAT_DELTA_SELF] < 0.5)
            )
        )
        sheer_force_active = (att_ab == float(AbilityID.SHEER_FORCE)) & (cat_idx != 2) & has_sheer_force_effect

        for pass_idx, (tgt_slot, pass_mask) in enumerate(target_passes):
            if not torch.any(pass_mask):
                continue

            tgt_exp_mon = tgt_slot.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
            p_tgt = torch.gather(P_mc, 3, tgt_exp_mon).squeeze(3)
            tgt_hp = p_tgt[:, :, :, MonIdx.HP_CUR]
            tgt_alive = tgt_hp > 0.0

            tgt_ab = p_tgt[:, :, :, MonIdx.ABILITY_ID]
            eff_tgt_ab = torch.where(user_has_mold_breaker, torch.zeros_like(tgt_ab), tgt_ab)
            is_foe_target = tgt_slot != partner_slot

            # Protect / Wide Guard / Quick Guard checks (Unseen Fist & Piercing Drill contact moves bypass Protect)
            is_contact_pre = chosen_move[:, :, :, MoveIdx.IS_CONTACT] > 0.5
            bypasses_protect = is_contact_pre & (
                (att_ab == float(AbilityID.UNSEEN_FIST)) | (att_ab == float(AbilityID.PIERCING_DRILL))
            )
            tgt_prot = (p_tgt[:, :, :, MonIdx.PROTECT_ACTIVE] > 0.5) & (~bypasses_protect)
            tgt_wg = is_spread & (p_tgt[:, :, :, MonIdx.WIDE_GUARD_ACTIVE] > 0.5)
            tgt_qg = (eff_move_prio > 0.0) & (p_tgt[:, :, :, MonIdx.QUICK_GUARD_ACTIVE] > 0.5) & is_foe_target
            is_guarded = tgt_prot | tgt_wg | tgt_qg

            valid_target = pass_mask & tgt_alive & (~is_guarded)
            if not torch.any(valid_target):
                continue

            # Telepathy ally-damage immunity (partner is immune to actor's damaging moves)
            is_telepathy_block = (
                (~is_foe_target)
                & (tgt_slot != actor_slot)
                & (cat_idx != 2)
                & (eff_tgt_ab == float(AbilityID.TELEPATHY))
            )
            valid_target = valid_target & (~is_telepathy_block)

            # Armor Tail / Queenly Majesty & Psychic Terrain priority blocking on opposing targets
            grav_on = F_mc[:, :, :, FieldIdx.GRAVITY_TURNS] > 0.0
            tgt_has_levitate = (eff_tgt_ab == float(AbilityID.LEVITATE)) | (eff_tgt_ab == float(AbilityID.EELEVATE))
            tgt_is_flying = (
                (p_tgt[:, :, :, MonIdx.TYPE1_START + TYPE_TO_IDX["flying"]] > 0.5)
                | (p_tgt[:, :, :, MonIdx.TYPE2_START + TYPE_TO_IDX["flying"]] > 0.5)
            )
            tgt_has_balloon = (
                (p_tgt[:, :, :, MonIdx.ITEM_ACTIVE] > 0.5)
                & (p_tgt[:, :, :, MonIdx.ITEM_ID] == float(ItemID.AIR_BALLOON))
            )
            tgt_has_iron_ball = (
                (p_tgt[:, :, :, MonIdx.ITEM_ACTIVE] > 0.5)
                & (p_tgt[:, :, :, MonIdx.ITEM_ID] == float(ItemID.IRON_BALL))
            )
            tgt_grounded = grav_on | tgt_has_iron_ball | ((~tgt_is_flying) & (~tgt_has_levitate) & (~tgt_has_balloon))

            if torch.any((eff_move_prio > 0.0) & is_foe_target):
                opp_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, opp_slot_a.unsqueeze(-1)).squeeze(-1)
                opp_b_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, opp_slot_b.unsqueeze(-1)).squeeze(-1)
                opp_a_ab_now = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, opp_slot_a.unsqueeze(-1)).squeeze(-1)
                opp_b_ab_now = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, opp_slot_b.unsqueeze(-1)).squeeze(-1)
                opp_prio_shield = (~user_has_mold_breaker) & (
                    ((opp_a_hp > 0.0) & ((opp_a_ab_now == float(AbilityID.ARMOR_TAIL)) | (opp_a_ab_now == float(AbilityID.QUEENLY_MAJESTY))))
                    | ((opp_b_hp > 0.0) & ((opp_b_ab_now == float(AbilityID.ARMOR_TAIL)) | (opp_b_ab_now == float(AbilityID.QUEENLY_MAJESTY))))
                )
                psy_prio_block = (F_mc[:, :, :, FieldIdx.TERRAIN_START + T_PSYCHIC] > 0.5) & tgt_grounded
                prio_blocked = (eff_move_prio > 0.0) & is_foe_target & (opp_prio_shield | psy_prio_block)
                valid_target = valid_target & (~prio_blocked)

            # Prankster vs Dark-type foe immunity
            tgt_is_dark = (
                (p_tgt[:, :, :, MonIdx.TYPE1_START + TYPE_TO_IDX["dark"]] > 0.5)
                | (p_tgt[:, :, :, MonIdx.TYPE2_START + TYPE_TO_IDX["dark"]] > 0.5)
            )
            prankster_dark_block = (att_ab == float(AbilityID.PRANKSTER)) & (cat_idx == 2) & is_foe_target & tgt_is_dark
            valid_target = valid_target & (~prankster_dark_block)

            # Soundproof, Bulletproof & Good as Gold immunities
            soundproof_block = (chosen_move[:, :, :, MoveIdx.IS_SOUND_MOVE] > 0.5) & (eff_tgt_ab == float(AbilityID.SOUNDPROOF))
            is_bullet_move = (field_op == int(FieldOpID.FLAG_BULLET)) | (field_op == int(FieldOpID.FLAG_PULSE_BULLET))
            bulletproof_block = is_bullet_move & (eff_tgt_ab == float(AbilityID.BULLETPROOF))
            good_as_gold_block = (cat_idx == 2) & (tgt_slot != actor_slot) & (eff_tgt_ab == float(AbilityID.GOOD_AS_GOLD))
            valid_target = valid_target & (~soundproof_block) & (~bulletproof_block) & (~good_as_gold_block)

            # Sucker Punch / Upper Hand validation (fails if target already acted or chose Status/Switch)
            is_sucker = field_op == int(FieldOpID.SUCKER_PUNCH)
            if torch.any(valid_target & is_sucker):
                tgt_act_idx = torch.clamp(torch.where(tgt_slot < 2, tgt_slot, tgt_slot - 2), min=0, max=3)
                tgt_already_acted = torch.gather(acted_mask_k, 3, tgt_act_idx.unsqueeze(-1)).squeeze(-1)
                tgt_c_val = torch.gather(choices_4, 3, tgt_act_idx.unsqueeze(-1)).squeeze(-1)
                tgt_c_sw = (tgt_c_val == CHOICE_SWITCH_BENCH1) | (tgt_c_val == CHOICE_SWITCH_BENCH2)
                tgt_m_idx = (tgt_c_val % 12) % 4
                tgt_flat_mv = (tgt_slot * MOVES_PER_MON + tgt_m_idx).view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MOVE_DIM)
                if not m_mc_is_cloned:
                    m_flat_base = M_moves.view(B1, B2, 1, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM).expand(
                        B1, B2, K, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM
                    )
                    tgt_mv_vec = torch.gather(m_flat_base, 3, tgt_flat_mv).squeeze(3)
                else:
                    m_flat_mc = M_mc.view(B1, B2, K, ROSTER_SLOTS * MOVES_PER_MON, MOVE_DIM)
                    tgt_mv_vec = torch.gather(m_flat_mc, 3, tgt_flat_mv).squeeze(3)
                tgt_c_status = tgt_mv_vec[:, :, :, MoveIdx.CAT_STATUS] > 0.5
                sucker_fails = is_sucker & (tgt_already_acted | tgt_c_sw | tgt_c_status)
                valid_target = valid_target & (~sucker_fails)

            # Elemental Absorption Abilities (Water Absorb/Dry Skin, Volt Absorb, Earth Eater, Motor Drive, Lightning Rod, Sap Sipper, Flash Fire)
            is_water_abs = (
                valid_target
                & (move_type_idx == TYPE_TO_IDX["water"])
                & ((eff_tgt_ab == float(AbilityID.WATER_ABSORB)) | (eff_tgt_ab == float(AbilityID.DRY_SKIN)))
            )
            is_volt_abs = valid_target & (move_type_idx == TYPE_TO_IDX["electric"]) & (eff_tgt_ab == float(AbilityID.VOLT_ABSORB))
            is_earth_eat = valid_target & (move_type_idx == TYPE_TO_IDX["ground"]) & (eff_tgt_ab == float(AbilityID.EARTH_EATER))
            is_hp_absorb = is_water_abs | is_volt_abs | is_earth_eat
            if torch.any(is_hp_absorb):
                max_t_hp = p_tgt[:, :, :, MonIdx.HP_MAX]
                abs_heal = torch.clamp(torch.floor(max_t_hp * 0.25), min=1.0)
                new_t_hp = torch.clamp(tgt_hp + torch.where(is_hp_absorb, abs_heal, torch.zeros_like(abs_heal)), max=max_t_hp)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, tgt_slot.unsqueeze(-1), new_t_hp.unsqueeze(-1))
                valid_target = valid_target & (~is_hp_absorb)

            is_motor_drive = valid_target & (move_type_idx == TYPE_TO_IDX["electric"]) & (eff_tgt_ab == float(AbilityID.MOTOR_DRIVE))
            if torch.any(is_motor_drive):
                cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_SPE], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                P_mc[:, :, :, :, MonIdx.BOOST_SPE].scatter_(
                    3, tgt_slot.unsqueeze(-1), torch.clamp(cur_b + torch.where(is_motor_drive, torch.ones_like(cur_b), torch.zeros_like(cur_b)), -6.0, 6.0).unsqueeze(-1)
                )
                valid_target = valid_target & (~is_motor_drive)

            is_lrod_absorb = valid_target & (move_type_idx == TYPE_TO_IDX["electric"]) & (eff_tgt_ab == float(AbilityID.LIGHTNING_ROD))
            if torch.any(is_lrod_absorb):
                cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_SPA], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                P_mc[:, :, :, :, MonIdx.BOOST_SPA].scatter_(
                    3, tgt_slot.unsqueeze(-1), torch.clamp(cur_b + torch.where(is_lrod_absorb, torch.ones_like(cur_b), torch.zeros_like(cur_b)), -6.0, 6.0).unsqueeze(-1)
                )
                valid_target = valid_target & (~is_lrod_absorb)

            is_sap_sipper = valid_target & (move_type_idx == TYPE_TO_IDX["grass"]) & (eff_tgt_ab == float(AbilityID.SAP_SIPPER))
            if torch.any(is_sap_sipper):
                cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_ATK], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                P_mc[:, :, :, :, MonIdx.BOOST_ATK].scatter_(
                    3, tgt_slot.unsqueeze(-1), torch.clamp(cur_b + torch.where(is_sap_sipper, torch.ones_like(cur_b), torch.zeros_like(cur_b)), -6.0, 6.0).unsqueeze(-1)
                )
                valid_target = valid_target & (~is_sap_sipper)

            is_flash_fire = valid_target & (move_type_idx == TYPE_TO_IDX["fire"]) & (eff_tgt_ab == float(AbilityID.FLASH_FIRE))
            valid_target = valid_target & (~is_flash_fire)

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
                & (chosen_move[:, :, :, MoveIdx.IS_SOUND_MOVE] < 0.5)
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
            # Official cartridge rule: Thunder & Hurricane (w_sure == 2.0) drop to 50% accuracy in Sun
            # (suppressed if Cloud Nine is active, since w_idx == W_CLEAR under Cloud Nine).
            raw_acc = torch.where(
                (w_sure == 2.0) & (w_idx_actor == W_SUN),
                torch.full_like(raw_acc, 0.50),
                raw_acc,
            )
            sure_hit = (
                (raw_acc >= 1.005)
                | (att_ab == float(AbilityID.NO_GUARD))
                | (tgt_ab == float(AbilityID.NO_GUARD))
                | ((w_sure == 2.0) & (w_idx_actor == W_RAIN))
                | ((w_sure == 4.0) & (w_idx_actor == W_SNOW))
            )
            acc_eva_stage = torch.clamp(
                p_actor[:, :, :, MonIdx.BOOST_ACC] - p_tgt[:, :, :, MonIdx.BOOST_EVA], min=-6.0, max=6.0
            )
            acc_mult = _acc_stage_ratio_torch(acc_eva_stage)
            acc_mult = torch.where(att_ab == float(AbilityID.COMPOUND_EYES), acc_mult * 1.3, acc_mult)
            acc_mult = torch.where(act_item_active & (act_item == float(ItemID.WIDE_LENS)), acc_mult * 1.1, acc_mult)
            acc_mult = torch.where(grav_on, acc_mult * (5.0 / 3.0), acc_mult)
            # Weather Evasion Abilities (Sand Veil / Snow Cloak 0.8x) & Bright Powder (0.9x)
            weather_evade = (
                ((eff_tgt_ab == float(AbilityID.SAND_VEIL)) & (w_idx == W_SAND))
                | ((eff_tgt_ab == float(AbilityID.SNOW_CLOAK)) & (w_idx == W_SNOW))
            )
            acc_mult = torch.where(weather_evade, acc_mult * 0.8, acc_mult)
            tgt_bright_powder = (
                (p_tgt[:, :, :, MonIdx.ITEM_ACTIVE] > 0.5)
                & (p_tgt[:, :, :, MonIdx.ITEM_ID] == float(ItemID.BRIGHT_POWDER))
            )
            acc_mult = torch.where(tgt_bright_powder, acc_mult * 0.9, acc_mult)

            eff_acc_pct = torch.where(
                sure_hit,
                torch.full_like(raw_acc, 100.0),
                torch.clamp(raw_acc * 100.0 * acc_mult, min=0.0, max=100.0),
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
                is_sleep_status = chosen_move[:, :, :, MoveIdx.SEC_STATUS_START + STATUS_TO_IDX["sleep"]] > 0.5
                elec_or_misty = (F_mc[:, :, :, FieldIdx.TERRAIN_START + T_ELECTRIC] > 0.5) | (
                    F_mc[:, :, :, FieldIdx.TERRAIN_START + T_MISTY] > 0.5
                )
                terrain_blocks_status = tgt_grounded & (
                    (is_sleep_status & elec_or_misty)
                    | (F_mc[:, :, :, FieldIdx.TERRAIN_START + T_MISTY] > 0.5)
                )
                leaf_guard_blocks = (eff_tgt_ab == float(AbilityID.LEAF_GUARD)) & (w_idx == W_SUN)
                is_burn_inflict = chosen_move[:, :, :, MoveIdx.SEC_STATUS_START + STATUS_TO_IDX["burn"]] > 0.5
                thermal_ex_burn_block = is_burn_inflict & (eff_tgt_ab == float(AbilityID.THERMAL_EXCHANGE))
                st_lands = (
                    status_hits
                    & tgt_healthy
                    & (~terrain_blocks_status)
                    & (~leaf_guard_blocks)
                    & (~thermal_ex_burn_block)
                    & spin_wheel_gate(
                        sec_chance_pct, seed=seed, event_id=int(RNGEventID.SECONDARY_STATUS), step_idx=step_idx * 4 + pass_idx
                    )
                )
                if torch.any(st_lands):
                    for st_i in range(7):
                        new_st_bit = chosen_move[:, :, :, MoveIdx.SEC_STATUS_START + st_i]
                        cur_st_bit = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_START + st_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.STATUS_START + st_i].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.where(st_lands, new_st_bit, cur_st_bit).unsqueeze(-1)
                        )
                    tgt_unnerved = _is_side_unnerved_torch(P_mc, tgt_slot) if flags.has_unnerve else None
                    if flags.has_chesto_berry:
                        _check_chesto_berry_and_unburden_torch(P_mc, tgt_slot, blocked_mask=tgt_unnerved)
                    if flags.has_lum_berry:
                        _check_lum_berry_and_unburden_torch(P_mc, tgt_slot, blocked_mask=tgt_unnerved)

                # Volatile Disruption Status Moves: Encore, Disable, Leech Seed, Yawn
                m_encore = status_hits & (field_op == int(FieldOpID.ENCORE)) & (p_tgt[:, :, :, MonIdx.LAST_MOVE_IDX] >= 0.0)
                if torch.any(m_encore):
                    cur_enc = torch.gather(P_mc[:, :, :, :, MonIdx.ENCORE_TURNS], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                    P_mc[:, :, :, :, MonIdx.ENCORE_TURNS].scatter_(
                        3, tgt_slot.unsqueeze(-1), torch.where(m_encore, torch.full_like(cur_enc, 3.0), cur_enc).unsqueeze(-1)
                    )
                    if flags.has_mental_herb:
                        _check_mental_herb_and_unburden_torch(P_mc, tgt_slot)

                m_disable = status_hits & (field_op == int(FieldOpID.DISABLE)) & (p_tgt[:, :, :, MonIdx.LAST_MOVE_IDX] >= 0.0)
                if torch.any(m_disable):
                    dis_buf = _get_ev("disabled")
                    cur_dis = torch.gather(dis_buf, 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                    dis_buf.scatter_(
                        3, tgt_slot.unsqueeze(-1), torch.where(m_disable, torch.ones_like(cur_dis), cur_dis).unsqueeze(-1)
                    )

                tgt_is_grass = (
                    (p_tgt[:, :, :, MonIdx.TYPE1_START + TYPE_TO_IDX["grass"]] > 0.5)
                    | (p_tgt[:, :, :, MonIdx.TYPE2_START + TYPE_TO_IDX["grass"]] > 0.5)
                )
                m_lseed = status_hits & (field_op == int(FieldOpID.LEECH_SEED)) & (~tgt_is_grass)
                if torch.any(m_lseed):
                    ls_buf = _get_ev("leech_seed_src")
                    cur_ls = torch.gather(ls_buf, 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                    ls_buf.scatter_(
                        3,
                        tgt_slot.unsqueeze(-1),
                        torch.where(m_lseed & (cur_ls <= 0.0), (actor_slot + 1).float(), cur_ls).unsqueeze(-1),
                    )

                m_yawn = status_hits & (field_op == int(FieldOpID.YAWN)) & tgt_healthy & (~(tgt_grounded & elec_or_misty)) & (~leaf_guard_blocks)
                if torch.any(m_yawn):
                    yw_buf = _get_ev("yawned")
                    cur_yw = torch.gather(yw_buf, 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                    yw_buf.scatter_(
                        3, tgt_slot.unsqueeze(-1), torch.where(m_yawn, torch.ones_like(cur_yw), cur_yw).unsqueeze(-1)
                    )

                # Target stat stage changes on status moves (Parting Shot, Charm, Scary Face, Fake Tears, Coaching)
                tgt_stat_op = status_hits & (~stat_self_flag) & (stat_chance_pct > 0.0)
                if torch.any(tgt_stat_op):
                    tgt_drop_immune = is_foe_target & (
                        (eff_tgt_ab == float(AbilityID.CLEAR_BODY))
                        | (eff_tgt_ab == float(AbilityID.MIRROR_ARMOR))
                        | (
                            (eff_tgt_ab == float(AbilityID.FLOWER_VEIL))
                            & (
                                (p_tgt[:, :, :, MonIdx.TYPE1_START + TYPE_TO_IDX["grass"]] > 0.5)
                                | (p_tgt[:, :, :, MonIdx.TYPE2_START + TYPE_TO_IDX["grass"]] > 0.5)
                            )
                        )
                    )
                    stat_lands = tgt_stat_op & (~tgt_drop_immune) & spin_wheel_gate(
                        stat_chance_pct, seed=seed, event_id=int(RNGEventID.STAT_STAGE_PROC), step_idx=step_idx * 4 + pass_idx
                    )
                    if torch.any(stat_lands):
                        any_drop = torch.zeros_like(stat_lands)
                        tgt_is_contrary = tgt_ab == float(AbilityID.CONTRARY)
                        for s_i in range(7):
                            delta_v = chosen_move[:, :, :, MoveIdx.STAT_DELTA_START + s_i]
                            if torch.any(stat_lands & (delta_v != 0.0)):
                                eff_dv = torch.where(tgt_is_contrary, -delta_v, delta_v)
                                if s_i == 0:
                                    hc_blocks = is_foe_target & (eff_dv < 0.0) & (eff_tgt_ab == float(AbilityID.HYPER_CUTTER))
                                    eff_dv = torch.where(hc_blocks, torch.zeros_like(eff_dv), eff_dv)
                                cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                                any_drop = any_drop | (stat_lands & is_foe_target & (eff_dv < 0.0) & (cur_b > -6.0))
                                new_b = torch.clamp(cur_b + torch.where(stat_lands, eff_dv, torch.zeros_like(eff_dv)), min=-6.0, max=6.0)
                                P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(3, tgt_slot.unsqueeze(-1), new_b.unsqueeze(-1))
                        # Defiant / Competitive / White Herb on target
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
                            if flags.has_white_herb:
                                _check_white_herb_and_unburden_torch(P_mc, tgt_slot)

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

            # Ground immunity on ungrounded targets (unless Gravity is active or Mold Breaker ignores Levitate)
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
            has_slink = (att_ab == float(AbilityID.SKILL_LINK)).float()
            hit_counts = spin_wheel_multihit_count(
                exp_hits_code, has_slink, seed=seed, step_idx=step_idx * 4 + pass_idx
            )
            # Parental Bond: single-target single-hit damaging moves strike twice (2nd hit at 0.25x damage)
            is_parental_bond = (
                (att_ab == float(AbilityID.PARENTAL_BOND))
                & (~is_spread)
                & (hit_counts == 1)
                & (~is_explosion_move)
            )
            hit_counts = torch.where(is_parental_bond, torch.full_like(hit_counts, 2), hit_counts)
            max_hits = int(torch.max(torch.where(dmg_move_hits, hit_counts, torch.ones_like(hit_counts))).item())

            # Offensive & Defensive Stat Overrides (Body Press, Foul Play, Psyshock/Psystrike/Secret Sword)
            off_ovr = torch.round(chosen_move[:, :, :, MoveIdx.OVERRIDE_OFF_STAT]).long()
            def_ovr = torch.round(chosen_move[:, :, :, MoveIdx.OVERRIDE_DEF_STAT]).long()
            is_phys = cat_idx == 0
            is_contact_move = chosen_move[:, :, :, MoveIdx.IS_CONTACT] > 0.5
            is_slicing_move = chosen_move[:, :, :, MoveIdx.IS_SLICING] > 0.5
            is_punch_move = chosen_move[:, :, :, MoveIdx.IS_PUNCH] > 0.5

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
            weather_mult = w_chart[w_idx_actor, move_type_idx]
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

            # Fairy Aura field check (1.33x to Fairy moves while any alive active mon has Fairy Aura)
            if flags.has_fairy_aura:
                ab_act_fa = P_mc[:, :, :, act_slots_idx, MonIdx.ABILITY_ID]
                hp_act_fa = P_mc[:, :, :, act_slots_idx, MonIdx.HP_CUR]
                fairy_aura_on = torch.any((hp_act_fa > 0.0) & (ab_act_fa == float(AbilityID.FAIRY_AURA)), dim=-1)
            else:
                fairy_aura_on = torch.zeros_like(dmg_move_hits)

            # Friend Guard check on target's alive ally partner (0.75x damage taken, bypassed by Mold Breaker)
            tgt_is_t1 = tgt_slot < 4
            tgt_ally_slot = torch.where(
                tgt_is_t1,
                torch.where(tgt_slot == SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_1_A),
                torch.where(tgt_slot == SLOT_TRAINER_2_A, SLOT_TRAINER_2_B, SLOT_TRAINER_2_A),
            )
            tgt_ally_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, tgt_ally_slot.unsqueeze(-1)).squeeze(-1)
            tgt_ally_ab = torch.gather(P_mc[:, :, :, :, MonIdx.ABILITY_ID], 3, tgt_ally_slot.unsqueeze(-1)).squeeze(-1)
            friend_guard_active = (~user_has_mold_breaker) & (tgt_ally_hp > 0.0) & (tgt_ally_ab == float(AbilityID.FRIEND_GUARD))

            # Crit stage calculation (base move stage + Scope Lens (+1) + Leek (+2))
            crit_stage = (
                chosen_move[:, :, :, MoveIdx.CRIT_STAGE]
                + torch.where(act_item_active & (act_item == float(ItemID.SCOPE_LENS)), torch.ones_like(base_power), torch.zeros_like(base_power))
                + torch.where(act_item_active & (act_item == float(ItemID.LEEK)), torch.full_like(base_power, 2.0), torch.zeros_like(base_power))
            )

            # Screens on defending side (0.667x in Doubles, bypassed on crits)
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
                cur_a_hp_hit = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                hit_active = dmg_move_hits & (hit_counts > hit_idx) & (cur_t_hp > 0.0) & (cur_a_hp_hit > 0.0)
                if not torch.any(hit_active):
                    break

                # 1. Critical Hit Spinning-Wheel per hit (blocked by Shell Armor / Battle Armor)
                can_crit_target = eff_tgt_ab != float(AbilityID.SHELL_ARMOR)
                is_crit = hit_active & can_crit_target & spin_wheel_crit_gate(
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

                # Official Weather Stat Buffs (suppressed automatically by Cloud Nine via w_idx == W_CLEAR;
                # apply even on Critical Hits and against Mold Breaker):
                # 1. Sandstorm: Rock-type defenders gain 1.5x SpD against attacks targeting SpD.
                # 2. Snow: Ice-type defenders gain 1.5x Def against attacks targeting Def (Physical & Psyshock),
                #    and Ice-type attackers gain 1.5x Def when using Body Press (OverrideOffStat.USER_DEF).
                uses_def_stat = is_phys | (def_ovr == int(OverrideDefStat.TARGET_DEF))
                tgt_is_rock = (
                    (p_tgt[:, :, :, MonIdx.TYPE1_START + TYPE_TO_IDX["rock"]] > 0.5)
                    | (p_tgt[:, :, :, MonIdx.TYPE2_START + TYPE_TO_IDX["rock"]] > 0.5)
                )
                tgt_is_ice = (
                    (p_tgt[:, :, :, MonIdx.TYPE1_START + TYPE_TO_IDX["ice"]] > 0.5)
                    | (p_tgt[:, :, :, MonIdx.TYPE2_START + TYPE_TO_IDX["ice"]] > 0.5)
                )
                att_is_ice = (att_t1 == TYPE_TO_IDX["ice"]) | (att_has_t2 & (att_t2 == TYPE_TO_IDX["ice"]))
                D = torch.where((~uses_def_stat) & (w_idx == W_SAND) & tgt_is_rock, torch.floor(D * 1.5), D)
                D = torch.where(uses_def_stat & (w_idx == W_SNOW) & tgt_is_ice, torch.floor(D * 1.5), D)
                A = torch.where(
                    (off_ovr == int(OverrideOffStat.USER_DEF)) & (w_idx == W_SNOW) & att_is_ice,
                    torch.floor(A * 1.5),
                    A,
                )

                # Thick Fat (halves attacker's effective Attack/SpA on Fire and Ice moves)
                is_thick_fat = (eff_tgt_ab == float(AbilityID.THICK_FAT)) & (
                    (move_type_idx == TYPE_TO_IDX["fire"]) | (move_type_idx == TYPE_TO_IDX["ice"])
                )
                A = torch.where(is_thick_fat, torch.floor(A * 0.5), A)

                # Ability & Item modifiers on A and D
                A = torch.where(is_phys & (att_ab == float(AbilityID.HUGE_POWER)), A * 2.0, A)
                A = torch.where(
                    is_phys & (att_ab == float(AbilityID.GUTS)) & (p_actor[:, :, :, MonIdx.STATUS_HEALTHY] < 0.5),
                    A * 1.5,
                    A,
                )
                A = torch.where(
                    (~is_phys) & (att_ab == float(AbilityID.SOLAR_POWER)) & (w_idx == W_SUN),
                    torch.floor(A * 1.5),
                    A,
                )
                # Pinch starter abilities (Blaze, Torrent, Overgrow, Swarm: 1.5x at <= 1/3 HP)
                in_pinch = p_actor[:, :, :, MonIdx.HP_CUR] <= torch.floor(p_actor[:, :, :, MonIdx.HP_MAX] / 3.0)
                pinch_boost = in_pinch & (
                    ((att_ab == float(AbilityID.BLAZE)) & (move_type_idx == TYPE_TO_IDX["fire"]))
                    | ((att_ab == float(AbilityID.TORRENT)) & (move_type_idx == TYPE_TO_IDX["water"]))
                    | ((att_ab == float(AbilityID.OVERGROW)) & (move_type_idx == TYPE_TO_IDX["grass"]))
                    | ((att_ab == float(AbilityID.SWARM)) & (move_type_idx == TYPE_TO_IDX["bug"]))
                )
                A = torch.where(pinch_boost, torch.floor(A * 1.5), A)
                # Fire Mane (Pyroar-Mega: 1.5x Atk/SpA on Fire moves)
                A = torch.where(
                    (att_ab == float(AbilityID.FIRE_MANE)) & (move_type_idx == TYPE_TO_IDX["fire"]),
                    torch.floor(A * 1.5),
                    A,
                )

                # Base Level 50 Damage (Technician 1.5x, Sheer Force 1.3x, Tough Claws 1.3x, Sharpness 1.5x,
                # Iron Fist 1.2x, Mega Launcher 1.5x, Strong Jaw 1.5x, Fairy Aura 1.33x)
                bp_eff = torch.where(
                    (att_ab == float(AbilityID.TECHNICIAN)) & (base_power <= 60.0),
                    torch.floor(base_power * 1.5),
                    base_power,
                )
                bp_eff = torch.where(sheer_force_active, torch.floor(bp_eff * 5325.0 / 4096.0), bp_eff)
                bp_eff = torch.where(
                    (att_ab == float(AbilityID.TOUGH_CLAWS)) & is_contact_move,
                    torch.floor(bp_eff * 5325.0 / 4096.0),
                    bp_eff,
                )
                bp_eff = torch.where(
                    (att_ab == float(AbilityID.SHARPNESS)) & is_slicing_move,
                    torch.floor(bp_eff * 6144.0 / 4096.0),
                    bp_eff,
                )
                bp_eff = torch.where(
                    (att_ab == float(AbilityID.IRON_FIST)) & is_punch_move,
                    torch.floor(bp_eff * 4915.0 / 4096.0),
                    bp_eff,
                )
                is_pulse_move = (field_op == int(FieldOpID.FLAG_PULSE)) | (field_op == int(FieldOpID.FLAG_PULSE_BULLET))
                bp_eff = torch.where(
                    (att_ab == float(AbilityID.MEGA_LAUNCHER)) & is_pulse_move,
                    torch.floor(bp_eff * 6144.0 / 4096.0),
                    bp_eff,
                )
                is_bite_move = field_op == int(FieldOpID.FLAG_BITE)
                bp_eff = torch.where(
                    (att_ab == float(AbilityID.STRONG_JAW)) & is_bite_move,
                    torch.floor(bp_eff * 6144.0 / 4096.0),
                    bp_eff,
                )
                bp_eff = torch.where(
                    act_item_active & is_phys & (act_item == float(ItemID.MUSCLE_BAND)),
                    torch.floor(bp_eff * 4505.0 / 4096.0),
                    bp_eff,
                )
                bp_eff = torch.where(
                    act_item_active & (~is_phys) & (act_item == float(ItemID.WISE_GLASSES)),
                    torch.floor(bp_eff * 4505.0 / 4096.0),
                    bp_eff,
                )
                bp_eff = torch.where(
                    fairy_aura_on & (move_type_idx == TYPE_TO_IDX["fairy"]),
                    torch.floor(bp_eff * 5448.0 / 4096.0),
                    bp_eff,
                )
                # Sand Force (1.3x BP on Rock, Ground, and Steel moves during active Sandstorm)
                is_sand_force_move = (
                    (att_ab == float(AbilityID.SAND_FORCE))
                    & (w_idx == W_SAND)
                    & (
                        (move_type_idx == TYPE_TO_IDX["rock"])
                        | (move_type_idx == TYPE_TO_IDX["ground"])
                        | (move_type_idx == TYPE_TO_IDX["steel"])
                    )
                )
                bp_eff = torch.where(is_sand_force_move, torch.floor(bp_eff * 5325.0 / 4096.0), bp_eff)
                bp_eff = torch.floor(bp_eff * hh_mult)
                base_calc = torch.floor((22.0 * bp_eff * (A / D)) / 50.0) + 2.0

                # Spread (0.75x only when > 1 target in spread domain is alive)
                base_calc = torch.where(spread_mult_active, torch.floor(base_calc * 0.75), base_calc)
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

                # Screens (2732/4096 ~ 0.667x in Doubles, bypassed on crit or Infiltrator)
                base_calc = torch.where(
                    screen_active & (~is_crit) & (att_ab != float(AbilityID.INFILTRATOR)),
                    torch.floor(base_calc * 2732.0 / 4096.0),
                    base_calc,
                )

                # Friend Guard (0.75x damage taken from any attack when ally has Friend Guard)
                base_calc = torch.where(
                    friend_guard_active,
                    torch.floor(base_calc * 3072.0 / 4096.0),
                    base_calc,
                )

                # Multiscale (0.5x at full HP), Solid Rock / Filter (0.75x on Super Effective),
                # Aura Guard (0.5x on incoming contact moves), Dry Skin (1.25x from Fire)
                base_calc = torch.where(
                    (eff_tgt_ab == float(AbilityID.MULTISCALE)) & (cur_t_hp >= max_t_hp),
                    torch.floor(base_calc * 0.5),
                    base_calc,
                )
                base_calc = torch.where(
                    (eff_tgt_ab == float(AbilityID.SOLID_ROCK)) & (type_eff > 1.0),
                    torch.floor(base_calc * 0.75),
                    base_calc,
                )
                base_calc = torch.where(
                    (eff_tgt_ab == float(AbilityID.AURA_GUARD)) & is_contact_move,
                    torch.floor(base_calc * 0.5),
                    base_calc,
                )
                base_calc = torch.where(
                    (eff_tgt_ab == float(AbilityID.DRY_SKIN)) & (move_type_idx == TYPE_TO_IDX["fire"]),
                    torch.floor(base_calc * 5120.0 / 4096.0),
                    base_calc,
                )
                # Parental Bond second hit deals 0.25x damage
                if hit_idx == 1:
                    base_calc = torch.where(is_parental_bond, torch.floor(base_calc * 0.25), base_calc)

                # Type-Boosting Item (1.2x on matching item boost type), Expert Belt (1.2x on Super Effective), Life Orb (5324/4096 ~ 1.3x)
                item_boost_type = torch.round(p_actor[:, :, :, MonIdx.ITEM_BOOST_TYPE]).long()
                is_tb_item = (
                    act_item_active
                    & (act_item == float(ItemID.TYPE_BOOST_ITEM))
                    & (item_boost_type == move_type_idx)
                )
                base_calc = torch.where(is_tb_item, torch.floor(base_calc * 4915.0 / 4096.0), base_calc)
                is_ebelt = act_item_active & (act_item == float(ItemID.EXPERT_BELT)) & (type_eff > 1.0)
                base_calc = torch.where(is_ebelt, torch.floor(base_calc * 4915.0 / 4096.0), base_calc)
                if flags.has_life_orb:
                    is_lo = act_item_active & (act_item == float(ItemID.LIFE_ORB))
                    base_calc = torch.where(is_lo, torch.floor(base_calc * 5324.0 / 4096.0), base_calc)

                # Type-Resist Berries (0.5x on matching super-effective hit or Chilan Berry on Normal)
                cur_t_item_act = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE], 3, tgt_slot.unsqueeze(-1)).squeeze(-1) > 0.5
                cur_t_item = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                if flags.has_resist_berry:
                    cur_t_item_idx = torch.clamp(torch.round(cur_t_item).long(), min=0, max=63)
                    berry_matched_type = berry_lut[cur_t_item_idx]
                    rb_unnerved = _is_side_unnerved_torch(P_mc, tgt_slot) if flags.has_unnerve else None
                    resist_berry_triggers = (
                        hit_active
                        & cur_t_item_act
                        & (berry_matched_type >= 0)
                        & (berry_matched_type == move_type_idx)
                        & ((type_eff > 1.0) | (move_type_idx == TYPE_TO_IDX["normal"]))
                    )
                    if rb_unnerved is not None:
                        resist_berry_triggers = resist_berry_triggers & (~rb_unnerved)
                    base_calc = torch.where(resist_berry_triggers, torch.floor(base_calc * 0.5), base_calc)
                    if torch.any(resist_berry_triggers):
                        P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
                            3,
                            tgt_slot.unsqueeze(-1),
                            torch.where(resist_berry_triggers, torch.zeros_like(cur_t_hp), cur_t_item_act.float()).unsqueeze(-1),
                        )
                        cur_t_item_act = cur_t_item_act & (~resist_berry_triggers)
                        is_rb_unb = resist_berry_triggers & (tgt_ab == float(AbilityID.UNBURDEN))
                        if torch.any(is_rb_unb):
                            cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                            P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
                                3, tgt_slot.unsqueeze(-1), torch.where(is_rb_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1)
                            )

                dmg_hit = torch.clamp(base_calc, min=1.0)

                # Focus Sash & Sturdy 1-HP Clamp (consumes Focus Sash so Hit 2+ KOs!)
                sash_triggers = (
                    hit_active
                    & (cur_t_hp >= max_t_hp)
                    & (dmg_hit >= cur_t_hp)
                    & cur_t_item_act
                    & (cur_t_item == float(ItemID.FOCUS_SASH))
                )
                sturdy_triggers = (
                    hit_active
                    & (cur_t_hp >= max_t_hp)
                    & (dmg_hit >= cur_t_hp)
                    & (eff_tgt_ab == float(AbilityID.STURDY))
                )

                applied_dmg = torch.where(sash_triggers | sturdy_triggers, cur_t_hp - 1.0, dmg_hit)
                applied_dmg = torch.where(hit_active, applied_dmg, torch.zeros_like(applied_dmg))

                if flags.has_focus_sash and torch.any(sash_triggers):
                    P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
                        3,
                        tgt_slot.unsqueeze(-1),
                        torch.where(sash_triggers, torch.zeros_like(cur_t_hp), cur_t_item_act.float()).unsqueeze(-1),
                    )
                    cur_t_item_act = cur_t_item_act & (~sash_triggers)
                    is_sash_unb = sash_triggers & (tgt_ab == float(AbilityID.UNBURDEN))
                    if torch.any(is_sash_unb):
                        cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.where(is_sash_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1)
                        )

                # Air Balloon pops upon taking damaging hit
                if flags.has_air_balloon:
                    balloon_pops = hit_active & (applied_dmg > 0.0) & cur_t_item_act & (cur_t_item == float(ItemID.AIR_BALLOON))
                    if torch.any(balloon_pops):
                        P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
                            3,
                            tgt_slot.unsqueeze(-1),
                            torch.where(balloon_pops, torch.zeros_like(cur_t_hp), cur_t_item_act.float()).unsqueeze(-1),
                        )
                        cur_t_item_act = cur_t_item_act & (~balloon_pops)
                        now_grounded = (~tgt_is_flying) & (tgt_ab != float(AbilityID.LEVITATE)) & (tgt_ab != float(AbilityID.EELEVATE))
                        cur_gr = torch.gather(P_mc[:, :, :, :, MonIdx.GROUNDED_FLAG], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.GROUNDED_FLAG].scatter_(
                            3,
                            tgt_slot.unsqueeze(-1),
                            torch.where(balloon_pops & now_grounded, torch.ones_like(cur_gr), cur_gr).unsqueeze(-1),
                        )
                        is_bal_unb = balloon_pops & (tgt_ab == float(AbilityID.UNBURDEN))
                        if torch.any(is_bal_unb):
                            cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                            P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
                                3, tgt_slot.unsqueeze(-1), torch.where(is_bal_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1)
                            )

                new_t_hp = torch.clamp(cur_t_hp - applied_dmg, min=0.0)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, tgt_slot.unsqueeze(-1), new_t_hp.unsqueeze(-1))
                P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, tgt_slot.unsqueeze(-1), (new_t_hp > 0.0).float().unsqueeze(-1))

                total_dmg_this_target = total_dmg_this_target + applied_dmg

                # Contact Punish (Rough Skin 1/8 max HP, Rocky Helmet 1/6 max HP, Flame Body 30% burn)
                if flags.has_contact_punish:
                    contact_hit = hit_active & (applied_dmg > 0.0) & is_contact_move
                    if torch.any(contact_hit):
                        cur_a_hp_c = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                        max_a_hp_c = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                        rs_hit = contact_hit & (tgt_ab == float(AbilityID.ROUGH_SKIN))
                        rh_hit = contact_hit & cur_t_item_act & (cur_t_item == float(ItemID.ROCKY_HELMET))
                        rs_dmg = torch.where(rs_hit, torch.clamp(torch.floor(max_a_hp_c / 8.0), min=1.0), torch.zeros_like(cur_a_hp_c))
                        rh_dmg = torch.where(rh_hit, torch.clamp(torch.floor(max_a_hp_c / 6.0), min=1.0), torch.zeros_like(cur_a_hp_c))
                        if torch.any(rs_hit | rh_hit):
                            new_a_hp_c = torch.clamp(cur_a_hp_c - rs_dmg - rh_dmg, min=0.0)
                            P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), new_a_hp_c.unsqueeze(-1))
                            P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, actor_slot.unsqueeze(-1), (new_a_hp_c > 0.0).float().unsqueeze(-1))

                        fb_cand = (
                            contact_hit
                            & (tgt_ab == float(AbilityID.FLAME_BODY))
                            & (torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1) > 0.0)
                            & (torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, actor_slot.unsqueeze(-1)).squeeze(-1) > 0.5)
                            & (att_t1 != TYPE_TO_IDX["fire"])
                            & (~(att_has_t2 & (att_t2 == TYPE_TO_IDX["fire"])))
                            & (att_ab != float(AbilityID.THERMAL_EXCHANGE))
                            & (~((att_ab == float(AbilityID.LEAF_GUARD)) & (w_idx == W_SUN)))
                        )
                        if torch.any(fb_cand):
                            fb_burns = fb_cand & spin_wheel_gate(
                                torch.full_like(cur_a_hp_c, 30.0),
                                seed=seed,
                                event_id=int(RNGEventID.SECONDARY_STATUS),
                                step_idx=step_idx * 4 + pass_idx,
                                hit_idx=hit_idx + 16,
                            )
                            if torch.any(fb_burns):
                                P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY].scatter_(
                                    3,
                                    actor_slot.unsqueeze(-1),
                                    torch.where(fb_burns, torch.zeros_like(cur_a_hp_c), torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, actor_slot.unsqueeze(-1)).squeeze(-1)).unsqueeze(-1),
                                )
                                P_mc[:, :, :, :, MonIdx.STATUS_BURN].scatter_(
                                    3,
                                    actor_slot.unsqueeze(-1),
                                    torch.where(fb_burns, torch.ones_like(cur_a_hp_c), torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_BURN], 3, actor_slot.unsqueeze(-1)).squeeze(-1)).unsqueeze(-1),
                                )
                                if flags.has_lum_berry:
                                    att_unv_fb = _is_side_unnerved_torch(P_mc, actor_slot) if flags.has_unnerve else None
                                    _check_lum_berry_and_unburden_torch(P_mc, actor_slot, blocked_mask=att_unv_fb)

                # Poison Touch (30% chance to poison target on contact hit)
                if flags.has_poison_touch:
                    pt_cand = (
                        hit_active
                        & (applied_dmg > 0.0)
                        & is_contact_move
                        & (att_ab == float(AbilityID.POISON_TOUCH))
                        & (new_t_hp > 0.0)
                        & (torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, tgt_slot.unsqueeze(-1)).squeeze(-1) > 0.5)
                        & (t1_idx != TYPE_TO_IDX["poison"])
                        & (t1_idx != TYPE_TO_IDX["steel"])
                        & (~(has_t2 & ((t2_idx == TYPE_TO_IDX["poison"]) | (t2_idx == TYPE_TO_IDX["steel"]))))
                        & (eff_tgt_ab != float(AbilityID.SHIELD_DUST))
                        & (~((eff_tgt_ab == float(AbilityID.LEAF_GUARD)) & (w_idx == W_SUN)))
                    )
                    if torch.any(pt_cand):
                        pt_procs = pt_cand & spin_wheel_gate(
                            torch.full_like(new_t_hp, 30.0),
                            seed=seed,
                            event_id=int(RNGEventID.SECONDARY_STATUS),
                            step_idx=step_idx * 4 + pass_idx,
                            hit_idx=hit_idx + 32,
                        )
                        if torch.any(pt_procs):
                            P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY].scatter_(
                                3,
                                tgt_slot.unsqueeze(-1),
                                torch.where(pt_procs, torch.zeros_like(new_t_hp), torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)).unsqueeze(-1),
                            )
                            P_mc[:, :, :, :, MonIdx.STATUS_POISON].scatter_(
                                3,
                                tgt_slot.unsqueeze(-1),
                                torch.where(pt_procs, torch.ones_like(new_t_hp), torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_POISON], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)).unsqueeze(-1),
                            )
                            if flags.has_lum_berry:
                                tgt_unv_pt = _is_side_unnerved_torch(P_mc, tgt_slot) if flags.has_unnerve else None
                                _check_lum_berry_and_unburden_torch(P_mc, tgt_slot, blocked_mask=tgt_unv_pt)

                # Stamina (+1 Def per hit taken when surviving, or -1 Def if Contrary)
                if flags.has_stamina:
                    is_stamina_hit = hit_active & (applied_dmg > 0.0) & (new_t_hp > 0.0) & (tgt_ab == float(AbilityID.STAMINA))
                    if torch.any(is_stamina_hit):
                        cur_def_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_DEF], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.BOOST_DEF].scatter_(
                            3,
                            tgt_slot.unsqueeze(-1),
                            torch.clamp(cur_def_b + torch.where(is_stamina_hit, torch.ones_like(cur_def_b), torch.zeros_like(cur_def_b)), -6.0, 6.0).unsqueeze(-1),
                        )
                        raw_def_stage = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_DEF], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)

                # Sitrus Berry check on target after hit (suppressed by Unnerve)
                if flags.has_sitrus_berry:
                    tgt_unv_hit = _is_side_unnerved_torch(P_mc, tgt_slot) if flags.has_unnerve else None
                    _check_sitrus_berry_and_unburden_torch(P_mc, tgt_slot, blocked_mask=tgt_unv_hit)

                # Justified (+1 Atk per Dark-type damaging hit on surviving defender, foe or ally Beat Up)
                if flags.has_justified:
                    is_justified_hit = (
                        hit_active
                        & (applied_dmg > 0.0)
                        & (move_type_idx == TYPE_TO_IDX["dark"])
                        & (tgt_ab == float(AbilityID.JUSTIFIED))
                        & (new_t_hp > 0.0)
                    )
                    if torch.any(is_justified_hit):
                        cur_ja = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_ATK], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.BOOST_ATK].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.clamp(cur_ja + torch.where(is_justified_hit, torch.ones_like(cur_ja), torch.zeros_like(cur_ja)), -6.0, 6.0).unsqueeze(-1)
                        )

                # Thermal Exchange (+1 Atk when hit by a Fire-type damaging move and survives)
                if flags.has_thermal_exchange:
                    is_te_hit = (
                        hit_active
                        & (applied_dmg > 0.0)
                        & (move_type_idx == TYPE_TO_IDX["fire"])
                        & (tgt_ab == float(AbilityID.THERMAL_EXCHANGE))
                        & (new_t_hp > 0.0)
                    )
                    if torch.any(is_te_hit):
                        cur_ta = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_ATK], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.BOOST_ATK].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.clamp(cur_ta + torch.where(is_te_hit, torch.ones_like(cur_ta), torch.zeros_like(cur_ta)), -6.0, 6.0).unsqueeze(-1)
                        )

                # Berserk (+1 SpA when a hit knocks defender from >50% HP down to <=50% HP while surviving)
                if flags.has_berserk:
                    half_t_hp = torch.floor(max_t_hp * 0.50)
                    is_berserk_hit = (
                        hit_active
                        & (applied_dmg > 0.0)
                        & (tgt_ab == float(AbilityID.BERSERK))
                        & (cur_t_hp > half_t_hp)
                        & (new_t_hp > 0.0)
                        & (new_t_hp <= half_t_hp)
                    )
                    if torch.any(is_berserk_hit):
                        cur_bs = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_SPA], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.BOOST_SPA].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.clamp(cur_bs + torch.where(is_berserk_hit, torch.ones_like(cur_bs), torch.zeros_like(cur_bs)), -6.0, 6.0).unsqueeze(-1)
                        )

                # Spicy Spray (Scovillain-Mega: inflicts Burn on attacker when hit by a damaging move)
                if flags.has_spicy_spray:
                    ss_burns = (
                        hit_active
                        & (applied_dmg > 0.0)
                        & (tgt_ab == float(AbilityID.SPICY_SPRAY))
                        & (torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1) > 0.0)
                        & (torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, actor_slot.unsqueeze(-1)).squeeze(-1) > 0.5)
                        & (att_t1 != TYPE_TO_IDX["fire"])
                        & (~(att_has_t2 & (att_t2 == TYPE_TO_IDX["fire"])))
                        & (att_ab != float(AbilityID.THERMAL_EXCHANGE))
                        & (~((att_ab == float(AbilityID.LEAF_GUARD)) & (w_idx == W_SUN)))
                    )
                    if torch.any(ss_burns):
                        P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY].scatter_(
                            3,
                            actor_slot.unsqueeze(-1),
                            torch.where(ss_burns, torch.zeros_like(cur_t_hp), torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, actor_slot.unsqueeze(-1)).squeeze(-1)).unsqueeze(-1),
                        )
                        P_mc[:, :, :, :, MonIdx.STATUS_BURN].scatter_(
                            3,
                            actor_slot.unsqueeze(-1),
                            torch.where(ss_burns, torch.ones_like(cur_t_hp), torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_BURN], 3, actor_slot.unsqueeze(-1)).squeeze(-1)).unsqueeze(-1),
                        )
                        if flags.has_lum_berry:
                            att_unv_ss = _is_side_unnerved_torch(P_mc, actor_slot) if flags.has_unnerve else None
                            _check_lum_berry_and_unburden_torch(P_mc, actor_slot, blocked_mask=att_unv_ss)

                # Innards Out (Victreebel-Mega: when KO'd, deals pre-hit HP back to attacker)
                if flags.has_innards_out:
                    io_triggers = hit_active & (cur_t_hp > 0.0) & (new_t_hp <= 0.0) & (tgt_ab == float(AbilityID.INNARDS_OUT))
                    if torch.any(io_triggers):
                        cur_a_io = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                        new_a_io = torch.clamp(cur_a_io - torch.where(io_triggers, cur_t_hp, torch.zeros_like(cur_t_hp)), min=0.0)
                        P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), new_a_io.unsqueeze(-1))
                        P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, actor_slot.unsqueeze(-1), (new_a_io > 0.0).float().unsqueeze(-1))

                # Eelevate (Eelektross-Mega: boosts attacker's highest non-HP stat by +1 upon KOing a target)
                if flags.has_eelevate:
                    ee_ko = (
                        hit_active
                        & (cur_t_hp > 0.0)
                        & (new_t_hp <= 0.0)
                        & (att_ab == float(AbilityID.EELEVATE))
                        & (torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1) > 0.0)
                    )
                    if torch.any(ee_ko):
                        att_stats_5 = p_actor[:, :, :, MonIdx.STAT_ATK:MonIdx.STAT_SPE + 1]
                        best_stat_idx = torch.argmax(att_stats_5, dim=-1)  # 0..4
                        for s_i in range(5):
                            m_si = ee_ko & (best_stat_idx == s_i)
                            if torch.any(m_si):
                                cur_eb = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                                P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(
                                    3, actor_slot.unsqueeze(-1), torch.clamp(cur_eb + torch.where(m_si, torch.ones_like(cur_eb), torch.zeros_like(cur_eb)), -6.0, 6.0).unsqueeze(-1)
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

            # Recoil (Flare Blitz, Wood Hammer, Wave Crash; nullified by Rock Head except 50% max-HP Mind Blown/Steel Beam)
            rock_head_blocks = (att_ab == float(AbilityID.ROCK_HEAD)) & (torch.abs(recoil_pct - 0.50) > 0.01)
            has_recoil = dmg_move_hits & (recoil_pct > 0.0) & (total_dmg_this_target > 0.0) & (~rock_head_blocks)
            if torch.any(has_recoil):
                rec_dmg = torch.clamp(torch.floor(total_dmg_this_target * recoil_pct), min=1.0)
                cur_a_hp = torch.clamp(cur_a_hp - torch.where(has_recoil, rec_dmg, torch.zeros_like(rec_dmg)), min=0.0)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), cur_a_hp.unsqueeze(-1))
                P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, actor_slot.unsqueeze(-1), (cur_a_hp > 0.0).float().unsqueeze(-1))

            has_drain = dmg_move_hits & (recoil_pct < 0.0) & (total_dmg_this_target > 0.0) & (cur_a_hp > 0.0)
            if torch.any(has_drain):
                drn_heal = torch.clamp(torch.floor(total_dmg_this_target * torch.abs(recoil_pct)), min=1.0)
                cur_a_hp = torch.minimum(cur_a_hp + torch.where(has_drain, drn_heal, torch.zeros_like(drn_heal)), max_a_hp)
                P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), cur_a_hp.unsqueeze(-1))

            # Shell Bell (heals attacker floor(total_damage / 8) after dealing damage)
            if flags.has_shell_bell:
                sb_heals = (
                    dmg_move_hits
                    & act_item_active
                    & (act_item == float(ItemID.SHELL_BELL))
                    & (total_dmg_this_target > 0.0)
                    & (cur_a_hp > 0.0)
                )
                if torch.any(sb_heals):
                    sb_amt = torch.clamp(torch.floor(total_dmg_this_target / 8.0), min=1.0)
                    cur_a_hp = torch.minimum(cur_a_hp + torch.where(sb_heals, sb_amt, torch.zeros_like(sb_amt)), max_a_hp)
                    P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), cur_a_hp.unsqueeze(-1))

            # Clear Smog resets target's stat stages to 0.0 on damaging hit; Salt Cure applies EoT Salt Cure
            surv_t_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
            is_clear_smog = dmg_move_hits & (surv_t_hp > 0.0) & (field_op == int(FieldOpID.HAZE))
            if torch.any(is_clear_smog):
                for s_i in range(7):
                    cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                    P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(
                        3, tgt_slot.unsqueeze(-1), torch.where(is_clear_smog, torch.zeros_like(cur_b), cur_b).unsqueeze(-1)
                    )

            is_salt_cure_hit = dmg_move_hits & (surv_t_hp > 0.0) & (field_op == int(FieldOpID.SALT_CURE))
            if torch.any(is_salt_cure_hit):
                sc_buf = _get_ev("salt_cured")
                cur_sc = torch.gather(sc_buf, 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                sc_buf.scatter_(
                    3, tgt_slot.unsqueeze(-1), torch.where(is_salt_cure_hit, torch.ones_like(cur_sc), cur_sc).unsqueeze(-1)
                )

            # Check surviving target for secondary effects (Sheer Force & Shield Dust suppress secondary effects)
            sec_blocked = sheer_force_active | (eff_tgt_ab == float(AbilityID.SHIELD_DUST))
            can_proc_sec = dmg_move_hits & (surv_t_hp > 0.0) & (~sec_blocked)

            # Secondary Status Wheel (Scald 30% burn, Thunderbolt 10% para, etc.; blocked by Leaf Guard in Sun / Thermal Exchange burn)
            sec_st_pct = chosen_move[:, :, :, MoveIdx.SEC_STATUS_CHANCE] * 100.0
            if torch.any(can_proc_sec & (sec_st_pct > 0.0)):
                tgt_healthy = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_HEALTHY], 3, tgt_slot.unsqueeze(-1)).squeeze(-1) > 0.5
                leaf_guard_sec_block = (eff_tgt_ab == float(AbilityID.LEAF_GUARD)) & (w_idx == W_SUN)
                sec_burn_block = (chosen_move[:, :, :, MoveIdx.SEC_STATUS_START + STATUS_TO_IDX["burn"]] > 0.5) & (
                    eff_tgt_ab == float(AbilityID.THERMAL_EXCHANGE)
                )
                sec_st_lands = (
                    can_proc_sec
                    & tgt_healthy
                    & (~leaf_guard_sec_block)
                    & (~sec_burn_block)
                    & spin_wheel_gate(
                        sec_st_pct, seed=seed, event_id=int(RNGEventID.SECONDARY_STATUS), step_idx=step_idx * 4 + pass_idx
                    )
                )
                if torch.any(sec_st_lands):
                    for st_i in range(7):
                        new_st_bit = chosen_move[:, :, :, MoveIdx.SEC_STATUS_START + st_i]
                        cur_st_bit = torch.gather(P_mc[:, :, :, :, MonIdx.STATUS_START + st_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                        P_mc[:, :, :, :, MonIdx.STATUS_START + st_i].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.where(sec_st_lands, new_st_bit, cur_st_bit).unsqueeze(-1)
                        )
                    tgt_unv_sec = _is_side_unnerved_torch(P_mc, tgt_slot) if flags.has_unnerve else None
                    if flags.has_chesto_berry:
                        _check_chesto_berry_and_unburden_torch(P_mc, tgt_slot, blocked_mask=tgt_unv_sec)
                    if flags.has_lum_berry:
                        _check_lum_berry_and_unburden_torch(P_mc, tgt_slot, blocked_mask=tgt_unv_sec)

            # Secondary Target Stat Drops (Icy Wind -1 Spe, Snarl -1 SpA, Mystical Fire -1 SpA, etc.)
            if torch.any(can_proc_sec & (~stat_self_flag) & (stat_chance_pct > 0.0)):
                tgt_drop_immune = (
                    (eff_tgt_ab == float(AbilityID.CLEAR_BODY))
                    | (eff_tgt_ab == float(AbilityID.MIRROR_ARMOR))
                    | (
                        (eff_tgt_ab == float(AbilityID.FLOWER_VEIL))
                        & (
                            (p_tgt[:, :, :, MonIdx.TYPE1_START + TYPE_TO_IDX["grass"]] > 0.5)
                            | (p_tgt[:, :, :, MonIdx.TYPE2_START + TYPE_TO_IDX["grass"]] > 0.5)
                        )
                    )
                )
                sec_stat_lands = (
                    can_proc_sec
                    & (~stat_self_flag)
                    & (~tgt_drop_immune)
                    & spin_wheel_gate(
                        stat_chance_pct,
                        seed=seed,
                        event_id=int(RNGEventID.STAT_STAGE_PROC),
                        step_idx=step_idx * 4 + pass_idx,
                    )
                )
                if torch.any(sec_stat_lands):
                    any_drop = torch.zeros_like(sec_stat_lands)
                    tgt_is_contrary = tgt_ab == float(AbilityID.CONTRARY)
                    for s_i in range(7):
                        delta_v = chosen_move[:, :, :, MoveIdx.STAT_DELTA_START + s_i]
                        if torch.any(sec_stat_lands & (delta_v != 0.0)):
                            eff_dv = torch.where(tgt_is_contrary, -delta_v, delta_v)
                            if s_i == 0:
                                hc_sec_blocks = (eff_dv < 0.0) & (eff_tgt_ab == float(AbilityID.HYPER_CUTTER))
                                eff_dv = torch.where(hc_sec_blocks, torch.zeros_like(eff_dv), eff_dv)
                            cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                            any_drop = any_drop | (sec_stat_lands & (eff_dv < 0.0) & (cur_b > -6.0))
                            new_b = torch.clamp(cur_b + torch.where(sec_stat_lands, eff_dv, torch.zeros_like(eff_dv)), min=-6.0, max=6.0)
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
                        if flags.has_white_herb:
                            _check_white_herb_and_unburden_torch(P_mc, tgt_slot)

            # Flinch Spinning-Wheel (Fake Out 100%, Rock Slide / Iron Head / Icicle Crash 30%)
            flinch_pct = chosen_move[:, :, :, MoveIdx.FLINCH_CHANCE] * 100.0
            can_flinch = can_proc_sec & (flinch_pct > 0.0) & (eff_tgt_ab != float(AbilityID.INNER_FOCUS))
            if torch.any(can_flinch):
                flinch_lands = can_flinch & spin_wheel_gate(
                    flinch_pct, seed=seed, event_id=int(RNGEventID.FLINCH_PROC), step_idx=step_idx * 4 + pass_idx
                )
                if torch.any(flinch_lands):
                    cur_fl = torch.gather(P_mc[:, :, :, :, MonIdx.FLINCHED], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                    P_mc[:, :, :, :, MonIdx.FLINCHED].scatter_(
                        3, tgt_slot.unsqueeze(-1), torch.where(flinch_lands, torch.ones_like(cur_fl), cur_fl).unsqueeze(-1)
                    )

            # Reactive Defender Items: Eject Button (defender pivots out) & Red Card (attacker forced out)
            if flags.has_eject_red_card:
                t_it_act_post = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE], 3, tgt_slot.unsqueeze(-1)).squeeze(-1) > 0.5
                t_it_id_post = torch.gather(P_mc[:, :, :, :, MonIdx.ITEM_ID], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                ej_trig = dmg_move_hits & (total_dmg_this_target > 0.0) & (surv_t_hp > 0.0) & t_it_act_post & (t_it_id_post == float(ItemID.EJECT_BUTTON))
                if torch.any(ej_trig):
                    tb1 = torch.where(tgt_is_t1, SLOT_TRAINER_1_BENCH1, SLOT_TRAINER_2_BENCH1)
                    tb2 = torch.where(tgt_is_t1, SLOT_TRAINER_1_BENCH2, SLOT_TRAINER_2_BENCH2)
                    tb1_al = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, tb1.unsqueeze(-1)).squeeze(-1) > 0.0
                    tb2_al = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, tb2.unsqueeze(-1)).squeeze(-1) > 0.0
                    ej_can = ej_trig & (tb1_al | tb2_al)
                    if torch.any(ej_can):
                        P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.where(ej_can, torch.zeros_like(surv_t_hp), t_it_act_post.float()).unsqueeze(-1)
                        )
                        chosen_tb = torch.where(tb1_al, tb1, tb2)
                        persist_mask = tables.switch_persist_mask.to(device).view(1, 1, 1, MON_DIM)
                        t_exp = tgt_slot.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
                        tb_exp = chosen_tb.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
                        p_t_cur = torch.gather(P_mc, 3, t_exp).squeeze(3) * persist_mask
                        p_tb_cur = torch.gather(P_mc, 3, tb_exp).squeeze(3)
                        ej_e = ej_can.unsqueeze(-1)
                        P_mc.scatter_(3, t_exp, torch.where(ej_e, p_tb_cur, torch.gather(P_mc, 3, t_exp).squeeze(3)).unsqueeze(3))
                        P_mc.scatter_(3, tb_exp, torch.where(ej_e, p_t_cur, p_tb_cur).unsqueeze(3))
                        if not m_mc_is_cloned:
                            M_mc = M_mc.clone()
                            m_mc_is_cloned = True
                        t_me = tgt_slot.view(B1, B2, K, 1, 1, 1).expand(B1, B2, K, 1, MOVES_PER_MON, MOVE_DIM)
                        tb_me = chosen_tb.view(B1, B2, K, 1, 1, 1).expand(B1, B2, K, 1, MOVES_PER_MON, MOVE_DIM)
                        m_tc, m_tbc = torch.gather(M_mc, 3, t_me).squeeze(3), torch.gather(M_mc, 3, tb_me).squeeze(3)
                        ej_me = ej_can.view(B1, B2, K, 1, 1)
                        M_mc.scatter_(3, t_me, torch.where(ej_me, m_tbc, m_tc).unsqueeze(3))
                        M_mc.scatter_(3, tb_me, torch.where(ej_me, m_tc, m_tbc).unsqueeze(3))

                rc_trig = (
                    dmg_move_hits
                    & (total_dmg_this_target > 0.0)
                    & (surv_t_hp > 0.0)
                    & (torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1) > 0.0)
                    & t_it_act_post
                    & (t_it_id_post == float(ItemID.RED_CARD))
                )
                if torch.any(rc_trig):
                    ab1 = torch.where(is_t1, SLOT_TRAINER_1_BENCH1, SLOT_TRAINER_2_BENCH1)
                    ab2 = torch.where(is_t1, SLOT_TRAINER_1_BENCH2, SLOT_TRAINER_2_BENCH2)
                    ab1_al = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, ab1.unsqueeze(-1)).squeeze(-1) > 0.0
                    ab2_al = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, ab2.unsqueeze(-1)).squeeze(-1) > 0.0
                    rc_can = rc_trig & (ab1_al | ab2_al)
                    if torch.any(rc_can):
                        P_mc[:, :, :, :, MonIdx.ITEM_ACTIVE].scatter_(
                            3, tgt_slot.unsqueeze(-1), torch.where(rc_can, torch.zeros_like(surv_t_hp), t_it_act_post.float()).unsqueeze(-1)
                        )
                        rc_unb = rc_can & (tgt_ab == float(AbilityID.UNBURDEN))
                        if torch.any(rc_unb):
                            cur_unb = torch.gather(P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE], 3, tgt_slot.unsqueeze(-1)).squeeze(-1)
                            P_mc[:, :, :, :, MonIdx.UNBURDEN_ACTIVE].scatter_(
                                3, tgt_slot.unsqueeze(-1), torch.where(rc_unb, torch.ones_like(cur_unb), cur_unb).unsqueeze(-1)
                            )
                        chosen_ab = torch.where(ab1_al, ab1, ab2)
                        persist_mask = tables.switch_persist_mask.to(device).view(1, 1, 1, MON_DIM)
                        a_exp = actor_slot.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
                        ab_exp = chosen_ab.view(B1, B2, K, 1, 1).expand(B1, B2, K, 1, MON_DIM)
                        p_a_cur = torch.gather(P_mc, 3, a_exp).squeeze(3) * persist_mask
                        p_ab_cur = torch.gather(P_mc, 3, ab_exp).squeeze(3)
                        rc_e = rc_can.unsqueeze(-1)
                        P_mc.scatter_(3, a_exp, torch.where(rc_e, p_ab_cur, torch.gather(P_mc, 3, a_exp).squeeze(3)).unsqueeze(3))
                        P_mc.scatter_(3, ab_exp, torch.where(rc_e, p_a_cur, p_ab_cur).unsqueeze(3))
                        if not m_mc_is_cloned:
                            M_mc = M_mc.clone()
                            m_mc_is_cloned = True
                        a_me = actor_slot.view(B1, B2, K, 1, 1, 1).expand(B1, B2, K, 1, MOVES_PER_MON, MOVE_DIM)
                        ab_me = chosen_ab.view(B1, B2, K, 1, 1, 1).expand(B1, B2, K, 1, MOVES_PER_MON, MOVE_DIM)
                        m_ac, m_abc = torch.gather(M_mc, 3, a_me).squeeze(3), torch.gather(M_mc, 3, ab_me).squeeze(3)
                        rc_me = rc_can.view(B1, B2, K, 1, 1)
                        M_mc.scatter_(3, a_me, torch.where(rc_me, m_abc, m_ac).unsqueeze(3))
                        M_mc.scatter_(3, ab_me, torch.where(rc_me, m_ac, m_abc).unsqueeze(3))

        # Explosion / Self-Destruct / Misty Explosion self-faint (always faints user when executed without Damp)
        exp_faint = can_act & is_explosion_move
        if torch.any(exp_faint):
            cur_a_exp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            new_a_exp = torch.where(exp_faint, torch.zeros_like(cur_a_exp), cur_a_exp)
            P_mc[:, :, :, :, MonIdx.HP_CUR].scatter_(3, actor_slot.unsqueeze(-1), new_a_exp.unsqueeze(-1))
            P_mc[:, :, :, :, MonIdx.ALIVE_FLAG].scatter_(3, actor_slot.unsqueeze(-1), (new_a_exp > 0.0).float().unsqueeze(-1))

        # ---------------------------------------------------------------------
        # L. SELF STAT CHANGES ON DAMAGING MOVES & LIFE ORB RECOIL
        # ---------------------------------------------------------------------
        if torch.any(actor_connected_any):
            cur_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_CUR], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            max_a_hp = torch.gather(P_mc[:, :, :, :, MonIdx.HP_MAX], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
            # Life Orb 10% recoil (once per move connection; suppressed when Sheer Force boosts the move)
            if flags.has_life_orb:
                lo_recoil_mask = (
                    actor_connected_any
                    & (cat_idx != 2)
                    & act_item_active
                    & (act_item == float(ItemID.LIFE_ORB))
                    & (~sheer_force_active)
                    & (cur_a_hp > 0.0)
                )
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
                    self_contrary = att_ab == float(AbilityID.CONTRARY)
                    for s_i in range(7):
                        delta_v = chosen_move[:, :, :, MoveIdx.STAT_DELTA_START + s_i]
                        if torch.any(self_stat_lands & (delta_v != 0.0)):
                            eff_dv = torch.where(self_contrary, -delta_v, delta_v)
                            cur_b = torch.gather(P_mc[:, :, :, :, MonIdx.BOOST_START + s_i], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                            new_b = torch.clamp(cur_b + torch.where(self_stat_lands, eff_dv, torch.zeros_like(eff_dv)), min=-6.0, max=6.0)
                            P_mc[:, :, :, :, MonIdx.BOOST_START + s_i].scatter_(3, actor_slot.unsqueeze(-1), new_b.unsqueeze(-1))
                    if flags.has_white_herb:
                        _check_white_herb_and_unburden_torch(P_mc, actor_slot)
            if flags.has_sitrus_berry:
                act_unv_end = _is_side_unnerved_torch(P_mc, actor_slot) if flags.has_unnerve else None
                _check_sitrus_berry_and_unburden_torch(P_mc, actor_slot, blocked_mask=act_unv_end)

            # Post-Attack Forced Recharge Flag (Hyper Beam, Giga Impact, Blast Burn, Hydro Cannon, etc.)
            is_recharge_move = chosen_move[:, :, :, MoveIdx.IS_RECHARGE_MOVE] > 0.5
            inflicts_recharge = actor_connected_any & is_recharge_move & (cur_a_hp > 0.0)
            if torch.any(inflicts_recharge):
                cur_rech = torch.gather(P_mc[:, :, :, :, MonIdx.MUST_RECHARGE], 3, actor_slot.unsqueeze(-1)).squeeze(-1)
                P_mc[:, :, :, :, MonIdx.MUST_RECHARGE].scatter_(
                    3,
                    actor_slot.unsqueeze(-1),
                    torch.where(inflicts_recharge, torch.ones_like(cur_rech), cur_rech).unsqueeze(-1),
                )

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

    # Clear spent recharge lock ONLY for slots that started this turn recharging
    # (Preserves newly inflicted MUST_RECHARGE = 1.0 from Hyper Beam/Giga Impact into EOT & Ply-2!)
    if torch.any(started_recharging):
        P_mc[:, :, :, :, MonIdx.MUST_RECHARGE] = torch.where(
            started_recharging,
            torch.zeros_like(P_mc[:, :, :, :, MonIdx.MUST_RECHARGE]),
            P_mc[:, :, :, :, MonIdx.MUST_RECHARGE],
        )

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
        extra_volatiles=extra_volatiles_dict if extra_volatiles_dict else None,
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
            extra_volatiles=(
                {k: v.numpy() for k, v in res_t.extra_volatiles.items()}
                if res_t.extra_volatiles
                else None
            ),
        )

    raise RuntimeError("PyTorch is required for vectorized tensor execution.")
