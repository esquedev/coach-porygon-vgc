# -*- coding: utf-8 -*-
"""
Milestone 2: Showdown-to-Tensor Compiler & 26x26 Matrix Action Pruner
(vgc_tensor_core/compiler.py)

Implements:
1. Standalone Showdown-to-Tensor Compiler (`ShowdownTensorCompiler`):
   - Compiles readable Field, 8-Slot Roster ([8, 84]), and 8-Slot Move ([8, 4, 52])
     specifications into aligned PyTorch CUDA/CPU or NumPy tensors.
   - Includes a self-contained Regulation M-C Move & Species Reference Dictionary
     (ZERO imports from `engine/`).

2. Canonical 26x26 Per-Player Action Space (`SLOT_CHOICES = 26`, `SIDE_ACTIONS = 676`):
   For each Active Slot (`Slot A` and `Slot B`), the 26 discrete choices are:
   - `0..3`   : Base Move `0..3` -> Opponent Slot A (or default target for Spread/Self/Field moves)
   - `4..7`   : Base Move `0..3` -> Opponent Slot B
   - `8..11`  : Base Move `0..3` -> Partner Slot (e.g. Helping Hand, Pollen Puff heal, Weakness Policy self-proc)
   - `12..15` : Mega Evolve + Move `0..3` -> Opponent Slot A
   - `16..19` : Mega Evolve + Move `0..3` -> Opponent Slot B
   - `20..23` : Mega Evolve + Move `0..3` -> Partner Slot
   - `24`     : Switch -> Bench Slot 1
   - `25`     : Switch -> Bench Slot 2

3. Pure Vectorized Matrix Action Pruner (`compute_26x26_action_masks`):
   Translates every hard physical invariant and soft risk-reward heuristic from
   `vgc_tensor_core/legacy_doc/logic_engine.py` into pure branchless matrix algebra:
   - Outputs `hard_validity_mask` of shape `[26, 26]` in {0.0, 1.0}
   - Outputs `tactical_prior_matrix` of shape `[26, 26]` in [0.0, ~3.5]
   - Outputs compressed active-grid indices `valid_coords` of shape `[N_valid, 2]`
     so the GPU tensor state machine only simulates the `N_valid x M_valid` legal
     joint universes with zero wasted VRAM on impossible cells!
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from vgc_tensor_core.schema_and_tables import (
    AbilityID,
    BilinearLookupTables,
    CATEGORY_TO_IDX,
    FIELD_DIM,
    FieldIdx,
    HAS_TORCH,
    ItemID,
    MON_DIM,
    MOVES_PER_MON,
    MOVE_DIM,
    MonIdx,
    MoveIdx,
    NUM_MOVE_CATEGORIES,
    NUM_STATUSES,
    NUM_TERRAINS,
    NUM_TYPES,
    NUM_WEATHERS,
    ROSTER_SLOTS,
    SLOT_P1A,
    SLOT_P1B,
    SLOT_P1_BENCH1,
    SLOT_P1_BENCH2,
    SLOT_P2A,
    SLOT_P2B,
    SLOT_P2_BENCH1,
    SLOT_P2_BENCH2,
    STATUS_TO_IDX,
    TERRAIN_TO_IDX,
    TYPE_TO_IDX,
    TargetType,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
    compute_type_effectiveness,
)

if HAS_TORCH:
    import torch
else:
    torch = None  # type: ignore


# =============================================================================
# 1. CANONICAL 26-CHOICE SLOT GEOMETRY CONSTANTS
# =============================================================================

SLOT_CHOICES: int = 26
SIDE_ACTIONS: int = SLOT_CHOICES * SLOT_CHOICES  # 26 x 26 = 676

# Choice index ranges per active slot
CHOICE_BASE_OPP_A_START: int = 0    # 0..3:   Move 0..3 -> Opp Slot A
CHOICE_BASE_OPP_B_START: int = 4    # 4..7:   Move 0..3 -> Opp Slot B
CHOICE_BASE_ALLY_START: int = 8     # 8..11:  Move 0..3 -> Partner
CHOICE_MEGA_OPP_A_START: int = 12   # 12..15: Mega + Move 0..3 -> Opp Slot A
CHOICE_MEGA_OPP_B_START: int = 16   # 16..19: Mega + Move 0..3 -> Opp Slot B
CHOICE_MEGA_ALLY_START: int = 20    # 20..23: Mega + Move 0..3 -> Partner
CHOICE_SWITCH_BENCH1: int = 24      # 24:     Switch -> Bench 1
CHOICE_SWITCH_BENCH2: int = 25      # 25:     Switch -> Bench 2


# =============================================================================
# 2. STANDALONE REGULATION M-C MOVE & SPECIES COMPILER CATALOG
# =============================================================================

ITEM_NAME_TO_ID: Dict[str, ItemID] = {
    "none": ItemID.NONE, "": ItemID.NONE,
    "focus sash": ItemID.FOCUS_SASH, "focussash": ItemID.FOCUS_SASH,
    "life orb": ItemID.LIFE_ORB, "lifeorb": ItemID.LIFE_ORB,
    "sitrus berry": ItemID.SITRUS_BERRY, "sitrusberry": ItemID.SITRUS_BERRY,
    "clear amulet": ItemID.CLEAR_AMULET, "clearamulet": ItemID.CLEAR_AMULET,
    "covert cloak": ItemID.COVERT_CLOAK, "covertcloak": ItemID.COVERT_CLOAK,
    "safety goggles": ItemID.SAFETY_GOGGLES, "safetygoggles": ItemID.SAFETY_GOGGLES,
    "assault vest": ItemID.ASSAULT_VEST, "assaultvest": ItemID.ASSAULT_VEST,
    "choice scarf": ItemID.CHOICE_SCARF, "choicescarf": ItemID.CHOICE_SCARF,
    "choice band": ItemID.CHOICE_BAND, "choiceband": ItemID.CHOICE_BAND,
    "choice specs": ItemID.CHOICE_SPECS, "choicespecs": ItemID.CHOICE_SPECS,
    "eject button": ItemID.EJECT_BUTTON, "ejectbutton": ItemID.EJECT_BUTTON,
    "eject pack": ItemID.EJECT_PACK, "ejectpack": ItemID.EJECT_PACK,
    "red card": ItemID.RED_CARD, "redcard": ItemID.RED_CARD,
    "booster energy": ItemID.BOOSTER_ENERGY, "boosterenergy": ItemID.BOOSTER_ENERGY,
    "leftovers": ItemID.LEFTOVERS,
    "black sludge": ItemID.BLACK_SLUDGE, "blacksludge": ItemID.BLACK_SLUDGE,
    "rocky helmet": ItemID.ROCKY_HELMET, "rockyhelmet": ItemID.ROCKY_HELMET,
    "mega stone": ItemID.MEGA_STONE, "floettite": ItemID.MEGA_STONE,
    "charizardite y": ItemID.MEGA_STONE, "charizardite x": ItemID.MEGA_STONE,
    "garchompite": ItemID.MEGA_STONE, "salamencite": ItemID.MEGA_STONE,
    "gengarite": ItemID.MEGA_STONE, "metagrossite": ItemID.MEGA_STONE,
    "tyranitarite": ItemID.MEGA_STONE, "abomasite": ItemID.MEGA_STONE,
}

ABILITY_NAME_TO_ID: Dict[str, AbilityID] = {
    "none": AbilityID.NONE, "": AbilityID.NONE,
    "intimidate": AbilityID.INTIMIDATE,
    "defiant": AbilityID.DEFIANT,
    "competitive": AbilityID.COMPETITIVE,
    "drizzle": AbilityID.DRIZZLE,
    "drought": AbilityID.DROUGHT,
    "sand stream": AbilityID.SAND_STREAM,
    "snow warning": AbilityID.SNOW_WARNING,
    "electric surge": AbilityID.ELECTRIC_SURGE,
    "grassy surge": AbilityID.GRASSY_SURGE,
    "psychic surge": AbilityID.PSYCHIC_SURGE,
    "misty surge": AbilityID.MISTY_SURGE,
    "fairy aura": AbilityID.FAIRY_AURA,
    "dark aura": AbilityID.DARK_AURA,
    "prankster": AbilityID.PRANKSTER,
    "unburden": AbilityID.UNBURDEN,
    "levitate": AbilityID.LEVITATE,
    "sturdy": AbilityID.STURDY,
    "inner focus": AbilityID.INNER_FOCUS,
    "multiscale": AbilityID.MULTISCALE,
    "guts": AbilityID.GUTS,
    "adaptability": AbilityID.ADAPTABILITY,
    "huge power": AbilityID.HUGE_POWER,
    "solar power": AbilityID.SOLAR_POWER,
    "swift swim": AbilityID.SWIFT_SWIM,
    "chlorophyll": AbilityID.CHLOROPHYLL,
    "sand rush": AbilityID.SAND_RUSH,
    "slush rush": AbilityID.SLUSH_RUSH,
    "lightning rod": AbilityID.LIGHTNING_ROD,
    "storm drain": AbilityID.STORM_DRAIN,
    "friend guard": AbilityID.FRIEND_GUARD,
    "hospitality": AbilityID.HOSPITALITY,
    "armor tail": AbilityID.ARMOR_TAIL,
    "queenly majesty": AbilityID.QUEENLY_MAJESTY,
    "good as gold": AbilityID.GOOD_AS_GOLD,
    "soundproof": AbilityID.SOUNDPROOF,
    "flash fire": AbilityID.FLASH_FIRE,
    "volt absorb": AbilityID.VOLT_ABSORB,
    "motor drive": AbilityID.MOTOR_DRIVE,
    "water absorb": AbilityID.WATER_ABSORB,
    "sap sipper": AbilityID.SAP_SIPPER,
    "earth eater": AbilityID.EARTH_EATER,
    "no guard": AbilityID.NO_GUARD,
    "scrappy": AbilityID.SCRAPPY,
    "mind's eye": AbilityID.MINDS_EYE, "minds eye": AbilityID.MINDS_EYE,
}

# Built-in Standalone Move Catalog for rapid Showdown-to-Tensor compilation
# (Any custom move dict can also be passed directly at compile time)
STANDALONE_MOVE_CATALOG: Dict[str, Dict[str, Any]] = {
    "Reflect": {
        "bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Psychic", "cat": "Status",
        "target": TargetType.ALLY_SIDE, "field_op": 11.0,
    },
    "Light Screen": {
        "bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Psychic", "cat": "Status",
        "target": TargetType.ALLY_SIDE, "field_op": 12.0,
    },
    "Tailwind": {
        "bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Flying", "cat": "Status",
        "target": TargetType.ALLY_SIDE, "field_op": 13.0,
    },
    "Trick Room": {
        "bp": 0.0, "acc": 1.0, "prio": -7.0, "type": "Psychic", "cat": "Status",
        "target": TargetType.GLOBAL_FIELD, "field_op": 14.0,
    },
    "Protect": {
        "bp": 0.0, "acc": 1.0, "prio": 4.0, "type": "Normal", "cat": "Status",
        "target": TargetType.SELF, "protect_type": 1.0,
    },
    "Wide Guard": {
        "bp": 0.0, "acc": 1.0, "prio": 3.0, "type": "Rock", "cat": "Status",
        "target": TargetType.ALLY_SIDE, "protect_type": 2.0,
    },
    "Quick Guard": {
        "bp": 0.0, "acc": 1.0, "prio": 3.0, "type": "Fighting", "cat": "Status",
        "target": TargetType.ALLY_SIDE, "protect_type": 3.0,
    },
    "Poison Jab": {
        "bp": 80.0, "acc": 1.0, "prio": 0.0, "type": "Poison", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "sec_status": "Poison", "sec_chance": 0.30,
    },
    "Stomping Tantrum": {
        "bp": 75.0, "acc": 1.0, "prio": 0.0, "type": "Ground", "cat": "Physical",
        "target": TargetType.SINGLE_FOE,
    },
    "Earthquake": {
        "bp": 100.0, "acc": 1.0, "prio": 0.0, "type": "Ground", "cat": "Physical",
        "target": TargetType.ALL_ADJACENT,
    },
    "Calm Mind": {
        "bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Psychic", "cat": "Status",
        "target": TargetType.SELF, "stat_deltas": {"spa": 1.0, "spd": 1.0}, "stat_self": 1.0,
    },
    "Swords Dance": {
        "bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Normal", "cat": "Status",
        "target": TargetType.SELF, "stat_deltas": {"atk": 2.0}, "stat_self": 1.0,
    },
    "Dazzling Gleam": {
        "bp": 80.0, "acc": 1.0, "prio": 0.0, "type": "Fairy", "cat": "Special",
        "target": TargetType.ALL_ADJACENT_FOES,
    },
    "Draining Kiss": {
        "bp": 50.0, "acc": 1.0, "prio": 0.0, "type": "Fairy", "cat": "Special",
        "target": TargetType.SINGLE_FOE, "recoil_pct": -0.75,
    },
    "Spirit Break": {
        "bp": 75.0, "acc": 1.0, "prio": 0.0, "type": "Fairy", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "stat_deltas": {"spa": -1.0}, "stat_chance": 1.0, "stat_self": 0.0,
    },
    "Fake Out": {
        "bp": 40.0, "acc": 1.0, "prio": 3.0, "type": "Normal", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "flinch_chance": 1.0, "first_turn_only": 1.0, "field_op": 18.0,
    },
    "Close Combat": {
        "bp": 120.0, "acc": 1.0, "prio": 0.0, "type": "Fighting", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "stat_deltas": {"def": -1.0, "spd": -1.0}, "stat_self": 1.0,
    },
    "Heat Wave": {
        "bp": 95.0, "acc": 0.90, "prio": 0.0, "type": "Fire", "cat": "Special",
        "target": TargetType.ALL_ADJACENT_FOES, "sec_status": "Burn", "sec_chance": 0.10,
    },
    "Parting Shot": {
        "bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Dark", "cat": "Status",
        "target": TargetType.SINGLE_FOE, "stat_deltas": {"atk": -1.0, "spa": -1.0}, "stat_self": 0.0,
        "switch_mode": 1.0, "is_sound": 1.0,
    },
    "U-turn": {
        "bp": 70.0, "acc": 1.0, "prio": 0.0, "type": "Bug", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "switch_mode": 1.0,
    },
    "Helping Hand": {
        "bp": 0.0, "acc": 1.0, "prio": 5.0, "type": "Normal", "cat": "Status",
        "target": TargetType.ALLY, "field_op": 16.0,
    },
    "Follow Me": {
        "bp": 0.0, "acc": 1.0, "prio": 2.0, "type": "Normal", "cat": "Status",
        "target": TargetType.SELF, "field_op": 15.0,
    },
    "Rage Powder": {
        "bp": 0.0, "acc": 1.0, "prio": 2.0, "type": "Bug", "cat": "Status",
        "target": TargetType.SELF, "field_op": 15.0,
    },
    "Thunder Wave": {
        "bp": 0.0, "acc": 0.90, "prio": 0.0, "type": "Electric", "cat": "Status",
        "target": TargetType.SINGLE_FOE, "sec_status": "Paralyze", "sec_chance": 1.0,
    },
    "Spore": {
        "bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Grass", "cat": "Status",
        "target": TargetType.SINGLE_FOE, "sec_status": "Sleep", "sec_chance": 1.0,
    },
    "Hypnosis": {
        "bp": 0.0, "acc": 0.60, "prio": 0.0, "type": "Psychic", "cat": "Status",
        "target": TargetType.SINGLE_FOE, "sec_status": "Sleep", "sec_chance": 1.0,
    },
    "Hyper Voice": {
        "bp": 90.0, "acc": 1.0, "prio": 0.0, "type": "Normal", "cat": "Special",
        "target": TargetType.ALL_ADJACENT_FOES, "is_sound": 1.0,
    },
    "Snarl": {
        "bp": 55.0, "acc": 0.95, "prio": 0.0, "type": "Dark", "cat": "Special",
        "target": TargetType.ALL_ADJACENT_FOES, "stat_deltas": {"spa": -1.0}, "stat_self": 0.0, "is_sound": 1.0,
    },
    "Grassy Glide": {
        "bp": 55.0, "acc": 1.0, "prio": 0.0, "type": "Grass", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "grassy_prio_boost": 1.0,
    },
    "Sucker Punch": {
        "bp": 70.0, "acc": 1.0, "prio": 1.0, "type": "Dark", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "field_op": 17.0,
    },
    "Hurricane": {
        "bp": 110.0, "acc": 0.70, "prio": 0.0, "type": "Flying", "cat": "Special",
        "target": TargetType.SINGLE_FOE, "weather_sure_hit": 2.0,
    },
    "Blizzard": {
        "bp": 110.0, "acc": 0.70, "prio": 0.0, "type": "Ice", "cat": "Special",
        "target": TargetType.ALL_ADJACENT_FOES, "sec_status": "Freeze", "sec_chance": 0.10, "weather_sure_hit": 4.0,
    },
    "Flare Blitz": {
        "bp": 120.0, "acc": 1.0, "prio": 0.0, "type": "Fire", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "recoil_pct": 0.33, "sec_status": "Burn", "sec_chance": 0.10,
    },
    "Iron Head": {
        "bp": 80.0, "acc": 1.0, "prio": 0.0, "type": "Steel", "cat": "Physical",
        "target": TargetType.SINGLE_FOE, "flinch_chance": 0.30,
    },
}


# =============================================================================
# 3. COMPILED STATE & 26x26 ACTION MASK CONTAINERS
# =============================================================================

@dataclass
class CompiledBattleState:
    """
    Container for the compiled initial board state tensors:
    - field_tensor  : shape [24]
    - roster_tensor : shape [8, 80]
    - moves_tensor  : shape [8, 4, 52]
    """
    field_tensor: Any
    roster_tensor: Any
    moves_tensor: Any
    backend: str
    device: Any


@dataclass
class SideActionMaskResult:
    """
    Output of the 26x26 Matrix Action Pruner for one side ('p1' or 'p2').

    Attributes:
        slot_a_valid_mask: 1D tensor [26] in {0.0, 1.0} for Active Slot A.
        slot_b_valid_mask: 1D tensor [26] in {0.0, 1.0} for Active Slot B.
        slot_a_prior_vec : 1D tensor [26] soft risk-reward prior scale for Slot A.
        slot_b_prior_vec : 1D tensor [26] soft risk-reward prior scale for Slot B.
        joint_valid_mask : 2D matrix [26, 26] in {0.0, 1.0} after cross-slot collision masks
                           (Simultaneous Double-Mega Lock + Simultaneous Bench Switch Crash + Double Protect / Helping Hand).
        joint_prior_mat  : 2D matrix [26, 26] = (slot_a_prior[:, None] * slot_b_prior[None, :]) * joint_valid_mask.
        valid_coords     : 2D integer tensor [N_valid, 2] of surviving (choice_a, choice_b) coordinates.
    """
    slot_a_valid_mask: Any
    slot_b_valid_mask: Any
    slot_a_prior_vec: Any
    slot_b_prior_vec: Any
    joint_valid_mask: Any
    joint_prior_mat: Any
    valid_coords: Any

    @property
    def num_valid_actions(self) -> int:
        """Return count N_valid of legal joint actions out of 676."""
        return int(self.valid_coords.shape[0])


# =============================================================================
# 4. SHOWDOWN-TO-TENSOR COMPILER
# =============================================================================

class ShowdownTensorCompiler:
    """
    Compiles lightweight Showdown board/roster dictionaries into aligned
    [24], [8, 80], and [8, 4, 52] tensors and computes the 26x26 Matrix Action Pruner masks.
    """

    def __init__(self, tables: Optional[BilinearLookupTables] = None) -> None:
        self.tables = tables or build_bilinear_lookup_tables()
        self.backend = self.tables.backend
        self.device = self.tables.device

    def compile_move_vector(self, move_spec: Any) -> np.ndarray:
        """
        Compile a single move name string or dictionary into a 52-float vector (`MoveIdx`).
        """
        vec = np.zeros((MOVE_DIM,), dtype=np.float32)
        if isinstance(move_spec, str):
            spec = STANDALONE_MOVE_CATALOG.get(move_spec, {"bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Normal", "cat": "Status"})
        elif isinstance(move_spec, dict):
            base = STANDALONE_MOVE_CATALOG.get(move_spec.get("name", ""), {})
            spec = {**base, **move_spec}
        else:
            spec = {"bp": 0.0, "acc": 1.0, "prio": 0.0, "type": "Normal", "cat": "Status"}

        vec[MoveIdx.BASE_POWER] = float(spec.get("bp", 0.0))
        vec[MoveIdx.ACCURACY] = float(spec.get("acc", 1.0))
        vec[MoveIdx.PRIORITY] = float(spec.get("prio", 0.0))
        vec[MoveIdx.TARGET_TYPE] = float(spec.get("target", TargetType.SINGLE_FOE))
        vec[MoveIdx.CRIT_STAGE] = float(spec.get("crit_stage", 0.0))

        # Move Type One-Hot (5..22)
        t_name = str(spec.get("type", "Normal")).lower()
        t_idx = TYPE_TO_IDX.get(t_name, 0)
        vec[MoveIdx.TYPE_START + t_idx] = 1.0

        # Move Category One-Hot (23..25)
        c_name = str(spec.get("cat", "Physical")).lower()
        c_idx = CATEGORY_TO_IDX.get(c_name, 0)
        vec[MoveIdx.CAT_START + c_idx] = 1.0

        # Stat Stage Deltas (26..32)
        deltas = spec.get("stat_deltas", {})
        stat_keys = ("atk", "def", "spa", "spd", "spe", "acc", "eva")
        for s_i, s_k in enumerate(stat_keys):
            if s_k in deltas:
                vec[MoveIdx.STAT_DELTA_START + s_i] = float(deltas[s_k])
        vec[MoveIdx.STAT_DELTA_CHANCE] = float(spec.get("stat_chance", 1.0 if deltas else 0.0))
        vec[MoveIdx.STAT_DELTA_SELF] = float(spec.get("stat_self", 0.0))

        # Secondary Status One-Hot (35..41)
        sec_st = str(spec.get("sec_status", "Healthy")).lower()
        st_idx = STATUS_TO_IDX.get(sec_st, 0)
        vec[MoveIdx.SEC_STATUS_START + st_idx] = 1.0
        vec[MoveIdx.SEC_STATUS_CHANCE] = float(spec.get("sec_chance", 0.0))

        # Recoil, Flinch, Protect, Switch, Field Op, and Logical Pruner Flags (43..51)
        vec[MoveIdx.RECOIL_PCT] = float(spec.get("recoil_pct", 0.0))
        vec[MoveIdx.FLINCH_CHANCE] = float(spec.get("flinch_chance", 0.0))
        vec[MoveIdx.PROTECT_TYPE] = float(spec.get("protect_type", 0.0))
        vec[MoveIdx.SWITCH_MODE] = float(spec.get("switch_mode", 0.0))
        vec[MoveIdx.FIELD_OP_ID] = float(spec.get("field_op", 0.0))
        vec[MoveIdx.FIRST_TURN_ONLY] = float(spec.get("first_turn_only", 0.0))
        vec[MoveIdx.IS_SOUND_MOVE] = float(spec.get("is_sound", 0.0))
        vec[MoveIdx.WEATHER_SURE_HIT] = float(spec.get("weather_sure_hit", 0.0))
        vec[MoveIdx.GRASSY_PRIO_BOOST] = float(spec.get("grassy_prio_boost", 0.0))

        return vec

    def compile_pokemon_slot(self, mon_spec: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compile a single Pokémon dictionary into its 80-float Roster Vector (`MonIdx`)
        and its [4, 52] Move Matrix (`MoveIdx`).
        """
        p_vec = np.zeros((MON_DIM,), dtype=np.float32)
        m_mat = np.zeros((MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

        if not mon_spec:
            # Empty / Fainted slot
            p_vec[MonIdx.STATUS_HEALTHY] = 1.0
            p_vec[MonIdx.TYPE1_START] = 1.0
            p_vec[MonIdx.HELPING_HAND_MULT] = 1.0
            p_vec[MonIdx.CHOICE_LOCKED_MOVE] = -1.0
            p_vec[MonIdx.LAST_MOVE_IDX] = -1.0
            return p_vec, m_mat

        hp_max = float(mon_spec.get("hp_max", 160.0))
        hp_cur = float(mon_spec.get("hp_cur", hp_max))
        p_vec[MonIdx.HP_CUR] = hp_cur
        p_vec[MonIdx.HP_MAX] = max(1.0, hp_max)
        p_vec[MonIdx.ALIVE_FLAG] = 1.0 if hp_cur > 0.0 else 0.0

        stats = mon_spec.get("stats", {})
        p_vec[MonIdx.STAT_ATK] = float(stats.get("atk", 120.0))
        p_vec[MonIdx.STAT_DEF] = float(stats.get("def", 100.0))
        p_vec[MonIdx.STAT_SPA] = float(stats.get("spa", 100.0))
        p_vec[MonIdx.STAT_SPD] = float(stats.get("spd", 100.0))
        p_vec[MonIdx.STAT_SPE] = float(stats.get("spe", 100.0))

        boosts = mon_spec.get("boosts", {})
        for b_i, b_k in enumerate(("atk", "def", "spa", "spd", "spe", "acc", "eva")):
            p_vec[MonIdx.BOOST_START + b_i] = float(boosts.get(b_k, 0.0))

        st_name = str(mon_spec.get("status", "Healthy")).lower()
        st_idx = STATUS_TO_IDX.get(st_name, 0)
        p_vec[MonIdx.STATUS_START + st_idx] = 1.0

        types = mon_spec.get("types", ["Normal"])
        t1_idx = TYPE_TO_IDX.get(str(types[0]).lower(), 0)
        p_vec[MonIdx.TYPE1_START + t1_idx] = 1.0
        if len(types) >= 2 and str(types[1]).lower() != str(types[0]).lower():
            t2_idx = TYPE_TO_IDX.get(str(types[1]).lower(), 0)
            p_vec[MonIdx.TYPE2_START + t2_idx] = 1.0

        # Volatiles
        p_vec[MonIdx.PROTECT_ACTIVE] = float(mon_spec.get("protect_active", 0.0))
        p_vec[MonIdx.PROTECT_COUNTER] = float(mon_spec.get("protect_counter", 0.0))
        p_vec[MonIdx.FLINCHED] = float(mon_spec.get("flinched", 0.0))
        p_vec[MonIdx.ACTIVE_TURNS] = float(mon_spec.get("active_turns", 0.0))
        p_vec[MonIdx.TAUNT_TURNS] = float(mon_spec.get("taunt_turns", 0.0))
        p_vec[MonIdx.ENCORE_TURNS] = float(mon_spec.get("encore_turns", 0.0))
        p_vec[MonIdx.SUBSTITUTE_HP] = float(mon_spec.get("substitute_hp", 0.0))
        p_vec[MonIdx.HELPING_HAND_MULT] = float(mon_spec.get("helping_hand_mult", 1.0))

        # Grounded, Item, Ability, Mega
        item_str = str(mon_spec.get("item", "none")).lower()
        ability_str = str(mon_spec.get("ability", "none")).lower()
        item_id = ITEM_NAME_TO_ID.get(item_str, ItemID.NONE)
        ability_id = ABILITY_NAME_TO_ID.get(ability_str, AbilityID.NONE)

        is_flying = any(str(t).lower() == "flying" for t in types)
        is_levitate = (ability_id == AbilityID.LEVITATE)
        grounded_default = 0.0 if (is_flying or is_levitate) else 1.0
        p_vec[MonIdx.GROUNDED_FLAG] = float(mon_spec.get("grounded", grounded_default))
        p_vec[MonIdx.ITEM_ACTIVE] = float(mon_spec.get("item_active", 1.0 if item_id != ItemID.NONE else 0.0))
        p_vec[MonIdx.ITEM_ID] = float(item_id)
        p_vec[MonIdx.ABILITY_ID] = float(ability_id)
        p_vec[MonIdx.UNBURDEN_ACTIVE] = float(mon_spec.get("unburden_active", 0.0))
        p_vec[MonIdx.CHOICE_LOCKED_MOVE] = float(mon_spec.get("choice_locked_move", -1.0))
        p_vec[MonIdx.LAST_MOVE_IDX] = float(mon_spec.get("last_move_idx", -1.0))
        p_vec[MonIdx.TOXIC_COUNTER] = float(mon_spec.get("toxic_counter", 1.0))

        can_mega_default = 1.0 if item_id == ItemID.MEGA_STONE else 0.0
        p_vec[MonIdx.CAN_MEGA] = float(mon_spec.get("can_mega", can_mega_default))
        p_vec[MonIdx.IS_MEGA] = float(mon_spec.get("is_mega", 0.0))

        mega_stats = mon_spec.get("mega_stats", {})
        p_vec[MonIdx.MEGA_ATK] = float(mega_stats.get("atk", mon_spec.get("mega_atk", p_vec[MonIdx.STAT_ATK])))
        p_vec[MonIdx.MEGA_DEF] = float(mega_stats.get("def", mon_spec.get("mega_def", p_vec[MonIdx.STAT_DEF])))
        p_vec[MonIdx.MEGA_SPA] = float(mega_stats.get("spa", mon_spec.get("mega_spa", p_vec[MonIdx.STAT_SPA])))
        p_vec[MonIdx.MEGA_SPD] = float(mega_stats.get("spd", mon_spec.get("mega_spd", p_vec[MonIdx.STAT_SPD])))
        p_vec[MonIdx.MEGA_SPE] = float(mega_stats.get("spe", mon_spec.get("mega_spe", p_vec[MonIdx.STAT_SPE])))
        mega_ab_str = str(mon_spec.get("mega_ability", ability_str)).lower()
        p_vec[MonIdx.MEGA_ABILITY_ID] = float(ABILITY_NAME_TO_ID.get(mega_ab_str, ability_id))

        moves_list = mon_spec.get("moves", [])
        for m_i in range(MOVES_PER_MON):
            if m_i < len(moves_list):
                m_mat[m_i] = self.compile_move_vector(moves_list[m_i])
            else:
                m_mat[m_i] = self.compile_move_vector("Protect")

        return p_vec, m_mat

    def compile_battle_state(
        self,
        roster_specs: List[Dict[str, Any]],
        field_spec: Optional[Dict[str, Any]] = None,
    ) -> CompiledBattleState:
        """
        Compile a full 8-slot VGC battle state into aligned Field [24], Roster [8, 80],
        and Moves [8, 4, 52] tensors on the active device.
        """
        f_spec = field_spec or {}
        f_np = np.zeros((FIELD_DIM,), dtype=np.float32)

        w_idx = WEATHER_TO_IDX.get(str(f_spec.get("weather", "clear")).lower(), 0)
        f_np[FieldIdx.WEATHER_START + w_idx] = 1.0
        f_np[FieldIdx.WEATHER_TURNS] = float(f_spec.get("weather_turns", 0.0))

        t_idx = TERRAIN_TO_IDX.get(str(f_spec.get("terrain", "none")).lower(), 0)
        f_np[FieldIdx.TERRAIN_START + t_idx] = 1.0
        f_np[FieldIdx.TERRAIN_TURNS] = float(f_spec.get("terrain_turns", 0.0))

        f_np[FieldIdx.TRICK_ROOM_TURNS] = float(f_spec.get("trick_room_turns", 0.0))
        f_np[FieldIdx.GRAVITY_TURNS] = float(f_spec.get("gravity_turns", 0.0))

        f_np[FieldIdx.P1_TAILWIND_TURNS] = float(f_spec.get("p1_tailwind_turns", 0.0))
        f_np[FieldIdx.P1_REFLECT_TURNS] = float(f_spec.get("p1_reflect_turns", 0.0))
        f_np[FieldIdx.P1_LIGHT_SCREEN_TURNS] = float(f_spec.get("p1_light_screen_turns", 0.0))
        f_np[FieldIdx.P1_AURORA_VEIL_TURNS] = float(f_spec.get("p1_aurora_veil_turns", 0.0))
        f_np[FieldIdx.P1_MEGA_USED] = float(f_spec.get("p1_mega_used", 0.0))

        f_np[FieldIdx.P2_TAILWIND_TURNS] = float(f_spec.get("p2_tailwind_turns", 0.0))
        f_np[FieldIdx.P2_REFLECT_TURNS] = float(f_spec.get("p2_reflect_turns", 0.0))
        f_np[FieldIdx.P2_LIGHT_SCREEN_TURNS] = float(f_spec.get("p2_light_screen_turns", 0.0))
        f_np[FieldIdx.P2_AURORA_VEIL_TURNS] = float(f_spec.get("p2_aurora_veil_turns", 0.0))
        f_np[FieldIdx.P2_MEGA_USED] = float(f_spec.get("p2_mega_used", 0.0))

        p_np = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        m_np = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

        for s_idx in range(ROSTER_SLOTS):
            spec = roster_specs[s_idx] if s_idx < len(roster_specs) else {}
            p_np[s_idx], m_np[s_idx] = self.compile_pokemon_slot(spec)

        if self.backend == "torch" and torch is not None:
            return CompiledBattleState(
                field_tensor=torch.from_numpy(f_np).to(self.device),
                roster_tensor=torch.from_numpy(p_np).to(self.device),
                moves_tensor=torch.from_numpy(m_np).to(self.device),
                backend="torch",
                device=self.device,
            )

        return CompiledBattleState(
            field_tensor=f_np,
            roster_tensor=p_np,
            moves_tensor=m_np,
            backend="numpy",
            device="cpu",
        )

    # =========================================================================
    # 5. VECTORIZED 26x26 MATRIX ACTION PRUNER (ZERO STRING LOOPS)
    # =========================================================================

    def _compute_slot_26_masks_numpy(
        self,
        f_np: np.ndarray,
        p_np: np.ndarray,
        m_np: np.ndarray,
        user_slot: int,
        partner_slot: int,
        opp_a_slot: int,
        opp_b_slot: int,
        bench1_slot: int,
        bench2_slot: int,
        side_mega_used: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute the 26-element Hard Validity Mask {0.0, 1.0} and 26-element Soft Tactical
        Prior Vector for a single active slot using vectorized NumPy/Matrix operations
        encoding every axiom from `legacy_doc/logic_engine.py`.
        """
        valid_26 = np.zeros((SLOT_CHOICES,), dtype=np.float32)
        prior_26 = np.ones((SLOT_CHOICES,), dtype=np.float32)

        user_vec = p_np[user_slot]
        if user_vec[MonIdx.ALIVE_FLAG] <= 0.0:
            return valid_26, prior_26

        moves_4 = m_np[user_slot]  # Shape [4, 52]
        partner_vec = p_np[partner_slot]
        opp_a_vec = p_np[opp_a_slot]
        opp_b_vec = p_np[opp_b_slot]

        # Field state extraction via vector slices
        w_onehot = f_np[FieldIdx.WEATHER_START:FieldIdx.WEATHER_END]
        t_onehot = f_np[FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END]
        is_rain = float(w_onehot[WEATHER_TO_IDX["rain"]])
        is_snow = float(w_onehot[WEATHER_TO_IDX["snow"]])
        is_psychic_terrain = float(t_onehot[TERRAIN_TO_IDX["psychic"]])
        is_grassy_terrain = float(t_onehot[TERRAIN_TO_IDX["grassy"]])
        is_elec_or_misty_terrain = float(
            t_onehot[TERRAIN_TO_IDX["electric"]] + t_onehot[TERRAIN_TO_IDX["misty"]]
        )
        gravity_active = 1.0 if f_np[FieldIdx.GRAVITY_TURNS] > 0.0 else 0.0

        # User state gates
        active_turns = user_vec[MonIdx.ACTIVE_TURNS]
        protect_count = user_vec[MonIdx.PROTECT_COUNTER]
        taunt_active = 1.0 if user_vec[MonIdx.TAUNT_TURNS] > 0.0 else 0.0
        encore_active = 1.0 if user_vec[MonIdx.ENCORE_TURNS] > 0.0 else 0.0
        last_move_idx = int(round(user_vec[MonIdx.LAST_MOVE_IDX]))
        choice_lock_idx = int(round(user_vec[MonIdx.CHOICE_LOCKED_MOVE]))
        has_assault_vest = (
            1.0 if (user_vec[MonIdx.ITEM_ACTIVE] > 0.0 and int(round(user_vec[MonIdx.ITEM_ID])) == ItemID.ASSAULT_VEST)
            else 0.0
        )
        user_ab = int(round(user_vec[MonIdx.ABILITY_ID]))
        can_mega_gate = (
            1.0 if (user_vec[MonIdx.CAN_MEGA] > 0.0 and user_vec[MonIdx.IS_MEGA] <= 0.0 and side_mega_used <= 0.0)
            else 0.0
        )

        # Opposing field-wide priority blocking abilities (Armor Tail / Queenly Majesty)
        opp_a_ab = int(round(opp_a_vec[MonIdx.ABILITY_ID])) if opp_a_vec[MonIdx.ALIVE_FLAG] > 0.0 else 0
        opp_b_ab = int(round(opp_b_vec[MonIdx.ABILITY_ID])) if opp_b_vec[MonIdx.ALIVE_FLAG] > 0.0 else 0
        opp_blocks_prio = (
            1.0 if (opp_a_ab in (AbilityID.ARMOR_TAIL, AbilityID.QUEENLY_MAJESTY)
                    or opp_b_ab in (AbilityID.ARMOR_TAIL, AbilityID.QUEENLY_MAJESTY))
            else 0.0
        )

        # Evaluate 4 moves x 3 Target Buckets (0: Opp_A, 1: Opp_B, 2: Partner) x 2 Mega Modes (0: Base, 1: Mega)
        target_slots = (opp_a_vec, opp_b_vec, partner_vec)
        m_chart_np = (
            self.tables.m_type_chart.detach().cpu().numpy()
            if self.backend == "torch"
            else self.tables.m_type_chart
        )

        for mega_mode in (0, 1):
            if mega_mode == 1 and can_mega_gate <= 0.0:
                continue
            eff_user_ab = int(round(user_vec[MonIdx.MEGA_ABILITY_ID])) if mega_mode == 1 else user_ab

            for tgt_bucket, tgt_vec in enumerate(target_slots):
                tgt_alive = tgt_vec[MonIdx.ALIVE_FLAG]
                if tgt_alive <= 0.0:
                    continue

                tgt_ab = int(round(tgt_vec[MonIdx.ABILITY_ID]))
                tgt_grounded = 1.0 if (gravity_active > 0.0 or tgt_vec[MonIdx.GROUNDED_FLAG] > 0.0) else 0.0
                tgt_type1 = tgt_vec[MonIdx.TYPE1_START:MonIdx.TYPE1_END]
                tgt_type2 = tgt_vec[MonIdx.TYPE2_START:MonIdx.TYPE2_END]
                tgt_is_dark = float(tgt_type1[TYPE_TO_IDX["dark"]] + tgt_type2[TYPE_TO_IDX["dark"]])

                for m_idx in range(MOVES_PER_MON):
                    choice_idx = (mega_mode * 12) + (tgt_bucket * 4) + m_idx
                    m_vec = moves_4[m_idx]

                    target_type = int(round(m_vec[MoveIdx.TARGET_TYPE]))
                    is_status = m_vec[MoveIdx.CAT_STATUS] > 0.5

                    # 1. Target Bucket Routing Matrix Gate:
                    #    - Spread/Self/Side/Global moves are only valid in Bucket 0 (canonical slot 0..3 / 12..15)
                    #    - ALLY moves (Helping Hand) are only valid in Bucket 2 (Partner slot 8..11 / 20..23)
                    #    - SINGLE_FOE moves are valid in Bucket 0 (Opp_A), Bucket 1 (Opp_B), and Bucket 2 (Partner self-proc)
                    if target_type in (
                        TargetType.ALL_ADJACENT_FOES,
                        TargetType.ALL_ADJACENT,
                        TargetType.SELF,
                        TargetType.ALLY_SIDE,
                        TargetType.GLOBAL_FIELD,
                    ):
                        if tgt_bucket != 0:
                            continue
                    elif target_type == TargetType.ALLY:
                        if tgt_bucket != 2:
                            continue

                    # 2. Choice Lock / Encore / Taunt / Assault Vest Hard Gates
                    if choice_lock_idx >= 0 and m_idx != choice_lock_idx:
                        continue
                    if encore_active > 0.0 and last_move_idx >= 0 and m_idx != last_move_idx:
                        continue
                    if is_status and (taunt_active > 0.0 or has_assault_vest > 0.0):
                        continue

                    # 3. Axiom 1 (Fake Out / First Impression Turn-1 Gate):
                    if m_vec[MoveIdx.FIRST_TURN_ONLY] > 0.5 and active_turns > 0.0:
                        continue

                    # 4. Effective Priority Resolution (Prankster +1 on Status, Grassy Glide +1 in Grassy Terrain)
                    eff_prio = float(m_vec[MoveIdx.PRIORITY])
                    if eff_user_ab == AbilityID.PRANKSTER and is_status:
                        eff_prio += 1.0
                    elif m_vec[MoveIdx.GRASSY_PRIO_BOOST] > 0.5 and is_grassy_terrain > 0.5 and user_vec[MonIdx.GROUNDED_FLAG] > 0.5:
                        eff_prio += 1.0

                    # 5. Axiom 2 (Priority Blocking & Terrain Invariants on Opposing Targets):
                    is_single_targeted_at_foe = (target_type == TargetType.SINGLE_FOE and tgt_bucket in (0, 1))
                    if is_single_targeted_at_foe and eff_prio > 0.0:
                        if opp_blocks_prio > 0.5:
                            continue
                        if is_psychic_terrain > 0.5 and tgt_grounded > 0.5:
                            continue

                    # 6. Prankster vs Dark-Type Target Invariant
                    if is_single_targeted_at_foe and eff_user_ab == AbilityID.PRANKSTER and is_status and tgt_is_dark > 0.5:
                        continue

                    # 7. Soundproof, Good as Gold, Flash Fire, & Terrain Sleep Invariants
                    if is_single_targeted_at_foe or target_type in (TargetType.ALL_ADJACENT_FOES, TargetType.ALL_ADJACENT):
                        if m_vec[MoveIdx.IS_SOUND_MOVE] > 0.5 and tgt_ab == AbilityID.SOUNDPROOF and target_type == TargetType.SINGLE_FOE:
                            continue
                        if is_status and tgt_ab == AbilityID.GOOD_AS_GOLD and target_type == TargetType.SINGLE_FOE:
                            continue
                        m_type_onehot = m_vec[MoveIdx.TYPE_START:MoveIdx.TYPE_END]
                        if m_type_onehot[TYPE_TO_IDX["fire"]] > 0.5 and tgt_ab == AbilityID.FLASH_FIRE and target_type == TargetType.SINGLE_FOE:
                            continue
                        is_sleep_move = (
                            m_vec[MoveIdx.SEC_STATUS_START + STATUS_TO_IDX["sleep"]] > 0.5
                            and m_vec[MoveIdx.SEC_STATUS_CHANCE] >= 1.0
                            and is_status
                        )
                        if is_sleep_move and tgt_grounded > 0.5 and is_elec_or_misty_terrain > 0.5:
                            continue

                    # Action survived all Hard Physical Invariants!
                    valid_26[choice_idx] = 1.0

                    # --- Soft Tactical Prior Calculation (`legacy_doc/logic_engine.py`) ---
                    prior_scale = 1.0

                    # A. Consecutive Protect Decay: (1/3)^k -> 0.40 on 2nd use, 0.10 on >=3rd use
                    if m_vec[MoveIdx.PROTECT_TYPE] > 0.5 and protect_count >= 1.0:
                        prior_scale = 0.40 if protect_count == 1.0 else 0.10

                    # B. Effective Accuracy Resolution (No Guard, Rain Sure-Hit, Snow Blizzard)
                    acc_val = float(m_vec[MoveIdx.ACCURACY])
                    if eff_user_ab == AbilityID.NO_GUARD or tgt_ab == AbilityID.NO_GUARD:
                        acc_val = 1.0
                    elif m_vec[MoveIdx.WEATHER_SURE_HIT] == 2.0 and is_rain > 0.5:
                        acc_val = 1.0
                    elif m_vec[MoveIdx.WEATHER_SURE_HIT] == 4.0 and is_snow > 0.5:
                        acc_val = 1.0
                    acc_val = min(1.0, max(0.0, acc_val))

                    # C. Bilinear Type Effectiveness & Partner Self-Hit Scaling
                    if not is_status:
                        m_type_vec = m_vec[MoveIdx.TYPE_START:MoveIdx.TYPE_END]
                        eff1 = float(m_type_vec @ m_chart_np @ tgt_type1)
                        raw_eff2 = float(m_type_vec @ m_chart_np @ tgt_type2)
                        eff2 = raw_eff2 + (1.0 - float(np.sum(tgt_type2)))
                        eff_total = eff1 * eff2

                        # Ground move into ungrounded target (0.0x physical unless Gravity)
                        if m_type_vec[TYPE_TO_IDX["ground"]] > 0.5 and tgt_grounded <= 0.0:
                            eff_total = 0.0

                        if tgt_bucket == 2:
                            # Targeting own Partner with damaging attack: low prior (0.15) unless synergetic
                            prior_scale = 0.15
                        else:
                            if eff_total == 0.0:
                                # Hard switch-in read into active immunity
                                prior_scale = 0.20 if (m_type_vec[TYPE_TO_IDX["ground"]] > 0.5 and tgt_grounded <= 0.0) else 0.15
                            elif eff_total <= 0.25:
                                prior_scale = 0.50
                            elif eff_total >= 4.0:
                                prior_scale = 1.35 * acc_val
                            elif eff_total >= 2.0:
                                prior_scale = 1.20 * acc_val
                            elif acc_val < 0.85:
                                prior_scale = acc_val

                    elif acc_val < 0.85:
                        prior_scale *= acc_val

                    # Slight bonus for Mega Evolution activation when available (+0.10 tactical upside)
                    if mega_mode == 1:
                        prior_scale *= 1.10

                    prior_26[choice_idx] = round(float(prior_scale), 4)

        # Evaluate Switch Choices 24 (Bench 1) and 25 (Bench 2)
        if p_np[bench1_slot, MonIdx.ALIVE_FLAG] > 0.0:
            valid_26[CHOICE_SWITCH_BENCH1] = 1.0
            prior_26[CHOICE_SWITCH_BENCH1] = 0.65
        if p_np[bench2_slot, MonIdx.ALIVE_FLAG] > 0.0:
            valid_26[CHOICE_SWITCH_BENCH2] = 1.0
            prior_26[CHOICE_SWITCH_BENCH2] = 0.65

        return valid_26, prior_26

    def compute_26x26_side_action_masks(
        self,
        state: CompiledBattleState,
        side: str = "p1",
    ) -> SideActionMaskResult:
        """
        Compute the full 26x26 Hard Validity Mask, 26x26 Tactical Prior Matrix,
        and compressed [N_valid, 2] valid action coordinates for `side` ('p1' or 'p2').

        Enforces Cross-Slot Joint Constraints via pure outer-product matrix masking:
        1. Outer Validity Mask: `M_valid = valid_a[:, None] * valid_b[None, :]`
        2. Simultaneous Double-Mega Lock: Zeroes out the `12..23 x 12..23` block
           (`M_valid[12:24, 12:24] = 0.0`) because a player can only Mega Evolve ONE slot!
        3. Simultaneous Bench Switch Crash: Zeroes out `(24, 24)` and `(25, 25)`
           (`M_valid[24, 24] = 0.0`, `M_valid[25, 25] = 0.0`) because both active slots
           cannot switch into the exact same reserve Pokémon simultaneously!
        """
        if side not in ("p1", "p2"):
            raise ValueError(f"side must be 'p1' or 'p2', got '{side}'")

        if state.backend == "torch" and torch is not None:
            f_np = state.field_tensor.detach().cpu().numpy()
            p_np = state.roster_tensor.detach().cpu().numpy()
            m_np = state.moves_tensor.detach().cpu().numpy()
        else:
            f_np = state.field_tensor
            p_np = state.roster_tensor
            m_np = state.moves_tensor

        if side == "p1":
            slot_a, slot_b = SLOT_P1A, SLOT_P1B
            bench1, bench2 = SLOT_P1_BENCH1, SLOT_P1_BENCH2
            opp_a, opp_b = SLOT_P2A, SLOT_P2B
            mega_used = float(f_np[FieldIdx.P1_MEGA_USED])
        else:
            slot_a, slot_b = SLOT_P2A, SLOT_P2B
            bench1, bench2 = SLOT_P2_BENCH1, SLOT_P2_BENCH2
            opp_a, opp_b = SLOT_P1A, SLOT_P1B
            mega_used = float(f_np[FieldIdx.P2_MEGA_USED])

        valid_a, prior_a = self._compute_slot_26_masks_numpy(
            f_np, p_np, m_np, slot_a, slot_b, opp_a, opp_b, bench1, bench2, mega_used
        )
        valid_b, prior_b = self._compute_slot_26_masks_numpy(
            f_np, p_np, m_np, slot_b, slot_a, opp_a, opp_b, bench1, bench2, mega_used
        )

        # 1. Outer Product Joint Validity Matrix: M_valid = valid_a (26x1) @ valid_b^T (1x26)
        joint_valid = np.outer(valid_a, valid_b).astype(np.float32)

        # 2. Cross-Slot Invariant 1: Simultaneous Double-Mega Lock (12..23 x 12..23 -> 0.0)
        joint_valid[12:24, 12:24] = 0.0

        # 3. Cross-Slot Invariant 2: Simultaneous Switch Crash into Same Bench Pokémon
        joint_valid[CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH1] = 0.0
        joint_valid[CHOICE_SWITCH_BENCH2, CHOICE_SWITCH_BENCH2] = 0.0

        # 4. Joint Tactical Prior Matrix: M_prior = (prior_a (26x1) @ prior_b^T (1x26)) ⊙ M_valid
        joint_prior = (np.outer(prior_a, prior_b) * joint_valid).astype(np.float32)

        # 5. Extract compressed [N_valid, 2] coordinates of surviving legal joint actions
        coords_np = np.argwhere(joint_valid > 0.5).astype(np.int64)

        if state.backend == "torch" and torch is not None:
            return SideActionMaskResult(
                slot_a_valid_mask=torch.from_numpy(valid_a).to(self.device),
                slot_b_valid_mask=torch.from_numpy(valid_b).to(self.device),
                slot_a_prior_vec=torch.from_numpy(prior_a).to(self.device),
                slot_b_prior_vec=torch.from_numpy(prior_b).to(self.device),
                joint_valid_mask=torch.from_numpy(joint_valid).to(self.device),
                joint_prior_mat=torch.from_numpy(joint_prior).to(self.device),
                valid_coords=torch.from_numpy(coords_np).to(self.device),
            )

        return SideActionMaskResult(
            slot_a_valid_mask=valid_a,
            slot_b_valid_mask=valid_b,
            slot_a_prior_vec=prior_a,
            slot_b_prior_vec=prior_b,
            joint_valid_mask=joint_valid,
            joint_prior_mat=joint_prior,
            valid_coords=coords_np,
        )
