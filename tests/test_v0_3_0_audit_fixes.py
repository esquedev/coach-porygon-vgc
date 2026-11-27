# -*- coding: utf-8 -*-
"""Comprehensive v0.3.0 Full-Repo Audit Regression & Cartridge Mechanics Suite.

Verifies genuine cartridge physics, solver equilibria, canonical species indexing,
chronological Bo3 ordering, persistent roster deletion, bilingual 8-pillar lexicon,
Showdown replay animations, and Regulation M-D Prep Dossier integrity — with zero
mocking or test-tricking shortcuts.
"""
from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from typing import Any, List

import numpy as np
import pytest

from apps.replay_coach.ots_db import (
    OTSRosterDatabase,
    canonical_deep_audit_cell_key,
    canonical_mode_key,
    compute_lead_lab_matchup_hash,
)
from apps.replay_coach.protocol_parser import (
    extract_replay_sort_key,
    sort_replay_entries,
)
from apps.replay_coach.server import ReplayCoachAppState, make_handler
from engine.db_registry import get_registry
from engine.solver.lead_matchup_solver import LeadMatchupSolver
from engine.terminology import (
    VICTORY_EQUITY_PILLARS,
    export_glossary_payload,
    get_pillar_description,
    get_pillar_label,
)
from engine.vgc_tensor_core.attack_cascade import execute_attack_cascade
from engine.vgc_tensor_core.compiler import (
    CHOICE_BASE_OPP_A_START,
    CHOICE_BASE_OPP_B_START,
    ShowdownTensorCompiler,
)
from engine.vgc_tensor_core.phases_pre_attack import execute_pre_attack_phases
from engine.vgc_tensor_core.schema_and_tables import (
    FieldIdx,
    FieldOpID,
    MonIdx,
    MoveIdx,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    build_bilinear_lookup_tables,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_REPLAY = (REPO_ROOT / "apps" / "replay_coach" / "sample_data" / "matchagotme_g1.html").read_text(encoding="utf-8")
SAMPLE_T1 = (REPO_ROOT / "data" / "teams" / "char_y_v4.txt").read_text(encoding="utf-8")
SAMPLE_T2 = (REPO_ROOT / "apps" / "replay_coach" / "sample_data" / "matchagotme_ots.txt").read_text(encoding="utf-8")

_NATURE_MULT = {
    "Adamant": {"atk": 1.1, "spa": 0.9},
    "Jolly": {"spe": 1.1, "spa": 0.9},
    "Modest": {"spa": 1.1, "atk": 0.9},
    "Timid": {"spe": 1.1, "atk": 0.9},
    "Impish": {"def": 1.1, "spa": 0.9},
    "Bold": {"def": 1.1, "atk": 0.9},
}


def _to_np(x: Any) -> np.ndarray:
    if hasattr(x, "detach"):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def _make_mon_spec(
    species: str,
    moves: List[str],
    ability: str = "Intimidate",
    item: str | None = None,
    nature: str = "Adamant",
    sp: dict | None = None,
) -> dict:
    """Build a DuckDB-grounded Champions Level 50 mon_spec dict for ShowdownTensorCompiler."""
    reg = get_registry()
    row = reg.get_pokemon(species)
    assert row is not None, f"Species '{species}' missing from DuckDB pokedex"
    base = row["baseStats"]
    sp_d = sp or {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
    nm = _NATURE_MULT.get(nature, {})
    hp_max = int(base["hp"]) + int(sp_d.get("hp", 0)) + 75
    stats = {
        k: int((int(base[k]) + int(sp_d.get(k, 0)) + 20) * float(nm.get(k, 1.0)))
        for k in ("atk", "def", "spa", "spd", "spe")
    }
    return {
        "species": species,
        "types": list(row["types"]),
        "hp_max": hp_max,
        "hp_cur": hp_max,
        "stats": stats,
        "ability": ability,
        "item": item or "none",
        "moves": list(moves),
    }


def _step_turn_single_action(
    roster_specs: List[dict],
    t1_pair: tuple[int, int],
    t2_pair: tuple[int, int],
    field_spec: dict | None = None,
    num_rng: int = 32,
    p_mutator: Any = None,
):
    """Compile an 8-slot roster & field spec and execute Phases 1..4 on one exact joint action pair."""
    tables = build_bilinear_lookup_tables(device="cpu")
    compiler = ShowdownTensorCompiler(tables=tables, device="cpu")
    comp = compiler.compile_battle_state(roster_specs, field_spec=field_spec)
    F = comp.field_tensor
    P = comp.roster_tensor.clone() if hasattr(comp.roster_tensor, "clone") else comp.roster_tensor.copy()
    M = comp.moves_tensor
    if p_mutator is not None:
        p_mutator(P)

    if hasattr(F, "unsqueeze"):
        F_batch = F.unsqueeze(0).unsqueeze(0)
        P_batch = P.unsqueeze(0).unsqueeze(0)
        M_batch = M.unsqueeze(0).unsqueeze(0)
    else:
        F_batch = F[None, None, :]
        P_batch = P[None, None, :, :]
        M_batch = M[None, None, :, :, :]

    A1 = np.array([[t1_pair[0], t1_pair[1]]], dtype=np.int64)
    A2 = np.array([[t2_pair[0], t2_pair[1]]], dtype=np.int64)
    pre = execute_pre_attack_phases(F_batch, P_batch, M_batch, A1, A2, tables)
    res = execute_attack_cascade(
        F_batch,
        P_batch,
        M_batch,
        A1,
        A2,
        pre,
        tables,
        num_mc_samples=num_rng,
        rng_seed=20261126,
    )
    return comp, res


# =============================================================================
# 1. TENSOR CORE CARTRIDGE MECHANICS: FEINT, PHANTOM FORCE, SCREEN-BREAKERS
# =============================================================================


def test_feint_breaks_protect_wide_guard_quick_guard_and_focus_sash() -> None:
    """Verify Feint hits through Protect/Wide Guard/Quick Guard at 1.0x, breaks Focus Sash,
    lifts Protect for partner's slower Stomping Tantrum, and respects Ghost/Psychic Terrain."""
    # Case A: Raichu Feint + Garchomp Stomping Tantrum into Protecting Focus Sash Excadrill
    t1_specs = [
        _make_mon_spec("Raichu", ["Feint", "Fake Out", "Volt Switch", "Protect"], ability="Lightning Rod", nature="Jolly"),
        _make_mon_spec("Garchomp", ["Stomping Tantrum", "Rock Slide", "Dragon Claw", "Protect"], ability="Rough Skin", nature="Jolly"),
        _make_mon_spec("Pelipper", ["Hurricane", "Weather Ball", "Wide Guard", "Protect"], ability="Drizzle"),
        _make_mon_spec("Venusaur", ["Sludge Bomb", "Earth Power", "Sleep Powder", "Protect"], ability="Chlorophyll"),
    ]
    t2_specs = [
        _make_mon_spec("Tyranitar", ["Rock Slide", "Knock Off", "High Horsepower", "Protect"], ability="Sand Stream", nature="Adamant"),
        _make_mon_spec("Excadrill", ["High Horsepower", "Iron Head", "Rock Slide", "Protect"], ability="Sand Rush", item="Focus Sash", nature="Jolly"),
        _make_mon_spec("Sinistcha", ["Matcha Gotcha", "Trick Room", "Rage Powder", "Protect"], ability="Hospitality"),
        _make_mon_spec("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Protect"], ability="Intimidate"),
    ]
    comp, res = _step_turn_single_action(
        t1_specs + t2_specs,
        t1_pair=(CHOICE_BASE_OPP_B_START + 0, CHOICE_BASE_OPP_B_START + 0),
        t2_pair=(CHOICE_BASE_OPP_A_START + 3, CHOICE_BASE_OPP_A_START + 3),
        num_rng=32,
    )

    M_np = _to_np(comp.moves_tensor)
    P_np = _to_np(res.P)
    assert int(round(float(M_np[SLOT_TRAINER_1_A, 0, MoveIdx.FIELD_OP_ID]))) == int(FieldOpID.FEINT)
    assert float(M_np[SLOT_TRAINER_1_A, 0, MoveIdx.PRIORITY]) == 2.0

    exca_hp_end = P_np[0, 0, :, SLOT_TRAINER_2_B, MonIdx.HP_CUR]
    exca_alive_end = P_np[0, 0, :, SLOT_TRAINER_2_B, MonIdx.ALIVE_FLAG]
    exca_prot_end = P_np[0, 0, :, SLOT_TRAINER_2_B, MonIdx.PROTECT_ACTIVE]
    # Feint breaks Protect + Focus Sash -> Stomping Tantrum finishes Excadrill across 100% of samples!
    assert float(np.mean(exca_hp_end)) == 0.0
    assert float(np.mean(exca_alive_end)) == 0.0
    assert float(np.mean(exca_prot_end)) == 0.0

    # Case B: Feint clears Wide Guard so partner's Rock Slide (spread) connects!
    t2_wg_specs = [
        _make_mon_spec("Pelipper", ["Wide Guard", "Hurricane", "Weather Ball", "Protect"], ability="Drizzle", nature="Modest"),
        _make_mon_spec("Charizard", ["Heat Wave", "Air Slash", "Solar Beam", "Protect"], ability="Blaze", nature="Timid"),
        _make_mon_spec("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Protect"], ability="Intimidate"),
        _make_mon_spec("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "Protect"], ability="Grassy Surge"),
    ]
    _, res_wg = _step_turn_single_action(
        t1_specs + t2_wg_specs,
        t1_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 1),
        t2_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 0),
        num_rng=32,
    )
    P_wg = _to_np(res_wg.P)
    assert float(np.mean(P_wg[0, 0, :, SLOT_TRAINER_2_A, MonIdx.WIDE_GUARD_ACTIVE])) == 0.0
    assert float(np.mean(P_wg[0, 0, :, SLOT_TRAINER_2_B, MonIdx.WIDE_GUARD_ACTIVE])) == 0.0
    zard_max = float(P_wg[0, 0, 0, SLOT_TRAINER_2_B, MonIdx.HP_MAX])
    assert float(np.mean(P_wg[0, 0, :, SLOT_TRAINER_2_B, MonIdx.HP_CUR])) < zard_max * 0.35

    # Case C: Feint clears Quick Guard so partner's priority move connects!
    t1_qg_specs = [
        _make_mon_spec("Raichu", ["Feint", "Fake Out", "Volt Switch", "Protect"], ability="Lightning Rod", nature="Jolly"),
        _make_mon_spec("Dragonite", ["Extreme Speed", "Dragon Claw", "Stomping Tantrum", "Protect"], ability="Inner Focus", nature="Adamant"),
        _make_mon_spec("Pelipper", ["Hurricane", "Weather Ball", "Wide Guard", "Protect"], ability="Drizzle"),
        _make_mon_spec("Venusaur", ["Sludge Bomb", "Earth Power", "Sleep Powder", "Protect"], ability="Chlorophyll"),
    ]
    t2_qg_specs = [
        _make_mon_spec("Talonflame", ["Quick Guard", "Brave Bird", "Tailwind", "Protect"], ability="Gale Wings", nature="Jolly"),
        _make_mon_spec("Charizard", ["Heat Wave", "Air Slash", "Solar Beam", "Protect"], ability="Blaze", nature="Timid"),
        _make_mon_spec("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Protect"], ability="Intimidate"),
        _make_mon_spec("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "Protect"], ability="Grassy Surge"),
    ]
    _, res_qg = _step_turn_single_action(
        t1_qg_specs + t2_qg_specs,
        t1_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_B_START + 0),
        t2_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 0),
        num_rng=16,
    )
    P_qg = _to_np(res_qg.P)
    assert float(np.mean(P_qg[0, 0, :, SLOT_TRAINER_2_A, MonIdx.QUICK_GUARD_ACTIVE])) == 0.0
    assert float(np.mean(P_qg[0, 0, :, SLOT_TRAINER_2_B, MonIdx.HP_CUR])) < float(P_qg[0, 0, 0, SLOT_TRAINER_2_B, MonIdx.HP_MAX])

    # Case D: Ghost immunity blocks Feint (Protect stays intact!)
    t2_ghost_specs = [
        _make_mon_spec("Gengar", ["Shadow Ball", "Sludge Bomb", "Icy Wind", "Protect"], ability="Cursed Body", nature="Timid"),
        _make_mon_spec("Excadrill", ["High Horsepower", "Iron Head", "Rock Slide", "Protect"], ability="Sand Rush", nature="Jolly"),
        _make_mon_spec("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Protect"], ability="Intimidate"),
        _make_mon_spec("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "Protect"], ability="Grassy Surge"),
    ]
    _, res_ghost = _step_turn_single_action(
        t1_specs + t2_ghost_specs,
        t1_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 0),
        t2_pair=(CHOICE_BASE_OPP_A_START + 3, CHOICE_BASE_OPP_A_START + 3),
        num_rng=16,
    )
    P_gh = _to_np(res_ghost.P)
    assert float(np.mean(P_gh[0, 0, :, SLOT_TRAINER_2_A, MonIdx.HP_CUR])) == float(P_gh[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_MAX])
    assert float(np.mean(P_gh[0, 0, :, SLOT_TRAINER_2_A, MonIdx.PROTECT_ACTIVE])) == 1.0

    # Case E: Psychic Terrain blocks priority +2 Feint against grounded Excadrill!
    _, res_pt = _step_turn_single_action(
        t1_specs + t2_specs,
        t1_pair=(CHOICE_BASE_OPP_B_START + 0, CHOICE_BASE_OPP_B_START + 0),
        t2_pair=(CHOICE_BASE_OPP_A_START + 3, CHOICE_BASE_OPP_A_START + 3),
        field_spec={"terrain": "psychic", "terrain_turns": 5},
        num_rng=16,
    )
    P_pt = _to_np(res_pt.P)
    assert float(np.mean(P_pt[0, 0, :, SLOT_TRAINER_2_B, MonIdx.HP_CUR])) == float(P_pt[0, 0, 0, SLOT_TRAINER_2_B, MonIdx.HP_MAX])
    assert float(np.mean(P_pt[0, 0, :, SLOT_TRAINER_2_B, MonIdx.PROTECT_ACTIVE])) == 1.0


