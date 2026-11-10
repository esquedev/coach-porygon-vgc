# -*- coding: utf-8 -*-
"""
Unit tests for Step 5 (`src/engine/solver/`):
- Iterated Elimination of Dominated Strategies (`run_iterated_dominance_elimination`)
- Zero-Sum Nash / Minimax Equilibrium Solver (`solve_zero_sum_nash`)
- Logit Quantal Response Equilibrium Solver (`solve_quantal_response`)
- End-to-End Bayesian Top-K Opponent Hypothesis & Turn Advisor (`CoachTurnAdvisor`)
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
from engine.parser.models import ParsedBattle, ParsedPokemon, ParsedTeam
from engine.solver import (
    CoachTurnAdvisor,
    decode_joint_action,
    format_equilibrium_coach_report,
    run_iterated_dominance_elimination,
    solve_quantal_response,
    solve_turn_equilibrium,
    solve_zero_sum_nash,
)


ADVISOR_TEAM_PASTE = """
Charizard @ Charizardite Y  
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
"""


class TestGameTheoryAndBayesianAdvisor(unittest.TestCase):
    """Verify IEDS, Zero-Sum Nash, Logit QRE, and Bayesian Top-K Turn Advisor."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.advisor = CoachTurnAdvisor(backend="torch", device="cpu")

    def test_multi_round_iterated_dominance_elimination(self) -> None:
        """Verify multi-round IEDS reduces a 3x3 cascading dominance game to its unique 1x1 core."""
        # Row 2 [0, 0, 0] is strictly dominated by Row 1 [2, 2, 2].
        # Once Row 2 is removed, Col 1 [4, 3] and Col 2 [5, 2] are dominated by Col 0 [1, 2] for minimizer trainer_2.
        # Once only Col 0 remains, Row 0 [1] is strictly dominated by Row 1 [2] for maximizer trainer_1!
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
        # 1. Pure saddle point at (row 0, col 1) with value 3.0
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

        # 2. Asymmetric 2x2 mindgame (e.g., Attack vs Protect / Sucker Punch):
        # U = [[ 2, -1],
        #      [-1,  4]]
        # Analytical Nash:
        # p_0 * 2 + (1 - p_0) * (-1) = p_0 * (-1) + (1 - p_0) * 4  =>  3 p_0 - 1 = 4 - 5 p_0  =>  8 p_0 = 5  => p = [5/8, 3/8] = [0.625, 0.375]
        # Game value v* = 5/8 * 2 - 3/8 * 1 = 7/8 = 0.875
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
        # Row 0 dominates Row 1 -> trainer_1 QRE must place >95% weight on Row 0
        self.assertGreater(float(qre.trainer_1_strategy[0]), 0.95)
        # Col 1 is better for minimizer trainer_2 when Row 0 is played -> Col 1 gets >90% weight
        self.assertGreater(float(qre.trainer_2_strategy[1]), 0.90)

    def test_end_to_end_coach_turn_advisor_and_bayesian_blending(self) -> None:
        """Verify CoachTurnAdvisor runs inference, multi-hypothesis simulation, IEDS, Nash, and QRE."""
        t1_sets = parse_showdown_paste(ADVISOR_TEAM_PASTE)

        # Give trainer_2 unrevealed sets (only species known from Team Preview / Lead reveal)
        t2_sets = {
            "Garchomp": ParsedPokemon(species="Garchomp", base_species="Garchomp"),
            "Kingambit": ParsedPokemon(species="Kingambit", base_species="Kingambit"),
            "Charizard": ParsedPokemon(species="Charizard", base_species="Charizard"),
            "Rillaboom": ParsedPokemon(species="Rillaboom", base_species="Rillaboom"),
        }

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

        advice = self.advisor.advise_battle(
            battle=battle,
            max_hypotheses=2,
            num_simulations=24,
            min_prior_threshold=0.80,
            rng_seed=77,
            top_k_recommendations=5,
        )

        self.assertGreaterEqual(advice.num_hypotheses, 1)
        self.assertEqual(len(advice.recommendations), 5)

        best = advice.best_recommendation
        self.assertIn("Charizard:", best.description)
        self.assertIn("Rillaboom:", best.description)
        self.assertGreaterEqual(best.expected_mean_utility_vs_nash, best.expected_cvar_10_vs_nash - 1e-5)

        # Test Coach (plain English) verbosity
        coach_text = advice.format_report(verbosity="coach", max_recommendations=3)
        self.assertIn("TURN COACH ADVICE (MATCH PLAY)", coach_text)
        self.assertIn("🎯 RECOMMENDED PLAY FOR THIS TURN", coach_text)
        self.assertIn("💡 WHY THIS PLAY", coach_text)
        self.assertIn("⚠️ WHAT COULD GO WRONG (THE RISK)", coach_text)
        self.assertIn("📊 FIELD SURVIVAL & KO PROBABILITIES", coach_text)

        # Test Standard (tactical metrics) verbosity
        standard_text = advice.format_report(verbosity="standard", max_recommendations=3)
        self.assertIn("BAYESIAN RISK-RESILIENT RECOMMENDATIONS FOR TRAINER_1", standard_text)
        self.assertIn("EXPECTED SLOT SURVIVAL / KO ODDS", standard_text)

        # Test Scientific (full mathematical & process audit) verbosity
        sci_text = advice.format_report(verbosity="scientific", max_recommendations=3)
        self.assertIn("COMPREHENSIVE MATHEMATICAL & PROCESS AUDIT REPORT", sci_text)
        self.assertIn("STEP 1: INGESTION & 66-SP REGULATION M-C STAT PIPELINE", sci_text)
        self.assertIn("STEP 2: COMBINATORIC ACTION SPACE & LOGICAL CONSTRAINT PRUNING", sci_text)
        self.assertIn("STEP 3: DISCRETE-RNG DUAL-DRAW SPINNING-WHEEL & 5-PHASE CASCADE", sci_text)
        self.assertIn("STEP 4: RISK-RESILIENT METRICS & BAD-LUCK FLOOR (CVaR_10)", sci_text)
        self.assertIn("STEP 5: GAME-THEORETIC SOLVERS (IEDS, ZERO-SUM NASH, LOGIT QRE)", sci_text)
        self.assertIn("STEP 6: RANKED JOINT ACTION EVALUATION TABLE", sci_text)

        eq_report = format_equilibrium_coach_report(
            advice.hypothesis_evaluations[0].equilibrium,
            num_simulations=24,
            verbosity="coach",
            max_recommendations=3,
        )
        self.assertIn("TURN COACH ADVICE", eq_report)

        eq_report_sci = format_equilibrium_coach_report(
            advice.hypothesis_evaluations[0].equilibrium,
            num_simulations=24,
            verbosity="scientific",
            max_recommendations=3,
        )
        self.assertIn("MATHEMATICAL & PROCESS AUDIT", eq_report_sci)


if __name__ == "__main__":
    unittest.main()

