# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Caster Aid Matchup Dossier Engine
Provides deterministic calculation of speed hierarchies, type threat matrices,
lead scenario projections, and print pagination validation for esports casting.
"""

from typing import Any, Dict, List
import re


class CasterDossierBuilder:
    """Deterministic matchup analyzer and broadcast dossier builder for esports casters."""

    def __init__(self) -> None:
        """Initialize the caster dossier builder with default multipliers."""
        self.scarf_multiplier: float = 1.5
        self.weather_multiplier: float = 2.0
        self.tailwind_multiplier: float = 2.0

    def compute_speed(
        self,
        base_speed: int,
        sp: int = 0,
        nature_mod: float = 1.0,
        item: str = "",
        weather_active: bool = False,
        tailwind_active: bool = False,
        is_mega: bool = False,
        mega_base_speed: int = 0,
    ) -> int:
        """
        Compute deterministic Level 50 speed according to Regulation M-C sequential floor formulas.

        :param base_speed: Base speed stat of the species.
        :param sp: Stat points invested (0 to 32).
        :param nature_mod: Nature multiplier (0.9, 1.0, or 1.1).
        :param item: Held item name.
        :param weather_active: Whether speed-doubling weather (Rain/Sun/Sand/Snow) is active.
        :param tailwind_active: Whether Tailwind is active on the side.
        :param is_mega: Whether the Pokémon is in its Mega Evolved state.
        :param mega_base_speed: Base speed of the Mega form if applicable.
        :return: Final effective speed integer.
        """
        effective_base = mega_base_speed if (is_mega and mega_base_speed > 0) else base_speed
        raw_stat = int((effective_base + sp + 20) * nature_mod)

        # Item modifier (Choice Scarf 1.5x)
        if "scarf" in item.lower():
            raw_stat = int(raw_stat * self.scarf_multiplier)

        # Field modifiers
        if weather_active:
            raw_stat = int(raw_stat * self.weather_multiplier)
        if tailwind_active:
            raw_stat = int(raw_stat * self.tailwind_multiplier)

        return raw_stat

    def build_speed_ladder(
        self,
        team_a_pokemon: List[Dict[str, Any]],
        team_b_pokemon: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Build an interleaved, descending speed ladder across all 12 Pokémon from both rosters.

        :param team_a_pokemon: List of Pokémon dictionaries for Team A.
        :param team_b_pokemon: List of Pokémon dictionaries for Team B.
        :return: Sorted list of speed entries with ranking and visual tags.
        """
        ladder: List[Dict[str, Any]] = []

        for p in team_a_pokemon:
            spe = self.compute_speed(
                base_speed=p.get("base_spe", 100),
                sp=p.get("sp_spe", 0),
                nature_mod=p.get("nature_mod", 1.0),
                item=p.get("item", ""),
                weather_active=p.get("weather_active", False),
                tailwind_active=p.get("tailwind_active", False),
                is_mega=p.get("is_mega", False),
                mega_base_speed=p.get("mega_base_spe", 0),
            )
            ladder.append({
                "team": "Team A",
                "player": p.get("player", "Player A"),
                "name": p.get("name", "Unknown"),
                "speed": spe,
                "item": p.get("item", "None"),
                "ability": p.get("ability", "None"),
                "tag": p.get("speed_tag", "Base 50"),
            })

        for p in team_b_pokemon:
            spe = self.compute_speed(
                base_speed=p.get("base_spe", 100),
                sp=p.get("sp_spe", 0),
                nature_mod=p.get("nature_mod", 1.0),
                item=p.get("item", ""),
                weather_active=p.get("weather_active", False),
                tailwind_active=p.get("tailwind_active", False),
                is_mega=p.get("is_mega", False),
                mega_base_speed=p.get("mega_base_spe", 0),
            )
            ladder.append({
                "team": "Team B",
                "player": p.get("player", "Player B"),
                "name": p.get("name", "Unknown"),
                "speed": spe,
                "item": p.get("item", "None"),
                "ability": p.get("ability", "None"),
                "tag": p.get("speed_tag", "Base 50"),
            })

        ladder.sort(key=lambda x: x["speed"], reverse=True)
        for rank, entry in enumerate(ladder, start=1):
            entry["rank"] = rank

        return ladder

    def validate_print_pagination_css(self, html_content: str) -> bool:
        """
        Validate that the generated HTML contains strict print anti-page-break CSS declarations.
        Ensures that infographics, cards, and data tables are not clipped across page breaks.

        :param html_content: Full HTML source string.
        :return: True if all required pagination safeguards are present.
        """
        required_patterns = [
            r"@media\s+print",
            r"@page\s*\{",
            r"(?:page-break-inside:\s*avoid|break-inside:\s*avoid)",
            r"(?:page-break-after:\s*always|break-after:\s*page)",
        ]

        for pattern in required_patterns:
            if not re.search(pattern, html_content, re.IGNORECASE):
                return False

        return True

    def generate_caster_talking_points(
        self,
        matchup_name: str,
        team_a_archetype: str,
        team_b_archetype: str,
        speed_ladder: List[Dict[str, Any]],
        trap_techs: List[str],
    ) -> Dict[str, Any]:
        """
        Generate structured broadcast talking points and live commentary cues.

        :param matchup_name: Title of the set (e.g. 'Puebla Regional Finals').
        :param team_a_archetype: Macro archetype of Team A (e.g. 'Rain Offense').
        :param team_b_archetype: Macro archetype of Team B (e.g. 'Sun Balance').
        :param speed_ladder: Sorted speed hierarchy.
        :param trap_techs: Identified surprise tech items or moves.
        :return: Structured dictionary containing talking points by broadcast phase.
        """
        fastest_mon = speed_ladder[0] if speed_ladder else {"name": "None", "speed": 0, "team": "None"}

        return {
            "matchup_name": matchup_name,
            "pre_game_hook_30s": (
                f"Clash of macro styles: {team_a_archetype} meets {team_b_archetype}. "
                f"The decisive tempo battle revolves around turn-1 speed control and whether "
                f"{fastest_mon['name']} ({fastest_mon['speed']} Spe) establishes positional dominance."
            ),
            "lead_reveal_drama_15s": (
                "Watch the opening pairing closely! The player who secures weather control or forces "
                "an immediate defensive Protect will dictate the entire pacing of Game 1."
            ),
            "mid_game_checkpoints": [
                "Track Mega Evolution timing: instantaneous speed recalculation can flip turn order on the spot.",
                "Redirection watch: Follow Me / Rage Powder CANNOT absorb spread attacks like Earthquake or Make It Rain.",
                "Psychic Terrain priority check: Grounded priority attacks fail, but airborne targets remain fully vulnerable.",
            ],
            "trap_tech_alerts": trap_techs if trap_techs else ["Standard sets anticipated; watch for damage reduction berries."],
            "lethal_checkmate_triggers": (
                "Identify when the primary damage sponge faints. Once opposing answers to the primary sweeper "
                "are eliminated, the game enters a deterministic checkmate track."
            ),
        }
