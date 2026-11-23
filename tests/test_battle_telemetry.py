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
Whimsicott / Glimmora / Charizard / Rillaboom / Incineroar / Archaludon

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

    def test_tactical_triggers_extraction(self) -> None:
        """Verify extraction of Mega Evolution, White Herb, Intimidate, and Defiant triggers."""
        log = """
☆trainer_1 and ☆trainer_2 joined
Format: [Gen 9 Champions] VGC 2026 Reg M-C
Battle started between trainer_1 and trainer_2!
Go! Charizard!
Go! Sneasler!
trainer_2 sent out Incineroar!
trainer_2 sent out Venusaur!
The opposing Incineroar's Intimidate cuts Sneasler's Attack!
Sneasler's White Herb restored its status!
Turn 1
Charizard Mega Evolved into Mega Charizard Y!
Charizard used Heat Wave!
(The opposing Incineroar lost 30% of its health!)
(The opposing Venusaur lost 80% of its health!)
The opposing Incineroar used Knock Off!
(Charizard lost 40% of its health!)
trainer_2 forfeited.
trainer_1 won the battle!
"""
        records = extract_turn_telemetry(log, pov_trainer="trainer_1")
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertIn("White Herb on Sneasler", r.variance_events)
        self.assertIn("Intimidate by Incineroar", r.variance_events)
        self.assertIn("Mega Evolution (Charizard Y)", r.variance_events)

    def test_auto_pov_inference_and_nicknames_and_pivots_and_faints(self) -> None:
        """Verify TEL-01, TEL-02, TEL-03: auto-POV when listed 2nd, nicknames, Mega aliases, pivots, double faints."""
        log = """
☆trainer_2 and ☆trainer_1 joined
Format: [Gen 9 Champions] VGC 2026 Reg M-C (Bo3)
trainer_2's team:Incineroar / Sneasler / Dragonite / Rillaboom / Milotic / Indeedee
trainer_1's team:Charizard / Raichu / Garchomp / Archaludon / Pelipper / Venusaur
Battle started between trainer_2 and trainer_1!
trainer_2 sent out Incineroar!
trainer_2 sent out Sneasler!
Go! Hazard (Charizard)!
Go! Raichu!
Turn 1
Raichu's Raichunite X is reacting to the Key Stone!
Raichu has Mega Evolved into Mega Raichu!
[Raichu's Electric Surge]
An electric current ran across the battlefield!
Hazard's Charizardite Y is reacting to the Key Stone!
Hazard has Mega Evolved into Mega Charizard!
[Hazard's Drought]
The sunlight turned harsh!
Raichu used Volt Switch!
(The opposing Incineroar lost 18% of its health!)
Raichu went back to trainer_1!
Go! Garchomp!
Hazard, come back!
Go! Venusaur!
The opposing Incineroar used Parting Shot!
Garchomp's Attack fell!
The opposing Incineroar went back to trainer_2!
trainer_2 sent out Dragonite!
Turn 2
The opposing Dragonite's Dragoninite is reacting to the Key Stone!
The opposing Dragonite has Mega Evolved into Mega Dragonite!
The opposing Sneasler used Dire Claw!
(Venusaur lost 100% of its health!)
Venusaur fainted!
The opposing Dragonite used Heat Wave!
(Garchomp lost 100% of its health!)
Garchomp fainted!
Go! Raichu (Raichu-Mega-X)!
Go! Hazard (Charizard-Mega-Y)!
Turn 3
Raichu used Volt Tackle!
(The opposing Sneasler lost 100% of its health!)
The opposing Sneasler fainted!
Hazard used Heat Wave!
(The opposing Dragonite lost 100% of its health!)
The opposing Dragonite fainted!
trainer_2 sent out Incineroar!
Turn 4
The opposing Incineroar used Flare Blitz!
(Raichu lost 100% of its health!)
Raichu fainted!
Hazard used Weather Ball!
(The opposing Incineroar lost 100% of its health!)
The opposing Incineroar fainted!
trainer_1 won the battle!
"""
        # Omit pov_trainer to test TEL-01 auto-inference when trainer_1 is listed 2nd
        records = extract_turn_telemetry(log)
        self.assertEqual(len(records), 4)
        self.assertEqual(records[0].trainer_1, "trainer_1")
        self.assertEqual(records[0].trainer_2, "trainer_2")
        self.assertEqual(records[0].terrain, "Electric")
        self.assertEqual(records[0].weather, "Sun")

        # Turn 2 active slots after Volt Switch (Slot 2 -> Garchomp), Hazard come back (Slot 1 -> Venusaur),
        # and Parting Shot (Incineroar Slot 1 -> Dragonite)
        self.assertEqual((records[1].trainer_1_active_1, records[1].trainer_1_active_2), ("Venusaur", "Garchomp"))
        self.assertEqual((records[1].trainer_2_active_1, records[1].trainer_2_active_2), ("Dragonite", "Sneasler"))

        # Turn 3 active slots after double faint of Venusaur (Slot 1) and Garchomp (Slot 2)
        self.assertEqual(
            (records[2].trainer_1_active_1, records[2].trainer_1_active_2),
            ("Raichu-Mega-X", "Charizard-Mega-Y"),
        )

        # Turn 4 active slots after both Sneasler and Dragonite fainted on T3, with only Incineroar left on bench (TEL-03)
        self.assertEqual((records[3].trainer_2_active_1, records[3].trainer_2_active_2), ("Incineroar", ""))

    def test_field_conditions_weather_damage_and_variance_precision(self) -> None:
        """Verify TEL-04..08: turn-scoped Tailwind/hazards, harsh sunlight fade, EoT weather, self-dmg, Fake Out/Phantom Force."""
        log = """
☆trainer_1 and ☆trainer_2 joined
Format: [Gen 9 Champions] VGC 2026 Reg M-C
Battle started between trainer_1 and trainer_2!
Go! Pelipper!
Go! Raichu!
trainer_2 sent out Glimmora!
trainer_2 sent out Annihilape!
[Pelipper's Drizzle]
It started to rain!
Turn 1
Raichu used Fake Out!
(The opposing Glimmora lost 5% of its health!)
[The opposing Glimmora's Toxic Debris]
Poison spikes were scattered around the feet of your team!
The opposing Glimmora flinched and couldn't move!
Pelipper used Tailwind!
The Tailwind blew from behind your team!
The opposing Annihilape used Substitute!
(The opposing Annihilape lost 25% of its health!)
Turn 2
Raichu used Feint!
(Pelipper lost 2.0% of its health!)
The opposing Annihilape used Phantom Force!
The opposing Annihilape vanished instantly!
Pelipper used Hurricane!
The opposing Annihilape avoided the attack!
A critical hit on the opposing Glimmora!
(The opposing Glimmora lost 95% of its health!)
The opposing Glimmora fainted!
The rain stopped.
trainer_2 sent out Tyranitar!
[The opposing Tyranitar's Sand Stream]
A sandstorm kicked up!
Turn 3
The opposing Annihilape used Phantom Force!
(Pelipper lost 45.0% of its health!)
Your team's Tailwind petered out!
The sandstorm subsided.
Turn 4
Raichu used Volt Switch!
(The opposing Tyranitar lost 20% of its health!)
trainer_2 forfeited.
trainer_1 won the battle!
"""
        records = extract_turn_telemetry(log, pov_trainer="trainer_1")
        self.assertEqual(len(records), 4)

        # Turn 1: Fake Out Flinch (TEL-08), Substitute 25% excluded from damage_dealt_to_trainer_2 (TEL-07),
        # T1_Tailwind + T1_Toxic_Spikes active (TEL-04)
        t1 = records[0]
        self.assertEqual(t1.damage_dealt_to_trainer_2, 5.0)
        self.assertIn("Fake Out Flinch on Glimmora", t1.variance_events)
        self.assertIn("T1_Tailwind", t1.field_conditions)
        self.assertIn("T1_Toxic_Spikes", t1.field_conditions)

        # Turn 2: Friendly-fire Feint (2.0%) excluded from damage_dealt_to_trainer_1 (TEL-07),
        # Phantom Force dodge NOT logged as Attack Missed (TEL-08), spread crit logged (TEL-08),
        # combat weather stays Rain even though Tyranitar set Sand at end-of-turn faint replacement (TEL-06)
        t2 = records[1]
        self.assertEqual(t2.damage_dealt_to_trainer_1, 0.0)
        self.assertEqual(t2.damage_dealt_to_trainer_2, 95.0)
        self.assertNotIn("Attack Missed", t2.variance_events)
        self.assertIn("Critical Hit", t2.variance_events)
        self.assertEqual(t2.weather, "Rain")

        # Turn 3: Sand carried into Turn 3 from T2 EoT Tyranitar switch-in; Tailwind still active during T3 combat
        t3 = records[2]
        self.assertEqual(t3.weather, "Sand")
        self.assertIn("T1_Tailwind", t3.field_conditions)

        # Turn 4: Tailwind petered out at end of T3 and Sand subsided at end of T3 (TEL-04, TEL-05)
        t4 = records[3]
        self.assertEqual(t4.weather, "None")
        self.assertNotIn("T1_Tailwind", t4.field_conditions)

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

    def test_bo3_next_link_uses_canonical_match_slug(self) -> None:
        """Ensure Bo3 footer `Next: [Game 2 of 3](.../battle-...)` does not hijack match_id."""
        bo3_log = (
            "Game 1 of [a best-of-3](https://play.pokemonshowdown.com/"
            "game-bestof3-gen9championsvgc2026regmcbo3-12345)\n"
            + SAMPLE_CHAT_LOG
            + "\nNext: [Game 2 of 3](https://play.pokemonshowdown.com/"
            "battle-gen9championsvgc2026regmcbo3-9999999999)\n"
        )
        records = extract_turn_telemetry(bo3_log, pov_trainer="trainer_1")
        self.assertEqual(len(records), 3)
        match_id = records[0].match_id
        self.assertRegex(match_id, r"^match-[0-9a-f]{12}$")
        self.assertNotIn("9999999999", match_id)


if __name__ == "__main__":
    unittest.main()
