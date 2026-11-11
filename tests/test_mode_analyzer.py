# -*- coding: utf-8 -*-
"""Unit tests for Regulation M-C Team Modes, Leads, Slug Map & Preview Playbook Generator."""

import csv
from pathlib import Path
import tempfile
import unittest

from engine.db_registry import get_registry
from engine.modes.mode_analyzer import (
    ALL_TYPES,
    LeadEvaluation,
    LeadPair,
    ModeEvaluation,
    TeamMemberData,
    TeamMode,
    TeamModeAnalyzer,
)
from engine.modes.archetype_matcher import (
    ArchetypeMatchupPlan,
    TournamentArchetype,
    TournamentArchetypeMatcher,
)
from scripts.generate_team_preview_playbook import (
    generate_html_playbook,
    generate_mermaid_cheatsheet,
    parse_telemetry_csv,
    resolve_item_path,
    resolve_sprite_path,
)

SAMPLE_PASTE = """
Hazard (Charizard) @ Charizardite Y  
Ability: Blaze  
Level: 50  
Modest Nature  
EVs: 22 HP / 19 Def / 3 SpA / 1 SpD / 21 Spe  
- Weather Ball  
- Heat Wave  
- Solar Beam  
- Protect  

Raichu @ Raichunite X  
Ability: Lightning Rod  
Level: 50  
Jolly Nature  
EVs: 31 HP / 2 Atk / 1 Def / 32 Spe  
- Volt Tackle  
- Volt Switch  
- Nuzzle  
- Fake Out  

Milotic @ Leftovers  
Ability: Competitive  
Level: 50  
Calm Nature  
EVs: 31 HP / 13 Def / 1 SpA / 21 SpD  
- Scald  
- Ice Beam  
- Icy Wind  
- Recover  

Garchomp @ Choice Scarf  
Ability: Rough Skin  
Level: 50  
Adamant Nature  
EVs: 2 HP / 30 Atk / 2 SpD / 32 Spe  
- Stomping Tantrum  
- Earthquake  
- Dragon Claw  
- Rock Slide  

Grimmsnarl @ Light Clay  
Ability: Prankster  
Level: 50  
Impish Nature  
EVs: 32 HP / 16 Def / 15 SpD / 3 Spe  
- Spirit Break  
- Light Screen  
- Reflect  
- Parting Shot  

Kingambit @ Focus Sash  
Ability: Defiant  
Level: 50  
Adamant Nature  
EVs: 32 Atk / 1 Def / 1 SpD / 32 Spe  
- Kowtow Cleave  
- Sucker Punch  
- Iron Head  
- Protect  
"""


class TestTeamModeAnalyzer(unittest.TestCase):
    """Test suite for 4-mon modes, lead combinatorics, and zero-hallucination move grounding."""

    @classmethod
    def setUpClass(cls):
        cls.registry = get_registry()
        cls.analyzer = TeamModeAnalyzer(cls.registry)
        cls.members = cls.analyzer.parse_team_paste(SAMPLE_PASTE)

    def test_parse_team_paste(self):
        """Verifies parsing of 6 unique team members and Mega Evolution handling."""
        self.assertEqual(len(self.members), 6)
        species_list = [m.species for m in self.members]
        for expected in ("Charizard", "Raichu", "Milotic", "Garchomp", "Grimmsnarl", "Kingambit"):
            self.assertIn(expected, species_list)

        char = next(m for m in self.members if m.species == "Charizard")
        self.assertTrue(char.is_mega)
        self.assertEqual(char.canonical_species, "Charizard-Mega-Y")

        raichu = next(m for m in self.members if m.species == "Raichu")
        self.assertTrue(raichu.is_mega)
        self.assertEqual(raichu.canonical_species, "Raichu-Mega-X")

    def test_generate_modes_combinatorics(self):
        """Verifies exactly C(6,4) = 15 4-mon modes are produced."""
        modes = self.analyzer.generate_all_modes(self.members)
        self.assertEqual(len(modes), 15)
        for idx, mode in enumerate(modes, start=1):
            self.assertEqual(mode.mode_id, idx)
            self.assertEqual(len(mode.members), 4)
            self.assertEqual(len(set(m.slot_index for m in mode.members)), 4)

    def test_generate_leads_combinatorics(self):
        """Verifies exactly C(6,2) = 15 unordered lead pairs are produced."""
        leads = self.analyzer.generate_all_leads(self.members)
        self.assertEqual(len(leads), 15)
        for idx, lead in enumerate(leads, start=1):
            self.assertEqual(lead.lead_id, idx)
            self.assertNotEqual(lead.pokemon_1.slot_index, lead.pokemon_2.slot_index)

    def test_mode_evaluation_metrics(self):
        """Verifies offensive coverage, defensive weaknesses, and composite scoring."""
        modes = self.analyzer.generate_all_modes(self.members)
        evaluation = self.analyzer.evaluate_mode(modes[0])

        self.assertGreaterEqual(evaluation.coverage_count, 1)
        self.assertLessEqual(evaluation.coverage_count, 18)
        self.assertGreaterEqual(evaluation.coverage_score, 0.0)
        self.assertLessEqual(evaluation.coverage_score, 1.0)
        self.assertEqual(len(evaluation.defensive_weaknesses), 18)
        self.assertGreaterEqual(evaluation.composite_score, 0.0)
        self.assertLessEqual(evaluation.composite_score, 100.0)

    def test_no_hallucinated_screens_on_raichu_garchomp(self):
        """Verifies Raichu + Garchomp has pivot (Volt Switch) but NEVER claims Screens."""
        leads = self.analyzer.generate_all_leads(self.members)
        raichu_chomp = next(
            l for l in leads
            if {"raichu", "garchomp"} == {l.pokemon_1.species.lower(), l.pokemon_2.species.lower()}
        )
        eval_res = self.analyzer.evaluate_lead(raichu_chomp)
        self.assertTrue(eval_res.has_fake_out)
        self.assertTrue(eval_res.has_pivot)
        self.assertFalse(eval_res.has_screens)
        self.assertTrue(eval_res.has_scarf_or_tailwind)
        self.assertNotIn("Screens", eval_res.tactical_summary)
        self.assertIn("Volt Switch", eval_res.tactical_summary)

        # Conversely, Grimmsnarl + Garchomp MUST have screens
        grimm_chomp = next(
            l for l in leads
            if {"grimmsnarl", "garchomp"} == {l.pokemon_1.species.lower(), l.pokemon_2.species.lower()}
        )
        grimm_eval = self.analyzer.evaluate_lead(grimm_chomp)
        self.assertTrue(grimm_eval.has_screens)
        self.assertIn("Screens", grimm_eval.tactical_summary)


