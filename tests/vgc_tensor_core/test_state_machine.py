# -*- coding: utf-8 -*-
"""
Unified State Machine Verification Suite
========================================
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
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_1_BENCH1,
    SLOT_TRAINER_1_BENCH2,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    SLOT_TRAINER_2_BENCH1,
    SLOT_TRAINER_2_BENCH2,
    TERRAIN_TO_IDX,
    TYPE_TO_IDX,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
)
from engine.vgc_tensor_core.compiler import ShowdownTensorCompiler
from engine.vgc_tensor_core.state_machine import (
    StepResult,
    VgcTensorStateMachine,
    execute_end_of_turn,
)

if HAS_TORCH:
    import torch


def _build_test_roster() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Builds a standardized 8-slot test roster and move matrix."""
    F = np.zeros(FIELD_DIM, dtype=np.float32)
    F[FieldIdx.WEATHER_START] = 1.0  # Clear weather

    P = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
    M = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

    # Slot 0 (trainer_1_a): Sneasler (Water/Fighting)
    P[SLOT_TRAINER_1_A, MonIdx.HP_CUR] = 175.0
    P[SLOT_TRAINER_1_A, MonIdx.HP_MAX] = 175.0
    P[SLOT_TRAINER_1_A, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_TRAINER_1_A, MonIdx.STAT_ATK] = 182.0
    P[SLOT_TRAINER_1_A, MonIdx.STAT_DEF] = 120.0
    P[SLOT_TRAINER_1_A, MonIdx.STAT_SPE] = 149.0
    P[SLOT_TRAINER_1_A, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_TRAINER_1_A, MonIdx.TYPE1_START + TYPE_TO_IDX["water"]] = 1.0
    P[SLOT_TRAINER_1_A, MonIdx.GROUNDED_FLAG] = 1.0

    M[SLOT_TRAINER_1_A, 0, MoveIdx.BASE_POWER] = 120.0
    M[SLOT_TRAINER_1_A, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_TRAINER_1_A, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["fighting"]] = 1.0
    M[SLOT_TRAINER_1_A, 0, MoveIdx.CAT_PHYSICAL] = 1.0

    # Slot 1 (trainer_1_b): Mismagius (Fairy/Ghost - Airborne/Levitate)
    P[SLOT_TRAINER_1_B, MonIdx.HP_CUR] = 135.0
    P[SLOT_TRAINER_1_B, MonIdx.HP_MAX] = 135.0
    P[SLOT_TRAINER_1_B, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_TRAINER_1_B, MonIdx.STAT_SPE] = 205.0
    P[SLOT_TRAINER_1_B, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_TRAINER_1_B, MonIdx.TYPE1_START + TYPE_TO_IDX["fairy"]] = 1.0
    P[SLOT_TRAINER_1_B, MonIdx.GROUNDED_FLAG] = 0.0  # AIRBORNE!

    # Slot 2 (trainer_1_bench1): Rillaboom
    P[SLOT_TRAINER_1_BENCH1, MonIdx.HP_CUR] = 207.0
    P[SLOT_TRAINER_1_BENCH1, MonIdx.HP_MAX] = 207.0
    P[SLOT_TRAINER_1_BENCH1, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_TRAINER_1_BENCH1, MonIdx.STAT_SPE] = 105.0

    # Slot 4 (trainer_2_a): Incineroar (Fire/Dark)
    P[SLOT_TRAINER_2_A, MonIdx.HP_CUR] = 202.0
    P[SLOT_TRAINER_2_A, MonIdx.HP_MAX] = 202.0
    P[SLOT_TRAINER_2_A, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_TRAINER_2_A, MonIdx.STAT_SPE] = 80.0
    P[SLOT_TRAINER_2_A, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_TRAINER_2_A, MonIdx.TYPE1_START + TYPE_TO_IDX["fire"]] = 1.0
    P[SLOT_TRAINER_2_A, MonIdx.GROUNDED_FLAG] = 1.0

    # Slot 5 (trainer_2_b): Venusaur (Grass/Fire)
    P[SLOT_TRAINER_2_B, MonIdx.HP_CUR] = 155.0
    P[SLOT_TRAINER_2_B, MonIdx.HP_MAX] = 155.0
    P[SLOT_TRAINER_2_B, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_TRAINER_2_B, MonIdx.STAT_SPE] = 162.0
    P[SLOT_TRAINER_2_B, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_TRAINER_2_B, MonIdx.TYPE1_START + TYPE_TO_IDX["grass"]] = 1.0
    P[SLOT_TRAINER_2_B, MonIdx.GROUNDED_FLAG] = 1.0

    return F, P, M


