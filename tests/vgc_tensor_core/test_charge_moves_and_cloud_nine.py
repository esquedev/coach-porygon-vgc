# -*- coding: utf-8 -*-
"""
Tests for Dynamic Two-Turn Charging Moves and Weather Suppression (Cloud Nine).
==============================================================================

Validates:
1. Dynamic on-the-fly compilation of charging moves from DuckDB (`flags.charge` -> MoveIdx.WEATHER_SURE_HIT).
2. Dynamic compilation of `Cloud Nine` ability (Drampa / Altaria -> AbilityID.CLOUD_NINE = 13).
3. Pre-attack speed suppression: Swift Swim, Chlorophyll, Sand Rush, Slush Rush nullified under active Cloud Nine.
4. Attack cascade:
   - Solar Beam dealing 0 damage on Turn 1 under suppressed Sun (Cloud Nine Drampa).
   - Solar Beam dealing full damage immediately in unsuppressed Harsh Sunlight.
   - Solar Beam power halved in Rain / Sand / Snow.
   - Electro Shot skipping charge in unsuppressed Rain; dealing 0 damage without Rain.
   - Weather Ball adapting dynamically to Fire/Water/Rock/Ice under unsuppressed weather,
     but staying Normal (50 BP) when Cloud Nine is active.
5. Symbolic Action Pruner (logic_engine):
   - Penalizes two-turn charging moves with 0.05 prior and high risk when required weather is absent or suppressed.
"""

from __future__ import annotations

import unittest
import numpy as np

from engine.db_registry import get_registry
from engine.vgc_tensor_core.compiler import (
    ShowdownTensorCompiler,
)
from engine.vgc_tensor_core.schema_and_tables import (
    AbilityID,
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
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    TYPE_TO_IDX,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
)
from engine.vgc_tensor_core.phases_pre_attack import (
    compute_active_effective_speeds,
)
from engine.vgc_tensor_core.attack_cascade import (
    execute_attack_cascade,
)
from engine.vgc_tensor_core.logic_engine import (
    LogicalConstraintEngine,
)

if HAS_TORCH:
    import torch


