# -*- coding: utf-8 -*-
"""
VGC Tensor Core 2.0 — Quickstart Interactive Demo
=================================================

Runs a live, end-to-end Turn 1 simulation on CUDA (RTX 3060) and displays
esports-grade matrix dashboards with real calculation evidence:
- CUDA hardware telemetry & VRAM usage
- 26x26 Action Pruning heatmap (676 branches)
- Pre-Attack turn order & speed tie jitter resolution
- Phase 4 Monte Carlo K=16 damage roll distributions
- Phase 5 End-of-Turn residuals and match status
"""

import os
import sys
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from vgc_tensor_core.state_machine import VgcTensorStateMachine
from vgc_tensor_core.compiler import ShowdownTensorCompiler
from vgc_tensor_core.telemetry_formatter import (
    format_action_pruning_matrix,
    format_full_turn_report,
)
from vgc_tensor_core.tests.test_milestone5_state_machine import _build_test_roster
from vgc_tensor_core.tests.test_milestone2_compiler_and_pruner import _build_turn1_sample_rosters


def main():
    print("\n================================================================================")
    print("VGC TENSOR CORE 2.0 — LIVE CUDA DEMO & MATRIX TELEMETRY")
    print("================================================================================")
    print("Initializing VgcTensorStateMachine on CUDA...")
    sm = VgcTensorStateMachine(backend="torch")
    F, P, M = _build_test_roster()

    # P1 choices: P1A uses Move 0 (Close Combat) -> Opp A; P1B uses Move 0 (Dazzling Gleam) -> Opp A
    # P2 choices: P2A uses Move 0 -> Slot 0; P2B uses Move 0 -> Slot 0
    p1_choices = np.zeros((1, 2), dtype=np.int64)
    p2_choices = np.zeros((1, 2), dtype=np.int64)

    print("Executing Turn 1 with 16 Monte Carlo cartridge damage rolls [85%..100%]...\n")
    step_res = sm.step(
        F=F,
        P=P,
        M_moves=M,
        p1_choices=p1_choices,
        p2_choices=p2_choices,
        num_mc_samples=16,
    )

    # 1. Print Full Turn Report
    print(format_full_turn_report(step_res, cell_b1=0, cell_b2=0, device=sm.device))

    # 2. Print Action Pruning Matrix Sample
    compiler = ShowdownTensorCompiler()
    raw_state = compiler.compile_battle_state(_build_turn1_sample_rosters())
    mask_res = compiler.compute_26x26_side_action_masks(raw_state, side="p1")
    print(format_action_pruning_matrix(mask_res.joint_valid_mask, side_name="Player 1"))

    print("\nDEMO EXECUTION COMPLETE: 100% Deterministic Tensor Core Operating on CUDA.")
    print("================================================================================\n")


if __name__ == "__main__":
    main()