def test_phantom_force_strike_turn_lifts_protect_for_partner() -> None:
    """Verify Phantom Force on its strike turn hits through Protect and lifts it for slower partner."""
    t1_specs = [
        _make_mon_spec("Dragapult", ["Phantom Force", "Dragon Darts", "U-turn", "Protect"], ability="Clear Body", nature="Jolly"),
        _make_mon_spec("Garchomp", ["Stomping Tantrum", "Rock Slide", "Dragon Claw", "Protect"], ability="Rough Skin", nature="Adamant", sp={"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}),
        _make_mon_spec("Pelipper", ["Hurricane", "Weather Ball", "Wide Guard", "Protect"], ability="Drizzle"),
        _make_mon_spec("Venusaur", ["Sludge Bomb", "Earth Power", "Sleep Powder", "Protect"], ability="Chlorophyll"),
    ]
    t2_specs = [
        _make_mon_spec("Tyranitar", ["Rock Slide", "Knock Off", "High Horsepower", "Protect"], ability="Sand Stream", nature="Adamant", sp={"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}),
        _make_mon_spec("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Protect"], ability="Intimidate", nature="Adamant", sp={"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 2, "spe": 0}),
        _make_mon_spec("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "Protect"], ability="Grassy Surge"),
        _make_mon_spec("Sinistcha", ["Matcha Gotcha", "Trick Room", "Rage Powder", "Protect"], ability="Hospitality"),
    ]

    def _prime_vanished(P: Any) -> None:
        P[SLOT_TRAINER_1_A, MonIdx.CHARGED_MOVE_IDX] = 1.0  # 1-based move index (move 0 = Phantom Force)
        P[SLOT_TRAINER_1_A, MonIdx.SEMI_INVULN] = 1.0

    comp, res = _step_turn_single_action(
        t1_specs + t2_specs,
        t1_pair=(CHOICE_BASE_OPP_B_START + 0, CHOICE_BASE_OPP_B_START + 0),
        t2_pair=(CHOICE_BASE_OPP_A_START + 3, CHOICE_BASE_OPP_A_START + 3),
        num_rng=16,
        p_mutator=_prime_vanished,
    )
    M_np = _to_np(comp.moves_tensor)
    P_np = _to_np(res.P)
    assert int(round(float(M_np[SLOT_TRAINER_1_A, 0, MoveIdx.FIELD_OP_ID]))) == int(FieldOpID.PHANTOM_FORCE)

    inc_hp_end = P_np[0, 0, :, SLOT_TRAINER_2_B, MonIdx.HP_CUR]
    inc_max = float(P_np[0, 0, 0, SLOT_TRAINER_2_B, MonIdx.HP_MAX])
    # Both Phantom Force AND Garchomp Stomping Tantrum (2x super effective!) must connect!
    assert float(np.mean(P_np[0, 0, :, SLOT_TRAINER_2_B, MonIdx.PROTECT_ACTIVE])) == 0.0
    assert float(np.mean(inc_hp_end)) < inc_max * 0.45


def test_screen_breakers_shatter_screens_before_damage_and_preserve_strong_jaw() -> None:
    """Verify Brick Break, Psychic Fangs (+Strong Jaw 1.5x), and Raging Bull break target-side
    Reflect/Light Screen/Aurora Veil BEFORE damage mitigation, and fail to break on immune/Protect targets."""
    t1_specs = [
        _make_mon_spec("Sharpedo", ["Psychic Fangs", "Brick Break", "Crunch", "Protect"], ability="Strong Jaw", nature="Adamant", sp={"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}),
        _make_mon_spec("Tauros-Paldea-Blaze", ["Raging Bull", "Flare Blitz", "Close Combat", "Protect"], ability="Intimidate", nature="Jolly"),
        _make_mon_spec("Pelipper", ["Hurricane", "Weather Ball", "Wide Guard", "Protect"], ability="Drizzle"),
        _make_mon_spec("Venusaur", ["Sludge Bomb", "Earth Power", "Sleep Powder", "Protect"], ability="Chlorophyll"),
    ]
    t2_specs = [
        _make_mon_spec("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Protect"], ability="Intimidate", nature="Impish", sp={"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 2, "spe": 0}),
        _make_mon_spec("Tyranitar", ["Rock Slide", "Knock Off", "High Horsepower", "Protect"], ability="Sand Stream", nature="Adamant", sp={"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}),
        _make_mon_spec("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "Protect"], ability="Grassy Surge"),
        _make_mon_spec("Sinistcha", ["Matcha Gotcha", "Trick Room", "Rage Powder", "Protect"], ability="Hospitality"),
    ]
    screens_field = {
        "trainer_2_reflect_turns": 5,
        "trainer_2_light_screen_turns": 5,
        "trainer_2_aurora_veil_turns": 5,
    }

    # 1. Brick Break (move 1) into Incineroar (Opp_A) with all 3 screens vs no screens -> identical damage!
    comp_scr, res_scr = _step_turn_single_action(
        t1_specs + t2_specs,
        t1_pair=(CHOICE_BASE_OPP_A_START + 1, CHOICE_BASE_OPP_A_START + 3),
        t2_pair=(CHOICE_BASE_OPP_A_START + 2, CHOICE_BASE_OPP_A_START + 3),
        field_spec=screens_field,
        num_rng=32,
    )
    _, res_clr = _step_turn_single_action(
        t1_specs + t2_specs,
        t1_pair=(CHOICE_BASE_OPP_A_START + 1, CHOICE_BASE_OPP_A_START + 3),
        t2_pair=(CHOICE_BASE_OPP_A_START + 2, CHOICE_BASE_OPP_A_START + 3),
        num_rng=32,
    )
    M_scr = _to_np(comp_scr.moves_tensor)
    F_scr = _to_np(res_scr.F)
    P_scr = _to_np(res_scr.P)
    P_clr = _to_np(res_clr.P)

    assert int(round(float(M_scr[SLOT_TRAINER_1_A, 0, MoveIdx.FIELD_OP_ID]))) == int(FieldOpID.BREAK_SCREENS_BITE)
    assert int(round(float(M_scr[SLOT_TRAINER_1_A, 1, MoveIdx.FIELD_OP_ID]))) == int(FieldOpID.BREAK_SCREENS)
    assert int(round(float(M_scr[SLOT_TRAINER_1_B, 0, MoveIdx.FIELD_OP_ID]))) == int(FieldOpID.BREAK_SCREENS)

    assert float(np.mean(F_scr[0, 0, :, FieldIdx.TRAINER_2_REFLECT_TURNS])) == 0.0
    assert float(np.mean(F_scr[0, 0, :, FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS])) == 0.0
    assert float(np.mean(F_scr[0, 0, :, FieldIdx.TRAINER_2_AURORA_VEIL_TURNS])) == 0.0
    assert np.allclose(P_scr[0, 0, :, SLOT_TRAINER_2_A, MonIdx.HP_CUR], P_clr[0, 0, :, SLOT_TRAINER_2_A, MonIdx.HP_CUR], atol=1e-4)

    # 2. Raging Bull (slot B move 0) also shatters screens
    _, res_rb = _step_turn_single_action(
        t1_specs + t2_specs,
        t1_pair=(CHOICE_BASE_OPP_A_START + 3, CHOICE_BASE_OPP_A_START + 0),
        t2_pair=(CHOICE_BASE_OPP_A_START + 2, CHOICE_BASE_OPP_A_START + 3),
        field_spec=screens_field,
        num_rng=16,
    )
    F_rb = _to_np(res_rb.F)
    assert float(np.mean(F_rb[0, 0, :, FieldIdx.TRAINER_2_REFLECT_TURNS])) == 0.0
    assert float(np.mean(F_rb[0, 0, :, FieldIdx.TRAINER_2_AURORA_VEIL_TURNS])) == 0.0

    # 3. Psychic Fangs breaks screens AND preserves Strong Jaw 1.5x boost vs Speed Boost!
    t2_non_dark = [
        _make_mon_spec("Venusaur", ["Sludge Bomb", "Earth Power", "Sleep Powder", "Protect"], ability="Chlorophyll", nature="Modest", sp={"hp": 32, "atk": 0, "def": 32, "spa": 2, "spd": 0, "spe": 0}),
        _make_mon_spec("Tyranitar", ["Rock Slide", "Knock Off", "High Horsepower", "Protect"], ability="Sand Stream"),
        _make_mon_spec("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Protect"], ability="Intimidate"),
        _make_mon_spec("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "Protect"], ability="Grassy Surge"),
    ]
    t1_no_sj = [
        _make_mon_spec("Sharpedo", ["Psychic Fangs", "Brick Break", "Crunch", "Protect"], ability="Speed Boost", nature="Adamant", sp={"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}),
        t1_specs[1], t1_specs[2], t1_specs[3],
    ]
    # Venusaur Protect blocks Psychic Fangs -> Reflect stays at 5!
    _, res_prot = _step_turn_single_action(
        t1_specs + t2_non_dark,
        t1_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 3),
        t2_pair=(CHOICE_BASE_OPP_A_START + 3, CHOICE_BASE_OPP_A_START + 3),
        field_spec={"trainer_2_reflect_turns": 5},
        num_rng=16,
    )
    assert float(np.mean(_to_np(res_prot.F)[0, 0, :, FieldIdx.TRAINER_2_REFLECT_TURNS])) == 5.0

    # Without Protect: Psychic Fangs shatters Reflect AND Strong Jaw deals ~1.5x more damage!
    _, res_sj_hit = _step_turn_single_action(
        t1_specs + t2_non_dark,
        t1_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 3),
        t2_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 3),
        field_spec={"trainer_2_reflect_turns": 5},
        num_rng=32,
    )
    _, res_nosj_hit = _step_turn_single_action(
        t1_no_sj + t2_non_dark,
        t1_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 3),
        t2_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 3),
        field_spec={"trainer_2_reflect_turns": 5},
        num_rng=32,
    )
    assert float(np.mean(_to_np(res_sj_hit.F)[0, 0, :, FieldIdx.TRAINER_2_REFLECT_TURNS])) == 0.0
    P_sj = _to_np(res_sj_hit.P)
    P_nosj = _to_np(res_nosj_hit.P)
    v_max = float(P_sj[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_MAX])
    dmg_sj = v_max - float(np.mean(P_sj[0, 0, :, SLOT_TRAINER_2_A, MonIdx.HP_CUR]))
    dmg_nosj = v_max - float(np.mean(P_nosj[0, 0, :, SLOT_TRAINER_2_A, MonIdx.HP_CUR]))
    assert dmg_sj > dmg_nosj * 1.30

    # 4. Brick Break into Ghost-type (type immune) does NOT shatter Reflect!
    t2_ghost = [
        _make_mon_spec("Gengar", ["Shadow Ball", "Sludge Bomb", "Icy Wind", "Protect"], ability="Cursed Body"),
        _make_mon_spec("Tyranitar", ["Rock Slide", "Knock Off", "High Horsepower", "Protect"], ability="Sand Stream"),
        _make_mon_spec("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Protect"], ability="Intimidate"),
        _make_mon_spec("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "Protect"], ability="Grassy Surge"),
    ]
    _, res_imm = _step_turn_single_action(
        t1_specs + t2_ghost,
        t1_pair=(CHOICE_BASE_OPP_A_START + 1, CHOICE_BASE_OPP_A_START + 3),
        t2_pair=(CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 3),
        field_spec={"trainer_2_reflect_turns": 5},
        num_rng=16,
    )
    assert float(np.mean(_to_np(res_imm.F)[0, 0, :, FieldIdx.TRAINER_2_REFLECT_TURNS])) == 5.0


def test_raichu_garchomp_vs_tyranitar_excadrill_feint_turn1_equilibrium(tmp_path: Path) -> None:
    """Verify real Turn-1 GPU solver credits `Feint -> Excadrill + Stomping Tantrum -> Excadrill`
    when Focus Sash Excadrill Protects alongside a Tyranitar switch."""
    t1_paste = SAMPLE_T1
    t2_paste = """Tyranitar @ Tyranitarite
Ability: Sand Stream
Level: 50
EVs: 252 HP / 252 Atk / 12 Def
Adamant Nature
- Rock Slide
- Knock Off
- High Horsepower
- Protect

Excadrill @ Focus Sash
Ability: Sand Rush
Level: 50
EVs: 12 HP / 252 Atk / 252 Spe
Jolly Nature
- High Horsepower
- Iron Head
- Rock Slide
- Protect

Sinistcha @ Sitrus Berry
Ability: Hospitality
Level: 50
EVs: 252 HP / 140 Def / 124 SpD
Bold Nature
- Matcha Gotcha
- Trick Room
- Rage Powder
- Protect

Incineroar @ Assault Vest
Ability: Intimidate
Level: 50
EVs: 252 HP / 100 Atk / 164 SpD
Adamant Nature
- Fake Out
- Flare Blitz
- Knock Off
- U-turn

Primarina @ Throat Spray
Ability: Liquid Voice
Level: 50
EVs: 252 HP / 252 SpA / 12 Spe
Modest Nature
- Hyper Voice
- Moonblast
- Haze
- Protect

Gholdengo @ Choice Specs
Ability: Good as Gold
Level: 50
EVs: 12 HP / 252 SpA / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Power Gem
- Trick
"""
    st = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "feint_eq.duckdb", device="cpu")
    solver = LeadMatchupSolver(device="cpu")
    pool_t1 = solver._precompile_team_pool(t1_paste, trainer_id="trainer_1", require_explicit_spreads=False)
    pool_t2 = solver._precompile_team_pool(t2_paste, trainer_id="trainer_2", require_explicit_spreads=False)

    # Locate exact mode indices by root species (handles Mega display labels like Raichu-Mega-X / Tyranitar-Mega)
    m1_idx = next(
        m.mode_idx for m in pool_t1.modes
        if {s.split("-")[0] for s in m.lead_species} == {"Raichu", "Garchomp"}
    )
    m2_idx = next(
        m.mode_idx for m in pool_t2.modes
        if {s.split("-")[0] for s in m.lead_species} == {"Tyranitar", "Excadrill"}
        and any(s.split("-")[0] == "Sinistcha" for s in m.bench_species)
    )
    board, _, _, _ = solver.build_turn1_battle_state(t1_paste, t2_paste, m1_idx, m2_idx)

    # Identify exact choice codes for Raichu+Garchomp vs Tyranitar+Excadrill directly from compiled move slots
    # Slot 0/1 may be (Raichu, Garchomp) or (Garchomp, Raichu); same for (Tyranitar, Excadrill).
    t1_sp = list(board.slot_species[:2])
    t2_sp = list(board.slot_species[4:6])
    r_slot = next(i for i, s in enumerate(t1_sp) if s.startswith("Raichu"))
    g_slot = 1 - r_slot
    exca_opp_offset = CHOICE_BASE_OPP_A_START if t2_sp[0].startswith("Excadrill") else CHOICE_BASE_OPP_B_START
    ttar_opp_offset = CHOICE_BASE_OPP_B_START if exca_opp_offset == CHOICE_BASE_OPP_A_START else CHOICE_BASE_OPP_A_START

    r_moves = [m.lower() for m in board.slot_move_names[r_slot]]
    g_moves = [m.lower() for m in board.slot_move_names[g_slot]]
    feint_idx = r_moves.index("feint")
    fakeout_idx = r_moves.index("fake out")
    stomp_idx = g_moves.index("stomping tantrum")

    t2_a_moves = [m.lower() for m in board.slot_move_names[4]]
    t2_b_moves = [m.lower() for m in board.slot_move_names[5]]
    sinistcha_bench_choice = 24 if board.slot_species[6].startswith("Sinistcha") else 25

    def _pair(r_c: int, g_c: int) -> list[int]:
        return [r_c, g_c] if r_slot == 0 else [g_c, r_c]

    t1_c_feint_stomp = _pair(exca_opp_offset + feint_idx, exca_opp_offset + stomp_idx)
    t1_c_fakeout_ttar = _pair(ttar_opp_offset + fakeout_idx, ttar_opp_offset + stomp_idx)

    if t2_sp[0].startswith("Tyranitar"):
        t2_c_switch_prot = [sinistcha_bench_choice, CHOICE_BASE_OPP_A_START + t2_b_moves.index("protect")]
        t2_c_stay_attack = [CHOICE_BASE_OPP_A_START + t2_a_moves.index("rock slide"), CHOICE_BASE_OPP_B_START + t2_b_moves.index("high horsepower")]
    else:
        t2_c_switch_prot = [CHOICE_BASE_OPP_A_START + t2_a_moves.index("protect"), sinistcha_bench_choice]
        t2_c_stay_attack = [CHOICE_BASE_OPP_B_START + t2_a_moves.index("high horsepower"), CHOICE_BASE_OPP_A_START + t2_b_moves.index("rock slide")]

    step_res = st.gpu_engine.sm.step(
        F=board.field_tensor,
        P=board.roster_tensor,
        M_moves=board.moves_tensor,
        trainer_1_choices=np.array([t1_c_feint_stomp, t1_c_fakeout_ttar], dtype=np.int64),
        trainer_2_choices=np.array([t2_c_switch_prot, t2_c_stay_attack], dtype=np.int64),
        num_mc_samples=64,
        rng_seed=20261126,
        resolve_lead_entry_abilities=False,
    )
    U_risk = _to_np(step_res.stats.risk_adjusted_utility)
    exca_slot = 4 if t2_sp[0].startswith("Excadrill") else 5
    exca_ko_prob = float(_to_np(step_res.faint_prob)[0, 0, exca_slot])

    # Feint -> Excadrill + Stomping Tantrum -> Excadrill vs Tyranitar->Sinistcha + Excadrill Protect:
    # Must achieve 100% Excadrill KO and strongly outperform Fake Out Tyranitar + Stomping Tantrum Tyranitar!
    assert exca_ko_prob >= 0.99, f"Expected ~100% Excadrill KO through Protect+Sash, got {exca_ko_prob:.2f}"
    assert float(U_risk[0, 0]) > 1.0, f"Expected strong positive U_risk for Feint+Stomping Tantrum punish, got {U_risk[0, 0]:.3f}"
    assert float(U_risk[0, 0]) > float(U_risk[1, 0]) + 0.50


# =============================================================================
# 2. REPO-WIDE 8-PILLAR VICTORY EQUITY LEXICON & VERIFIED OTS MOVES ON BOARD
# =============================================================================


def test_victory_equity_8_pillars_lexicon_and_ots_verified_board_moves(tmp_path: Path) -> None:
    """Verify single-source-of-truth 8-pillar lexicon across 4 registers & verified OTS board moves."""
    expected_pillars = (
        "material",
        "threat",
        "malposition",
        "restriction",
        "status_boost",
        "two_turn_prime",
        "resources",
        "field_tempo",
    )
    assert set(VICTORY_EQUITY_PILLARS.keys()) == set(expected_pillars)
    payload = export_glossary_payload()
    assert payload["pillars"] == VICTORY_EQUITY_PILLARS

    forbidden_vgc = ("IEDS", "Nash", "LQRE", "QRE", "CVaR", "Minimax", "U_risk")
    for pkey in expected_pillars:
        for lang in ("es", "en"):
            for style in ("vgc", "scientific"):
                lbl = get_pillar_label(pkey, lang, style)
                desc = get_pillar_description(pkey, lang, style)
                assert lbl and lbl != pkey
                assert len(desc) >= 25
                if style == "vgc":
                    combined = f"{lbl} {desc}"
                    for bad in forbidden_vgc:
                        assert not re.search(rf"\b{re.escape(bad)}\b", combined), (
                            f"Academic token '{bad}' leaked into pillar {pkey} [{lang}_{style}]: {combined}"
                        )
        assert get_pillar_label(pkey, "es", "vgc") != get_pillar_label(pkey, "en", "vgc")

    # Verify board_slots carries verified 4-move OTS lists from compiled board
    st = ReplayCoachAppState(preload_sample=True, db_path=tmp_path / "ots_moves.duckdb", device="cpu")
    res = st.gpu_engine.analyze_turn(st.replay, turn_number=1, num_mc=16)
    for side in ("trainer_1", "trainer_2"):
        assert len(res["board"][side]) == 4
        for mon in res["board"][side]:
            assert mon["ots_verified"] is True
            assert isinstance(mon["moves"], list) and len(mon["moves"]) == 4
            assert all(isinstance(mv, str) and mv.strip() for mv in mon["moves"])


# =============================================================================
# 3. SHOWDOWN REPLAY MOVE ANIMATIONS & REFERRER POLICY
# =============================================================================


def test_showdown_replay_player_animations_and_referrer_header(tmp_path: Path) -> None:
    """Verify /api/replay-player loads live Showdown embed + fixed local fallback and sends Referrer-Policy."""
    st = ReplayCoachAppState(preload_sample=True, db_path=tmp_path / "anim_test.duckdb", device="cpu")
    html_doc = st.render_official_showdown_player_html()
    assert "https://play.pokemonshowdown.com/js/replay-embed.js" in html_doc
    assert "/vendor/replay-embed.js" in html_doc
    assert "onerror=" in html_doc and "s.async=false" in html_doc

    vendor_js = (REPO_ROOT / "apps" / "replay_coach" / "vendor" / "replay-embed.js").read_text(encoding="utf-8")
    assert "scriptEl.async=false;" in vendor_js or "scriptEl.async = false;" in vendor_js
    assert "battle-animations.js" in vendor_js
    assert "battle-animations-moves.js" in vendor_js
    assert "?a7" not in vendor_js

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(st))
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/replay-player", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        assert resp.status == 200
        assert resp.getheader("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "https://play.pokemonshowdown.com/js/replay-embed.js" in body
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()


# =============================================================================
# 4. LEAD LAB K=128 DEEP AUDIT CANONICAL SPECIES KEYING & ZERO ABSENT MOVES
# =============================================================================


def _reverse_showdown_paste_order(paste_text: str) -> str:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", paste_text.strip()) if b.strip()]
    return "\n\n".join(reversed(blocks)) + "\n"


def test_lead_lab_deep_audit_canonical_species_keying_across_paste_reordering(tmp_path: Path) -> None:
    """Reordering a 6-mon paste shifts positional mode_idx while keeping matchup_hash identical.
    Deep Turn-1 Audit MUST resolve & cache by canonical species identity and never leak absent Pokémon."""
    st = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "deep_canon.duckdb")
    solver = LeadMatchupSolver(device="cpu")
    pool1_a = solver._precompile_team_pool(SAMPLE_T1, trainer_id="trainer_1", require_explicit_spreads=False)
    pool2_a = solver._precompile_team_pool(SAMPLE_T2, trainer_id="trainer_2", require_explicit_spreads=False)

    target_m1 = pool1_a.modes[7]
    target_m2 = pool2_a.modes[4]
    m_hash = compute_lead_lab_matchup_hash(SAMPLE_T1, SAMPLE_T2, preset="fast")

    st._lead_jobs["job_orig"] = {
        "job_id": "job_orig",
        "t1_paste": SAMPLE_T1,
        "t2_paste": SAMPLE_T2,
        "matchup_hash": m_hash,
        "sprites": {},
    }
    audit_orig = st.run_lead_lab_deep_turn1(
        job_id="job_orig",
        mode_1_idx=target_m1.mode_idx,
        mode_2_idx=target_m2.mode_idx,
        num_mc=32,
        lead_1=target_m1.lead_species,
        bench_1=target_m1.bench_species,
        lead_2=target_m2.lead_species,
        bench_2=target_m2.bench_species,
    )
    assert audit_orig["from_vault_cache"] is False
    assert set(audit_orig["mode_1"]["lead_species"]) == set(target_m1.lead_species)
    assert set(audit_orig["mode_1"]["bench_species"]) == set(target_m1.bench_species)
    assert set(audit_orig["mode_2"]["lead_species"]) == set(target_m2.lead_species)
    assert set(audit_orig["mode_2"]["bench_species"]) == set(target_m2.bench_species)

    # Assert ZERO absent Pokémon appear anywhere in Turn-1 recommended lines!
    all_t1_species = set(pool1_a.display_species)
    brought_t1_species = set(target_m1.lead_species) | set(target_m1.bench_species)
    absent_t1_species = all_t1_species - brought_t1_species
    assert len(absent_t1_species) == 2
    for act in audit_orig["top_actions"]:
        for abs_sp in absent_t1_species:
            assert abs_sp not in act["desc"], f"Absent Pokémon '{abs_sp}' leaked into Deep Audit action: {act['desc']}"

    # Reverse SAMPLE_T1 paste order (same matchup_hash, completely different positional mode_idx!)
    reordered_t1 = _reverse_showdown_paste_order(SAMPLE_T1)
    assert compute_lead_lab_matchup_hash(reordered_t1, SAMPLE_T2, preset="fast") == m_hash
    pool1_b = solver._precompile_team_pool(reordered_t1, trainer_id="trainer_1", require_explicit_spreads=False)
    shifted_m1 = next(
        m for m in pool1_b.modes
        if canonical_mode_key(m.lead_species, m.bench_species) == canonical_mode_key(target_m1.lead_species, target_m1.bench_species)
    )
    assert shifted_m1.mode_idx != target_m1.mode_idx

    st._lead_jobs["job_reordered"] = {
        "job_id": "job_reordered",
        "t1_paste": reordered_t1,
        "t2_paste": SAMPLE_T2,
        "matchup_hash": m_hash,
        "sprites": {},
    }
    audit_cached = st.run_lead_lab_deep_turn1(
        job_id="job_reordered",
        mode_1_idx=0,  # Intentionally stale positional index!
        mode_2_idx=0,
        num_mc=32,
        lead_1=target_m1.lead_species,
        bench_1=target_m1.bench_species,
        lead_2=target_m2.lead_species,
        bench_2=target_m2.bench_species,
    )
    assert audit_cached["from_vault_cache"] is True
    assert set(audit_cached["mode_1"]["lead_species"]) == set(target_m1.lead_species)
    assert set(audit_cached["mode_1"]["bench_species"]) == set(target_m1.bench_species)
    assert set(audit_cached["mode_2"]["lead_species"]) == set(target_m2.lead_species)
    assert set(audit_cached["mode_2"]["bench_species"]) == set(target_m2.bench_species)
    assert audit_cached["audit_cell_key"] == canonical_deep_audit_cell_key(
        target_m1.lead_species, target_m1.bench_species, target_m2.lead_species, target_m2.bench_species
    )

    # Also verify get_cached_deep_audit rejects species-mismatched payloads
    wrong_m1 = pool1_a.modes[0]
    if canonical_mode_key(wrong_m1.lead_species, wrong_m1.bench_species) != canonical_mode_key(target_m1.lead_species, target_m1.bench_species):
        rejected = st.ots_db.get_cached_deep_audit(
            matchup_hash=m_hash,
            t1_mode_key=canonical_mode_key(target_m1.lead_species, target_m1.bench_species),
            t2_mode_key=canonical_mode_key(target_m2.lead_species, target_m2.bench_species),
            expected_lead_1=wrong_m1.lead_species,
            expected_bench_1=wrong_m1.bench_species,
        )
        assert rejected is None


# =============================================================================
# 5. BO3 CHRONOLOGICAL SORTING (CHROME DUPLICATE FILENAMES + WIRE METADATA)
# =============================================================================


def _make_bo3_game_html(game_num: int, ts_epoch: int, replay_id: str) -> str:
    """Create a realistic Showdown Bo3 HTML replay based on SAMPLE_REPLAY with distinct game number & timestamp."""
    text = re.sub(r"\|t\|\d+", f"|t|{ts_epoch}", SAMPLE_REPLAY, count=1)
    text = re.sub(r'value="[^"]*"', f'value="{replay_id}"', text, count=1)
    bestof_line = f"|uhtml|bestof|<h2><strong>Game {game_num}</strong> of <a href=\"/game-bestof3-test\">a best-of-3</a></h2>"
    return text.replace("|start", f"{bestof_line}\n|start", 1)


def test_bo3_chronological_sorting_handles_chrome_duplicate_filenames(tmp_path: Path) -> None:
    """Scrambled Chrome downloads (`match (1).html`=G2, `match (2).html`=G3, `match.html`=G1)
    must always sort strictly into Game 1 -> Game 2 -> Game 3 across preview & load."""
    g1_html = _make_bo3_game_html(1, 1795600100, "gen9vgc-1001")
    g2_html = _make_bo3_game_html(2, 1795600500, "gen9vgc-1002")
    g3_html = _make_bo3_game_html(3, 1795600900, "gen9vgc-1003")

    scrambled = [
        {"filename": "Gen9VGCBo3-2026-11-26-twomewy-trecesgc (1).html", "raw_input": g2_html},
        {"filename": "Gen9VGCBo3-2026-11-26-twomewy-trecesgc (2).html", "raw_input": g3_html},
        {"filename": "Gen9VGCBo3-2026-11-26-twomewy-trecesgc.html", "raw_input": g1_html},
    ]
    sorted_entries, order_idx = sort_replay_entries(scrambled)
    assert order_idx == [2, 0, 1]
    assert [e["filename"] for e in sorted_entries] == [
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc.html",
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc (1).html",
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc (2).html",
    ]

    k_g1 = extract_replay_sort_key("|start\n|turn|1", "match.html")
    k_g2 = extract_replay_sort_key("|start\n|turn|1", "match (1).html")
    k_g3 = extract_replay_sort_key("|start\n|turn|1", "match (2).html")
    assert k_g1 < k_g2 < k_g3

    st = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "bo3_order.duckdb", device="cpu")
    prev = st.preview_bo3_bundle(replays=scrambled, pov_trainer="treces_gc")
    assert prev["ok"] is True
    assert prev["sorted_order"] == [2, 0, 1]
    assert [g["game_index"] for g in prev["games"]] == [1, 2, 3]
    assert [g["filename"] for g in prev["games"]] == [
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc.html",
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc (1).html",
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc (2).html",
    ]

    loaded = st.load_bo3_bundle(
        replays=scrambled,
        pov_trainer="treces_gc",
        t1_paste_text=SAMPLE_T1,
        t2_paste_text=SAMPLE_T2,
    )
    assert [g["filename"] for g in loaded["bo3_games"]] == [
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc.html",
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc (1).html",
        "Gen9VGCBo3-2026-11-26-twomewy-trecesgc (2).html",
    ]


# =============================================================================
# 6. PERSISTENT DELETION OF BUILT-IN SAMPLE ROSTERS
# =============================================================================


def test_persistent_sample_roster_deletion_and_reimport(tmp_path: Path) -> None:
    """Deleting a built-in seed roster (`matchagotme_camerupt_tr`) must persist across DB restarts."""
    db_file = tmp_path / "persist_delete.duckdb"
    db1 = OTSRosterDatabase(db_path=db_file)
    assert db1.get_roster("matchagotme_camerupt_tr") is not None
    assert db1.get_roster("treces_gc_char_y_v4") is not None

    assert db1.delete_roster("matchagotme_camerupt_tr") is True
    assert db1.get_roster("matchagotme_camerupt_tr") is None
    db1.conn.close()

    # Reopen brand-new DB & AppState on same file -> deleted seed roster must NOT respawn!
    st2 = ReplayCoachAppState(preload_sample=True, db_path=db_file, device="cpu")
    assert st2.ots_db.get_roster("matchagotme_camerupt_tr") is None
    assert st2.ots_db.get_roster("treces_gc_char_y_v4") is not None
    # Sample bundle must still preload cleanly via fallback paste file even when seed roster was deleted!
    assert st2.replay is not None and len(st2.replay.turns) == 10

    # Explicitly re-importing clears dismissal so it persists again
    st2.ots_db.save_roster("matchagotme_camerupt_tr", "MatchaGotMe TR", "MatchaGotMe", SAMPLE_T2)
    st2.ots_db.conn.close()

    db3 = OTSRosterDatabase(db_path=db_file)
    assert db3.get_roster("matchagotme_camerupt_tr") is not None
    db3.conn.close()


# =============================================================================
# 7. REGULATION M-D TOURNAMENT PREP DOSSIER DEPTH & REG M-C ASSET ISOLATION
# =============================================================================


def test_reg_md_dossier_v0_3_0_depth_and_mc_isolation() -> None:
    """Verify the upgraded Regulation M-D Prep Dossier has all 7 deep competitive sections,
    valid inline JS, zero Tera Blast, and zero leaked rumored M-D species into Reg M-C slug_map."""
    py_mini_racer = pytest.importorskip("py_mini_racer")
    dossier_path = REPO_ROOT / "reports" / "reg_md_meta_scout.html"
    assert dossier_path.is_file()
    content = dossier_path.read_text(encoding="utf-8")

    # All 7 deep tabs & interactive widgets present
    for required_id in (
        'id="panel-calcs"',
        'id="panel-shift"',
        'id="panel-speed"',
        'id="panel-playbooks"',
        'id="panel-checker"',
        'id="panel-tiers"',
        'id="panel-blueprints"',
    ):
        assert required_id in content, f"Missing Dossier tab panel: {required_id}"

    # Zero broken sprites & zero Tera Blast (Champions is strictly Tera-free!)
    assert 'src=""' not in content
    assert "Tera Blast" not in content
    assert content.count("data:image/png;base64,") >= 150
    assert "CONFIRMED M-D" in content and "RUMORED / UNCONFIRMED" in content

    # Embedded JS compiles cleanly under V8
    m = re.search(r"<script>(.*?)</script>", content, re.DOTALL)
    assert m is not None
    ctx = py_mini_racer.MiniRacer()
    ctx.eval("new Function(" + repr(m.group(1)) + ");")

    # Verify M-C / Rumored M-D Asset Isolation in assets/slug_map.json
    slug_map = json.loads((REPO_ROOT / "assets" / "slug_map.json").read_text(encoding="utf-8"))
    species_map = slug_map.get("species") or {}
    species_keys = {k.lower() for k in species_map.keys()}
    for rel_path in species_map.values():
        assert "Reg_M-D_rumored" not in str(rel_path), f"Rumored M-D sprite leaked into slug_map: {rel_path}"
    for rumored_only in ("amoonguss", "flamigo", "porygon-z", "latios-mega", "terrakion"):
        assert rumored_only not in species_keys, f"Rumored M-D species '{rumored_only}' leaked into slug_map.json!"