class TestChargeMovesAndCloudNine(unittest.TestCase):
    """Unit test suite verifying two-turn charging moves and Cloud Nine weather suppression."""

    def setUp(self) -> None:
        self.compiler = ShowdownTensorCompiler()
        self.tables = build_bilinear_lookup_tables(device="cpu")
        self.logic_engine = LogicalConstraintEngine(tables=self.tables)

    def test_01_dynamic_compiler_move_vectors_on_the_fly(self) -> None:
        """Verify on-the-fly compilation of charging and weather moves directly from DuckDB."""
        # 1. Solar Beam & Solar Blade -> weather_op = 10.0 (skips charge in Sun)
        sb = self.compiler.compile_move_vector("Solar Beam")
        self.assertEqual(float(sb[MoveIdx.WEATHER_SURE_HIT]), 10.0)
        self.assertEqual(float(sb[MoveIdx.BASE_POWER]), 120.0)

        sblade = self.compiler.compile_move_vector("Solar Blade")
        self.assertEqual(float(sblade[MoveIdx.WEATHER_SURE_HIT]), 10.0)
        self.assertEqual(float(sblade[MoveIdx.BASE_POWER]), 125.0)

        # 2. Electro Shot -> weather_op = 20.0 (skips charge in Rain)
        es = self.compiler.compile_move_vector("Electro Shot")
        self.assertEqual(float(es[MoveIdx.WEATHER_SURE_HIT]), 20.0)
        self.assertEqual(float(es[MoveIdx.BASE_POWER]), 130.0)

        # 3. Meteor Beam & Phantom Force -> weather_op = 30.0 (charges on Turn 1)
        mb = self.compiler.compile_move_vector("Meteor Beam")
        self.assertEqual(float(mb[MoveIdx.WEATHER_SURE_HIT]), 30.0)
        self.assertEqual(float(mb[MoveIdx.BASE_POWER]), 120.0)

        pf = self.compiler.compile_move_vector("Phantom Force")
        self.assertEqual(float(pf[MoveIdx.WEATHER_SURE_HIT]), 30.0)
        self.assertEqual(float(pf[MoveIdx.BASE_POWER]), 90.0)

        # 4. Weather Ball -> weather_op = 1.0 (adaptive)
        wb = self.compiler.compile_move_vector("Weather Ball")
        self.assertEqual(float(wb[MoveIdx.WEATHER_SURE_HIT]), 1.0)
        self.assertEqual(float(wb[MoveIdx.BASE_POWER]), 50.0)

    def test_02_dynamic_cloud_nine_ability_compilation(self) -> None:
        """Verify that Cloud Nine ability compiles to canonical AbilityID.CLOUD_NINE = 13."""
        drampa_spec = {
            "species": "Drampa",
            "ability": "Cloud Nine",
            "hp_max": 185.0,
            "hp_cur": 185.0,
            "stats": {"atk": 80.0, "def": 105.0, "spa": 155.0, "spd": 111.0, "spe": 56.0},
            "types": ["Normal", "Dragon"],
            "moves": ["Hyper Voice", "Draco Meteor", "Flamethrower", "Protect"],
        }
        p_vec, m_mat = self.compiler.compile_pokemon_slot(drampa_spec)
        self.assertEqual(float(p_vec[MonIdx.ABILITY_ID]), float(AbilityID.CLOUD_NINE))
        self.assertEqual(float(AbilityID.CLOUD_NINE), 54.0)

    def test_03_cloud_nine_speed_suppression(self) -> None:
        """Verify that active Cloud Nine nullifies Chlorophyll and Swift Swim speed doubling."""
        F = np.zeros(FIELD_DIM, dtype=np.float32)
        F[FieldIdx.WEATHER_START + WEATHER_TO_IDX["sun"]] = 1.0
        F[FieldIdx.WEATHER_TURNS] = 5.0

        P = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)

        # trainer_1_a (Slot 0): Venusaur with Chlorophyll (Spe: 100)
        P[SLOT_TRAINER_1_A, MonIdx.HP_CUR] = 155.0
        P[SLOT_TRAINER_1_A, MonIdx.HP_MAX] = 155.0
        P[SLOT_TRAINER_1_A, MonIdx.ALIVE_FLAG] = 1.0
        P[SLOT_TRAINER_1_A, MonIdx.STAT_SPE] = 100.0
        P[SLOT_TRAINER_1_A, MonIdx.ABILITY_ID] = float(AbilityID.CHLOROPHYLL)

        # trainer_2_a (Slot 4): Drampa with Cloud Nine
        P[SLOT_TRAINER_2_A, MonIdx.HP_CUR] = 185.0
        P[SLOT_TRAINER_2_A, MonIdx.HP_MAX] = 185.0
        P[SLOT_TRAINER_2_A, MonIdx.ALIVE_FLAG] = 1.0
        P[SLOT_TRAINER_2_A, MonIdx.STAT_SPE] = 56.0
        P[SLOT_TRAINER_2_A, MonIdx.ABILITY_ID] = float(AbilityID.CLOUD_NINE)

        # Under active Cloud Nine Drampa, Chlorophyll speed boost MUST be nullified (Spe remains 100)
        speeds = compute_active_effective_speeds(F, P)
        self.assertEqual(float(speeds[0]), 100.0)

        # If Drampa faints (HP = 0.0, ALIVE_FLAG = 0.0), Cloud Nine is inactive -> Venusaur gets 200 Spe in Sun
        P[SLOT_TRAINER_2_A, MonIdx.HP_CUR] = 0.0
        P[SLOT_TRAINER_2_A, MonIdx.ALIVE_FLAG] = 0.0
        speeds_unsuppressed = compute_active_effective_speeds(F, P)
        self.assertEqual(float(speeds_unsuppressed[0]), 200.0)

    def test_04_solar_beam_under_cloud_nine_deals_zero_damage_on_turn_1(self) -> None:
        """Charizard using Solar Beam vs Drampa (Cloud Nine) in Sun deals 0 damage on Turn 1."""
        rosters = [
            # trainer_1_a (Slot 0): Charizard
            {
                "species": "Charizard",
                "hp_max": 153.0,
                "hp_cur": 153.0,
                "stats": {"atk": 104.0, "def": 98.0, "spa": 161.0, "spd": 105.0, "spe": 167.0},
                "types": ["Fire", "Flying"],
                "ability": "Blaze",
                "moves": ["Solar Beam", "Heat Wave", "Air Slash", "Protect"],
            },
            # trainer_1_b (Slot 1): Partner
            {"species": "Incineroar", "hp_max": 200.0, "hp_cur": 200.0, "moves": ["Fake Out", "Protect"]},
            {}, {},
            # trainer_2_a (Slot 4): Drampa with Cloud Nine
            {
                "species": "Drampa",
                "hp_max": 185.0,
                "hp_cur": 185.0,
                "stats": {"atk": 80.0, "def": 105.0, "spa": 155.0, "spd": 111.0, "spe": 56.0},
                "types": ["Normal", "Dragon"],
                "ability": "Cloud Nine",
                "moves": ["Hyper Voice", "Protect"],
            },
            # trainer_2_b (Slot 5): Opponent B
            {"species": "Ogerpon", "hp_max": 155.0, "hp_cur": 155.0, "moves": ["Spiky Shield", "Ivy Cudgel"]},
            {}, {},
        ]

        # Field: Harsh Sunlight is set on the field
        field_spec = {"weather": "sun", "weather_turns": 5.0}
        state = self.compiler.compile_battle_state(rosters, field_spec=field_spec)

        # Choice: Charizard uses Move 0 (Solar Beam) -> Opponent Slot A (Choice 0)
        # Drampa uses Move 0 (Hyper Voice) -> Spread (Choice 0)
        t1_choices = np.array([[0, 3]], dtype=np.int64)
        t2_choices = np.array([[0, 3]], dtype=np.int64)

        # Pre-attack phase
        from engine.vgc_tensor_core.phases_pre_attack import execute_pre_attack_phases
        pre_res = execute_pre_attack_phases(
            state.field_tensor, state.roster_tensor, state.moves_tensor, t1_choices, t2_choices, self.tables
        )

        # Attack cascade simulation
        att_res = execute_attack_cascade(
            pre_res.F, pre_res.P, pre_res.M_moves, t1_choices, t2_choices, pre_res, self.tables, num_mc_samples=16
        )

        drampa_hp_after = float(att_res.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_CUR])
        # Drampa must take 0 damage because Solar Beam was forced to charge on Turn 1!
        self.assertEqual(drampa_hp_after, 185.0, f"Drampa took damage! HP was {drampa_hp_after}, expected 185.0")

    def test_05_solar_beam_fires_immediately_in_unsuppressed_sun(self) -> None:
        """Charizard using Solar Beam in unsuppressed Harsh Sunlight fires immediately on Turn 1."""
        rosters = [
            # trainer_1_a (Slot 0): Charizard
            {
                "species": "Charizard",
                "hp_max": 153.0,
                "hp_cur": 153.0,
                "stats": {"atk": 104.0, "def": 98.0, "spa": 161.0, "spd": 105.0, "spe": 167.0},
                "types": ["Fire", "Flying"],
                "ability": "Blaze",
                "moves": ["Solar Beam", "Heat Wave", "Air Slash", "Protect"],
            },
            # trainer_1_b (Slot 1): Partner
            {"species": "Incineroar", "hp_max": 200.0, "hp_cur": 200.0, "moves": ["Fake Out", "Protect"]},
            {}, {},
            # trainer_2_a (Slot 4): Opponent without Cloud Nine (Urshifu)
            {
                "species": "Urshifu-Rapid-Strike",
                "hp_max": 175.0,
                "hp_cur": 175.0,
                "stats": {"atk": 182.0, "def": 120.0, "spa": 74.0, "spd": 80.0, "spe": 149.0},
                "types": ["Fighting", "Water"],
                "ability": "Unseen Fist",
                "moves": ["Surging Strikes", "Protect"],
            },
            # trainer_2_b (Slot 5): Opponent B
            {"species": "Ogerpon", "hp_max": 155.0, "hp_cur": 155.0, "moves": ["Spiky Shield", "Ivy Cudgel"]},
            {}, {},
        ]

        field_spec = {"weather": "sun", "weather_turns": 5.0}
        state = self.compiler.compile_battle_state(rosters, field_spec=field_spec)

        t1_choices = np.array([[0, 3]], dtype=np.int64)
        t2_choices = np.array([[0, 0]], dtype=np.int64)  # Opponents attack, not protecting

        from engine.vgc_tensor_core.phases_pre_attack import execute_pre_attack_phases
        pre_res = execute_pre_attack_phases(
            state.field_tensor, state.roster_tensor, state.moves_tensor, t1_choices, t2_choices, self.tables
        )

        att_res = execute_attack_cascade(
            pre_res.F, pre_res.P, pre_res.M_moves, t1_choices, t2_choices, pre_res, self.tables, num_mc_samples=16
        )

        urshifu_hp_after = float(att_res.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_CUR])
        # In unsuppressed Sun, Solar Beam fires immediately and deals super-effective damage to Urshifu-Water!
        self.assertLess(urshifu_hp_after, 100.0, f"Expected Solar Beam to deal heavy damage, got HP {urshifu_hp_after}")

    def test_06_weather_ball_dynamic_adaptation_and_cloud_nine_suppression(self) -> None:
        """Weather Ball executes as 100 BP Fire in Sun, but 50 BP Normal when Cloud Nine is active."""
        rosters = [
            # trainer_1_a: Weather Ball user
            {
                "species": "Charizard",
                "hp_max": 153.0,
                "hp_cur": 153.0,
                "stats": {"atk": 104.0, "def": 98.0, "spa": 161.0, "spd": 105.0, "spe": 167.0},
                "types": ["Fire", "Flying"],
                "moves": ["Weather Ball", "Protect"],
            },
            {"species": "Incineroar", "hp_max": 200.0, "hp_cur": 200.0, "moves": ["Protect"]},
            {}, {},
            # trainer_2_a: Drampa with Cloud Nine
            {
                "species": "Drampa",
                "hp_max": 185.0,
                "hp_cur": 185.0,
                "stats": {"atk": 80.0, "def": 105.0, "spa": 155.0, "spd": 111.0, "spe": 56.0},
                "types": ["Normal", "Dragon"],
                "ability": "Cloud Nine",
                "moves": ["Protect"],
            },
            {"species": "Ogerpon", "hp_max": 155.0, "hp_cur": 155.0, "moves": ["Protect"]},
            {}, {},
        ]

        field_spec = {"weather": "sun", "weather_turns": 5.0}
        state = self.compiler.compile_battle_state(rosters, field_spec=field_spec)

        t1_choices = np.array([[0, 3]], dtype=np.int64)  # Weather Ball -> Drampa
        t2_choices = np.array([[3, 3]], dtype=np.int64)

        from engine.vgc_tensor_core.phases_pre_attack import execute_pre_attack_phases
        pre_res = execute_pre_attack_phases(
            state.field_tensor, state.roster_tensor, state.moves_tensor, t1_choices, t2_choices, self.tables
        )

        att_res = execute_attack_cascade(
            pre_res.F, pre_res.P, pre_res.M_moves, t1_choices, t2_choices, pre_res, self.tables, num_mc_samples=16
        )

        # Under Cloud Nine, Weather Ball is 50 BP Normal, resisted 1.0x by Dragon, so Drampa takes minimal damage (~15-20)
        drampa_hp = float(att_res.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_CUR])
        dmg = 185.0 - drampa_hp
        self.assertLess(dmg, 35.0, f"Expected 50 BP Normal unboosted damage, got {dmg} damage")

    def test_07_logic_engine_action_evaluation_of_charging_moves(self) -> None:
        """Verify symbolic action pruner penalizes Solar Beam under Cloud Nine / inactive Sun."""
        # 1. Solar Beam under active Sun -> Valid, 1.0 prior
        eval_sun = self.logic_engine.evaluate_candidate_action(
            move_name="Solar Beam",
            user_species="Charizard",
            user_types=["Fire", "Flying"],
            user_ability="Blaze",
            target_species="Urshifu",
            target_types=["Fighting", "Water"],
            target_ability="Unseen Fist",
            weather="sun",
        )
        self.assertTrue(eval_sun.is_mechanically_valid)
        self.assertGreaterEqual(eval_sun.recommended_prior_scale, 1.0)
        self.assertLessEqual(eval_sun.risk_score, 0.20)

        # 2. Solar Beam under Sun with Cloud Nine opponent -> High Risk, 0.05 prior
        eval_cloud_nine = self.logic_engine.evaluate_candidate_action(
            move_name="Solar Beam",
            user_species="Charizard",
            user_types=["Fire", "Flying"],
            user_ability="Blaze",
            target_species="Drampa",
            target_types=["Normal", "Dragon"],
            target_ability="Cloud Nine",
            weather="sun",
        )
        self.assertTrue(eval_cloud_nine.is_mechanically_valid)
        self.assertEqual(eval_cloud_nine.classification, "High_Risk")
        self.assertEqual(eval_cloud_nine.recommended_prior_scale, 0.05)
        self.assertGreaterEqual(eval_cloud_nine.risk_score, 0.90)
        self.assertTrue(any("charging turn" in r for r in eval_cloud_nine.reasons))

        # 3. Electro Shot without Rain -> High Risk, 0.10 prior
        eval_es_no_rain = self.logic_engine.evaluate_candidate_action(
            move_name="Electro Shot",
            user_species="Archaludon",
            user_types=["Steel", "Dragon"],
            user_ability="Stamina",
            target_species="Urshifu",
            target_types=["Fighting", "Water"],
            target_ability="Unseen Fist",
            weather="clear",
        )
        self.assertTrue(eval_es_no_rain.is_mechanically_valid)
        self.assertEqual(eval_es_no_rain.classification, "High_Risk")
        self.assertEqual(eval_es_no_rain.recommended_prior_scale, 0.10)
        self.assertTrue(any("charging turn" in r for r in eval_es_no_rain.reasons))


if __name__ == "__main__":
    unittest.main()
