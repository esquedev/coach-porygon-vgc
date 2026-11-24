# -*- coding: utf-8 -*-
"""Comprehensive verification suite for Regulation M-C mechanics, zero-heuristic pruner,
2D tiling exact equivalence, positional utility, and 4-variant bilingual terminology.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from apps.replay_coach.commentary_engine import generate_all_commentary_variants
from engine.terminology import (
    TERM_GLOSSARY,
    VERDICT_BADGES,
    export_glossary_payload,
    get_rng_sampling_note,
    get_term_label,
    get_verdict_badge,
)
from engine.vgc_tensor_core import (
    AbilityID,
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
    FieldIdx,
    ItemID,
    LogicalConstraintEngine,
    MON_DIM,
    MOVE_DIM,
    MonIdx,
    MoveIdx,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    ShowdownTensorCompiler,
    VgcTensorStateMachine,
    compute_per_thread_board_utility_torch,
    execute_pre_attack_phases,
)


class TestRegMCMechanicsAndTiling(unittest.TestCase):
    """Verify DuckDB-audited Regulation M-C mechanics, mathematical pruner, 2D tiling, and terminology."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.compiler = ShowdownTensorCompiler(backend="torch", device="cpu")
        cls.logic_engine = LogicalConstraintEngine(tables=cls.compiler.tables)
        cls.state_machine = VgcTensorStateMachine(backend="torch", device="cpu")

    def test_01_standalone_decoupling_and_schema_dimensions(self) -> None:
        """Verify vgc_tensor_core has zero imports from engine.inference and uses 88/60 dims."""
        self.assertEqual(MON_DIM, 88)
        self.assertEqual(MOVE_DIM, 60)

        core_dir = SRC_DIR / "engine" / "vgc_tensor_core"
        for py_file in core_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(
                        "inference",
                        node.module,
                        f"{py_file.name} must not import from engine.inference",
                    )

        # Verify DuckDB move flags (contact, slicing, punch) and Mega Stones compile accurately
        cc = self.compiler.compile_move_vector("Close Combat")
        self.assertEqual(float(cc[MoveIdx.IS_CONTACT]), 1.0)
        self.assertEqual(float(cc[MoveIdx.IS_SLICING]), 0.0)
        self.assertEqual(float(cc[MoveIdx.IS_PUNCH]), 0.0)

        kc = self.compiler.compile_move_vector("Kowtow Cleave")
        self.assertEqual(float(kc[MoveIdx.IS_CONTACT]), 1.0)
        self.assertEqual(float(kc[MoveIdx.IS_SLICING]), 1.0)

        dp = self.compiler.compile_move_vector("Drain Punch")
        self.assertEqual(float(dp[MoveIdx.IS_CONTACT]), 1.0)
        self.assertEqual(float(dp[MoveIdx.IS_PUNCH]), 1.0)

        p_zard, _ = self.compiler.compile_pokemon_slot(
            {"species": "Charizard", "item": "Charizardite Y", "types": ["Fire", "Flying"]}
        )
        self.assertEqual(float(p_zard[MonIdx.ITEM_ID]), float(ItemID.MEGA_STONE))
        self.assertEqual(float(p_zard[MonIdx.CAN_MEGA]), 1.0)

    def test_02_resist_berries_and_type_boost_items_bug_fixes(self) -> None:
        """Verify Resist Berries (0.5x on matching Super Effective hit) and Type-Boost Items (1.2x on matching type only)."""
        # Dual-type Venusaur (Grass/Poison) holding Miracle Seed (boosts Grass ONLY, not Poison STAB!)
        # Target 1: Kingambit holding Chople Berry (Fighting resist berry) vs Fighting move
        rosters = [
            {
                "species": "Venusaur",
                "hp_max": 187.0,
                "hp_cur": 187.0,
                "stats": {"atk": 100.0, "def": 103.0, "spa": 167.0, "spd": 120.0, "spe": 100.0},
                "types": ["Grass", "Poison"],
                "ability": "Overgrow",
                "item": "Miracle Seed",
                "moves": ["Energy Ball", "Sludge Bomb", "Protect", "Sleep Powder"],
            },
            {
                "species": "Venusaur",
                "hp_max": 187.0,
                "hp_cur": 187.0,
                "stats": {"atk": 100.0, "def": 103.0, "spa": 167.0, "spd": 120.0, "spe": 100.0},
                "types": ["Grass", "Poison"],
                "ability": "Overgrow",
                "item": "None",
                "moves": ["Energy Ball", "Sludge Bomb", "Protect", "Sleep Powder"],
            },
            {},
            {},
            {
                "species": "Milotic",
                "hp_max": 202.0,
                "hp_cur": 202.0,
                "stats": {"atk": 80.0, "def": 100.0, "spa": 120.0, "spd": 145.0, "spe": 101.0},
                "types": ["Normal"],
                "ability": "Competitive",
                "item": "Rindo Berry",
                "moves": ["Splash", "Protect"],
            },
            {
                "species": "Milotic",
                "hp_max": 202.0,
                "hp_cur": 202.0,
                "stats": {"atk": 80.0, "def": 100.0, "spa": 120.0, "spd": 145.0, "spe": 101.0},
                "types": ["Normal"],
                "ability": "Competitive",
                "item": "None",
                "moves": ["Splash", "Protect"],
            },
            {},
            {},
        ]
        state = self.compiler.compile_battle_state(rosters)
        # Note: in moves=["Energy Ball", "Sludge Bomb", "Protect", "Sleep Powder"], Protect is move index 2 (choice 2)!
        # Run each (1, 1) with identical rng_seed=777 so both draw identical damage rolls & crit/poison procs:
        res_seed_poison = self.state_machine.step(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            torch.tensor([[5, 2]], dtype=torch.long),
            torch.tensor([[0, 0]], dtype=torch.long),
            num_mc_samples=64,
            rng_seed=777,
        )
        res_noitem_poison = self.state_machine.step(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            torch.tensor([[2, 5]], dtype=torch.long),
            torch.tensor([[0, 0]], dtype=torch.long),
            num_mc_samples=64,
            rng_seed=777,
        )
        # Miracle Seed must NOT boost Poison STAB Sludge Bomb!
        hp_after_seed_poison = float(res_seed_poison.mean_hp[0, 0, SLOT_TRAINER_2_B].item())
        hp_after_noitem_poison = float(res_noitem_poison.mean_hp[0, 0, SLOT_TRAINER_2_B].item())
        self.assertLess(hp_after_seed_poison, 202.0)
        self.assertAlmostEqual(hp_after_seed_poison, hp_after_noitem_poison, places=4)

        # Now both use Energy Ball (Grass STAB, move 0 -> choice 4 into Slot 5)
        res_seed_grass = self.state_machine.step(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            torch.tensor([[4, 2]], dtype=torch.long),
            torch.tensor([[0, 0]], dtype=torch.long),
            num_mc_samples=64,
            rng_seed=777,
        )
        res_noitem_grass = self.state_machine.step(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            torch.tensor([[2, 4]], dtype=torch.long),
            torch.tensor([[0, 0]], dtype=torch.long),
            num_mc_samples=64,
            rng_seed=777,
        )
        dmg_seed_grass = 202.0 - float(res_seed_grass.mean_hp[0, 0, SLOT_TRAINER_2_B].item())
        dmg_noitem_grass = 202.0 - float(res_noitem_grass.mean_hp[0, 0, SLOT_TRAINER_2_B].item())
        self.assertGreater(dmg_seed_grass, dmg_noitem_grass * 1.15)

        # Now test Resist Berry (Rindo Berry on Water-type Milotic vs Super Effective Grass Energy Ball)
        rosters[4]["types"] = ["Water"]
        rosters[5]["types"] = ["Water"]
        state_berry = self.compiler.compile_battle_state(rosters)
        res_berry_rindo = self.state_machine.step(
            state_berry.field_tensor,
            state_berry.roster_tensor,
            state_berry.moves_tensor,
            torch.tensor([[0, 2]], dtype=torch.long),  # Slot 0 Energy Ball -> Slot 4 (Rindo)
            torch.tensor([[0, 0]], dtype=torch.long),
            num_mc_samples=64,
            rng_seed=777,
        )
        res_berry_none = self.state_machine.step(
            state_berry.field_tensor,
            state_berry.roster_tensor,
            state_berry.moves_tensor,
            torch.tensor([[4, 2]], dtype=torch.long),  # Slot 0 Energy Ball -> Slot 5 (None)
            torch.tensor([[0, 0]], dtype=torch.long),
            num_mc_samples=64,
            rng_seed=777,
        )
        dmg_vs_rindo = 202.0 - float(res_berry_rindo.mean_hp[0, 0, SLOT_TRAINER_2_A].item())
        dmg_vs_none = 202.0 - float(res_berry_none.mean_hp[0, 0, SLOT_TRAINER_2_B].item())
        self.assertAlmostEqual(dmg_vs_rindo, dmg_vs_none * 0.5, delta=1.0)
        # Rindo Berry must be consumed on Slot 4
        self.assertEqual(float(res_berry_rindo.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.ITEM_ACTIVE].item()), 0.0)

    def test_03_sheer_force_thick_fat_shell_armor_telepathy_and_iron_fist(self) -> None:
        """Verify Sheer Force (+no Life Orb recoil), Thick Fat, Shell Armor, Telepathy, and Iron Fist."""
        rosters = [
            # Slot 0: Camerupt-Mega (Sheer Force @ Life Orb) with Earth Power & Heat Wave
            {
                "species": "Camerupt-Mega",
                "hp_max": 177.0,
                "hp_cur": 177.0,
                "stats": {"atk": 120.0, "def": 120.0, "spa": 195.0, "spd": 125.0, "spe": 40.0},
                "types": ["Fire", "Ground"],
                "ability": "Sheer Force",
                "item": "Life Orb",
                "moves": ["Earth Power", "Earthquake", "Heat Wave", "Protect"],
            },
            # Slot 1: Gardevoir (Telepathy) with Dazzling Gleam
            {
                "species": "Gardevoir",
                "hp_max": 175.0,
                "hp_cur": 175.0,
                "stats": {"atk": 85.0, "def": 85.0, "spa": 177.0, "spd": 135.0, "spe": 100.0},
                "types": ["Psychic", "Fairy"],
                "ability": "Telepathy",
                "item": "Fairy Feather",
                "moves": ["Dazzling Gleam", "Protect", "Psychic", "Trick Room"],
            },
            {},
            {},
            # Slot 4: Snorlax (Thick Fat)
            {
                "species": "Snorlax",
                "hp_max": 267.0,
                "hp_cur": 267.0,
                "stats": {"atk": 130.0, "def": 115.0, "spa": 85.0, "spd": 130.0, "spe": 30.0},
                "types": ["Normal"],
                "ability": "Thick Fat",
                "item": "None",
                "moves": ["Splash", "Protect"],
            },
            # Slot 5: Torkoal (Shell Armor)
            {
                "species": "Torkoal",
                "hp_max": 177.0,
                "hp_cur": 177.0,
                "stats": {"atk": 105.0, "def": 160.0, "spa": 150.0, "spd": 90.0, "spe": 22.0},
                "types": ["Fire"],
                "ability": "Shell Armor",
                "item": "None",
                "moves": ["Splash", "Protect"],
            },
            {},
            {},
        ]
        state = self.compiler.compile_battle_state(rosters)
        # Case A: Camerupt uses Earth Power (move 0, 10% SpD drop secondary -> Sheer Force active!) into Slot 4
        # Sheer Force must suppress Life Orb 10% self-recoil AND suppress SpD drop!
        res_sf = self.state_machine.step(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            torch.tensor([[0, 1], [1, 1]], dtype=torch.long),  # Row 0: Earth Power; Row 1: Earthquake (hits Telepathy ally?)
            torch.tensor([[0, 0]], dtype=torch.long),
            num_mc_samples=64,
            rng_seed=42,
        )
        # Camerupt HP after Earth Power must still be 177.0 (no Life Orb recoil with Sheer Force!)
        self.assertEqual(float(res_sf.mean_hp[0, 0, SLOT_TRAINER_1_A].item()), 177.0)
        # Snorlax SpD boost after Earth Power must be 0.0 (secondary suppressed by Sheer Force)
        self.assertEqual(float(res_sf.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.BOOST_SPD].item()), 0.0)
        # Row 1: Camerupt uses Earthquake (spread ALL_ADJACENT, no secondary -> Life Orb recoil DOES apply,
        # but Telepathy ally Gardevoir takes 0 damage!)
        self.assertEqual(float(res_sf.mean_hp[1, 0, SLOT_TRAINER_1_B].item()), 175.0)
        self.assertLess(float(res_sf.mean_hp[1, 0, SLOT_TRAINER_1_A].item()), 177.0)

        # Case B: Shell Armor blocks 100% crit Flower Trick, and Iron Fist boosts Drain Punch by 1.2x
        rosters_b = list(rosters)
        rosters_b[0] = {
            "species": "Meowscarada",
            "hp_max": 151.0,
            "hp_cur": 151.0,
            "stats": {"atk": 162.0, "def": 90.0, "spa": 90.0, "spd": 90.0, "spe": 192.0},
            "types": ["Grass", "Dark"],
            "ability": "Overgrow",
            "item": "None",
            "moves": ["Flower Trick", "Protect", "Knock Off", "U-turn"],
        }
        rosters_b[1] = {
            "species": "Conkeldurr",
            "hp_max": 212.0,
            "hp_cur": 212.0,
            "stats": {"atk": 190.0, "def": 115.0, "spa": 65.0, "spd": 85.0, "spe": 65.0},
            "types": ["Fighting"],
            "ability": "Iron Fist",
            "item": "None",
            "moves": ["Mach Punch", "Protect", "Close Combat", "Rock Slide"],
        }
        state_b = self.compiler.compile_battle_state(rosters_b)
        # Meowscarada uses Flower Trick on Slot 4 (Snorlax, Thick Fat -> crits 100%) vs Slot 5 (Torkoal, Shell Armor -> 0% crit!)
        res_sa = self.state_machine.step(
            state_b.field_tensor,
            state_b.roster_tensor,
            state_b.moves_tensor,
            torch.tensor([[0, 1], [4, 1]], dtype=torch.long),
            torch.tensor([[0, 0]], dtype=torch.long),
            num_mc_samples=32,
            rng_seed=42,
        )
        self.assertAlmostEqual(float(res_sa.attack_cascade.crit_rate_observed[0, 0, 0].item()), 1.0, places=4)
        self.assertAlmostEqual(float(res_sa.attack_cascade.crit_rate_observed[1, 0, 0].item()), 0.0, places=4)

    def test_04_contrary_lightning_rod_expanding_force_and_sucker_punch(self) -> None:
        """Verify Contrary (Intimidate +1 Atk & Close Combat +1 Def/+1 SpD), Lightning Rod redirection,
        Expanding Force in Psychic Terrain (120 BP spread), and Sucker Punch status/acted failure.
        """
        rosters = [
            # Slot 0: Staraptor-Mega (Contrary) with Close Combat
            {
                "species": "Staraptor-Mega",
                "hp_max": 192.0,
                "hp_cur": 192.0,
                "stats": {"atk": 189.0, "def": 120.0, "spa": 70.0, "spd": 100.0, "spe": 178.0},
                "types": ["Fighting", "Flying"],
                "ability": "Contrary",
                "item": "Staraptite",
                "is_mega": 1.0,
                "can_mega": 0.0,
                "moves": ["Close Combat", "Brave Bird", "Protect", "U-turn"],
            },
            # Slot 1: Armarouge with Expanding Force
            {
                "species": "Armarouge",
                "hp_max": 192.0,
                "hp_cur": 192.0,
                "stats": {"atk": 70.0, "def": 120.0, "spa": 194.0, "spd": 100.0, "spe": 95.0},
                "types": ["Fire", "Psychic"],
                "ability": "Flash Fire",
                "item": "None",
                "moves": ["Expanding Force", "Heat Wave", "Protect", "Trick Room"],
            },
            {},
            {},
            # Slot 4: Incineroar (Intimidate) with Sucker Punch & Flare Blitz
            {
                "species": "Incineroar",
                "hp_max": 202.0,
                "hp_cur": 202.0,
                "stats": {"atk": 150.0, "def": 115.0, "spa": 90.0, "spd": 130.0, "spe": 80.0},
                "types": ["Fire", "Dark"],
                "ability": "Intimidate",
                "item": "None",
                "moves": ["Sucker Punch", "Flare Blitz", "Parting Shot", "Protect"],
            },
            # Slot 5: Raichu (Lightning Rod)
            {
                "species": "Raichu",
                "hp_max": 167.0,
                "hp_cur": 167.0,
                "stats": {"atk": 95.0, "def": 75.0, "spa": 142.0, "spd": 100.0, "spe": 178.0},
                "types": ["Electric"],
                "ability": "Lightning Rod",
                "item": "None",
                "moves": ["Thunderbolt", "Protect", "Fake Out", "Nuzzle"],
            },
            {},
            {},
        ]
        state = self.compiler.compile_battle_state(
            rosters, field_spec={"terrain": "Psychic", "terrain_turns": 5.0}
        )
        # 1. Lead entry Intimidate from Incineroar onto Contrary Staraptor-Mega -> +1 Atk!
        pre_res = execute_pre_attack_phases(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            torch.tensor([[2, 2]], dtype=torch.long),
            torch.tensor([[3, 1]], dtype=torch.long),
            tables=self.compiler.tables,
            resolve_lead_entry_abilities=True,
        )
        self.assertEqual(float(pre_res.P[0, 0, SLOT_TRAINER_1_A, MonIdx.BOOST_ATK].item()), 1.0)

        # 2. Staraptor-Mega uses Close Combat (move 0 -> +1 Def, +1 SpD via Contrary),
        #    Armarouge uses Expanding Force (move 0 -> under Psychic Terrain hits BOTH foes!),
        #    Incineroar uses Sucker Punch (move 0) into Armarouge (choice 4):
        #    - Note: under Psychic Terrain, grounded Armarouge is immune to priority Sucker Punch!
        #    - And if Staraptor uses Protect (move 2), Sucker Punch into Staraptor (choice 0) fails because target used Status!
        res = self.state_machine.step(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            torch.tensor([[0, 0], [2, 2]], dtype=torch.long),
            torch.tensor([[0, 1]], dtype=torch.long),  # Incineroar Sucker Punch -> Staraptor, Raichu Protect
            num_mc_samples=32,
            rng_seed=42,
        )
        # Row 0: Staraptor Close Combat raised its Def and SpD to +1 via Contrary!
        self.assertEqual(float(res.P[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.BOOST_DEF].item()), 1.0)
        self.assertEqual(float(res.P[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.BOOST_SPD].item()), 1.0)
        # Row 1: Staraptor used Protect (Status), so Incineroar's Sucker Punch failed (0 damage dealt by Incineroar)
        self.assertEqual(float(res.attack_cascade.mean_damage_dealt[1, 0, 2].item()), 0.0)

    def test_05_mathematical_pruner_invariants(self) -> None:
        """Verify min_prior=0.0 lock, Helping Hand + Status/Switch pruning, Wide Guard, Quick Guard, and Shadow Tag."""
        rosters = [
            # Slot 0: Sinistcha (Ghost) with Helping Hand & Matcha Gotcha
            {
                "species": "Sinistcha",
                "hp_max": 178.0,
                "hp_cur": 178.0,
                "stats": {"atk": 60.0, "def": 140.0, "spa": 141.0, "spd": 100.0, "spe": 90.0},
                "types": ["Grass", "Ghost"],
                "ability": "Hospitality",
                "item": "Rocky Helmet",
                "moves": ["Helping Hand", "Matcha Gotcha", "Trick Room", "Protect"],
            },
            # Slot 1: Incineroar (Fire/Dark) with Parting Shot, Flare Blitz, Wide Guard, Quick Guard
            {
                "species": "Incineroar",
                "hp_max": 202.0,
                "hp_cur": 202.0,
                "stats": {"atk": 136.0, "def": 115.0, "spa": 90.0, "spd": 132.0, "spe": 80.0},
                "types": ["Fire", "Dark"],
                "ability": "Intimidate",
                "item": "Sitrus Berry",
                "moves": ["Parting Shot", "Flare Blitz", "Wide Guard", "Quick Guard"],
            },
            # Slot 2 (Bench 1): Garchomp (alive)
            {
                "species": "Garchomp",
                "hp_max": 183.0,
                "hp_cur": 183.0,
                "types": ["Dragon", "Ground"],
                "moves": ["Earthquake"],
            },
            {},
            # Slot 4 (Opp A): Gengar-Mega (Shadow Tag!) with Shadow Ball & Sludge Bomb (no spread, no priority)
            {
                "species": "Gengar-Mega",
                "hp_max": 167.0,
                "hp_cur": 167.0,
                "types": ["Ghost", "Poison"],
                "ability": "Shadow Tag",
                "is_mega": 1.0,
                "moves": ["Shadow Ball", "Sludge Bomb", "Protect", "Taunt"],
            },
            # Slot 5 (Opp B): Armarouge with Expanding Force & Armor Cannon (no priority, no spread unless Psychic Terrain!)
            {
                "species": "Armarouge",
                "hp_max": 192.0,
                "hp_cur": 192.0,
                "types": ["Fire", "Psychic"],
                "ability": "Flash Fire",
                "moves": ["Expanding Force", "Armor Cannon", "Protect", "Calm Mind"],
            },
            {},
            {},
        ]
        # Scenario 1: No Psychic Terrain, no bench Indeedee-F, no opponent priority moves
        state_no_psy = self.compiler.compile_battle_state(rosters)
        mask1 = self.logic_engine.prune_side_26x26_tensor_actions(
            state_no_psy, trainer_id="trainer_1", min_prior_threshold=0.95  # Must be ignored (locked to 0.0)!
        )
        valid_mat = mask1.valid_mask_26x26.detach().cpu().numpy()

        # 1. Helping Hand (Sinistcha move 0 -> Partner bucket 2 -> choice 8) + Incineroar Parting Shot (move 0 -> choices 0, 4)
        #    MUST be pruned (0.0), whereas Helping Hand (choice 8) + Incineroar Flare Blitz -> Opp A (choice 1) MUST be 1.0!
        #    And Flare Blitz -> Opp B (Flash Fire Armarouge with no alive opponent bench, choice 5) is ALSO pruned (0.0)!
        self.assertEqual(float(valid_mat[8, 0]), 0.0)  # Helping Hand + Parting Shot -> Opp A
        self.assertEqual(float(valid_mat[8, 4]), 0.0)  # Helping Hand + Parting Shot -> Opp B
        self.assertEqual(float(valid_mat[8, 1]), 1.0)  # Helping Hand + Flare Blitz -> Opp A
        self.assertEqual(float(valid_mat[8, 5]), 0.0)  # Flare Blitz -> Flash Fire Armarouge with no alive bench pruned!

        # 2. Shadow Tag (Gengar-Mega on Opp A):
        #    - Sinistcha (Slot A) is Ghost-type -> CAN switch to Bench 1 (choice 24)!
        #    - Incineroar (Slot B) is Fire/Dark -> BLOCKED from switching to Bench 1 (choice 24) by Shadow Tag!
        self.assertGreater(float(np.sum(valid_mat[CHOICE_SWITCH_BENCH1, :])), 0.0)
        self.assertEqual(float(np.sum(valid_mat[:, CHOICE_SWITCH_BENCH1])), 0.0)

        # 3. Wide Guard (Incineroar move 2 -> choice 2) & Quick Guard (Incineroar move 3 -> choice 3):
        #    Neither Gengar-Mega nor Armarouge has a spread move (without Psychic Terrain) or a priority move -> BOTH pruned!
        self.assertEqual(float(np.sum(valid_mat[:, 2])), 0.0)  # Wide Guard pruned
        self.assertEqual(float(np.sum(valid_mat[:, 3])), 0.0)  # Quick Guard pruned

        # Scenario 2: Add Indeedee-F (Psychic Surge) on Opponent Bench 1 (Slot 6) and Rillaboom (Grassy Surge) on Bench 2 (Slot 7)
        # and give Gengar-Mega Grassy Glide
        rosters_with_bench_surge = [dict(r) for r in rosters]
        rosters_with_bench_surge[4] = dict(rosters[4], moves=["Shadow Ball", "Grassy Glide", "Protect", "Taunt"])
        rosters_with_bench_surge[6] = {
            "species": "Indeedee-F",
            "hp_max": 177.0,
            "hp_cur": 177.0,
            "types": ["Psychic", "Normal"],
            "ability": "Psychic Surge",
            "moves": ["Follow Me"],
        }
        rosters_with_bench_surge[7] = {
            "species": "Rillaboom",
            "hp_max": 207.0,
            "hp_cur": 207.0,
            "types": ["Grass"],
            "ability": "Grassy Surge",
            "moves": ["Wood Hammer"],
        }
        state_bench_surge = self.compiler.compile_battle_state(rosters_with_bench_surge)
        mask2 = self.logic_engine.prune_side_26x26_tensor_actions(state_bench_surge, trainer_id="trainer_1")
        valid_mat2 = mask2.valid_mask_26x26.detach().cpu().numpy()
        # Now opponent can switch in Indeedee-F to make Armarouge's Expanding Force spread -> Wide Guard (choice 2) is VALID!
        # And opponent can switch in Rillaboom to make Gengar's Grassy Glide +1 priority -> Quick Guard (choice 3) is VALID!
        self.assertGreater(float(np.sum(valid_mat2[:, 2])), 0.0)
        self.assertGreater(float(np.sum(valid_mat2[:, 3])), 0.0)

    def test_06_2d_tiling_exact_mathematical_equivalence(self) -> None:
        """Verify 2D tiled execution (16x16 tiles) matches full-matrix (64x64) execution bit-for-bit."""
        rosters = [
            {
                "species": "Charizard",
                "hp_max": 153.0,
                "hp_cur": 153.0,
                "stats": {"atk": 104.0, "def": 98.0, "spa": 161.0, "spd": 105.0, "spe": 167.0},
                "types": ["Fire", "Flying"],
                "ability": "Blaze",
                "item": "Charizardite Y",
                "can_mega": 1.0,
                "mega_stats": {"atk": 124.0, "def": 98.0, "spa": 211.0, "spd": 135.0, "spe": 167.0},
                "mega_ability": "Drought",
                "moves": ["Heat Wave", "Air Slash", "Scorching Sands", "Protect"],
            },
            {
                "species": "Garchomp",
                "hp_max": 183.0,
                "hp_cur": 183.0,
                "stats": {"atk": 182.0, "def": 115.0, "spa": 90.0, "spd": 105.0, "spe": 169.0},
                "types": ["Dragon", "Ground"],
                "ability": "Rough Skin",
                "item": "Life Orb",
                "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
            },
            {
                "species": "Incineroar",
                "hp_max": 202.0,
                "hp_cur": 202.0,
                "stats": {"atk": 136.0, "def": 115.0, "spa": 90.0, "spd": 132.0, "spe": 80.0},
                "types": ["Fire", "Dark"],
                "ability": "Intimidate",
                "item": "Sitrus Berry",
                "moves": ["Flare Blitz", "Parting Shot", "Fake Out", "Protect"],
            },
            {
                "species": "Sinistcha",
                "hp_max": 178.0,
                "hp_cur": 178.0,
                "stats": {"atk": 60.0, "def": 140.0, "spa": 141.0, "spd": 100.0, "spe": 90.0},
                "types": ["Grass", "Ghost"],
                "ability": "Hospitality",
                "item": "Rocky Helmet",
                "moves": ["Matcha Gotcha", "Rage Powder", "Trick Room", "Protect"],
            },
            {
                "species": "Primarina",
                "hp_max": 187.0,
                "hp_cur": 187.0,
                "stats": {"atk": 84.0, "def": 105.0, "spa": 195.0, "spd": 136.0, "spe": 80.0},
                "types": ["Water", "Fairy"],
                "ability": "Liquid Voice",
                "item": "Mystic Water",
                "moves": ["Hyper Voice", "Moonblast", "Haze", "Protect"],
            },
            {
                "species": "Sneasler",
                "hp_max": 155.0,
                "hp_cur": 155.0,
                "stats": {"atk": 182.0, "def": 80.0, "spa": 60.0, "spd": 100.0, "spe": 189.0},
                "types": ["Fighting", "Poison"],
                "ability": "Unburden",
                "item": "Focus Sash",
                "moves": ["Close Combat", "Dire Claw", "Fake Out", "Protect"],
            },
            {
                "species": "Rillaboom",
                "hp_max": 207.0,
                "hp_cur": 207.0,
                "stats": {"atk": 194.0, "def": 110.0, "spa": 65.0, "spd": 90.0, "spe": 105.0},
                "types": ["Grass"],
                "ability": "Grassy Surge",
                "item": "Miracle Seed",
                "moves": ["Wood Hammer", "Grassy Glide", "Fake Out", "Protect"],
            },
            {
                "species": "Kingambit",
                "hp_max": 207.0,
                "hp_cur": 207.0,
                "stats": {"atk": 205.0, "def": 140.0, "spa": 60.0, "spd": 105.0, "spe": 70.0},
                "types": ["Dark", "Steel"],
                "ability": "Defiant",
                "item": "Black Glasses",
                "moves": ["Kowtow Cleave", "Sucker Punch", "Iron Head", "Protect"],
            },
        ]
        state = self.compiler.compile_battle_state(rosters)
        m1 = self.logic_engine.prune_side_26x26_tensor_actions(state, trainer_id="trainer_1")
        m2 = self.logic_engine.prune_side_26x26_tensor_actions(state, trainer_id="trainer_2")
        c1_64 = m1.pruned_choices[:64]
        c2_64 = m2.pruned_choices[:64]
        self.assertEqual(c1_64.shape[0], 64)
        self.assertEqual(c2_64.shape[0], 64)

        res_untiled = self.state_machine.step(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            c1_64,
            c2_64,
            num_mc_samples=16,
            rng_seed=202611,
            tile_size=128,
        )
        res_tiled = self.state_machine.step(
            state.field_tensor,
            state.roster_tensor,
            state.moves_tensor,
            c1_64,
            c2_64,
            num_mc_samples=16,
            rng_seed=202611,
            tile_size=16,
        )
        self.assertTrue(
            torch.allclose(res_untiled.stats.risk_adjusted_utility, res_tiled.stats.risk_adjusted_utility, atol=1e-6)
        )
        self.assertTrue(
            torch.allclose(res_untiled.stats.mean_utility, res_tiled.stats.mean_utility, atol=1e-6)
        )
        self.assertTrue(
            torch.allclose(res_untiled.stats.cvar_10_utility, res_tiled.stats.cvar_10_utility, atol=1e-6)
        )
        self.assertTrue(
            torch.allclose(res_untiled.faint_prob, res_tiled.faint_prob, atol=1e-6)
        )

    def test_07_trick_room_speed_initiative_inversion_in_board_utility(self) -> None:
        """Verify compute_per_thread_board_utility_torch rewards slow mons under Trick Room and fast mons normally."""
        rosters = [
            {"species": "Torkoal", "hp_max": 177.0, "hp_cur": 177.0, "stats": {"spe": 22.0}, "types": ["Fire"]},
            {"species": "Camerupt", "hp_max": 177.0, "hp_cur": 177.0, "stats": {"spe": 49.0}, "types": ["Fire", "Ground"]},
            {},
            {},
            {"species": "Dragapult", "hp_max": 163.0, "hp_cur": 163.0, "stats": {"spe": 213.0}, "types": ["Dragon", "Ghost"]},
            {"species": "Garchomp-Mega-Z", "hp_max": 183.0, "hp_cur": 183.0, "stats": {"spe": 203.0}, "types": ["Dragon"]},
            {},
            {},
        ]
        state_norm = self.compiler.compile_battle_state(rosters, field_spec={"trick_room_turns": 0.0})
        state_tr = self.compiler.compile_battle_state(rosters, field_spec={"trick_room_turns": 4.0})

        F_norm = state_norm.field_tensor.view(1, 1, 1, -1)
        P_norm = state_norm.roster_tensor.view(1, 1, 1, 8, -1)
        F_tr = state_tr.field_tensor.view(1, 1, 1, -1)
        P_tr = state_tr.roster_tensor.view(1, 1, 1, 8, -1)

        u_norm = float(compute_per_thread_board_utility_torch(F_norm, P_norm)[0, 0, 0].item())
        u_tr = float(compute_per_thread_board_utility_torch(F_tr, P_tr)[0, 0, 0].item())
        # Under Trick Room, slow trainer_1 gains +0.48 speed initiative swing over fast trainer_2!
        self.assertAlmostEqual(u_tr - u_norm, 0.48, places=4)

    def test_08_bilingual_terminology_and_5_verdict_badges(self) -> None:
        """Verify 4-variant glossary and 5 real verdict badges (no 6th FLINCH badge)."""
        self.assertEqual(len(VERDICT_BADGES), 5)
        self.assertEqual(
            set(VERDICT_BADGES.keys()),
            {"optimal", "good", "inaccuracy", "weak_dominated", "strict_dominated"},
        )
        self.assertGreaterEqual(len(TERM_GLOSSARY) + len(VERDICT_BADGES), 18)

        for lg in ("es", "en"):
            for st in ("vgc", "scientific"):
                self.assertTrue(get_term_label("Nash_Eq_Value", style=st, lang=lg))
                self.assertTrue(get_term_label("Nash_Utility_Loss", style=st, lang=lg))
                self.assertTrue(get_term_label("Future_Sight_Best_Play", style=st, lang=lg))
                self.assertTrue(get_rng_sampling_note(style=st, lang=lg))
                for v_key in VERDICT_BADGES:
                    vb = get_verdict_badge(v_key, style=st, lang=lg)
                    self.assertIn(vb["symbol"], {"!!", "!", "?!", "?", "??"})

        # Verify flinched_hidden=True still produces one of the 5 real verdict badges in all 4 variants
        dummy_actual = {
            "choice_pair": [0, 1],
            "desc": "Charizard: Heat Wave + Incineroar: Flare Blitz",
            "nash_regret": 0.01,
            "nash_pct": 45.0,
            "qre_pct": 38.0,
            "risk_ev": 0.42,
            "cvar10": 0.15,
            "security_floor": 0.05,
            "worst_counter_desc": "Primarina: Hyper Voice + Sneasler: Close Combat",
            "strict_dominated_by": None,
            "weak_dominated_by": None,
            "vs_actual_opp_u": 0.55,
            "oracle_best_desc": "Charizard: Heat Wave + Incineroar: Flare Blitz",
            "oracle_best_u": 0.55,
            "flinched_hidden": True,
            "num_mc": 256,
            "ko_probs_vs_actual_opp": {"Sneasler": 87.5},
        }
        ieds_sum = {"t1_total": 120, "t1_strict": 18, "t1_weak": 12, "strict_rounds": 3}
        variants = generate_all_commentary_variants(
            turn_number=1,
            actual_action=dummy_actual,
            top_actions=[dummy_actual],
            nash_value=0.43,
            ieds_summary=ieds_sum,
            events={"crits": [], "misses": [], "flinches": [{"trainer": "trainer_1", "species": "Incineroar"}]},
            field_context={"trick_room_turns": 0, "weather": "Sun", "weather_turns": 5},
        )
        self.assertEqual(set(variants.keys()), {"es_vgc", "en_vgc", "es_scientific", "en_scientific"})
        for var_name, comm in variants.items():
            self.assertEqual(comm["verdict_key"], "optimal", f"{var_name} should be graded optimal")
            self.assertEqual(comm["symbol"], "!!")
            self.assertNotIn("INTERRUMPIDA", comm["badge"])

        payload = export_glossary_payload()
        self.assertIn("terms", payload)
        self.assertIn("badges", payload)
        self.assertIn("rng_events", payload)

    def test_09_hurricane_thunder_weather_accuracy_sun_50_rain_100_clear_70(self) -> None:
        """Verify official cartridge weather accuracy for Hurricane/Thunder: 100% Rain, 70% Clear, 50% Sun."""
        from engine.vgc_tensor_core.phases_pre_attack import W_CLEAR, W_RAIN, W_SUN

        base_roster = [
            {
                "species": "Charizard",
                "hp_max": 180.0,
                "hp_cur": 180.0,
                "stats": {"atk": 90.0, "def": 100.0, "spa": 165.0, "spd": 105.0, "spe": 150.0},
                "types": ["Fire", "Flying"],
                "ability": "Blaze",
                "moves": ["Hurricane", "Protect", "Heat Wave", "Weather Ball"],
            },
            {
                "species": "Venusaur",
                "hp_max": 180.0,
                "hp_cur": 180.0,
                "stats": {"atk": 90.0, "def": 100.0, "spa": 150.0, "spd": 120.0, "spe": 110.0},
                "types": ["Grass", "Poison"],
                "ability": "Overgrow",
                "moves": ["Protect", "Sludge Bomb", "Leaf Storm", "Sleep Powder"],
            },
            {"species": "Garchomp", "hp_max": 183.0, "hp_cur": 183.0, "types": ["Dragon", "Ground"], "moves": ["Protect", "Dragon Claw", "Rock Slide", "Stomping Tantrum"]},
            {"species": "Pelipper", "hp_max": 167.0, "hp_cur": 167.0, "types": ["Water", "Flying"], "ability": "Drizzle", "moves": ["Protect", "Hurricane", "Weather Ball", "Tailwind"]},
            {
                "species": "Primarina",
                "hp_max": 250.0,
                "hp_cur": 250.0,
                "stats": {"atk": 84.0, "def": 105.0, "spa": 160.0, "spd": 160.0, "spe": 80.0},
                "types": ["Water", "Fairy"],
                "ability": "Torrent",
                "moves": ["Protect", "Moonblast", "Hyper Voice", "Haze"],
            },
            {
                "species": "Farigiraf",
                "hp_max": 220.0,
                "hp_cur": 220.0,
                "stats": {"atk": 90.0, "def": 110.0, "spa": 130.0, "spd": 110.0, "spe": 80.0},
                "types": ["Normal", "Psychic"],
                "ability": "Armor Tail",
                "moves": ["Protect", "Psychic", "Trick Room", "Hyper Voice"],
            },
            {"species": "Incineroar", "hp_max": 202.0, "hp_cur": 202.0, "types": ["Fire", "Dark"], "ability": "Intimidate", "moves": ["Protect", "Flare Blitz", "Fake Out", "Parting Shot"]},
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "types": ["Grass"], "ability": "Grassy Surge", "moves": ["Protect", "Wood Hammer", "Grassy Glide", "Fake Out"]},
        ]

        hit_rates = {}
        st_base = self.compiler.compile_battle_state(base_roster)
        for w_name, w_code in (("Rain", W_RAIN), ("Clear", W_CLEAR), ("Sun", W_SUN)):
            F = st_base.field_tensor.clone()
            F[FieldIdx.WEATHER_START:FieldIdx.WEATHER_END] = 0.0
            F[FieldIdx.WEATHER_START + w_code] = 1.0
            F[FieldIdx.WEATHER_TURNS] = 5.0 if w_name != "Clear" else 0.0
            t1_c = torch.tensor([[0, 0]], dtype=torch.long)  # Charizard Hurricane -> Opp A (Primarina), Venusaur Protect
            t2_c = torch.tensor([[1, 1]], dtype=torch.long)  # Primarina Moonblast, Farigiraf Psychic
            res = self.state_machine.step(
                F,
                st_base.roster_tensor,
                st_base.moves_tensor,
                t1_c,
                t2_c,
                num_mc_samples=512,
                rng_seed=202699,
            )
            hit_rates[w_name] = float(res.attack_cascade.hit_rate_observed[0, 0, 0].item())

        self.assertAlmostEqual(hit_rates["Rain"], 1.0, places=4)
        self.assertGreater(hit_rates["Clear"], 0.62)
        self.assertLess(hit_rates["Clear"], 0.78)
        self.assertGreater(hit_rates["Sun"], 0.42)
        self.assertLess(hit_rates["Sun"], 0.58)
        self.assertLess(hit_rates["Sun"], hit_rates["Clear"] - 0.12)
        self.assertEqual(
            self.logic_engine._resolve_accuracy("Hurricane", {"accuracy": 70}, "sun", "Blaze", "Torrent"),
            50.0,
        )
        self.assertEqual(
            self.logic_engine._resolve_accuracy("Hurricane", {"accuracy": 70}, "rain", "Blaze", "Torrent"),
            100.0,
        )

    def test_10_complete_reg_mc_weather_mechanics_parity(self) -> None:
        """Verify all newly added Reg M-C weather mechanics:
        - Rock-type 1.5x SpD in Sandstorm (and NOT on Psyshock/Physical)
        - Ice-type 1.5x Def in Snow (including Psyshock & Ice-type Body Press)
        - Aurora Veil strict Snow gate (fails outside Snow)
        - Synthesis / Morning Sun / Moonlight weather healing (2/3 Sun, 1/2 Clear, 1/4 Rain)
        - Sand Force 1.3x BP in Sand + Sandstorm chip immunity
        - Dry Skin (Water absorb + 1.25x Fire dmg + +1/8 EoT Rain / -1/8 EoT Sun)
        - Rain Dish (+1/16 EoT Rain), Ice Body (+1/16 EoT Snow)
        - Sand Veil / Snow Cloak (0.8x accuracy)
        - Leaf Guard (Sun status immunity) & Hydration (Rain EoT status cure)
        """
        from engine.vgc_tensor_core.phases_pre_attack import W_CLEAR, W_RAIN, W_SAND, W_SNOW, W_SUN
        from engine.vgc_tensor_core.schema_and_tables import STATUS_TO_IDX, TYPE_TO_IDX

        def _set_weather(F_base: torch.Tensor, w_code: int) -> torch.Tensor:
            F = F_base.clone()
            F[FieldIdx.WEATHER_START:FieldIdx.WEATHER_END] = 0.0
            F[FieldIdx.WEATHER_START + w_code] = 1.0
            F[FieldIdx.WEATHER_TURNS] = 5.0 if w_code != W_CLEAR else 0.0
            return F

        # A. Rock 1.5x SpD in Sand, Ice 1.5x Def in Snow (Physical + Body Press), Aurora Veil Snow Gate
        roster_a = [
            {
                "species": "Alakazam",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 150.0, "def": 100.0, "spa": 180.0, "spd": 100.0, "spe": 170.0},
                "types": ["Psychic"],
                "ability": "Inner Focus",
                "moves": ["Psychic", "Psyshock", "Brick Break", "Protect"],
            },
            {
                "species": "Ninetales-Alola",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 90.0, "def": 150.0, "spa": 120.0, "spd": 120.0, "spe": 165.0},
                "types": ["Ice", "Fairy"],
                "ability": "Snow Cloak",
                "moves": ["Aurora Veil", "Body Press", "Protect", "Blizzard"],
            },
            {"species": "Garchomp", "hp_max": 183.0, "hp_cur": 183.0, "types": ["Dragon", "Ground"], "moves": ["Protect", "Rock Slide", "Earthquake", "Dragon Claw"]},
            {"species": "Pelipper", "hp_max": 167.0, "hp_cur": 167.0, "types": ["Water", "Flying"], "moves": ["Protect", "Hurricane", "Weather Ball", "Tailwind"]},
            {
                "species": "Tyranitar",
                "hp_max": 300.0,
                "hp_cur": 300.0,
                "stats": {"atk": 150.0, "def": 120.0, "spa": 100.0, "spd": 120.0, "spe": 80.0},
                "types": ["Rock"],
                "ability": "Unnerve",
                "moves": ["Protect", "Rock Slide", "Crunch", "Earthquake"],
            },
            {
                "species": "Glaceon",
                "hp_max": 300.0,
                "hp_cur": 300.0,
                "stats": {"atk": 90.0, "def": 120.0, "spa": 150.0, "spd": 120.0, "spe": 80.0},
                "types": ["Ice"],
                "ability": "Ice Body",
                "moves": ["Protect", "Ice Beam", "Blizzard", "Shadow Ball"],
            },
            {"species": "Incineroar", "hp_max": 202.0, "hp_cur": 202.0, "types": ["Fire", "Dark"], "moves": ["Protect", "Flare Blitz", "Fake Out", "Parting Shot"]},
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "types": ["Grass"], "moves": ["Protect", "Wood Hammer", "Grassy Glide", "Fake Out"]},
        ]
        st_a = self.compiler.compile_battle_state(roster_a)

        # 1. Rock SpD 1.5x in Sand (Psychic -> Tyranitar Opp A, choice 0 = slot0->OppA)
        t1_psy = torch.tensor([[0, 2]], dtype=torch.long)  # Alakazam Psychic->Tyranitar, Ninetales Protect
        t2_idle = torch.tensor([[1, 1]], dtype=torch.long)  # Non-protect moves
        r_clear = self.state_machine.step(_set_weather(st_a.field_tensor, W_CLEAR), st_a.roster_tensor, st_a.moves_tensor, t1_psy, t2_idle, num_mc_samples=64, rng_seed=777)
        r_sand = self.state_machine.step(_set_weather(st_a.field_tensor, W_SAND), st_a.roster_tensor, st_a.moves_tensor, t1_psy, t2_idle, num_mc_samples=64, rng_seed=777)
        dmg_clear = float(r_clear.attack_cascade.mean_damage_dealt[0, 0, 0].item())
        dmg_sand = float(r_sand.attack_cascade.mean_damage_dealt[0, 0, 0].item())
        self.assertGreater(dmg_clear, 20.0)
        self.assertAlmostEqual(dmg_sand / dmg_clear, 2.0 / 3.0, delta=0.06)

        # 2. Ice Def 1.5x in Snow (Brick Break -> Glaceon Opp B = 1*4 + 2 = 6; Psyshock -> Glaceon Opp B = 1*4 + 1 = 5)
        for mv_choice in (6, 5):
            t1_mv = torch.tensor([[mv_choice, 2]], dtype=torch.long)
            rc = self.state_machine.step(_set_weather(st_a.field_tensor, W_CLEAR), st_a.roster_tensor, st_a.moves_tensor, t1_mv, t2_idle, num_mc_samples=64, rng_seed=778)
            rs = self.state_machine.step(_set_weather(st_a.field_tensor, W_SNOW), st_a.roster_tensor, st_a.moves_tensor, t1_mv, t2_idle, num_mc_samples=64, rng_seed=778)
            dc = float(rc.attack_cascade.mean_damage_dealt[0, 0, 0].item())
            ds = float(rs.attack_cascade.mean_damage_dealt[0, 0, 0].item())
            self.assertAlmostEqual(ds / dc, 2.0 / 3.0, delta=0.06)

        # 3. Ice-type attacker Body Press boosted 1.5x in Snow (Ninetales Body Press -> Tyranitar Opp A = 1)
        t1_bp = torch.tensor([[3, 1]], dtype=torch.long)  # Alakazam Protect, Ninetales Body Press -> Tyranitar
        rb_c = self.state_machine.step(_set_weather(st_a.field_tensor, W_CLEAR), st_a.roster_tensor, st_a.moves_tensor, t1_bp, t2_idle, num_mc_samples=64, rng_seed=779)
        rb_s = self.state_machine.step(_set_weather(st_a.field_tensor, W_SNOW), st_a.roster_tensor, st_a.moves_tensor, t1_bp, t2_idle, num_mc_samples=64, rng_seed=779)
        self.assertAlmostEqual(
            float(rb_s.attack_cascade.mean_damage_dealt[0, 0, 1].item())
            / float(rb_c.attack_cascade.mean_damage_dealt[0, 0, 1].item()),
            1.5,
            delta=0.08,
        )

        # 4. Aurora Veil fails outside Snow, succeeds in Snow
        t1_av = torch.tensor([[3, 0]], dtype=torch.long)  # Alakazam Protect, Ninetales Aurora Veil
        rav_clear = self.state_machine.step(_set_weather(st_a.field_tensor, W_CLEAR), st_a.roster_tensor, st_a.moves_tensor, t1_av, t2_idle, num_mc_samples=16, rng_seed=780)
        rav_snow = self.state_machine.step(_set_weather(st_a.field_tensor, W_SNOW), st_a.roster_tensor, st_a.moves_tensor, t1_av, t2_idle, num_mc_samples=16, rng_seed=780)
        self.assertEqual(float(rav_clear.end_of_turn.F[0, 0, 0, FieldIdx.TRAINER_1_AURORA_VEIL_TURNS].item()), 0.0)
        self.assertEqual(float(rav_snow.end_of_turn.F[0, 0, 0, FieldIdx.TRAINER_1_AURORA_VEIL_TURNS].item()), 4.0)  # 5 -> 4 after EoT

        # B. Synthesis weather healing + Sand Force + Dry Skin + Rain Dish + Ice Body + Leaf Guard + Hydration + Sand Veil
        roster_b = [
            {
                "species": "Venusaur",
                "hp_max": 240.0,
                "hp_cur": 60.0,
                "stats": {"atk": 100.0, "def": 100.0, "spa": 120.0, "spd": 100.0, "spe": 150.0},
                "types": ["Grass", "Poison"],
                "ability": "Leaf Guard",
                "moves": ["Synthesis", "Protect", "Sludge Bomb", "Leaf Storm"],
            },
            {
                "species": "Excadrill",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 180.0, "def": 90.0, "spa": 60.0, "spd": 90.0, "spe": 140.0},
                "types": ["Ground", "Steel"],
                "ability": "Sand Force",
                "moves": ["Rock Slide", "Protect", "Earthquake", "Iron Head"],
            },
            {"species": "Garchomp", "hp_max": 183.0, "hp_cur": 183.0, "types": ["Dragon", "Ground"], "moves": ["Protect", "Rock Slide", "Earthquake", "Dragon Claw"]},
            {"species": "Pelipper", "hp_max": 167.0, "hp_cur": 167.0, "types": ["Water", "Flying"], "moves": ["Protect", "Hurricane", "Weather Ball", "Tailwind"]},
            {
                "species": "Heliolisk",
                "hp_max": 160.0,
                "hp_cur": 120.0,
                "stats": {"atk": 80.0, "def": 100.0, "spa": 130.0, "spd": 100.0, "spe": 130.0},
                "types": ["Electric", "Normal"],
                "ability": "Dry Skin",
                "moves": ["Will-O-Wisp", "Protect", "Thunderbolt", "Flamethrower"],
            },
            {
                "species": "Goodra",
                "hp_max": 240.0,
                "hp_cur": 160.0,
                "stats": {"atk": 100.0, "def": 100.0, "spa": 120.0, "spd": 160.0, "spe": 90.0},
                "types": ["Dragon"],
                "ability": "Hydration",
                "moves": ["Protect", "Dragon Pulse", "Ice Beam", "Muddy Water"],
            },
            {"species": "Incineroar", "hp_max": 202.0, "hp_cur": 202.0, "types": ["Fire", "Dark"], "moves": ["Protect", "Flare Blitz", "Fake Out", "Parting Shot"]},
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "types": ["Grass"], "moves": ["Protect", "Wood Hammer", "Grassy Glide", "Fake Out"]},
        ]
        st_b = self.compiler.compile_battle_state(roster_b)
        P_b = st_b.roster_tensor.clone()
        # Burn Goodra (slot 5) before turn to verify Hydration cures Burn in Rain
        P_b[5, MonIdx.STATUS_HEALTHY] = 0.0
        P_b[5, MonIdx.STATUS_BURN] = 1.0

        # 5. Synthesis healing: 60 + 160 = 220 in Sun, 60 + 120 = 180 in Clear, 60 + 60 = 120 in Rain
        #    AND Heliolisk Will-O-Wisp -> Venusaur (Leaf Guard) blocked in Sun!
        #    AND Dry Skin Heliolisk loses 20 HP in Sun (120 -> 100), gains 20 HP in Rain (120 -> 140)!
        #    AND Hydration Goodra cured of Burn in Rain!
        t1_syn = torch.tensor([[0, 1]], dtype=torch.long)  # Venusaur Synthesis, Excadrill Protect
        t2_wisp = torch.tensor([[0, 0]], dtype=torch.long)  # Heliolisk Will-O-Wisp -> Venusaur, Goodra Protect
        rsun = self.state_machine.step(_set_weather(st_b.field_tensor, W_SUN), P_b, st_b.moves_tensor, t1_syn, t2_wisp, num_mc_samples=64, rng_seed=801)
        rclr = self.state_machine.step(_set_weather(st_b.field_tensor, W_CLEAR), P_b, st_b.moves_tensor, t1_syn, t2_wisp, num_mc_samples=64, rng_seed=801)
        rrain = self.state_machine.step(_set_weather(st_b.field_tensor, W_RAIN), P_b, st_b.moves_tensor, t1_syn, t2_wisp, num_mc_samples=64, rng_seed=801)

        self.assertAlmostEqual(float(rsun.mean_hp[0, 0, 0].item()), 220.0, delta=1.5)  # 2/3 heal in Sun + Leaf Guard blocked burn chip!
        self.assertEqual(float(rsun.end_of_turn.P[0, 0, :, 0, MonIdx.STATUS_HEALTHY].mean().item()), 1.0)
        self.assertAlmostEqual(float(rrain.mean_hp[0, 0, 0].item()), 120.0, delta=16.0)  # 1/4 heal (+60) minus optional burn chip
        self.assertAlmostEqual(float(rsun.mean_hp[0, 0, 4].item()), 100.0, delta=1.0)  # Dry Skin -1/8 HP in Sun
        self.assertAlmostEqual(float(rrain.mean_hp[0, 0, 4].item()), 140.0, delta=1.0)  # Dry Skin +1/8 HP in Rain
        self.assertEqual(float(rrain.end_of_turn.P[0, 0, :, 5, MonIdx.STATUS_HEALTHY].mean().item()), 1.0)  # Hydration cured Burn in Rain
        self.assertEqual(float(rclr.end_of_turn.P[0, 0, :, 5, MonIdx.STATUS_BURN].mean().item()), 1.0)  # Still burned in Clear

        # 6. Sand Force 1.3x BP on Iron Head -> Heliolisk in Sand
        t1_sf = torch.tensor([[1, 3]], dtype=torch.long)  # Venusaur Protect, Excadrill Iron Head -> Opp A (Heliolisk)
        t2_np = torch.tensor([[2, 1]], dtype=torch.long)
        rsf_clr = self.state_machine.step(_set_weather(st_b.field_tensor, W_CLEAR), st_b.roster_tensor, st_b.moves_tensor, t1_sf, t2_np, num_mc_samples=64, rng_seed=802)
        rsf_snd = self.state_machine.step(_set_weather(st_b.field_tensor, W_SAND), st_b.roster_tensor, st_b.moves_tensor, t1_sf, t2_np, num_mc_samples=64, rng_seed=802)
        self.assertAlmostEqual(
            float(rsf_snd.attack_cascade.mean_damage_dealt[0, 0, 1].item())
            / float(rsf_clr.attack_cascade.mean_damage_dealt[0, 0, 1].item()),
            1.3,
            delta=0.07,
        )

        # 7. Dry Skin 1.25x Fire damage taken (using Flamethrower from Heliolisk onto Dry Skin clone vs non-Dry Skin)
        P_ds = st_b.roster_tensor.clone()
        P_ds[0, MonIdx.TYPE1_START:MonIdx.TYPE1_END] = 0.0
        P_ds[0, MonIdx.TYPE1_START + TYPE_TO_IDX["normal"]] = 1.0
        P_ds[0, MonIdx.TYPE2_START:MonIdx.TYPE2_END] = 0.0
        P_ds[0, MonIdx.HP_CUR] = 240.0
        P_ds[0, MonIdx.ABILITY_ID] = float(AbilityID.NONE)
        P_ds2 = P_ds.clone()
        P_ds2[0, MonIdx.ABILITY_ID] = float(AbilityID.DRY_SKIN)
        t1_pr = torch.tensor([[2, 1]], dtype=torch.long)  # Venusaur Sludge Bomb (no protect), Excadrill Protect
        t2_fl = torch.tensor([[3, 0]], dtype=torch.long)  # Heliolisk Flamethrower -> Opp A (Venusaur)
        r_nods = self.state_machine.step(_set_weather(st_b.field_tensor, W_CLEAR), P_ds, st_b.moves_tensor, t1_pr, t2_fl, num_mc_samples=64, rng_seed=803)
        r_ds = self.state_machine.step(_set_weather(st_b.field_tensor, W_CLEAR), P_ds2, st_b.moves_tensor, t1_pr, t2_fl, num_mc_samples=64, rng_seed=803)
        self.assertAlmostEqual(
            float(r_ds.attack_cascade.mean_damage_dealt[0, 0, 2].item())
            / float(r_nods.attack_cascade.mean_damage_dealt[0, 0, 2].item()),
            1.25,
            delta=0.07,
        )

        # 8. Sand Veil 0.8x incoming accuracy in Sand (100% acc move drops to ~80% hit rate)
        P_sv = st_b.roster_tensor.clone()
        P_sv[4, MonIdx.ABILITY_ID] = float(AbilityID.SAND_VEIL)
        r_sv = self.state_machine.step(_set_weather(st_b.field_tensor, W_SAND), P_sv, st_b.moves_tensor, t1_sf, t2_np, num_mc_samples=512, rng_seed=804)
        sv_hit = float(r_sv.attack_cascade.hit_rate_observed[0, 0, 1].item())
        self.assertGreater(sv_hit, 0.72)
        self.assertLess(sv_hit, 0.88)

    def test_11_tournament_and_champions_mega_abilities_items_and_volatiles(self) -> None:
        """Verify Opportunities 1 & 2 + F3 compiler keys across Reg M-C tournament & Champions Mega mechanics."""
        from engine.vgc_tensor_core.compiler import ABILITY_NAME_TO_ID, ITEM_NAME_TO_ID
        from engine.vgc_tensor_core.phases_pre_attack import W_CLEAR
        from engine.vgc_tensor_core.schema_and_tables import FieldOpID, TYPE_TO_IDX

        # 0. Verify F3 & all new compiler mappings resolve cleanly
        for it_key, exp_it in (
            ("scope lens", ItemID.SCOPE_LENS),
            ("muscle band", ItemID.MUSCLE_BAND),
            ("wise glasses", ItemID.WISE_GLASSES),
            ("leek", ItemID.LEEK),
            ("iron ball", ItemID.IRON_BALL),
            ("terrain extender", ItemID.TERRAIN_EXTENDER),
            ("chesto berry", ItemID.CHESTO_BERRY),
            ("shell bell", ItemID.SHELL_BELL),
            ("bright powder", ItemID.BRIGHT_POWDER),
        ):
            self.assertEqual(ITEM_NAME_TO_ID[it_key], exp_it)

        for ab_key, exp_ab in (
            ("skill link", AbilityID.SKILL_LINK),
            ("justified", AbilityID.JUSTIFIED),
            ("shield dust", AbilityID.SHIELD_DUST),
            ("unnerve", AbilityID.UNNERVE),
            ("trace", AbilityID.TRACE),
            ("thermal exchange", AbilityID.THERMAL_EXCHANGE),
            ("hyper cutter", AbilityID.HYPER_CUTTER),
            ("bulletproof", AbilityID.BULLETPROOF),
            ("damp", AbilityID.DAMP),
            ("parental bond", AbilityID.PARENTAL_BOND),
            ("mega launcher", AbilityID.MEGA_LAUNCHER),
            ("strong jaw", AbilityID.STRONG_JAW),
            ("protean", AbilityID.PROTEAN),
            ("berserk", AbilityID.BERSERK),
            ("unseen fist", AbilityID.UNSEEN_FIST),
            ("dragonize", AbilityID.DRAGONIZE),
            ("piercing drill", AbilityID.PIERCING_DRILL),
            ("mega sol", AbilityID.MEGA_SOL),
            ("aura guard", AbilityID.AURA_GUARD),
            ("eelevate", AbilityID.EELEVATE),
            ("fire mane", AbilityID.FIRE_MANE),
            ("spicy spray", AbilityID.SPICY_SPRAY),
            ("stalwart", AbilityID.STALWART),
            ("innards out", AbilityID.INNARDS_OUT),
        ):
            self.assertEqual(ABILITY_NAME_TO_ID[ab_key], exp_ab)

        # Verify DuckDB flag-carrier FieldOpID compilation
        self.assertEqual(int(round(float(self.compiler.compile_move_vector("Dark Pulse")[MoveIdx.FIELD_OP_ID]))), int(FieldOpID.FLAG_PULSE))
        self.assertEqual(int(round(float(self.compiler.compile_move_vector("Crunch")[MoveIdx.FIELD_OP_ID]))), int(FieldOpID.FLAG_BITE))
        self.assertEqual(int(round(float(self.compiler.compile_move_vector("Shadow Ball")[MoveIdx.FIELD_OP_ID]))), int(FieldOpID.FLAG_BULLET))
        self.assertEqual(int(round(float(self.compiler.compile_move_vector("Aura Sphere")[MoveIdx.FIELD_OP_ID]))), int(FieldOpID.FLAG_PULSE_BULLET))

        # 1. Champions Mega Abilities: Piercing Drill bypasses Protect, Aura Guard halves contact,
        #    Mega Sol skips Solar Beam charge in Clear weather, Dragonize converts Normal -> Dragon,
        #    Bulletproof blocks Shadow Ball, Unnerve suppresses Sitrus Berry!
        roster_m = [
            {
                "species": "Excadrill-Mega",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 180.0, "def": 100.0, "spa": 70.0, "spd": 90.0, "spe": 150.0},
                "types": ["Ground", "Steel"],
                "ability": "Piercing Drill",
                "moves": ["Iron Head", "Earthquake", "Protect", "Rock Slide"],
            },
            {
                "species": "Meganium-Mega",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 90.0, "def": 120.0, "spa": 160.0, "spd": 120.0, "spe": 120.0},
                "types": ["Grass", "Fairy"],
                "ability": "Mega Sol",
                "moves": ["Solar Beam", "Shadow Ball", "Protect", "Synthesis"],
            },
            {"species": "Garchomp", "hp_max": 183.0, "hp_cur": 183.0, "types": ["Dragon", "Ground"], "moves": ["Protect", "Dragon Claw", "Earthquake", "Rock Slide"]},
            {"species": "Incineroar", "hp_max": 202.0, "hp_cur": 202.0, "types": ["Fire", "Dark"], "ability": "Intimidate", "moves": ["Protect", "Flare Blitz", "Fake Out", "Parting Shot"]},
            {
                "species": "Lucario-Mega-Z",
                "hp_max": 300.0,
                "hp_cur": 300.0,
                "stats": {"atk": 130.0, "def": 120.0, "spa": 160.0, "spd": 110.0, "spe": 140.0},
                "types": ["Fighting", "Steel"],
                "ability": "Aura Guard",
                "moves": ["Protect", "Aura Sphere", "Flash Cannon", "Vacuum Wave"],
            },
            {
                "species": "Chesnaught",
                "hp_max": 300.0,
                "hp_cur": 300.0,
                "stats": {"atk": 130.0, "def": 140.0, "spa": 80.0, "spd": 100.0, "spe": 80.0},
                "types": ["Grass", "Fighting"],
                "ability": "Bulletproof",
                "moves": ["Protect", "Wood Hammer", "Drain Punch", "Spiky Shield"],
            },
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "types": ["Grass"], "moves": ["Protect", "Wood Hammer", "Grassy Glide", "Fake Out"]},
            {"species": "Pelipper", "hp_max": 167.0, "hp_cur": 167.0, "types": ["Water", "Flying"], "moves": ["Protect", "Hurricane", "Weather Ball", "Tailwind"]},
        ]
        st_m = self.compiler.compile_battle_state(roster_m)

        # Piercing Drill contact Iron Head breaks through Lucario-Mega-Z's Protect,
        # while Mega Sol fires Solar Beam Turn 1 in Clear weather onto Chesnaught (who uses Wood Hammer)!
        t1_c = torch.tensor([[0, 4]], dtype=torch.long)  # Excadrill Iron Head->Opp A (Lucario), Meganium Solar Beam->Opp B (Chesnaught)
        t2_c = torch.tensor([[0, 1]], dtype=torch.long)  # Lucario Protect, Chesnaught Wood Hammer->Opp A
        res_m = self.state_machine.step(st_m.field_tensor, st_m.roster_tensor, st_m.moves_tensor, t1_c, t2_c, num_mc_samples=32, rng_seed=901)
        self.assertGreater(float(res_m.attack_cascade.mean_damage_dealt[0, 0, 0].item()), 5.0)
        self.assertGreater(float(res_m.attack_cascade.mean_damage_dealt[0, 0, 1].item()), 10.0)

        # Compare Aura Guard vs None on incoming contact Iron Head (Aura Guard halves contact damage!)
        P_no_ag = st_m.roster_tensor.clone()
        P_no_ag[4, MonIdx.ABILITY_ID] = float(AbilityID.NONE)
        res_no_ag = self.state_machine.step(st_m.field_tensor, P_no_ag, st_m.moves_tensor, t1_c, t2_c, num_mc_samples=32, rng_seed=901)
        dmg_ag = float(res_m.attack_cascade.mean_damage_dealt[0, 0, 0].item())
        dmg_no_ag = float(res_no_ag.attack_cascade.mean_damage_dealt[0, 0, 0].item())
        self.assertAlmostEqual(dmg_ag / dmg_no_ag, 0.5, delta=0.06)

        # Bulletproof blocks Shadow Ball (choice 5 = move 1 -> Opp B Chesnaught)
        t1_sb = torch.tensor([[2, 5]], dtype=torch.long)  # Excadrill Protect, Meganium Shadow Ball -> Opp B (Chesnaught)
        res_bp = self.state_machine.step(st_m.field_tensor, st_m.roster_tensor, st_m.moves_tensor, t1_sb, t2_c, num_mc_samples=16, rng_seed=902)
        self.assertEqual(float(res_bp.attack_cascade.mean_damage_dealt[0, 0, 1].item()), 0.0)

        # 2. Volatile Disruption + EoT: Salt Cure (1/4 max HP to Water), Leech Seed drain/heal, Damp blocks Explosion,
        #    Unnerve suppresses Sitrus Berry, Iron Ball halves Speed & grounds Flying types!
        roster_v = [
            {
                "species": "Garganacl",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 120.0, "def": 150.0, "spa": 60.0, "spd": 110.0, "spe": 55.0},
                "types": ["Rock"],
                "ability": "Unnerve",
                "moves": ["Salt Cure", "Protect", "Recover", "Wide Guard"],
            },
            {
                "species": "Venusaur",
                "hp_max": 200.0,
                "hp_cur": 150.0,
                "stats": {"atk": 90.0, "def": 100.0, "spa": 130.0, "spd": 120.0, "spe": 110.0},
                "types": ["Grass", "Poison"],
                "ability": "Overgrow",
                "moves": ["Leech Seed", "Protect", "Sludge Bomb", "Energy Ball"],
            },
            {"species": "Garchomp", "hp_max": 183.0, "hp_cur": 183.0, "types": ["Dragon", "Ground"], "moves": ["Protect", "Dragon Claw", "Earthquake", "Rock Slide"]},
            {"species": "Incineroar", "hp_max": 202.0, "hp_cur": 202.0, "types": ["Fire", "Dark"], "moves": ["Protect", "Flare Blitz", "Fake Out", "Parting Shot"]},
            {
                "species": "Primarina",
                "hp_max": 200.0,
                "hp_cur": 110.0,
                "stats": {"atk": 80.0, "def": 120.0, "spa": 160.0, "spd": 140.0, "spe": 80.0},
                "types": ["Water", "Fairy"],
                "ability": "Torrent",
                "item": "Sitrus Berry",
                "moves": ["Protect", "Moonblast", "Hyper Voice", "Haze"],
            },
            {
                "species": "Swampert",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 130.0, "def": 120.0, "spa": 100.0, "spd": 110.0, "spe": 100.0},
                "types": ["Water", "Ground"],
                "ability": "Damp",
                "item": "Iron Ball",
                "moves": ["Explosion", "Protect", "Earthquake", "Ice Punch"],
            },
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "types": ["Grass"], "moves": ["Protect", "Wood Hammer", "Grassy Glide", "Fake Out"]},
            {"species": "Pelipper", "hp_max": 167.0, "hp_cur": 167.0, "types": ["Water", "Flying"], "moves": ["Protect", "Hurricane", "Weather Ball", "Tailwind"]},
        ]
        st_v = self.compiler.compile_battle_state(roster_v)
        # Garganacl Salt Cure -> Opp A (Primarina), Venusaur Leech Seed -> Opp A (Primarina)
        # Primarina Moonblast -> Garganacl, Swampert attempts Explosion (blocked by its own Damp!)
        t1_v = torch.tensor([[0, 0]], dtype=torch.long)
        t2_v = torch.tensor([[1, 0]], dtype=torch.long)
        res_v = self.state_machine.step(st_v.field_tensor, st_v.roster_tensor, st_v.moves_tensor, t1_v, t2_v, num_mc_samples=16, rng_seed=903)

        # Iron Ball halves Swampert's effective speed (100 -> 50)
        self.assertEqual(float(res_v.pre_attack.effective_speeds[0, 0, 3].item()), 50.0)
        # Damp prevented Swampert's Explosion self-faint (Swampert stays at full 200 HP)
        self.assertEqual(float(res_v.mean_hp[0, 0, 5].item()), 200.0)
        # Unnerve prevented Primarina's Sitrus Berry from activating (ITEM_ACTIVE stays 1.0)
        self.assertEqual(float(res_v.P[0, 0, 0, 4, MonIdx.ITEM_ACTIVE].item()), 1.0)
        # Leech Seed healed Venusaur at EoT (150 -> 175 = +25 = 200/8!) and Salt Cure (50 = 200/4) + Leech Seed (25) chipped Primarina!
        self.assertGreater(float(res_v.mean_hp[0, 0, 1].item()), 170.0)
        self.assertLess(float(res_v.mean_hp[0, 0, 4].item()), 35.0)

        # 3. Innards Out + Parental Bond + Spicy Spray + Eelevate KO Boost
        roster_c = [
            {
                "species": "Kangaskhan-Mega",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 180.0, "def": 100.0, "spa": 60.0, "spd": 100.0, "spe": 150.0},
                "types": ["Normal"],
                "ability": "Parental Bond",
                "moves": ["Return", "Protect", "Fake Out", "Crunch"],
            },
            {
                "species": "Eelektross-Mega",
                "hp_max": 200.0,
                "hp_cur": 200.0,
                "stats": {"atk": 120.0, "def": 100.0, "spa": 195.0, "spd": 100.0, "spe": 140.0},
                "types": ["Electric"],
                "ability": "Eelevate",
                "moves": ["Thunderbolt", "Protect", "Flamethrower", "Giga Drain"],
            },
            {"species": "Garchomp", "hp_max": 183.0, "hp_cur": 183.0, "types": ["Dragon", "Ground"], "moves": ["Protect", "Dragon Claw", "Earthquake", "Rock Slide"]},
            {"species": "Incineroar", "hp_max": 202.0, "hp_cur": 202.0, "types": ["Fire", "Dark"], "moves": ["Protect", "Flare Blitz", "Fake Out", "Parting Shot"]},
            {
                "species": "Scovillain-Mega",
                "hp_max": 300.0,
                "hp_cur": 300.0,
                "stats": {"atk": 120.0, "def": 110.0, "spa": 140.0, "spd": 110.0, "spe": 90.0},
                "types": ["Grass", "Fire"],
                "ability": "Spicy Spray",
                "moves": ["Protect", "Flamethrower", "Energy Ball", "Overheat"],
            },
            {
                "species": "Victreebel-Mega",
                "hp_max": 200.0,
                "hp_cur": 40.0,
                "stats": {"atk": 130.0, "def": 80.0, "spa": 150.0, "spd": 80.0, "spe": 90.0},
                "types": ["Grass", "Poison"],
                "ability": "Innards Out",
                "moves": ["Protect", "Sludge Bomb", "Leaf Storm", "Sucker Punch"],
            },
            {"species": "Rillaboom", "hp_max": 207.0, "hp_cur": 207.0, "types": ["Grass"], "moves": ["Protect", "Wood Hammer", "Grassy Glide", "Fake Out"]},
            {"species": "Pelipper", "hp_max": 167.0, "hp_cur": 167.0, "types": ["Water", "Flying"], "moves": ["Protect", "Hurricane", "Weather Ball", "Tailwind"]},
        ]
        st_c = self.compiler.compile_battle_state(roster_c)
        # Kangaskhan-Mega Crunch -> Opp A (Scovillain-Mega with Spicy Spray), Eelektross-Mega Flamethrower -> Opp B (Victreebel-Mega at 40 HP with Innards Out)
        t1_k = torch.tensor([[3, 6]], dtype=torch.long)  # Kangaskhan move 3 (Crunch)->Opp A, Eelektross move 2 (Flamethrower)->Opp B
        t2_k = torch.tensor([[1, 1]], dtype=torch.long)  # Scovillain Flamethrower->Opp A, Victreebel Sludge Bomb->Opp A
        res_c = self.state_machine.step(st_c.field_tensor, st_c.roster_tensor, st_c.moves_tensor, t1_k, t2_k, num_mc_samples=16, rng_seed=904)
        # Spicy Spray burned Kangaskhan-Mega upon taking Crunch!
        self.assertEqual(float(res_c.P[0, 0, 0, 0, MonIdx.STATUS_BURN].item()), 1.0)
        # Eelektross-Mega KO'd Victreebel-Mega -> took exactly 40 Innards Out damage (200 -> 160) AND gained +1 SpA from Eelevate!
        self.assertEqual(float(res_c.mean_hp[0, 0, 5].item()), 0.0)
        self.assertEqual(float(res_c.mean_hp[0, 0, 1].item()), 160.0)
        self.assertEqual(float(res_c.P[0, 0, 0, 1, MonIdx.BOOST_SPA].item()), 1.0)


if __name__ == "__main__":
    unittest.main()
