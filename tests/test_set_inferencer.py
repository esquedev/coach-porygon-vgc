# -*- coding: utf-8 -*-
"""Unit tests for the OTS-Enforced Zero-AI 66-SP Mathematical Constraint Solver (`engine.inference`)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.inference import (
    MissingOTSError,
    OpponentSetInferencer,
    SeriesSPInferenceReport,
    TournamentUsageRepository,
    compute_effective_speed,
    get_tournament_repository,
)
from engine.parser import parse_showdown_paste
from engine.parser.models import (
    DamageObservation,
    HpTickObservation,
    ParsedBattle,
    ParsedPokemon,
    ParsedTeam,
    SpeedObservation,
    StatSpread,
)
from engine.state.state_compiler import compute_level_50_stats_from_base
from apps.replay_coach.protocol_parser import parse_showdown_replay


T1_PASTE = """
Charizard @ Charizardite Y
Ability: Blaze
Level: 50
EVs: 2 HP / 12 Def / 28 SpA / 24 Spe
Timid Nature
- Heat Wave
- Scorching Sands
- Solar Beam
- Protect

Venusaur @ Focus Sash
Ability: Chlorophyll
Level: 50
EVs: 1 HP / 1 Def / 32 SpA / 32 Spe
Modest Nature
- Sludge Bomb
- Earth Power
- Sleep Powder
- Protect

Pelipper @ Damp Rock
Ability: Drizzle
Level: 50
EVs: 32 HP / 2 Def / 16 SpA / 16 SpD
Modest Nature
- Weather Ball
- Hurricane
- Wide Guard
- Tailwind
"""

T2_EVLESS_OTS = """
Incineroar @ White Herb
Ability: Intimidate
Level: 50
Adamant Nature
- Flare Blitz
- Darkest Lariat
- Fake Out
- Parting Shot

