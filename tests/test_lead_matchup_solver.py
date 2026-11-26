# -*- coding: utf-8 -*-
"""Regulation M-C Anti-Hallucination & Factored 90×90 Lead Matchup Solver Test Suite.

Covers:
1. Anti Regulation M-C Hallucination regressions:
   - `Floette-Eternal @ Floettite` (74 Base HP) & `Meowstic-F @ Meowsticite` Mega evolution
   - Pre-Mega base form normalization on `-Mega` pastes (`Garchomp-Mega-Z`, `Raichu-Mega-Y`, `Charizard-Mega-Y`)
   - Duplicate nickname/species alias deduplication on `data/teams/char_y_v4.txt`
   - `MonIdx.ACTIVE_TURNS == 0.0` Turn-1 `Fake Out` legality & Turn-0 `Psychic Surge` blocking
   - Pure `resolve_turn_zero_lead_entry` single-fire entry abilities (Weather, Terrain, Intimidate, White Herb + Unburden)
   - Verified-move-only Bench Matchup Residual (`-ate`, `Freeze-Dry`, `Levitate`, `Soundproof`)
   - Strict Regulation M-C 66-SP / 32-cap validation & zero-Tera tolerance
2. Factored `90 × 90` Lead & Bring Solver symmetry, Nash/QRE simplexes, progress callbacks, and cancellation.
3. Replay Coach Studio Lead Lab backend APIs (`infer_lead_lab_opponent`, `create_lead_lab_job`,
   bare EV-less OTS rejection, and `run_lead_lab_deep_turn1`).
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import unittest

import numpy as np

from apps.replay_coach.server import ReplayCoachAppState, SAMPLE_REPLAY_PATH
from engine.parser.showdown_parser import parse_showdown_paste
from engine.solver.lead_matchup_solver import (
    LeadMatchupConfig,
    LeadMatchupSolver,
    _effective_move_multiplier,
)
from engine.state.state_compiler import TurnStateCompiler
from engine.vgc_tensor_core.compiler import ShowdownTensorCompiler
from engine.vgc_tensor_core.phases_pre_attack import resolve_turn_zero_lead_entry
from engine.vgc_tensor_core.schema_and_tables import (
    FIELD_DIM,
    FieldIdx,
    MON_DIM,
    MonIdx,
    ROSTER_SLOTS,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    TERRAIN_TO_IDX,
    WEATHER_TO_IDX,
)
from engine.vgc_tensor_core.state_machine import AnalysisCancelledError


REPO_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_4V4_T1 = """
Charizard-Mega-Y @ Charizardite Y
Ability: Blaze
Level: 50
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
- Heat Wave
- Solar Beam
- Protect
- Air Slash

Raichu @ Raichunite X
Ability: Lightning Rod
Level: 50
EVs: 4 HP / 252 Atk / 252 Spe
Jolly Nature
- Fake Out
- Volt Tackle
- Brick Break
- Protect

Pelipper @ Sitrus Berry
Ability: Drizzle
Level: 50
EVs: 252 HP / 4 Def / 252 SpA
Modest Nature
- Weather Ball
- Hurricane
- Tailwind
- Protect

Sneasler @ White Herb
Ability: Unburden
Level: 50
EVs: 4 HP / 252 Atk / 252 Spe
Adamant Nature
- Fake Out
- Close Combat
- Dire Claw
- Protect
"""

SAMPLE_4V4_T2 = """
Incineroar @ Sitrus Berry
Ability: Intimidate
Level: 50
EVs: 252 HP / 124 Def / 132 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Parting Shot

Indeedee-F @ Psychic Seed
Ability: Psychic Surge
Level: 50
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Follow Me
- Psychic
- Trick Room
- Helping Hand

Floette-Eternal @ Floettite
Ability: Flower Veil
Level: 50
EVs: 252 HP / 252 SpA / 4 Spe
Modest Nature
- Light of Ruin
- Moonblast
- Protect
- Helping Hand

