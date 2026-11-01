#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for Roster Validator (engine/validate_roster.py)
"""

import unittest

from engine.validate_roster import validate_roster, classify_move


class TestValidateRoster(unittest.TestCase):
    """Verifies Regulation M-C roster validation and legality checks."""

    def test_valid_single_pokemon_paste(self):
        """Test for valid single pokemon paste."""
        paste = """
Garchomp @ Focus Sash
Ability: Rough Skin
Level: 50
Jolly Nature
SP: 0 HP / 32 Atk / 2 Def / 0 SpA / 0 SpD / 32 Spe
- Earthquake
- Dragon Claw
- Stomping Tantrum
- Protect
"""
        audit = validate_roster(paste)
        self.assertTrue(audit["is_valid"])
        self.assertEqual(len(audit["errors"]), 0)
        self.assertEqual(len(audit["slots"]), 1)
        slot = audit["slots"][0]
        self.assertEqual(slot["species"], "Garchomp")
        self.assertIn("Ground", slot["verified_types"])
        self.assertIn("Dragon", slot["verified_types"])

    def test_item_clause_violation(self):
        """Test for item clause violation."""
        paste = """
Garchomp @ Focus Sash
Ability: Rough Skin
Level: 50
Jolly Nature
SP: 0 HP / 32 Atk / 2 Def / 0 SpA / 0 SpD / 32 Spe
- Protect

Sneasler @ Focus Sash
Ability: Unburden
Level: 50
Jolly Nature
SP: 0 HP / 32 Atk / 2 Def / 0 SpA / 0 SpD / 32 Spe
- Protect
"""
        audit = validate_roster(paste)
        self.assertFalse(audit["is_valid"])
        self.assertTrue(any("Item Clause Violation" in err for err in audit["errors"]))

    def test_illegal_item_rejected(self):
        """Test for illegal item rejected."""
        paste = """
Pelipper @ Custap Berry
Ability: Drizzle
Level: 50
Bold Nature
SP: 32 HP / 0 Atk / 20 Def / 14 SpA / 0 SpD / 0 Spe
- Protect
"""
        audit = validate_roster(paste)
        self.assertFalse(audit["is_valid"])
        self.assertTrue(any("Illegal Item" in err for err in audit["errors"]))

    def test_illegal_species_rejected(self):
        """Test for illegal species rejected."""
        paste = """
Flutter Mane @ Choice Specs
Ability: Protosynthesis
Level: 50
Timid Nature
SP: 0 HP / 0 Atk / 2 Def / 32 SpA / 0 SpD / 32 Spe
- Moonblast
"""
        audit = validate_roster(paste)
        self.assertFalse(audit["is_valid"])
        self.assertTrue(any("Illegal or Unknown Species" in err for err in audit["errors"]))



    def test_classify_move_dual_type_stab_and_conversions(self):
        """Test move classification for Primary STAB, Secondary STAB, Adaptability, and -ate conversions."""
        # Garchomp (Dragon/Ground): Earthquake is Secondary STAB Ground, Dragon Claw is Primary STAB Dragon
        c_eq = classify_move("Earthquake", ["Dragon", "Ground"])
        self.assertTrue(c_eq["is_stab"])
        self.assertIn("Secondary STAB (Ground)", c_eq["classification"])

        c_dc = classify_move("Dragon Claw", ["Dragon", "Ground"])
        self.assertTrue(c_dc["is_stab"])
        self.assertIn("Primary STAB (Dragon)", c_dc["classification"])

        # Non-STAB Coverage: Rock Slide on Garchomp
        c_rs = classify_move("Rock Slide", ["Dragon", "Ground"])
        self.assertFalse(c_rs["is_stab"])
        self.assertEqual(c_rs["classification"], "Non-STAB Coverage (1.0x)")

        # Aerilate Hyper Voice on Mega Salamence (Dragon/Flying): Converted to Flying with STAB
        c_aeri = classify_move("Hyper Voice", ["Dragon", "Flying"], ability="Aerilate")
        self.assertTrue(c_aeri["is_stab"])
        self.assertTrue(c_aeri["type_converted"])
        self.assertEqual(c_aeri["type"], "Flying")
        self.assertIn("Converted Secondary STAB (Flying)", c_aeri["classification"])

        # Status move
        c_prot = classify_move("Protect", ["Dragon", "Ground"])
        self.assertEqual(c_prot["classification"], "Status")


if __name__ == "__main__":
    unittest.main()
