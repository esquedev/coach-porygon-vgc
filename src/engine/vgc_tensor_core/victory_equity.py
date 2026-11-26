# -*- coding: utf-8 -*-
"""8-Pillar Linear Victory Equity Evaluator (`V_eq = w^T * phi(s)`) for Regulation M-C.

Pure-domain vectorized PyTorch evaluator grounded in KO-equivalent units
(`1 Full Healthy KO = 1.75 Equity Points`: `1.00` HP% + `0.75` Alive Mon).

Evaluates 8 strictly antisymmetric (`trainer_1 - trainer_2`) tactical pillars:
1. **Material** (`hp`, `alive`, `terminal`)
2. **Speed-Weighted Lethal Threat & Focus-Fire** (`M_moves`-aware `2x2` active coverage)
3. **Enemy Mal-Positioning & Bench Escape Audit** (trapped matchup surplus x bench escape safety)
4. **Role-Aware Option Restriction** (Choice-lock trap, Protect-streak lethal exposure, Taunt,
   Throat Chop, Encore, Disable, Recharge lock, Yawn, Leech Seed, Salt Cure, Perish Song)
5. **Role-Aware Status & HP-Scaled Stat Boosts** (Physical vs Special Burn, TR Paralysis, move-role boosts)
6. **HP-Gated 2-Turn Primed Payoffs** (`LAST_MOVE_FAILED` w/ Stomping Tantrum, queued charges, Charge, -Glaive Rush)
7. **Shield Thresholds & Resource Economy** (intact Focus Sash, Disguise, Multiscale, Sturdy, unspent Mega, berries, Fake Out)
8. **Field Tempo, Remaining Turns & Entry Hazards** (turn-scaled Tailwind/Screens/TR, Weather/Terrain synergy, Toxic Spikes)

Zero web/UI dependencies. Strictly `trainer_1` / `trainer_2` identifiers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from .phases_pre_attack import (
    T_ELECTRIC,
    T_GRASSY,
    T_MISTY,
    T_PSYCHIC,
    W_RAIN,
    W_SAND,
    W_SNOW,
    W_SUN,
)
from .schema_and_tables import (
    AbilityID,
    BilinearLookupTables,
    FieldIdx,
    FieldOpID,
    HAS_TORCH,
    ItemID,
    MonIdx,
    MoveIdx,
    OverrideDefStat,
    OverrideOffStat,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    TYPE_TO_IDX,
    TargetType,
    build_bilinear_lookup_tables,
)

if HAS_TORCH:
    import torch
else:
    torch = None  # type: ignore

EQUITY_ENGINE_VERSION: str = "v2_8pillar"
DEFAULT_TUNED_WEIGHTS_PATH: Path = Path("data/telemetry/equity_weights.json")

# Canonical feature names for Texel/TD logging and attribution
PILLAR_NAMES: Tuple[str, ...] = (
    "material",
    "threat",
    "malposition",
    "restriction",
    "status_boost",
    "two_turn_prime",
    "resources",
    "field_tempo",
)


@dataclass(frozen=True)
class VictoryEquityWeights:
    """KO-anchored linear weights for the 8-Pillar Victory Equity model.

    Anchor: 1 Full Healthy KO = `1.75` Equity Points (`w_hp = 1.00`, `w_alive = 0.75`).
    All tactical weights are bounded so a single clean KO dominates minor tempo edges.
    """

    w_hp: float = 1.00
    w_alive: float = 0.75
    w_terminal: float = 2.50
    w_threat: float = 0.32
    w_malposition: float = 0.28
    w_restriction: float = 0.30
    w_status: float = 0.30
    w_boost: float = 0.12
    w_two_turn_prime: float = 0.25
    w_resources: float = 0.14
    w_field_tempo: float = 0.25

    def to_dict(self) -> Dict[str, float]:
        """Serialize weights to a plain float dictionary."""
        return {k: float(v) for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VictoryEquityWeights":
        """Construct weights from a dictionary, falling back to anchor defaults for omitted keys."""
        base = cls()
        kwargs: Dict[str, float] = {}
        for field_name, default_val in asdict(base).items():
            if field_name in data and data[field_name] is not None:
                kwargs[field_name] = float(data[field_name])
            else:
                kwargs[field_name] = float(default_val)
        return cls(**kwargs)

    @classmethod
    def load_or_default(cls, path: Path = DEFAULT_TUNED_WEIGHTS_PATH) -> "VictoryEquityWeights":
        """Load user-calibrated weights from JSON if present and valid; otherwise return anchor defaults."""
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                w_dict = raw.get("weights", raw) if isinstance(raw, dict) else {}
                if isinstance(w_dict, dict) and w_dict:
                    return cls.from_dict(w_dict)
            except Exception:
                pass
        return cls()


@dataclass(frozen=True)
class VictoryEquityBreakdown:
    """Decomposed 8-pillar equity attribution (mean across `[B1, B2, K]` or single cell)."""

    material: float
    threat: float
    malposition: float
    restriction: float
    status_boost: float
    two_turn_prime: float
    resources: float
    field_tempo: float
    total: float
    phi_raw: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize breakdown for API responses, commentary attribution, and telemetry logging."""
        return {
            "engine_version": EQUITY_ENGINE_VERSION,
            "pillars": {
                "material": round(self.material, 4),
                "threat": round(self.threat, 4),
                "malposition": round(self.malposition, 4),
                "restriction": round(self.restriction, 4),
                "status_boost": round(self.status_boost, 4),
                "two_turn_prime": round(self.two_turn_prime, 4),
                "resources": round(self.resources, 4),
                "field_tempo": round(self.field_tempo, 4),
            },
            "total": round(self.total, 4),
            "phi_raw": {k: round(float(v), 5) for k, v in self.phi_raw.items()},
        }


_DEFAULT_TABLES_CACHE: Dict[str, BilinearLookupTables] = {}


def _get_type_chart_on_device(
    device: Any,
    tables: Optional[BilinearLookupTables],
) -> Tuple["torch.Tensor", "torch.Tensor", "torch.Tensor"]:
    """Retrieve `(m_type_chart, m_weather_mod, m_terrain_mod)` tensors on `device`."""
    if tables is not None:
        return (
            tables.m_type_chart.to(device),
            tables.m_weather_mod.to(device),
            tables.m_terrain_mod.to(device),
        )
    key = str(device)
    cached = _DEFAULT_TABLES_CACHE.get(key)
    if cached is None:
        cached = build_bilinear_lookup_tables(device=device)
        _DEFAULT_TABLES_CACHE[key] = cached
    return (
        cached.m_type_chart.to(device),
        cached.m_weather_mod.to(device),
        cached.m_terrain_mod.to(device),
    )


def _stage_mult(stage: "torch.Tensor") -> "torch.Tensor":
    """Exact cartridge stat-stage multiplier tensor in `[2/8 .. 8/2]`."""
    s = torch.clamp(stage, -6.0, 6.0)
    two = torch.tensor(2.0, dtype=torch.float32, device=stage.device)
    return torch.maximum(two, two + s) / torch.maximum(two, two - s)


