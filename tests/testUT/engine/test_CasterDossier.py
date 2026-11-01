# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for Caster Dossier Engine (engine/caster_dossier.py)
Validates speed calculation, speed ladder interleaving, print pagination CSS verification,
and commentary talking point generation for esports casting.
"""

import unittest
from engine.caster_dossier import CasterDossierBuilder


class TestCasterDossier(unittest.TestCase):
    """Unit tests for the CasterDossierBuilder service."""

    def setUp(self) -> None:
        """Initialize the builder instance and fixture rosters."""
        self.builder = CasterDossierBuilder()

        self.team_a = [
            {"name": "Archaludon", "base_spe": 85, "sp_spe": 4, "nature_mod": 1.0, "item": "Assault Vest", "player": "Trainer A", "speed_tag": "Base 50"},
            {"name": "Pelipper", "base_spe": 65, "sp_spe": 0, "nature_mod": 1.0, "item": "Damp Rock", "player": "Trainer A", "speed_tag": "Base 50"},
            {"name": "Basculegion", "base_spe": 78, "sp_spe": 28, "nature_mod": 1.1, "item": "Choice Band", "weather_active": True, "player": "Trainer A", "speed_tag": "Swift Swim"},
        ]

        self.team_b = [
            {"name": "Charizard", "base_spe": 100, "sp_spe": 28, "nature_mod": 1.1, "item": "Charizardite Y", "is_mega": True, "mega_base_spe": 100, "player": "Trainer B", "speed_tag": "Mega Y"},
            {"name": "Garchomp", "base_spe": 102, "sp_spe": 32, "nature_mod": 1.1, "item": "Life Orb", "player": "Trainer B", "speed_tag": "Base 50"},
            {"name": "Whimsicott", "base_spe": 116, "sp_spe": 20, "nature_mod": 1.1, "item": "Focus Sash", "tailwind_active": True, "player": "Trainer B", "speed_tag": "Tailwind"},
        ]

    def test_compute_speed_base_and_modifiers(self) -> None:
        """Verify speed calculation with base, SP, nature, scarf, weather, and tailwind."""
        # Jolly Garchomp 32 SP (Nature 1.1x)
        # floor((102 + 32 + 20) * 1.1) = floor(154 * 1.1) = floor(169.4) = 169
        spe = self.builder.compute_speed(base_speed=102, sp=32, nature_mod=1.1)
        self.assertEqual(spe, 169)

        # Choice Scarf (+50%)
        spe_scarf = self.builder.compute_speed(base_speed=102, sp=32, nature_mod=1.1, item="Choice Scarf")
        self.assertEqual(spe_scarf, int(169 * 1.5))

        # Weather boost (2x)
        spe_weather = self.builder.compute_speed(base_speed=78, sp=28, nature_mod=1.1, weather_active=True)
        base_calc = int((78 + 28 + 20) * 1.1)  # floor(126 * 1.1) = 138
        self.assertEqual(spe_weather, base_calc * 2)

    def test_build_speed_ladder_interleaving_and_ranking(self) -> None:
        """Verify that the speed ladder ranks Pokémon across both teams descending by speed."""
        ladder = self.builder.build_speed_ladder(self.team_a, self.team_b)
        self.assertEqual(len(ladder), 6)

        # Ranks must be 1 to 6 in descending order of speed
        for i in range(len(ladder) - 1):
            self.assertGreaterEqual(ladder[i]["speed"], ladder[i + 1]["speed"])
            self.assertEqual(ladder[i]["rank"], i + 1)

    def test_validate_print_pagination_css(self) -> None:
        """Ensure the validator catches missing print CSS and passes compliant stylesheets."""
        valid_css_html = """
        <html>
        <head>
          <style>
            @media print {
              @page { size: A4 portrait; margin: 10mm; }
              .card { break-inside: avoid; }
              .page { break-after: page; }
            }
          </style>
        </head>
        <body></body>
        </html>
        """
        self.assertTrue(self.builder.validate_print_pagination_css(valid_css_html))

        invalid_html = "<html><head><style>.card { color: red; }</style></head><body></body></html>"
        self.assertFalse(self.builder.validate_print_pagination_css(invalid_html))

    def test_generate_caster_talking_points(self) -> None:
        """Verify the structured dictionary of commentary talking points."""
        ladder = self.builder.build_speed_ladder(self.team_a, self.team_b)
        points = self.builder.generate_caster_talking_points(
            matchup_name="Regional Finals",
            team_a_archetype="Rain Offense",
            team_b_archetype="Sun Balance",
            speed_ladder=ladder,
            trap_techs=["Archaludon holds Assault Vest", "Whimsicott holds Focus Sash"],
        )

        self.assertIn("pre_game_hook_30s", points)
        self.assertIn("lead_reveal_drama_15s", points)
        self.assertIn("mid_game_checkpoints", points)
        self.assertIn("trap_tech_alerts", points)
        self.assertIn("lethal_checkmate_triggers", points)
        self.assertEqual(len(points["trap_tech_alerts"]), 2)


if __name__ == "__main__":
    unittest.main()
