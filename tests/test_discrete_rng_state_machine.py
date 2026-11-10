# -*- coding: utf-8 -*-
"""
Unit tests for Step 4B:
- Dual-Draw Spinning-Wheel & Counter-Based Hash RNG (`rng_engine.py`)
- Logical Constraint & Tensor Action Pruner (`logic_engine.py`)
- 5-Phase Vectorized Discrete-RNG State Machine & Risk Evaluator (`state_machine.py`)
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.parser import parse_showdown_paste
from engine.parser.models import ParsedBattle, ParsedTeam
from engine.state import TurnStateCompiler
from engine.vgc_tensor_core import (
    LogicalConstraintEngine,
    RNGEventID,
    SLOT_TRAINER_2_A,
    ShowdownTensorCompiler,
    VgcTensorStateMachine,
    counter_uniform_0_100_numpy,
    format_action_pruning_matrix,
    format_full_turn_report,
    spin_wheel_crit_gate,
    spin_wheel_damage_rolls_16,
    spin_wheel_gate,
    spin_wheel_multihit_count,
)


TEST_TEAM_PASTE = """
Charizard @ Focus Sash  
Ability: Blaze  
EVs: 2 HP / 12 Def / 28 SpA / 24 Spe  
Timid Nature  
Level: 50  
- Heat Wave  
- Scorching Sands  
- Solar Beam  
- Protect  

Rillaboom @ Assault Vest  
Ability: Grassy Surge  
EVs: 28 HP / 32 Atk / 6 Spe  
Adamant Nature  
Level: 50  
- Fake Out  
- Grassy Glide  
- Wood Hammer  
- U-turn  

Meowscarada @ Focus Sash  
Ability: Overgrow  
EVs: 2 HP / 32 Atk / 32 Spe  
Jolly Nature  
Level: 50  
- Flower Trick  
- Knock Off  
- Sucker Punch  
- Protect  

Garchomp @ Loaded Dice  
Ability: Rough Skin  
EVs: 2 HP / 32 Atk / 32 Spe  
Jolly Nature  
Level: 50  
- Rock Blast  
- Stomping Tantrum  
- Dragon Claw  
- Protect  

Kingambit @ Black Glasses  
Ability: Defiant  
EVs: 32 HP / 32 Atk / 2 Spe  
Adamant Nature  
Level: 50  
- Kowtow Cleave  
- Iron Head  
- Sucker Punch  
- Protect  