def test_end_of_turn_chip_damage(tables: BilinearLookupTables) -> None:
    """Verifies Burn and Sandstorm chip damage at end of turn."""
    print("  [TEST 1] Testing End-of-Turn Chip Damage (Burn & Sandstorm)...")
    F, P, M = _build_test_roster()

    # trainer_1_a has Burn
    P[SLOT_TRAINER_1_A, MonIdx.STATUS_HEALTHY] = 0.0
    P[SLOT_TRAINER_1_A, MonIdx.STATUS_BURN] = 1.0
    t1a_init_hp = float(P[SLOT_TRAINER_1_A, MonIdx.HP_CUR])  # 175.0

    # Set Sandstorm weather
    F[FieldIdx.WEATHER_START] = 0.0
    F[FieldIdx.WEATHER_START + WEATHER_TO_IDX["sand"]] = 1.0
    F[FieldIdx.WEATHER_TURNS] = 5.0

    F_b = np.expand_dims(np.expand_dims(np.expand_dims(F, 0), 0), 0)
    P_b = np.expand_dims(np.expand_dims(np.expand_dims(P, 0), 0), 0)
    M_b = np.expand_dims(np.expand_dims(np.expand_dims(M, 0), 0), 0)

    eot_res = execute_end_of_turn(F_b, P_b, M_b, tables, auto_promote=True)

    # trainer_1_a (Water/Fighting) takes Burn chip (-10 HP: floor(175/16)) AND Sand chip (-10 HP: floor(175/16))
    t1a_end_hp = float(eot_res.mean_hp[0, 0, SLOT_TRAINER_1_A])
    expected_burn_chip = np.floor(175.0 / 16.0)
    expected_sand_chip = np.floor(175.0 / 16.0)
    expected_hp = t1a_init_hp - expected_burn_chip - expected_sand_chip

    assert t1a_end_hp == expected_hp, f"Expected trainer_1_a HP {expected_hp}, got {t1a_end_hp}"
    print(f"    -> PASS: trainer_1_a took Burn (-{expected_burn_chip}) and Sand (-{expected_sand_chip}) chip (HP: {t1a_init_hp} -> {t1a_end_hp}).")


def test_end_of_turn_healing(tables: BilinearLookupTables) -> None:
    """Verifies Grassy Terrain and Leftovers healing with Airborne exemption."""
    print("  [TEST 2] Testing Grassy Terrain & Leftovers Healing (Airborne Exemption)...")
    F, P, M = _build_test_roster()

    # Set Grassy Terrain
    F[FieldIdx.TERRAIN_START] = 0.0
    F[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX["grassy"]] = 1.0
    F[FieldIdx.TERRAIN_TURNS] = 5.0

    # trainer_1_a (Grounded) damaged at 100 HP, holding Leftovers
    P[SLOT_TRAINER_1_A, MonIdx.HP_CUR] = 100.0
    P[SLOT_TRAINER_1_A, MonIdx.ITEM_ID] = ItemID.LEFTOVERS
    P[SLOT_TRAINER_1_A, MonIdx.ITEM_ACTIVE] = 1.0

    # trainer_1_b (Airborne, GROUNDED_FLAG == 0.0) damaged at 80 HP, NO Leftovers
    P[SLOT_TRAINER_1_B, MonIdx.HP_CUR] = 80.0

    F_b = np.expand_dims(np.expand_dims(np.expand_dims(F, 0), 0), 0)
    P_b = np.expand_dims(np.expand_dims(np.expand_dims(P, 0), 0), 0)
    M_b = np.expand_dims(np.expand_dims(np.expand_dims(M, 0), 0), 0)

    eot_res = execute_end_of_turn(F_b, P_b, M_b, tables, auto_promote=True)

    # trainer_1_a should heal Grassy (+10 HP) + Leftovers (+10 HP) = +20 HP -> 120 HP
    t1a_end_hp = float(eot_res.mean_hp[0, 0, SLOT_TRAINER_1_A])
    expected_grassy_heal = np.floor(175.0 / 16.0)
    expected_leftovers_heal = np.floor(175.0 / 16.0)
    expected_t1a = 100.0 + expected_grassy_heal + expected_leftovers_heal
    assert t1a_end_hp == expected_t1a, f"Expected trainer_1_a HP {expected_t1a}, got {t1a_end_hp}"

    # trainer_1_b (Airborne) should receive ZERO Grassy Terrain healing -> stays at 80 HP!
    t1b_end_hp = float(eot_res.mean_hp[0, 0, SLOT_TRAINER_1_B])
    assert t1b_end_hp == 80.0, f"Expected Airborne trainer_1_b HP to remain 80.0, got {t1b_end_hp}"
    print(f"    -> PASS: Grounded trainer_1_a healed +{expected_t1a - 100.0} HP; Airborne trainer_1_b correctly received 0 heal.")


