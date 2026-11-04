# -*- coding: utf-8 -*-
"""
VGC AI Agent: Turn 1 Automated Solver & Verbose Strategy Inspector
===================================================================
Chains Compiler Masks -> Parallel GPU State Machine -> Heuristic Evaluator -> Nash LP Solver.
Provides verbose telemetry, switch-line isolation, and turn playbacks.
"""

import sys
from pathlib import Path

# Add project root directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch
from scipy.optimize import linprog

from vgc_tensor_core.schema_and_tables import (
    build_bilinear_lookup_tables, 
    HAS_TORCH,
    MonIdx,
    SLOT_P1A,
    SLOT_P1B,
    SLOT_P1_BENCH1,
    SLOT_P1_BENCH2,
    SLOT_P2A,
    SLOT_P2B,
    SLOT_P2_BENCH1,
    SLOT_P2_BENCH2,
)
from vgc_tensor_core.compiler import (
    ShowdownTensorCompiler, 
    CompiledBattleState,
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
)
from vgc_tensor_core.state_machine import VgcTensorStateMachine
from vgc_tensor_core.state_translator import ShowdownStateTranslator
from vgc_tensor_core.replay_unroller import ReplayTurnExpectation, ShowdownReplayUnroller
from vgc_tensor_core.tests.test_replay_verifier import _build_game1_initial_state, _build_game1_manifest

# =====================================================================
# 1. ACTION DECODER HELPER
# =====================================================================
def decode_single_choice(actor_slot: int, choice_val: int, manifest) -> str:
    """Translates a discrete choice ID (0..25) into an English tactical action string."""
    actor_meta = manifest.slots[actor_slot]
    name = actor_meta.display_name

    if choice_val == CHOICE_SWITCH_BENCH1:
        bench_slot = SLOT_P1_BENCH1 if actor_slot < 4 else SLOT_P2_BENCH1
        bench_name = manifest.slots[bench_slot].display_name
        return f"{name} [SWITCH -> {bench_name}]"
    
    if choice_val == CHOICE_SWITCH_BENCH2:
        bench_slot = SLOT_P1_BENCH2 if actor_slot < 4 else SLOT_P2_BENCH2
        bench_name = manifest.slots[bench_slot].display_name
        return f"{name} [SWITCH -> {bench_name}]"

    is_mega = (12 <= choice_val <= 23)
    move_idx = choice_val % 4
    target_code = (choice_val // 4) % 3

    move_name = actor_meta.moves[move_idx] if move_idx < len(actor_meta.moves) else f"Move_{move_idx}"
    
    # Target resolution
    if actor_slot in (SLOT_P1A, SLOT_P1B):
        target_name = manifest.slots[SLOT_P2A].display_name if target_code == 0 else (
            manifest.slots[SLOT_P2B].display_name if target_code == 1 else
            (manifest.slots[SLOT_P1B].display_name if actor_slot == SLOT_P1A else manifest.slots[SLOT_P1A].display_name)
        )
    else:
        target_name = manifest.slots[SLOT_P1A].display_name if target_code == 0 else (
            manifest.slots[SLOT_P1B].display_name if target_code == 1 else
            (manifest.slots[SLOT_P2B].display_name if actor_slot == SLOT_P2A else manifest.slots[SLOT_P2A].display_name)
        )

    mega_str = "<MEGA> " if is_mega else ""
    return f"{name}: {mega_str}{move_name} -> {target_name}"

def format_joint_action(side: str, coords: tuple[int, int], manifest) -> str:
    """Formats a pair of actions (Slot A + Slot B) for one player."""
    slot_a = SLOT_P1A if side == "p1" else SLOT_P2A
    slot_b = SLOT_P1B if side == "p1" else SLOT_P2B
    desc_a = decode_single_choice(slot_a, int(coords[0]), manifest)
    desc_b = decode_single_choice(slot_b, int(coords[1]), manifest)
    return f"({desc_a})  ||  ({desc_b})"

def contains_switch(choice_pair: tuple[int, int]) -> bool:
    """Returns True if either slot choice represents a voluntary bench switch."""
    return (int(choice_pair[0]) in (CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH2) or
            int(choice_pair[1]) in (CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH2))

# =====================================================================
# 2. HEURISTIC EVALUATOR
# =====================================================================
def evaluate_payoff_matrix(step_res, P_pre_attack):
    """
    Evaluates the board state across the [B1, B2] matrix.
    Positive scores favor Player 1, negative scores favor Player 2.
    """
    hp_pct = step_res.mean_hp / torch.clamp(P_pre_attack[..., 1], min=1.0)
    faint_risk = step_res.faint_prob
    
    faint_penalty = 2.5
    
    p1_active_score = torch.sum(hp_pct[..., 0:2] - (faint_risk[..., 0:2] * faint_penalty), dim=-1)
    p1_bench_score = torch.sum(hp_pct[..., 2:4] - (faint_risk[..., 2:4] * faint_penalty), dim=-1)
    
    p2_active_score = torch.sum(hp_pct[..., 4:6] - (faint_risk[..., 4:6] * faint_penalty), dim=-1)
    p2_bench_score = torch.sum(hp_pct[..., 6:8] - (faint_risk[..., 6:8] * faint_penalty), dim=-1)
    
    p1_total = p1_active_score + (p1_bench_score * 0.8)
    p2_total = p2_active_score + (p2_bench_score * 0.8)
    
    return p1_total - p2_total

# =====================================================================
# 3. NASH EQUILIBRIUM SOLVER
# =====================================================================
def solve_nash_mixed_strategy(payoff_matrix):
    if isinstance(payoff_matrix, torch.Tensor):
        payoff_matrix = payoff_matrix.detach().cpu().numpy()
        
    N, M = payoff_matrix.shape

    c = np.zeros(N + 1)
    c[-1] = -1.0

    A_ub = np.zeros((M, N + 1))
    A_ub[:, :N] = -payoff_matrix.T
    A_ub[:, -1] = 1.0
    b_ub = np.zeros(M)

    A_eq = np.zeros((1, N + 1))
    A_eq[0, :N] = 1.0
    b_eq = np.array([1.0])

    bounds = [(0, 1) for _ in range(N)] + [(None, None)]

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method='highs')

    if not res.success:
        return np.ones(N)/N, np.ones(M)/M, 0.0

    p1_probs = res.x[:N]
    game_value = res.x[-1]
    p2_probs = np.abs(res.ineqlin.marginals)

    p1_probs = np.where(p1_probs < 1e-4, 0.0, p1_probs)
    p2_probs = np.where(p2_probs < 1e-4, 0.0, p2_probs)
    
    return p1_probs / p1_probs.sum(), p2_probs / p2_probs.sum(), game_value

