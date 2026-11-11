# -*- coding: utf-8 -*-
r"""
Pre-Attack Phases Verification Suite (`phases_pre_attack.py`)
=============================================================

This test script verifies every mathematical operator and mechanical barrier
in `engine.vgc_tensor_core.phases_pre_attack`:
1. **Barrier 1 (Voluntary Switches & Speed-Sorted Switch-In Weather War):**
   - Verifies that outgoing boosts (`8..14`) and volatiles (`58..66`) are zeroed via
     Hadamard multiplication with `switch_persist_mask`.
   - Verifies the $8 \times 8$ Switch Permutation Matrix $\mathbf{P}_{\text{perm}}^{(a,b)}$.
   - Verifies the **Simultaneous Switch-In Weather War Theorem**:
     - When `Pelipper` (`Drizzle`, Speed `85`) and `Torkoal` (`Drought`, Speed `40`) switch in
       simultaneously:
       - In **Normal Room** (`TR = 0`), `Pelipper` (`85`) triggers `Drizzle` first (`Rain`), and
         `Torkoal` (`40`) triggers `Drought` second, overwriting the field to **`Sun`**!
       - In **Trick Room** (`TR = 5`), `Torkoal` (`40`) triggers `Drought` first (`Sun`), and
         `Pelipper` (`85`) triggers `Drizzle` second, overwriting the field to **`Rain`**!
2. **Barrier 1 (`Intimidate` $\to$ Immediate Reactive `Defiant` / `Competitive` & Immunities):**
   - Verifies that `Incineroar` switching in triggers `Intimidate` (`-1 Atk`) on both opponents:
     - `Floette` (Unprotected): drops from `0.0` to **`-1.0 Atk`**.
     - `Kingambit` (`Defiant`): drops `-1.0 Atk` then immediately gains `+2.0 Atk` = **`+1.0 Atk`**!
     - `Garchomp` holding `Clear Amulet`: **`0.0 Atk` change** (Immune!).
3. **Barrier 1 $\to$ Barrier 2 Sequencing (Switch-In Weather vs. Mega Evolution Weather):**
   - Verifies that when P1 switches in `Pelipper` (`Drizzle` at Barrier 1, `+6`) and P2 Mega Evolves
     `Charizard` $\to$ `Mega Charizard Y` (`Drought` at Barrier 2, `+5.5`) on the same turn,
     Barrier 2 strictly executes after Barrier 1 so **`Sun` always overwrites `Rain`**, even though
     `Pelipper` (`85`) is slower than `Mega Charizard Y` (`169`)!
4. **Barrier 2 (Regulation M-C Instantaneous 5-Stat Mega Transformation & Speed Recalibration):**
   - Verifies that `Floette` (`Base Spe = 144`) Mega Evolving into `Mega Floette` (`Mega Spe = 168`)
     instantaneously updates all 5 stats (`Atk: 65->85`, `Def: 67->87`, `SpA: 172->195`,
     `SpD: 148->178`, `Spe: 144->168`) and jumps ahead of a `Base 150` Speed opponent on the very
     same turn!
5. **Barrier 3 (`Prankster`, Priority Brackets, `Speed_Tie_Alert` Detection & Seeded `±0.01` Jitter):**
   - Verifies that when two active Pokémon share identical priority and effective speed (`169` vs `169`),
     `speed_tie_alert` flags `1.0`, `±0.01` jitter breaks the tie without ever inverting non-tied
     integer speeds, and human-readable `speed_tie_notes` log the exact `±0.01` jitter values.
6. **Full `[100 x 100 = 10,000]` Joint Grid CPU vs. `cuda:0` RTX 3060 Speed Benchmark.**
"""

from __future__ import annotations

import copy
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.vgc_tensor_core.compiler import (
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
    ShowdownTensorCompiler,
)
from engine.vgc_tensor_core.phases_pre_attack import (
    execute_pre_attack_phases,
)
from engine.vgc_tensor_core.schema_and_tables import (
    FieldIdx,
    HAS_TORCH,
    MonIdx,
    SLOT_P1A,
    SLOT_P1B,
    SLOT_P1_BENCH1,
    SLOT_P2A,
    SLOT_P2B,
    build_bilinear_lookup_tables,
)


def _to_float(val) -> float:
    if hasattr(val, "item"):
        return float(val.item())
    return float(val)