def test_counter_decrements(tables: BilinearLookupTables) -> None:
    """Verifies that field and side condition turn counters decrement properly."""
    print("  [TEST 3] Testing Field & Side Turn Counter Decrements...")
    F, P, M = _build_test_roster()

    F[FieldIdx.WEATHER_TURNS] = 1.0  # Weather ending this turn
    F[FieldIdx.WEATHER_START] = 0.0
    F[FieldIdx.WEATHER_START + WEATHER_TO_IDX["sun"]] = 1.0

    F[FieldIdx.TERRAIN_TURNS] = 2.0  # Terrain has 2 turns left
    F[FieldIdx.TRAINER_1_TAILWIND_TURNS] = 3.0

    F_b = np.expand_dims(np.expand_dims(np.expand_dims(F, 0), 0), 0)
    P_b = np.expand_dims(np.expand_dims(np.expand_dims(P, 0), 0), 0)
    M_b = np.expand_dims(np.expand_dims(np.expand_dims(M, 0), 0), 0)

    eot_res = execute_end_of_turn(F_b, P_b, M_b, tables, auto_promote=True)

    # Weather had 1 turn left -> should decrement to 0 and reset to Clear (0)
    end_w_turns = float(eot_res.F[0, 0, 0, FieldIdx.WEATHER_TURNS])
    end_w_clear = float(eot_res.F[0, 0, 0, FieldIdx.WEATHER_START + WEATHER_TO_IDX["clear"]])
    assert end_w_turns == 0.0, f"Expected weather turns 0.0, got {end_w_turns}"
    assert end_w_clear == 1.0, f"Expected weather to reset to Clear, got {end_w_clear}"

    # Terrain had 2 turns left -> should decrement to 1
    end_t_turns = float(eot_res.F[0, 0, 0, FieldIdx.TERRAIN_TURNS])
    assert end_t_turns == 1.0, f"Expected terrain turns 1.0, got {end_t_turns}"

    # Tailwind had 3 turns left -> should decrement to 2
    end_tw_turns = float(eot_res.F[0, 0, 0, FieldIdx.TRAINER_1_TAILWIND_TURNS])
    assert end_tw_turns == 2.0, f"Expected tailwind turns 2.0, got {end_tw_turns}"
    print("    -> PASS: Weather reset to Clear; Terrain & Tailwind counters decremented by 1.")