class TestTournamentArchetypeMatcher(unittest.TestCase):
    """Test suite for Regulation M-C tournament archetype matching & move verification."""

    @classmethod
    def setUpClass(cls):
        cls.registry = get_registry()
        cls.analyzer = TeamModeAnalyzer(cls.registry)
        cls.members, cls.modes, cls.leads = cls.analyzer.analyze_team(SAMPLE_PASTE)
        cls.matcher = TournamentArchetypeMatcher(cls.registry)

    def test_canonical_archetypes_strictly_reg_mc_legal(self):
        """Verifies all core species in all 8 archetypes exist in the Regulation M-C Pokédex."""
        archetypes = self.matcher.get_canonical_archetypes()
        self.assertEqual(len(archetypes), 8)
        for arch in archetypes:
            for sp in arch.core_species:
                dex_entry = self.registry.get_pokemon(sp)
                self.assertIsNotNone(dex_entry, f"Species '{sp}' in '{arch.name}' is not in Regulation M-C Pokédex!")

    def test_generate_all_plans_and_move_verification(self):
        """Verifies every plan has valid Bring-4, Leads, and strictly verified Turn 1 moves."""
        plans = self.matcher.generate_all_plans(self.modes, self.leads)
        self.assertEqual(len(plans), 8)

        for plan in plans:
            lead_slots = set(plan.recommended_lead.slot_indices)
            mode_slots = set(plan.recommended_mode.slot_indices)
            self.assertTrue(lead_slots.issubset(mode_slots))

            self.assertEqual(len(plan.backline), 2)
            back_slots = set(m.slot_index for m in plan.backline)
            self.assertEqual(lead_slots.union(back_slots), mode_slots)

            # Verify Turn 1 command matrix references only moves actually known by that Pokémon
            lead_by_name = {
                plan.recommended_lead.pokemon_1.species: plan.recommended_lead.pokemon_1,
                plan.recommended_lead.pokemon_2.species: plan.recommended_lead.pokemon_2,
            }
            for sp_name, cmd_str in plan.step_4_turn_1_matrix.items():
                self.assertIn(sp_name, lead_by_name)
                mon = lead_by_name[sp_name]
                self.assertTrue(
                    any(mv in cmd_str for mv in mon.moves),
                    f"Command '{cmd_str}' for {sp_name} does not contain any of its known moves {mon.moves}!",
                )

    def test_tailwind_spike_offense_response(self):
        """Verifies that Garchomp + Grimmsnarl is recommended against Whimsicott/Glimmora."""
        plans = self.matcher.generate_all_plans(self.modes, self.leads)
        tailwind_plan = next(p for p in plans if p.archetype.archetype_id == "tailwind_spike_offense")
        lead_species = {tailwind_plan.recommended_lead.pokemon_1.species, tailwind_plan.recommended_lead.pokemon_2.species}
        self.assertEqual(lead_species, {"Garchomp", "Grimmsnarl"})


