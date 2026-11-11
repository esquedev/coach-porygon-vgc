# -*- coding: utf-8 -*-
"""
Vectorized Attack Cascade Engine Verification Suite
===================================================
"""

from __future__ import annotations

import os
import sys
import time
from typing import Dict, Tuple
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from engine.vgc_tensor_core.schema_and_tables import (
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
    TYPE_TO_IDX,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
)
from engine.vgc_tensor_core.phases_pre_attack import (
    execute_pre_attack_phases,
)
from engine.vgc_tensor_core.attack_cascade import (
    AttackCascadeResult,
    execute_attack_cascade,
)

if HAS_TORCH:
    import torch


def _build_test_roster() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Builds a standardized 8-slot test roster and move matrix."""
    F = np.zeros(FIELD_DIM, dtype=np.float32)
    F[FieldIdx.WEATHER_START] = 1.0  # Clear weather

    P = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
    M = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

    # Slot 0 (P1A): Urshifu-Rapid-Strike (Water/Fighting)
    P[SLOT_P1A, MonIdx.HP_CUR] = 175.0
    P[SLOT_P1A, MonIdx.HP_MAX] = 175.0
    P[SLOT_P1A, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P1A, MonIdx.STAT_ATK] = 182.0
    P[SLOT_P1A, MonIdx.STAT_DEF] = 120.0
    P[SLOT_P1A, MonIdx.STAT_SPA] = 74.0
    P[SLOT_P1A, MonIdx.STAT_SPD] = 80.0
    P[SLOT_P1A, MonIdx.STAT_SPE] = 149.0
    P[SLOT_P1A, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P1A, MonIdx.TYPE1_START + TYPE_TO_IDX["water"]] = 1.0
    P[SLOT_P1A, MonIdx.TYPE2_START + TYPE_TO_IDX["fighting"]] = 1.0
    P[SLOT_P1A, MonIdx.GROUNDED_FLAG] = 1.0

    # P1A Move 0: Close Combat (Fighting Physical, BP 120, Prio 0, Single Foe)
    M[SLOT_P1A, 0, MoveIdx.BASE_POWER] = 120.0
    M[SLOT_P1A, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P1A, 0, MoveIdx.PRIORITY] = 0.0
    M[SLOT_P1A, 0, MoveIdx.TARGET_TYPE] = TargetType.SINGLE_FOE
    M[SLOT_P1A, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["fighting"]] = 1.0
    M[SLOT_P1A, 0, MoveIdx.CAT_PHYSICAL] = 1.0

    # P1A Move 1: U-turn (Bug Physical, BP 70, Pivot)
    M[SLOT_P1A, 1, MoveIdx.BASE_POWER] = 70.0
    M[SLOT_P1A, 1, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P1A, 1, MoveIdx.PRIORITY] = 0.0
    M[SLOT_P1A, 1, MoveIdx.TARGET_TYPE] = TargetType.SINGLE_FOE
    M[SLOT_P1A, 1, MoveIdx.TYPE_START + TYPE_TO_IDX["bug"]] = 1.0
    M[SLOT_P1A, 1, MoveIdx.CAT_PHYSICAL] = 1.0
    M[SLOT_P1A, 1, MoveIdx.SWITCH_MODE] = 1.0  # Voluntary Pivot

    # Slot 1 (P1B): Flutter Mane / Whimsicott (Fairy Support)
    P[SLOT_P1B, MonIdx.HP_CUR] = 135.0
    P[SLOT_P1B, MonIdx.HP_MAX] = 135.0
    P[SLOT_P1B, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P1B, MonIdx.STAT_ATK] = 67.0
    P[SLOT_P1B, MonIdx.STAT_DEF] = 75.0
    P[SLOT_P1B, MonIdx.STAT_SPA] = 187.0
    P[SLOT_P1B, MonIdx.STAT_SPD] = 155.0
    P[SLOT_P1B, MonIdx.STAT_SPE] = 205.0
    P[SLOT_P1B, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P1B, MonIdx.TYPE1_START + TYPE_TO_IDX["fairy"]] = 1.0
    P[SLOT_P1B, MonIdx.GROUNDED_FLAG] = 1.0

    # P1B Move 0: Draining Kiss (Fairy Special, BP 50, Drain -0.75)
    M[SLOT_P1B, 0, MoveIdx.BASE_POWER] = 50.0
    M[SLOT_P1B, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P1B, 0, MoveIdx.TARGET_TYPE] = TargetType.SINGLE_FOE
    M[SLOT_P1B, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["fairy"]] = 1.0
    M[SLOT_P1B, 0, MoveIdx.CAT_SPECIAL] = 1.0
    M[SLOT_P1B, 0, MoveIdx.RECOIL_PCT] = -0.75  # 75% Drain

    # Slot 2 (P1 Bench 1): Rillaboom
    P[SLOT_P1_BENCH1, MonIdx.HP_CUR] = 207.0
    P[SLOT_P1_BENCH1, MonIdx.HP_MAX] = 207.0
    P[SLOT_P1_BENCH1, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P1_BENCH1, MonIdx.STAT_SPE] = 105.0

    # Slot 4 (P2A): Incineroar (Fire/Dark)
    P[SLOT_P2A, MonIdx.HP_CUR] = 202.0
    P[SLOT_P2A, MonIdx.HP_MAX] = 202.0
    P[SLOT_P2A, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P2A, MonIdx.STAT_ATK] = 135.0
    P[SLOT_P2A, MonIdx.STAT_DEF] = 110.0
    P[SLOT_P2A, MonIdx.STAT_SPA] = 90.0
    P[SLOT_P2A, MonIdx.STAT_SPD] = 110.0
    P[SLOT_P2A, MonIdx.STAT_SPE] = 80.0
    P[SLOT_P2A, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P2A, MonIdx.TYPE1_START + TYPE_TO_IDX["fire"]] = 1.0
    P[SLOT_P2A, MonIdx.TYPE2_START + TYPE_TO_IDX["dark"]] = 1.0
    P[SLOT_P2A, MonIdx.GROUNDED_FLAG] = 1.0

    # P2A Move 0: Flare Blitz (Fire Physical, BP 120, Recoil 0.33)
    M[SLOT_P2A, 0, MoveIdx.BASE_POWER] = 120.0
    M[SLOT_P2A, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P2A, 0, MoveIdx.TARGET_TYPE] = TargetType.SINGLE_FOE
    M[SLOT_P2A, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["fire"]] = 1.0
    M[SLOT_P2A, 0, MoveIdx.CAT_PHYSICAL] = 1.0
    M[SLOT_P2A, 0, MoveIdx.RECOIL_PCT] = 0.33

    # Slot 5 (P2B): Ogerpon-Hearthflame (Grass/Fire)
    P[SLOT_P2B, MonIdx.HP_CUR] = 155.0
    P[SLOT_P2B, MonIdx.HP_MAX] = 155.0
    P[SLOT_P2B, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P2B, MonIdx.STAT_ATK] = 172.0
    P[SLOT_P2B, MonIdx.STAT_DEF] = 104.0
    P[SLOT_P2B, MonIdx.STAT_SPA] = 72.0
    P[SLOT_P2B, MonIdx.STAT_SPD] = 116.0
    P[SLOT_P2B, MonIdx.STAT_SPE] = 162.0
    P[SLOT_P2B, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P2B, MonIdx.TYPE1_START + TYPE_TO_IDX["grass"]] = 1.0
    P[SLOT_P2B, MonIdx.TYPE2_START + TYPE_TO_IDX["fire"]] = 1.0
    P[SLOT_P2B, MonIdx.GROUNDED_FLAG] = 1.0

    # P2B Move 0: Follow Me (+2 prio)
    M[SLOT_P2B, 0, MoveIdx.BASE_POWER] = 0.0
    M[SLOT_P2B, 0, MoveIdx.PRIORITY] = 2.0
    M[SLOT_P2B, 0, MoveIdx.TARGET_TYPE] = TargetType.SELF
    M[SLOT_P2B, 0, MoveIdx.FIELD_OP_ID] = 15.0  # Follow Me

    # Slot 6 (P2 Bench 1): Chien-Pao
    P[SLOT_P2_BENCH1, MonIdx.HP_CUR] = 155.0
    P[SLOT_P2_BENCH1, MonIdx.HP_MAX] = 155.0
    P[SLOT_P2_BENCH1, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P2_BENCH1, MonIdx.STAT_SPE] = 187.0

    return F, P, M


def test_follow_me_redirection(tables: BilinearLookupTables) -> None:
    """Verifies that Follow Me successfully redirects single-target attacks away from partner."""
    print("  [TEST 0] Testing Follow Me Single-Target Redirection...")
    F, P, M = _build_test_roster()

    # Remove Flare Blitz recoil on P2A so it doesn't chip itself when attacking
    M[SLOT_P2A, 0, MoveIdx.RECOIL_PCT] = 0.0

    # P2B uses Follow Me (FIELD_OP_ID == 15.0, priority +2)
    # P1A targets P2A (Opp A) with Close Combat
    p1_choices = np.zeros((1, 2), dtype=np.int64)
    p1_choices[0, 0] = 0  # P1A -> Opp A (P2A)
    p1_choices[0, 1] = 4  # P1B -> Opp B (P2B)
    p2_choices = np.zeros((1, 2), dtype=np.int64)

    F_batch = np.expand_dims(np.expand_dims(F, 0), 0)
    P_batch = np.expand_dims(np.expand_dims(P, 0), 0)
    M_batch = np.expand_dims(np.expand_dims(M, 0), 0)

    pre_res = execute_pre_attack_phases(F_batch, P_batch, M_batch, p1_choices, p2_choices, tables)
    cascade_res = execute_attack_cascade(F_batch, P_batch, M_batch, p1_choices, p2_choices, pre_res, tables, num_mc_samples=16)

    # P2A should take ZERO damage because P1A was redirected to P2B
    p2a_mean_hp = float(cascade_res.mean_hp[0, 0, SLOT_P2A])
    p2b_mean_hp = float(cascade_res.mean_hp[0, 0, SLOT_P2B])

    assert p2a_mean_hp == 202.0, f"Expected P2A to take 0 damage due to Follow Me, got HP {p2a_mean_hp}"
    assert p2b_mean_hp < 155.0, f"Expected P2B to take redirected damage from Follow Me, got HP {p2b_mean_hp}"
    print(f"    -> PASS: Follow Me successfully redirected attack away from P2A (HP: 202.0) into P2B (HP: {p2b_mean_hp:.1f}).")


def test_focus_sash_and_sturdy_clamp(tables: BilinearLookupTables) -> None:
    """Verifies Focus Sash and Sturdy 1 HP survival clamp from lethal damage."""
    print("  [TEST 1] Testing Focus Sash & Sturdy 1 HP Clamping...")
    F, P, M = _build_test_roster()

    # Give P2A (Incineroar) Focus Sash at 100% HP, and remove Flare Blitz recoil so it survives its own attack
    P[SLOT_P2A, MonIdx.ITEM_ID] = ItemID.FOCUS_SASH
    P[SLOT_P2A, MonIdx.ITEM_ACTIVE] = 1.0
    M[SLOT_P2A, 0, MoveIdx.RECOIL_PCT] = 0.0
    # Disable Follow Me on P2B so P1A hits P2A directly
    M[SLOT_P2B, 0, MoveIdx.FIELD_OP_ID] = 0.0

    # Give P1A (Urshifu) immense Attack to guarantee overkill
    P[SLOT_P1A, MonIdx.STAT_ATK] = 500.0

    # Actions: P1A uses Close Combat -> Opp A (Incineroar). P1B attacks Opp B (so P2A only takes 1 hit)
    p1_choices = np.zeros((1, 2), dtype=np.int64)
    p1_choices[0, 0] = 0  # P1A -> Opp A
    p1_choices[0, 1] = 4  # P1B -> Opp B (choice 4 is Move 0 -> Opp B)
    p2_choices = np.zeros((1, 2), dtype=np.int64)

    F_batch = np.expand_dims(np.expand_dims(F, 0), 0)
    P_batch = np.expand_dims(np.expand_dims(P, 0), 0)
    M_batch = np.expand_dims(np.expand_dims(M, 0), 0)

    pre_res = execute_pre_attack_phases(F_batch, P_batch, M_batch, p1_choices, p2_choices, tables)
    cascade_res = execute_attack_cascade(F_batch, P_batch, M_batch, p1_choices, p2_choices, pre_res, tables, num_mc_samples=16)

    # Check P2A HP across samples
    mean_hp_p2a = float(cascade_res.mean_hp[0, 0, SLOT_P2A])
    sash_active = float(cascade_res.P[0, 0, 0, SLOT_P2A, MonIdx.ITEM_ACTIVE])

    assert mean_hp_p2a == 1.0, f"Expected Focus Sash to clamp HP to 1.0, got {mean_hp_p2a}"
    assert sash_active == 0.0, f"Expected Focus Sash to be consumed (ITEM_ACTIVE=0.0), got {sash_active}"
    assert cascade_res.faint_prob[0, 0, SLOT_P2A] == 0.0, "Expected faint probability 0.0 with Sash"
    print("    -> PASS: Focus Sash clamped lethal damage to 1 HP and consumed item.")


def test_ko_target_redirection_xor(tables: BilinearLookupTables) -> None:
    """Verifies that if Opp A faints in Step 0, Step 1 single-target attacks redirect to Opp B."""
    print("  [TEST 2] Testing KO Target Redirection XOR...")
    F, P, M = _build_test_roster()

    # Set P2A to 10 HP so P1B (faster slot) KOs it in Step 0
    P[SLOT_P2A, MonIdx.HP_CUR] = 10.0

    # Disable Follow Me on P2B for this test so single-target attacks hit declared targets
    M[SLOT_P2B, 0, MoveIdx.FIELD_OP_ID] = 0.0

    # P1B (Spe 205) attacks Opp A with Move 0 (Draining Kiss)
    # P1A (Spe 149) ALSO attacks Opp A with Move 0 (Close Combat)
    p1_choices = np.zeros((1, 2), dtype=np.int64)
    p1_choices[0, 0] = 0  # P1A -> Opp A
    p1_choices[0, 1] = 0  # P1B -> Opp A
    p2_choices = np.zeros((1, 2), dtype=np.int64)

    F_batch = np.expand_dims(np.expand_dims(F, 0), 0)
    P_batch = np.expand_dims(np.expand_dims(P, 0), 0)
    M_batch = np.expand_dims(np.expand_dims(M, 0), 0)

    pre_res = execute_pre_attack_phases(F_batch, P_batch, M_batch, p1_choices, p2_choices, tables)
    cascade_res = execute_attack_cascade(F_batch, P_batch, M_batch, p1_choices, p2_choices, pre_res, tables, num_mc_samples=16)

    # P2A should be dead
    p2a_faint = float(cascade_res.faint_prob[0, 0, SLOT_P2A])
    assert p2a_faint == 1.0, f"Expected P2A to faint, got faint_prob={p2a_faint}"

    # P2B should have taken damage from P1A's redirected Close Combat!
    p2b_initial_hp = 155.0
    p2b_mean_hp = float(cascade_res.mean_hp[0, 0, SLOT_P2B])
    assert p2b_mean_hp < p2b_initial_hp, f"Expected P2B to take redirected damage, got HP {p2b_mean_hp}"
    assert len(cascade_res.redirection_events) > 0, "Expected redirection event log entry"
    print(f"    -> PASS: KO Redirection redirected attack to P2B (HP: {p2b_initial_hp} -> {p2b_mean_hp:.1f}).")


def test_life_orb_and_drain_moves(tables: BilinearLookupTables) -> None:
    """Verifies Life Orb 10% recoil and Draining Kiss 75% drain healing."""
    print("  [TEST 3] Testing Life Orb Recoil and Move Drain Healing...")
    F, P, M = _build_test_roster()

    # Give P1A Life Orb
    P[SLOT_P1A, MonIdx.ITEM_ID] = ItemID.LIFE_ORB
    P[SLOT_P1A, MonIdx.ITEM_ACTIVE] = 1.0
    p1a_initial_hp = float(P[SLOT_P1A, MonIdx.HP_CUR])  # 175
    M[SLOT_P2B, 0, MoveIdx.FIELD_OP_ID] = 0.0  # Disable Follow Me

    # Damaged P1B at 50 HP (out of 135) to test Draining Kiss heal
    P[SLOT_P1B, MonIdx.HP_CUR] = 50.0

    p1_choices = np.zeros((1, 2), dtype=np.int64)
    p2_choices = np.zeros((1, 2), dtype=np.int64)

    F_batch = np.expand_dims(np.expand_dims(F, 0), 0)
    P_batch = np.expand_dims(np.expand_dims(P, 0), 0)
    M_batch = np.expand_dims(np.expand_dims(M, 0), 0)

    pre_res = execute_pre_attack_phases(F_batch, P_batch, M_batch, p1_choices, p2_choices, tables)
    cascade_res = execute_attack_cascade(F_batch, P_batch, M_batch, p1_choices, p2_choices, pre_res, tables, num_mc_samples=16)

    # P1A should take 10% recoil (17 HP) -> 158 HP
    p1a_mean_hp = float(cascade_res.mean_hp[0, 0, SLOT_P1A])
    expected_lo_recoil = np.floor(175.0 * 0.10)
    assert p1a_mean_hp == (p1a_initial_hp - expected_lo_recoil), f"Expected P1A HP {p1a_initial_hp - expected_lo_recoil}, got {p1a_mean_hp}"

    # P1B used Draining Kiss -> healed HP should be > 50.0
    p1b_mean_hp = float(cascade_res.mean_hp[0, 0, SLOT_P1B])
    assert p1b_mean_hp > 50.0, f"Expected P1B to heal from Draining Kiss, got HP {p1b_mean_hp}"
    print(f"    -> PASS: Life Orb recoil applied (-{expected_lo_recoil} HP) and Drain healed (+{p1b_mean_hp - 50.0:.1f} HP).")


def test_monte_carlo_roll_variance_alert(tables: BilinearLookupTables) -> None:
    """Verifies that when damage roll straddles KO threshold, roll_variance_alert triggers."""
    print("  [TEST 4] Testing Monte Carlo Roll Variance Alert...")
    F, P, M = _build_test_roster()

    # Find the exact damage range of Close Combat from P1A into P2A
    # At neutral, CC does ~150-180 damage to Incineroar.
    # Min damage of CC is 224, Max is 266. Set HP to 245.0 so exactly 8 rolls KO and 8 rolls survive!
    P[SLOT_P2A, MonIdx.HP_CUR] = 245.0
    P[SLOT_P2A, MonIdx.HP_MAX] = 245.0
    M[SLOT_P2B, 0, MoveIdx.FIELD_OP_ID] = 0.0  # Disable Follow Me

    p1_choices = np.zeros((1, 2), dtype=np.int64)
    p1_choices[0, 0] = 0  # P1A -> Opp A (P2A)
    p1_choices[0, 1] = 4  # P1B -> Opp B (P2B)
    p2_choices = np.zeros((1, 2), dtype=np.int64)

    F_batch = np.expand_dims(np.expand_dims(F, 0), 0)
    P_batch = np.expand_dims(np.expand_dims(P, 0), 0)
    M_batch = np.expand_dims(np.expand_dims(M, 0), 0)

    pre_res = execute_pre_attack_phases(F_batch, P_batch, M_batch, p1_choices, p2_choices, tables)
    cascade_res = execute_attack_cascade(F_batch, P_batch, M_batch, p1_choices, p2_choices, pre_res, tables, num_mc_samples=16)

    faint_prob = float(cascade_res.faint_prob[0, 0, SLOT_P2A])
    var_alert = float(cascade_res.roll_variance_alert[0, 0, SLOT_P2A])

    print(f"    Empirical Faint Probability for P2A across 16 rolls: {faint_prob * 100.0:.1f}%")
    assert 0.0 < faint_prob < 1.0, f"Expected roll-dependent survival (0 < p < 1), got {faint_prob}"
    assert var_alert == 1.0, f"Expected roll_variance_alert == 1.0, got {var_alert}"
    print("    -> PASS: Roll variance alert successfully triggered on straddled damage threshold.")


def test_voluntary_pivot_execution(tables: BilinearLookupTables) -> None:
    """Verifies that U-turn executes in-place bench swap upon dealing damage."""
    print("  [TEST 5] Testing Mid-Turn Voluntary Pivot (U-turn)...")
    F, P, M = _build_test_roster()

    # P1A chooses Move 1 (U-turn) -> Opp A (choice 1)
    M[SLOT_P2B, 0, MoveIdx.FIELD_OP_ID] = 0.0  # Disable Follow Me
    p1_choices = np.zeros((1, 2), dtype=np.int64)
    p1_choices[0, 0] = 1  # Move 1 (U-turn -> Opp A)
    p1_choices[0, 1] = 4  # Move 0 -> Opp B
    p2_choices = np.zeros((1, 2), dtype=np.int64)

    F_batch = np.expand_dims(np.expand_dims(F, 0), 0)
    P_batch = np.expand_dims(np.expand_dims(P, 0), 0)
    M_batch = np.expand_dims(np.expand_dims(M, 0), 0)

    pre_res = execute_pre_attack_phases(F_batch, P_batch, M_batch, p1_choices, p2_choices, tables)
    cascade_res = execute_attack_cascade(F_batch, P_batch, M_batch, p1_choices, p2_choices, pre_res, tables, num_mc_samples=16)

    # After U-turn, Slot 0 (P1A) should now hold Rillaboom (Spe 105, HP 207)
    # and Slot 2 (Bench 1) should hold Urshifu (Spe 149, HP 175)
    slot0_spe = float(cascade_res.P[0, 0, 0, SLOT_P1A, MonIdx.STAT_SPE])
    bench1_spe = float(cascade_res.P[0, 0, 0, SLOT_P1_BENCH1, MonIdx.STAT_SPE])

    assert slot0_spe == 105.0, f"Expected Rillaboom (Spe 105) in Slot 0, got {slot0_spe}"
    assert bench1_spe == 149.0, f"Expected Urshifu (Spe 149) in Bench 1, got {bench1_spe}"
    print("    -> PASS: U-turn swapped Urshifu to Bench and promoted Rillaboom.")


def test_benchmarks() -> None:
    """Benchmarks 10,000 cells (100x100) across K=16 Monte Carlo samples on CPU and CUDA."""
    print("  [TEST 6] Running Performance Benchmarks (10,000 cells x 16 K-samples)...")
    F, P, M = _build_test_roster()
    B1, B2 = 100, 100

    F_batch = np.tile(np.expand_dims(np.expand_dims(F, 0), 0), (B1, B2, 1))
    P_batch = np.tile(np.expand_dims(np.expand_dims(P, 0), 0), (B1, B2, 1, 1))
    M_batch = np.tile(np.expand_dims(np.expand_dims(M, 0), 0), (B1, B2, 1, 1, 1))
    p1_choices = np.zeros((B1, 2), dtype=np.int64)
    p2_choices = np.zeros((B2, 2), dtype=np.int64)

    tables_cpu = build_bilinear_lookup_tables(device="cpu")
    pre_res_cpu = execute_pre_attack_phases(F_batch, P_batch, M_batch, p1_choices, p2_choices, tables_cpu)

    # CPU Benchmark
    t0 = time.perf_counter()
    res_cpu = execute_attack_cascade(F_batch, P_batch, M_batch, p1_choices, p2_choices, pre_res_cpu, tables_cpu, num_mc_samples=16)
    cpu_latency = (time.perf_counter() - t0) * 1000.0
    print(f"    • NumPy CPU Latency [10,000 cells x 16 K]: {cpu_latency:.2f} ms")

    # CUDA Benchmark if available
    if HAS_TORCH and torch.cuda.is_available():
        dev_cuda = torch.device("cuda:0")
        tables_cuda = build_bilinear_lookup_tables(device=dev_cuda)
        F_cuda = torch.from_numpy(F_batch).to(device=dev_cuda)
        P_cuda = torch.from_numpy(P_batch).to(device=dev_cuda)
        M_cuda = torch.from_numpy(M_batch).to(device=dev_cuda)
        p1_cuda = torch.from_numpy(p1_choices).to(device=dev_cuda)
        p2_cuda = torch.from_numpy(p2_choices).to(device=dev_cuda)

        pre_res_cuda = execute_pre_attack_phases(F_cuda, P_cuda, M_cuda, p1_cuda, p2_cuda, tables_cuda)

        # Warmup
        _ = execute_attack_cascade(F_cuda, P_cuda, M_cuda, p1_cuda, p2_cuda, pre_res_cuda, tables_cuda, num_mc_samples=16)
        torch.cuda.synchronize()

        t0_cuda = time.perf_counter()
        _ = execute_attack_cascade(F_cuda, P_cuda, M_cuda, p1_cuda, p2_cuda, pre_res_cuda, tables_cuda, num_mc_samples=16)
        torch.cuda.synchronize()
        cuda_latency = (time.perf_counter() - t0_cuda) * 1000.0
        print(f"    • PyTorch CUDA Latency [10,000 cells x 16 K]: {cuda_latency:.2f} ms on {torch.cuda.get_device_name(0)}")
    else:
        print("    • PyTorch CUDA: Skipped (CUDA not detected)")


def main() -> None:
    print("================================================================================")
    print("VGC TENSOR CORE TEST SUITE: VECTORIZED ATTACK CASCADE")
    print("================================================================================")
    tables = build_bilinear_lookup_tables(device="cpu")

    test_follow_me_redirection(tables)
    test_focus_sash_and_sturdy_clamp(tables)
    test_ko_target_redirection_xor(tables)
    test_life_orb_and_drain_moves(tables)
    test_monte_carlo_roll_variance_alert(tables)
    test_voluntary_pivot_execution(tables)
    test_benchmarks()

    print("\nALL ATTACK CASCADE UNIT TESTS PASSED SUCCESSFULLY!")
    print("================================================================================")


if __name__ == "__main__":
    main()
