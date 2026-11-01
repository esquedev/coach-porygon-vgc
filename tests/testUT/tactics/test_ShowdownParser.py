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


if __name__ == "__main__":
    unittest.main()
