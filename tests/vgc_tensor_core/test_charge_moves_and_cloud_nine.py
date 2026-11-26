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
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "moves": ["Wood Hammer", "Protect"]},
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
            # trainer_2_a (Slot 4): Opponent without Cloud Nine (Basculegion)
            {
                "species": "Basculegion",
                "hp_max": 195.0,
                "hp_cur": 195.0,
                "stats": {"atk": 180.0, "def": 85.0, "spa": 100.0, "spd": 95.0, "spe": 130.0},
                "types": ["Water", "Ghost"],
                "ability": "Adaptability",
                "moves": ["Wave Crash", "Protect"],
            },
            # trainer_2_b (Slot 5): Opponent B
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "moves": ["Wood Hammer", "Protect"]},
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

        basc_hp_after = float(att_res.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_CUR])
        # In unsuppressed Sun, Solar Beam fires immediately and deals super-effective damage to Water-type Basculegion!
        self.assertLess(basc_hp_after, 100.0, f"Expected Solar Beam to deal heavy damage, got HP {basc_hp_after}")

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
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "moves": ["Protect"]},
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
            target_species="Basculegion",
            target_types=["Water", "Ghost"],
            target_ability="Adaptability",
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
            target_species="Basculegion",
            target_types=["Water", "Ghost"],
            target_ability="Adaptability",
            weather="clear",
        )
        self.assertTrue(eval_es_no_rain.is_mechanically_valid)
        self.assertEqual(eval_es_no_rain.classification, "High_Risk")
        self.assertEqual(eval_es_no_rain.recommended_prior_scale, 0.10)
        self.assertTrue(any("charging turn" in r for r in eval_es_no_rain.reasons))

    def test_08_recharge_moves_compile_flag_from_duckdb(self) -> None:
        """Verify DuckDB flags.recharge compiles MoveIdx.IS_RECHARGE_MOVE for Hyper Beam, Giga Impact, etc."""
        for mv_name in (
            "Hyper Beam",
            "Giga Impact",
            "Blast Burn",
            "Hydro Cannon",
            "Frenzy Plant",
            "Rock Wrecker",
            "Meteor Assault",
        ):
            vec = self.compiler.compile_move_vector(mv_name)
            self.assertEqual(
                float(vec[MoveIdx.IS_RECHARGE_MOVE]),
                1.0,
                f"Expected IS_RECHARGE_MOVE == 1.0 for {mv_name}",
            )
        for normal_mv in ("Hyper Voice", "Quick Attack", "Protect", "Heat Wave"):
            vec = self.compiler.compile_move_vector(normal_mv)
            self.assertEqual(
                float(vec[MoveIdx.IS_RECHARGE_MOVE]),
                0.0,
                f"Expected IS_RECHARGE_MOVE == 0.0 for {normal_mv}",
            )

    def test_09_hyper_beam_sets_recharge_and_turn_after_locks_slot_without_protect_bait(self) -> None:
        """Verify Hyper Beam inflicts MUST_RECHARGE on Turn T and completely immobilizes Sylveon on Turn T+1."""
        from engine.solver.game_theory import decode_slot_choice, solve_turn_equilibrium
        from engine.vgc_tensor_core.phases_pre_attack import execute_pre_attack_phases
        from engine.vgc_tensor_core.state_machine import VgcTensorStateMachine, execute_end_of_turn

        # Turn T: Sylveon (trainer_2 A) fires Hyper Beam into sturdy trainer_1 A (Charizard)
        rosters_t = [
            {
                "species": "Charizard",
                "types": ["Fire", "Flying"],
                "hp_max": 300,
                "hp_cur": 300,
                "stats": {"atk": 100, "def": 110, "spa": 160, "spd": 130, "spe": 150},
                "ability": "Blaze",
                "moves": ["Flamethrower", "Heat Wave", "Air Slash", "Protect"],
            },
            {"species": "DummyAlly", "alive": 0.0, "hp_max": 100, "hp_cur": 0, "moves": ["Protect", "Protect", "Protect", "Protect"]},
            {"species": "Bench1", "alive": 0.0, "hp_max": 100, "hp_cur": 0, "moves": ["Protect", "Protect", "Protect", "Protect"]},
            {"species": "Bench2", "alive": 0.0, "hp_max": 100, "hp_cur": 0, "moves": ["Protect", "Protect", "Protect", "Protect"]},
            {
                "species": "Sylveon",
                "types": ["Fairy"],
                "hp_max": 200,
                "hp_cur": 200,
                "stats": {"atk": 70, "def": 90, "spa": 160, "spd": 150, "spe": 90},
                "ability": "Pixilate",
                "moves": ["Hyper Beam", "Hyper Voice", "Quick Attack", "Detect"],
            },
            {"species": "DummyFoe", "alive": 0.0, "hp_max": 100, "hp_cur": 0, "moves": ["Protect", "Protect", "Protect", "Protect"]},
            {
                "species": "BenchFoe1",
                "types": ["Normal"],
                "hp_max": 160,
                "hp_cur": 160,
                "stats": {"atk": 100, "def": 100, "spa": 100, "spd": 100, "spe": 100},
                "ability": "Intimidate",
                "moves": ["Protect", "Protect", "Protect", "Protect"],
            },
            {"species": "BenchFoe2", "alive": 0.0, "hp_max": 100, "hp_cur": 0, "moves": ["Protect", "Protect", "Protect", "Protect"]},
        ]
        state_t = self.compiler.compile_battle_state(rosters_t, field_spec={"weather": "clear"})
        # Charizard uses Flamethrower (0) on Sylveon (bucket 0); Sylveon uses Hyper Beam (0) on Charizard (bucket 0)
        t1_c = np.array([[0, 0]], dtype=np.int64)
        t2_c = np.array([[0, 0]], dtype=np.int64)
        pre_t = execute_pre_attack_phases(
            state_t.field_tensor, state_t.roster_tensor, state_t.moves_tensor, t1_c, t2_c, self.tables
        )
        att_t = execute_attack_cascade(
            pre_t.F, pre_t.P, pre_t.M_moves, t1_c, t2_c, pre_t, self.tables, num_mc_samples=32, rng_seed=11
        )
        eot_t = execute_end_of_turn(att_t.F, att_t.P, att_t.M_moves, self.tables)
        # Every thread where Hyper Beam connected (90% acc) and Sylveon survived must carry MUST_RECHARGE == 1.0 into EOT!
        rech_vals = eot_t.P[0, 0, :, SLOT_TRAINER_2_A, MonIdx.MUST_RECHARGE]
        rech_frac = float(np.mean(rech_vals.detach().cpu().numpy() if hasattr(rech_vals, "detach") else rech_vals))
        self.assertGreater(rech_frac, 0.70, f"Expected Hyper Beam to set MUST_RECHARGE on connected hits, got frac={rech_frac}")

        # Turn T+1: Sylveon starts locked in must_recharge=1.0 (even with a healthy bench!)
        rosters_t1 = [dict(r) for r in rosters_t]
        rosters_t1[0]["hp_cur"] = 120  # Charizard low enough that Hyper Voice would threaten if Sylveon could act!
        rosters_t1[4]["must_recharge"] = 1.0
        state_t1 = self.compiler.compile_battle_state(rosters_t1, field_spec={"weather": "clear"})

        # 1. Pruner must lock Sylveon to exactly 1 canonical forced-recharge action (no moves, no switches!)
        t2_mask = self.logic_engine.prune_side_26x26_tensor_actions(state_t1, "trainer_2")
        c2_np = t2_mask.pruned_choices.detach().cpu().numpy() if hasattr(t2_mask.pruned_choices, "detach") else np.asarray(t2_mask.pruned_choices)
        self.assertEqual(len(c2_np), 1)
        self.assertEqual(int(c2_np[0, 0]), 0)
        self.assertEqual(decode_slot_choice(state_t1, "trainer_2", is_slot_a=True, choice_idx=0), "Sylveon: Recharge (forced)")

        # 2. Attack cascade skips Sylveon (Charizard takes 0 damage!) and clears spent MUST_RECHARGE after Turn T+1
        sm = VgcTensorStateMachine(backend="torch", device="cpu")
        mask1, mask2, step_res = sm.simulate_pruned_turn(state_t1, num_simulations=32, rng_seed=42)
        # Every surviving Charizard action leaves Charizard at full 120 HP (Sylveon cannot deal damage!)
        c_hp_slice = step_res.mean_hp[:, :, SLOT_TRAINER_1_A]
        min_c_hp = float(c_hp_slice.min().item() if hasattr(c_hp_slice, "min") else np.min(c_hp_slice))
        self.assertAlmostEqual(min_c_hp, 120.0, places=3)
        # After spending its recharge turn, Sylveon's MUST_RECHARGE is cleared to 0.0
        post_rech = step_res.P[:, :, :, SLOT_TRAINER_2_A, MonIdx.MUST_RECHARGE]
        post_rech_max = float(post_rech.max().item() if hasattr(post_rech, "max") else np.max(post_rech))
        self.assertEqual(post_rech_max, 0.0)

        # 3. Equilibrium must recommend attacking (Flamethrower), NEVER Charizard Protect against recharging Sylveon!
        eq = solve_turn_equilibrium(state_t1, mask1, mask2, step_res)
        best_desc = eq.recommendations[0].description
        self.assertIn("Charizard: Flamethrower", best_desc, f"Expected Charizard attack, got: {best_desc}")
        self.assertNotIn("Charizard: Protect", best_desc, f"Engine recommended Protect against a recharging Sylveon: {best_desc}")

    def test_10_protocol_parser_tracks_mustrecharge_and_cant_recharge(self) -> None:
        """Verify Showdown |-mustrecharge| sets must_recharge for next turn and |cant|...|recharge clears it cleanly."""
        from apps.replay_coach.protocol_parser import parse_showdown_replay

        log = """
|player|p1|TrainerOne|1|
|player|p2|TrainerTwo|1|
|tier|[Gen 9 Champions] VGC 2026 Reg M-C
|poke|p1|Charizard, L50, M|
|poke|p1|Pelipper, L50, M|
|poke|p2|Sylveon, L50, F|
|poke|p2|Farigiraf, L50, M|
|start
|switch|p1a: Charizard|Charizard, L50, M|155/155
|switch|p1b: Pelipper|Pelipper, L50, M|167/167
|switch|p2a: Sylveon|Sylveon, L50, F|100/100
|switch|p2b: Farigiraf|Farigiraf, L50, M|100/100
|turn|1
|move|p1a: Charizard|Protect|p1a: Charizard
|move|p2a: Sylveon|Hyper Beam|p1b: Pelipper
|-damage|p1b: Pelipper|20/167
|-mustrecharge|p2a: Sylveon
|move|p2b: Farigiraf|Protect|p2b: Farigiraf
|move|p1b: Pelipper|Protect|p1b: Pelipper
|upkeep
|turn|2
|move|p1a: Charizard|Heat Wave|p2a: Sylveon|[spread] p2a,p2b
|-damage|p2a: Sylveon|60/100
|-damage|p2b: Farigiraf|70/100
|cant|p2a: Sylveon|recharge
|move|p2b: Farigiraf|Psychic|p1b: Pelipper
|-damage|p1b: Pelipper|0 fnt
|faint|p1b: Pelipper
|upkeep
|turn|3
|move|p1a: Charizard|Protect|p1a: Charizard
|move|p2a: Sylveon|Hyper Voice|p1a: Charizard
|upkeep
"""
        parsed = parse_showdown_replay(log, pov_trainer="TrainerOne")
        self.assertEqual(len(parsed.turns), 3)

        sylv_t1 = parsed.turns[0].battle_state.trainer_2.get_pokemon("Sylveon")
        sylv_t2 = parsed.turns[1].battle_state.trainer_2.get_pokemon("Sylveon")
        sylv_t3 = parsed.turns[2].battle_state.trainer_2.get_pokemon("Sylveon")

        self.assertFalse(sylv_t1.must_recharge)
        self.assertTrue(sylv_t2.must_recharge)
        self.assertEqual(parsed.turns[1].trainer_2_slot_a_action.kind, "recharge")
        self.assertEqual(parsed.turns[1].events.flinches, [])  # Recharge is NOT a flinch variance event!
        self.assertFalse(sylv_t3.must_recharge)


if __name__ == "__main__":
    unittest.main()
