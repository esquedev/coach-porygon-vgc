#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for Logical Constraint Engine (engine/tactics/logic_engine.py)
Validates:
1. Physical invariants (Fake Out active_turns > 1, priority on grounded under Psychic Terrain).
2. Soft tactical constraints (Consecutive Protect as High-Risk/High-Reward).
3. Continuous risk-reward scoring (0.25x double resistances, 0x immunity switch reads, 4x double weaknesses).
4. Accuracy risk evaluation and weather bypasses.
"""

import unittest

from engine.tactics.logic_engine import ConstraintResult, LogicalConstraintEngine


class TestLogicEngine(unittest.TestCase):
    """Verifies logical invariants, soft constraints, and risk-reward continuum."""

    def setUp(self):
        """Initialize LogicalConstraintEngine instance."""
        self.engine = LogicalConstraintEngine()

    def test_physical_invariant_fake_out_turn_restriction(self):
        """Test that Fake Out is flagged mechanically invalid on turn > 1, but valid on turn 1."""
        res_t2 = self.engine.evaluate_slot_action(
            slot_species="Incineroar",
            move_name="Fake Out",
            target_species="Garchomp",
            active_turns=2,
        )
        self.assertFalse(res_t2.is_mechanically_valid)
        self.assertEqual(res_t2.classification, "Mechanically_Invalid")
        self.assertEqual(res_t2.recommended_prior_scale, 0.001)

        res_t1 = self.engine.evaluate_slot_action(
            slot_species="Incineroar",
            move_name="Fake Out",
            target_species="Garchomp",
            active_turns=1,
        )
        self.assertTrue(res_t1.is_mechanically_valid)
        self.assertEqual(res_t1.classification, "Deterministic_Safe")

    def test_soft_constraint_consecutive_protect_high_risk_high_reward(self):
        """Test consecutive Protect is recognized as viable high-risk/high-reward rather than 0% dropped."""
        res_consec = self.engine.evaluate_slot_action(
            slot_species="Garchomp",
            move_name="Protect",
            was_protected_last_turn=True,
        )
        self.assertTrue(res_consec.is_mechanically_valid)
        self.assertEqual(res_consec.classification, "High_Risk_High_Reward")
        self.assertEqual(res_consec.risk_score, 0.67)
        self.assertEqual(res_consec.recommended_prior_scale, 0.40)

        res_fresh = self.engine.evaluate_slot_action(
            slot_species="Garchomp",
            move_name="Protect",
            was_protected_last_turn=False,
        )
        self.assertTrue(res_fresh.is_mechanically_valid)
        self.assertEqual(res_fresh.classification, "Deterministic_Safe")

    def test_priority_psychic_terrain_grounded_vs_airborne(self):
        """Test priority move fails on grounded target under Psychic Terrain but connects on airborne."""
        res_grounded = self.engine.evaluate_slot_action(
            slot_species="Dragonite",
            move_name="Extreme Speed",
            target_species="Garchomp",
            field_state={"terrain": "psychic"},
            is_target_airborne=False,
        )
        self.assertFalse(res_grounded.is_mechanically_valid)
        self.assertEqual(res_grounded.classification, "Mechanically_Invalid")

        res_airborne = self.engine.evaluate_slot_action(
            slot_species="Dragonite",
            move_name="Extreme Speed",
            target_species="Charizard",
            field_state={"terrain": "psychic"},
            is_target_airborne=True,
        )
        self.assertTrue(res_airborne.is_mechanically_valid)
        self.assertEqual(res_airborne.classification, "Calculated_Risk")

    def test_type_effectiveness_risk_reward_scoring(self):
        """Test 4x weakness, 0.25x double resistance, and 0x immunity switch read scoring."""
        # 4.0x Rock into Charizard (Fire/Flying)
        res_4x = self.engine.evaluate_slot_action(
            slot_species="Tyranitar",
            move_name="Rock Slide",
            target_species="Charizard",
        )
        self.assertTrue(res_4x.is_mechanically_valid)
        self.assertEqual(res_4x.classification, "Deterministic_Safe")
        self.assertGreaterEqual(res_4x.recommended_prior_scale, 1.2)

        # 0.25x Grass into Charizard (Fire/Flying)
        res_025x = self.engine.evaluate_slot_action(
            slot_species="Venusaur",
            move_name="Energy Ball",
            target_species="Charizard",
        )
        self.assertTrue(res_025x.is_mechanically_valid)
        self.assertEqual(res_025x.classification, "Calculated_Risk")
        self.assertEqual(res_025x.recommended_prior_scale, 0.50)

        # 0.0x Ground into Charizard (Airborne)
        res_0x = self.engine.evaluate_slot_action(
            slot_species="Garchomp",
            move_name="Earthquake",
            target_species="Charizard",
            is_target_airborne=True,
        )
        self.assertTrue(res_0x.is_mechanically_valid)
        self.assertEqual(res_0x.classification, "High_Risk_High_Reward")
        self.assertEqual(res_0x.recommended_prior_scale, 0.20)

    def test_accuracy_risk_scoring_and_weather_bypass(self):
        """Test accuracy risk scoring and 100% weather bypasses."""
        res_focus_blast = self.engine.evaluate_slot_action(
            slot_species="Gengar",
            move_name="Focus Blast",
            target_species="Tyranitar",
        )
        self.assertTrue(res_focus_blast.is_mechanically_valid)
        self.assertEqual(res_focus_blast.classification, "Calculated_Risk")
        self.assertEqual(res_focus_blast.risk_score, 0.30)

        res_thunder_rain = self.engine.evaluate_slot_action(
            slot_species="Archaludon",
            move_name="Thunder",
            target_species="Pelipper",
            field_state={"weather": "rain"},
        )
        self.assertTrue(res_thunder_rain.is_mechanically_valid)
        self.assertEqual(res_thunder_rain.classification, "Deterministic_Safe")


if __name__ == "__main__":
    unittest.main()