# =====================================================================
# 4. VERBOSE TURN REPLAY INSPECTOR
# =====================================================================
def print_detailed_turn_line(
    title: str,
    p1_choice: tuple[int, int],
    p2_choice: tuple[int, int],
    manifest,
    F_init,
    P_init,
    M_init,
    state_machine,
    payoff_score: float,
):
    """Simulates and prints a fully formatted, verbose breakdown of any action collision."""
    print("\n" + "#" * 80)
    print(f"PLAYBACK: {title}")
    print(f"Collision Payoff Score: {payoff_score:+.4f} (Higher favors P1)")
    print(f"P1 Action: {format_joint_action('p1', p1_choice, manifest)}")
    print(f"P2 Action: {format_joint_action('p2', p2_choice, manifest)}")
    print("#" * 80)

    translator = ShowdownStateTranslator(manifest=manifest.clone())
    unroller = ShowdownReplayUnroller(state_machine, translator)

    t_exp = ReplayTurnExpectation(
        turn=1,
        p1_choices=(int(p1_choice[0]), int(p1_choice[1])),
        p2_choices=(int(p2_choice[0]), int(p2_choice[1])),
        expected_damages={},
        expected_flinches=[],
    )

    _, cp, _ = unroller.step_and_verify_turn(F_init, P_init, M_init, t_exp, num_mc_samples=16)

    print("\n[NARRATIVE ACTIONS]")
    for line in cp.human_readable_log:
        if line.startswith("==="):
            print("\n[FINAL BOARD STATE]")
        print(line)
    print("-" * 80)

