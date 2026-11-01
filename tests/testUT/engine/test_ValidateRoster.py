#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for Roster Validator (engine/validate_roster.py)
"""

import unittest

from engine.validate_roster import validate_roster


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


if __name__ == "__main__":
    unittest.main()