Garchomp-Mega-Z @ Garchompite Z
Ability: Rough Skin
Level: 50
EVs: 4 HP / 252 Atk / 252 Spe
Jolly Nature
- Earthquake
- Dragon Claw
- Swords Dance
- Protect
"""


class TestLeadMatchupSolverAndRegMCInvariants(unittest.TestCase):
    """Comprehensive unit and integration tests for Regulation M-C Lead Lab."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.solver = LeadMatchupSolver(device="cpu")
        cls.turn_compiler = TurnStateCompiler()
        cls.tensor_compiler = ShowdownTensorCompiler(backend="numpy", device="cpu")

    def test_floette_eternal_and_meowstic_f_mega_compilation(self) -> None:
        """Floette-Eternal @ Floettite & Meowstic-F @ Meowsticite compile with can_mega_evolve=True."""
        paste = """
Floette-Eternal @ Floettite
Ability: Flower Veil
Level: 50
EVs: 252 HP / 252 SpA / 4 Spe
Modest Nature
- Light of Ruin
- Moonblast
- Protect
- Helping Hand

Floette-Mega @ Floettite
Ability: Flower Veil
Level: 50
EVs: 252 HP / 252 SpA / 4 Spe
Modest Nature
- Light of Ruin
- Moonblast
- Protect
- Helping Hand

Meowstic-F @ Meowsticite
Ability: Competitive
Level: 50
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
- Psychic
- Expanding Force
- Protect
- Fake Out
"""
        parsed = parse_showdown_paste(paste)
        fl_et = self.turn_compiler.compile_pokemon(parsed["Floette-Eternal"], trainer_mega_used=False)
        fl_mg = self.turn_compiler.compile_pokemon(parsed["Floette-Mega"], trainer_mega_used=False)
        mw_f = self.turn_compiler.compile_pokemon(parsed["Meowstic-F"], trainer_mega_used=False)

        self.assertTrue(fl_et.can_mega_evolve)
        self.assertEqual(fl_et.mega_target_species, "Floette-Mega")
        self.assertEqual(fl_et.max_hp, 181)  # Base 74 + 32 SP + 75
        self.assertEqual(fl_et.level_50_stats["spe"], 113)
        self.assertEqual(fl_et.mega_level_50_stats["spe"], 123)
        self.assertEqual(fl_et.mega_ability, "Fairy Aura")

        # Floette-Mega paste (pre-Mega Turn 0) MUST inherit Floette-Eternal stats (HP=181, not base Floette 161!)
        self.assertTrue(fl_mg.can_mega_evolve)
        self.assertEqual(fl_mg.base_species, "Floette-Eternal")
        self.assertEqual(fl_mg.max_hp, 181)
        self.assertEqual(fl_mg.level_50_stats["spe"], 113)
        self.assertEqual(fl_mg.mega_level_50_stats["spe"], 123)

        # Meowstic-F @ Meowsticite resolves cleanly to Meowstic-F-Mega
        self.assertTrue(mw_f.can_mega_evolve)
        self.assertEqual(mw_f.mega_target_species, "Meowstic-F-Mega")
        self.assertEqual(mw_f.ability, "Competitive")
        self.assertEqual(mw_f.mega_ability, "Trace")

    def test_pre_mega_paste_enters_turn0_as_base_form(self) -> None:
        """Garchomp-Mega-Z / Raichu-Mega-Y / Charizard-Mega-Y pastes enter Turn 0 in true Base forms."""
        paste = """
Garchomp-Mega-Z @ Garchompite Z
Ability: Rough Skin
Level: 50
EVs: 4 HP / 252 Atk / 252 Spe
Jolly Nature
- Earthquake
- Dragon Claw
- Swords Dance
- Protect

Raichu-Mega-Y @ Raichunite Y
Ability: Lightning Rod
Level: 50
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
- Fake Out
- Thunderbolt
- Volt Switch
- Protect

Charizard-Mega-Y @ Charizardite Y
Ability: Blaze
Level: 50
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
- Heat Wave
- Solar Beam
- Protect
- Air Slash

Pelipper @ Sitrus Berry
Ability: Drizzle
Level: 50
EVs: 252 HP / 4 Def / 252 SpA
Modest Nature
- Weather Ball
- Hurricane
- Tailwind
- Protect
"""
        pool = self.solver._precompile_team_pool(paste, trainer_id="trainer_1", require_explicit_spreads=True)
        # Garchomp-Mega-Z: Base Garchomp Spe=169 (102 base), Mega-Z Spe=223 (151 base)
        self.assertEqual(float(pool.roster_rows[0, MonIdx.IS_MEGA]), 0.0)
        self.assertEqual(float(pool.roster_rows[0, MonIdx.CAN_MEGA]), 1.0)
        self.assertEqual(float(pool.roster_rows[0, MonIdx.STAT_SPE]), 169.0)
        self.assertEqual(float(pool.roster_rows[0, MonIdx.MEGA_SPE]), 223.0)
        # Raichu-Mega-Y: Base Raichu Spe=178 (110 base), Mega-Y Spe=200 (130 base)
        self.assertEqual(float(pool.roster_rows[1, MonIdx.STAT_SPE]), 178.0)
        self.assertEqual(float(pool.roster_rows[1, MonIdx.MEGA_SPE]), 200.0)
        # Charizard-Mega-Y: Base Charizard SpA=161 (109 base), Mega-Y SpA=211 (159 base)
        self.assertEqual(float(pool.roster_rows[2, MonIdx.STAT_SPA]), 161.0)
        self.assertEqual(float(pool.roster_rows[2, MonIdx.MEGA_SPA]), 211.0)
        # All active leads have ACTIVE_TURNS == 0.0 for Turn-1 Fake Out legality
        for idx in range(4):
            self.assertEqual(float(pool.roster_rows[idx, MonIdx.ACTIVE_TURNS]), 0.0)

    def test_deduplicate_nicknamed_paste_and_strict_sp_validation(self) -> None:
        """Nicknamed char_y_v4.txt deduplicates to 6 unique Pokémon (90 modes); illegal SP & bare OTS rejected."""
        char_v4_path = REPO_ROOT / "data" / "teams" / "char_y_v4.txt"
        pool = self.solver._precompile_team_pool(
            char_v4_path.read_text(encoding="utf-8"),
            trainer_id="trainer_1",
            require_explicit_spreads=True,
        )
        self.assertEqual(len(pool.mons), 6)
        self.assertEqual(len(pool.leads), 15)
        self.assertEqual(len(pool.modes), 90)
        self.assertEqual(len(set(pool.display_species)), 6)

        # Bare EV-less OTS rejected when require_explicit_spreads=True
        evless = "\n".join(
            line for line in SAMPLE_4V4_T2.splitlines() if not line.strip().startswith("EVs:")
        )
        with self.assertRaises(ValueError):
            self.solver._precompile_team_pool(evless, trainer_id="trainer_2", require_explicit_spreads=True)

        # > 66 SP rejected
        over_budget = SAMPLE_4V4_T1.replace("EVs: 4 HP / 252 SpA / 252 Spe", "EVs: 252 HP / 252 SpA / 252 Spe")
        with self.assertRaises(ValueError):
            self.solver._precompile_team_pool(over_budget, trainer_id="trainer_1", require_explicit_spreads=True)

        # Tera Type line is silently ignored (zero Terastallization in Reg M-C)
        with_tera = SAMPLE_4V4_T1.replace("Timid Nature", "Tera Type: Fire\nTimid Nature", 1)
        pool_tera = self.solver._precompile_team_pool(
            with_tera, trainer_id="trainer_1", require_explicit_spreads=True
        )
        self.assertEqual(len(pool_tera.mons), 4)

    def test_turn0_lead_entry_single_fire_and_fake_out_psychic_terrain(self) -> None:
        """Turn-0 entry fires Intimidate->White Herb/Unburden & Psychic Surge, and Turn-1 Fake Out respects terrain."""
        pool_t1 = self.solver._precompile_team_pool(SAMPLE_4V4_T1, "trainer_1")
        pool_t2 = self.solver._precompile_team_pool(SAMPLE_4V4_T2, "trainer_2")

        # Lead Sneasler (White Herb + Unburden, idx=3) + Pelipper (Drizzle, idx=2) vs Incineroar (Intimidate, idx=0) + Indeedee-F (Psychic Surge, idx=1)
        f_clean = np.zeros((FIELD_DIM,), dtype=np.float32)
        f_clean[FieldIdx.WEATHER_START + WEATHER_TO_IDX["clear"]] = 1.0
        f_clean[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX["none"]] = 1.0
        p_init = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        p_init[SLOT_TRAINER_1_A] = pool_t1.roster_rows[3]  # Sneasler
        p_init[SLOT_TRAINER_1_B] = pool_t1.roster_rows[2]  # Pelipper
        p_init[SLOT_TRAINER_2_A] = pool_t2.roster_rows[0]  # Incineroar
        p_init[SLOT_TRAINER_2_B] = pool_t2.roster_rows[1]  # Indeedee-F

        f_t0, p_t0 = resolve_turn_zero_lead_entry(f_clean, p_init, tables=self.solver.sm.tables)
        # Drizzle Rain + Psychic Terrain set
        self.assertEqual(float(f_t0[FieldIdx.WEATHER_START + WEATHER_TO_IDX["rain"]]), 1.0)
        self.assertEqual(float(f_t0[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX["psychic"]]), 1.0)
        # Sneasler popped White Herb on Intimidate -> Atk restored to 0, Unburden active!
        self.assertEqual(float(p_t0[SLOT_TRAINER_1_A, MonIdx.BOOST_ATK]), 0.0)
        self.assertEqual(float(p_t0[SLOT_TRAINER_1_A, MonIdx.UNBURDEN_ACTIVE]), 1.0)
        # Pelipper dropped to -1 Atk
        self.assertEqual(float(p_t0[SLOT_TRAINER_1_B, MonIdx.BOOST_ATK]), -1.0)
        # Indeedee-F popped Psychic Seed -> +1 SpD
        self.assertEqual(float(p_t0[SLOT_TRAINER_2_B, MonIdx.BOOST_SPD]), 1.0)

        # Now check Fake Out legality:
        # 1) Under Turn-0 Psychic Terrain, Sneasler Fake Out (choice 0) into grounded Incineroar deals 0 damage!
        board_psy = self.solver._build_board_state(
            f_t0, p_t0, pool_t1, pool_t2, (3, 2), (0, 1), (0, 1), (2, 3)
        )
        step_psy = self.solver.sm.step(
            F=board_psy.field_tensor,
            P=board_psy.roster_tensor,
            M_moves=board_psy.moves_tensor,
            trainer_1_choices=np.array([[0, 3]], dtype=np.int64),  # Sneasler Fake Out -> Opp A, Pelipper Protect
            trainer_2_choices=np.array([[1, 1]], dtype=np.int64),  # Grounded Incineroar + Indeedee-F stay in
            num_mc_samples=4,
            resolve_lead_entry_abilities=False,
        )
        dmg_psy = np.asarray(step_psy.attack_cascade.mean_damage_dealt)
        self.assertEqual(float(dmg_psy[0, 0, 0]), 0.0)

        # 2) Without Psychic Terrain (ACTIVE_TURNS == 0.0), Turn-1 Fake Out is legal; at ACTIVE_TURNS == 1.0 it is pruned!
        f_no_psy = f_clean.copy()
        p_no_psy = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        p_no_psy[SLOT_TRAINER_1_A] = pool_t1.roster_rows[3]  # Sneasler
        p_no_psy[SLOT_TRAINER_1_B] = pool_t1.roster_rows[2]  # Pelipper
        p_no_psy[SLOT_TRAINER_2_A] = pool_t2.roster_rows[0]  # Incineroar
        p_no_psy[SLOT_TRAINER_2_B] = pool_t2.roster_rows[3]  # Garchomp
        f_t0_b, p_t0_b = resolve_turn_zero_lead_entry(f_no_psy, p_no_psy, tables=self.solver.sm.tables)
        board_open = self.solver._build_board_state(
            f_t0_b, p_t0_b, pool_t1, pool_t2, (3, 2), (0, 1), (0, 3), (1, 2)
        )
        mask_open = self.solver.sm.logic_engine.prune_side_26x26_tensor_actions(board_open, "trainer_1")
        coords_open = np.asarray(mask_open.pruned_choices)
        fake_out_choices_open = [int(r[0]) for r in coords_open if int(r[0]) in (0, 4)]
        self.assertGreater(len(fake_out_choices_open), 0)

        # Flip ACTIVE_TURNS to 1.0 (Turn 2) -> Fake Out MUST be hard-pruned!
        raw_r = board_open.roster_tensor
        p_t2_turn = (
            raw_r.detach().cpu().numpy().copy()
            if hasattr(raw_r, "detach")
            else np.asarray(raw_r).copy()
        )
        p_t2_turn[SLOT_TRAINER_1_A, MonIdx.ACTIVE_TURNS] = 1.0
        board_turn2 = self.solver._build_board_state(
            f_t0_b, p_t2_turn, pool_t1, pool_t2, (3, 2), (0, 1), (0, 3), (1, 2)
        )
        mask_t2 = self.solver.sm.logic_engine.prune_side_26x26_tensor_actions(board_turn2, "trainer_1")
        coords_t2 = np.asarray(mask_t2.pruned_choices)
        fake_out_choices_t2 = [int(r[0]) for r in coords_t2 if int(r[0]) in (0, 4)]
        self.assertEqual(len(fake_out_choices_t2), 0)

    def test_bench_residual_verified_moves_and_immunities(self) -> None:
        """Verify zero-hallucination move multiplier respects Levitate, Pixilate, Freeze-Dry, and Soundproof."""
        m_lev, _ = _effective_move_multiplier("Ground", "Earthquake", {}, "Rough Skin", ("Dragon",), "Levitate")
        self.assertEqual(m_lev, 0.0)

        m_fd, _ = _effective_move_multiplier("Ice", "Freeze-Dry", {}, "Snow Warning", ("Water", "Flying"), "Drizzle")
        self.assertEqual(m_fd, 4.0)

        m_pix, eff_t = _effective_move_multiplier("Normal", "Hyper Voice", {"sound": 1}, "Pixilate", ("Dragon",), "Rough Skin")
        self.assertEqual(eff_t, "Fairy")
        self.assertEqual(m_pix, 2.0)

        m_sp, _ = _effective_move_multiplier("Normal", "Hyper Voice", {"sound": 1}, "Pixilate", ("Dragon",), "Soundproof")
        self.assertEqual(m_sp, 0.0)

    def test_factored_4v4_solve_simplex_and_cancellation(self) -> None:
        """Factored solver produces valid 6×6 payoff matrix, Nash/QRE simplexes, and honours cancellation."""
        cfg = LeadMatchupConfig(
            preset="fast",
            num_rng_samples=4,
            cap_stay=6,
            cap_switch_per_mon=2,
            tile_size=12,
            device="cpu",
        )
        seen_cells: list[dict] = []
        res = self.solver.solve_90x90_matchup(
            SAMPLE_4V4_T1,
            SAMPLE_4V4_T2,
            config=cfg,
            progress_cb=lambda ev: seen_cells.append(ev),
        )
        self.assertEqual(res.payoff_matrix.shape, (6, 6))
        self.assertEqual(len(seen_cells), 36)
        self.assertAlmostEqual(float(np.sum(res.trainer_1_nash_weights)), 1.0, places=5)
        self.assertAlmostEqual(float(np.sum(res.trainer_2_nash_weights)), 1.0, places=5)
        self.assertAlmostEqual(float(np.sum(res.trainer_1_qre_weights)), 1.0, places=5)
        self.assertTrue(np.isfinite(res.global_game_value))
        self.assertGreater(len(res.trainer_1_top_brings), 0)
        self.assertGreater(len(res.trainer_2_top_brings), 0)
        # Drilldown cell schema intact
        c00 = res.heatmap_cells[0][0]
        self.assertIn("sub_matrix_6x6", c00)
        self.assertIn("turn0_events", c00)
        self.assertTrue(bool(c00["t1_opening"]))

        # Cancellation aborts cleanly
        cancel_ev = threading.Event()
        cancel_ev.set()
        with self.assertRaises(AnalysisCancelledError):
            self.solver.solve_90x90_matchup(
                SAMPLE_4V4_T1, SAMPLE_4V4_T2, config=cfg, cancel_event=cancel_ev
            )

    def test_studio_lead_lab_apis_rejection_inference_and_deep_turn1(self) -> None:
        """Studio Lead Lab APIs reject bare OTS, infer Bo3 clamped SP, and run Deep Turn-1 Audit."""
        tmp_db = Path(tempfile.mkdtemp()) / "lead_lab_test.duckdb"
        app_state = ReplayCoachAppState(preload_sample=False, db_path=tmp_db, device="cpu")

        # 1. Bare EV-less OTS with 0 scouting logs is strictly rejected
        evless = "\n".join(
            line for line in SAMPLE_4V4_T2.splitlines() if not line.strip().startswith("EVs:")
        )
        with self.assertRaises(ValueError):
            app_state.create_lead_lab_job(
                t1_paste_text=SAMPLE_4V4_T1,
                t2_paste_text=evless,
                preset="fast",
            )

        # 2. Infer opponent clamped 66-SP from Bo3 scouting log (matchagotme_g1.html)
        if SAMPLE_REPLAY_PATH.exists():
            inf = app_state.infer_lead_lab_opponent(
                replays=[
                    {
                        "filename": SAMPLE_REPLAY_PATH.name,
                        "raw_input": SAMPLE_REPLAY_PATH.read_text(encoding="utf-8"),
                    }
                ],
                t1_roster_id="treces_gc_char_y_v4",
            )
            self.assertTrue(inf["ok"])
            self.assertEqual(inf["games_pooled"], 1)
            self.assertGreaterEqual(len(inf["pokemon"]), 4)

        # 3. Create valid Lead Lab job & execute Deep Unpruned Turn-1 Audit
        job = app_state.create_lead_lab_job(
            t1_paste_text=SAMPLE_4V4_T1,
            t2_paste_text=SAMPLE_4V4_T2,
            preset="fast",
        )
        self.assertTrue(job["ok"])
        self.assertEqual(job["total_lead_pairs"], 36)

        audit = app_state.run_lead_lab_deep_turn1(
            job_id=job["job_id"],
            mode_1_idx=0,
            mode_2_idx=0,
            num_mc=32,
        )
        self.assertTrue(audit["ok"])
        self.assertGreater(len(audit["top_actions"]), 0)
        self.assertGreater(len(audit["opp_top_actions"]), 0)
        for profile in ("es_vgc", "en_vgc", "es_scientific", "en_scientific"):
            self.assertIn(profile, audit["commentary_variants"])

    def test_telemetry_create_team_folder_and_empty_summary(self) -> None:
        """Telemetry analytics creates local team folders cleanly and handles empty state."""
        import apps.replay_coach.server as srv_mod

        tmp_root = Path(tempfile.mkdtemp())
        tmp_db = tmp_root / "telemetry_test.duckdb"
        orig_root = srv_mod.TELEMETRY_ROOT
        try:
            srv_mod.TELEMETRY_ROOT = tmp_root / "telemetry"
            app_state = ReplayCoachAppState(preload_sample=False, db_path=tmp_db, device="cpu")
            # Zero folders on fresh install
            self.assertEqual(app_state.list_telemetry_teams(), [])
            empty_sum = app_state.get_telemetry_session_summary()
            self.assertTrue(empty_sum["ok"])
            self.assertEqual(empty_sum["total_matches"], 0)
            self.assertEqual(empty_sum["teams"], [])

            # Create a custom team folder cleanly
            created = app_state.create_telemetry_team("My Rain Squad!")
            self.assertTrue(created["ok"])
            self.assertEqual(created["team_folder"], "my_rain_squad")
            self.assertTrue(created["created"])
            self.assertIn("my_rain_squad", created["teams"])
            self.assertTrue((srv_mod.TELEMETRY_ROOT / "my_rain_squad" / "battles_telemetry.csv").exists())

            # Re-creating existing folder is non-destructive (created=False)
            again = app_state.create_telemetry_team("my_rain_squad")
            self.assertFalse(again["created"])
        finally:
            srv_mod.TELEMETRY_ROOT = orig_root

    def test_lead_lab_duckdb_vault_crud_search_and_deep_audit_cache(self) -> None:
        """DuckDB Lead Lab Vault persists sweeps, matches order-invariant hashes, searches, caches K=128 audits, and cascades deletes."""
        from apps.replay_coach.ots_db import compute_lead_lab_matchup_hash
        from engine.vgc_tensor_core.victory_equity import EQUITY_ENGINE_VERSION

        tmp_db = Path(tempfile.mkdtemp()) / "lead_vault_test.duckdb"
        app_state = ReplayCoachAppState(preload_sample=False, db_path=tmp_db, device="cpu")
        ots_db = app_state.ots_db

        # Order-invariant hashing: reordering mons in T1 paste yields the EXACT same matchup hash
        t1_blocks = [b.strip() for b in SAMPLE_4V4_T1.strip().split("\n\n") if b.strip()]
        t1_reordered = "\n\n".join(reversed(t1_blocks))
        h1 = compute_lead_lab_matchup_hash(SAMPLE_4V4_T1, SAMPLE_4V4_T2, "fast")
        h2 = compute_lead_lab_matchup_hash(t1_reordered, SAMPLE_4V4_T2, "fast")
        self.assertEqual(h1, h2)

        # Save a completed Lead Lab run into DuckDB Vault
        fake_payload = {
            "global_game_value": 0.245,
            "elapsed_s": 12.4,
            "num_t1_modes": 6,
            "num_t2_modes": 6,
            "total_modes_evaluated": 36,
            "t1_species": ["Charizard-Mega-Y", "Raichu", "Pelipper", "Sneasler"],
            "t2_species": ["Incineroar", "Indeedee-F", "Floette-Eternal", "Garchomp-Mega-Z"],
            "t1_leads": [["Charizard-Mega-Y", "Raichu"]],
            "t2_leads": [["Incineroar", "Indeedee-F"]],
            "trainer_1_top_brings": [
                {
                    "rank": 1,
                    "lead_idx": 0,
                    "bench_idx": 0,
                    "lead_species": ["Charizard-Mega-Y", "Raichu"],
                    "bench_species": ["Pelipper", "Sneasler"],
                    "nash_weight": 0.62,
                    "ev_vs_opp_nash": 0.245,
                    "worst_case_floor": 0.05,
                }
            ],
            "trainer_2_top_brings": [
                {
                    "rank": 1,
                    "lead_idx": 0,
                    "bench_idx": 0,
                    "lead_species": ["Incineroar", "Indeedee-F"],
                    "bench_species": ["Floette-Eternal", "Garchomp-Mega-Z"],
                    "opp_nash_weight": 0.55,
                    "best_counter_mode_idx": 0,
                    "best_counter_lead": ["Charizard-Mega-Y", "Raichu"],
                    "best_counter_bench": ["Pelipper", "Sneasler"],
                    "best_counter_score": 0.30,
                }
            ],
            "heatmap_cells": [],
        }
        saved = ots_db.save_lead_lab_run(
            t1_name="Charizard-Y Sun",
            t2_name="Indeedee TR",
            t1_paste=SAMPLE_4V4_T1,
            t2_paste=SAMPLE_4V4_T2,
            preset="fast",
            result_payload=fake_payload,
            tags="Regional TopCut",
        )
        self.assertEqual(saved["matchup_hash"], h1)

        # Lookup hits even with reordered paste!
        hit = ots_db.lookup_lead_lab_run(t1_reordered, SAMPLE_4V4_T2, "fast")
        self.assertIsNotNone(hit)
        self.assertTrue(hit["found"])
        self.assertFalse(hit["is_outdated"])
        self.assertAlmostEqual(hit["global_nash_value"], 0.245, places=3)

        # Outdated engine_version detection works cleanly
        ots_db.save_lead_lab_run(
            t1_name="Charizard-Y Sun",
            t2_name="Indeedee TR",
            t1_paste=SAMPLE_4V4_T1,
            t2_paste=SAMPLE_4V4_T2,
            preset="balanced",
            result_payload=fake_payload,
            engine_version="v1_legacy",
        )
        outdated_hit = ots_db.lookup_lead_lab_run(
            SAMPLE_4V4_T1, SAMPLE_4V4_T2, "balanced", engine_version=EQUITY_ENGINE_VERSION
        )
        self.assertIsNotNone(outdated_hit)
        self.assertTrue(outdated_hit["is_outdated"])

        # Multi-facet search: species, tag, advantage, team name
        res_sp = ots_db.search_lead_lab_runs(q="Floette Regional", advantage="win", t1_name="Charizard-Y Sun")
        self.assertEqual(res_sp["matched_count"], 1)
        self.assertEqual(res_sp["runs"][0]["run_id"], saved["run_id"])
        res_lose = ots_db.search_lead_lab_runs(advantage="lose")
        self.assertEqual(res_lose["matched_count"], 0)

        # Tag update
        self.assertTrue(ots_db.update_lead_lab_tags(saved["run_id"], "Finals G1"))
        loaded = app_state.load_lead_lab_vault_run(saved["run_id"])
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["tags"], "Finals G1")

        # Deep Turn-1 Audit runs once (cache miss), persists, and serves instantly on 2nd call (cache hit)
        a1 = app_state.run_lead_lab_deep_turn1(loaded["job_id"], mode_1_idx=0, mode_2_idx=0, num_mc=32)
        self.assertTrue(a1["ok"])
        self.assertFalse(a1["from_vault_cache"])
        self.assertIn("equity_breakdown", a1)
        self.assertIn("nash_pillars", a1["equity_breakdown"])
        a2 = app_state.run_lead_lab_deep_turn1(loaded["job_id"], mode_1_idx=0, mode_2_idx=0, num_mc=32)
        self.assertTrue(a2["ok"])
        self.assertTrue(a2["from_vault_cache"])
        self.assertIn("m0__m0", ots_db.list_cached_deep_audit_keys(saved["matchup_hash"]))

        # Cascade delete removes both run and cached deep audits
        self.assertTrue(ots_db.delete_lead_lab_run(saved["run_id"]))
        self.assertIsNone(ots_db.load_lead_lab_run(saved["run_id"]))
        self.assertEqual(ots_db.list_cached_deep_audit_keys(saved["matchup_hash"]), [])

    def test_texel_equity_weight_tuner_safety_bounds_and_anchor_lock(self) -> None:
        """Offline Texel/TD tuner locks material anchor (w_hp=1.00, w_alive=0.75) and enforces positive bounds."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "tune_equity_weights", REPO_ROOT / "scripts" / "tune_equity_weights.py"
        )
        assert spec is not None and spec.loader is not None
        tuner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tuner)

        rng = np.random.default_rng(2026)
        samples = []
        for idx in range(40):
            # Include both clean correlated samples and noisy adversarial flips
            win = 1.0 if idx % 2 == 0 else 0.0
            sign = 1.0 if win > 0.5 else -1.0
            samples.append(
                {
                    "match_id": f"m_{idx // 4}",
                    "turn": (idx % 4) + 1,
                    "winner": win,
                    "ply2_nash_value": float(sign * 0.9 + rng.normal(0.0, 0.2)),
                    "phi_raw": {
                        "hp": float(sign * 0.5 + rng.normal(0.0, 0.2)),
                        "alive": float(sign * 0.4),
                        "terminal": 0.0,
                        "threat": float(sign * 0.8 + rng.normal(0.0, 0.3)),
                        "malposition": float(-sign * 2.0),  # Adversarial sign flip to test lower bound!
                        "restriction": float(sign * 0.6),
                        "status": float(sign * 0.4),
                        "boost": float(sign * 0.3),
                        "two_turn_prime": float(sign * 0.5),
                        "resources": float(sign * 0.2),
                        "field_tempo": float(sign * 0.7),
                    },
                }
            )

        fitted, rep = tuner.fit_equity_weights_from_samples(samples, lambda_reg=0.08, eta_td=0.25, k_folds=4)
        self.assertEqual(fitted.w_hp, 1.00)
        self.assertEqual(fitted.w_alive, 0.75)
        self.assertEqual(fitted.w_terminal, 2.50)
        for wname, _fkey, lo, hi in tuner.TUNABLE_SPEC:
            val = float(getattr(fitted, wname))
            self.assertGreaterEqual(val, lo - 1e-6, f"{wname}={val} fell below safe bound {lo}")
            self.assertLessEqual(val, hi + 1e-6, f"{wname}={val} exceeded safe bound {hi}")
        self.assertGreater(rep["cv_tuned"]["log_loss"], 0.0)
        self.assertGreaterEqual(rep["cv_tuned"]["brier_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
