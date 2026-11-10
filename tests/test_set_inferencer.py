# -*- coding: utf-8 -*-
"""Unit tests for Regulation M-C Tournament Usage Repository and Opponent Set Inferencer."""

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from engine.inference import (
        OpponentSetInferencer,
        TournamentUsageRepository,
        compute_level_50_stats_from_base,
        get_tournament_repository,
    )
    from engine.parser import parse_showdown_chat_log
except ImportError:
    from src.engine.inference import (
        OpponentSetInferencer,
        TournamentUsageRepository,
        compute_level_50_stats_from_base,
        get_tournament_repository,
    )
    from src.engine.parser import parse_showdown_chat_log


class TestOpponentSetInferencer(unittest.TestCase):
    """Test suite verifying tournament usage queries and Bayesian/constraint set inference."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = get_tournament_repository()
        cls.inferencer = OpponentSetInferencer(cls.repo)

        cls.user_paste = """
Charizard @ Charizardite Y  
Ability: Blaze  
EVs: 2 HP / 12 Def / 28 SpA / 24 Spe  
Timid Nature  
Level: 50  
- Heat Wave  
- Scorching Sands  
- Solar Beam  
- Protect  

Arcanine-Hisui @ Sitrus Berry  
Ability: Intimidate  
EVs: 20 HP / 32 Atk / 14 Spe  
Adamant Nature  
Level: 50  
- Flare Blitz  
- Rock Slide  
- Extreme Speed  
- Protect  
"""

        cls.bo1_chat_log = """
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
Battle timer is ON: inactive players will automatically lose when time's up. (requested by khoihandsome)
khoihandsome has 60 seconds left.

Battle started between Lupiticus and khoihandsome!

Go! Charizard!

Go! Arcanine (Arcanine-Hisui)!

khoihandsome sent out Starmie!