Grimmsnarl @ Light Clay  
Ability: Prankster  
EVs: 32 HP / 16 Def / 15 SpD / 3 Spe  
Impish Nature  
Level: 50  
- Reflect  
- Light Screen  
- Spirit Break  
- Parting Shot  
"""


def _build_test_battle(
    t1_roster: list[str],
    t2_roster: list[str],
) -> ParsedBattle:
    sets = parse_showdown_paste(TEST_TEAM_PASTE)
    battle = ParsedBattle()
    battle.trainer_1 = ParsedTeam(
        trainer_name="trainer_1",
        team_preview=list(sets.keys()),
        battle_roster=t1_roster,
        leads=(t1_roster[0], t1_roster[1]),
        active_slots=[t1_roster[0], t1_roster[1]],
        pokemon_sets=parse_showdown_paste(TEST_TEAM_PASTE),
    )
    battle.trainer_2 = ParsedTeam(
        trainer_name="trainer_2",
        team_preview=list(sets.keys()),
        battle_roster=t2_roster,
        leads=(t2_roster[0], t2_roster[1]),
        active_slots=[t2_roster[0], t2_roster[1]],
        pokemon_sets=parse_showdown_paste(TEST_TEAM_PASTE),
    )
    return battle


class TestDiscreteRNGAndStateMachine(unittest.TestCase):
    """Verify Spinning-Wheel RNG de-biasing, Logical Action Pruning, and 5-Phase Tensor Execution."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.state_compiler = TurnStateCompiler()
        cls.tensor_compiler = ShowdownTensorCompiler(backend="torch", device="cpu")
        cls.logic_engine = LogicalConstraintEngine()
        cls.state_machine = VgcTensorStateMachine(backend="torch", device="cpu")

    def test_spinning_wheel_debiasing_and_exact_rates(self) -> None:
        """Verify 85% accuracy hits ~85% and misses are distributed uniformly across [0, 100) darts."""
        K = 20000
        thresh = np.full((K,), 85.0, dtype=np.float32)
        hits = spin_wheel_gate(thresh, seed=12345, event_id=int(RNGEventID.MOVE_ACCURACY))
        hit_rate = float(np.mean(hits))
        self.assertAlmostEqual(hit_rate, 0.85, delta=0.015)

        # Verify misses are NOT trapped at the top [85..100] of raw dart values!
        darts = counter_uniform_0_100_numpy(
            (K,), seed=12345, event_id=int(RNGEventID.MOVE_ACCURACY), sub_draw=1
        )
        miss_darts = darts[~hits]
        # In a de-biased spinning wheel, miss darts span [0, 100) with mean ~50.0 (not 92.5!)
        self.assertAlmostEqual(float(np.mean(miss_darts)), 50.0, delta=2.5)
        self.assertTrue(np.any(miss_darts < 20.0))
        self.assertTrue(np.any((miss_darts >= 40.0) & (miss_darts <= 60.0)))
        self.assertTrue(np.any(miss_darts > 80.0))

    def test_cartridge_crit_stages_and_16_damage_rolls(self) -> None:
        """Verify Crit Stages 0..3 match 1/24 (~4.17%), 1/8 (12.5%), 1/2 (50%), 1/1 (100%) and 16 rolls."""
        K = 24000
        c0 = spin_wheel_crit_gate(np.zeros((K,), dtype=np.float32), seed=77)
        c1 = spin_wheel_crit_gate(np.ones((K,), dtype=np.float32), seed=77)
        c2 = spin_wheel_crit_gate(np.full((K,), 2.0, dtype=np.float32), seed=77)
        c3 = spin_wheel_crit_gate(np.full((K,), 3.0, dtype=np.float32), seed=77)

        self.assertAlmostEqual(float(np.mean(c0)), 1.0 / 24.0, delta=0.008)
        self.assertAlmostEqual(float(np.mean(c1)), 0.125, delta=0.01)
        self.assertAlmostEqual(float(np.mean(c2)), 0.50, delta=0.015)
        self.assertEqual(float(np.mean(c3)), 1.0)

        rolls = spin_wheel_damage_rolls_16((K,), seed=99, is_torch=False)
        unique_rolls = np.unique(np.round(rolls, 2))
        self.assertEqual(len(unique_rolls), 16)
        self.assertAlmostEqual(float(unique_rolls[0]), 0.85, places=2)
        self.assertAlmostEqual(float(unique_rolls[-1]), 1.00, places=2)
        self.assertAlmostEqual(float(np.mean(rolls)), 0.925, delta=0.005)

    def test_multihit_wheel_distributions(self) -> None:
        """Verify variable 2..5 multi-hit wheel (35/35/15/15) and Loaded Dice (50/50 4 or 5)."""
        K = 20000
        code_var = np.full((K,), 3.1, dtype=np.float32)
        no_dice = np.zeros((K,), dtype=np.float32)
        with_dice = np.ones((K,), dtype=np.float32)
        no_slink = np.zeros((K,), dtype=np.float32)

        counts_std = spin_wheel_multihit_count(code_var, no_dice, no_slink, seed=42)
        self.assertAlmostEqual(float(np.mean(counts_std == 2)), 0.35, delta=0.015)
        self.assertAlmostEqual(float(np.mean(counts_std == 3)), 0.35, delta=0.015)
        self.assertAlmostEqual(float(np.mean(counts_std == 4)), 0.15, delta=0.015)
        self.assertAlmostEqual(float(np.mean(counts_std == 5)), 0.15, delta=0.015)

        counts_dice = spin_wheel_multihit_count(code_var, with_dice, no_slink, seed=42)
        self.assertEqual(int(np.sum(counts_dice < 4)), 0)
        self.assertAlmostEqual(float(np.mean(counts_dice == 4)), 0.50, delta=0.015)
        self.assertAlmostEqual(float(np.mean(counts_dice == 5)), 0.50, delta=0.015)

    def test_logical_constraint_engine_and_tensor_pruner(self) -> None:
        """Verify symbolic and 26x26 tensor pruning via LogicalConstraintEngine."""
        res_fo = self.logic_engine.evaluate_slot_action(
            slot_species="Rillaboom",
            move_name="Fake Out",
            target_species="Tornadus",
            active_turns=2,
        )
        self.assertFalse(res_fo.is_mechanically_valid)

        res_prank = self.logic_engine.evaluate_slot_action(
            slot_species="Tornadus",
            move_name="Taunt",
            target_species="Kingambit",
            user_ability="Prankster",
        )
        self.assertFalse(res_prank.is_mechanically_valid)

        battle = _build_test_battle(
            t1_roster=["Charizard", "Rillaboom", "Meowscarada", "Kingambit"],
            t2_roster=["Garchomp", "Grimmsnarl", "Kingambit", "Rillaboom"],
        )
        turn_state = self.state_compiler.compile_turn_state(battle, run_inference=False)
        compiled = self.tensor_compiler.compile_turn_state(turn_state)

        mask_t1 = self.logic_engine.prune_side_26x26_tensor_actions(compiled, trainer_id="trainer_1")
        mask_t2 = self.logic_engine.prune_side_26x26_tensor_actions(compiled, trainer_id="trainer_2")

        self.assertEqual(mask_t1.valid_mask_26x26.shape, (26, 26))
        self.assertEqual(mask_t2.valid_mask_26x26.shape, (26, 26))
        self.assertGreater(mask_t1.pruned_choices.shape[0], 10)
        self.assertLess(mask_t1.pruned_choices.shape[0], 300)

        summary_str = format_action_pruning_matrix(mask_t1.valid_mask_26x26, side_name="trainer_1")
        self.assertIn("TRAINER_1 26x26 ACTION PRUNING MATRIX", summary_str)

    def test_multihit_rock_blast_and_willcrit_flower_trick(self) -> None:
        """Verify Loaded Dice Rock Blast (4-5 hits, 4x SE) breaks Focus Sash on Charizard and Flower Trick crits 100%."""
        battle = _build_test_battle(
            t1_roster=["Meowscarada", "Garchomp", "Rillaboom", "Kingambit"],
            t2_roster=["Charizard", "Grimmsnarl", "Kingambit", "Rillaboom"],
        )
        turn_state = self.state_compiler.compile_turn_state(battle, run_inference=False)
        compiled = self.tensor_compiler.compile_turn_state(turn_state)

        # trainer_1_a (Meowscarada) uses Flower Trick (move 0, 100% crit) on trainer_2_b (Grimmsnarl, choice 4)
        # trainer_1_b (Garchomp @ Loaded Dice) uses Rock Blast (move 0, 4-5 hits, 100% acc via No Guard or ~90% acc) on trainer_2_a (Charizard @ Focus Sash, choice 0)
        # trainer_2_a (Charizard) uses Protect? No, let Charizard use Scorching Sands on Garchomp (choice 5) and Grimmsnarl use Reflect (choice 0)
        import torch
        t1_choices = torch.tensor([[4, 0]], dtype=torch.long)
        t2_choices = torch.tensor([[5, 0]], dtype=torch.long)

        step_res = self.state_machine.step(
            F=compiled.field_tensor,
            P=compiled.roster_tensor,
            M_moves=compiled.moves_tensor,
            trainer_1_choices=t1_choices,
            trainer_2_choices=t2_choices,
            num_mc_samples=128,
            rng_seed=42,
        )

        # Charizard (SLOT_TRAINER_2_A = 4) holds Focus Sash, but whenever 4x SE Rock Blast hits (~90% acc), 4-5 hits break Focus Sash and KO!
        charizard_faint_prob = float(step_res.faint_prob[0, 0, SLOT_TRAINER_2_A].item())
        self.assertGreater(charizard_faint_prob, 0.80)

        # Meowscarada's observed crit rate on Flower Trick (willCrit=True) must be 1.0 (100%)
        meow_crit_rate = float(step_res.attack_cascade.crit_rate_observed[0, 0, 0].item())
        self.assertAlmostEqual(meow_crit_rate, 1.0, places=4)

    def test_simulate_pruned_turn_and_risk_resilience_metrics(self) -> None:
        """Verify full pruned turn simulation across K=32 repetitions per (i, j) pair."""
        battle = _build_test_battle(
            t1_roster=["Charizard", "Rillaboom", "Meowscarada", "Kingambit"],
            t2_roster=["Garchomp", "Grimmsnarl", "Kingambit", "Rillaboom"],
        )
        turn_state = self.state_compiler.compile_turn_state(battle, run_inference=False)
        compiled = self.tensor_compiler.compile_turn_state(turn_state)

        mask_t1, mask_t2, step_res = self.state_machine.simulate_pruned_turn(
            compiled_state=compiled,
            num_simulations=32,
            min_prior_threshold=0.80,
            rng_seed=101,
            risk_aversion_lambda=0.25,
            max_sim_chunk_size=16,
        )

        B1 = mask_t1.pruned_choices.shape[0]
        B2 = mask_t2.pruned_choices.shape[0]
        self.assertEqual(step_res.stats.mean_utility.shape, (B1, B2))
        self.assertEqual(step_res.stats.cvar_10_utility.shape, (B1, B2))
        self.assertEqual(step_res.stats.risk_adjusted_utility.shape, (B1, B2))

        # CVaR_10 (worst 10% bad luck) must always be <= Mean Utility
        diff = (step_res.stats.mean_utility - step_res.stats.cvar_10_utility).detach().cpu().numpy()
        self.assertTrue(np.all(diff >= -1e-5))

        report = format_full_turn_report(step_res, cell_b1=0, cell_b2=0)
        self.assertIn("DISCRETE-RNG ATTACK CASCADE", report)
        self.assertIn("CVaR_10(Worst10%)", report)


if __name__ == "__main__":
    unittest.main()
