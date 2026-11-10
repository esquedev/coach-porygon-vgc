# -*- coding: utf-8 -*-
"""Comprehensive tests for Esports Battle Telemetry & CSV Logger."""

from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.telemetry import (
    TurnTelemetryRecord,
    batch_update_comments,
    extract_turn_telemetry,
    save_telemetry_to_csv,
    update_telemetry_comment,
)

SAMPLE_CHAT_LOG = """
☆trainer_1 and ☆trainer_2 joined
Format:
[Gen 9 Champions] VGC 2026 Reg M-C
Rated battle
Species Clause: Limit one of each Pokemon
Item Clause: Limit 1 of each item
trainer_1's team:
Charizard / Raichu / Milotic / Garchomp / Grimmsnarl / Kingambit
trainer_2's team:
Whimsicott / Glimmora / Charizard / Rillaboom / Incineroar / Urshifu

Battle started between trainer_1 and trainer_2!

Go! Charizard!
Go! Raichu!
trainer_2 sent out Whimsicott!
trainer_2 sent out Glimmora!

Turn 1

Raichu used Fake Out!
trainer_2's Whimsicott flinched and couldn't move!

trainer_1's Charizard used Heat Wave!
(The opposing Whimsicott lost 85% of its health!)
(The opposing Glimmora lost 25% of its health!)

The opposing Glimmora used Power Gem!
(Charizard lost 60% of its health!)

Turn 2

trainer_1's Charizard used Weather Ball!
It's super effective!
(The opposing Whimsicott lost 15% of its health!)
The opposing Whimsicott fainted!

The opposing Glimmora used Sludge Bomb!
A critical hit!
(Raichu lost 90% of its health!)

Turn 3

Raichu used Volt Tackle!
(The opposing Glimmora lost 50% of its health!)

trainer_2 sent out Charizard!
trainer_2 forfeited.

trainer_1 won the battle!
"""


class TestBattleTelemetry(unittest.TestCase):
    """Test suite validating turn-by-turn telemetry extraction and CSV operations."""

    def test_extract_turn_telemetry(self) -> None:
        """Verify turn-by-turn telemetry extraction from raw Showdown log."""
        records = extract_turn_telemetry(
            raw_log=SAMPLE_CHAT_LOG,
            pov_trainer="trainer_1",
        )
        self.assertEqual(len(records), 3, "Expected exactly 3 turns extracted.")

        # Turn 1
        t1 = records[0]
        self.assertEqual(t1.turn, 1)
        self.assertEqual(t1.trainer_1, "trainer_1")
        self.assertEqual(t1.trainer_2, "trainer_2")
        self.assertIn("Charizard", [t1.trainer_1_active_1, t1.trainer_1_active_2])
        self.assertIn("Raichu", [t1.trainer_1_active_1, t1.trainer_1_active_2])
        self.assertIn("Whimsicott", [t1.trainer_2_active_1, t1.trainer_2_active_2])
        self.assertIn("Glimmora", [t1.trainer_2_active_1, t1.trainer_2_active_2])
        self.assertGreater(t1.damage_dealt_to_trainer_2, 100.0)
        self.assertEqual(t1.damage_dealt_to_trainer_1, 60.0)
        self.assertIn("Flinch", t1.variance_events)
        self.assertEqual(t1.comment, "")

        # Turn 2
        t2 = records[1]
        self.assertEqual(t2.turn, 2)
        self.assertIn("Critical Hit", t2.variance_events)
        self.assertIn("Whimsicott", t2.faints_this_turn)

        # Turn 3
        t3 = records[2]
        self.assertEqual(t3.turn, 3)
        self.assertEqual(t3.winner, "trainer_1")

    def test_csv_save_and_comment_injection(self) -> None:
        """Verify saving to CSV, appending records, and updating the comment column."""
        records = extract_turn_telemetry(SAMPLE_CHAT_LOG, pov_trainer="trainer_1")
        match_id = records[0].match_id

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_telemetry.csv"

            # 1. Save records
            saved_path = save_telemetry_to_csv(records, csv_path=csv_file, append=False)
            self.assertTrue(saved_path.is_file())

            # 2. Update comment on Turn 1
            updated = update_telemetry_comment(
                csv_path=csv_file,
                match_id=match_id,
                turn=1,
                comment="Great Fake Out read into Whimsicott to deny Tailwind.",
            )
            self.assertTrue(updated)

            # 3. Batch update comments on Turns 2 and 3
            batch_count = batch_update_comments(
                csv_path=csv_file,
                match_id=match_id,
                comments_by_turn={
                    2: "Critical hit on Raichu from Glimmora Sludge Bomb (cartridge variance).",
                    3: "Opponent forfeited after losing primary speed control.",
                },
            )
            self.assertEqual(batch_count, 2)

            # 4. Verify CSV contents
            import csv
            with open(csv_file, mode="r", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
                self.assertEqual(len(reader), 3)
                self.assertEqual(reader[0]["comment"], "Great Fake Out read into Whimsicott to deny Tailwind.")
                self.assertIn("Critical hit on Raichu", reader[1]["comment"])
                self.assertIn("Opponent forfeited", reader[2]["comment"])


if __name__ == "__main__":
    unittest.main()
