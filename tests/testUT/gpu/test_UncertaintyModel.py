# -*- coding: utf-8 -*-
"""
Unit tests for UncertaintyModel (engine/gpu/uncertainty.py).
Verifies exact 16-roll damage distribution, critical hit stages, move accuracy
convolution, quantile monotonicity, and luck delta calculation.
"""

from pathlib import Path
import unittest

from engine.gpu.uncertainty import DAMAGE_ROLLS_16, UncertaintyModel, UncertaintyProfile
from engine.tactics.action_pruner import ActionPruner
from engine.tactics.showdown_parser import ShowdownParser


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


class TestUncertaintyModel(unittest.TestCase):
    """Unit test suite for UncertaintyModel."""

    def setUp(self) -> None:
        """Initialize UncertaintyModel with default risk aversion."""
        self.model = UncertaintyModel(risk_lambda=0.25)

    def test_compute_damage_distribution_quantiles_and_bounds(self) -> None:
        """Verify 16-roll + crit + accuracy convolution obeys quantile monotonicity."""
        base_rolls = [round(80.0 * r, 2) for r in DAMAGE_ROLLS_16]
        profile = self.model.compute_damage_distribution(
            base_rolls_16=base_rolls,
            crit_stage=0,
            accuracy_pct=90.0,
            defender_hp=75.0,
            observed_damage=78.0,
        )
        self.assertIsInstance(profile, UncertaintyProfile)
        self.assertLessEqual(profile.p10, profile.p50)
        self.assertLessEqual(profile.p50, profile.p90)
        self.assertLessEqual(profile.p90, profile.p95)
        self.assertGreaterEqual(profile.ko_probability, 0.0)
        self.assertLessEqual(profile.ko_probability, 1.0)
        self.assertGreaterEqual(profile.survival_probability, 0.0)
        self.assertLessEqual(profile.survival_probability, 1.0)
        self.assertAlmostEqual(
            profile.luck_delta,
            round(78.0 - profile.expected_payoff, 4),
            places=3,
        )

    def test_guaranteed_crit_increases_ko_probability(self) -> None:
        """Verify stage 3 critical hit (100% crit) raises KO probability on borderline targets."""
        base_rolls = [round(75.0 * r, 2) for r in DAMAGE_ROLLS_16]
        p_stage0 = self.model.compute_damage_distribution(
            base_rolls_16=base_rolls,
            crit_stage=0,
            accuracy_pct=100.0,
            defender_hp=90.0,
        )
        p_stage3 = self.model.compute_damage_distribution(
            base_rolls_16=base_rolls,
            crit_stage=3,
            accuracy_pct=100.0,
            defender_hp=90.0,
        )
        self.assertGreater(p_stage3.ko_probability, p_stage0.ko_probability)
        self.assertEqual(p_stage3.ko_probability, 1.0)

    def test_evaluate_turn_uncertainty_over_snapshot(self) -> None:
        """Verify turn-level uncertainty evaluation on a real TurnSnapshot and action pair."""
        parser = ShowdownParser()
        pruner = ActionPruner()
        raw_log = SAMPLE_LOG_PATH.read_text(encoding="utf-8")
        history = parser.parse(raw_log)
        snap = history.turns[2]
        p1_lines = pruner.prune_side_actions(snap, side="p1")
        p2_lines = pruner.prune_side_actions(snap, side="p2")
        prof = self.model.evaluate_turn_uncertainty(
            snapshot=snap,
            p1_line=p1_lines[0],
            p2_line=p2_lines[0],
        )
        dump = prof.model_dump()
        self.assertIn("expected_payoff", dump)
        self.assertIn("risk_adjusted_value", dump)
        self.assertLessEqual(prof.p10, prof.p95)


if __name__ == "__main__":
    unittest.main()