Primarina @ Leftovers
Ability: Liquid Voice
Level: 50
Modest Nature
- Hyper Voice
- Moonblast
- Perish Song
- Protect
"""


def _make_synthetic_battle(
    t1_sets: dict,
    t2_sets: dict,
    speed_obs=None,
    damage_obs=None,
    hp_tick_obs=None,
) -> ParsedBattle:
    """Construct a lightweight `ParsedBattle` container carrying empirical observations."""
    b = ParsedBattle(
        trainer_1=ParsedTeam(trainer_name="trainer_1", pokemon_sets=t1_sets),
        trainer_2=ParsedTeam(trainer_name="trainer_2", pokemon_sets=t2_sets),
        speed_observations=list(speed_obs or []),
        damage_observations=list(damage_obs or []),
        hp_tick_observations=list(hp_tick_obs or []),
    )
    return b


class TestOpponentSetInferencer(unittest.TestCase):
    """Verify OTS enforcement, exact Smogon-backed 66-SP DP bounds, Bo3 pooling, and blind holdout."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = get_tournament_repository()
        cls.inferencer = OpponentSetInferencer()
        cls.t1_sets = parse_showdown_paste(T1_PASTE)
        cls.t2_ots = parse_showdown_paste(T2_EVLESS_OTS)

    def test_tournament_archive_loaded(self) -> None:
        """Verify DuckDB regional tournament archive and mega species resolution remain intact."""
        self.assertGreaterEqual(self.repo.total_tournament_teams, 4965)
        self.assertIn("Charizard-Mega-Y", self.repo.pokedex)
        self.assertEqual(
            self.repo.resolve_species_name("Mega Charizard", item="Charizardite Y", is_mega=True),
            "Charizard-Mega-Y",
        )
        self.assertIn("Grassy Glide", self.repo.moves)

    def test_missing_ots_raises_error(self) -> None:
        """Verify solver strictly enforces OTS metadata (Nature, Ability, Moves) even in Bo1."""
        # Empty opponent OTS
        with self.assertRaises(MissingOTSError):
            self.inferencer.infer_series(self.t1_sets, {}, [])

        # Missing nature on opponent mon
        incomplete = {
            "Incineroar": ParsedPokemon(
                species="Incineroar",
                base_species="Incineroar",
                item="White Herb",
                ability="Intimidate",
                nature=None,
                moves=["Flare Blitz", "Fake Out", "Parting Shot", "Darkest Lariat"],
            )
        }
        with self.assertRaises(MissingOTSError):
            self.inferencer.infer_series(self.t1_sets, incomplete, [])

        # Missing moves
        no_moves = {
            "Incineroar": ParsedPokemon(
                species="Incineroar",
                base_species="Incineroar",
                item="White Herb",
                ability="Intimidate",
                nature="Adamant",
                moves=[],
            )
        }
        with self.assertRaises(MissingOTSError):
            self.inferencer.infer_series(self.t1_sets, no_moves, [])

    def test_speed_order_switch_in_and_trick_room(self) -> None:
        """Verify Turn-0 switch-in ability order and Trick Room speed inequalities clamp Spe SP."""
        # Pelipper (Base 65 Spe, 0 Spe SP, Modest) => L50 Spe = 65 + 0 + 20 = 85.
        # Incineroar (Base 60 Spe, Adamant): L50 Spe = 60 + sp + 20 = 80 + sp.
        # If Incineroar's Intimidate triggers BEFORE Pelipper's Drizzle on Turn 0:
        # Incineroar Spe >= 85 => 80 + sp >= 85 => sp >= 5!
        # And if under Trick Room Incineroar moves AFTER Pelipper (i.e. Incineroar is faster):
        # also confirms sp >= 5. Suppose instead Pelipper outspeeds Incineroar normally -> sp <= 5!
        obs_fast = SpeedObservation(
            turn=0,
            priority=0,
            faster_move="[Ability: Intimidate]",
            slower_move="[Ability: Drizzle]",
            faster_trainer="trainer_2",
            faster_mon="Incineroar",
            slower_trainer="trainer_1",
            slower_mon="Pelipper",
            trick_room_active=False,
            source="switch_in_ability",
            game_index=1,
        )
        obs_slow_vs_venu = SpeedObservation(
            turn=1,
            priority=0,
            faster_move="Weather Ball",
            slower_move="Flare Blitz",
            faster_trainer="trainer_1",
            faster_mon="Pelipper",
            slower_trainer="trainer_2",
            slower_mon="Incineroar",
            trick_room_active=False,
            source="turn_order",
            game_index=1,
        )
        # Together: Incineroar Spe >= 85 AND Incineroar Spe <= 85 => Exact Pin at 5 SP (Speed tie = 85)!
        b = _make_synthetic_battle(
            self.t1_sets,
            {"Incineroar": self.t2_ots["Incineroar"]},
            speed_obs=[obs_fast, obs_slow_vs_venu],
        )
        report = self.inferencer.infer_series(
            self.t1_sets,
            {"Incineroar": self.t2_ots["Incineroar"]},
            [b],
        )
        inc_spe = report.pokemon_inferences["Incineroar"].bounds["spe"]
        self.assertEqual(inc_spe.min_sp, 5)
        self.assertEqual(inc_spe.max_sp, 5)
        self.assertTrue(inc_spe.locked)
        self.assertEqual(inc_spe.status, "pinned")

        # Verify Unburden / Tailwind helper
        eff_unb = compute_effective_speed(100, ability="Unburden", unburden_active=True, tailwind_active=True)
        self.assertEqual(eff_unb, 400)

    def test_exact_hp_offensive_inversion_and_recoil_hp_isolation(self) -> None:
        """Verify exact integer HP damage on `trainer_1` narrows Atk SP and recoil narrows HP SP."""
        # Incineroar (Adamant, 28 Atk SP) Fake Out into Venusaur (1 HP / 1 Def SP, Max HP 156):
        # Also Flare Blitz dealing 98 exact HP to trainer_1 with Incineroar dropping 100% -> 84% recoil:
        # 1/3 of 98 = 33 HP recoil. 84% of MaxHP implies MaxHP around 195-202 (HP SP >= 13).
        obs_fake_out = DamageObservation(
            turn=1,
            attacker_trainer="trainer_2",
            attacker="Incineroar",
            defender_trainer="trainer_1",
            defender="Venusaur",
            move="Fake Out",
            damage_pct=20.5,
            hp_pct_before=100.0,
            hp_pct_after=79.5,
            damage_hp_exact=32,
            defender_max_hp_exact=156,
            is_spread_multi_target=False,
            game_index=1,
        )
        tick_recoil = HpTickObservation(
            turn=2,
            trainer="trainer_2",
            species="Incineroar",
            kind="recoil",
            hp_pct_before=100.0,
            hp_pct_after=84.0,
            source_damage_hp_exact=98,
            recoil_fraction=1.0 / 3.0,
            game_index=1,
        )
        b = _make_synthetic_battle(
            self.t1_sets,
            {"Incineroar": self.t2_ots["Incineroar"]},
            damage_obs=[obs_fake_out],
            hp_tick_obs=[tick_recoil],
        )
        report = self.inferencer.infer_series(
            self.t1_sets,
            {"Incineroar": self.t2_ots["Incineroar"]},
            [b],
        )
        inc = report.pokemon_inferences["Incineroar"]
        self.assertFalse(inc.soft_fallback_used)
        self.assertGreaterEqual(inc.bounds["hp"].min_sp, 10)
        self.assertGreaterEqual(inc.bounds["atk"].min_sp, 20)
        self.assertEqual(inc.default_spread.total_sp, 66)

    def test_bo3_multi_game_pooling_tightens_bounds(self) -> None:
        """Verify pooling Game 1 + Game 2 produces strictly tighter bounds than Game 1 alone."""
        # Game 1: Primarina Hyper Voice (spread 2 foes) deals 27/156 exact HP to Venusaur (1 HP/0 SpD)
        # Game 2: Primarina moves faster than Pelipper (85 Spe) -> Spe SP >= 5
        g1 = _make_synthetic_battle(
            self.t1_sets,
            {"Primarina": self.t2_ots["Primarina"]},
            damage_obs=[
                DamageObservation(
                    turn=1,
                    attacker_trainer="trainer_2",
                    attacker="Primarina",
                    defender_trainer="trainer_1",
                    defender="Venusaur",
                    move="Hyper Voice",
                    damage_pct=17.3,
                    hp_pct_before=100.0,
                    hp_pct_after=82.7,
                    damage_hp_exact=27,
                    defender_max_hp_exact=156,
                    is_spread_multi_target=True,
                    game_index=1,
                )
            ],
        )
        g2 = _make_synthetic_battle(
            self.t1_sets,
            {"Primarina": self.t2_ots["Primarina"]},
            speed_obs=[
                SpeedObservation(
                    turn=2,
                    priority=0,
                    faster_move="Hyper Voice",
                    slower_move="Weather Ball",
                    faster_trainer="trainer_2",
                    faster_mon="Primarina",
                    slower_trainer="trainer_1",
                    slower_mon="Pelipper",
                    trick_room_active=False,
                    source="turn_order",
                    game_index=2,
                )
            ],
        )
        rep_g1 = self.inferencer.infer_series(self.t1_sets, {"Primarina": self.t2_ots["Primarina"]}, [g1])
        rep_bo3 = self.inferencer.infer_series(self.t1_sets, {"Primarina": self.t2_ots["Primarina"]}, [g1, g2])

        self.assertEqual(rep_bo3.games_pooled, 2)
        p_g1 = rep_g1.pokemon_inferences["Primarina"]
        p_bo3 = rep_bo3.pokemon_inferences["Primarina"]
        # G1 alone does not know Primarina's Spe min; G1+G2 pins Spe >= 5
        self.assertEqual(p_g1.bounds["spe"].min_sp, 0)
        self.assertGreaterEqual(p_bo3.bounds["spe"].min_sp, 5)
        # Both clamp SpA tightly from G1's 27 HP Hyper Voice hit (well below 32 SP cap)
        self.assertLessEqual(p_bo3.bounds["spa"].max_sp, 15)
        # Pure special attacker Primarina must allocate 0 SP to unused Atk!
        self.assertEqual(p_bo3.default_spread.atk, 0)

    def test_validate_user_spreads_enforces_clamps_and_budget(self) -> None:
        """Verify `validate_user_spreads` strictly rejects violations of `[min_sp, max_sp]` or 66-SP budget."""
        obs_fast = SpeedObservation(
            turn=0,
            priority=0,
            faster_move="[Ability: Intimidate]",
            slower_move="[Ability: Drizzle]",
            faster_trainer="trainer_2",
            faster_mon="Incineroar",
            slower_trainer="trainer_1",
            slower_mon="Pelipper",
            source="switch_in_ability",
            game_index=1,
        )
        b = _make_synthetic_battle(
            self.t1_sets,
            {"Incineroar": self.t2_ots["Incineroar"]},
            speed_obs=[obs_fast],
        )
        report = self.inferencer.infer_series(self.t1_sets, {"Incineroar": self.t2_ots["Incineroar"]}, [b])
        inc = report.pokemon_inferences["Incineroar"]
        self.assertGreaterEqual(inc.bounds["spe"].min_sp, 5)

        # Valid default spread passes
        ok_def, errs_def = report.validate_user_spreads({"Incineroar": inc.default_spread.to_dict()})
        self.assertTrue(ok_def, f"Unexpected errors: {errs_def}")

        # Violating deterministic Spe clamp (setting spe=0 when min_sp >= 5) MUST fail!
        bad_clamp = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}
        ok_clamp, errs_clamp = report.validate_user_spreads({"Incineroar": bad_clamp})
        self.assertFalse(ok_clamp)
        self.assertTrue(any("violates inferred deterministic bounds" in e for e in errs_clamp))

        # Violating 66-SP total budget MUST fail!
        bad_sum = {"hp": 30, "atk": 20, "def": 0, "spa": 0, "spd": 0, "spe": 10}
        ok_sum, errs_sum = report.validate_user_spreads({"Incineroar": bad_sum})
        self.assertFalse(ok_sum)
        self.assertTrue(any("total SP must equal 66" in e for e in errs_sum))

        # Violating single-stat max (33 > 32) MUST fail!
        bad_max = {"hp": 33, "atk": 28, "def": 0, "spa": 0, "spd": 0, "spe": 5}
        ok_max, errs_max = report.validate_user_spreads({"Incineroar": bad_max})
        self.assertFalse(ok_max)
        self.assertTrue(any("out of [0, 32]" in e for e in errs_max))

    def test_blind_holdout_matchagotme_g1_replay(self) -> None:
        """End-to-end blind holdout against real Showdown replay `matchagotme_g1.html` + `char_y_v4.txt`."""
        replay_path = REPO_ROOT / "apps" / "replay_coach" / "sample_data" / "matchagotme_g1.html"
        team_path = REPO_ROOT / "data" / "teams" / "char_y_v4.txt"
        self.assertTrue(replay_path.exists())
        self.assertTrue(team_path.exists())

        t1_sets = parse_showdown_paste(team_path.read_text(encoding="utf-8"))
        parsed = parse_showdown_replay(
            replay_path.read_text(encoding="utf-8"),
            pov_trainer="treces_gc",
            trainer_1_ots_sets=t1_sets,
            game_index=1,
        )
        # Opponent OTS is extracted directly from |showteam| with zero EVs/SPs!
        self.assertEqual(len(parsed.trainer_2_showteam_ots), 6)

        report: SeriesSPInferenceReport = self.inferencer.infer_series(
            trainer_1_sets=t1_sets,
            trainer_2_ots_sets=parsed.trainer_2_showteam_ots,
            replays=[parsed],
            trainer_1_name=parsed.trainer_1_name,
            trainer_2_name=parsed.trainer_2_name,
        )
        self.assertEqual(len(report.pokemon_inferences), 6)
        self.assertGreater(report.total_smogon_calcs, 200)

        for sp, inf in report.pokemon_inferences.items():
            self.assertFalse(inf.soft_fallback_used, f"{sp} unexpectedly triggered soft fallback: {inf.notes}")
            self.assertEqual(inf.default_spread.total_sp, 66, f"{sp} spread != 66")
            for sk, b in inf.bounds.items():
                val = getattr(inf.default_spread, "def_" if sk == "def" else sk)
                self.assertGreaterEqual(val, b.min_sp)
                self.assertLessEqual(val, b.max_sp)

        # Empirical invariants verified from matchagotme_g1.html:
        inc = report.pokemon_inferences["Incineroar"]
        self.assertGreaterEqual(inc.bounds["hp"].min_sp, 10)  # Flare Blitz 98 HP recoil (100%->84%)
        self.assertGreaterEqual(inc.bounds["atk"].min_sp, 24)  # Fake Out 32/157 + Darkest Lariat 75/175
        self.assertLessEqual(inc.bounds["atk"].max_sp, 31)

        prim = report.pokemon_inferences["Primarina"]
        self.assertLessEqual(prim.bounds["spa"].max_sp, 9)  # Hyper Voice 27/157 & 92/175
        self.assertEqual(prim.default_spread.atk, 0)  # Unused physical offense stays 0 SP!

        fari = report.pokemon_inferences["Farigiraf"]
        self.assertLessEqual(fari.bounds["spe"].max_sp, 6)  # Outsped Pelipper (85 Spe) under Trick Room
        self.assertEqual(fari.default_spread.atk, 0)

        # Verify generated 66-SP Showdown paste round-trips cleanly
        paste_out = report.build_paste()
        reparsed = parse_showdown_paste(paste_out)
        self.assertEqual(len(reparsed), 6)
        for sp, mon in reparsed.items():
            self.assertEqual(mon.spread.total_sp, 66)
            self.assertIsNotNone(mon.nature)
            self.assertEqual(len(mon.moves), 4)


if __name__ == "__main__":
    unittest.main()