khoihandsome sent out Rillaboom!
[The opposing Rillaboom's Grassy Surge]
Grass grew to cover the battlefield!

Turn 1

The opposing Starmie's Starminite is reacting to the Key Stone!
The opposing Starmie has Mega Evolved into Mega Starmie!

Charizard used Protect!
Charizard protected itself!

Arcanine used Protect!
Arcanine protected itself!

The opposing Starmie used Minimize!
The opposing Starmie's evasiveness rose sharply!

The opposing Rillaboom used Swords Dance!
The opposing Rillaboom's Attack rose sharply!

Turn 2
khoihandsome has 30 seconds left.

Charizard's Charizardite Y is reacting to the Key Stone!
Charizard has Mega Evolved into Mega Charizard!
[Charizard's Drought]
The sunlight turned harsh!

The opposing Rillaboom used Grassy Glide!
(Arcanine lost 75% of its health!)

Charizard used Solar Beam!
Charizard absorbed light!
It's super effective!
(The opposing Starmie lost 97% of its health!)

The opposing Starmie used Minimize!
The opposing Starmie's evasiveness rose sharply!

Arcanine used Flare Blitz!
It's super effective!
(The opposing Rillaboom lost 100% of its health!)

The opposing Rillaboom fainted!

(The sunlight is strong.)
The opposing Starmie's HP was restored.
Arcanine's HP was restored.

khoihandsome sent out Golisopod!

Turn 3

Arcanine used Extreme Speed!
The opposing Starmie avoided the attack!

Charizard used Heat Wave!
It's not very effective on the opposing Starmie.
(The opposing Starmie lost 9% of its health!)
(The opposing Golisopod lost 54% of its health!)

The opposing Starmie fainted!
The opposing Golisopod held up its Red Card against Charizard!
[The opposing Golisopod's Emergency Exit]

Kingambit was dragged out!
khoihandsome forfeited.

Lupiticus won the battle!
"""

        cls.bo3_chat_log = """
☆ssooner and ☆lucillajade joined
Game 2 of [a best-of-3](https://play.pokemonshowdown.com/game-bestof3-gen9championsvgc2026regmcbo3-2711791290)
Format:
[Gen 9 Champions] VGC 2026 Reg M-C (Bo3)
Rated battle
ssooner's team:Metagross / Milotic / Staraptor / Kingambit / Whimsicott / Arcanine-Hisui
lucillajade's team:Kingambit / Sneasler / Rillaboom / Basculegion / Floette-Eternal / Salamence
Open team sheet for ssooner
Metagross @ Metagrossite
Ability: Clear Body
Jolly Nature
Level: 50
- Iron Head
- Protect
- Psychic Fangs
- Ice Punch
Milotic (M) @ Leftovers
Ability: Competitive
Bold Nature
Level: 50
- Muddy Water
- Coil
- Hypnosis
- Protect
Staraptor (M) @ Staraptite
Ability: Intimidate
Jolly Nature
Level: 50
- Dual Wingbeat
- Close Combat
- Protect
- Brave Bird
Kingambit (F) @ Life Orb
Ability: Defiant
Adamant Nature
Level: 50
- Kowtow Cleave
- Protect
- Sucker Punch
- Swords Dance
Whimsicott (M) @ Focus Sash
Ability: Prankster
Timid Nature
Level: 50
- Encore
- Charm
- Moonblast
- Tailwind
Arcanine-Hisui (M) @ Sitrus Berry
Ability: Rock Head
Jolly Nature
Level: 50
- Rock Blast
- Head Smash
- Flare Blitz
- Protect
Open team sheet for lucillajade
Kingambit (M) @ Chople Berry
Ability: Defiant
Adamant Nature
Level: 50
- Kowtow Cleave
- Sucker Punch
- Swords Dance
- Protect
Sneasler (M) @ Focus Sash
Ability: Poison Touch
Jolly Nature
Level: 50
- Poison Jab
- Close Combat
- Coaching
- Fake Out
Rillaboom (F) @ Life Orb
Ability: Grassy Surge
Adamant Nature
Level: 50
- Wood Hammer
- Grassy Glide
- High Horsepower
- Fake Out
Basculegion (M) @ Choice Scarf
Ability: Adaptability
Jolly Nature
Level: 50
- Wave Crash
- Last Respects
- Flip Turn
- Soak
Floette-Eternal (F) @ Floettite
Ability: Flower Veil
Modest Nature
Level: 50
- Draining Kiss
- Dazzling Gleam
- Calm Mind
- Protect
Salamence (M) @ Salamencite
Ability: Intimidate
Hasty Nature
Level: 50
- Body Slam
- Hyper Voice
- Draco Meteor
- Protect
Battle started between ssooner and lucillajade!
Go! Staraptor!
Go! Whimsicott!
lucillajade sent out Basculegion (Basculegion-M)!
lucillajade sent out Sneasler!
[Staraptor's Intimidate]
The opposing Basculegion's Attack fell!
The opposing Sneasler's Attack fell!
Turn 1
Staraptor's Staraptite is reacting to the Key Stone!
Staraptor has Mega Evolved into Mega Staraptor!
Whimsicott used Tailwind!
The Tailwind blew from behind your team!
Staraptor used Dual Wingbeat!
It's super effective!
(The opposing Sneasler lost 63% of its health!)
It's super effective!
(The opposing Sneasler lost 37% of its health!)
The opposing Sneasler fainted!
The Pokémon was hit 2 times!
The opposing Basculegion used Flip Turn!
It's not very effective...
(Whimsicott lost 21% of its health!)
lucillajade forfeited.
ssooner won the battle!
"""

    def test_tournament_archive_loaded(self) -> None:
        """Verify that all 4,965 regional tournament teams and Showdown mechanics are indexed."""
        self.assertEqual(self.repo.total_tournament_teams, 4965)
        self.assertIn("Charizard-Mega-Y", self.repo.pokedex)
        self.assertIn("Starmie-Mega", self.repo.pokedex)
        self.assertEqual(
            self.repo.resolve_species_name("Mega Charizard", item="Charizardite Y", is_mega=True),
            "Charizard-Mega-Y",
        )
        self.assertEqual(
            self.repo.resolve_species_name("Mega Starmie", item="Starminite", is_mega=True),
            "Starmie-Mega",
        )

        rilla_profile = self.repo.query_species_profile("Rillaboom")
        self.assertEqual(rilla_profile.sample_count, 2500)
        self.assertIn("Grassy Glide", rilla_profile.moves)
        self.assertIn("Miracle Seed", rilla_profile.items)

    def test_infer_bo1_opponent_sets_and_constraints(self) -> None:
        """Verify Bo1 opponent set inference, Single-Mega clause, and Speed bounds."""
        battle = parse_showdown_chat_log(
            self.bo1_chat_log,
            pov_trainer="Lupiticus",
            user_team_paste=self.user_paste,
        )
        report = self.inferencer.infer_battle(battle)

        # 1. Verify Starmie resolved to Starmie-Mega with Huge Power, Starminite, Minimize + 3 tournament moves
        starmie = battle.trainer_2.get_pokemon("Starmie")
        self.assertIsNotNone(starmie)
        self.assertEqual(starmie.species, "Starmie-Mega")
        self.assertEqual(starmie.ability, "Huge Power")
        self.assertEqual(starmie.item, "Starminite")
        self.assertIn("Minimize", starmie.moves)
        self.assertEqual(len(starmie.moves), 4)
        self.assertEqual(starmie.spread.total_sp, 66)

        # 2. Verify Empirical Speed Bound on Starmie-Mega:
        # In Turn 2, trainer_1's Charizard-Mega-Y (Base 100 Spe, 24 Spe SP, Timid = 158 Spe)
        # moved before Starmie-Mega (Solar Beam vs Minimize, both Priority 0)
        # and Starmie-Mega moved before trainer_1's Arcanine-Hisui (Base 90 Spe, 14 Spe SP, Adamant = 124 Spe).
        self.assertIn("Starmie", report.speed_bounds_by_species)
        min_spe, max_spe = report.speed_bounds_by_species["Starmie"]
        self.assertEqual(min_spe, 124)
        self.assertEqual(max_spe, 158)

        # Confirm chosen Starmie-Mega spread satisfies [124, 158] effective speed
        starmie_base = self.repo.get_base_stats("Starmie-Mega", is_mega=True)
        starmie_l50 = compute_level_50_stats_from_base(
            starmie_base, starmie.spread, starmie.nature or "Jolly"
        )
        self.assertGreaterEqual(starmie_l50["spe"], 124)
        self.assertLessEqual(starmie_l50["spe"], 158)

        # 3. Verify Rillaboom kept Grassy Surge, Grassy Glide, Swords Dance + filled to 4 moves
        rillaboom = battle.trainer_2.get_pokemon("Rillaboom")
        self.assertIsNotNone(rillaboom)
        self.assertEqual(rillaboom.ability, "Grassy Surge")
        self.assertIn("Grassy Glide", rillaboom.moves)
        self.assertIn("Swords Dance", rillaboom.moves)
        self.assertEqual(len(rillaboom.moves), 4)
        self.assertNotEqual(rillaboom.item, "Assault Vest")  # Ruled out by Swords Dance!
        self.assertEqual(rillaboom.spread.total_sp, 66)

        # 4. Verify Golisopod kept Red Card and is NOT Mega (since Starmie already Mega Evolved)
        golisopod = battle.trainer_2.get_pokemon("Golisopod")
        self.assertIsNotNone(golisopod)
        self.assertFalse(golisopod.is_mega)
        self.assertEqual(golisopod.item, "Red Card")
        self.assertEqual(golisopod.ability, "Emergency Exit")
        self.assertEqual(len(golisopod.moves), 4)
        self.assertEqual(golisopod.spread.total_sp, 66)

        # 5. Verify unrevealed bench Pokémon (Farigiraf, Aegislash, Umbreon) have complete 66-SP sets
        for bench_name in ("Farigiraf", "Aegislash", "Umbreon"):
            bench_mon = battle.trainer_2.get_pokemon(bench_name)
            self.assertIsNotNone(bench_mon)
            self.assertEqual(len(bench_mon.moves), 4)
            self.assertIsNotNone(bench_mon.item)
            self.assertIsNotNone(bench_mon.ability)
            self.assertIsNotNone(bench_mon.nature)
            self.assertEqual(bench_mon.spread.total_sp, 66)

        aegislash = battle.trainer_2.get_pokemon("Aegislash")
        self.assertIn("King's Shield", aegislash.moves)  # Normalized straight apostrophe!

    def test_infer_bo3_ots_spreads(self) -> None:
        """Verify Bo3 OTS inference preserves exact OTS fields while assigning 66-SP spreads."""
        battle = parse_showdown_chat_log(self.bo3_chat_log, pov_trainer="ssooner")
        report = self.inferencer.infer_battle(battle)

        self.assertEqual(len(report.primary_sets), 6)
        for sp_name, mon in battle.trainer_2.pokemon_sets.items():
            self.assertEqual(mon.spread.total_sp, 66)
            self.assertEqual(len(mon.moves), 4)

        sneasler = battle.trainer_2.get_pokemon("Sneasler")
        self.assertEqual(sneasler.item, "Focus Sash")
        self.assertEqual(sneasler.ability, "Poison Touch")
        self.assertEqual(sneasler.nature, "Jolly")
        self.assertEqual(sneasler.spread.atk, 32)
        self.assertEqual(sneasler.spread.spe, 32)


if __name__ == "__main__":
    unittest.main()
