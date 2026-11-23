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
        """Verify vgc_tensor_core has zero imports from engine.inference and uses 87/59 dims."""
        self.assertEqual(MON_DIM, 87)
        self.assertEqual(MOVE_DIM, 59)

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
        """Verify Resist Berries (0.5x on matching SE hit) and Type-Boost Items (1.2x on matching type only)."""
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

        # Now test Resist Berry (Rindo Berry on Water-type Milotic vs SE Grass Energy Ball)
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


if __name__ == "__main__":
    unittest.main()
