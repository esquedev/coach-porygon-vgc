# -*- coding: utf-8 -*-
"""
VGC Tensor Core — Full Bo3 Tournament Match Simulator
=====================================================

Simulates an entire Best-of-3 competitive VGC Doubles match (Game 1, Game 2, and
Decider Game 3 if tied) between two regulation rosters:
- Evaluates multi-turn state transitions from Turn 1 to Game Over.
- Chains state vectors seamlessly across turns.
- Generates rich esports telemetry and matrix calc evidence per turn using
  `vgc_tensor_core/telemetry_formatter.py`.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Dict, List, Tuple
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from vgc_tensor_core.schema_and_tables import (
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
)
from vgc_tensor_core.state_machine import VgcTensorStateMachine, StepResult
from vgc_tensor_core.telemetry_formatter import (
    format_cuda_device_header,
    format_full_turn_report,
)

if HAS_TORCH:
    import torch


def _to_numpy(x: Any) -> np.ndarray:
    if HAS_TORCH and isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def _build_initial_teams() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Builds two balanced competitive 4-mon teams."""
    F = np.zeros(FIELD_DIM, dtype=np.float32)
    F[FieldIdx.WEATHER_START] = 1.0  # Clear

    P = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
    M = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

    # Player 1 Team: Urshifu-Rapid (0), Flutter Mane (1), Rillaboom (2), Chien-Pao (3)
    # Slot 0: Urshifu
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
    P[SLOT_P1A, MonIdx.GROUNDED_FLAG] = 1.0

    M[SLOT_P1A, 0, MoveIdx.BASE_POWER] = 120.0  # Close Combat
    M[SLOT_P1A, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P1A, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["fighting"]] = 1.0
    M[SLOT_P1A, 0, MoveIdx.CAT_PHYSICAL] = 1.0

    # Slot 1: Flutter Mane
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

    M[SLOT_P1B, 0, MoveIdx.BASE_POWER] = 80.0  # Dazzling Gleam (Spread)
    M[SLOT_P1B, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P1B, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["fairy"]] = 1.0
    M[SLOT_P1B, 0, MoveIdx.CAT_SPECIAL] = 1.0
    M[SLOT_P1B, 0, MoveIdx.TARGET_TYPE] = TargetType.ALL_ADJACENT_FOES

    # P1 Bench 1: Rillaboom
    P[SLOT_P1_BENCH1, MonIdx.HP_CUR] = 207.0
    P[SLOT_P1_BENCH1, MonIdx.HP_MAX] = 207.0
    P[SLOT_P1_BENCH1, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P1_BENCH1, MonIdx.STAT_SPE] = 105.0

    # Player 2 Team: Incineroar (4), Ogerpon (5), Landorus (6), Kingambit (7)
    # Slot 4: Incineroar
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
    P[SLOT_P2A, MonIdx.GROUNDED_FLAG] = 1.0

    M[SLOT_P2A, 0, MoveIdx.BASE_POWER] = 85.0  # Flare Blitz / Knock Off
    M[SLOT_P2A, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P2A, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["dark"]] = 1.0
    M[SLOT_P2A, 0, MoveIdx.CAT_PHYSICAL] = 1.0

    # Slot 5: Ogerpon
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
    P[SLOT_P2B, MonIdx.GROUNDED_FLAG] = 1.0

    M[SLOT_P2B, 0, MoveIdx.BASE_POWER] = 120.0  # Ivy Cudgel
    M[SLOT_P2B, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P2B, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["grass"]] = 1.0
    M[SLOT_P2B, 0, MoveIdx.CAT_PHYSICAL] = 1.0

    # P2 Bench 1: Kingambit
    P[SLOT_P2_BENCH1, MonIdx.HP_CUR] = 207.0
    P[SLOT_P2_BENCH1, MonIdx.HP_MAX] = 207.0
    P[SLOT_P2_BENCH1, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P2_BENCH1, MonIdx.STAT_SPE] = 70.0

    return F, P, M


