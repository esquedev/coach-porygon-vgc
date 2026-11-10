# -*- coding: utf-8 -*-
"""
Showdown Replay Verification Suite: aws_secret vs asfdiha (Game 1)
===================================================================
"""

from __future__ import annotations

import unittest
import numpy as np

from vgc_tensor_core.replay_unroller import ReplayTurnExpectation, ShowdownReplayUnroller
from vgc_tensor_core.schema_and_tables import (
    AbilityID,
    BilinearLookupTables,
    FIELD_DIM,
    FieldIdx,
    HAS_TORCH,
    ItemID,
    MON_DIM,
    MOVE_DIM,
    MOVES_PER_MON,
    MonIdx,
    MoveIdx,
    ROSTER_SLOTS,
    SLOT_P1A,
    SLOT_P1B,
    SLOT_P1_BENCH1,
    SLOT_P1_BENCH2,
    SLOT_P2A,
    SLOT_P2B,
    SLOT_P2_BENCH1,
    SLOT_P2_BENCH2,
    TERRAIN_TO_IDX,
    TYPE_TO_IDX,
    TargetType,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
)
from vgc_tensor_core.state_machine import VgcTensorStateMachine
from vgc_tensor_core.state_translator import (
    ShowdownStateTranslator,
    SlotMetadata,
    TeamManifest,
)

if HAS_TORCH:
    import torch

def parse_showdown_to_english(wire_lines: list[str]) -> list[str]:
    """Lightweight parser to translate Showdown wire protocol into human-readable English."""
    english_log = []
    
    def clean_name(raw: str) -> str:
        return raw.split(":", 1)[1].strip() if ":" in raw else raw

    for line in wire_lines:
        if not line.startswith("|"):
            continue
        
        parts = line.split("|")[1:]
        if not parts:
            continue
            
        tag = parts[0]
        if tag == "turn":
            english_log.append(f"\n--- Turn {parts[1]} Actions ---")
        elif tag == "switch":
            incoming = parts[2].split(",")[0]
            english_log.append(f"{clean_name(parts[1])} switched out for {incoming}!")
        elif tag == "move":
            actor, move = clean_name(parts[1]), parts[2]
            target = f" on {clean_name(parts[3])}" if len(parts) > 3 and parts[3] else ""
            english_log.append(f"{actor} used {move}{target}!")
        elif tag == "-damage":
            english_log.append(f"{clean_name(parts[1])} took damage! (HP: {parts[2]})")
        elif tag == "-heal":
            english_log.append(f"{clean_name(parts[1])} restored some HP.")
        elif tag == "faint":
            english_log.append(f"{clean_name(parts[1])} fainted!")
        elif tag == "cant":
            reason = "flinched and couldn't move" if parts[2] == "flinch" else f"couldn't move ({parts[2]})"
            english_log.append(f"{clean_name(parts[1])} {reason}!")
        elif tag == "-mega":
            english_log.append(f"{clean_name(parts[1])} Mega Evolved into {parts[2]}!")
        elif tag in ("-weather", "-fieldstart"):
            effect = parts[1].replace("move: ", "")
            english_log.append(f"The field changed to {effect}!")

    return english_log