def test_protect_streak_reset(tables: BilinearLookupTables) -> None:
    """Verifies that consecutive protect counter resets if Protect is not used."""
    print("  [TEST 4] Testing Protect Streak Consecutive Counter Reset...")
    F, P, M = _build_test_roster()

    # Slot 0 used Protect last turn (PROTECT_COUNTER == 1.0), but did NOT protect this turn (PROTECT_ACTIVE == 0.0)
    P[SLOT_TRAINER_1_A, MonIdx.PROTECT_COUNTER] = 1.0
    P[SLOT_TRAINER_1_A, MonIdx.PROTECT_ACTIVE] = 0.0

    # Slot 4 DID protect this turn (PROTECT_ACTIVE == 1.0, PROTECT_COUNTER == 1.0)
    P[SLOT_TRAINER_2_A, MonIdx.PROTECT_COUNTER] = 1.0
    P[SLOT_TRAINER_2_A, MonIdx.PROTECT_ACTIVE] = 1.0

    F_b = np.expand_dims(np.expand_dims(np.expand_dims(F, 0), 0), 0)
    P_b = np.expand_dims(np.expand_dims(np.expand_dims(P, 0), 0), 0)
    M_b = np.expand_dims(np.expand_dims(np.expand_dims(M, 0), 0), 0)

    eot_res = execute_end_of_turn(F_b, P_b, M_b, tables, auto_promote=True)

    # Slot 0 did NOT protect -> counter reset to 0.0
    t1a_counter = float(eot_res.P[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.PROTECT_COUNTER])
    assert t1a_counter == 0.0, f"Expected trainer_1_a protect counter reset to 0.0, got {t1a_counter}"

    # Slot 4 DID protect -> counter preserved at 1.0, volatile flag reset to 0.0
    t2a_counter = float(eot_res.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.PROTECT_COUNTER])
    t2a_active = float(eot_res.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.PROTECT_ACTIVE])
    assert t2a_counter == 1.0, f"Expected trainer_2_a protect counter to remain 1.0, got {t2a_counter}"
    assert t2a_active == 0.0, f"Expected trainer_2_a volatile protect flag reset to 0.0, got {t2a_active}"
    print("    -> PASS: Protect streak reset for non-protecting slot; preserved for protecting slot.")


def test_auto_replacement_heuristic(tables: BilinearLookupTables) -> None:
    """Verifies that fainted active slots auto-promote the highest equity bench mon."""
    print("  [TEST 5] Testing Compiler Tactical Prior Auto-Replacement Heuristic...")
    F, P, M = _build_test_roster()

    # trainer_1_a fainted during the turn (HP_CUR == 0.0, ALIVE_FLAG == 0.0)
    P[SLOT_TRAINER_1_A, MonIdx.HP_CUR] = 0.0
    P[SLOT_TRAINER_1_A, MonIdx.ALIVE_FLAG] = 0.0

    # Bench 1 (Rillaboom) is alive with Spe 105
    P[SLOT_TRAINER_1_BENCH1, MonIdx.HP_CUR] = 207.0
    P[SLOT_TRAINER_1_BENCH1, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_TRAINER_1_BENCH1, MonIdx.STAT_SPE] = 105.0

    F_b = np.expand_dims(np.expand_dims(np.expand_dims(F, 0), 0), 0)
    P_b = np.expand_dims(np.expand_dims(np.expand_dims(P, 0), 0), 0)
    M_b = np.expand_dims(np.expand_dims(np.expand_dims(M, 0), 0), 0)

    eot_res = execute_end_of_turn(F_b, P_b, M_b, tables, auto_promote=True)

    # After replacement, Slot 0 should now hold Rillaboom (Spe 105, HP 207)
    slot0_hp = float(eot_res.P[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.HP_CUR])
    slot0_spe = float(eot_res.P[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.STAT_SPE])

    assert slot0_hp == 207.0, f"Expected promoted Rillaboom (HP 207) in Slot 0, got {slot0_hp}"
    assert slot0_spe == 105.0, f"Expected promoted Rillaboom (Spe 105) in Slot 0, got {slot0_spe}"
    print(f"    -> PASS: Fainted Slot 0 was automatically replaced by alive Bench 1 (HP: {slot0_hp}, Spe: {slot0_spe}).")