def simulate_game(sm: VgcTensorStateMachine, game_num: int, rng_seed: int = 42) -> Tuple[int, List[str]]:
    """Simulates a single competitive game from Turn 1 until a player achieves 4 KOs."""
    game_logs: List[str] = []
    game_logs.append(f"\n================================================================================")
    game_logs.append(f"                           GAME {game_num} SIMULATION START")
    game_logs.append(f"================================================================================")

    F, P, M = _build_initial_teams()
    rng = np.random.RandomState(rng_seed)

    turn = 1
    winner = 0

    while turn <= 10:
        game_logs.append(f"\n>>> TURN {turn} EXECUTION >>>")

        # Heuristic actions: P1 attacks Opp A and Opp B; P2 attacks P1
        p1_c = np.zeros((1, 2), dtype=np.int64)
        p1_c[0, 0] = 0  # Urshifu -> Opp A
        p1_c[0, 1] = 0  # Flutter Mane -> Spread Dazzling Gleam

        p2_c = np.zeros((1, 2), dtype=np.int64)
        p2_c[0, 0] = 0  # Incineroar -> Slot 0
        p2_c[0, 1] = 0  # Ogerpon -> Slot 0

        step_res = sm.step(
            F=F,
            P=P,
            M_moves=M,
            p1_choices=p1_c,
            p2_choices=p2_c,
            num_mc_samples=16,
            rng_seed=rng_seed + turn,
        )

        turn_report = format_full_turn_report(step_res, cell_b1=0, cell_b2=0, device=sm.device)
        game_logs.append(turn_report)

        is_term = bool(_to_numpy(step_res.is_terminal)[0, 0] > 0.5)
        if is_term:
            winner = int(_to_numpy(step_res.winner)[0, 0])
            game_logs.append(f"\n*** GAME {game_num} COMPLETED ON TURN {turn}! WINNER: PLAYER {winner} ***")
            break

        # State transition: next turn takes output of current turn (using sample 0 as representative)
        if HAS_TORCH and isinstance(step_res.P, torch.Tensor):
            F = step_res.F[:, :, 0, :].clone()
            P = step_res.P[:, :, 0, :, :].clone()
            M = step_res.M_moves[:, :, 0, :, :, :].clone()
        else:
            F = step_res.F[:, :, 0, :].copy()
            P = step_res.P[:, :, 0, :, :].copy()
            M = step_res.M_moves[:, :, 0, :, :, :].copy()

        turn += 1

    if winner == 0:
        # Resolve by remaining HP if max turns reached
        p1_hp = float(np.sum(_to_numpy(P)[0, 0, 0:4, MonIdx.HP_CUR]))
        p2_hp = float(np.sum(_to_numpy(P)[0, 0, 4:8, MonIdx.HP_CUR]))
        winner = 1 if p1_hp >= p2_hp else 2
        game_logs.append(f"\n*** TURN LIMIT REACHED. RESOLVED BY HP (P1: {p1_hp:.0f} vs P2: {p2_hp:.0f}) -> WINNER: PLAYER {winner} ***")

    return winner, game_logs


def simulate_full_bo3_match() -> str:
    """Executes a full Best-of-3 tournament match."""
    device = torch.device("cuda:0") if HAS_TORCH and torch.cuda.is_available() else "cpu"
    sm = VgcTensorStateMachine(backend="torch" if HAS_TORCH else "numpy", device=device)

    all_logs: List[str] = []
    all_logs.append("================================================================================================")
    all_logs.append("VGC TENSOR CORE 2.0 — FULL BEST-OF-3 (Bo3) TOURNAMENT SIMULATION")
    all_logs.append("================================================================================================")
    all_logs.append(format_cuda_device_header(sm.device))

    p1_wins = 0
    p2_wins = 0

    # Game 1
    w1, logs1 = simulate_game(sm, game_num=1, rng_seed=101)
    all_logs.extend(logs1)
    if w1 == 1:
        p1_wins += 1
    else:
        p2_wins += 1

    # Game 2
    w2, logs2 = simulate_game(sm, game_num=2, rng_seed=202)
    all_logs.extend(logs2)
    if w2 == 1:
        p1_wins += 1
    else:
        p2_wins += 1

    # Game 3 if needed
    if p1_wins == 1 and p2_wins == 1:
        w3, logs3 = simulate_game(sm, game_num=3, rng_seed=303)
        all_logs.extend(logs3)
        if w3 == 1:
            p1_wins += 1
        else:
            p2_wins += 1

    match_winner = "PLAYER 1" if p1_wins > p2_wins else "PLAYER 2"
    all_logs.append("\n================================================================================================")
    all_logs.append(f"MATCH CONCLUSION: {match_winner} WINS THE Bo3 SERIES ({p1_wins} - {p2_wins})")
    all_logs.append("================================================================================================")

    res_str = "\n".join(all_logs)
    print(f"\nBo3 Simulation Finished! Series Score: P1 ({p1_wins}) - P2 ({p2_wins}).")
    return res_str


def main() -> None:
    res = simulate_full_bo3_match()
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "bo3_simulation_output.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(res)
    print(f"Full tournament dossier written to: {out_path}")


if __name__ == "__main__":
    main()