def _build_game1_manifest() -> TeamManifest:
    return TeamManifest(
        slots={
            SLOT_P1A: SlotMetadata(species="Raichu", mega_species="Raichu-Mega-X", item="Mega Stone", ability="Electric Surge", moves=["Fake Out", "Volt Tackle", "Protect", "Volt Switch"]),
            SLOT_P1B: SlotMetadata(species="Kingambit", item="Focus Sash", ability="Defiant", moves=["Kowtow Cleave", "Iron Head", "Sucker Punch", "Protect"]),
            SLOT_P1_BENCH1: SlotMetadata(species="Garchomp", item="Clear Amulet", ability="Rough Skin", moves=["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]),
            SLOT_P1_BENCH2: SlotMetadata(species="Charizard", moves=["Heat Wave", "Air Slash", "Solar Beam", "Protect"]),
            SLOT_P2A: SlotMetadata(species="Rillaboom", item="Assault Vest", ability="Grassy Surge", moves=["Grassy Glide", "Wood Hammer", "Fake Out", "U-turn"]),
            SLOT_P2B: SlotMetadata(species="Charizard", mega_species="Charizard-Mega-Y", item="Mega Stone", ability="Drought", moves=["Heat Wave", "Solar Beam", "Air Slash", "Protect"]),
            SLOT_P2_BENCH1: SlotMetadata(species="Raichu", item="Life Orb", ability="Lightning Rod", moves=["Thunderbolt", "Volt Switch", "Protect", "Fake Out"]),
            SLOT_P2_BENCH2: SlotMetadata(species="Basculegion-F", moves=["Wave Crash", "Shadow Ball", "Ice Beam", "Protect"]),
        }
    )

def _build_game1_initial_state(tables: BilinearLookupTables, device: str):
    F = np.zeros((FIELD_DIM,), dtype=np.float32)
    P = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
    M = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

    F[FieldIdx.WEATHER_START + WEATHER_TO_IDX["clear"]] = 1.0
    F[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX["grassy"]] = 1.0
    F[FieldIdx.TERRAIN_TURNS] = 5.0

    # Player 1
    P[SLOT_P1A, MonIdx.HP_CUR] = 135.0
    P[SLOT_P1A, MonIdx.HP_MAX] = 135.0
    P[SLOT_P1A, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P1A, MonIdx.STAT_ATK] = 142.0
    P[SLOT_P1A, MonIdx.STAT_DEF] = 75.0
    P[SLOT_P1A, MonIdx.STAT_SPA] = 110.0
    P[SLOT_P1A, MonIdx.STAT_SPD] = 100.0
    P[SLOT_P1A, MonIdx.STAT_SPE] = 178.0
    P[SLOT_P1A, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P1A, MonIdx.TYPE1_START + TYPE_TO_IDX["electric"]] = 1.0
    P[SLOT_P1A, MonIdx.ITEM_ID] = float(ItemID.MEGA_STONE)
    P[SLOT_P1A, MonIdx.ITEM_ACTIVE] = 1.0
    P[SLOT_P1A, MonIdx.CAN_MEGA] = 1.0
    P[SLOT_P1A, MonIdx.MEGA_ABILITY_ID] = float(AbilityID.ELECTRIC_SURGE)
    P[SLOT_P1A, MonIdx.MEGA_ATK] = 142.0
    P[SLOT_P1A, MonIdx.MEGA_DEF] = 75.0
    P[SLOT_P1A, MonIdx.MEGA_SPA] = 110.0
    P[SLOT_P1A, MonIdx.MEGA_SPD] = 100.0
    P[SLOT_P1A, MonIdx.MEGA_SPE] = 178.0
    P[SLOT_P1A, MonIdx.GROUNDED_FLAG] = 1.0

    M[SLOT_P1A, 0, MoveIdx.BASE_POWER] = 40.0
    M[SLOT_P1A, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P1A, 0, MoveIdx.PRIORITY] = 3.0
    M[SLOT_P1A, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["normal"]] = 1.0
    M[SLOT_P1A, 0, MoveIdx.CAT_PHYSICAL] = 1.0
    M[SLOT_P1A, 0, MoveIdx.FLINCH_CHANCE] = 1.0
    M[SLOT_P1A, 0, MoveIdx.FIRST_TURN_ONLY] = 1.0
    M[SLOT_P1A, 1, MoveIdx.BASE_POWER] = 120.0
    M[SLOT_P1A, 1, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P1A, 1, MoveIdx.TYPE_START + TYPE_TO_IDX["electric"]] = 1.0
    M[SLOT_P1A, 1, MoveIdx.CAT_PHYSICAL] = 1.0

    P[SLOT_P1B, MonIdx.HP_CUR] = 176.0
    P[SLOT_P1B, MonIdx.HP_MAX] = 176.0
    P[SLOT_P1B, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P1B, MonIdx.STAT_ATK] = 205.0
    P[SLOT_P1B, MonIdx.STAT_DEF] = 140.0
    P[SLOT_P1B, MonIdx.STAT_SPA] = 72.0
    P[SLOT_P1B, MonIdx.STAT_SPD] = 105.0
    P[SLOT_P1B, MonIdx.STAT_SPE] = 70.0
    P[SLOT_P1B, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P1B, MonIdx.TYPE1_START + TYPE_TO_IDX["dark"]] = 1.0
    P[SLOT_P1B, MonIdx.TYPE2_START + TYPE_TO_IDX["steel"]] = 1.0
    P[SLOT_P1B, MonIdx.ITEM_ID] = float(ItemID.FOCUS_SASH)
    P[SLOT_P1B, MonIdx.ITEM_ACTIVE] = 1.0
    P[SLOT_P1B, MonIdx.ABILITY_ID] = float(AbilityID.DEFIANT)
    P[SLOT_P1B, MonIdx.GROUNDED_FLAG] = 1.0

    M[SLOT_P1B, 0, MoveIdx.BASE_POWER] = 85.0
    M[SLOT_P1B, 0, MoveIdx.ACCURACY] = 1.01
    M[SLOT_P1B, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["dark"]] = 1.0
    M[SLOT_P1B, 0, MoveIdx.CAT_PHYSICAL] = 1.0
    M[SLOT_P1B, 2, MoveIdx.BASE_POWER] = 70.0
    M[SLOT_P1B, 2, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P1B, 2, MoveIdx.PRIORITY] = 1.0
    M[SLOT_P1B, 2, MoveIdx.TYPE_START + TYPE_TO_IDX["dark"]] = 1.0
    M[SLOT_P1B, 2, MoveIdx.CAT_PHYSICAL] = 1.0
    M[SLOT_P1B, 3, MoveIdx.PRIORITY] = 4.0
    M[SLOT_P1B, 3, MoveIdx.PROTECT_TYPE] = 1.0
    M[SLOT_P1B, 3, MoveIdx.TARGET_TYPE] = float(TargetType.SELF)

    P[SLOT_P1_BENCH1, MonIdx.HP_CUR] = 184.0
    P[SLOT_P1_BENCH1, MonIdx.HP_MAX] = 184.0
    P[SLOT_P1_BENCH1, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P1_BENCH1, MonIdx.STAT_SPE] = 169.0
    P[SLOT_P1_BENCH1, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P1_BENCH1, MonIdx.TYPE1_START + TYPE_TO_IDX["dragon"]] = 1.0
    P[SLOT_P1_BENCH1, MonIdx.TYPE2_START + TYPE_TO_IDX["ground"]] = 1.0

    # Player 2
    P[SLOT_P2A, MonIdx.HP_CUR] = 176.0
    P[SLOT_P2A, MonIdx.HP_MAX] = 176.0
    P[SLOT_P2A, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P2A, MonIdx.STAT_ATK] = 194.0
    P[SLOT_P2A, MonIdx.STAT_DEF] = 110.0
    P[SLOT_P2A, MonIdx.STAT_SPE] = 105.0
    P[SLOT_P2A, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P2A, MonIdx.TYPE1_START + TYPE_TO_IDX["grass"]] = 1.0
    P[SLOT_P2A, MonIdx.ABILITY_ID] = float(AbilityID.GRASSY_SURGE)
    P[SLOT_P2A, MonIdx.GROUNDED_FLAG] = 1.0

    P[SLOT_P2B, MonIdx.HP_CUR] = 154.0
    P[SLOT_P2B, MonIdx.HP_MAX] = 154.0
    P[SLOT_P2B, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P2B, MonIdx.STAT_SPA] = 161.0
    P[SLOT_P2B, MonIdx.STAT_DEF] = 98.0
    P[SLOT_P2B, MonIdx.STAT_SPE] = 167.0
    P[SLOT_P2B, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P2B, MonIdx.TYPE1_START + TYPE_TO_IDX["fire"]] = 1.0
    P[SLOT_P2B, MonIdx.TYPE2_START + TYPE_TO_IDX["flying"]] = 1.0
    P[SLOT_P2B, MonIdx.ITEM_ID] = float(ItemID.MEGA_STONE)
    P[SLOT_P2B, MonIdx.ITEM_ACTIVE] = 1.0
    P[SLOT_P2B, MonIdx.CAN_MEGA] = 1.0
    P[SLOT_P2B, MonIdx.MEGA_ABILITY_ID] = float(AbilityID.DROUGHT)
    P[SLOT_P2B, MonIdx.MEGA_ATK] = 113.0
    P[SLOT_P2B, MonIdx.MEGA_DEF] = 98.0
    P[SLOT_P2B, MonIdx.MEGA_SPA] = 211.0
    P[SLOT_P2B, MonIdx.MEGA_SPD] = 135.0
    P[SLOT_P2B, MonIdx.MEGA_SPE] = 167.0
    P[SLOT_P2B, MonIdx.GROUNDED_FLAG] = 0.0

    M[SLOT_P2B, 0, MoveIdx.BASE_POWER] = 95.0
    M[SLOT_P2B, 0, MoveIdx.ACCURACY] = 0.90
    M[SLOT_P2B, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["fire"]] = 1.0
    M[SLOT_P2B, 0, MoveIdx.CAT_SPECIAL] = 1.0
    M[SLOT_P2B, 0, MoveIdx.TARGET_TYPE] = float(TargetType.ALL_ADJACENT_FOES)

    P[SLOT_P2_BENCH1, MonIdx.HP_CUR] = 135.0
    P[SLOT_P2_BENCH1, MonIdx.HP_MAX] = 135.0
    P[SLOT_P2_BENCH1, MonIdx.ALIVE_FLAG] = 1.0
    P[SLOT_P2_BENCH1, MonIdx.STAT_DEF] = 75.0
    P[SLOT_P2_BENCH1, MonIdx.STAT_SPA] = 142.0
    P[SLOT_P2_BENCH1, MonIdx.STAT_SPE] = 178.0
    P[SLOT_P2_BENCH1, MonIdx.STATUS_HEALTHY] = 1.0
    P[SLOT_P2_BENCH1, MonIdx.TYPE1_START + TYPE_TO_IDX["electric"]] = 1.0

    M[SLOT_P2_BENCH1, 0, MoveIdx.BASE_POWER] = 90.0
    M[SLOT_P2_BENCH1, 0, MoveIdx.ACCURACY] = 1.0
    M[SLOT_P2_BENCH1, 0, MoveIdx.TYPE_START + TYPE_TO_IDX["electric"]] = 1.0
    M[SLOT_P2_BENCH1, 0, MoveIdx.CAT_SPECIAL] = 1.0

    if HAS_TORCH and device.startswith("cuda"):
        return torch.from_numpy(F).to(device), torch.from_numpy(P).to(device), torch.from_numpy(M).to(device)
    return F, P, M


class TestShowdownReplayVerifier(unittest.TestCase):
    def setUp(self) -> None:
        self.device = "cuda:0" if (HAS_TORCH and torch.cuda.is_available()) else "cpu"
        self.tables = build_bilinear_lookup_tables(device=self.device)
        self.state_machine = VgcTensorStateMachine(device=self.device)
        self.manifest = _build_game1_manifest()
        self.translator = ShowdownStateTranslator(manifest=self.manifest)
        self.unroller = ShowdownReplayUnroller(self.state_machine, self.translator)

    # ---------------------------------------------------------
    # TEST 1: Verificar el registro de Showdown (Turno 1)
    # ---------------------------------------------------------
    def test_aws_secret_vs_asfdiha_game1_replay(self) -> None:
        curr_F, curr_P, curr_M = _build_game1_initial_state(self.tables, self.device)

        t1_exp = ReplayTurnExpectation(
            turn=1,
            p1_choices=(16, 0),
            p2_choices=(24, 12),
            expected_damages={"p2b": (10.0, 20.0), "p2a": (65.0, 100.0)},
            expected_flinches=["p2b"],
        )

        step1, cp1, dual_log = self.unroller.step_and_verify_turn(curr_F, curr_P, curr_M, t1_exp)
        
        print("\n\n" + "="*60)
        print("                 TURN 1 OUTPUT")
        print("="*60)
        print("\n".join(cp1.human_readable_log))
        
    # ---------------------------------------------------------
    # TEST 2: Validar los 16 daños simultáneos de Monte Carlo
    # ---------------------------------------------------------
    def test_all_mc_damage_rolls(self) -> None:
        rng_seeds_to_test = [42, 999]
        for seed in rng_seeds_to_test:
            curr_F, curr_P, curr_M = _build_game1_initial_state(self.tables, self.device)
            p1_choices = np.array([[16, 0]], dtype=np.int64)
            p2_choices = np.array([[24, 12]], dtype=np.int64)
            
            p1_c_t = torch.tensor(p1_choices, device=self.device) if HAS_TORCH else p1_choices
            p2_c_t = torch.tensor(p2_choices, device=self.device) if HAS_TORCH else p2_choices

            step_res = self.state_machine.step(curr_F, curr_P, curr_M, p1_c_t, p2_c_t, num_mc_samples=16, rng_seed=seed)
            P_mc = step_res.P.detach().cpu().numpy()[0, 0] if HAS_TORCH else np.asarray(step_res.P)[0, 0]
                
            for k in range(16):
                charizard_dmg = ((154.0 - P_mc[k, SLOT_P2B, MonIdx.HP_CUR]) / 154.0) * 100.0
                raichu_dmg = ((135.0 - P_mc[k, SLOT_P2A, MonIdx.HP_CUR]) / 135.0) * 100.0
                self.assertTrue(10.0 <= charizard_dmg <= 20.0)
                self.assertTrue(65.0 <= raichu_dmg <= 100.0)

    # ---------------------------------------------------------
    # TEST 3: Empates de velocidad, log de Turno 2 y Monte Carlo
    # ---------------------------------------------------------
    def test_turn2_monte_carlo_edge_cases(self) -> None:
        """
        Runs Turn 2 for logging, then across 12,000 different RNG seeds (192,000 parallel timelines)
        to evaluate exact fractional KO probabilities and Speed Tie Jitter flips.
        """
        curr_F, curr_P, curr_M = _build_game1_initial_state(self.tables, self.device)
        
        p1_c1 = torch.tensor([[16, 0]], dtype=torch.long, device=self.device) if HAS_TORCH else np.array([[16, 0]])
        p2_c1 = torch.tensor([[24, 12]], dtype=torch.long, device=self.device) if HAS_TORCH else np.array([[24, 12]])
        
        step1 = self.state_machine.step(curr_F, curr_P, curr_M, p1_c1, p2_c1, num_mc_samples=16)

        # Extraer la línea temporal K=0 como la realidad base para encadenar
        F_t2 = step1.F[:, :, 0, :]
        P_t2 = step1.P[:, :, 0, :, :]
        M_t2 = step1.M_moves[:, :, 0, :, :, :]

        # Turn 2 Actions
        # P1: Raichu Volt Tackle (Opp B -> +4 = 5), Kingambit Sucker Punch (Opp B -> +4 = 6)
        # P2: Raichu Thunderbolt (Opp B -> +4 = 4), Charizard Heat Wave (Spread -> +0 = 0)
        p1_c2_t = torch.tensor([[5, 6]], dtype=torch.long, device=self.device) if HAS_TORCH else np.array([[5, 6]])
        p2_c2_t = torch.tensor([[4, 0]], dtype=torch.long, device=self.device) if HAS_TORCH else np.array([[4, 0]])

        # =========================================================
        # 1. EJECUCIÓN ÚNICA PARA OBTENER EL LOG LEGIBLE (Turno 2)
        # =========================================================
        t2_exp = ReplayTurnExpectation(
            turn=2,
            p1_choices=(5, 6),
            p2_choices=(4, 0),
            expected_damages={
                "p2b": (0.0, 100.0),
                "p1b": (0.0, 100.0),
            },
            expected_flinches=[],
        )

        step2_log, cp2, dual_log2 = self.unroller.step_and_verify_turn(
            F_t2, P_t2, M_t2, t2_exp, num_mc_samples=16
        )
        
        print("\n\n" + "="*70)
        print("                 TURN 2: HUMAN READABLE OUTPUT")
        print("="*70)
        print("\n".join(cp2.human_readable_log))
        print("="*70 + "\n\n")

        # =========================================================
        # 2. PRUEBA DE ESTRÉS MONTE CARLO (12,000 Semillas)
        # =========================================================
        seeds = range(12000)
        
        p1a_wins_tie = 0
        p2a_wins_tie = 0
        kingambit_ko_sum = 0.0
        charizard_ko_sum = 0.0

        print("     TURN 2: 12,000 SEEDS MONTE CARLO STRESS TEST (192,000 Timelines)")
        print("="*70)

        for seed in seeds:
            step2 = self.state_machine.step(
                F_t2, P_t2, M_t2, p1_c2_t, p2_c2_t, num_mc_samples=16, rng_seed=seed
            )
            
            notes = step2.pre_attack.speed_tie_notes
            if len(notes) > 0 and "wins tie-break" in notes[0]:
                if "P1A(Slot0) wins tie-break" in notes[0]:
                    p1a_wins_tie += 1
                elif "P2A(Slot4) wins tie-break" in notes[0]:
                    p2a_wins_tie += 1
                        
            f_prob = step2.faint_prob.detach().cpu().numpy()[0, 0] if HAS_TORCH else step2.faint_prob[0, 0]
            kingambit_ko_sum += f_prob[SLOT_P1B] * 100.0
            charizard_ko_sum += f_prob[SLOT_P2B] * 100.0
            
            if seed > 0 and seed % 2000 == 0:
                print(f"Processed {seed} / 12000 seeds...")

        print(f"\n--- FINAL RESULTS ACROSS 12,000 SEEDS ---")
        print(f"Speed Tie Wins -> Raichu-Mega-X (P1): {p1a_wins_tie} | Raichu Y (P2): {p2a_wins_tie}")
        print(f"Average KO Odds -> Kingambit: {kingambit_ko_sum / 12000:.2f}% | Charizard: {charizard_ko_sum / 12000:.2f}%")
        print("="*70 + "\n\n")

        self.assertGreater(p1a_wins_tie, 5000, "P1A won significantly less than expected.")
        self.assertGreater(p2a_wins_tie, 5000, "P2A won significantly less than expected.")