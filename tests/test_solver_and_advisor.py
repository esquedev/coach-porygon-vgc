# -*- coding: utf-8 -*-
"""
Unit tests for `src/engine/solver/game_theory.py`:
- Iterated Elimination of Dominated Strategies (`run_iterated_dominance_elimination`)
- Zero-Sum Nash / Minimax Equilibrium Solver (`solve_zero_sum_nash`)
- Logit Quantal Response Equilibrium Solver (`solve_quantal_response`)
- Direct Turn Equilibrium Rollout & Coach Report Formatting (`solve_turn_equilibrium`, `format_equilibrium_coach_report`)
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
from engine.solver import (
    format_equilibrium_coach_report,
    run_iterated_dominance_elimination,
    solve_quantal_response,
    solve_turn_equilibrium,
    solve_zero_sum_nash,
)
from engine.state import TurnStateCompiler
from engine.vgc_tensor_core import ShowdownTensorCompiler, VgcTensorStateMachine


TEAM_PASTE = """
Charizard @ Charizardite Y
Ability: Blaze
EVs: 2 HP / 12 Def / 28 SpA / 24 Spe
Timid Nature
Level: 50
- Heat Wave
- Scorching Sands
- Solar Beam
- Protect

Rillaboom @ Miracle Seed
Ability: Grassy Surge
EVs: 28 HP / 32 Atk / 6 Spe
Adamant Nature
Level: 50
- Fake Out
- Grassy Glide
- Wood Hammer
- U-turn

Garchomp @ Life Orb
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
"""


class TestGameTheorySolvers(unittest.TestCase):
    """Verify IEDS, Zero-Sum Nash, Logit QRE, and direct turn equilibrium."""

    def test_multi_round_iterated_dominance_elimination(self) -> None:
        """Verify multi-round IEDS reduces a 3x3 cascading dominance game to its unique 1x1 core."""
        U = np.array(
            [
                [1.0, 4.0, 5.0],
                [2.0, 3.0, 2.0],
                [0.0, 0.0, 0.0],
            ],
            dtype=np.float64,
        )
        res = run_iterated_dominance_elimination(U, eliminate_weakly_dominated=True)
        self.assertEqual(list(res.trainer_1_surviving_indices), [1])
        self.assertEqual(list(res.trainer_2_surviving_indices), [0])
        self.assertGreaterEqual(res.rounds_executed, 2)
        self.assertEqual(res.reduced_payoff_matrix.shape, (1, 1))
        self.assertAlmostEqual(float(res.reduced_payoff_matrix[0, 0]), 2.0, places=6)

    def test_zero_sum_nash_saddle_point_and_mixed_mindgame(self) -> None:
        """Verify exact Nash equilibrium on both a pure saddle-point matrix and a 2x2 Sucker Punch mindgame."""
        U_saddle = np.array(
            [
                [5.0, 3.0, 6.0],
                [1.0, 2.0, 8.0],
            ],
            dtype=np.float64,
        )
        nash_pure = solve_zero_sum_nash(U_saddle)
        self.assertEqual(nash_pure.solver_used, "pure_saddle_point")
        self.assertAlmostEqual(nash_pure.game_value, 3.0, places=6)
        self.assertAlmostEqual(float(nash_pure.trainer_1_strategy[0]), 1.0, places=6)
        self.assertAlmostEqual(float(nash_pure.trainer_2_strategy[1]), 1.0, places=6)

        U_mix = np.array(
            [
                [2.0, -1.0],
                [-1.0, 4.0],
            ],
            dtype=np.float64,
        )
        nash_mix = solve_zero_sum_nash(U_mix)
        self.assertAlmostEqual(float(nash_mix.trainer_1_strategy[0]), 0.625, delta=0.015)
        self.assertAlmostEqual(float(nash_mix.trainer_1_strategy[1]), 0.375, delta=0.015)
        self.assertAlmostEqual(float(nash_mix.trainer_2_strategy[0]), 0.625, delta=0.015)
        self.assertAlmostEqual(float(nash_mix.trainer_2_strategy[1]), 0.375, delta=0.015)
        self.assertAlmostEqual(nash_mix.game_value, 0.875, delta=0.015)
        self.assertLess(nash_mix.exploitability_gap, 0.02)

    def test_quantal_response_equilibrium(self) -> None:
        """Verify Logit QRE produces valid probability distributions favoring higher payoffs."""
        U = np.array(
            [
                [2.5, 1.5],
                [-1.0, -0.5],
            ],
            dtype=np.float64,
        )
        qre = solve_quantal_response(U, rationality_beta=4.0)
        self.assertAlmostEqual(float(np.sum(qre.trainer_1_strategy)), 1.0, places=6)
        self.assertAlmostEqual(float(np.sum(qre.trainer_2_strategy)), 1.0, places=6)
        self.assertGreater(float(qre.trainer_1_strategy[0]), 0.95)
        self.assertGreater(float(qre.trainer_2_strategy[1]), 0.90)

    def test_direct_turn_equilibrium_and_coach_report_formatting(self) -> None:
        """Verify decoupled tensor state -> VgcTensorStateMachine -> solve_turn_equilibrium -> report."""
        t1_sets = parse_showdown_paste(TEAM_PASTE)
        t2_sets = parse_showdown_paste(TEAM_PASTE)

        battle = ParsedBattle()
        battle.trainer_1 = ParsedTeam(
            trainer_name="trainer_1",
            team_preview=list(t1_sets.keys()),
            battle_roster=["Charizard", "Rillaboom", "Garchomp", "Kingambit"],
            leads=("Charizard", "Rillaboom"),
            active_slots=["Charizard", "Rillaboom"],
            pokemon_sets=t1_sets,
        )
        battle.trainer_2 = ParsedTeam(
            trainer_name="trainer_2",
            team_preview=list(t2_sets.keys()),
            battle_roster=["Garchomp", "Kingambit", "Charizard", "Rillaboom"],
            leads=("Garchomp", "Kingambit"),
            active_slots=["Garchomp", "Kingambit"],
            pokemon_sets=t2_sets,
        )

        sc = TurnStateCompiler()
        ts = sc.compile_turn_state(battle, run_inference=False)
        tc = ShowdownTensorCompiler(registry=sc.registry, backend="numpy")
        comp = tc.compile_turn_state(ts)

        sm = VgcTensorStateMachine(backend="numpy", risk_aversion_lambda=0.25)
        mask_t1, mask_t2, step_res = sm.simulate_pruned_turn(comp, num_simulations=16, rng_seed=77)
        eq = solve_turn_equilibrium(comp, mask_t1, mask_t2, step_res)

        self.assertGreaterEqual(len(eq.recommendations), 1)
        self.assertAlmostEqual(float(np.sum(eq.nash.trainer_1_strategy)), 1.0, places=5)
        self.assertAlmostEqual(float(np.sum(eq.qre.trainer_1_strategy)), 1.0, places=5)

        coach_report = format_equilibrium_coach_report(
            eq, num_simulations=16, verbosity="coach", max_recommendations=3
        )
        self.assertIn("TURN COACH ADVICE", coach_report)

        sci_report = format_equilibrium_coach_report(
            eq, num_simulations=16, verbosity="scientific", max_recommendations=3
        )
        self.assertIn("MATHEMATICAL & PROCESS AUDIT", sci_report)


if __name__ == "__main__":
    unittest.main()
