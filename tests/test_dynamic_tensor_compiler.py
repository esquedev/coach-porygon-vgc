# -*- coding: utf-8 -*-
"""Unit tests for the Programmatic Showdown-to-Tensor Compiler & 26x26 Action Pruner."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.parser import parse_showdown_chat_log, parse_showdown_paste
from engine.parser.models import ParsedBattle, ParsedTeam
from engine.state import TurnStateCompiler
from engine.vgc_tensor_core import (
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
    FIELD_DIM,
    FieldIdx,
    FieldOpID,
    MON_DIM,
    MOVE_DIM,
    MonIdx,
    MoveIdx,
    OverrideDefStat,
    OverrideOffStat,
    ROSTER_SLOTS,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    STATUS_TO_IDX,
    ShowdownTensorCompiler,
    TYPE_TO_IDX,
    TargetType,
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


class TestDynamicTensorCompiler(unittest.TestCase):
    """Verify programmatic on-the-fly move tensor compilation and 26x26 action pruning."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.state_compiler = TurnStateCompiler()
        cls.tensor_compiler = ShowdownTensorCompiler()

    def test_compile_all_564_duckdb_moves_on_the_fly(self) -> None:
        """Verify all 564 moves in DuckDB moves.jsonl compile programmatically into 56-float vectors."""
        all_moves = self.tensor_compiler.compile_all_showdown_moves()
        self.assertGreaterEqual(len(all_moves), 550)

        for name, vec in all_moves.items():
            self.assertEqual(vec.shape, (MOVE_DIM,), f"Move {name} has wrong shape")
            self.assertEqual(vec.dtype, np.float32)
            # Every move must have exactly 1 active Type One-Hot and 1 active Category One-Hot
            self.assertAlmostEqual(
                float(np.sum(vec[MoveIdx.TYPE_START:MoveIdx.TYPE_END])),
                1.0,
                places=5,
                msg=f"Move {name} type one-hot sum != 1.0",
            )
            self.assertAlmostEqual(
                float(np.sum(vec[MoveIdx.CAT_START:MoveIdx.CAT_END])),
                1.0,
                places=5,
                msg=f"Move {name} category one-hot sum != 1.0",
            )

    def test_programmatic_move_archetypes_from_duckdb(self) -> None:
        """Verify key VGC move mechanics are extracted programmatically from Showdown's schema."""
        c = self.tensor_compiler

        # 1. Heat Wave: Spread Fire Special, 95 BP, 90% acc, 10% Burn
        hw = c.compile_move_vector("Heat Wave")
        self.assertEqual(hw[MoveIdx.BASE_POWER], 95.0)
        self.assertAlmostEqual(hw[MoveIdx.ACCURACY], 0.90, places=4)
        self.assertEqual(hw[MoveIdx.TARGET_TYPE], float(TargetType.ALL_ADJACENT_FOES))
        self.assertEqual(hw[MoveIdx.TYPE_START + TYPE_TO_IDX["fire"]], 1.0)
        self.assertEqual(hw[MoveIdx.CAT_SPECIAL], 1.0)
        self.assertEqual(hw[MoveIdx.SEC_STATUS_START + STATUS_TO_IDX["burn"]], 1.0)
        self.assertAlmostEqual(hw[MoveIdx.SEC_STATUS_CHANCE], 0.10, places=4)

        # 2. Fake Out: +3 priority, 100% flinch, first-turn-only
        fo = c.compile_move_vector("Fake Out")
        self.assertEqual(fo[MoveIdx.BASE_POWER], 40.0)
        self.assertEqual(fo[MoveIdx.PRIORITY], 3.0)
        self.assertEqual(fo[MoveIdx.FLINCH_CHANCE], 1.0)
        self.assertEqual(fo[MoveIdx.FIRST_TURN_ONLY], 1.0)
        self.assertEqual(fo[MoveIdx.FIELD_OP_ID], float(FieldOpID.FAKE_OUT))

        # 3. Parting Shot: Status pivot, sound move, -1 Atk / -1 SpA on target
        ps = c.compile_move_vector("Parting Shot")
        self.assertEqual(ps[MoveIdx.CAT_STATUS], 1.0)
        self.assertEqual(ps[MoveIdx.SWITCH_MODE], 1.0)
        self.assertEqual(ps[MoveIdx.IS_SOUND_MOVE], 1.0)
        self.assertEqual(ps[MoveIdx.STAT_DELTA_ATK], -1.0)
        self.assertEqual(ps[MoveIdx.STAT_DELTA_SPA], -1.0)
        self.assertEqual(ps[MoveIdx.STAT_DELTA_SELF], 0.0)

        # 4. Close Combat & Leaf Storm: Self-stat drops on damaging moves
        cc = c.compile_move_vector("Close Combat")
        self.assertEqual(cc[MoveIdx.BASE_POWER], 120.0)
        self.assertEqual(cc[MoveIdx.STAT_DELTA_DEF], -1.0)
        self.assertEqual(cc[MoveIdx.STAT_DELTA_SPD], -1.0)
        self.assertEqual(cc[MoveIdx.STAT_DELTA_SELF], 1.0)

        ls = c.compile_move_vector("Leaf Storm")
        self.assertEqual(ls[MoveIdx.BASE_POWER], 130.0)
        self.assertEqual(ls[MoveIdx.STAT_DELTA_SPA], -2.0)
        self.assertEqual(ls[MoveIdx.STAT_DELTA_SELF], 1.0)

        # 5. Icy Wind: Spread speed drop on foes
        iw = c.compile_move_vector("Icy Wind")
        self.assertEqual(iw[MoveIdx.TARGET_TYPE], float(TargetType.ALL_ADJACENT_FOES))
        self.assertEqual(iw[MoveIdx.STAT_DELTA_SPE], -1.0)
        self.assertEqual(iw[MoveIdx.STAT_DELTA_SELF], 0.0)
        self.assertEqual(iw[MoveIdx.STAT_DELTA_CHANCE], 1.0)

        # 6. Flare Blitz, Draining Kiss, Recover: Recoil, Drain & Heal
        fb = c.compile_move_vector("Flare Blitz")
        self.assertAlmostEqual(fb[MoveIdx.RECOIL_PCT], 0.33, places=2)
        dk = c.compile_move_vector("Draining Kiss")
        self.assertAlmostEqual(dk[MoveIdx.RECOIL_PCT], -0.75, places=2)
        rec = c.compile_move_vector("Recover")
        self.assertAlmostEqual(rec[MoveIdx.RECOIL_PCT], -0.50, places=2)

        # 7. Multi-hit, willCrit, and Stat Overrides
        dw = c.compile_move_vector("Dual Wingbeat")
        self.assertEqual(dw[MoveIdx.EXPECTED_HITS], 2.0)
        rb = c.compile_move_vector("Rock Blast")
        self.assertAlmostEqual(rb[MoveIdx.EXPECTED_HITS], 3.1, places=2)
        ft = c.compile_move_vector("Flower Trick")
        self.assertAlmostEqual(ft[MoveIdx.ACCURACY], 1.01, places=2)
        self.assertEqual(ft[MoveIdx.CRIT_STAGE], 3.0)
        bp = c.compile_move_vector("Body Press")
        self.assertEqual(bp[MoveIdx.OVERRIDE_OFF_STAT], float(OverrideOffStat.USER_DEF))
        fp = c.compile_move_vector("Foul Play")
        self.assertEqual(fp[MoveIdx.OVERRIDE_OFF_STAT], float(OverrideOffStat.TARGET_ATK))
        psy = c.compile_move_vector("Psyshock")
        self.assertEqual(psy[MoveIdx.OVERRIDE_DEF_STAT], float(OverrideDefStat.TARGET_DEF))

    def test_compile_turn_state_and_26x26_action_masks(self) -> None:
        """Verify compiling TurnState into [24], [8, 84], [8, 4, 56] tensors and 26x26 masks."""
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
            battle_roster=["Grimmsnarl", "Milotic", "Garchomp", "Kingambit"],
            leads=("Grimmsnarl", "Milotic"),
            active_slots=["Grimmsnarl", "Milotic"],
            pokemon_sets=parse_showdown_paste(USER_TEAM_PASTE),
        )

        turn_state = self.state_compiler.compile_turn_state(battle, run_inference=False)
        compiled_tensors = self.tensor_compiler.compile_turn_state(turn_state)

        self.assertEqual(tuple(compiled_tensors.field_tensor.shape), (FIELD_DIM,))
        self.assertEqual(tuple(compiled_tensors.roster_tensor.shape), (ROSTER_SLOTS, MON_DIM))
        self.assertEqual(tuple(compiled_tensors.moves_tensor.shape), (ROSTER_SLOTS, 4, MOVE_DIM))

        # Compute 26x26 action masks for trainer_1 and trainer_2
        t1_masks = self.tensor_compiler.compute_26x26_side_action_masks(
            compiled_tensors, trainer_id="trainer_1"
        )
        t2_masks = self.tensor_compiler.compute_26x26_side_action_masks(
            compiled_tensors, trainer_id="trainer_2"
        )

        self.assertEqual(tuple(t1_masks.joint_valid_mask.shape), (26, 26))
        self.assertEqual(tuple(t2_masks.joint_valid_mask.shape), (26, 26))
        self.assertGreater(t1_masks.num_valid_actions, 0)
        self.assertGreater(t2_masks.num_valid_actions, 0)

        # Verify Double-Mega block (12:24, 12:24) is strictly zeroed out on trainer_1
        j_valid_np = (
            t1_masks.joint_valid_mask.detach().cpu().numpy()
            if compiled_tensors.backend == "torch"
            else t1_masks.joint_valid_mask
        )
        self.assertEqual(float(np.sum(j_valid_np[12:24, 12:24])), 0.0)
        # While single-Mega rows (12:24, 0:12) and cols (0:12, 12:24) are valid!
        self.assertGreater(float(np.sum(j_valid_np[12:24, 0:12])), 0.0)
        self.assertGreater(float(np.sum(j_valid_np[0:12, 12:24])), 0.0)

        # Verify Simultaneous Bench Switch Crash (24, 24) and (25, 25) are zeroed out
        self.assertEqual(float(j_valid_np[CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH1]), 0.0)
        self.assertEqual(float(j_valid_np[CHOICE_SWITCH_BENCH2, CHOICE_SWITCH_BENCH2]), 0.0)
        # While double-switching to different bench slots (24, 25) and (25, 24) is valid!
        self.assertEqual(float(j_valid_np[CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH2]), 1.0)
        self.assertEqual(float(j_valid_np[CHOICE_SWITCH_BENCH2, CHOICE_SWITCH_BENCH1]), 1.0)


if __name__ == "__main__":
    unittest.main()

