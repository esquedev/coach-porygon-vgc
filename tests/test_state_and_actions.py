# -*- coding: utf-8 -*-
"""Unit tests for Regulation M-C Turn State Compiler & Legal Action Enumerator."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.parser import parse_showdown_chat_log, parse_showdown_paste
from engine.parser.models import ParsedBattle, ParsedTeam
from engine.state import (
    ActionType,
    LegalActionEnumerator,
    TurnStateCompiler,
    calculate_level_50_stats,
)


USER_TEAM_PASTE = """
Charizard @ Charizardite Y  
Ability: Blaze  
EVs: 2 HP / 12 Def / 28 SpA / 24 Spe  
Timid Nature  
Level: 50  
- Heat Wave  
- Scorching Sands  
- Solar Beam  
- Protect  

Raichu @ Raichunite X  
Ability: Lightning Rod  
EVs: 10 HP / 30 Atk / 26 Spe  
Jolly Nature  
Level: 50  
- Volt Tackle  
- Volt Switch  
- Nuzzle  
- Fake Out  

Garchomp @ Life Orb  
Ability: Rough Skin  
EVs: 2 HP / 32 Atk / 32 Spe  
Jolly Nature  
Level: 50  
- Stomping Tantrum  
- Dragon Claw  
- Rock Slide  
- Protect  

Grimmsnarl @ Light Clay  
Ability: Prankster  
EVs: 32 HP / 16 Def / 15 SpD / 3 Spe  
Impish Nature  
Level: 50  
- Reflect  
- Light Screen  
- Spirit Break  
- Parting Shot  

Kingambit @ Focus Sash  
Ability: Defiant  
EVs: 2 HP / 32 Atk / 32 Spe  
Jolly Nature  
Level: 50  
- Kowtow Cleave  
- Iron Head  
- Low Kick  
- Protect  

