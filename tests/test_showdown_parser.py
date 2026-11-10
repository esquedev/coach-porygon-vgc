# -*- coding: utf-8 -*-
"""Comprehensive tests for Universal Showdown Battle & Team Parser under Regulation M-C."""

import sys
import unittest
from pathlib import Path

# Resolve to repo root and include src/ in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from engine.parser import (
        DamageObservation,
        ParsedBattle,
        ParsedPokemon,
        ParsedTeam,
        SpeedObservation,
        StatSpread,
        get_move_priority,
        parse_showdown_chat_log,
        parse_showdown_paste,
    )
except ImportError:
    from src.engine.parser import (
        DamageObservation,
        ParsedBattle,
        ParsedPokemon,
        ParsedTeam,
        SpeedObservation,
        StatSpread,
        get_move_priority,
        parse_showdown_chat_log,
        parse_showdown_paste,
    )


class TestShowdownParser(unittest.TestCase):
    """Test suite validating Showdown paste and chat log parsing."""

    def setUp(self):
        self.user_paste = """
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

        self.bo1_chat_log = """
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
Lupiticus's rating: 1000 → 1050
(+50 for winning)
khoihandsome's rating: 1087 → 1058
(-29 for losing)
"""

        self.bo3_chat_log = """
☆ssooner and ☆lucillajade joined
ssooner
lucillajade
Game 2 of [a best-of-3](https://play.pokemonshowdown.com/game-bestof3-gen9championsvgc2026regmcbo3-2711791290)
Format:
[Gen 9 Champions] VGC 2026 Reg M-C (Bo3)
Rated battle
Species Clause: Limit one of each Pokemon
Item Clause: Limit 1 of each item
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
Battle timer is ON: inactive players will automatically lose when time's up. (requested by ssooner)
QueerCrocodile joined
ssooner has 60 seconds left.
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
ssooner's rating: 1122 → 1150
(+28 for winning)
lucillajade's rating: 1163 → 1135
(-28 for losing)
"""

    def test_parse_showdown_paste(self):
        """Test exact team paste parsing with 66-SP Reg M-C verification."""
        team = parse_showdown_paste(self.user_paste)
        self.assertEqual(len(team), 6)

        # 1. Charizard
        chz = team["Charizard"]
        self.assertEqual(chz.species, "Charizard")
        self.assertEqual(chz.item, "Charizardite Y")
        self.assertEqual(chz.mega_stone, "Charizardite Y")
        self.assertEqual(chz.ability, "Blaze")
        self.assertEqual(chz.nature, "Timid")
        self.assertEqual(chz.spread.hp, 2)
        self.assertEqual(chz.spread.def_, 12)
        self.assertEqual(chz.spread.spa, 28)
        self.assertEqual(chz.spread.spe, 24)
        self.assertEqual(chz.spread.total_sp, 66)
        self.assertEqual(len(chz.moves), 4)

        # 2. Raichu
        rai = team["Raichu"]
        self.assertEqual(rai.item, "Raichunite X")
        self.assertEqual(rai.mega_stone, "Raichunite X")
        self.assertEqual(rai.spread.hp, 10)
        self.assertEqual(rai.spread.atk, 30)
        self.assertEqual(rai.spread.spe, 26)
        self.assertEqual(rai.spread.total_sp, 66)

        # 3. Garchomp
        gar = team["Garchomp"]
        self.assertEqual(gar.item, "Life Orb")
        self.assertEqual(gar.spread.total_sp, 66)
        self.assertEqual(gar.spread.atk, 32)
        self.assertEqual(gar.spread.spe, 32)

        # 4. Grimmsnarl
        grim = team["Grimmsnarl"]
        self.assertEqual(grim.item, "Light Clay")
        self.assertEqual(grim.spread.total_sp, 66)
        self.assertEqual(grim.spread.hp, 32)
        self.assertEqual(grim.spread.def_, 16)
        self.assertEqual(grim.spread.spd, 15)
        self.assertEqual(grim.spread.spe, 3)

        # 5. Kingambit
        gam = team["Kingambit"]
        self.assertEqual(gam.item, "Focus Sash")
        self.assertEqual(gam.spread.total_sp, 66)

        # 6. Milotic
        mil = team["Milotic"]
        self.assertEqual(mil.item, "Sitrus Berry")
        self.assertEqual(mil.spread.total_sp, 66)
        self.assertEqual(mil.spread.hp, 32)
        self.assertEqual(mil.spread.def_, 6)
        self.assertEqual(mil.spread.spa, 15)
        self.assertEqual(mil.spread.spe, 13)

    def test_parse_bo1_chat_log(self):
        """Test parsing of Bo1 chat log with active leads, megas, and constraints."""
        battle = parse_showdown_chat_log(self.bo1_chat_log, pov_trainer="Lupiticus")

        # Identity validation: trainer_1 and trainer_2
        self.assertEqual(battle.trainer_1.trainer_name, "Lupiticus")
        self.assertEqual(battle.trainer_2.trainer_name, "khoihandsome")

        # Team preview (6 species each)
        self.assertEqual(len(battle.trainer_1.team_preview), 6)
        self.assertIn("Charizard", battle.trainer_1.team_preview)
        self.assertIn("Arcanine-Hisui", battle.trainer_1.team_preview)
        self.assertEqual(len(battle.trainer_2.team_preview), 6)
        self.assertIn("Starmie", battle.trainer_2.team_preview)
        self.assertIn("Rillaboom", battle.trainer_2.team_preview)

        # Leads
        self.assertEqual(battle.trainer_1.leads, ("Charizard", "Arcanine-Hisui"))
        self.assertEqual(battle.trainer_2.leads, ("Starmie", "Rillaboom"))

        # Battle roster (brought to match)
        self.assertIn("Charizard", battle.trainer_1.battle_roster)
        self.assertIn("Arcanine-Hisui", battle.trainer_1.battle_roster)
        self.assertIn("Kingambit", battle.trainer_1.battle_roster)  # Dragged out!
        self.assertIn("Starmie", battle.trainer_2.battle_roster)
        self.assertIn("Rillaboom", battle.trainer_2.battle_roster)
        self.assertIn("Golisopod", battle.trainer_2.battle_roster)

        # Mega Evolution tracking
        starmie = battle.trainer_2.get_pokemon("Starmie")
        self.assertIsNotNone(starmie)
        self.assertTrue(starmie.is_mega)
        self.assertEqual(starmie.mega_stone, "Starminite")

        charizard = battle.trainer_1.get_pokemon("Charizard")
        self.assertIsNotNone(charizard)
        self.assertTrue(charizard.is_mega)
        self.assertEqual(charizard.mega_stone, "Charizardite Y")
        self.assertEqual(charizard.ability, "Drought")

        # Ability and item triggers
        rilla = battle.trainer_2.get_pokemon("Rillaboom")
        self.assertEqual(rilla.ability, "Grassy Surge")
        golis = battle.trainer_2.get_pokemon("Golisopod")
        self.assertEqual(golis.item, "Red Card")

        # Speed Observations (same-priority order)
        self.assertTrue(len(battle.speed_observations) >= 3)
        # Turn 1: Charizard Protect (+4) before Arcanine Protect (+4)
        turn1_protect = [o for o in battle.speed_observations if o.turn == 1 and o.priority == 4]
        self.assertEqual(len(turn1_protect), 1)
        self.assertEqual(turn1_protect[0].faster_mon, "Charizard")
        self.assertEqual(turn1_protect[0].slower_mon, "Arcanine")

        # Turn 1: Starmie Minimize (0) before Rillaboom Swords Dance (0)
        turn1_prio0 = [o for o in battle.speed_observations if o.turn == 1 and o.priority == 0]
        self.assertEqual(len(turn1_prio0), 1)
        self.assertEqual(turn1_prio0[0].faster_mon, "Starmie")
        self.assertEqual(turn1_prio0[0].slower_mon, "Rillaboom")

        # Damage Observations
        self.assertTrue(len(battle.damage_observations) >= 4)
        # Flare Blitz 100% on Rillaboom
        flare_blitz_obs = [o for o in battle.damage_observations if o.move == "Flare Blitz"]
        self.assertEqual(len(flare_blitz_obs), 1)
        self.assertEqual(flare_blitz_obs[0].damage_pct, 100.0)
        self.assertEqual(flare_blitz_obs[0].defender, "Rillaboom")

        # Winner & Forfeit
        self.assertTrue(battle.forfeit)
        self.assertEqual(battle.winner, "Lupiticus")
        self.assertEqual(battle.trainer_1_rating, (1000, 1050))
        self.assertEqual(battle.trainer_2_rating, (1087, 1058))

    def test_parse_bo3_chat_log_with_ots(self):
        """Test parsing Bo3 chat log with Open Team Sheets and multi-hit attack."""
        battle = parse_showdown_chat_log(self.bo3_chat_log, pov_trainer="ssooner")

        self.assertTrue(battle.is_bo3)
        self.assertEqual(battle.game_number, 2)
        self.assertEqual(battle.trainer_1.trainer_name, "ssooner")
        self.assertEqual(battle.trainer_2.trainer_name, "lucillajade")

        # Check that OTS sets were fully ingested
        self.assertIn("Metagross", battle.trainer_1.pokemon_sets)
        self.assertIn("Staraptor", battle.trainer_1.pokemon_sets)
        staraptor = battle.trainer_1.pokemon_sets["Staraptor"]
        self.assertEqual(staraptor.item, "Staraptite")
        self.assertEqual(staraptor.ability, "Intimidate")
        self.assertEqual(staraptor.nature, "Jolly")
        self.assertIn("Dual Wingbeat", staraptor.moves)

        # Check Opponent OTS sets
        self.assertIn("Sneasler", battle.trainer_2.pokemon_sets)
        sneasler = battle.trainer_2.pokemon_sets["Sneasler"]
        self.assertEqual(sneasler.item, "Focus Sash")
        self.assertEqual(sneasler.ability, "Poison Touch")

        # Check leads
        self.assertEqual(battle.trainer_1.leads, ("Staraptor", "Whimsicott"))
        self.assertEqual(battle.trainer_2.leads, ("Basculegion-M", "Sneasler"))

        # Turn 1 Multi-hit Damage
        wingbeat_obs = [o for o in battle.damage_observations if o.move == "Dual Wingbeat"]
        self.assertEqual(len(wingbeat_obs), 2)
        self.assertEqual(wingbeat_obs[0].damage_pct, 63.0)
        self.assertEqual(wingbeat_obs[1].damage_pct, 37.0)

        # Sneasler fainted
        self.assertTrue(sneasler.fainted)

        # Outcome
        self.assertTrue(battle.forfeit)
        self.assertEqual(battle.winner, "ssooner")
        self.assertEqual(battle.trainer_1_rating, (1122, 1150))
        self.assertEqual(battle.trainer_2_rating, (1163, 1135))

    def test_cartridge_ev_conversion(self):
        """Test conversion of standard cartridge EVs (>32) to Regulation M-C SPs."""
        ev_dict = {"hp": 4, "atk": 252, "spe": 252}
        spread = StatSpread.from_evs_or_sp(ev_dict)
        self.assertEqual(spread.hp, 1)
        self.assertEqual(spread.atk, 32)
        self.assertEqual(spread.spe, 32)
        self.assertEqual(spread.def_, 0)
        self.assertEqual(spread.total_sp, 65)

    def test_user_paste_overlay(self):
        """Test that user_team_paste overrides trainer_1 sets in chat log."""
        battle = parse_showdown_chat_log(
            self.bo1_chat_log,
            pov_trainer="Lupiticus",
            user_team_paste=self.user_paste,
        )
        chz = battle.trainer_1.get_pokemon("Charizard")
        self.assertIsNotNone(chz)
        self.assertEqual(chz.spread.total_sp, 66)
        self.assertEqual(chz.spread.spa, 28)
        self.assertEqual(chz.spread.spe, 24)
        self.assertIn("Scorching Sands", chz.moves)


if __name__ == "__main__":
    unittest.main()
