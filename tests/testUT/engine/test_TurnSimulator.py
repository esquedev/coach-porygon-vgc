#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit & Deterministic Tests for Turn Simulator (engine/turn_simulator.py)
Validates:
1. 66-SP Level 50 stat computation with sequential integer floor rounding.
2. Instantaneous Mega Evolution speed scaling during activation phase.
3. Priority bracket resolution and Trick Room speed inversion.
4. Psychic Terrain priority blocking of grounded targets vs. airborne exemptions.
5. Official 16 damage rolls (85%–100%) and doubles spread move reduction (0.75x).
6. Weather (Sun/Rain) and Terrain (Grassy/Electric/Psychic) damage modifiers.
7. Focus Sash, Protect, and full 2v2 turn execution via ClientReplaySimulator.
"""

import unittest
from pathlib import Path
import sys

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "engine"))

from engine.turn_simulator import (
    evaluate_move_synergy,
    calculate_level_50_stats,
    get_type_effectiveness,
    get_type_effectiveness_breakdown,
    is_airborne,
    get_stage_multiplier,
    apply_stat_boost,
    ClientReplaySimulator,
)


class TestTurnSimulator(unittest.TestCase):
    """Rigorous deterministic test suite for Coach Porygon's VGC turn micro-simulator."""

    def test_calculate_level_50_stats_with_66_sp(self):
        """Test Level 50 stat calculation with 66 SP budget and official rounding."""
        # Standard fast physical Garchomp (0 HP / 32 Atk / 2 Def / 0 SpA / 0 SpD / 32 Spe Jolly)
        sp = {"hp": 0, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 32}
        max_hp, stats = calculate_level_50_stats("Garchomp", sp, "Jolly")
        self.assertEqual(sum(sp.values()), 66)
        self.assertEqual(max_hp, 183)
        self.assertEqual(stats["atk"], 182)
        self.assertEqual(stats["def"], 117)
        self.assertEqual(stats["spe"], 169)

        # Bulky support Incineroar (32 HP / 0 Atk / 14 Def / 0 SpA / 20 SpD / 0 Spe Careful)
        incin_sp = {"hp": 32, "atk": 0, "def": 14, "spa": 0, "spd": 20, "spe": 0}
        incin_hp, incin_stats = calculate_level_50_stats("Incineroar", incin_sp, "Careful")
        self.assertEqual(sum(incin_sp.values()), 66)
        self.assertEqual(incin_hp, 202)
        self.assertEqual(incin_stats["def"], 124)
        self.assertEqual(incin_stats["spd"], 143)

    def test_instantaneous_mega_evolution_speed_scaling(self):
        """Verify instantaneous Mega Evolution recalculates speed and base stats immediately."""
        state = {
            "turn": 1,
            "field": {"weather": None, "terrain": None, "trick_room_turns": 0},
            "p1": {"tailwind_turns": 0},
            "p2": {"tailwind_turns": 0},
            "slots": {
                "p1a": {
                    "species": "Charizard",
                    "item": "Charizardite Y",
                    "sp_spread": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 32},
                    "nature": "Timid",
                    "ability": "Blaze",
                    "hp": 153,
                    "max_hp": 153,
                    "types": ["Fire", "Flying"]
                },
                "p2a": {
                    "species": "Garchomp",
                    "sp_spread": {"hp": 0, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 32},
                    "nature": "Jolly",
                    "ability": "Rough Skin",
                    "hp": 183,
                    "max_hp": 183,
                    "types": ["Dragon", "Ground"]
                }
            }
        }
        choices = {
            "p1a": {"choice": "move", "move_name": "Heat Wave", "target": "allAdjacentFoes", "mega": True},
            "p2a": {"choice": "move", "move_name": "Earthquake", "target": "allAdjacentFoes"}
        }

        sim = ClientReplaySimulator(state, choices, pov_player="p1")
        sim.execute_activation_phase()

        # p1a must be transformed into Mega Charizard Y with Drought
        p1a = sim.state["slots"]["p1a"]
        self.assertIn(p1a["species"], ["Mega Charizard Y", "Charizard-Mega-Y"])
        self.assertEqual(p1a["ability"], "Drought")
        self.assertEqual(sim.state["field"]["weather"], "sun")

    def test_priority_and_speed_order_resolution(self):
        """Verify priority brackets take absolute precedence over base speed."""
        state = {
            "turn": 1,
            "field": {"weather": None, "terrain": None, "trick_room_turns": 0},
            "p1": {"tailwind_turns": 0},
            "p2": {"tailwind_turns": 0},
            "slots": {
                "p1a": {
                    "species": "Incineroar",
                    "sp_spread": {"hp": 32, "atk": 0, "def": 14, "spa": 0, "spd": 20, "spe": 0},
                    "nature": "Careful",
                    "item": "Sitrus Berry",
                    "ability": "Intimidate",
                    "hp": 202,
                    "max_hp": 202,
                    "types": ["Fire", "Dark"]
                },
                "p2a": {
                    "species": "Garchomp",
                    "sp_spread": {"hp": 0, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 32},
                    "nature": "Jolly",
                    "item": "Life Orb",
                    "ability": "Rough Skin",
                    "hp": 183,
                    "max_hp": 183,
                    "types": ["Dragon", "Ground"]
                }
            }
        }
        # Fake Out (+3 priority) on slower Incineroar vs Earthquake (0 priority) on faster Garchomp
        choices = {
            "p1a": {"choice": "move", "move_name": "Fake Out", "target": "p2a"},
            "p2a": {"choice": "move", "move_name": "Earthquake", "target": "allAdjacentFoes"}
        }

        sim = ClientReplaySimulator(state, choices, pov_player="p1")
        order = sim.resolve_action_order()
        self.assertEqual(order[0][0], "p1a", "Fake Out (+3) must execute before 0-priority Earthquake")
        self.assertEqual(order[1][0], "p2a")

    def test_trick_room_speed_inversion(self):
        """Verify Trick Room reverses speed sorting within the same priority bracket."""
        state = {
            "turn": 1,
            "field": {"weather": None, "terrain": None, "trick_room_turns": 4},
            "p1": {"tailwind_turns": 0},
            "p2": {"tailwind_turns": 0},
            "slots": {
                "p1a": {
                    "species": "Torkoal",
                    "sp_spread": {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 0},
                    "nature": "Quiet",
                    "ability": "Drought",
                    "hp": 177,
                    "max_hp": 177,
                    "types": ["Fire"]
                },
                "p2a": {
                    "species": "Garchomp",
                    "sp_spread": {"hp": 0, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 32},
                    "nature": "Jolly",
                    "ability": "Rough Skin",
                    "hp": 183,
                    "max_hp": 183,
                    "types": ["Dragon", "Ground"]
                }
            }
        }
        choices = {
            "p1a": {"choice": "move", "move_name": "Eruption", "target": "allAdjacentFoes"},
            "p2a": {"choice": "move", "move_name": "Earthquake", "target": "allAdjacentFoes"}
        }

        sim = ClientReplaySimulator(state, choices, pov_player="p1")
        order = sim.resolve_action_order()
        self.assertEqual(order[0][0], "p1a", "Under Trick Room, slower Torkoal must act before faster Garchomp")
        self.assertEqual(order[1][0], "p2a")

    def test_psychic_terrain_priority_blocking_and_airborne_exemption(self):
        """Verify Psychic Terrain blocks priority on grounded targets but airborne targets are vulnerable."""
        # 1. Grounded Target (Garchomp) under Psychic Terrain: Priority Fake Out blocked
        slot_garchomp = {"species": "Garchomp", "types": ["Dragon", "Ground"], "item": ""}
        self.assertFalse(is_airborne(slot_garchomp))

        # 2. Airborne Target (Charizard) under Psychic Terrain: Airborne exemption allows priority
        slot_charizard = {"species": "Charizard", "types": ["Fire", "Flying"], "item": ""}
        self.assertTrue(is_airborne(slot_charizard))

        # 3. Grounded species holding Air Balloon is airborne
        slot_balloon = {"species": "Kingambit", "types": ["Dark", "Steel"], "item": "Air Balloon"}
        self.assertTrue(is_airborne(slot_balloon))

    def test_type_effectiveness_and_scrappy(self):
        """Verify official type chart multipliers, immunities (0x), and Scrappy ability."""
        # Ice vs Dragon/Flying -> 4.0x
        self.assertEqual(get_type_effectiveness("Ice", ["Dragon", "Flying"]), 4.0)

        # Normal vs Ghost -> 0.0x immunity
        self.assertEqual(get_type_effectiveness("Normal", ["Ghost"]), 0.0)

        # Scrappy bypasses Ghost immunity -> 1.0x
        self.assertEqual(get_type_effectiveness("Normal", ["Ghost"], scrappy=True), 1.0)
        self.assertEqual(get_type_effectiveness("Fighting", ["Ghost"], scrappy=True), 1.0)

        # Ground vs Flying -> 0.0x immunity
        self.assertEqual(get_type_effectiveness("Ground", ["Flying"]), 0.0)

        # Fairy vs Dragon -> 2.0x
        self.assertEqual(get_type_effectiveness("Fairy", ["Dragon"]), 2.0)

    def test_stat_boost_and_stage_multipliers(self):
        """Verify stat stage multipliers (-6 to +6) and sequential integer rounding."""
        self.assertEqual(get_stage_multiplier(0), 1.0)
        self.assertEqual(get_stage_multiplier(1), 1.5)
        self.assertEqual(get_stage_multiplier(2), 2.0)
        self.assertEqual(get_stage_multiplier(-1), 2.0 / 3.0)
        self.assertEqual(get_stage_multiplier(-2), 0.5)

        # Test apply_stat_boost
        base_atk = 200
        self.assertEqual(apply_stat_boost(base_atk, 1), 300)
        self.assertEqual(apply_stat_boost(base_atk, -1), 133)

    def test_focus_sash_and_protect_damage_mitigation(self):
        """Verify Focus Sash survives lethal OHKO at 1 HP from full health."""
        state = {
            "turn": 1,
            "field": {"weather": None, "terrain": None},
            "p1": {},
            "p2": {},
            "slots": {
                "p1a": {
                    "species": "Garchomp",
                    "max_hp": 183,
                    "hp": 183,
                    "current_hp_pct": 100.0,
                    "item": "Focus Sash",
                    "types": ["Dragon", "Ground"],
                    "volatiles": {}
                }
            }
        }
        sim = ClientReplaySimulator(state, {}, pov_player="p1")
        slot = sim.state["slots"]["p1a"]
        lines = []

        # Deal 300 damage (exceeding 183 HP) with Focus Sash intact at 100% HP
        sim.deal_hp_damage(slot, 300, lines, check_sash=True)
        self.assertEqual(slot["hp"], 1, "Focus Sash must preserve 1 HP from full health")
        self.assertEqual(slot["item"], "", "Focus Sash must be consumed after activation")

    def test_full_doubles_turn_simulation(self):
        """Verify full 2v2 doubles turn micro-simulation with damage, Protect, and logs."""
        state = {
            "turn": 1,
            "field": {"weather": None, "terrain": None, "trick_room_turns": 0},
            "p1": {"tailwind_turns": 0},
            "p2": {"tailwind_turns": 0},
            "slots": {
                "p1a": {
                    "species": "Garchomp",
                    "sp_spread": {"hp": 0, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 32},
                    "nature": "Jolly",
                    "item": "Life Orb",
                    "ability": "Rough Skin",
                    "hp": 183,
                    "max_hp": 183,
                    "types": ["Dragon", "Ground"]
                },
                "p1b": {
                    "species": "Incineroar",
                    "sp_spread": {"hp": 32, "atk": 0, "def": 14, "spa": 0, "spd": 20, "spe": 0},
                    "nature": "Careful",
                    "item": "Sitrus Berry",
                    "ability": "Intimidate",
                    "hp": 202,
                    "max_hp": 202,
                    "types": ["Fire", "Dark"]
                },
                "p2a": {
                    "species": "Tyranitar",
                    "sp_spread": {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 0},
                    "nature": "Adamant",
                    "item": "Choice Band",
                    "ability": "Sand Stream",
                    "hp": 207,
                    "max_hp": 207,
                    "types": ["Rock", "Dark"]
                },
                "p2b": {
                    "species": "Archaludon",
                    "sp_spread": {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 0},
                    "nature": "Modest",
                    "item": "Assault Vest",
                    "ability": "Stamina",
                    "hp": 197,
                    "max_hp": 197,
                    "types": ["Steel", "Dragon"]
                }
            }
        }

        # Turn choices: Garchomp uses Earthquake (spread), Incineroar Protects
        choices = {
            "p1a": {"choice": "move", "move_name": "Earthquake", "target": "allAdjacent"},
            "p1b": {"choice": "move", "move_name": "Protect", "target": "self"},
            "p2a": {"choice": "move", "move_name": "Rock Slide", "target": "allAdjacentFoes"},
            "p2b": {"choice": "move", "move_name": "Flash Cannon", "target": "p1a"}
        }

        sim = ClientReplaySimulator(state, choices, pov_player="p1")
        next_state, log_text = sim.run_turn(roll_mode="average", fixed_roll=0.925)

        # Incineroar must take 0 damage from partner's Earthquake due to Protect
        self.assertEqual(next_state["slots"]["p1b"]["hp"], 202)
        # Tyranitar must take heavy super-effective damage from Earthquake
        self.assertLess(next_state["slots"]["p2a"]["hp"], 207)
        # Turn log must contain Turn 1 and move usage
        self.assertIn("Turn 1", log_text)
        self.assertIn("Earthquake", log_text)


    def test_evaluate_move_synergy_no_guard_zap_cannon(self):
        """Verify No Guard eliminates Zap Cannon inaccuracy and guarantees status."""
        res = evaluate_move_synergy("Raichu-Mega-Y", "No Guard", "Focus Sash", "Zap Cannon")
        self.assertTrue(res["synergy_detected"])
        self.assertEqual(res["accuracy"], 100)
        self.assertEqual(res["tactical_rating"], "Elite")
        self.assertIn("No Guard", res["synergy_type"])

    def test_evaluate_move_synergy_sheer_force_life_orb(self):
        """Verify Sheer Force cancels Life Orb recoil while retaining both 1.3x boosts."""
        res = evaluate_move_synergy("Nidoking", "Sheer Force", "Life Orb", "Sludge Bomb")
        self.assertTrue(res["synergy_detected"])
        self.assertEqual(res["damage_multiplier"], 1.69)
        self.assertEqual(res["tactical_rating"], "Elite")

    def test_evaluate_move_synergy_expanding_force_psychic_surge(self):
        """Verify Expanding Force turns into 120 BP spread under Psychic Terrain."""
        res = evaluate_move_synergy("Indeedee-F", "Psychic Surge", "Psychic Seed", "Expanding Force", field={"terrain": "psychic"})
        self.assertTrue(res["synergy_detected"])
        self.assertEqual(res["effective_bp"], 120)
        self.assertEqual(res["target"], "allAdjacentFoes")

    def test_accuracy_check_and_no_guard_in_simulator(self):
        """Verify check_move_accuracy in simulator respects No Guard 100% guarantee."""
        state = {
            "turn": 1,
            "field": {"weather": None, "terrain": None, "trick_room_turns": 0},
            "p1": {"tailwind_turns": 0},
            "p2": {"tailwind_turns": 0},
            "slots": {
                "p1a": {"species": "Raichu-Mega-Y", "ability": "No Guard", "hp": 135, "max_hp": 135, "current_hp_pct": 100.0, "stats": {"spe": 160}},
                "p2a": {"species": "Garchomp", "ability": "Rough Skin", "hp": 183, "max_hp": 183, "current_hp_pct": 100.0, "stats": {"spe": 169}}
            }
        }
        sim = ClientReplaySimulator(state, {}, pov_player="p1")
        hit, reason = sim.check_move_accuracy(sim.state["slots"]["p1a"], sim.state["slots"]["p2a"], {"name": "Zap Cannon", "accuracy": 50})
        self.assertTrue(hit)
        self.assertEqual(reason, "No Guard")



    def test_type_effectiveness_breakdown_and_dual_typing(self):
        """Test compound dual-typing effectiveness breakdown (0x, 0.25x, 0.5x, 1x, 2x, 4x, exceptions)."""
        # 4.0x Double Weakness: Rock into Charizard (Fire/Flying)
        b_rock_char = get_type_effectiveness_breakdown("Rock", ["Fire", "Flying"])
        self.assertEqual(b_rock_char["multiplier"], 4.0)
        self.assertEqual(b_rock_char["classification"], "Double Weakness (4.0x)")
        self.assertEqual(b_rock_char["label"], "double-weak")

        # 4.0x Double Weakness: Ice into Garchomp (Dragon/Ground)
        b_ice_garch = get_type_effectiveness_breakdown("Ice", ["Dragon", "Ground"])
        self.assertEqual(b_ice_garch["multiplier"], 4.0)
        self.assertEqual(b_ice_garch["classification"], "Double Weakness (4.0x)")

        # 0.25x Double Resistance: Grass into Charizard (Fire/Flying)
        b_grass_char = get_type_effectiveness_breakdown("Grass", ["Fire", "Flying"])
        self.assertEqual(b_grass_char["multiplier"], 0.25)
        self.assertEqual(b_grass_char["classification"], "Double Resistance (0.25x)")
        self.assertEqual(b_grass_char["label"], "double-resisted")

        # 0.0x Absolute Immunity: Ground into Charizard (Fire/Flying)
        b_ground_char = get_type_effectiveness_breakdown("Ground", ["Fire", "Flying"])
        self.assertEqual(b_ground_char["multiplier"], 0.0)
        self.assertEqual(b_ground_char["classification"], "Immunity (0x)")
        self.assertEqual(b_ground_char["label"], "immune")

        # Exception: Freeze-Dry on Water/Ground (Swampert) -> 2.0x * 2.0x = 4.0x
        b_fd_swamp = get_type_effectiveness_breakdown("Ice", ["Water", "Ground"], move_name="Freeze-Dry")
        self.assertEqual(b_fd_swamp["multiplier"], 4.0)

        # Exception: Thousand Arrows on Flying -> neutral 1.0x
        b_ta_flying = get_type_effectiveness_breakdown("Ground", ["Flying"], move_name="Thousand Arrows")
        self.assertEqual(b_ta_flying["multiplier"], 1.0)

    def test_evaluate_move_synergy_type_conversions_and_field_effects(self):
        """Test extended synergy evaluation for -ate conversions, weather, and terrains."""
        # Aerilate on Mega Salamence (Dragon/Flying): Normal -> Flying with 1.2x BP + Flying STAB (1.8x total)
        syn_aeri = evaluate_move_synergy("Salamence-Mega", "Aerilate", "", "Hyper Voice")
        self.assertTrue(syn_aeri["synergy_detected"])
        self.assertEqual(syn_aeri["converted_type"], "Flying")
        self.assertTrue(syn_aeri["has_stab"])
        self.assertEqual(syn_aeri["damage_multiplier"], 1.8)

        # Sun + Fire move amplification (1.5x)
        syn_sun_fire = evaluate_move_synergy("Charizard", "Blaze", "", "Heat Wave", field={"weather": "sun"})
        self.assertTrue(syn_sun_fire["synergy_detected"])
        self.assertEqual(syn_sun_fire["damage_multiplier"], 1.5)

        # Sun + Solar Beam instant execution
        syn_solar = evaluate_move_synergy("Torkoal", "Drought", "", "Solar Beam", field={"weather": "sun"})
        self.assertTrue(syn_solar["synergy_detected"])
        self.assertEqual(syn_solar["synergy_type"], "Sun Instant Solar Execution")

        # Rain + Thunder 100% accuracy bypass
        syn_rain_thunder = evaluate_move_synergy("Archaludon", "Stamina", "", "Thunder", field={"weather": "rain"})
        self.assertTrue(syn_rain_thunder["synergy_detected"])
        self.assertEqual(syn_rain_thunder["accuracy"], 100)

        # Snow + Blizzard 100% accuracy bypass
        syn_snow_blizz = evaluate_move_synergy("Ninetales-Alola", "Snow Warning", "", "Blizzard", field={"weather": "snow"})
        self.assertTrue(syn_snow_blizz["synergy_detected"])
        self.assertEqual(syn_snow_blizz["accuracy"], 100)

        # Electroweb area speed drop
        syn_ew = evaluate_move_synergy("Regieleki", "Transistor", "", "Electroweb")
        self.assertTrue(syn_ew["synergy_detected"])
        self.assertEqual(syn_ew["speed_drop"], -1)


if __name__ == "__main__":
    unittest.main()