# =====================================================================
# 5. MAIN PIPELINE
# =====================================================================
def run_ai_turn1():
    print("=" * 80)
    print("      VGC TENSOR AI ENGINE: VERBOSE TURN 1 TELEMETRY & STRATEGY SOLVER")
    print("=" * 80)
    
    device = "cuda:0" if (HAS_TORCH and torch.cuda.is_available()) else "cpu"
    tables = build_bilinear_lookup_tables(device=device)
    compiler = ShowdownTensorCompiler(tables=tables)
    state_machine = VgcTensorStateMachine(device=device)
    manifest = _build_game1_manifest()
    
    F_init, P_init, M_init = _build_game1_initial_state(tables, device)
    
    comp_state = CompiledBattleState(
        field_tensor=F_init,
        roster_tensor=P_init,
        moves_tensor=M_init,
        backend="torch" if HAS_TORCH else "numpy",
        device=device
    )

    print(f"[*] Backend: {comp_state.backend.upper()} | Device: {device}")
    print("[*] Generating physical validity & tactical prior action masks (26x26 per side)...")
    p1_mask = compiler.compute_26x26_side_action_masks(comp_state, side="p1")
    p2_mask = compiler.compute_26x26_side_action_masks(comp_state, side="p2")
    
    p1_valid_coords = p1_mask.valid_coords
    p2_valid_coords = p2_mask.valid_coords
    B1 = p1_mask.num_valid_actions
    B2 = p2_mask.num_valid_actions

    print(f"[*] Pruning Complete:")
    print(f"    - Player 1 Legal Joint Actions: {B1} / 676")
    print(f"    - Player 2 Legal Joint Actions: {B2} / 676")
    print(f"[*] Simulating parallel tensor grid: [{B1} x {B2} x 16 (Monte Carlo Rolls)] = {B1 * B2 * 16:,} timelines...")
    
    step_res = state_machine.step(
        F_init, P_init, M_init, 
        p1_valid_coords, p2_valid_coords, 
        num_mc_samples=16, rng_seed=42
    )

    print("[*] Evaluating multi-dimensional payoff tensor (HP preservation, faint penalties, equity)...")
    payoff_matrix = evaluate_payoff_matrix(step_res, P_init)
    
    # Inject soft tactical prior from compiler axioms
    joint_prior = p1_mask.joint_prior_mat[p1_valid_coords[:, 0], p1_valid_coords[:, 1]].unsqueeze(1) + \
                  p2_mask.joint_prior_mat[p2_valid_coords[:, 0], p2_valid_coords[:, 1]].unsqueeze(0)
    payoff_matrix = payoff_matrix + (joint_prior * 0.1)

    print("[*] Computing Mixed-Strategy Nash Equilibrium using HiGHS Linear Programming...")
    p1_probs, p2_probs, game_value = solve_nash_mixed_strategy(payoff_matrix)

    # -------------------------------------------------------------
    # 1. VERBOSE STRATEGY DECOMPOSITION
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"GAME VALUE (EQUILIBRIUM ADVANTAGE): {game_value:+.4f}")
    print("Note: > 0 favors Player 1, < 0 favors Player 2")
    print("=" * 80)

    # Display Player 1 Lines
    print("\n[PLAYER 1 (aws_secret) MIXED-STRATEGY DISTRIBUTION]")
    p1_sorted_indices = np.argsort(-p1_probs)
    for rank, idx in enumerate(p1_sorted_indices):
        prob = p1_probs[idx]
        if prob <= 0.0001:
            break
        coords = p1_valid_coords[idx].cpu().numpy()
        switch_flag = "[CONTAINS SWITCH] " if contains_switch(coords) else ""
        desc = format_joint_action("p1", coords, manifest)
        print(f"  Rank {rank+1:02d} | Weight: {prob*100:6.2f}% | {switch_flag}{desc}")

    # Display Player 2 Lines
    print("\n[PLAYER 2 (asfdiha) MIXED-STRATEGY DISTRIBUTION]")
    p2_sorted_indices = np.argsort(-p2_probs)
    for rank, idx in enumerate(p2_sorted_indices):
        prob = p2_probs[idx]
        if prob <= 0.0001:
            break
        coords = p2_valid_coords[idx].cpu().numpy()
        switch_flag = "[CONTAINS SWITCH] " if contains_switch(coords) else ""
        desc = format_joint_action("p2", coords, manifest)
        print(f"  Rank {rank+1:02d} | Weight: {prob*100:6.2f}% | {switch_flag}{desc}")

    # -------------------------------------------------------------
    # 2. SWITCH LINE ISOLATION & TELEMETRY
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("SWITCH-IN ANALYSIS (LINES WHERE PLAYERS PIVOT)")
    print("=" * 80)

    # Check P1 best switch
    p1_switch_found = False
    for idx in p1_sorted_indices:
        coords = p1_valid_coords[idx].cpu().numpy()
        if contains_switch(coords):
            prob = p1_probs[idx]
            desc = format_joint_action("p1", coords, manifest)
            print(f"  [*] Best P1 Switch Line (Rank {np.where(p1_sorted_indices == idx)[0][0] + 1}, {prob*100:.2f}% eq weight):")
            print(f"      {desc}")
            p1_switch_found = True
            break
    if not p1_switch_found:
        print("  [*] Player 1: No switch lines carried non-zero equilibrium weight.")

    # Check P2 best switch
    p2_switch_idx = None
    for idx in p2_sorted_indices:
        coords = p2_valid_coords[idx].cpu().numpy()
        if contains_switch(coords):
            prob = p2_probs[idx]
            desc = format_joint_action("p2", coords, manifest)
            rank_num = np.where(p2_sorted_indices == idx)[0][0] + 1
            print(f"  [*] Best P2 Switch Line (Rank {rank_num}, {prob*100:.2f}% eq weight):")
            print(f"      {desc}")
            p2_switch_idx = idx
            break

    # -------------------------------------------------------------
    # 3. VERBOSE NARRATIVE PLAYBACK: PRIMARY EQUILIBRIUM
    # -------------------------------------------------------------
    top_p1_idx = p1_sorted_indices[0]
    top_p2_idx = p2_sorted_indices[0]
    p1_best_choice = p1_valid_coords[top_p1_idx].cpu().numpy()
    p2_best_choice = p2_valid_coords[top_p2_idx].cpu().numpy()
    eq_payoff = float(payoff_matrix[top_p1_idx, top_p2_idx].item())

    print_detailed_turn_line(
        title="PRIMARY NASH EQUILIBRIUM COLLISION (Rank 1 vs Rank 1)",
        p1_choice=p1_best_choice,
        p2_choice=p2_best_choice,
        manifest=manifest,
        F_init=F_init,
        P_init=P_init,
        M_init=M_init,
        state_machine=state_machine,
        payoff_score=eq_payoff,
    )

    # -------------------------------------------------------------
    # 4. VERBOSE NARRATIVE PLAYBACK: THE TOURNAMENT MATCH LINE
    # -------------------------------------------------------------
    # Tournament Line: Raichu Fake Out + Kingambit Kowtow vs Rillaboom Switch to Raichu + Mega Charizard Y Heat Wave
    if p2_switch_idx is not None and p2_switch_idx != top_p2_idx:
        p2_switch_choice = p2_valid_coords[p2_switch_idx].cpu().numpy()
        switch_payoff = float(payoff_matrix[top_p1_idx, p2_switch_idx].item())
        print_detailed_turn_line(
            title="ALTERNATIVE INSPECTION: P1 OPTIMAL vs P2 SWITCH LINE",
            p1_choice=p1_best_choice,
            p2_choice=p2_switch_choice,
            manifest=manifest,
            F_init=F_init,
            P_init=P_init,
            M_init=M_init,
            state_machine=state_machine,
            payoff_score=switch_payoff,
        )

if __name__ == "__main__":
    run_ai_turn1()