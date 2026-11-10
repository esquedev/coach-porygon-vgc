# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Dynamic Showdown Replay Unroller
====================================================

Executes turns through `VgcTensorStateMachine`, asserts mathematical damage brackets,
and reconstructs Showdown wire protocol lines on CPU using `trainer_1` and `trainer_2`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import numpy as np

from .schema_and_tables import (
    HAS_TORCH,
    MonIdx,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_1_BENCH1,
    SLOT_TRAINER_1_BENCH2,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    SLOT_TRAINER_2_BENCH1,
    SLOT_TRAINER_2_BENCH2,
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
    """Expected bounds and outcomes for a replayed VGC turn."""

    turn: int
    trainer_1_choices: Tuple[int, int]
    trainer_2_choices: Tuple[int, int]
    expected_damages: Dict[str, Tuple[float, float]]  # e.g. {'trainer_2_b': (10.0, 20.0)}
    expected_flinches: List[str]                      # e.g. ['trainer_2_b']
    expected_terrains: Optional[str] = None
    expected_weathers: Optional[str] = None
    expected_faints: Optional[List[str]] = None


class ShowdownReplayUnroller:
    """Steps the GPU state machine, captures intermediate checkpoints, and produces turn logs."""

    def __init__(
        self,
        state_machine: VgcTensorStateMachine,
        translator: ShowdownStateTranslator,
    ) -> None:
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
        """Execute turn on GPU/CPU, validate damage brackets, and generate dual protocol logs."""
        turn = expectation.turn
        t1_choice_arr = np.array([list(expectation.trainer_1_choices)], dtype=np.int64)
        t2_choice_arr = np.array([list(expectation.trainer_2_choices)], dtype=np.int64)

        if HAS_TORCH and isinstance(current_p, torch.Tensor):
            dev = current_p.device
            t1_c_t = torch.tensor(t1_choice_arr, dtype=torch.long, device=dev)
            t2_c_t = torch.tensor(t2_choice_arr, dtype=torch.long, device=dev)
        else:
            t1_c_t = t1_choice_arr
            t2_c_t = t2_choice_arr

        self.translator.save_checkpoint(
            turn=turn,
            stage="T0_START",
            F=current_f,
            P=current_p,
            M_moves=current_m,
            showdown_lines=[f"# Turn {turn} Pre-Action Snapshot"],
            human_readable=[],
        )

        step_res = self.sm.step(
            current_f,
            current_p,
            current_m,
            t1_c_t,
            t2_c_t,
            num_mc_samples=num_mc_samples,
        )

        showdown_lines, summary_table = self.translator.decode_turn_events(
            turn=turn,
            pre_F=current_f,
            pre_P=current_p,
            pre_M=current_m,
            post_step_res=step_res,
            trainer_1_choices=t1_c_t,
            trainer_2_choices=t2_c_t,
        )

        post_p = _slice_to_cpu_numpy(step_res.P)
        pre_p = _slice_to_cpu_numpy(current_p)
        slot_map = {
            "trainer_1_a": SLOT_TRAINER_1_A,
            "trainer_1_b": SLOT_TRAINER_1_B,
            "trainer_2_a": SLOT_TRAINER_2_A,
            "trainer_2_b": SLOT_TRAINER_2_B,
        }

        for slot_str, (min_pct, max_pct) in expectation.expected_damages.items():
            s_idx = slot_map[slot_str]
            choice_val = (
                expectation.trainer_1_choices[0]
                if s_idx == SLOT_TRAINER_1_A
                else (
                    expectation.trainer_1_choices[1]
                    if s_idx == SLOT_TRAINER_1_B
                    else (
                        expectation.trainer_2_choices[0]
                        if s_idx == SLOT_TRAINER_2_A
                        else expectation.trainer_2_choices[1]
                    )
                )
            )

            if choice_val in (24, 25):
                bench_idx = (
                    (SLOT_TRAINER_1_BENCH1 if choice_val == 24 else SLOT_TRAINER_1_BENCH2)
                    if s_idx < 4
                    else (SLOT_TRAINER_2_BENCH1 if choice_val == 24 else SLOT_TRAINER_2_BENCH2)
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

        dual_output = (
            f"\n=== Showdown Wire Protocol (Turn {turn}) ===\n"
            + "\n".join(showdown_lines)
            + "\n\n"
            + "\n".join(summary_table)
        )

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

