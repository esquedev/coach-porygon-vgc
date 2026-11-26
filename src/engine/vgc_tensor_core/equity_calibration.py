# -*- coding: utf-8 -*-
"""Canonical Regulation M-C Tactical Calibration Puzzle Suite for 8-Pillar Victory Equity.

Pure-domain verification harness shared by Acceptance Gate `TestAT-10` and the offline
Texel/TD weight tuner (`scripts/tune_equity_weights.py`). Ensures any candidate
`VictoryEquityWeights` vector preserves exact zero-sum antisymmetry, KO-anchored
material dominance, and all core VGC doubles tactical invariants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from engine.db_registry import get_registry
from engine.sp_validator import validate_and_calculate_sp
from .compiler import ShowdownTensorCompiler
from .schema_and_tables import (
    FieldIdx,
    HAS_TORCH,
    MonIdx,
    build_bilinear_lookup_tables,
)
from .victory_equity import (
    VictoryEquityWeights,
    compute_victory_equity_torch,
)

if HAS_TORCH:
    import torch
else:
    torch = None  # type: ignore


@dataclass(frozen=True)
class CalibrationPuzzleResult:
    """Outcome of a single tactical calibration puzzle."""

    name: str
    passed: bool
    detail: str


def _make_mon_spec(
    reg: Any,
    species: str,
    item: str,
    ability: str,
    nature: str,
    moves: List[str],
    hp_sp: int = 2,
    atk_sp: int = 32,
    def_sp: int = 0,
    spa_sp: int = 0,
    spd_sp: int = 0,
    spe_sp: int = 32,
    hp_pct: float = 100.0,
) -> Dict[str, Any]:
    """Build an authentic DuckDB-grounded Regulation M-C slot spec with exact 66-SP Lv.50 stats."""
    sp_dict = {
        "hp": hp_sp,
        "atk": atk_sp,
        "def": def_sp,
        "spa": spa_sp,
        "spd": spd_sp,
        "spe": spe_sp,
    }
    _ok, _msg, l50 = validate_and_calculate_sp(species, sp_dict, nature)
    row = reg.get_pokemon(species) or {}
    types = list(row.get("types") or ["Normal"])
    hp_max = float(l50.get("hp", 180))
    hp_cur = max(0.0, hp_max * float(hp_pct) / 100.0)
    return {
        "species": species,
        "item": item,
        "ability": ability,
        "moves": list(moves),
        "hp_cur": hp_cur,
        "hp_max": hp_max,
        "stats": {
            "atk": float(l50.get("atk", 120)),
            "def": float(l50.get("def", 100)),
            "spa": float(l50.get("spa", 100)),
            "spd": float(l50.get("spd", 100)),
            "spe": float(l50.get("spe", 100)),
        },
        "types": types,
    }


def _compile_board(
    compiler: ShowdownTensorCompiler,
    t1_mons: List[Dict[str, Any]],
    t2_mons: List[Dict[str, Any]],
) -> Any:
    return compiler.compile_battle_state(t1_mons + t2_mons, field_spec={})


def _eval_scalar(
    F: "torch.Tensor",
    P: "torch.Tensor",
    M: "torch.Tensor",
    tables: Any,
    weights: VictoryEquityWeights,
) -> float:
    val = compute_victory_equity_torch(
        F.view(1, 1, 1, -1),
        P.view(1, 1, 1, 8, -1),
        M_moves=M.view(1, 1, 1, 8, 4, -1),
        tables=tables,
        weights=weights,
        return_breakdown=False,
    )
    return float(val.item())


def _swap_sides(
    F: "torch.Tensor",
    P: "torch.Tensor",
    M: "torch.Tensor",
) -> Tuple["torch.Tensor", "torch.Tensor", "torch.Tensor"]:
    """Swap `trainer_1` (slots `0..3`) and `trainer_2` (slots `4..7`) plus side field channels."""
    F_sw = F.clone()
    side_pairs = (
        (FieldIdx.TRAINER_1_TAILWIND_TURNS, FieldIdx.TRAINER_2_TAILWIND_TURNS),
        (FieldIdx.TRAINER_1_REFLECT_TURNS, FieldIdx.TRAINER_2_REFLECT_TURNS),
        (FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS, FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS),
        (FieldIdx.TRAINER_1_AURORA_VEIL_TURNS, FieldIdx.TRAINER_2_AURORA_VEIL_TURNS),
        (FieldIdx.TRAINER_1_MEGA_USED, FieldIdx.TRAINER_2_MEGA_USED),
        (FieldIdx.TRAINER_1_TOXIC_SPIKES, FieldIdx.TRAINER_2_TOXIC_SPIKES),
    )
    for idx_a, idx_b in side_pairs:
        tmp = F_sw[idx_a].clone()
        F_sw[idx_a] = F_sw[idx_b]
        F_sw[idx_b] = tmp
    perm = torch.tensor([4, 5, 6, 7, 0, 1, 2, 3], dtype=torch.long, device=P.device)
    return F_sw, P[perm].clone(), M[perm].clone()


def verify_victory_equity_puzzles(
    weights: Optional[VictoryEquityWeights] = None,
) -> List[CalibrationPuzzleResult]:
    """Run all 13 canonical Regulation M-C tactical calibration puzzles against `weights`."""
    if not HAS_TORCH:
        raise RuntimeError("PyTorch is required to run Victory Equity calibration puzzles.")

    w = weights if weights is not None else VictoryEquityWeights()
    reg = get_registry()
    dev = torch.device("cpu")
    tables = build_bilinear_lookup_tables(device=dev)
    compiler = ShowdownTensorCompiler(registry=reg, backend="torch", device=dev)

    # Authentic Regulation M-C DuckDB-grounded fixtures (66-SP, 31 IVs)
    garchomp = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Garchomp", "Clear Amulet", "Rough Skin", "Jolly",
        ["Stomping Tantrum", "Dragon Claw", "Rock Slide", "Protect"],
        hp_sp=2, atk_sp=32, spe_sp=32, hp_pct=hp_pct,
    )
    charizard_y = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Charizard-Mega-Y", "Charizardite Y", "Drought", "Timid",
        ["Heat Wave", "Solar Beam", "Air Slash", "Protect"],
        hp_sp=2, atk_sp=0, spa_sp=32, spe_sp=32, hp_pct=hp_pct,
    )
    pelipper = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Pelipper", "Focus Sash", "Drizzle", "Modest",
        ["Weather Ball", "Hurricane", "Tailwind", "Protect"],
        hp_sp=2, atk_sp=0, spa_sp=32, spe_sp=32, hp_pct=hp_pct,
    )
    whimsicott = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Whimsicott", "Covert Cloak", "Prankster", "Timid",
        ["Tailwind", "Encore", "Helping Hand", "Moonblast"],
        hp_sp=32, atk_sp=0, spd_sp=2, spe_sp=32, hp_pct=hp_pct,
    )
    incineroar = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Incineroar", "Sitrus Berry", "Intimidate", "Careful",
        ["Fake Out", "Flare Blitz", "Knock Off", "Parting Shot"],
        hp_sp=32, atk_sp=2, def_sp=16, spd_sp=16, spe_sp=0, hp_pct=hp_pct,
    )
    excadrill = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Excadrill", "Choice Band", "Sand Rush", "Adamant",
        ["Earthquake", "Iron Head", "Rock Slide", "High Horsepower"],
        hp_sp=2, atk_sp=32, spe_sp=32, hp_pct=hp_pct,
    )
    dragapult = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Dragapult", "Life Orb", "Clear Body", "Jolly",
        ["Dragon Darts", "Phantom Force", "U-turn", "Sucker Punch"],
        hp_sp=2, atk_sp=32, spe_sp=32, hp_pct=hp_pct,
    )
    dragonite = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Dragonite", "Loaded Dice", "Multiscale", "Adamant",
        ["Scale Shot", "Extreme Speed", "Low Kick", "Protect"],
        hp_sp=2, atk_sp=32, spe_sp=32, hp_pct=hp_pct,
    )
    mimikyu = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Mimikyu", "Life Orb", "Disguise", "Jolly",
        ["Play Rough", "Shadow Claw", "Shadow Sneak", "Trick Room"],
        hp_sp=2, atk_sp=32, spe_sp=32, hp_pct=hp_pct,
    )
    snorlax = lambda hp_pct=100.0: _make_mon_spec(
        reg, "Snorlax", "Leftovers", "Thick Fat", "Careful",
        ["Facade", "High Horsepower", "Yawn", "Protect"],
        hp_sp=32, atk_sp=2, def_sp=16, spd_sp=16, spe_sp=0, hp_pct=hp_pct,
    )

    results: List[CalibrationPuzzleResult] = []

    # 1. Exact Zero-Sum Antisymmetry under full side swap + asymmetric statuses/field
    c_sym = _compile_board(
        compiler,
        [garchomp(82.0), whimsicott(64.0), charizard_y(100.0), pelipper(100.0)],
        [incineroar(55.0), excadrill(90.0), dragapult(40.0), snorlax(100.0)],
    )
    F_s = c_sym.field_tensor.clone()
    P_s = c_sym.roster_tensor.clone()
    M_s = c_sym.moves_tensor.clone()
    F_s[FieldIdx.TRAINER_1_TAILWIND_TURNS] = 3.0
    F_s[FieldIdx.TRAINER_2_REFLECT_TURNS] = 4.0
    F_s[FieldIdx.TRAINER_2_TOXIC_SPIKES] = 1.0
    P_s[0, MonIdx.LAST_MOVE_FAILED] = 1.0
    P_s[1, MonIdx.TAUNT_TURNS] = 2.0
    P_s[4, MonIdx.STATUS_HEALTHY] = 0.0
    P_s[4, MonIdx.STATUS_BURN] = 1.0
    P_s[5, MonIdx.PROTECT_COUNTER] = 1.0
    P_s[5, MonIdx.YAWN_ACTIVE] = 1.0
    v_fwd = _eval_scalar(F_s, P_s, M_s, tables, w)
    F_sw, P_sw, M_sw = _swap_sides(F_s, P_s, M_s)
    v_rev = _eval_scalar(F_sw, P_sw, M_sw, tables, w)
    anti_err = abs(v_fwd + v_rev)
    results.append(CalibrationPuzzleResult(
        "zero_sum_antisymmetry",
        anti_err < 1e-4,
        f"|V + V_swap|={anti_err:.2e} (V={v_fwd:+.4f}, V_swap={v_rev:+.4f})",
    ))

    # 2. Material Dominance: 4v3 clean KO beats opponent minor Tailwind + boost
    c_mat = _compile_board(
        compiler,
        [garchomp(), incineroar(), charizard_y(), pelipper()],
        [garchomp(), incineroar(), charizard_y(), pelipper()],
    )
    F_m = c_mat.field_tensor.clone()
    P_m = c_mat.roster_tensor.clone()
    P_m[7, MonIdx.HP_CUR] = 0.0
    P_m[7, MonIdx.ALIVE_FLAG] = 0.0
    F_m[FieldIdx.TRAINER_2_TAILWIND_TURNS] = 2.0
    P_m[4, MonIdx.BOOST_ATK] = 1.0
    v_mat = _eval_scalar(F_m, P_m, c_mat.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "material_dominance_ko_over_tempo",
        v_mat > 0.75,
        f"4v3 KO vs opp TW(2t)++1Atk -> V={v_mat:+.4f} (expected > +0.75)",
    ))

    # 3. Speed-Weighted Lethal Threat: faster OHKO threat > slower equal-damage threat
    c_spd = _compile_board(
        compiler,
        [charizard_y(), incineroar(), pelipper(), snorlax()],
        [excadrill(), snorlax(), incineroar(), pelipper()],
    )
    F_fast = c_spd.field_tensor.clone()
    v_fast = _eval_scalar(F_fast, c_spd.roster_tensor, c_spd.moves_tensor, tables, w)
    F_tr = F_fast.clone()
    F_tr[FieldIdx.TRICK_ROOM_TURNS] = 4.0
    v_tr = _eval_scalar(F_tr, c_spd.roster_tensor, c_spd.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "speed_weighted_lethal_threat",
        v_fast > v_tr + 0.03,
        f"Normal speed V={v_fast:+.4f} vs TR reversed V={v_tr:+.4f}",
    ))

    # 4. Mal-Positioning & Bench Escape: trapped foe w/ weak bench > foe w/ safe Ground-immune bench
    c_weak_bench = _compile_board(
        compiler,
        [garchomp(), charizard_y(), incineroar(), snorlax()],
        [excadrill(), incineroar(), excadrill(), incineroar()],
    )
    c_safe_bench = _compile_board(
        compiler,
        [garchomp(), charizard_y(), incineroar(), snorlax()],
        [excadrill(), incineroar(), pelipper(), dragonite()],
    )
    v_weak_b = _eval_scalar(c_weak_bench.field_tensor, c_weak_bench.roster_tensor, c_weak_bench.moves_tensor, tables, w)
    v_safe_b = _eval_scalar(c_safe_bench.field_tensor, c_safe_bench.roster_tensor, c_safe_bench.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "malposition_bench_escape",
        v_weak_b > v_safe_b + 0.02,
        f"Foe weak bench V={v_weak_b:+.4f} vs resistant/immune bench V={v_safe_b:+.4f}",
    ))

    # 5. Choice-Lock into 0x Immunity Trap
    c_ch = _compile_board(
        compiler,
        [pelipper(), dragonite(), garchomp(), incineroar()],
        [excadrill(), incineroar(), garchomp(), snorlax()],
    )
    P_free = c_ch.roster_tensor.clone()
    P_lock = c_ch.roster_tensor.clone()
    P_lock[4, MonIdx.CHOICE_LOCKED_MOVE] = 0.0  # Earthquake vs Pelipper + Dragonite (both Flying!)
    v_free = _eval_scalar(c_ch.field_tensor, P_free, c_ch.moves_tensor, tables, w)
    v_lock = _eval_scalar(c_ch.field_tensor, P_lock, c_ch.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "choice_lock_immunity_trap",
        v_lock > v_free + 0.08,
        f"Foe Choice-locked EQ into 2 Flying V={v_lock:+.4f} vs unlocked V={v_free:+.4f}",
    ))

    # 6. Protect-Streak Lethal Exposure
    c_pr = _compile_board(
        compiler,
        [charizard_y(), garchomp(), pelipper(), snorlax()],
        [excadrill(), incineroar(), pelipper(), snorlax()],
    )
    P_p0 = c_pr.roster_tensor.clone()
    P_p1 = c_pr.roster_tensor.clone()
    P_p1[4, MonIdx.PROTECT_COUNTER] = 1.0
    v_p0 = _eval_scalar(c_pr.field_tensor, P_p0, c_pr.moves_tensor, tables, w)
    v_p1 = _eval_scalar(c_pr.field_tensor, P_p1, c_pr.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "protect_streak_exposure",
        v_p1 > v_p0 + 0.02,
        f"Foe ProtectStreak=1 V={v_p1:+.4f} vs ProtectStreak=0 V={v_p0:+.4f}",
    ))

    # 7. Role-Aware Burn: Burned physical Garchomp penalized strictly more than burned special Charizard-Y
    c_brn = _compile_board(
        compiler,
        [garchomp(), charizard_y(), pelipper(), snorlax()],
        [incineroar(), snorlax(), pelipper(), dragonite()],
    )
    P_brn_base = c_brn.roster_tensor.clone()
    P_brn_phys = P_brn_base.clone()
    P_brn_phys[0, MonIdx.STATUS_HEALTHY] = 0.0
    P_brn_phys[0, MonIdx.STATUS_BURN] = 1.0
    P_brn_spec = P_brn_base.clone()
    P_brn_spec[1, MonIdx.STATUS_HEALTHY] = 0.0
    P_brn_spec[1, MonIdx.STATUS_BURN] = 1.0
    v_base_b = _eval_scalar(c_brn.field_tensor, P_brn_base, c_brn.moves_tensor, tables, w)
    pen_phys = v_base_b - _eval_scalar(c_brn.field_tensor, P_brn_phys, c_brn.moves_tensor, tables, w)
    pen_spec = v_base_b - _eval_scalar(c_brn.field_tensor, P_brn_spec, c_brn.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "role_aware_burn",
        pen_phys > pen_spec + 0.05,
        f"Burn penalty Garchomp(Phys)={pen_phys:+.4f} vs Charizard-Y(Spec)={pen_spec:+.4f}",
    ))

    # 8. Role-Aware Taunt: Taunted support Whimsicott penalized strictly more than 4-attack Dragapult
    c_tnt = _compile_board(
        compiler,
        [whimsicott(), dragapult(), incineroar(), snorlax()],
        [incineroar(), snorlax(), pelipper(), dragonite()],
    )
    P_t_base = c_tnt.roster_tensor.clone()
    P_t_sup = P_t_base.clone()
    P_t_sup[0, MonIdx.TAUNT_TURNS] = 3.0
    P_t_atk = P_t_base.clone()
    P_t_atk[1, MonIdx.TAUNT_TURNS] = 3.0
    v_t_base = _eval_scalar(c_tnt.field_tensor, P_t_base, c_tnt.moves_tensor, tables, w)
    pen_sup = v_t_base - _eval_scalar(c_tnt.field_tensor, P_t_sup, c_tnt.moves_tensor, tables, w)
    pen_atk = v_t_base - _eval_scalar(c_tnt.field_tensor, P_t_atk, c_tnt.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "role_aware_taunt",
        pen_sup > pen_atk + 0.05,
        f"Taunt penalty Whimsicott(Support)={pen_sup:+.4f} vs Dragapult(4-Atk)={pen_atk:+.4f}",
    ))

    # 9. Shield Threshold Break (Focus Sash / Disguise / Multiscale break > 1% raw chip on unshielded)
    c_sh = _compile_board(
        compiler,
        [garchomp(), incineroar(), charizard_y(), whimsicott()],
        [pelipper(), mimikyu(), dragonite(), snorlax()],
    )
    P_sh_full = c_sh.roster_tensor.clone()
    P_sh_sash_broken = P_sh_full.clone()
    P_sh_sash_broken[4, MonIdx.HP_CUR] = P_sh_sash_broken[4, MonIdx.HP_MAX] * 0.99
    P_sh_disg_broken = P_sh_full.clone()
    P_sh_disg_broken[5, MonIdx.DISGUISE_INTACT] = 0.0
    c_nosh = _compile_board(
        compiler,
        [garchomp(), incineroar(), charizard_y(), whimsicott()],
        [snorlax(), incineroar(), garchomp(), charizard_y()],
    )
    P_nosh_full = c_nosh.roster_tensor.clone()
    P_nosh_chip = P_nosh_full.clone()
    P_nosh_chip[4, MonIdx.HP_CUR] = P_nosh_chip[4, MonIdx.HP_MAX] * 0.99
    gain_sash = _eval_scalar(c_sh.field_tensor, P_sh_sash_broken, c_sh.moves_tensor, tables, w) - _eval_scalar(c_sh.field_tensor, P_sh_full, c_sh.moves_tensor, tables, w)
    gain_disg = _eval_scalar(c_sh.field_tensor, P_sh_disg_broken, c_sh.moves_tensor, tables, w) - _eval_scalar(c_sh.field_tensor, P_sh_full, c_sh.moves_tensor, tables, w)
    gain_plain = _eval_scalar(c_nosh.field_tensor, P_nosh_chip, c_nosh.moves_tensor, tables, w) - _eval_scalar(c_nosh.field_tensor, P_nosh_full, c_nosh.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "shield_threshold_break",
        (gain_sash > gain_plain + 0.02) and (gain_disg > 0.05),
        f"Sash break gain={gain_sash:+.4f}, Disguise break={gain_disg:+.4f} vs plain 1% chip={gain_plain:+.4f}",
    ))

    # 10. Turn-Scaled Field Tempo: 4-turn Tailwind > 1-turn Tailwind
    F_tw4 = c_mat.field_tensor.clone()
    F_tw4[FieldIdx.TRAINER_1_TAILWIND_TURNS] = 4.0
    F_tw1 = c_mat.field_tensor.clone()
    F_tw1[FieldIdx.TRAINER_1_TAILWIND_TURNS] = 1.0
    v_tw4 = _eval_scalar(F_tw4, c_mat.roster_tensor, c_mat.moves_tensor, tables, w)
    v_tw1 = _eval_scalar(F_tw1, c_mat.roster_tensor, c_mat.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "turn_scaled_field_tempo",
        v_tw4 > v_tw1 + 0.08,
        f"Tailwind(4t) V={v_tw4:+.4f} vs Tailwind(1t) V={v_tw1:+.4f}",
    ))

    # 11. HP-Gated 2-Turn Prime: Healthy primed Stomping Tantrum > Unprimed, AND healthy > low HP prime delta
    c_st = _compile_board(
        compiler,
        [garchomp(100.0), pelipper(), charizard_y(), incineroar()],
        [incineroar(), snorlax(), pelipper(), dragonite()],
    )
    P_st0 = c_st.roster_tensor.clone()
    P_st1 = P_st0.clone()
    P_st1[0, MonIdx.LAST_MOVE_FAILED] = 1.0
    delta_healthy = _eval_scalar(c_st.field_tensor, P_st1, c_st.moves_tensor, tables, w) - _eval_scalar(c_st.field_tensor, P_st0, c_st.moves_tensor, tables, w)

    P_st_low0 = P_st0.clone()
    P_st_low0[0, MonIdx.HP_CUR] = P_st_low0[0, MonIdx.HP_MAX] * 0.15
    P_st_low1 = P_st_low0.clone()
    P_st_low1[0, MonIdx.LAST_MOVE_FAILED] = 1.0
    delta_low = _eval_scalar(c_st.field_tensor, P_st_low1, c_st.moves_tensor, tables, w) - _eval_scalar(c_st.field_tensor, P_st_low0, c_st.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "two_turn_prime_hp_gated",
        (delta_healthy > 0.05) and (delta_healthy > delta_low + 0.02),
        f"Primed Stomping Tantrum delta: healthy={delta_healthy:+.4f} vs 15%HP={delta_low:+.4f}",
    ))

    # 12. Glaive Rush Vulnerability Penalty on opponent
    P_gl0 = c_st.roster_tensor.clone()
    P_gl1 = P_gl0.clone()
    P_gl1[4, MonIdx.GLAIVE_RUSH_VULN] = 1.0
    v_gl0 = _eval_scalar(c_st.field_tensor, P_gl0, c_st.moves_tensor, tables, w)
    v_gl1 = _eval_scalar(c_st.field_tensor, P_gl1, c_st.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "glaive_rush_vuln_penalty",
        v_gl1 > v_gl0 + 0.04,
        f"Foe GlaiveRushVuln=1 V={v_gl1:+.4f} vs 0 V={v_gl0:+.4f}",
    ))

    # 13. Yawn Drowsy Threat on opponent
    P_yw0 = c_st.roster_tensor.clone()
    P_yw1 = P_yw0.clone()
    P_yw1[4, MonIdx.YAWN_ACTIVE] = 1.0
    v_yw0 = _eval_scalar(c_st.field_tensor, P_yw0, c_st.moves_tensor, tables, w)
    v_yw1 = _eval_scalar(c_st.field_tensor, P_yw1, c_st.moves_tensor, tables, w)
    results.append(CalibrationPuzzleResult(
        "yawn_drowsy_threat",
        v_yw1 > v_yw0 + 0.02,
        f"Foe YawnActive=1 V={v_yw1:+.4f} vs 0 V={v_yw0:+.4f}",
    ))

    return results