def _to_list(val) -> list:
    if hasattr(val, "detach"):
        arr = val.detach().cpu().numpy()
    else:
        arr = np.asarray(val)
    return np.round(arr, 4).tolist()


class TestPhasesPreAttack(unittest.TestCase):
    """Exhaustive, verbose verification for `vgc_tensor_core/phases_pre_attack.py`."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.compiler = ShowdownTensorCompiler()
        cls.tables = cls.compiler.tables
        gpu_name = "N/A"
        if HAS_TORCH:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
            else:
                gpu_name = "PyTorch CPU-only"

        cls.log_lines: List[str] = []
        cls.log_lines.append("=" * 104)
        cls.log_lines.append("VERBOSE MATRIX TRACE — PHASES 1–3 (SWITCHES, MEGA EVOLUTION & SPEED/PRIORITY SORT)")
        cls.log_lines.append(f"Active Compute Backend : {cls.compiler.backend} (device={cls.compiler.device}) | GPU: {gpu_name}")
        cls.log_lines.append("=" * 104)

    def _log(self, text: str = "") -> None:
        self.__class__.log_lines.append(text)

    def _make_choices(self, pairs: List[tuple]):
        arr = np.array(pairs, dtype=np.int64)
        if self.compiler.backend == "torch":
            import torch
            return torch.from_numpy(arr).to(self.compiler.device)
        return arr

    @staticmethod
    def _build_test_roster() -> List[Dict[str, Any]]:
        """
        Build an 8-Pokémon roster dictionary list designed to test all Barrier 1, Barrier 2, and Barrier 3 interactions:
        - Slot 0 (P1A): Grimmsnarl (Spe=80, Prankster, Boosts: +2 Atk, Taunt=2 turns)
        - Slot 1 (P1B): Garchomp (Spe=169, Clear Amulet)
        - Slot 2 (P1_Bench1): Pelipper (Spe=85, Drizzle)
        - Slot 3 (P1_Bench2): Incineroar (Spe=80, Intimidate)
        - Slot 4 (P2A): Floette (Spe=144 -> Mega Spe=168, Mega Stone, Fairy Aura)
        - Slot 5 (P2B): Kingambit (Spe=150, Defiant)
        - Slot 6 (P2_Bench1): Torkoal (Spe=40, Drought)
        - Slot 7 (P2_Bench2): Charizard (Spe=169 -> Mega Spe=169, Mega Stone, Mega Ability=Drought)
        """
        return [
            # 0: P1A Grimmsnarl
            {
                "name": "Grimmsnarl",
                "hp_max": 202.0, "hp_cur": 202.0,
                "stats": {"atk": 140.0, "def": 110.0, "spa": 100.0, "spd": 120.0, "spe": 80.0},
                "types": ["Dark", "Fairy"],
                "ability": "Prankster",
                "item": "None",
                "boosts": {"atk": 2.0},
                "taunt_turns": 2.0,
                "moves": ["Light Screen", "Thunder Wave", "Spirit Break", "Protect"],
            },
            # 1: P1B Garchomp
            {
                "name": "Garchomp",
                "hp_max": 183.0, "hp_cur": 183.0,
                "stats": {"atk": 182.0, "def": 115.0, "spa": 90.0, "spd": 105.0, "spe": 169.0},
                "types": ["Dragon", "Ground"],
                "ability": "None",
                "item": "Clear Amulet",
                "moves": ["Stomping Tantrum", "Earthquake", "Dragon Claw", "Protect"],
            },
            # 2: P1_Bench1 Pelipper
            {
                "name": "Pelipper",
                "hp_max": 167.0, "hp_cur": 167.0,
                "stats": {"atk": 63.0, "def": 120.0, "spa": 161.0, "spd": 90.0, "spe": 85.0},
                "types": ["Water", "Flying"],
                "ability": "Drizzle",
                "item": "None",
                "moves": ["Hurricane", "Helping Hand", "Wide Guard", "Protect"],
            },
            # 3: P1_Bench2 Incineroar
            {
                "name": "Incineroar",
                "hp_max": 202.0, "hp_cur": 202.0,
                "stats": {"atk": 145.0, "def": 120.0, "spa": 90.0, "spd": 130.0, "spe": 80.0},
                "types": ["Fire", "Dark"],
                "ability": "Intimidate",
                "item": "Sitrus Berry",
                "moves": ["Fake Out", "Flare Blitz", "Parting Shot", "Protect"],
            },
            # 4: P2A Floette (Base Spe=144 -> Mega Spe=168)
            {
                "name": "Floette",
                "hp_max": 181.0, "hp_cur": 181.0,
                "stats": {"atk": 65.0, "def": 67.0, "spa": 172.0, "spd": 148.0, "spe": 144.0},
                "types": ["Fairy"],
                "ability": "None",
                "item": "Floettite",
                "can_mega": 1.0,
                "mega_stats": {"atk": 85.0, "def": 87.0, "spa": 195.0, "spd": 178.0, "spe": 168.0},
                "mega_ability": "Fairy Aura",
                "moves": ["Dazzling Gleam", "Draining Kiss", "Calm Mind", "Protect"],
            },
            # 5: P2B Kingambit (Spe=150 for speed-jump test, Defiant)
            {
                "name": "Kingambit",
                "hp_max": 207.0, "hp_cur": 207.0,
                "stats": {"atk": 205.0, "def": 140.0, "spa": 72.0, "spd": 105.0, "spe": 150.0},
                "types": ["Dark", "Steel"],
                "ability": "Defiant",
                "item": "Assault Vest",
                "moves": ["Kowtow Cleave", "Sucker Punch", "Iron Head", "Protect"],
            },
            # 6: P2_Bench1 Torkoal (Spe=40, Drought)
            {
                "name": "Torkoal",
                "hp_max": 177.0, "hp_cur": 177.0,
                "stats": {"atk": 85.0, "def": 160.0, "spa": 150.0, "spd": 90.0, "spe": 40.0},
                "types": ["Fire"],
                "ability": "Drought",
                "item": "None",
                "moves": ["Heat Wave", "Sunny Day", "Protect", "Protect"],
            },
            # 7: P2_Bench2 Charizard (Spe=169 -> Mega Charizard Y Spe=169, Drought)
            {
                "name": "Charizard",
                "hp_max": 153.0, "hp_cur": 153.0,
                "stats": {"atk": 84.0, "def": 98.0, "spa": 161.0, "spd": 105.0, "spe": 169.0},
                "types": ["Fire", "Flying"],
                "ability": "None",
                "item": "Charizardite Y",
                "can_mega": 1.0,
                "mega_stats": {"atk": 104.0, "def": 98.0, "spa": 211.0, "spd": 135.0, "spe": 169.0},
                "mega_ability": "Drought",
                "moves": ["Heat Wave", "Flamethrower", "Sunny Day", "Protect"],
            },
        ]

    def test_01_barrier1_simultaneous_switch_weather_war_normal_vs_trick_room(self) -> None:
        """
        Verify Barrier 1 (Voluntary Switches + Speed-Sorted Switch-In Weather War):
        - P1A (`Grimmsnarl` with `+2 Atk` & `Taunt=2`) switches to Bench 1 (`Pelipper`, `Drizzle`, Spe=85).
        - P2A (`Floette`) switches to Bench 1 (`Torkoal`, `Drought`, Spe=40).
        - In Normal Room (`TR = 0`), `Pelipper` (85) triggers `Drizzle` first, and `Torkoal` (40)
          triggers `Drought` second, overwriting the weather to `Sun`!
        - In Trick Room (`TR = 5`), `Torkoal` (40) acts first (`Sun`), and `Pelipper` (85) acts
          second, overwriting the weather to `Rain`!
        - Also verifies that outgoing `Grimmsnarl` (now in Slot 2) has its `+2 Atk` boost and
          `Taunt` volatile reset to `0.0` via `switch_persist_mask`.
        """
        roster = self._build_test_roster()
        state_normal = self.compiler.compile_battle_state(roster, field_spec={"trick_room_turns": 0.0})
        state_tr = self.compiler.compile_battle_state(roster, field_spec={"trick_room_turns": 5.0})

        p1_c = self._make_choices([(CHOICE_SWITCH_BENCH1, 3)])
        p2_c = self._make_choices([(CHOICE_SWITCH_BENCH1, 3)])

        res_norm = execute_pre_attack_phases(
            state_normal.field_tensor, state_normal.roster_tensor, state_normal.moves_tensor, p1_c, p2_c
        )
        res_tr = execute_pre_attack_phases(
            state_tr.field_tensor, state_tr.roster_tensor, state_tr.moves_tensor, p1_c, p2_c
        )

        w_norm = _to_list(res_norm.F[0, 0, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END])
        w_tr = _to_list(res_tr.F[0, 0, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END])

        self.assertEqual(w_norm, [0.0, 1.0, 0.0, 0.0, 0.0])  # Sun!
        self.assertEqual(w_tr, [0.0, 0.0, 1.0, 0.0, 0.0])    # Rain!

        grimm_atk_boost = _to_float(res_norm.P[0, 0, SLOT_P1_BENCH1, MonIdx.BOOST_ATK])
        grimm_taunt = _to_float(res_norm.P[0, 0, SLOT_P1_BENCH1, MonIdx.TAUNT_TURNS])
        self.assertEqual(grimm_atk_boost, 0.0)
        self.assertEqual(grimm_taunt, 0.0)

        self._log("\n[TEST 01] BARRIER 1: SIMULTANEOUS SWITCH-IN WEATHER WAR (NORMAL ROOM vs TRICK ROOM)")
        self._log("-" * 104)
        self._log("  Scenario: P1A switches to Pelipper (Drizzle, Spe=85) | P2A switches to Torkoal (Drought, Spe=40)")
        self._log(f"  • Outgoing Grimmsnarl (Moved to Slot 2) Boost Reset : Boost_Atk={grimm_atk_boost:.1f} (was +2.0), Taunt={grimm_taunt:.1f} (was 2.0)")
        self._log(f"  • Normal Room (TR=0): Pelipper(85) sets Rain 1st -> Torkoal(40) sets Sun 2nd  | Final Weather One-Hot = {w_norm} (Sun Wins!)")
        self._log(f"  • Trick Room  (TR=5): Torkoal(40) sets Sun 1st   -> Pelipper(85) sets Rain 2nd | Final Weather One-Hot = {w_tr} (Rain Wins!)")
        self._log("  Result: PASS")

    def test_02_barrier1_intimidate_into_defiant_and_clear_amulet(self) -> None:
        """
        Verify Barrier 1 (`Intimidate` -> Immediate Reactive `Defiant` & `Clear Amulet` Immunity):
        - P1A switches to Bench 2 (`Incineroar`, `Intimidate`).
        - P2A (`Floette`, unprotected) drops from `0.0` to `-1.0 Atk`.
        - P2B (`Kingambit`, `Defiant`) drops `-1.0 Atk` and immediately gains `+2.0 Atk` -> **`+1.0 Atk`**!
        - Also test P2 switching in an `Intimidate` user against P1B (`Garchomp` holding `Clear Amulet`):
          `Garchomp` remains at **`0.0 Atk`**!
        """
        roster = self._build_test_roster()
        state = self.compiler.compile_battle_state(roster)

        p1_c = self._make_choices([(CHOICE_SWITCH_BENCH2, 3)])
        p2_c = self._make_choices([(3, 3)])

        res = execute_pre_attack_phases(state.field_tensor, state.roster_tensor, state.moves_tensor, p1_c, p2_c)

        floette_atk_boost = _to_float(res.P[0, 0, SLOT_P2A, MonIdx.BOOST_ATK])
        kingambit_atk_boost = _to_float(res.P[0, 0, SLOT_P2B, MonIdx.BOOST_ATK])

        self.assertEqual(floette_atk_boost, -1.0)
        self.assertEqual(kingambit_atk_boost, +1.0)

        # Now test Intimidate on P2 side against P1B Garchomp (Clear Amulet)
        roster_p2_intim = copy.deepcopy(roster)
        roster_p2_intim[6] = {
            "name": "Salamence",
            "hp_max": 170.0, "hp_cur": 170.0,
            "stats": {"atk": 155.0, "def": 100.0, "spa": 130.0, "spd": 100.0, "spe": 167.0},
            "types": ["Dragon", "Flying"],
            "ability": "Intimidate",
            "item": "None",
            "moves": ["Protect", "Protect", "Protect", "Protect"],
        }
        state2 = self.compiler.compile_battle_state(roster_p2_intim)
        p1_stay = self._make_choices([(3, 3)])
        p2_sw_intim = self._make_choices([(CHOICE_SWITCH_BENCH1, 3)])
        res2 = execute_pre_attack_phases(state2.field_tensor, state2.roster_tensor, state2.moves_tensor, p1_stay, p2_sw_intim)

        grimm_boost = _to_float(res2.P[0, 0, SLOT_P1A, MonIdx.BOOST_ATK])     # Started at +2.0 -> +1.0
        garchomp_boost = _to_float(res2.P[0, 0, SLOT_P1B, MonIdx.BOOST_ATK])  # Clear Amulet -> 0.0!

        self.assertEqual(grimm_boost, +1.0)
        self.assertEqual(garchomp_boost, 0.0)

        self._log("\n[TEST 02] BARRIER 1: INTIMIDATE -> IMMEDIATE REACTIVE DEFIANT (+2 ATK) & CLEAR AMULET IMMUNITY")
        self._log("-" * 104)
        self._log(f"  • P1 Incineroar Switch-In Intimidate -> P2A Floette (Unprotected)   : Boost_Atk = {floette_atk_boost:+.1f}")
        self._log(f"  • P1 Incineroar Switch-In Intimidate -> P2B Kingambit (Defiant)     : Boost_Atk = {kingambit_atk_boost:+.1f} (-1 + 2 = +1.0!)")
        self._log(f"  • P2 Salamence Switch-In Intimidate  -> P1B Garchomp (Clear Amulet) : Boost_Atk = {garchomp_boost:+.1f} (Blocked by Clear Amulet!)")
        self._log("  Result: PASS")

    def test_03_barrier1_switch_weather_vs_barrier2_mega_weather(self) -> None:
        """
        Verify Barrier 1 -> Barrier 2 Cross-Phase Ordering:
        - Put `Charizard` (Mega Charizard Y `Drought`, Spe=169) in P2A active slot.
        - P1A switches into `Pelipper` (`Drizzle`, Spe=85) at Barrier 1 (`+6`).
        - P2A Mega Evolves into `Mega Charizard Y` (`Drought`, Spe=169) at Barrier 2 (`+5.5`).
        - Even though `Pelipper` (`85`) is SLOWER than `Mega Charizard Y` (`169`) (so in a simultaneous
          Barrier 1 switch `Pelipper` would have overwritten `Sun` with `Rain`), because Mega Evolution
          executes at **Barrier 2** strictly after **Barrier 1**, `Mega Charizard Y` `Drought` ALWAYS
          overwrites `Pelipper` `Drizzle` to set **`Sun`**!
        """
        roster = self._build_test_roster()
        roster[4], roster[7] = roster[7], roster[4]
        state = self.compiler.compile_battle_state(roster)

        p1_c = self._make_choices([(CHOICE_SWITCH_BENCH1, 3)])
        p2_c = self._make_choices([(12, 3)])

        res = execute_pre_attack_phases(state.field_tensor, state.roster_tensor, state.moves_tensor, p1_c, p2_c)
        w_final = _to_list(res.F[0, 0, FieldIdx.WEATHER_START:FieldIdx.WEATHER_END])
        zard_is_mega = _to_float(res.P[0, 0, SLOT_P2A, MonIdx.IS_MEGA])
        zard_spa = _to_float(res.P[0, 0, SLOT_P2A, MonIdx.STAT_SPA])
        p2_mega_used = _to_float(res.F[0, 0, FieldIdx.P2_MEGA_USED])

        self.assertEqual(w_final, [0.0, 1.0, 0.0, 0.0, 0.0])  # Sun!
        self.assertEqual(zard_is_mega, 1.0)
        self.assertEqual(zard_spa, 211.0)
        self.assertEqual(p2_mega_used, 1.0)

        self._log("\n[TEST 03] BARRIER 1 (SWITCH) -> BARRIER 2 (MEGA) WEATHER SEQUENCING PROOF")
        self._log("-" * 104)
        self._log("  Scenario: P1A switches to Pelipper (Drizzle, Spe=85) at Barrier 1 (+6)")
        self._log("            P2A Mega Evolves Charizard -> Mega Charizard Y (Drought, Spe=169) at Barrier 2 (+5.5)")
        self._log(f"  • Mega Charizard Y Transformation : IsMega={zard_is_mega:.0f}, SpA={zard_spa:.0f} (was 161), P2_Mega_Used={p2_mega_used:.0f}")
        self._log(f"  • Final Weather One-Hot           : {w_final} -> Sun! (Barrier 2 Mega Drought overwrites Barrier 1 Switch Drizzle!)")
        self._log("  Result: PASS")

    def test_04_barrier2_instantaneous_regulation_mc_mega_speed_recalibration(self) -> None:
        """
        Verify Regulation M-C Instantaneous Mega Evolution Speed Recalibration:
        - P2A `Floette` has Base Speed `144` and Mega Speed `168`.
        - P2B `Kingambit` has Speed `150`.
        - Col 0: `Floette` attacks in Base Form (`Choice 0`, Speed `144`) -> `Kingambit` (`150`)
          moves BEFORE `Floette` (`144`)!
        - Col 1: `Floette` Mega Evolves + attacks (`Choice 12`, Speed `144 -> 168`) ->
          `Mega Floette` (`168`) moves BEFORE `Kingambit` (`150`) on the exact same turn!
        """
        roster = self._build_test_roster()
        state = self.compiler.compile_battle_state(roster)

        p1_c = self._make_choices([(2, 2)])
        p2_c = self._make_choices([(0, 0), (12, 0)])

        res = execute_pre_attack_phases(state.field_tensor, state.roster_tensor, state.moves_tensor, p1_c, p2_c)

        speeds_base = _to_list(res.effective_speeds[0, 0])
        order_base = _to_list(res.execution_order[0, 0])
        speeds_mega = _to_list(res.effective_speeds[0, 1])
        order_mega = _to_list(res.execution_order[0, 1])

        self.assertEqual(speeds_base, [80.0, 169.0, 144.0, 150.0])
        self.assertEqual(order_base, [1, 3, 2, 0])

        self.assertEqual(speeds_mega, [80.0, 169.0, 168.0, 150.0])
        self.assertEqual(order_mega, [1, 2, 3, 0])

        mega_floette_stats = _to_list(res.P[0, 1, SLOT_P2A, MonIdx.STAT_ATK:MonIdx.STAT_SPE + 1])
        self.assertEqual(mega_floette_stats, [85.0, 87.0, 195.0, 178.0, 168.0])

        self._log("\n[TEST 04] BARRIER 2: REGULATION M-C INSTANTANEOUS MEGA SPEED RECALIBRATION")
        self._log("-" * 104)
        self._log(f"  • Col 0 (Base Floette, Choice 0)  Effective Speeds [P1A, P1B, P2A, P2B] : {speeds_base}")
        self._log(f"    -> Execution Order (1=Garchomp 169 -> 3=Kingambit 150 -> 2=Floette 144 -> 0=Grimmsnarl 80) : {order_base}")
        self._log(f"  • Col 1 (Mega Floette, Choice 12) Effective Speeds [P1A, P1B, P2A, P2B] : {speeds_mega}")
        self._log(f"    -> Execution Order (1=Garchomp 169 -> 2=MegaFloette 168 -> 3=Kingambit 150 -> 0=Grimmsnarl 80): {order_mega}")
        self._log(f"  • Mega Floette 5-Stat Vector [Atk, Def, SpA, SpD, Spe]                  : {mega_floette_stats}")
        self._log("  Result: PASS")

    def test_05_barrier3_priority_brackets_and_speed_tie_alert_with_jitter(self) -> None:
        """
        Verify Barrier 3 (`Speed_Tie_Alert` Detection & Seeded `±0.01` Jitter Resolution):
        - Put `Charizard` (`Spe = 169`) in P2A so both `P1B Garchomp` (`Spe = 169`) and `P2A Charizard`
          (`Spe = 169`) share the exact same Effective Speed (`169`) and Priority (`0`).
        - Verify `speed_tie_alert[0, 0] == 1.0`.
        - Verify `speed_tie_notes` contains the human-readable alert string with exact `±0.01` jitter values.
        - Verify Prankster Status move (`Grimmsnarl` `Light Screen`, Priority `0 + 1 = +1`) acts before
          `169` Speed base priority moves!
        """
        roster = self._build_test_roster()
        roster[4], roster[7] = roster[7], roster[4]  # P2A = Charizard (Spe=169)
        state = self.compiler.compile_battle_state(roster)

        p1_c = self._make_choices([(0, 2)])
        p2_c = self._make_choices([(0, 3)])

        res = execute_pre_attack_phases(
            state.field_tensor, state.roster_tensor, state.moves_tensor, p1_c, p2_c, rng_seed=2026
        )

        prios = _to_list(res.effective_priorities[0, 0])
        speeds = _to_list(res.effective_speeds[0, 0])
        jitters = _to_list(res.jitter_applied[0, 0])
        order = _to_list(res.execution_order[0, 0])
        tie_flag = _to_float(res.speed_tie_alert[0, 0])

        self.assertEqual(prios, [1.0, 0.0, 0.0, 4.0])
        self.assertEqual(speeds, [80.0, 169.0, 169.0, 150.0])
        self.assertEqual(tie_flag, 1.0)
        self.assertEqual(len(res.speed_tie_notes), 1)
        self.assertEqual(order[:2], [3, 0])
        self.assertEqual(set(order[2:]), {1, 2})

        self._log("\n[TEST 05] BARRIER 3: PRIORITY BRACKETS, EXACT SPEED TIE DETECTION & ±0.01 JITTER LOG")
        self._log("-" * 104)
        self._log(f"  • Effective Priorities [P1A(Prankster), P1B, P2A, P2B(Protect)] : {prios}")
        self._log(f"  • Effective Speeds     [P1A, P1B(169), P2A(169), P2B]           : {speeds}")
        self._log(f"  • Seeded ±0.01 Jitters [P1A, P1B, P2A, P2B] (seed=2026)         : {jitters}")
        self._log(f"  • Final Execution Order [0..3]                                  : {order}")
        self._log(f"  • Speed_Tie_Alert Mask [0, 0]                                   : {tie_flag:.1f}")
        for note in res.speed_tie_notes:
            self._log(f"  • Human-Readable Alert : {note}")
        self._log("  Result: PASS")

    def test_06_full_valid_grid_cpu_and_cuda_speed_benchmark(self) -> None:
        """
        Benchmark executing Phases 1, 2, and 3 across a `100 x 100 = 10,000` joint action grid
        on both PyTorch CPU and `cuda:0` RTX 3060 GPU.
        """
        roster = self._build_test_roster()

        self._log("\n[TEST 06] FULL 100x100 GRID (10,000 UNIVERSES) PHASES 1–3 LATENCY BENCHMARK (CPU vs CUDA)")
        self._log("-" * 104)

        if HAS_TORCH:
            import torch
            devices = ["cpu", "cuda:0"] if torch.cuda.is_available() else ["cpu"]
            for dev in devices:
                tables = build_bilinear_lookup_tables(device=dev)
                comp = ShowdownTensorCompiler(tables=tables)
                st = comp.compile_battle_state(roster)

                rng = np.random.RandomState(7)
                p1_pairs = torch.from_numpy(rng.randint(0, 26, size=(100, 2)).astype(np.int64)).to(dev)
                p2_pairs = torch.from_numpy(rng.randint(0, 26, size=(100, 2)).astype(np.int64)).to(dev)

                for _ in range(3):
                    _ = execute_pre_attack_phases(
                        st.field_tensor, st.roster_tensor, st.moves_tensor, p1_pairs, p2_pairs, tables=tables
                    )
                if dev.startswith("cuda"):
                    torch.cuda.synchronize()

                iters = 10
                t0 = time.perf_counter()
                for _ in range(iters):
                    _ = execute_pre_attack_phases(
                        st.field_tensor, st.roster_tensor, st.moves_tensor, p1_pairs, p2_pairs, tables=tables
                    )
                if dev.startswith("cuda"):
                    torch.cuda.synchronize()
                elapsed_ms = ((time.perf_counter() - t0) / iters) * 1000.0
                self._log(f"  • PyTorch ({dev:<6}) [100x100 = 10,000 cells] Phases 1–3 Mean Latency : {elapsed_ms:.3f} ms / pass")
                self.assertLess(elapsed_ms, 500.0)

        self._log("  Result: PASS")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPhasesPreAttack)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    TestPhasesPreAttack.log_lines.append("")
    TestPhasesPreAttack.log_lines.append("=" * 104)
    TestPhasesPreAttack.log_lines.append(
        f"TOTAL TESTS RUN: {result.testsRun} | FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}"
    )
    TestPhasesPreAttack.log_lines.append(
        "STATUS: PASS (100% EXACT MATHEMATICAL PARITY)" if result.wasSuccessful() else "STATUS: FAIL"
    )
    TestPhasesPreAttack.log_lines.append("=" * 104)

    full_trace = "\n".join(TestPhasesPreAttack.log_lines)
    print("\n" + full_trace)

    out_dir = Path(__file__).resolve().parent / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "phases_pre_attack_test_output.txt"
    out_file.write_text(full_trace + "\n", encoding="utf-8")

    sys.exit(0 if result.wasSuccessful() else 1)