class TestPlaybookGeneratorOutputs(unittest.TestCase):
    """Test suite for deterministic slug resolution, telemetry sync, and HTML/Markdown rendering."""

    @classmethod
    def setUpClass(cls):
        cls.registry = get_registry()
        cls.analyzer = TeamModeAnalyzer(cls.registry)
        cls.members, cls.modes, cls.leads = cls.analyzer.analyze_team(SAMPLE_PASTE)
        cls.matcher = TournamentArchetypeMatcher(cls.registry)
        cls.plans = cls.matcher.generate_all_plans(cls.modes, cls.leads)

    def test_slug_map_deterministic_resolution(self):
        """Verifies exact sprite and item resolution via assets/slug_map.json without mega collisions."""
        base_chomp = resolve_sprite_path("Garchomp")
        self.assertIsNotNone(base_chomp)
        self.assertEqual(base_chomp.name, "garchomp.png")

        mega_chomp = resolve_sprite_path("Garchomp", "Garchomp-Mega-Z")
        self.assertIsNotNone(mega_chomp)
        self.assertEqual(mega_chomp.name, "garchomp-mega-z.png")

        indeedee_f = resolve_sprite_path("Indeedee-F")
        self.assertIsNotNone(indeedee_f)
        self.assertEqual(indeedee_f.name, "indeedee-female.png")

        scarf_path = resolve_item_path("Choice Scarf")
        self.assertIsNotNone(scarf_path)
        self.assertEqual(scarf_path.name, "choice-scarf.png")

        mega_stone_path = resolve_item_path("Charizardite Y")
        self.assertIsNotNone(mega_stone_path)
        self.assertEqual(mega_stone_path.name, "charizardite-y.png")

    def test_telemetry_csv_integration_and_rendering(self):
        """Verifies live telemetry CSV parsing and rendering into HTML and Markdown reports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "battles_telemetry.csv"
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "match_id", "timestamp", "turn", "trainer_1", "trainer_2",
                        "trainer_1_active_1", "trainer_1_active_2", "trainer_2_active_1", "trainer_2_active_2",
                        "trainer_1_moves", "trainer_2_moves", "damage_dealt_to_trainer_2", "damage_dealt_to_trainer_1",
                        "faints_this_turn", "variance_events", "weather", "terrain", "field_conditions", "winner", "comment",
                    ],
                )
                writer.writeheader()
                writer.writerow({
                    "match_id": "battle-test-101",
                    "timestamp": "2026-11-10T17:00:00Z",
                    "turn": "1",
                    "trainer_1": "BeRightVGC",
                    "trainer_2": "RivalPlayer",
                    "trainer_1_active_1": "Garchomp",
                    "trainer_1_active_2": "Grimmsnarl",
                    "trainer_2_active_1": "Whimsicott",
                    "trainer_2_active_2": "Glimmora",
                    "trainer_1_moves": "Garchomp: Rock Slide; Grimmsnarl: Light Screen",
                    "trainer_2_moves": "Whimsicott: Tailwind",
                    "damage_dealt_to_trainer_2": "95.0",
                    "damage_dealt_to_trainer_1": "30.0",
                    "faints_this_turn": "None",
                    "variance_events": "None",
                    "weather": "Clear",
                    "terrain": "None",
                    "field_conditions": "Light Screen (T1)",
                    "winner": "BeRightVGC",
                    "comment": "Textbook Scarf Rock Slide + Light Screen countered Tailwind lead!",
                })

            telemetry = parse_telemetry_csv(csv_path)
            self.assertEqual(telemetry.total_matches, 1)
            self.assertEqual(telemetry.wins, 1)

            html = generate_html_playbook("char_y_v3", self.members, self.plans, self.modes, self.leads, telemetry)
            self.assertIn("90-Second Team Preview Sequential Checklist", html)
            self.assertIn("If-Then-Else Decision-Tree Rulebook", html)
            self.assertIn("battle-test-101", html)
            self.assertIn("Textbook Scarf Rock Slide + Light Screen countered Tailwind lead!", html)

            md = generate_mermaid_cheatsheet("char_y_v3", self.plans, self.modes, self.leads, telemetry)
            self.assertIn("## 1. The 90-Second Team Preview Execution Protocol", md)
            self.assertIn("## 2. If-Then-Else Decision-Tree Rulebook", md)
            self.assertIn("1W / 1G", md)


if __name__ == "__main__":
    unittest.main()