def _compute_directional_threat_matrix_torch(
    F_eot: "torch.Tensor",
    P_eot: "torch.Tensor",
    M_moves: "torch.Tensor",
    att_slots: Tuple[int, int],
    def_slots: Tuple[int, int],
    s_eff_8: "torch.Tensor",
    tr_sign: "torch.Tensor",
    w_idx_clear_adj: "torch.Tensor",
    tr_idx: "torch.Tensor",
    def_is_t1: bool,
    type_chart: "torch.Tensor",
    w_chart: "torch.Tensor",
    t_chart: "torch.Tensor",
) -> Tuple["torch.Tensor", "torch.Tensor", "torch.Tensor", "torch.Tensor"]:
    """Compute vectorized `[B1, B2, K, 2, 2]` best legal move threat from `att_slots` onto `def_slots`.

    Returns:
        `(best_weighted_threat, best_raw_dmg, max_legal_move_dmg_per_att, att_phys_spec_status_ratios)`
        - `best_weighted_threat`: `[B1, B2, K, 2, 2]` speed/priority-weighted best damage fraction.
        - `best_raw_dmg`: `[B1, B2, K, 2, 2]` unweighted best damage fraction in `[0.0, 1.25]`.
        - `max_legal_move_dmg_per_att`: `[B1, B2, K, 2]` max raw damage fraction each attacker can deal to either defender.
        - `att_has_sound_and_tantrum`: `[B1, B2, K, 2, 4]` summary flags `[phys_frac, spec_frac, status_frac, has_sound]`.
    """
    device = P_eot.device
    p_att = P_eot[:, :, :, list(att_slots), :]       # [..., 2, MON_DIM]
    p_def = P_eot[:, :, :, list(def_slots), :]       # [..., 2, MON_DIM]
    m_att = M_moves[:, :, :, list(att_slots), :, :]  # [..., 2, 4, MOVE_DIM]

    att_alive = (p_att[..., MonIdx.HP_CUR] > 0.0).float()  # [..., 2]
    def_alive = (p_def[..., MonIdx.HP_CUR] > 0.0).float()  # [..., 2]

    # Move properties: [..., 2, 4]
    bp = m_att[..., MoveIdx.BASE_POWER]
    is_phys = m_att[..., MoveIdx.CAT_PHYSICAL] > 0.5
    is_spec = m_att[..., MoveIdx.CAT_SPECIAL] > 0.5
    is_status = m_att[..., MoveIdx.CAT_STATUS] > 0.5
    is_sound = m_att[..., MoveIdx.IS_SOUND_MOVE] > 0.5
    is_contact = m_att[..., MoveIdx.IS_CONTACT] > 0.5
    is_slicing = m_att[..., MoveIdx.IS_SLICING] > 0.5
    is_punch = m_att[..., MoveIdx.IS_PUNCH] > 0.5
    fop = torch.round(m_att[..., MoveIdx.FIELD_OP_ID]).long()
    w_sure = m_att[..., MoveIdx.WEATHER_SURE_HIT]
    m_prio = m_att[..., MoveIdx.PRIORITY]
    tgt_type = torch.round(m_att[..., MoveIdx.TARGET_TYPE]).long()
    m_type_idx = torch.argmax(m_att[..., MoveIdx.TYPE_START:MoveIdx.TYPE_END], dim=-1)  # [..., 2, 4]

    # Role ratios per attacker across valid move slots: [..., 2]
    valid_m = (bp > 0.0) | is_status
    valid_cnt = torch.clamp(valid_m.float().sum(dim=-1), min=1.0)
    phys_frac = (is_phys & (bp > 0.0)).float().sum(dim=-1) / valid_cnt
    spec_frac = (is_spec & (bp > 0.0)).float().sum(dim=-1) / valid_cnt
    stat_frac = is_status.float().sum(dim=-1) / valid_cnt
    has_sound = is_sound.any(dim=-1).float()
    role_summary = torch.stack([phys_frac, spec_frac, stat_frac, has_sound], dim=-1)  # [..., 2, 4]

    # Legality mask per move [..., 2, 4]
    m_slots = torch.arange(4, device=device, dtype=torch.long).view(1, 1, 1, 1, 4)
    ch_lock = torch.round(p_att[..., MonIdx.CHOICE_LOCKED_MOVE]).long().unsqueeze(-1)
    enc_on = (p_att[..., MonIdx.ENCORE_TURNS] > 0.0).unsqueeze(-1)
    last_mv = torch.round(p_att[..., MonIdx.LAST_MOVE_IDX]).long().unsqueeze(-1)
    tc_on = (p_att[..., MonIdx.THROAT_CHOP_TURNS] > 0.0).unsqueeze(-1)
    rech_on = (p_att[..., MonIdx.MUST_RECHARGE] > 0.5).unsqueeze(-1)
    act_turns = p_att[..., MonIdx.ACTIVE_TURNS].unsqueeze(-1)
    chg_idx = torch.round(p_att[..., MonIdx.CHARGED_MOVE_IDX]).long().unsqueeze(-1)  # 0 none, 1..4 = m+1

    legal_dmg_move = (
        (bp > 0.0)
        & (~is_status)
        & (~rech_on)
        & ((ch_lock < 0) | (m_slots == ch_lock))
        & ((~enc_on) | (last_mv < 0) | (m_slots == last_mv))
        & ((~tc_on) | (~is_sound))
        & ((m_att[..., MoveIdx.FIRST_TURN_ONLY] <= 0.5) | (act_turns <= 0.0))
        & ((chg_idx <= 0) | (chg_idx == (m_slots + 1)))
    )

    # Attacker abilities / items / types: [..., 2, 1]
    att_ab = p_att[..., MonIdx.ABILITY_ID].unsqueeze(-1)
    att_it = p_att[..., MonIdx.ITEM_ID].unsqueeze(-1)
    att_it_on = (p_att[..., MonIdx.ITEM_ACTIVE] > 0.5).unsqueeze(-1)
    att_mb = att_ab == float(AbilityID.MOLD_BREAKER)
    att_t1 = torch.argmax(p_att[..., MonIdx.TYPE1_START:MonIdx.TYPE1_END], dim=-1).unsqueeze(-1)
    att_t2 = torch.argmax(p_att[..., MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1).unsqueeze(-1)
    att_has_t2 = (p_att[..., MonIdx.TYPE2_START:MonIdx.TYPE2_END].sum(dim=-1) > 0.5).unsqueeze(-1)
    grav_on = (F_eot[..., FieldIdx.GRAVITY_TURNS] > 0.0).unsqueeze(-1).unsqueeze(-1)
    att_gr = (p_att[..., MonIdx.GROUNDED_FLAG] > 0.5).unsqueeze(-1) | grav_on

    w_act = w_idx_clear_adj.unsqueeze(-1).unsqueeze(-1)  # [..., 1, 1]
    w_act_eff = torch.where(att_ab == float(AbilityID.MEGA_SOL), torch.full_like(w_act, W_SUN), w_act)
    tr_act = tr_idx.unsqueeze(-1).unsqueeze(-1)          # [..., 1, 1]

    # Dynamic move type adjustments (Weather Ball, Liquid Voice, -ate)
    is_wb = w_sure == 1.0
    wb_type = torch.where(
        w_act_eff == W_SUN,
        torch.full_like(m_type_idx, TYPE_TO_IDX["fire"]),
        torch.where(
            w_act_eff == W_RAIN,
            torch.full_like(m_type_idx, TYPE_TO_IDX["water"]),
            torch.where(
                w_act_eff == W_SAND,
                torch.full_like(m_type_idx, TYPE_TO_IDX["rock"]),
                torch.where(
                    w_act_eff == W_SNOW,
                    torch.full_like(m_type_idx, TYPE_TO_IDX["ice"]),
                    torch.full_like(m_type_idx, TYPE_TO_IDX["normal"]),
                ),
            ),
        ),
    )
    m_type_eff = torch.where(is_wb, wb_type, m_type_idx)
    bp_eff = torch.where(is_wb & (w_act_eff != 0), torch.full_like(bp, 100.0), bp)

    is_lv = (att_ab == float(AbilityID.LIQUID_VOICE)) & is_sound
    m_type_eff = torch.where(is_lv, torch.full_like(m_type_eff, TYPE_TO_IDX["water"]), m_type_eff)

    is_norm_conv = (m_type_eff == TYPE_TO_IDX["normal"]) & (~is_wb) & (~is_lv)
    is_aer = is_norm_conv & (att_ab == float(AbilityID.AERILATE))
    is_pix = is_norm_conv & (att_ab == float(AbilityID.PIXILATE))
    is_ref = is_norm_conv & (att_ab == float(AbilityID.REFRIGERATE))
    is_drg = is_norm_conv & (att_ab == float(AbilityID.DRAGONIZE))
    m_type_eff = torch.where(
        is_aer,
        torch.full_like(m_type_eff, TYPE_TO_IDX["flying"]),
        torch.where(
            is_pix,
            torch.full_like(m_type_eff, TYPE_TO_IDX["fairy"]),
            torch.where(
                is_ref,
                torch.full_like(m_type_eff, TYPE_TO_IDX["ice"]),
                torch.where(is_drg, torch.full_like(m_type_eff, TYPE_TO_IDX["dragon"]), m_type_eff),
            ),
        ),
    )
    bp_eff = torch.where(is_aer | is_pix | is_ref | is_drg, bp_eff * 1.2, bp_eff)

    # Effective Base Power boosts (Technician, Tough Claws, Sharpness, Iron Fist, Expanding Force, Stomping Tantrum, Charge, Multi-hit)
    exp_hits = torch.clamp(m_att[..., MoveIdx.EXPECTED_HITS], min=1.0)
    bp_eff = bp_eff * exp_hits
    bp_eff = torch.where((att_ab == float(AbilityID.TECHNICIAN)) & (bp <= 60.0), bp_eff * 1.5, bp_eff)
    bp_eff = torch.where((att_ab == float(AbilityID.TOUGH_CLAWS)) & is_contact, bp_eff * 1.3, bp_eff)
    bp_eff = torch.where((att_ab == float(AbilityID.SHARPNESS)) & is_slicing, bp_eff * 1.5, bp_eff)
    bp_eff = torch.where((att_ab == float(AbilityID.IRON_FIST)) & is_punch, bp_eff * 1.2, bp_eff)
    is_exp_psy = (fop == int(FieldOpID.EXPANDING_FORCE)) & (tr_act == T_PSYCHIC) & att_gr
    bp_eff = torch.where(is_exp_psy, bp_eff * 1.5, bp_eff)
    # 2-turn primed BP multipliers
    prev_failed = (p_att[..., MonIdx.LAST_MOVE_FAILED] > 0.5).unsqueeze(-1)
    bp_eff = torch.where((fop == int(FieldOpID.STOMPING_TANTRUM)) & prev_failed, bp_eff * 2.0, bp_eff)
    chg_act = (p_att[..., MonIdx.CHARGE_ACTIVE] > 0.5).unsqueeze(-1)
    bp_eff = torch.where(chg_act & (m_type_eff == TYPE_TO_IDX["electric"]), bp_eff * 2.0, bp_eff)
    # Discount uncharged 2-turn moves (unless already charged or weather-skipped)
    uncharged_2t = (
        (((w_sure == 10.0) & (w_act_eff != W_SUN)) | ((w_sure == 20.0) & (w_act_eff != W_RAIN)) | (w_sure == 30.0) | (fop == int(FieldOpID.PHANTOM_FORCE)))
        & (chg_idx != (m_slots + 1))
    )
    bp_eff = torch.where(uncharged_2t, bp_eff * 0.35, bp_eff)

    # Spread factor when both defenders are alive
    both_def_alive = ((def_alive[..., 0] > 0.5) & (def_alive[..., 1] > 0.5)).unsqueeze(-1).unsqueeze(-1)
    is_spread_mv = (tgt_type == int(TargetType.ALL_ADJACENT_FOES)) | (tgt_type == int(TargetType.ALL_ADJACENT)) | is_exp_psy
    bp_eff = torch.where(is_spread_mv & both_def_alive, bp_eff * 0.75, bp_eff)

    # Expand to pairwise [..., 2(att), 4(move), 2(def)]
    bp_pair = bp_eff.unsqueeze(-1)                          # [..., 2, 4, 1]
    m_type_pair = m_type_eff.unsqueeze(-1).expand(-1, -1, -1, -1, -1, 2)  # [..., 2, 4, 2]
    fop_pair = fop.unsqueeze(-1)                            # [..., 2, 4, 1]
    is_phys_pair = is_phys.unsqueeze(-1)                    # [..., 2, 4, 1]
    is_contact_pair = is_contact.unsqueeze(-1)
    is_sound_pair = is_sound.unsqueeze(-1)

    # Defender properties: [..., 1, 1, 2]
    def_t1 = torch.argmax(p_def[..., MonIdx.TYPE1_START:MonIdx.TYPE1_END], dim=-1).unsqueeze(-2).unsqueeze(-2)
    def_t2 = torch.argmax(p_def[..., MonIdx.TYPE2_START:MonIdx.TYPE2_END], dim=-1).unsqueeze(-2).unsqueeze(-2)
    def_has_t2 = (p_def[..., MonIdx.TYPE2_START:MonIdx.TYPE2_END].sum(dim=-1) > 0.5).unsqueeze(-2).unsqueeze(-2)
    def_ab_raw = p_def[..., MonIdx.ABILITY_ID].unsqueeze(-2).unsqueeze(-2)
    att_mb_pair = att_mb.unsqueeze(-1)
    def_ab = torch.where(att_mb_pair, torch.zeros_like(def_ab_raw), def_ab_raw)
    def_gr = (p_def[..., MonIdx.GROUNDED_FLAG] > 0.5).unsqueeze(-2).unsqueeze(-2) | grav_on.unsqueeze(-1)
    def_it_on = (p_def[..., MonIdx.ITEM_ACTIVE] > 0.5).unsqueeze(-2).unsqueeze(-2)
    def_it_id = p_def[..., MonIdx.ITEM_ID].unsqueeze(-2).unsqueeze(-2)

    # Knock Off 1.5x vs removable item (never Mega Stone)
    ko_rem = (
        (fop_pair == int(FieldOpID.KNOCK_OFF))
        & def_it_on
        & (def_it_id != float(ItemID.NONE))
        & (def_it_id != float(ItemID.MEGA_STONE))
    )
    bp_pair = torch.where(ko_rem, bp_pair * 1.5, bp_pair)

    # Type effectiveness [..., 2, 4, 2]
    eff1 = type_chart[m_type_pair, def_t1.expand_as(m_type_pair)]
    eff2 = torch.where(def_has_t2.expand_as(m_type_pair), type_chart[m_type_pair, def_t2.expand_as(m_type_pair)], torch.ones_like(eff1))
    is_fd_pair = fop_pair == int(FieldOpID.FREEZE_DRY)
    eff1 = torch.where(is_fd_pair & (def_t1 == TYPE_TO_IDX["water"]), torch.full_like(eff1, 2.0), eff1)
    eff2 = torch.where(is_fd_pair & def_has_t2 & (def_t2 == TYPE_TO_IDX["water"]), torch.full_like(eff2, 2.0), eff2)
    type_eff = eff1 * eff2

    # Scrappy & Ground immunity
    is_scrappy = (att_ab.unsqueeze(-1) == float(AbilityID.SCRAPPY)) & (
        (m_type_pair == TYPE_TO_IDX["normal"]) | (m_type_pair == TYPE_TO_IDX["fighting"])
    )
    type_eff = torch.where(is_scrappy & (type_eff == 0.0), torch.ones_like(type_eff), type_eff)
    type_eff = torch.where((m_type_pair == TYPE_TO_IDX["ground"]) & (~def_gr), torch.zeros_like(type_eff), type_eff)

    # Elemental / Sound / Bullet / Priority Ability Immunities
    immune_mask = (
        ((m_type_pair == TYPE_TO_IDX["fire"]) & (def_ab == float(AbilityID.FLASH_FIRE)))
        | ((m_type_pair == TYPE_TO_IDX["water"]) & ((def_ab == float(AbilityID.WATER_ABSORB)) | (def_ab == float(AbilityID.DRY_SKIN))))
        | ((m_type_pair == TYPE_TO_IDX["electric"]) & ((def_ab == float(AbilityID.VOLT_ABSORB)) | (def_ab == float(AbilityID.MOTOR_DRIVE)) | (def_ab == float(AbilityID.LIGHTNING_ROD))))
        | ((m_type_pair == TYPE_TO_IDX["grass"]) & (def_ab == float(AbilityID.SAP_SIPPER)))
        | ((m_type_pair == TYPE_TO_IDX["ground"]) & (def_ab == float(AbilityID.EARTH_EATER)))
        | (is_sound_pair & (def_ab == float(AbilityID.SOUNDPROOF)))
        | (((fop_pair == int(FieldOpID.FLAG_BULLET)) | (fop_pair == int(FieldOpID.FLAG_PULSE_BULLET))) & (def_ab == float(AbilityID.BULLETPROOF)))
    )
    # Effective priority & priority blockers
    eff_prio = (
        m_prio
        + ((m_att[..., MoveIdx.GRASSY_PRIO_BOOST] > 0.5) & (tr_act == T_GRASSY) & att_gr).float()
        + (
            (att_ab == float(AbilityID.GALE_WINGS))
            & (m_type_eff == TYPE_TO_IDX["flying"])
            & (p_att[..., MonIdx.HP_CUR].unsqueeze(-1) >= p_att[..., MonIdx.HP_MAX].unsqueeze(-1))
        ).float()
    )
    eff_prio_pair = eff_prio.unsqueeze(-1)
    def_side_prio_block = torch.any(
        (p_def[..., MonIdx.HP_CUR] > 0.0)
        & ((p_def[..., MonIdx.ABILITY_ID] == float(AbilityID.ARMOR_TAIL)) | (p_def[..., MonIdx.ABILITY_ID] == float(AbilityID.QUEENLY_MAJESTY))),
        dim=-1,
    ).unsqueeze(-1).unsqueeze(-1).unsqueeze(-1)
    prio_blocked = (eff_prio_pair > 0.0) & (
        (def_side_prio_block & (~att_mb_pair)) | ((tr_act.unsqueeze(-1) == T_PSYCHIC) & def_gr)
    )
    type_eff = torch.where(immune_mask | prio_blocked, torch.zeros_like(type_eff), type_eff)

    # Offensive / Defensive stats & stages (with Body Press, Psyshock, Unaware, Huge Power, Water Bubble, Thick Fat)
    off_ovr = torch.round(m_att[..., MoveIdx.OVERRIDE_OFF_STAT]).long().unsqueeze(-1)
    def_ovr = torch.round(m_att[..., MoveIdx.OVERRIDE_DEF_STAT]).long().unsqueeze(-1)

    att_stat_raw = torch.where(
        off_ovr == int(OverrideOffStat.USER_DEF),
        p_att[..., MonIdx.STAT_DEF].unsqueeze(-1).unsqueeze(-1),
        torch.where(
            is_phys_pair,
            p_att[..., MonIdx.STAT_ATK].unsqueeze(-1).unsqueeze(-1),
            p_att[..., MonIdx.STAT_SPA].unsqueeze(-1).unsqueeze(-1),
        ),
    )
    att_stage_raw = torch.where(
        off_ovr == int(OverrideOffStat.USER_DEF),
        p_att[..., MonIdx.BOOST_DEF].unsqueeze(-1).unsqueeze(-1),
        torch.where(
            is_phys_pair,
            p_att[..., MonIdx.BOOST_ATK].unsqueeze(-1).unsqueeze(-1),
            p_att[..., MonIdx.BOOST_SPA].unsqueeze(-1).unsqueeze(-1),
        ),
    )
    def_stat_raw = torch.where(
        is_phys_pair | (def_ovr == int(OverrideDefStat.TARGET_DEF)),
        p_def[..., MonIdx.STAT_DEF].unsqueeze(-2).unsqueeze(-2),
        p_def[..., MonIdx.STAT_SPD].unsqueeze(-2).unsqueeze(-2),
    )
    def_stage_raw = torch.where(
        is_phys_pair | (def_ovr == int(OverrideDefStat.TARGET_DEF)),
        p_def[..., MonIdx.BOOST_DEF].unsqueeze(-2).unsqueeze(-2),
        p_def[..., MonIdx.BOOST_SPD].unsqueeze(-2).unsqueeze(-2),
    )
    # Unaware stage suppression
    att_stage_eff = torch.where(def_ab == float(AbilityID.UNAWARE), torch.zeros_like(att_stage_raw), att_stage_raw)
    def_stage_eff = torch.where(att_ab.unsqueeze(-1) == float(AbilityID.UNAWARE), torch.zeros_like(def_stage_raw), def_stage_raw)

    A = att_stat_raw * _stage_mult(att_stage_eff)
    D = torch.clamp(def_stat_raw * _stage_mult(def_stage_eff), min=1.0)
    A = torch.where(is_phys_pair & (att_ab.unsqueeze(-1) == float(AbilityID.HUGE_POWER)), A * 2.0, A)
    A = torch.where((att_ab.unsqueeze(-1) == float(AbilityID.WATER_BUBBLE)) & (m_type_pair == TYPE_TO_IDX["water"]), A * 2.0, A)
    A = torch.where(
        ((def_ab == float(AbilityID.THICK_FAT)) & ((m_type_pair == TYPE_TO_IDX["fire"]) | (m_type_pair == TYPE_TO_IDX["ice"])))
        | ((def_ab == float(AbilityID.WATER_BUBBLE)) & (m_type_pair == TYPE_TO_IDX["fire"])),
        A * 0.5,
        A,
    )

    # STAB, Weather, Terrain, Burn, Screens, Defensive Abilities, Items
    is_stab = (m_type_eff == att_t1) | (att_has_t2 & (m_type_eff == att_t2))
    stab_mult = torch.where(
        is_stab,
        torch.where(att_ab == float(AbilityID.ADAPTABILITY), torch.full_like(bp_eff, 2.0), torch.full_like(bp_eff, 1.5)),
        torch.ones_like(bp_eff),
    ).unsqueeze(-1)
    w_mult = w_chart[w_act_eff, m_type_eff].unsqueeze(-1)
    t_mult = torch.where(att_gr, t_chart[tr_act, m_type_eff], torch.ones_like(bp_eff)).unsqueeze(-1)
    burn_pen = torch.where(
        is_phys_pair & (p_att[..., MonIdx.STATUS_BURN].unsqueeze(-1).unsqueeze(-1) > 0.5) & (att_ab.unsqueeze(-1) != float(AbilityID.GUTS)),
        torch.full_like(bp_pair, 0.5),
        torch.ones_like(bp_pair),
    )

    # Screens on defending side
    refl_t = F_eot[..., FieldIdx.TRAINER_1_REFLECT_TURNS if def_is_t1 else FieldIdx.TRAINER_2_REFLECT_TURNS]
    lscr_t = F_eot[..., FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS if def_is_t1 else FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS]
    veil_t = F_eot[..., FieldIdx.TRAINER_1_AURORA_VEIL_TURNS if def_is_t1 else FieldIdx.TRAINER_2_AURORA_VEIL_TURNS]
    scr_on = (
        (is_phys_pair & ((refl_t > 0.0) | (veil_t > 0.0)).unsqueeze(-1).unsqueeze(-1).unsqueeze(-1))
        | ((~is_phys_pair) & ((lscr_t > 0.0) | (veil_t > 0.0)).unsqueeze(-1).unsqueeze(-1).unsqueeze(-1))
    ) & (att_ab.unsqueeze(-1) != float(AbilityID.INFILTRATOR))
    scr_mult = torch.where(scr_on, torch.full_like(bp_pair, 0.667), torch.ones_like(bp_pair))

    lo_mult = torch.where(
        att_it_on & (att_it == float(ItemID.LIFE_ORB)), torch.full_like(bp_eff, 1.3), torch.ones_like(bp_eff)
    ).unsqueeze(-1)
    gr_mult = torch.where(
        p_def[..., MonIdx.GLAIVE_RUSH_VULN].unsqueeze(-2).unsqueeze(-2) > 0.5,
        torch.full_like(type_eff, 2.0),
        torch.ones_like(type_eff),
    )
    def_mod = torch.where(
        (def_ab == float(AbilityID.MULTISCALE))
        & (p_def[..., MonIdx.HP_CUR].unsqueeze(-2).unsqueeze(-2) >= p_def[..., MonIdx.HP_MAX].unsqueeze(-2).unsqueeze(-2)),
        torch.full_like(type_eff, 0.5),
        torch.ones_like(type_eff),
    )
    def_mod = torch.where((def_ab == float(AbilityID.SOLID_ROCK)) & (type_eff > 1.0), def_mod * 0.75, def_mod)
    def_mod = torch.where((def_ab == float(AbilityID.AURA_GUARD)) & is_contact_pair, def_mod * 0.5, def_mod)
    # Intact Disguise caps immediate single-hit lethal threat at 1/8 HP
    disg_intact = (def_ab == float(AbilityID.DISGUISE)) & (p_def[..., MonIdx.DISGUISE_INTACT].unsqueeze(-2).unsqueeze(-2) > 0.5)

    est_hp_dmg = (((22.0 * bp_pair * (A / D)) / 50.0) + 2.0) * 0.925 * stab_mult * type_eff * w_mult * t_mult * burn_pen * scr_mult * lo_mult * gr_mult * def_mod
    def_hp_cur = torch.clamp(p_def[..., MonIdx.HP_CUR].unsqueeze(-2).unsqueeze(-2), min=1.0)
    dmg_frac = torch.clamp(est_hp_dmg / def_hp_cur, min=0.0, max=1.25)
    dmg_frac = torch.where(disg_intact & (dmg_frac > 0.125), torch.full_like(dmg_frac, 0.125), dmg_frac)
    dmg_frac = torch.where(legal_dmg_move.unsqueeze(-1), dmg_frac, torch.zeros_like(dmg_frac))

    # Speed / priority coupling [..., 2, 4, 2]
    att_ord_spe = (s_eff_8[..., list(att_slots)] * tr_sign.unsqueeze(-1)).unsqueeze(-1).unsqueeze(-1)
    def_ord_spe = (s_eff_8[..., list(def_slots)] * tr_sign.unsqueeze(-1)).unsqueeze(-2).unsqueeze(-2)
    faster = (eff_prio_pair > 0.0) | (att_ord_spe > def_ord_spe)
    tied = (~faster) & (att_ord_spe == def_ord_spe)
    spe_weight = torch.where(faster, torch.ones_like(dmg_frac), torch.where(tied, torch.full_like(dmg_frac, 0.68), torch.full_like(dmg_frac, 0.48)))

    weighted_dmg = dmg_frac * spe_weight
    best_weighted = torch.max(weighted_dmg, dim=-2).values   # [..., 2(att), 2(def)]
    best_raw = torch.max(dmg_frac, dim=-2).values            # [..., 2(att), 2(def)]

    pair_mask = att_alive.unsqueeze(-1) * def_alive.unsqueeze(-2)
    best_weighted = best_weighted * pair_mask
    best_raw = best_raw * pair_mask
    max_legal_per_att = torch.max(best_raw, dim=-1).values   # [..., 2]

    return best_weighted, best_raw, max_legal_per_att, role_summary


def compute_victory_equity_torch(
    F_eot: "torch.Tensor",
    P_eot: "torch.Tensor",
    M_moves: Optional["torch.Tensor"] = None,
    tables: Optional[BilinearLookupTables] = None,
    extra_volatiles: Optional[Dict[str, "torch.Tensor"]] = None,
    weights: Optional[VictoryEquityWeights] = None,
    return_breakdown: bool = False,
) -> Union["torch.Tensor", Tuple["torch.Tensor", VictoryEquityBreakdown]]:
    """Evaluate strictly zero-sum 8-pillar Victory Equity `U[B1, B2, K]` for `trainer_1` vs `trainer_2`.

    When `M_moves` is provided, computes the full `2x2` Active Lethal Threat + `2x2` Bench Escape
    Mal-Positioning Tensor and moveset-aware option restrictions. When `M_moves` is `None`,
    gracefully falls back to speed-initiative and roster-only approximations.
    """
    w = weights if weights is not None else VictoryEquityWeights()
    device = P_eot.device

    hp_cur = P_eot[:, :, :, :, MonIdx.HP_CUR]
    hp_max = torch.clamp(P_eot[:, :, :, :, MonIdx.HP_MAX], min=1.0)
    hp_frac = torch.clamp(hp_cur / hp_max, min=0.0, max=1.0)
    alive = (hp_cur > 0.0).float()

    # -------------------------------------------------------------------------
    # PILLAR 1: MATERIAL (HP% + Alive Count + Terminal Wipe)
    # -------------------------------------------------------------------------
    t1_hp_sum = torch.sum(hp_frac[:, :, :, 0:4], dim=-1)
    t2_hp_sum = torch.sum(hp_frac[:, :, :, 4:8], dim=-1)
    t1_alive_sum = torch.sum(alive[:, :, :, 0:4], dim=-1)
    t2_alive_sum = torch.sum(alive[:, :, :, 4:8], dim=-1)

    phi_hp = t1_hp_sum - t2_hp_sum
    phi_alive = t1_alive_sum - t2_alive_sum
    phi_term = (
        torch.where(t2_alive_sum <= 0.0, torch.ones_like(phi_hp), torch.zeros_like(phi_hp))
        - torch.where(t1_alive_sum <= 0.0, torch.ones_like(phi_hp), torch.zeros_like(phi_hp))
    )
    pillar_material = w.w_hp * phi_hp + w.w_alive * phi_alive + w.w_terminal * phi_term

    # -------------------------------------------------------------------------
    # SHARED EFFECTIVE SPEEDS & WEATHER / TERRAIN CONTEXT
    # -------------------------------------------------------------------------
    abil_8 = P_eot[:, :, :, :, MonIdx.ABILITY_ID]
    act_slots_idx = [SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_2_A, SLOT_TRAINER_2_B]
    cloud_nine_on = torch.any(
        (alive[:, :, :, act_slots_idx] > 0.5) & (abil_8[:, :, :, act_slots_idx] == float(AbilityID.CLOUD_NINE)),
        dim=-1,
        keepdim=True,
    )
    no_c9 = (~cloud_nine_on).float()
    w_raw_idx = torch.argmax(F_eot[:, :, :, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END], dim=-1)
    w_idx_eff = torch.where(cloud_nine_on.squeeze(-1), torch.zeros_like(w_raw_idx), w_raw_idx)
    tr_idx = torch.argmax(F_eot[:, :, :, FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END], dim=-1)

    w_sun = F_eot[:, :, :, FieldIdx.WEATHER_START + W_SUN].unsqueeze(-1) * no_c9
    w_rain = F_eot[:, :, :, FieldIdx.WEATHER_START + W_RAIN].unsqueeze(-1) * no_c9
    w_sand = F_eot[:, :, :, FieldIdx.WEATHER_START + W_SAND].unsqueeze(-1) * no_c9
    w_snow = F_eot[:, :, :, FieldIdx.WEATHER_START + W_SNOW].unsqueeze(-1) * no_c9
    t_elec = F_eot[:, :, :, FieldIdx.TERRAIN_START + T_ELECTRIC].unsqueeze(-1)
    t_grassy = F_eot[:, :, :, FieldIdx.TERRAIN_START + T_GRASSY].unsqueeze(-1)
    t_psychic = F_eot[:, :, :, FieldIdx.TERRAIN_START + T_PSYCHIC].unsqueeze(-1)

    t1_tw_turns = torch.clamp(F_eot[:, :, :, FieldIdx.TRAINER_1_TAILWIND_TURNS], min=0.0, max=4.0)
    t2_tw_turns = torch.clamp(F_eot[:, :, :, FieldIdx.TRAINER_2_TAILWIND_TURNS], min=0.0, max=4.0)
    t1_tw = (t1_tw_turns > 0.0).float()
    t2_tw = (t2_tw_turns > 0.0).float()

    base_spe_8 = P_eot[:, :, :, :, MonIdx.STAT_SPE]
    s1_8 = torch.floor(base_spe_8 * _stage_mult(P_eot[:, :, :, :, MonIdx.BOOST_SPE]))
    w_spe_gate = torch.clamp(
        ((abil_8 == float(AbilityID.CHLOROPHYLL)).float() * w_sun)
        + ((abil_8 == float(AbilityID.SWIFT_SWIM)).float() * w_rain)
        + ((abil_8 == float(AbilityID.SAND_RUSH)).float() * w_sand)
        + ((abil_8 == float(AbilityID.SLUSH_RUSH)).float() * w_snow)
        + ((abil_8 == float(AbilityID.SURGE_SURFER)).float() * t_elec),
        0.0,
        1.0,
    )
    unb_8 = P_eot[:, :, :, :, MonIdx.UNBURDEN_ACTIVE]
    qf_8 = ((abil_8 == float(AbilityID.QUICK_FEET)).float()) * torch.clamp(1.0 - P_eot[:, :, :, :, MonIdx.STATUS_HEALTHY], 0.0, 1.0)
    s2_8 = torch.floor(s1_8 * (1.0 + w_spe_gate) * (1.0 + unb_8) * (1.0 + 0.5 * qf_8))
    is_scarf_8 = ((P_eot[:, :, :, :, MonIdx.ITEM_ID] == float(ItemID.CHOICE_SCARF)).float()) * P_eot[:, :, :, :, MonIdx.ITEM_ACTIVE]
    is_iron_ball_8 = ((P_eot[:, :, :, :, MonIdx.ITEM_ID] == float(ItemID.IRON_BALL)).float()) * P_eot[:, :, :, :, MonIdx.ITEM_ACTIVE]
    s3_8 = torch.floor(s2_8 * (1.0 + 0.5 * is_scarf_8) * (1.0 - 0.5 * is_iron_ball_8))
    tw_8 = torch.cat([t1_tw.unsqueeze(-1).expand(-1, -1, -1, 4), t2_tw.unsqueeze(-1).expand(-1, -1, -1, 4)], dim=-1)
    s4_8 = torch.floor(s3_8 * (1.0 + tw_8))
    para_8 = P_eot[:, :, :, :, MonIdx.STATUS_PARALYZE] * (1.0 - qf_8)
    s_eff_8 = torch.floor(s4_8 * (1.0 - 0.5 * para_8))

    tr_turns = torch.clamp(F_eot[:, :, :, FieldIdx.TRICK_ROOM_TURNS], min=0.0, max=5.0)
    tr_active = (tr_turns > 0.0).float()
    tr_sign = 1.0 - 2.0 * tr_active  # +1 normal, -1 Trick Room
    ordered_spe_8 = s_eff_8 * tr_sign.unsqueeze(-1)

    t1_act_spe = ordered_spe_8[:, :, :, 0:2].unsqueeze(-1)
    t2_act_spe = ordered_spe_8[:, :, :, 4:6].unsqueeze(-2)
    pair_alive = alive[:, :, :, 0:2].unsqueeze(-1) * alive[:, :, :, 4:6].unsqueeze(-2)
    speed_pair_sign = torch.sum(torch.sign(t1_act_spe - t2_act_spe) * pair_alive, dim=(-2, -1))

    # -------------------------------------------------------------------------
    # PILLARS 2 & 3: LETHAL THREAT + ENEMY MAL-POSITIONING & BENCH ESCAPE AUDIT
    # -------------------------------------------------------------------------
    if M_moves is not None:
        type_chart, w_chart, t_chart = _get_type_chart_on_device(device, tables)
        t1_to_t2_w, t1_to_t2_raw, t1_max_out, t1_roles = _compute_directional_threat_matrix_torch(
            F_eot, P_eot, M_moves, (0, 1), (4, 5), s_eff_8, tr_sign, w_idx_eff, tr_idx, False, type_chart, w_chart, t_chart
        )
        t2_to_t1_w, t2_to_t1_raw, t2_max_out, t2_roles = _compute_directional_threat_matrix_torch(
            F_eot, P_eot, M_moves, (4, 5), (0, 1), s_eff_8, tr_sign, w_idx_eff, tr_idx, True, type_chart, w_chart, t_chart
        )
        # Bench escape audits (threat onto alive bench slots)
        _, t1_to_t2b_raw, _, _ = _compute_directional_threat_matrix_torch(
            F_eot, P_eot, M_moves, (0, 1), (6, 7), s_eff_8, tr_sign, w_idx_eff, tr_idx, False, type_chart, w_chart, t_chart
        )
        _, t2_to_t1b_raw, _, _ = _compute_directional_threat_matrix_torch(
            F_eot, P_eot, M_moves, (4, 5), (2, 3), s_eff_8, tr_sign, w_idx_eff, tr_idx, True, type_chart, w_chart, t_chart
        )

        # Lethal pins + focus-fire OHKO bonus
        t1_fast_ohko = (t1_to_t2_w >= 0.90).float().sum(dim=(-2, -1)) * 0.25
        t2_fast_ohko = (t2_to_t1_w >= 0.90).float().sum(dim=(-2, -1)) * 0.25
        t1_focus_ko = (t1_to_t2_raw.sum(dim=-2) >= 1.0).float() * alive[:, :, :, 4:6]
        t2_focus_ko = (t2_to_t1_raw.sum(dim=-2) >= 1.0).float() * alive[:, :, :, 0:2]
        t1_threat_s = 0.40 * t1_to_t2_w.sum(dim=(-2, -1)) + t1_fast_ohko + 0.18 * t1_focus_ko.sum(dim=-1)
        t2_threat_s = 0.40 * t2_to_t1_w.sum(dim=(-2, -1)) + t2_fast_ohko + 0.18 * t2_focus_ko.sum(dim=-1)
        phi_threat = t1_threat_s - t2_threat_s + 0.15 * speed_pair_sign

        # Mal-Positioning & Bench Escape Safety
        t2_in_on_act = torch.max(t1_to_t2_w, dim=-2).values          # [..., 2]
        t1_in_on_act = torch.max(t2_to_t1_w, dim=-2).values          # [..., 2]
        t2_in_raw_act = torch.max(t1_to_t2_raw, dim=-2).values       # [..., 2]
        t1_in_raw_act = torch.max(t2_to_t1_raw, dim=-2).values       # [..., 2]

        t2_b_in = torch.max(t1_to_t2b_raw, dim=-2).values            # [..., 2]
        t1_b_in = torch.max(t2_to_t1b_raw, dim=-2).values            # [..., 2]
        t2_escape = torch.max(alive[:, :, :, 6:8] * torch.clamp(1.0 - t2_b_in, 0.0, 1.0), dim=-1).values
        t1_escape = torch.max(alive[:, :, :, 2:4] * torch.clamp(1.0 - t1_b_in, 0.0, 1.0), dim=-1).values

        t2_trapped = (alive[:, :, :, 4:6] * torch.clamp(t2_in_on_act - t2_max_out, 0.0, 1.0)).sum(dim=-1) * (1.0 - 0.65 * t2_escape)
        t1_trapped = (alive[:, :, :, 0:2] * torch.clamp(t1_in_on_act - t1_max_out, 0.0, 1.0)).sum(dim=-1) * (1.0 - 0.65 * t1_escape)
        phi_malpos = t2_trapped - t1_trapped

        # Move role tensors for all 8 slots (Physical/Special/Status/Sound + Stomping Tantrum / Electric / Fake Out)
        m_bp_8 = M_moves[:, :, :, :, :, MoveIdx.BASE_POWER]
        m_ph_8 = (M_moves[:, :, :, :, :, MoveIdx.CAT_PHYSICAL] > 0.5) & (m_bp_8 > 0.0)
        m_sp_8 = (M_moves[:, :, :, :, :, MoveIdx.CAT_SPECIAL] > 0.5) & (m_bp_8 > 0.0)
        m_st_8 = M_moves[:, :, :, :, :, MoveIdx.CAT_STATUS] > 0.5
        m_valid_8 = torch.clamp((m_ph_8 | m_sp_8 | m_st_8).float().sum(dim=-1), min=1.0)
        phys_frac_8 = m_ph_8.float().sum(dim=-1) / m_valid_8
        spec_frac_8 = m_sp_8.float().sum(dim=-1) / m_valid_8
        stat_frac_8 = m_st_8.float().sum(dim=-1) / m_valid_8
        has_sound_8 = (M_moves[:, :, :, :, :, MoveIdx.IS_SOUND_MOVE] > 0.5).any(dim=-1).float()
        fop_8 = torch.round(M_moves[:, :, :, :, :, MoveIdx.FIELD_OP_ID]).long()
        has_tantrum_8 = (fop_8 == int(FieldOpID.STOMPING_TANTRUM)).any(dim=-1).float()
        has_elec_dmg_8 = ((M_moves[:, :, :, :, :, MoveIdx.TYPE_START + TYPE_TO_IDX["electric"]] > 0.5) & (m_bp_8 > 0.0)).any(dim=-1).float()
        has_fake_out_8 = ((fop_8 == int(FieldOpID.FAKE_OUT)) | (M_moves[:, :, :, :, :, MoveIdx.FIRST_TURN_ONLY] > 0.5)).any(dim=-1).float()
    else:
        phi_threat = 0.20 * speed_pair_sign
        phi_malpos = torch.zeros_like(phi_hp)
        t1_max_out = torch.ones((P_eot.shape[0], P_eot.shape[1], P_eot.shape[2], 2), dtype=torch.float32, device=device)
        t2_max_out = torch.ones_like(t1_max_out)
        t1_in_raw_act = torch.zeros_like(t1_max_out)
        t2_in_raw_act = torch.zeros_like(t1_max_out)
        phys_frac_8 = torch.full_like(alive, 0.5)
        spec_frac_8 = torch.full_like(alive, 0.5)
        stat_frac_8 = torch.full_like(alive, 0.25)
        has_sound_8 = torch.zeros_like(alive)
        has_tantrum_8 = torch.zeros_like(alive)
        has_elec_dmg_8 = torch.zeros_like(alive)
        has_fake_out_8 = torch.zeros_like(alive)

    pillar_threat = w.w_threat * phi_threat
    pillar_malpos = w.w_malposition * phi_malpos

    # -------------------------------------------------------------------------
    # PILLAR 4: ROLE-AWARE OPTION RESTRICTION & LOCK-IN
    # -------------------------------------------------------------------------
    def _side_restriction(slots: slice, max_out: "torch.Tensor", in_raw: "torch.Tensor") -> "torch.Tensor":
        alv = alive[:, :, :, slots]
        ch_lck = (P_eot[:, :, :, slots, MonIdx.CHOICE_LOCKED_MOVE] >= 0.0).float()
        # Choice-locked into 0x immunity (0.85) or resisted (<0.25 dmg, 0.40)
        ch_trap = ch_lck * torch.where(max_out <= 1e-4, torch.full_like(max_out, 0.85), torch.where(max_out < 0.25, torch.full_like(max_out, 0.40), torch.zeros_like(max_out)))
        # Protect-streak exposure when facing high lethal threat next turn
        prot_exp = ((P_eot[:, :, :, slots, MonIdx.PROTECT_COUNTER] >= 1.0).float()) * torch.clamp((in_raw - 0.55) * 1.4, 0.0, 0.70)
        # Role-aware Taunt, Throat Chop, Encore, Recharge, Yawn
        taunt_pen = (P_eot[:, :, :, slots, MonIdx.TAUNT_TURNS] > 0.0).float() * (0.20 + 0.80 * stat_frac_8[:, :, :, slots])
        tc_pen = (P_eot[:, :, :, slots, MonIdx.THROAT_CHOP_TURNS] > 0.0).float() * (0.15 + 0.55 * has_sound_8[:, :, :, slots])
        enc_pen = (P_eot[:, :, :, slots, MonIdx.ENCORE_TURNS] > 0.0).float() * 0.65
        rech_pen = (P_eot[:, :, :, slots, MonIdx.MUST_RECHARGE] > 0.5).float() * 1.25
        yawn_pen = (P_eot[:, :, :, slots, MonIdx.YAWN_ACTIVE] > 0.5).float() * 0.55
        return torch.sum((ch_trap + prot_exp + taunt_pen + tc_pen + enc_pen + rech_pen + yawn_pen) * alv, dim=-1)

    phi_restrict = _side_restriction(slice(4, 6), t2_max_out, t2_in_raw_act) - _side_restriction(slice(0, 2), t1_max_out, t1_in_raw_act)
    if extra_volatiles:
        for v_key, v_weight in (
            ("leech_seed_src", 0.50),
            ("salt_cured", 0.50),
            ("disabled", 0.35),
            ("perish_song", 0.25),
        ):
            v_tens = extra_volatiles.get(v_key)
            if v_tens is not None:
                v_mask = (v_tens > 0.5).float() * alive
                phi_restrict = phi_restrict + v_weight * (
                    torch.sum(v_mask[:, :, :, 4:6], dim=-1) - torch.sum(v_mask[:, :, :, 0:2], dim=-1)
                )
    pillar_restrict = w.w_restriction * phi_restrict

    # -------------------------------------------------------------------------
    # PILLAR 5: ROLE-AWARE STATUS & HP-SCALED STAT BOOSTS
    # -------------------------------------------------------------------------
    is_guts_8 = (abil_8 == float(AbilityID.GUTS)).float()
    burn_sev = P_eot[:, :, :, :, MonIdx.STATUS_BURN] * (0.25 + 0.65 * phys_frac_8) * (1.0 - is_guts_8)
    para_sev = P_eot[:, :, :, :, MonIdx.STATUS_PARALYZE] * (0.75 * (1.0 - 0.55 * tr_active.unsqueeze(-1))) * (1.0 - qf_8)
    slp_frz_sev = (P_eot[:, :, :, :, MonIdx.STATUS_SLEEP] + P_eot[:, :, :, :, MonIdx.STATUS_FREEZE]) * 1.00
    tox_psn_sev = P_eot[:, :, :, :, MonIdx.STATUS_TOXIC] * 0.55 + P_eot[:, :, :, :, MonIdx.STATUS_POISON] * 0.35
    status_sev_8 = (burn_sev + para_sev + slp_frz_sev + tox_psn_sev) * alive
    phi_status = torch.sum(status_sev_8[:, :, :, 4:8], dim=-1) - torch.sum(status_sev_8[:, :, :, 0:4], dim=-1)

    hp_scale_8 = 0.50 + 0.50 * hp_frac
    b_atk = P_eot[:, :, :, :, MonIdx.BOOST_ATK] * (0.35 + 0.85 * phys_frac_8)
    b_def = P_eot[:, :, :, :, MonIdx.BOOST_DEF] * 0.55
    b_spa = P_eot[:, :, :, :, MonIdx.BOOST_SPA] * (0.35 + 0.85 * spec_frac_8)
    b_spd = P_eot[:, :, :, :, MonIdx.BOOST_SPD] * 0.55
    b_spe = P_eot[:, :, :, :, MonIdx.BOOST_SPE] * (1.00 * tr_sign.unsqueeze(-1))
    boost_score_8 = (b_atk + b_def + b_spa + b_spd + b_spe) * alive * hp_scale_8
    phi_boost = torch.sum(boost_score_8[:, :, :, 0:2], dim=-1) - torch.sum(boost_score_8[:, :, :, 4:6], dim=-1)
    pillar_status_boost = w.w_status * phi_status + w.w_boost * phi_boost

    # -------------------------------------------------------------------------
    # PILLAR 6: HP-GATED 2-TURN PRIMED PAYOFFS
    # -------------------------------------------------------------------------
    tantrum_primed_8 = (P_eot[:, :, :, :, MonIdx.LAST_MOVE_FAILED] > 0.5).float() * has_tantrum_8 * 0.75
    charged_ready_8 = (P_eot[:, :, :, :, MonIdx.CHARGED_MOVE_IDX] > 0.5).float() * 0.85 + (P_eot[:, :, :, :, MonIdx.SEMI_INVULN] > 0.5).float() * 0.25
    charge_elec_8 = (P_eot[:, :, :, :, MonIdx.CHARGE_ACTIVE] > 0.5).float() * has_elec_dmg_8 * 0.60
    glaive_pen_8 = (P_eot[:, :, :, :, MonIdx.GLAIVE_RUSH_VULN] > 0.5).float() * (-0.70)
    prime_8 = (tantrum_primed_8 + charged_ready_8 + charge_elec_8 + glaive_pen_8) * alive * hp_frac
    phi_prime = torch.sum(prime_8[:, :, :, 0:2], dim=-1) - torch.sum(prime_8[:, :, :, 4:6], dim=-1)
    pillar_prime = w.w_two_turn_prime * phi_prime

    # -------------------------------------------------------------------------
    # PILLAR 7: SHIELD THRESHOLDS & RESOURCE ECONOMY
    # -------------------------------------------------------------------------
    full_hp_8 = (hp_frac >= 0.999).float()
    it_on_8 = (P_eot[:, :, :, :, MonIdx.ITEM_ACTIVE] > 0.5).float()
    it_id_8 = P_eot[:, :, :, :, MonIdx.ITEM_ID]
    sash_intact_8 = it_on_8 * (it_id_8 == float(ItemID.FOCUS_SASH)).float() * full_hp_8 * 0.60
    disg_shield_8 = (abil_8 == float(AbilityID.DISGUISE)).float() * (P_eot[:, :, :, :, MonIdx.DISGUISE_INTACT] > 0.5).float() * 0.70
    ms_st_8 = ((abil_8 == float(AbilityID.MULTISCALE)) | (abil_8 == float(AbilityID.STURDY))).float() * full_hp_8 * 0.45
    def_item_8 = it_on_8 * (
        (it_id_8 == float(ItemID.SITRUS_BERRY))
        | (it_id_8 == float(ItemID.WHITE_HERB))
        | (it_id_8 == float(ItemID.MENTAL_HERB))
        | (it_id_8 == float(ItemID.LUM_BERRY))
    ).float() * 0.22
    res_mon_8 = (sash_intact_8 + disg_shield_8 + ms_st_8 + def_item_8) * alive

    t1_mega_avail = (torch.any((alive[:, :, :, 0:4] > 0.5) & (P_eot[:, :, :, 0:4, MonIdx.CAN_MEGA] > 0.5), dim=-1).float()) * (1.0 - F_eot[:, :, :, FieldIdx.TRAINER_1_MEGA_USED])
    t2_mega_avail = (torch.any((alive[:, :, :, 4:8] > 0.5) & (P_eot[:, :, :, 4:8, MonIdx.CAN_MEGA] > 0.5), dim=-1).float()) * (1.0 - F_eot[:, :, :, FieldIdx.TRAINER_2_MEGA_USED])

    # Active Turn-1 Fake Out pressure (when opp lacks Armor Tail/Queenly Majesty and no Psychic Terrain)
    t2_prio_block = torch.any((alive[:, :, :, 4:6] > 0.5) & ((abil_8[:, :, :, 4:6] == float(AbilityID.ARMOR_TAIL)) | (abil_8[:, :, :, 4:6] == float(AbilityID.QUEENLY_MAJESTY))), dim=-1).float()
    t1_prio_block = torch.any((alive[:, :, :, 0:2] > 0.5) & ((abil_8[:, :, :, 0:2] == float(AbilityID.ARMOR_TAIL)) | (abil_8[:, :, :, 0:2] == float(AbilityID.QUEENLY_MAJESTY))), dim=-1).float()
    no_psy_t = 1.0 - t_psychic.squeeze(-1)
    t1_fo_ready = torch.sum((P_eot[:, :, :, 0:2, MonIdx.ACTIVE_TURNS] <= 0.0).float() * has_fake_out_8[:, :, :, 0:2] * alive[:, :, :, 0:2], dim=-1) * (1.0 - t2_prio_block) * no_psy_t
    t2_fo_ready = torch.sum((P_eot[:, :, :, 4:6, MonIdx.ACTIVE_TURNS] <= 0.0).float() * has_fake_out_8[:, :, :, 4:6] * alive[:, :, :, 4:6], dim=-1) * (1.0 - t1_prio_block) * no_psy_t

    phi_resources = (
        torch.sum(res_mon_8[:, :, :, 0:4], dim=-1)
        - torch.sum(res_mon_8[:, :, :, 4:8], dim=-1)
        + 0.45 * (t1_mega_avail - t2_mega_avail)
        + 0.30 * (t1_fo_ready - t2_fo_ready)
    )
    pillar_resources = w.w_resources * phi_resources

    # -------------------------------------------------------------------------
    # PILLAR 8: FIELD TEMPO, REMAINING TURNS & ENTRY HAZARDS
    # -------------------------------------------------------------------------
    t1_scr_turns = torch.clamp(
        torch.maximum(
            torch.maximum(F_eot[:, :, :, FieldIdx.TRAINER_1_REFLECT_TURNS], F_eot[:, :, :, FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS]),
            F_eot[:, :, :, FieldIdx.TRAINER_1_AURORA_VEIL_TURNS],
        ),
        0.0,
        5.0,
    )
    t2_scr_turns = torch.clamp(
        torch.maximum(
            torch.maximum(F_eot[:, :, :, FieldIdx.TRAINER_2_REFLECT_TURNS], F_eot[:, :, :, FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS]),
            F_eot[:, :, :, FieldIdx.TRAINER_2_AURORA_VEIL_TURNS],
        ),
        0.0,
        5.0,
    )
    tw_term = 1.15 * ((t1_tw_turns - t2_tw_turns) / 4.0)
    scr_term = 0.65 * ((t1_scr_turns - t2_scr_turns) / 5.0)
    # Trick Room value scaled by remaining turns and who benefits from reversed speed
    tr_term = (tr_turns / 5.0) * 0.25 * speed_pair_sign

    def _has_type(t_name: str) -> "torch.Tensor":
        t_i = TYPE_TO_IDX[t_name]
        return torch.clamp(P_eot[:, :, :, :, MonIdx.TYPE1_START + t_i] + P_eot[:, :, :, :, MonIdx.TYPE2_START + t_i], 0.0, 1.0)

    is_fire = _has_type("fire")
    is_water = _has_type("water")
    is_rock_gnd_stl = torch.clamp(_has_type("rock") + _has_type("ground") + _has_type("steel"), 0.0, 1.0)
    is_ice = _has_type("ice")
    is_elec = _has_type("electric")
    is_grass = _has_type("grass")
    is_psychic = _has_type("psychic")
    grounded_8 = P_eot[:, :, :, :, MonIdx.GROUNDED_FLAG]

    sun_syn = w_sun * (is_fire + (abil_8 == float(AbilityID.SOLAR_POWER)).float() + (abil_8 == float(AbilityID.CHLOROPHYLL)).float() + 0.4 * (abil_8 == float(AbilityID.LEAF_GUARD)).float() - 0.5 * is_water - 0.6 * (abil_8 == float(AbilityID.DRY_SKIN)).float())
    rain_syn = w_rain * (is_water + (abil_8 == float(AbilityID.SWIFT_SWIM)).float() + 0.6 * (abil_8 == float(AbilityID.DRY_SKIN)).float() + 0.4 * (abil_8 == float(AbilityID.RAIN_DISH)).float() + 0.4 * (abil_8 == float(AbilityID.HYDRATION)).float() - 0.5 * is_fire)
    sand_syn = w_sand * (0.6 * is_rock_gnd_stl + (abil_8 == float(AbilityID.SAND_RUSH)).float() + 0.6 * (abil_8 == float(AbilityID.SAND_FORCE)).float())
    snow_syn = w_snow * (0.9 * is_ice + (abil_8 == float(AbilityID.SLUSH_RUSH)).float() + 0.4 * (abil_8 == float(AbilityID.ICE_BODY)).float())
    terr_syn = grounded_8 * (t_elec * (0.8 * is_elec + (abil_8 == float(AbilityID.SURGE_SURFER)).float()) + t_grassy * (0.8 * is_grass) + t_psychic * (0.8 * is_psychic))
    mon_syn = (sun_syn + rain_syn + sand_syn + snow_syn + terr_syn) * alive
    syn_term = 0.30 * (torch.sum(mon_syn[:, :, :, 0:4], dim=-1) - torch.sum(mon_syn[:, :, :, 4:8], dim=-1))

    is_psn_or_stl = torch.clamp(_has_type("poison") + _has_type("steel"), 0.0, 1.0)
    bench_vuln = alive * grounded_8 * (1.0 - is_psn_or_stl) * P_eot[:, :, :, :, MonIdx.STATUS_HEALTHY]
    tspikes_term = 0.25 * (
        F_eot[:, :, :, FieldIdx.TRAINER_2_TOXIC_SPIKES] * torch.sum(bench_vuln[:, :, :, 6:8], dim=-1)
        - F_eot[:, :, :, FieldIdx.TRAINER_1_TOXIC_SPIKES] * torch.sum(bench_vuln[:, :, :, 2:4], dim=-1)
    )

    phi_field = tw_term + scr_term + tr_term + syn_term + tspikes_term
    pillar_field = w.w_field_tempo * phi_field

    total = (
        pillar_material
        + pillar_threat
        + pillar_malpos
        + pillar_restrict
        + pillar_status_boost
        + pillar_prime
        + pillar_resources
        + pillar_field
    )

    if not return_breakdown:
        return total

    def _m(t: "torch.Tensor") -> float:
        return float(torch.mean(t).item())

    breakdown = VictoryEquityBreakdown(
        material=_m(pillar_material),
        threat=_m(pillar_threat),
        malposition=_m(pillar_malpos),
        restriction=_m(pillar_restrict),
        status_boost=_m(pillar_status_boost),
        two_turn_prime=_m(pillar_prime),
        resources=_m(pillar_resources),
        field_tempo=_m(pillar_field),
        total=_m(total),
        phi_raw={
            "hp": _m(phi_hp),
            "alive": _m(phi_alive),
            "terminal": _m(phi_term),
            "threat": _m(phi_threat),
            "malposition": _m(phi_malpos),
            "restriction": _m(phi_restrict),
            "status": _m(phi_status),
            "boost": _m(phi_boost),
            "two_turn_prime": _m(phi_prime),
            "resources": _m(phi_resources),
            "field_tempo": _m(phi_field),
        },
    )
    return total, breakdown