def test_state_machine_full_step() -> None:
    """Tests a complete end-to-end Turn 1 execution via VgcTensorStateMachine.step()."""
    print("  [TEST 6] Testing VgcTensorStateMachine.step() End-to-End Turn 1...")
    sm = VgcTensorStateMachine(backend="numpy")
    F, P, M = _build_test_roster()

    t1_choices = np.zeros((1, 2), dtype=np.int64)
    t2_choices = np.zeros((1, 2), dtype=np.int64)

    step_res: StepResult = sm.step(
        F=F,
        P=P,
        M_moves=M,
        trainer_1_choices=t1_choices,
        trainer_2_choices=t2_choices,
        num_mc_samples=16,
    )

    assert step_res.F.shape == (1, 1, 16, FIELD_DIM), f"Unexpected F shape: {step_res.F.shape}"
    assert step_res.P.shape == (1, 1, 16, ROSTER_SLOTS, MON_DIM), f"Unexpected P shape: {step_res.P.shape}"
    assert step_res.mean_hp.shape == (1, 1, ROSTER_SLOTS), f"Unexpected mean_hp shape: {step_res.mean_hp.shape}"
    assert step_res.faint_prob.shape == (1, 1, ROSTER_SLOTS), f"Unexpected faint_prob shape: {step_res.faint_prob.shape}"
    assert step_res.is_terminal.shape == (1, 1), f"Unexpected is_terminal shape: {step_res.is_terminal.shape}"

    print(f"    -> PASS: Full turn executed cleanly. Mean HP vector: {np.round(step_res.mean_hp[0, 0, :], 1)}")


def test_benchmarks() -> None:
    """Runs performance benchmarks on 1,000 cells across CPU and PyTorch CUDA."""
    print("  [TEST 7] Running Full Turn State Machine Benchmarks (1,000 cells x 16 K-samples)...")
    F, P, M = _build_test_roster()
    B1, B2 = 32, 32  # ~1,024 cells

    F_batch = np.tile(np.expand_dims(np.expand_dims(F, 0), 0), (B1, B2, 1))
    P_batch = np.tile(np.expand_dims(np.expand_dims(P, 0), 0), (B1, B2, 1, 1))
    M_batch = np.tile(np.expand_dims(np.expand_dims(M, 0), 0), (B1, B2, 1, 1, 1))
    p1_choices = np.zeros((B1, 2), dtype=np.int64)
    p2_choices = np.zeros((B2, 2), dtype=np.int64)

    sm_cpu = VgcTensorStateMachine(backend="numpy")
    t0 = time.perf_counter()
    _ = sm_cpu.step(F_batch, P_batch, M_batch, p1_choices, p2_choices, num_mc_samples=16)
    cpu_latency = (time.perf_counter() - t0) * 1000.0
    print(f"    • NumPy CPU Full Turn Latency [1,024 cells x 16 K]: {cpu_latency:.2f} ms")

    if HAS_TORCH and torch.cuda.is_available():
        dev_cuda = torch.device("cuda:0")
        sm_cuda = VgcTensorStateMachine(backend="torch", device=dev_cuda)

        F_cuda = torch.from_numpy(F_batch).to(device=dev_cuda)
        P_cuda = torch.from_numpy(P_batch).to(device=dev_cuda)
        M_cuda = torch.from_numpy(M_batch).to(device=dev_cuda)
        p1_cuda = torch.from_numpy(p1_choices).to(device=dev_cuda)
        p2_cuda = torch.from_numpy(p2_choices).to(device=dev_cuda)

        # Warmup
        _ = sm_cuda.step(F_cuda, P_cuda, M_cuda, p1_cuda, p2_cuda, num_mc_samples=16)
        torch.cuda.synchronize()

        t0_cuda = time.perf_counter()
        _ = sm_cuda.step(F_cuda, P_cuda, M_cuda, p1_cuda, p2_cuda, num_mc_samples=16)
        torch.cuda.synchronize()
        cuda_latency = (time.perf_counter() - t0_cuda) * 1000.0
        print(f"    • PyTorch CUDA Full Turn Latency [1,024 cells x 16 K]: {cuda_latency:.2f} ms on {torch.cuda.get_device_name(0)}")


def main() -> None:
    print("================================================================================")
    print("VGC TENSOR CORE — TEST SUITE: END-OF-TURN & UNIFIED STATE MACHINE")
    print("================================================================================")
    tables = build_bilinear_lookup_tables(device="cpu")

    test_end_of_turn_chip_damage(tables)
    test_end_of_turn_healing(tables)
    test_counter_decrements(tables)
    test_protect_streak_reset(tables)
    test_auto_replacement_heuristic(tables)
    test_state_machine_full_step()
    test_benchmarks()

    print("\nALL STATE MACHINE UNIT TESTS PASSED SUCCESSFULLY!")
    print("================================================================================")


if __name__ == "__main__":
    main()
