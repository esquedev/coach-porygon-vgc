# -*- coding: utf-8 -*-
"""
Unit tests for ShowdownParser (engine/tactics/showdown_parser.py).
Verifies deterministic board state reconstruction across human-readable and
pipe-delimited Showdown Regulation M-C logs.
"""

from pathlib import Path
import unittest

from engine.tactics.showdown_parser import ShowdownParser


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"
BO3_SAMPLE_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_bo3_ots_log.txt"


class TestShowdownParser(unittest.TestCase):
    """Unit test suite for ShowdownParser."""

    def setUp(self) -> None:
        """Initialize parser and load sample battle log fixture."""
        self.parser = ShowdownParser()
        self.raw_log = SAMPLE_LOG_PATH.read_text(encoding="utf-8")

    def test_parse_real_regulation_mc_fixture_metadata(self) -> None:
        """Verify trainer names, teams, winner, and turn count from real fixture."""
        history = self.parser.parse(self.raw_log)
        self.assertEqual(history.p1_name, "aws_secret")
        self.assertEqual(history.p2_name, "DarKgoD16")
        self.assertEqual(history.winner, "aws_secret")
        self.assertEqual(len(history.p1_team), 6)
        self.assertEqual(len(history.p2_team), 6)
        self.assertGreaterEqual(len(history.turns), 5)

    def test_turn_1_mega_evolution_and_focus_sash_hp(self) -> None:
        """Verify Turn 1 Mega Floette activation, instantaneous speed scaling, and HP deltas."""
        history = self.parser.parse(self.raw_log)
        t1 = history.turns[0]
        self.assertEqual(t1.turn_number, 1)
        self.assertTrue(t1.p2_mega_used)
        self.assertIn("p2:Floette-Eternal", t1.mega_evolutions)
        self.assertAlmostEqual(t1.hp_deltas.get("p2:Sneasler", 0.0), 0.99, places=2)
        self.assertAlmostEqual(t1.hp_deltas.get("p1:Grimmsnarl", 0.0), 0.495, places=3)

        floette_slot = next(
            (s for s in t1.p2_slots if "Floette" in s.species), None
        )
        self.assertIsNotNone(floette_slot)
        self.assertTrue(floette_slot.is_mega)
        self.assertEqual(floette_slot.speed_tier, 102.0)

    def test_turn_3_drought_redirection_and_ko(self) -> None:
        """Verify Turn 3 Mega Charizard Y Drought, Rage Powder redirection, and Sinistcha KO."""
        history = self.parser.parse(self.raw_log)
        t3 = history.turns[2]
        self.assertEqual(t3.turn_number, 3)
        self.assertTrue(t3.p1_mega_used)
        self.assertEqual(t3.weather, "Sun")
        self.assertTrue(t3.weather_changed)
        self.assertTrue(t3.redirection_active)
        self.assertIn("p2:Sinistcha", t3.kos)

    def test_turn_4_protect_absorption_tracking(self) -> None:
        """Verify Turn 4 Protect absorption when Draining Kiss targets protected Charizard."""
        history = self.parser.parse(self.raw_log)
        t4 = history.turns[3]
        self.assertEqual(t4.turn_number, 4)
        self.assertGreaterEqual(t4.protect_absorptions, 1)
        self.assertIn("p2:Floette-Eternal", t4.kos)

    def test_pipe_protocol_stream_parsing_and_empty_error(self) -> None:
        """Verify pipe-delimited protocol stream parsing and error on empty log."""
        pipe_log = (
            "|player|p1|aws_secret|1\n"
            "|player|p2|DarKgoD16|2\n"
            "|switch|p1a: Charizard|Charizard, L50|100/100\n"
            "|switch|p1b: Kingambit|Kingambit, L50|100/100\n"
            "|switch|p2a: Sinistcha|Sinistcha, L50|100/100\n"
            "|switch|p2b: Floette-Eternal|Floette-Eternal, L50|100/100\n"
            "|turn|1\n"
            "|-mega|p1a: Charizard|Charizard|Charizardite Y\n"
            "|-weather|SunnyDay|[from] ability: Drought|[of] p1a: Charizard\n"
            "|move|p2a: Sinistcha|Protect|p2a: Sinistcha\n"
            "|move|p1a: Charizard|Heat Wave|p2b: Floette-Eternal\n"
            "|-activate|p2a: Sinistcha|move: Protect\n"
            "|-damage|p2b: Floette-Eternal|40/100\n"
            "|faint|p2b: Floette-Eternal\n"
            "|win|aws_secret\n"
        )
        history = self.parser.parse(pipe_log)
        self.assertEqual(history.p1_name, "aws_secret")
        self.assertEqual(len(history.turns), 1)
        self.assertTrue(history.turns[0].p1_mega_used)
        self.assertEqual(history.turns[0].protect_absorptions, 1)
        self.assertIn("p2:Floette-Eternal", history.turns[0].kos)

        with self.assertRaises(ValueError):
            self.parser.parse("   ")

    def test_parse_bo3_ots_log_metadata_and_sheets(self) -> None:
        """Verify Best-of-3 metadata, URL, and full 6-mon Open Team Sheets extraction."""
        if not BO3_SAMPLE_PATH.exists():
            self.skipTest("Sample Bo3 OTS log fixture not found.")
        bo3_log = BO3_SAMPLE_PATH.read_text(encoding="utf-8")
        history = self.parser.parse(bo3_log)

        self.assertTrue(history.is_bo3)
        self.assertEqual(history.bo3_game_number, 1)
        self.assertIn("game-bestof3-gen9championsvgc2026regmcbo3-2707626996", history.bo3_url)
        self.assertTrue(history.is_ots)
        self.assertEqual(history.p1_name, "aws_secret")
        self.assertEqual(history.p2_name, "Franconcino")
        self.assertEqual(history.winner, "Franconcino")

        # Open Team Sheets verification
        self.assertIsNotNone(history.p1_ots)
        self.assertIsNotNone(history.p2_ots)
        self.assertEqual(len(history.p1_ots.pokemon), 6)
        self.assertEqual(len(history.p2_ots.pokemon), 6)

        # Check aws_secret team members
        zard = history.p1_ots.get_member("Charizard")
        self.assertIsNotNone(zard)
        self.assertEqual(zard.item, "Charizardite Y")
        self.assertEqual(zard.ability, "Blaze")
        self.assertEqual(zard.nature, "Timid")
        self.assertEqual(zard.moves, ["Heat Wave", "Scorching Sands", "Solar Beam", "Protect"])

        # Check Franconcino team members
        glalie = history.p2_ots.get_member("Glalie")
        self.assertIsNotNone(glalie)
        self.assertEqual(glalie.item, "Glalitite")
        self.assertEqual(glalie.ability, "Inner Focus")
        self.assertEqual(glalie.nature, "Jolly")
        self.assertEqual(glalie.moves, ["Body Slam", "Explosion", "Earthquake", "Protect"])

        gardevoir = history.p2_ots.get_member("Gardevoir")
        self.assertIsNotNone(gardevoir)
        self.assertEqual(gardevoir.item, "Gardevoirite")
        self.assertEqual(gardevoir.ability, "Telepathy")
        self.assertEqual(gardevoir.nature, "Timid")

    def test_bo3_turn_snapshots_and_bench_tracking(self) -> None:
        """Verify dynamic living bench species tracking and slot state propagation across turns."""
        if not BO3_SAMPLE_PATH.exists():
            self.skipTest("Sample Bo3 OTS log fixture not found.")
        bo3_log = BO3_SAMPLE_PATH.read_text(encoding="utf-8")
        history = self.parser.parse(bo3_log)

        # Turn 1
        t1 = history.turns[0]
        self.assertEqual(t1.turn_number, 1)
        self.assertTrue(t1.is_ots)
        self.assertEqual(t1.p1_bench_alive, 2)
        self.assertEqual(t1.p1_bench_species, ["Garchomp", "Kingambit"])
        self.assertEqual(t1.p2_bench_alive, 2)
        self.assertEqual(t1.p2_bench_species, ["Rillaboom", "Espathra"])

        # Turn 1 Slot States: check items and abilities pre-populated
        grim = next((s for s in t1.p1_slots if s.species == "Grimmsnarl"), None)
        self.assertIsNotNone(grim)
        self.assertEqual(grim.item, "Light Clay")
        self.assertEqual(grim.ability, "Prankster")

        # Turn 2: after Turn 1 Explosion double KO, P1 brings in both bench Pokemon
        t2 = history.turns[1]
        self.assertEqual(t2.turn_number, 2)
        self.assertEqual(t2.p1_bench_species, [])
        self.assertEqual(t2.p1_bench_alive, 0)
        self.assertEqual(t2.p2_bench_species, ["Espathra"])
        self.assertEqual(t2.p2_bench_alive, 1)

    def test_ots_simulator_state_and_action_pruning(self) -> None:
        """Verify simulator state export and ActionPruner line generation with real OTS moves."""
        if not BO3_SAMPLE_PATH.exists():
            self.skipTest("Sample Bo3 OTS log fixture not found.")
        from engine.gpu.tensor_encoder import TensorEncoder
        from engine.tactics.action_pruner import ActionPruner

        bo3_log = BO3_SAMPLE_PATH.read_text(encoding="utf-8")
        history = self.parser.parse(bo3_log)
        t1 = history.turns[0]

        # Simulator state conversion
        sim_state = self.parser.to_simulator_state(t1)
        self.assertIn("p1a", sim_state["slots"])
        p1a = sim_state["slots"]["p1a"]
        self.assertIn("moves", p1a)
        self.assertGreater(len(p1a["moves"]), 0)
        self.assertNotEqual(p1a["item"], "")

        # ActionPruner with OTS
        pruner = ActionPruner()
        p2_lines = pruner.prune_side_actions(t1, side="p2")
        self.assertEqual(len(p2_lines), 5)
        # Glalie spread move should be Explosion from OTS!
        line_2 = p2_lines[2]
        self.assertEqual(line_2.category, "Spread / Area Move")
        self.assertEqual(line_2.slot_b_move, "Explosion")

        # Strategic pivot line for P1 should switch to actual bench Pokemon Garchomp!
        p1_lines = pruner.prune_side_actions(t1, side="p1")
        line_4 = p1_lines[4]
        self.assertEqual(line_4.category, "Strategic Pivot / Switch")
        self.assertEqual(line_4.simulator_choices["p1a"]["switch_to"], "Garchomp")

        # TensorEncoder with OTS: features 59 and 60 should be populated (> 0.0) from Turn 1
        encoder = TensorEncoder()
        t_tensor = encoder.encode(t1)
        # Check active slot 0 item/ability features
        self.assertGreater(float(t_tensor.s_mons[0, 0, 59]), 0.0)
        self.assertGreater(float(t_tensor.s_mons[0, 0, 60]), 0.0)


if __name__ == "__main__":
    unittest.main()
