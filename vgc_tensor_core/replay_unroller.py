# -*- coding: utf-8 -*-
"""
VGC Tensor Core — Dynamic Showdown Replay Unroller
===================================================

Executes turns through VgcTensorStateMachine, asserts mathematical brackets,
and reconstructs authentic Showdown wire protocol lines on CPU with zero GPU stalls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import numpy as np

from .schema_and_tables import (
    FieldIdx,
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
from .state_machine import StepResult, VgcTensorStateMachine
from .state_translator import ShowdownStateTranslator, TurnCheckpoint, _slice_to_cpu_numpy

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray


@dataclass
class ReplayTurnExpectation:
    turn: int
    p1_choices: Tuple[int, int]
    p2_choices: Tuple[int, int]
    expected_damages: Dict[str, Tuple[float, float]]  # e.g. {'p2b': (10.0, 20.0)}
    expected_flinches: List[str]                      # e.g. ['p2b']
    expected_terrains: Optional[str] = None
    expected_weathers: Optional[str] = None
    expected_faints: Optional[List[str]] = None


class ShowdownReplayUnroller:
    """
    Steps the GPU state machine, captures intermediate checkpoints,
    and dynamically produces human-readable and Showdown-protocol turn logs.
    """

    def __init__(self, state_machine: VgcTensorStateMachine, translator: ShowdownStateTranslator):
        self.sm = state_machine
        self.translator = translator

    def step_and_verify_turn(
        self,
        current_f: TensorOrArray,
        current_p: TensorOrArray,
        current_m: TensorOrArray,
        expectation: ReplayTurnExpectation,
        num_mc_samples: int = 16,
    ) -> Tuple[StepResult, TurnCheckpoint, str]:
        """
        Executes turn on GPU, validates damage brackets, and generates dual protocol logs.
        """
        turn = expectation.turn
        p1_choice_arr = np.array([list(expectation.p1_choices)], dtype=np.int64)
        p2_choice_arr = np.array([list(expectation.p2_choices)], dtype=np.int64)

        if HAS_TORCH and isinstance(current_p, torch.Tensor):
            dev = current_p.device
            p1_c_t = torch.tensor(p1_choice_arr, dtype=torch.long, device=dev)
            p2_c_t = torch.tensor(p2_choice_arr, dtype=torch.long, device=dev)
        else:
            p1_c_t = p1_choice_arr
            p2_c_t = p2_choice_arr

        # Checkpoint T0: Pre-Action Start of Turn
        self.translator.save_checkpoint(
            turn=turn,
            stage="T0_START",
            F=current_f,
            P=current_p,
            M_moves=current_m,
            showdown_lines=[f"# Turn {turn} Pre-Action Snapshot"],
            human_readable=[],
        )

        # Step GPU State Machine
        step_res = self.sm.step(
            current_f,
            current_p,
            current_m,
            p1_c_t,
            p2_c_t,
            num_mc_samples=num_mc_samples,
        )

        # Dynamic Showdown Reconstruction on CPU
        showdown_lines, summary_table = self.translator.decode_turn_events(
            turn=turn,
            pre_F=current_f,
            pre_P=current_p,
            pre_M=current_m,
            post_step_res=step_res,
            p1_choices=p1_c_t,
            p2_choices=p2_c_t,
        )

        # Validate Damage Expectations
        post_p = _slice_to_cpu_numpy(step_res.P)
        pre_p = _slice_to_cpu_numpy(current_p)
        slot_map = {"p1a": 0, "p1b": 1, "p2a": 4, "p2b": 5}

        for slot_str, (min_pct, max_pct) in expectation.expected_damages.items():
            s_idx = slot_map[slot_str]
            choice_val = (
                expectation.p1_choices[0] if s_idx == 0 else (
                    expectation.p1_choices[1] if s_idx == 1 else (
                        expectation.p2_choices[0] if s_idx == 4 else expectation.p2_choices[1]
                    )
                )
            )

            # If slot switched, starting HP is from pre-switch bench slot
            if choice_val in (24, 25):
                bench_idx = (
                    (SLOT_P1_BENCH1 if choice_val == 24 else SLOT_P1_BENCH2)
                    if s_idx < 4
                    else (SLOT_P2_BENCH1 if choice_val == 24 else SLOT_P2_BENCH2)
                )
                hp_before = float(pre_p[bench_idx, MonIdx.HP_CUR])
                hp_max = float(pre_p[bench_idx, MonIdx.HP_MAX])
            else:
                hp_before = float(pre_p[s_idx, MonIdx.HP_CUR])
                hp_max = float(pre_p[s_idx, MonIdx.HP_MAX])

            hp_after = float(post_p[s_idx, MonIdx.HP_CUR])
            dmg_taken = max(0.0, hp_before - hp_after)
            dmg_pct = (dmg_taken / max(1.0, hp_max)) * 100.0

            assert min_pct <= dmg_pct <= max_pct, (
                f"Turn {turn} Damage Discrepancy on {slot_str}: observed {dmg_pct:.1f}%, expected [{min_pct}, {max_pct}]%"
            )

        # Dual Protocol Output Formatting
        dual_output = (
            f"\n=== Showdown Wire Protocol (Turn {turn}) ===\n"
            + "\n".join(showdown_lines)
            + "\n\n"
            + "\n".join(summary_table)
        )

        # Save Final Turn Checkpoint
        final_cp = self.translator.save_checkpoint(
            turn=turn,
            stage="T4_POST_EOT",
            F=step_res.F,
            P=step_res.P,
            M_moves=step_res.M_moves,
            showdown_lines=showdown_lines,
            human_readable=summary_table,
        )

        return step_res, final_cp, dual_output