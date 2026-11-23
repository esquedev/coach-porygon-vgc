# -*- coding: utf-8 -*-
"""Unit tests for Regulation M-C Turn State Compiler (`engine.state`)."""

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


class TestTurnStateCompiler(unittest.TestCase):
    """Verify TurnStateCompiler under Regulation M-C."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.compiler = TurnStateCompiler()

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

    def test_dual_mega_holders_compilation(self) -> None:
        """Verify TurnStateCompiler pre-compiles Mega transitions for multiple Mega Stone holders."""
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


if __name__ == "__main__":
    unittest.main()