Milotic @ Sitrus Berry  
Ability: Competitive  
EVs: 32 HP / 6 Def / 15 SpA / 13 Spe  
Bold Nature  
Level: 50  
- Scald  
- Icy Wind  
- Recover  
- Protect
"""

BO1_TURN_1_LOG = """
☆Lupiticus and ☆khoihandsome joined
Format:
[Gen 9 Champions] VGC 2026 Reg M-C
Rated battle
Species Clause: Limit one of each Pokemon
Item Clause: Limit 1 of each item
Lupiticus's team:
Arcanine-Hisui / Charizard / Mimikyu / Kingambit / Golisopod / Zoroark-Hisui
khoihandsome's team:
Starmie / Umbreon / Golisopod / Farigiraf / Aegislash / Rillaboom
Battle started between Lupiticus and khoihandsome!
Go! Charizard!
Go! Arcanine (Arcanine-Hisui)!
khoihandsome sent out Starmie!
khoihandsome sent out Rillaboom!
[The opposing Rillaboom's Grassy Surge]
Grass grew to cover the battlefield!
Turn 1
"""


class TestTurnStateAndLegalActions(unittest.TestCase):
    """Verify TurnStateCompiler and LegalActionEnumerator under Regulation M-C."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.compiler = TurnStateCompiler()
        cls.enumerator = LegalActionEnumerator()

    def test_duckdb_backed_calculate_level_50_stats(self) -> None:
        """Verify calculate_level_50_stats queries real base stats from in-memory DuckDB."""
        # Charizard base stats: 78 HP / 84 Atk / 78 Def / 109 SpA / 85 SpD / 100 Spe
        # With 2 HP / 12 Def / 28 SpA / 24 Spe and Timid (+Spe, -Atk):
        # HP = 78 + 2 + 15 + 60 = 155
        # Spe = trunc(trunc((100 + 24 + 15 + 5) * 110, 16) / 100) = trunc(144 * 1.1) = 158
        max_hp, stats = calculate_level_50_stats(
            "Charizard",
            {"hp": 2, "def": 12, "spa": 28, "spe": 24},
            "Timid",
        )
        self.assertEqual(max_hp, 155)
        self.assertEqual(stats["spe"], 158)
        self.assertEqual(stats["spa"], 109 + 28 + 15 + 5)  # 157

    def test_compile_bo1_turn_1_and_unrevealed_bench_selection(self) -> None:
        """Verify Bo1 state compilation and tournament-weighted 2-slot bench inference."""
        battle = parse_showdown_chat_log(
            BO1_TURN_1_LOG,
            pov_trainer="Lupiticus",
            user_team_paste=USER_TEAM_PASTE,
        )
        state = self.compiler.compile_turn_state(battle)

        # Active leads for trainer_1: Charizard & Arcanine-Hisui
        t1_s0, t1_s1 = state.trainer_1.active_slots
        self.assertIsNotNone(t1_s0)
        self.assertIsNotNone(t1_s1)
        self.assertEqual(t1_s0.base_species, "Charizard")
        self.assertEqual(t1_s1.base_species, "Arcanine-Hisui")

        # Charizard holds Charizardite Y -> pre-compiled Mega Charizard Y transition
        self.assertTrue(t1_s0.can_mega_evolve)
        self.assertEqual(t1_s0.mega_target_species, "Charizard-Mega-Y")
        self.assertEqual(t1_s0.mega_ability, "Drought")
        self.assertIsNotNone(t1_s0.mega_level_50_stats)
        # Mega Charizard Y has 159 base SpA vs 109 base SpA (+50 SpA at Level 50!)
        self.assertEqual(
            t1_s0.mega_level_50_stats["spa"],
            t1_s0.level_50_stats["spa"] + 50,
        )

        # Active leads for trainer_2: Starmie & Rillaboom, plus 2 inferred bench slots
        t2_s0, t2_s1 = state.trainer_2.active_slots
        self.assertIsNotNone(t2_s0)
        self.assertIsNotNone(t2_s1)
        self.assertEqual({t2_s0.base_species, t2_s1.base_species}, {"Starmie", "Rillaboom"})
        self.assertEqual(len(state.trainer_2.bench_slots), 2)
        bench_species = {b.base_species for b in state.trainer_2.bench_slots}
        self.assertTrue(
            bench_species.issubset({"Umbreon", "Golisopod", "Farigiraf", "Aegislash"})
        )

        # Field terrain from Rillaboom's Grassy Surge
        self.assertEqual(state.field.terrain, "Grassy")

    def test_dual_mega_holders_branching_and_joint_constraint(self) -> None:
        """Verify both mega_evolve=False and mega_evolve=True branch, and joint actions forbid double Mega."""
        sets = parse_showdown_paste(USER_TEAM_PASTE)
        battle = ParsedBattle()
        battle.trainer_1 = ParsedTeam(
            trainer_name="trainer_1",
            team_preview=list(sets.keys()),
            battle_roster=["Charizard", "Raichu", "Garchomp", "Kingambit"],
            leads=("Charizard", "Raichu"),
            active_slots=["Charizard", "Raichu"],
            pokemon_sets=sets,
        )
        battle.trainer_2 = ParsedTeam(
            trainer_name="trainer_2",
            team_preview=list(sets.keys()),
            battle_roster=["Garchomp", "Grimmsnarl", "Kingambit", "Milotic"],
            leads=("Garchomp", "Grimmsnarl"),
            active_slots=["Garchomp", "Grimmsnarl"],
            pokemon_sets=parse_showdown_paste(USER_TEAM_PASTE),
        )

        state = self.compiler.compile_turn_state(battle, run_inference=False)

        # Both Charizard (slot 0) and Raichu (slot 1) hold valid Mega Stones
        s0_mon, s1_mon = state.trainer_1.active_slots
        self.assertTrue(s0_mon.can_mega_evolve)
        self.assertEqual(s0_mon.mega_target_species, "Charizard-Mega-Y")
        self.assertTrue(s1_mon.can_mega_evolve)
        self.assertEqual(s1_mon.mega_target_species, "Raichu-Mega-X")

        s0_actions = self.enumerator.enumerate_slot_actions(state, "trainer_1", 0)
        s1_actions = self.enumerator.enumerate_slot_actions(state, "trainer_1", 1)

        # Every move on Charizard and Raichu must appear with mega_evolve=False AND mega_evolve=True
        s0_heat_wave_mega = [
            a for a in s0_actions if a.move_name == "Heat Wave" and a.mega_evolve
        ]
        s0_heat_wave_base = [
            a for a in s0_actions if a.move_name == "Heat Wave" and not a.mega_evolve
        ]
        self.assertEqual(len(s0_heat_wave_mega), 1)
        self.assertEqual(len(s0_heat_wave_base), 1)

        s1_fake_out_mega = [
            a for a in s1_actions if a.move_name == "Fake Out" and a.mega_evolve
        ]
        s1_fake_out_base = [
            a for a in s1_actions if a.move_name == "Fake Out" and not a.mega_evolve
        ]
        # Fake Out is normal targeting -> 3 targets (2 foes + 1 ally partner)
        self.assertEqual(len(s1_fake_out_mega), 3)
        self.assertEqual(len(s1_fake_out_base), 3)

        # Joint enumeration must allow s0 Mega OR s1 Mega OR neither, NEVER both
        joint_actions = self.enumerator.enumerate_joint_actions(state, "trainer_1")
        both_mega = [
            ja for ja in joint_actions if ja.slot_0_action.mega_evolve and ja.slot_1_action.mega_evolve
        ]
        only_s0_mega = [
            ja for ja in joint_actions if ja.slot_0_action.mega_evolve and not ja.slot_1_action.mega_evolve
        ]
        only_s1_mega = [
            ja for ja in joint_actions if not ja.slot_0_action.mega_evolve and ja.slot_1_action.mega_evolve
        ]
        neither_mega = [
            ja for ja in joint_actions if not ja.slot_0_action.mega_evolve and not ja.slot_1_action.mega_evolve
        ]
        self.assertEqual(len(both_mega), 0)
        self.assertGreater(len(only_s0_mega), 0)
        self.assertGreater(len(only_s1_mega), 0)
        self.assertGreater(len(neither_mega), 0)

    def test_ally_targeting_fake_out_restriction_and_joint_switches(self) -> None:
        """Verify ally targeting, Turn > 1 Fake Out pruning, and joint switch constraints."""
        sets = parse_showdown_paste(USER_TEAM_PASTE)
        # Set Garchomp and Raichu as active on Turn 2 (active_turns = 2)
        sets["Garchomp"].active_turns = 2
        sets["Garchomp"].used_protect_last_turn = True
        sets["Raichu"].active_turns = 2

        battle = ParsedBattle(turns_played=1)
        battle.trainer_1 = ParsedTeam(
            trainer_name="trainer_1",
            team_preview=list(sets.keys()),
            battle_roster=["Garchomp", "Raichu", "Charizard", "Kingambit"],
            leads=("Garchomp", "Raichu"),
            active_slots=["Garchomp", "Raichu"],
            pokemon_sets=sets,
        )
        battle.trainer_2 = ParsedTeam(
            trainer_name="trainer_2",
            team_preview=list(sets.keys()),
            battle_roster=["Grimmsnarl", "Milotic", "Charizard", "Kingambit"],
            leads=("Grimmsnarl", "Milotic"),
            active_slots=["Grimmsnarl", "Milotic"],
            pokemon_sets=parse_showdown_paste(USER_TEAM_PASTE),
        )

        state = self.compiler.compile_turn_state(battle, run_inference=False)
        s0_actions = self.enumerator.enumerate_slot_actions(state, "trainer_1", 0)
        s1_actions = self.enumerator.enumerate_slot_actions(state, "trainer_1", 1)

        # 1. Garchomp's Stomping Tantrum (normal target) must include targeting ally Raichu (trainer_1, slot=1)
        tantrum_targets = {
            (a.target.domain, a.target.slot)
            for a in s0_actions
            if a.move_name == "Stomping Tantrum" and a.target is not None
        }
        self.assertEqual(
            tantrum_targets,
            {("trainer_2", 0), ("trainer_2", 1), ("trainer_1", 1)},
        )

        # 2. Garchomp used Protect last turn -> consecutive Protect is pruned by default
        protect_actions = [a for a in s0_actions if a.move_name == "Protect"]
        self.assertEqual(len(protect_actions), 0)

        # 3. Raichu has active_turns == 2 -> Fake Out must be blocked
        fake_out_actions = [a for a in s1_actions if a.move_name == "Fake Out"]
        self.assertEqual(len(fake_out_actions), 0)

        # 4. Joint switch actions cannot switch both slots into the same bench Pokemon
        joint_actions = self.enumerator.enumerate_joint_actions(state, "trainer_1")
        double_switches = [
            (ja.slot_0_action.switch_in_species, ja.slot_1_action.switch_in_species)
            for ja in joint_actions
            if ja.slot_0_action.action_type == ActionType.SWITCH
            and ja.slot_1_action.action_type == ActionType.SWITCH
        ]
        # Bench has Charizard and Kingambit -> only (Charizard, Kingambit) and (Kingambit, Charizard) are valid
        self.assertEqual(
            set(double_switches),
            {("Charizard", "Kingambit"), ("Kingambit", "Charizard")},
        )


if __name__ == "__main__":
    unittest.main()

