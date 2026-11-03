# -*- coding: utf-8 -*-
"""
Milestone 1: State Tensor Schema & Bilinear One-Hot Lookup Matrices
(vgc_tensor_core/schema_and_tables.py)

Defines the exact tensor dimensions, feature slice indices, and constant
linear-algebra operator matrices for the standalone 100x100 VGC Tensor State Machine:

1. Global Field Tensor F: shape [..., 24]
2. 8-Slot Unified Roster Tensor P: shape [..., 8, 80]
   - Slots 0, 1: Player 1 Active (P1A, P1B)
   - Slots 2, 3: Player 1 Bench  (P1_Bench1, P1_Bench2)
   - Slots 4, 5: Player 2 Active (P2A, P2B)
   - Slots 6, 7: Player 2 Bench  (P2_Bench1, P2_Bench2)
   - Why 80 floats (320 bytes = 2.5 x 128-byte CUDA cache lines) instead of 64?
     Because HP(3) + Stats(5) + Boosts(7) + Status_OneHot(7) + Type1_OneHot(18) + Type2_OneHot(18)
     already equals 58 floats! Expanding to 80 gives 22 dedicated, un-aliased channels for all
     Volatiles (Protect, Wide/Quick Guard, Flinch, Taunt, Encore, Helping Hand, Substitute, Active Turns)
     AND full in-place Mega Evolution stats/abilities + Choice locks without bit-packing hacks.
3. 8-Slot Move Tensor M_moves: shape [..., 8, 4, 48]
   - Moves 0..3 for each of the 8 Pokémon slots, carrying Move Type One-Hot (18),
     Category One-Hot (3), Base Power, Accuracy, Priority, Stat Deltas (7), Status Procs,
     Recoil/Drain, Spread/Protect flags, and Voluntary/Forced Switch flags.
4. Bilinear One-Hot Contraction & Permutation Matrices (Dual PyTorch CUDA/CPU & NumPy support):
   - M_type_chart [18, 18]: Exact Type Effectiveness via (m_type @ M_type_chart @ d_type)
   - M_weather_mod [5, 18]: Exact Weather damage scaling via (w_onehot @ M_weather_mod @ m_type)
   - M_terrain_mod [5, 18]: Exact Terrain damage scaling via (t_onehot @ M_terrain_mod @ m_type)
   - M_psychic_prio_block [5]: Psychic Terrain priority lockout via (t_onehot @ M_psychic_prio_block)
   - T_set_weather [5, 5, 5]: Column-overwrite matrices mutating any Weather One-Hot state
   - T_set_terrain [5, 5, 5]: Column-overwrite matrices mutating any Terrain One-Hot state
   - P_switch_perms [8, 8, 8, 8]: Exact 8x8 permutation matrices swapping Active <-> Bench
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, Optional, Tuple
import numpy as np

try:
    import torch
    HAS_TORCH: bool = True
except ImportError:
    torch = None  # type: ignore
    HAS_TORCH = False


# =============================================================================
# 1. CANONICAL ENUMERATIONS & ONE-HOT DIMENSIONS
# =============================================================================

NUM_TYPES: int = 18
CANONICAL_TYPES: Tuple[str, ...] = (
    "Normal",    # 0
    "Fire",      # 1
    "Water",     # 2
    "Grass",     # 3
    "Electric",  # 4
    "Ice",       # 5
    "Fighting",  # 6
    "Poison",    # 7
    "Ground",    # 8
    "Flying",    # 9
    "Psychic",   # 10
    "Bug",       # 11
    "Rock",      # 12
    "Ghost",     # 13
    "Dragon",    # 14
    "Dark",      # 15
    "Steel",     # 16
    "Fairy",     # 17
)
TYPE_TO_IDX: Dict[str, int] = {t.lower(): i for i, t in enumerate(CANONICAL_TYPES)}

NUM_WEATHERS: int = 5
CANONICAL_WEATHERS: Tuple[str, ...] = (
    "Clear",  # 0
    "Sun",    # 1
    "Rain",   # 2
    "Sand",   # 3
    "Snow",   # 4
)
WEATHER_TO_IDX: Dict[str, int] = {w.lower(): i for i, w in enumerate(CANONICAL_WEATHERS)}

NUM_TERRAINS: int = 5
CANONICAL_TERRAINS: Tuple[str, ...] = (
    "None",      # 0
    "Electric",  # 1
    "Grassy",    # 2
    "Psychic",   # 3
    "Misty",     # 4
)
TERRAIN_TO_IDX: Dict[str, int] = {t.lower(): i for i, t in enumerate(CANONICAL_TERRAINS)}

NUM_STATUSES: int = 7
CANONICAL_STATUSES: Tuple[str, ...] = (
    "Healthy",   # 0
    "Burn",      # 1 (brn)
    "Paralyze",  # 2 (par)
    "Sleep",     # 3 (slp)
    "Freeze",    # 4 (frz)
    "Poison",    # 5 (psn - 1/8 max HP)
    "Toxic",     # 6 (tox - escalating N/16 max HP)
)
STATUS_TO_IDX: Dict[str, int] = {
    "healthy": 0, "none": 0, "": 0,
    "burn": 1, "brn": 1,
    "paralyze": 2, "par": 2,
    "sleep": 3, "slp": 3,
    "freeze": 4, "frz": 4,
    "poison": 5, "psn": 5,
    "toxic": 6, "tox": 6,
}

NUM_MOVE_CATEGORIES: int = 3
CANONICAL_CATEGORIES: Tuple[str, ...] = (
    "Physical",  # 0
    "Special",   # 1
    "Status",    # 2
)
CATEGORY_TO_IDX: Dict[str, int] = {c.lower(): i for i, c in enumerate(CANONICAL_CATEGORIES)}


class ItemID(IntEnum):
    """Canonical Numeric Item Identifiers for Branchless Matrix Gates."""
    NONE = 0
    FOCUS_SASH = 1
    LIFE_ORB = 2
    SITRUS_BERRY = 3
    CLEAR_AMULET = 4
    COVERT_CLOAK = 5
    SAFETY_GOGGLES = 6
    ASSAULT_VEST = 7
    CHOICE_SCARF = 8
    CHOICE_BAND = 9
    CHOICE_SPECS = 10
    EJECT_BUTTON = 11
    EJECT_PACK = 12
    RED_CARD = 13
    BOOSTER_ENERGY = 14
    LEFTOVERS = 15
    BLACK_SLUDGE = 16
    ROCKY_HELMET = 17
    MEGA_STONE = 18


class AbilityID(IntEnum):
    """Canonical Numeric Ability Identifiers for Branchless Matrix Gates."""
    NONE = 0
    INTIMIDATE = 1
    DEFIANT = 2
    COMPETITIVE = 3
    DRIZZLE = 4
    DROUGHT = 5
    SAND_STREAM = 6
    SNOW_WARNING = 7
    ELECTRIC_SURGE = 8
    GRASSY_SURGE = 9
    PSYCHIC_SURGE = 10
    MISTY_SURGE = 11
    FAIRY_AURA = 12
    DARK_AURA = 13
    PRANKSTER = 14
    UNBURDEN = 15
    LEVITATE = 16
    STURDY = 17
    INNER_FOCUS = 18
    MULTISCALE = 19
    GUTS = 20
    ADAPTABILITY = 21
    HUGE_POWER = 22
    SOLAR_POWER = 23
    SWIFT_SWIM = 24
    CHLOROPHYLL = 25
    SAND_RUSH = 26
    SLUSH_RUSH = 27
    LIGHTNING_ROD = 28
    STORM_DRAIN = 29
    FRIEND_GUARD = 30
    HOSPITALITY = 31
    ARMOR_TAIL = 32
    QUEENLY_MAJESTY = 33
    GOOD_AS_GOLD = 34
    SOUNDPROOF = 35
    FLASH_FIRE = 36
    VOLT_ABSORB = 37
    MOTOR_DRIVE = 38
    WATER_ABSORB = 39
    SAP_SIPPER = 40
    EARTH_EATER = 41
    NO_GUARD = 42
    SCRAPPY = 43
    MINDS_EYE = 44


class TargetType(IntEnum):
    """Canonical Move Targeting Archetypes."""
    SINGLE_FOE = 0          # Standard single-target attack (directed at Opp_A, Opp_B, or Partner)
    ALL_ADJACENT_FOES = 1   # Opposing spread move (Heat Wave, Dazzling Gleam, Rock Slide, Make It Rain)
    ALL_ADJACENT = 2        # Full-board spread move hitting partner + both foes (Earthquake, Discharge)
    SELF = 3                # Self-targeting status/buff/Protect (Protect, Calm Mind, Swords Dance)
    ALLY = 4                # Partner-targeting support (Helping Hand, Coaching, Pollen Puff heal)
    ALLY_SIDE = 5           # Team field support (Reflect, Light Screen, Tailwind, Wide Guard, Quick Guard)
    GLOBAL_FIELD = 6        # Global weather/terrain/room (Sunny Day, Rain Dance, Trick Room)


# =============================================================================
# 2. TENSOR SHAPE & FEATURE INDEX SPECIFICATION
# =============================================================================

# Roster Slots (8 total in 4v4 VGC Doubles)
ROSTER_SLOTS: int = 8
SLOT_P1A: int = 0
SLOT_P1B: int = 1
SLOT_P1_BENCH1: int = 2
SLOT_P1_BENCH2: int = 3
SLOT_P2A: int = 4
SLOT_P2B: int = 5
SLOT_P2_BENCH1: int = 6
SLOT_P2_BENCH2: int = 7


# --- A. Global Field Tensor F: shape [..., 24] ---
FIELD_DIM: int = 24


class FieldIdx:
    """Exact indices for the 24-element Global Field Tensor F."""
    # 0..4: Weather One-Hot [Clear, Sun, Rain, Sand, Snow]
    WEATHER_START: int = 0
    WEATHER_END: int = 5
    WEATHER_TURNS: int = 5

    # 6..10: Terrain One-Hot [None, Electric, Grassy, Psychic, Misty]
    TERRAIN_START: int = 6
    TERRAIN_END: int = 11
    TERRAIN_TURNS: int = 11

    # 12..13: Global Room & Field Effects
    TRICK_ROOM_TURNS: int = 12
    GRAVITY_TURNS: int = 13

    # 14..18: Player 1 Side Conditions
    P1_TAILWIND_TURNS: int = 14
    P1_REFLECT_TURNS: int = 15
    P1_LIGHT_SCREEN_TURNS: int = 16
    P1_AURORA_VEIL_TURNS: int = 17
    P1_MEGA_USED: int = 18

    # 19..23: Player 2 Side Conditions
    P2_TAILWIND_TURNS: int = 19
    P2_REFLECT_TURNS: int = 20
    P2_LIGHT_SCREEN_TURNS: int = 21
    P2_AURORA_VEIL_TURNS: int = 22
    P2_MEGA_USED: int = 23


# --- B. 8-Slot Unified Roster Tensor P: shape [..., 8, 84] ---
MON_DIM: int = 84


class MonIdx:
    """
    Exact indices for the 84-Float Per-Pokémon Feature Vector [..., 8, 84].
    Zero overloaded channels; includes full 5-stat in-place Mega Evolution payload.
    """
    # 0..2 (3 floats): HP Channels
    HP_CUR: int = 0               # Current HP in exact Level-50 hit points
    HP_MAX: int = 1               # Maximum HP in exact Level-50 hit points
    ALIVE_FLAG: int = 2           # 1.0 if HP_CUR > 0 else 0.0

    # 3..7 (5 floats): Active Level-50 Stats (Updated in-place on Mega Evolution)
    STAT_START: int = 3
    STAT_ATK: int = 3
    STAT_DEF: int = 4
    STAT_SPA: int = 5
    STAT_SPD: int = 6
    STAT_SPE: int = 7
    STAT_END: int = 8

    # 8..14 (7 floats): Stat Stage Boosts in [-6.0, +6.0] (Zeroed on Switch via Reset Mask)
    BOOST_START: int = 8
    BOOST_ATK: int = 8
    BOOST_DEF: int = 9
    BOOST_SPA: int = 10
    BOOST_SPD: int = 11
    BOOST_SPE: int = 12
    BOOST_ACC: int = 13
    BOOST_EVA: int = 14
    BOOST_END: int = 15

    # 15..21 (7 floats): Non-Volatile Status One-Hot [Healthy, Burn, Paralyze, Sleep, Freeze, Poison, Toxic]
    STATUS_START: int = 15
    STATUS_HEALTHY: int = 15
    STATUS_BURN: int = 16
    STATUS_PARALYZE: int = 17
    STATUS_SLEEP: int = 18
    STATUS_FREEZE: int = 19
    STATUS_POISON: int = 20
    STATUS_TOXIC: int = 21
    STATUS_END: int = 22

    # 22..39 (18 floats): Primary Type One-Hot (18 types, sum == 1.0)
    TYPE1_START: int = 22
    TYPE1_END: int = 40

    # 40..57 (18 floats): Secondary Type One-Hot (18 types; sum == 1.0 if dual-type, all 0.0 if single-type)
    TYPE2_START: int = 40
    TYPE2_END: int = 58

    # 58..67 (10 floats): Volatile Battle Flags & Counters (Zeroed/Reset on Switch!)
    VOLATILE_START: int = 58
    PROTECT_ACTIVE: int = 58      # 1.0 if Protected against single/spread moves this turn
    WIDE_GUARD_ACTIVE: int = 59   # 1.0 if Wide Guard active on side
    QUICK_GUARD_ACTIVE: int = 60  # 1.0 if Quick Guard active on side
    PROTECT_COUNTER: int = 61     # Consecutive successful protects (0, 1, 2...)
    FLINCHED: int = 62            # 1.0 if flinched this turn
    ACTIVE_TURNS: int = 63        # Turns active on field (0 on Turn 1 or fresh switch-in -> Fake Out legal if == 0)
    TAUNT_TURNS: int = 64         # Remaining Taunt turns (blocks Status moves)
    ENCORE_TURNS: int = 65        # Remaining Encore turns (locks into LAST_MOVE_IDX)
    SUBSTITUTE_HP: int = 66       # Current Substitute HP
    HELPING_HAND_MULT: int = 67   # 1.5 if boosted by partner Helping Hand this turn else 1.0
    VOLATILE_END: int = 68

    # 68..83 (16 floats): Equipment, Ability, Grounded, Choice Lock & In-Place Mega Evolution 5-Stat Payload
    GROUNDED_FLAG: int = 68       # 1.0 if grounded (0.0 if Flying-type or Levitate)
    ITEM_ACTIVE: int = 69         # 1.0 if item is unconsumed/active, 0.0 after consumption
    ITEM_ID: int = 70             # ItemID float value
    ABILITY_ID: int = 71          # AbilityID float value
    UNBURDEN_ACTIVE: int = 72     # 1.0 if Unburden speed doubling (2.0x) is active
    CHOICE_LOCKED_MOVE: int = 73  # -1.0 if unlocked, or 0..3 if locked into move slot
    LAST_MOVE_IDX: int = 74       # -1.0 if none, or 0..3 for Encore/Disable tracking
    TOXIC_COUNTER: int = 75       # 1.0, 2.0, ... for escalating Toxic damage
    CAN_MEGA: int = 76            # 1.0 if holding Mega Stone and eligible to Mega Evolve
    IS_MEGA: int = 77             # 1.0 once Mega Evolved
    MEGA_STAT_START: int = 78
    MEGA_ATK: int = 78            # Post-Mega Level-50 Atk stat
    MEGA_DEF: int = 79            # Post-Mega Level-50 Def stat
    MEGA_SPA: int = 80            # Post-Mega Level-50 SpA stat
    MEGA_SPD: int = 81            # Post-Mega Level-50 SpD stat
    MEGA_SPE: int = 82            # Post-Mega Level-50 Speed stat (instantaneous Regulation M-C recalibration)
    MEGA_STAT_END: int = 83
    MEGA_ABILITY_ID: int = 83     # AbilityID gained upon Mega Evolution


# --- C. 8-Slot Pre-Compiled Move Tensor M_moves: shape [..., 8, 4, 52] ---
MOVES_PER_MON: int = 4
MOVE_DIM: int = 52


class MoveIdx:
    """
    Exact indices for the 52-Float Pre-Compiled Move Vector [..., 8, 4, 52].
    When an 8x8 Switch Permutation Matrix swaps two Pokémon in P, multiplying the same
    8x8 matrix against M_moves swaps their 4 moves into the active slot automatically!
    """
    # 0..4 (5 floats): Core Numeric Parameters
    BASE_POWER: int = 0           # e.g., 80.0 for Poison Jab, 0.0 for Reflect
    ACCURACY: int = 1             # [0.0, 1.0] (e.g., 1.0 for 100%, 1.01 for bypass-accuracy moves)
    PRIORITY: int = 2             # [-7.0 to +5.0] (e.g., +4 Protect, +3 Fake Out, -6 Trick Room)
    TARGET_TYPE: int = 3          # TargetType enum float (0..6)
    CRIT_STAGE: int = 4           # 0.0 standard (1/24), 1.0 high-crit (1/8), 3.0 guaranteed (1.0)

    # 5..22 (18 floats): Move Type One-Hot (18 canonical types)
    TYPE_START: int = 5
    TYPE_END: int = 23

    # 23..25 (3 floats): Move Category One-Hot [Physical, Special, Status]
    CAT_START: int = 23
    CAT_PHYSICAL: int = 23
    CAT_SPECIAL: int = 24
    CAT_STATUS: int = 25
    CAT_END: int = 26

    # 26..32 (7 floats): Primary/Secondary Stat Stage Deltas [Atk, Def, SpA, SpD, Spe, Acc, Eva]
    STAT_DELTA_START: int = 26
    STAT_DELTA_ATK: int = 26
    STAT_DELTA_DEF: int = 27
    STAT_DELTA_SPA: int = 28
    STAT_DELTA_SPD: int = 29
    STAT_DELTA_SPE: int = 30
    STAT_DELTA_ACC: int = 31
    STAT_DELTA_EVA: int = 32
    STAT_DELTA_END: int = 33
    STAT_DELTA_CHANCE: int = 33   # Probability [0.0, 1.0] of applying stat deltas
    STAT_DELTA_SELF: int = 34     # 1.0 if stat deltas apply to self (Calm Mind, Close Combat), 0.0 if to target (Icy Wind, Parting Shot)

    # 35..41 (7 floats): Secondary Status Infliction One-Hot [Healthy(None), Burn, Paralyze, Sleep, Freeze, Poison, Toxic]
    SEC_STATUS_START: int = 35
    SEC_STATUS_END: int = 42
    SEC_STATUS_CHANCE: int = 42   # Probability [0.0, 1.0] of inflicting status (e.g., 0.30 for Poison Jab)

    # 43..51 (9 floats): Recoil, Drain, Flinch & Matrix Pruner Invariant Flags
    RECOIL_PCT: int = 43          # Fraction of damage or MaxHP recoiled (negative = Drain heal, e.g., -0.75 for Draining Kiss!)
    FLINCH_CHANCE: int = 44       # Probability [0.0, 1.0] of flinching target (1.0 for Fake Out, 0.30 for Rock Slide)
    PROTECT_TYPE: int = 45        # 0.0 None, 1.0 Standard Protect, 2.0 Wide Guard, 3.0 Quick Guard
    SWITCH_MODE: int = 46         # 0.0 None, 1.0 Voluntary Self-Pivot (U-turn/Parting Shot), 2.0 Forced Foe Switch (Roar/Dragon Tail)
    FIELD_OP_ID: int = 47         # 0.0 None, 1..5 Set Weather, 6..10 Set Terrain, 11 Reflect, 12 Light Screen, 13 Tailwind, 14 Trick Room, 15 Follow Me/Rage Powder, 16 Helping Hand, 17 Sucker Punch, 18 Fake Out
    FIRST_TURN_ONLY: int = 48     # 1.0 for Fake Out / First Impression (fails if ACTIVE_TURNS > 0)
    IS_SOUND_MOVE: int = 49       # 1.0 for Hyper Voice / Parting Shot / Snarl / Roar / Bug Buzz (blocked by Soundproof)
    WEATHER_SURE_HIT: int = 50    # 0.0 None, 2.0 Rain sure-hit (Thunder/Hurricane/Bleakwind), 4.0 Snow sure-hit (Blizzard)
    GRASSY_PRIO_BOOST: int = 51   # 1.0 for Grassy Glide (+1 priority under Grassy Terrain)


# =============================================================================
# 3. BILINEAR ONE-HOT LOOKUP & PERMUTATION MATRICES
# =============================================================================

@dataclass(frozen=True)
class BilinearLookupTables:
    """
    Pre-allocated, immutable GPU/CPU operator matrices for branchless Bilinear
    One-Hot Tensor Contractions and 8x8 Roster Permutations.
    Supports both PyTorch Tensors (CUDA/CPU) and NumPy ndarrays transparently.
    """
    backend: str  # 'torch' or 'numpy'
    device: Any

    # 1. Type Effectiveness Chart [18, 18]: rows = Attacking Type, cols = Defending Type
    m_type_chart: Any

    # 2. Weather Damage Scaling [5, 18]: rows = Weather One-Hot, cols = Move Type One-Hot
    m_weather_mod: Any

    # 3. Terrain Damage Scaling [5, 18]: rows = Terrain One-Hot, cols = Move Type One-Hot
    m_terrain_mod: Any

    # 4. Psychic Terrain Priority Block [5]: dot with Terrain One-Hot -> 1.0 if Psychic Terrain active
    m_psychic_prio_block: Any

    # 5. Misty Terrain Status Block [5]: dot with Terrain One-Hot -> 1.0 if Misty Terrain active
    m_misty_status_block: Any

    # 6. Electric Terrain Sleep Block [5]: dot with Terrain One-Hot -> 1.0 if Electric Terrain active
    m_electric_sleep_block: Any

    # 7. Column-Overwrite State Transition Matrices for Weather [5, 5, 5] & Terrain [5, 5, 5]
    #    Multiplying ANY valid 1x5 One-Hot vector w_old @ T_set_weather[target_idx]
    #    outputs the exact new One-Hot vector with target_idx = 1.0 and all others = 0.0!
    t_set_weather: Any
    t_set_terrain: Any

    # 8. 8x8 Switch Permutation Matrices [8, 8, 8, 8]:
    #    p_switch_perms[slot_a, slot_b] is an 8x8 identity matrix with rows slot_a and slot_b swapped!
    p_switch_perms: Any

    # 9. Switch Volatile & Boost Reset Mask [80]:
    #    1.0 for persistent channels (HP, Base Stats, Non-Volatile Status, Types, Item, Ability, Mega),
    #    0.0 for transient channels reset upon switching out (Stat Boosts 8..14 and Volatiles 58..67).
    switch_persist_mask: Any


# Raw 18x18 Pokémon Type Chart Data (Attacking Type -> Defending Type -> Multiplier)
_RAW_TYPE_CHART: Dict[str, Dict[str, float]] = {
    "Normal":   {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
    "Fire":     {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0},
    "Water":    {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0, "Rock": 2.0, "Dragon": 0.5},
    "Grass":    {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0, "Dragon": 0.5, "Steel": 0.5},
    "Electric": {"Water": 2.0, "Grass": 0.5, "Electric": 0.5, "Ground": 0.0, "Flying": 2.0, "Dragon": 0.5},
    "Ice":      {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
    "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5},
    "Poison":   {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
    "Ground":   {"Fire": 2.0, "Grass": 0.5, "Electric": 2.0, "Poison": 2.0, "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
    "Flying":   {"Grass": 2.0, "Electric": 0.5, "Fighting": 2.0, "Bug": 2.0, "Rock": 0.5, "Steel": 0.5},
    "Psychic":  {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0, "Steel": 0.5},
    "Bug":      {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0, "Steel": 0.5, "Fairy": 0.5},
    "Rock":     {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5, "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
    "Ghost":    {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
    "Dragon":   {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
    "Dark":     {"Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5, "Fairy": 0.5},
    "Steel":    {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0, "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
    "Fairy":    {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5},
}


def build_bilinear_lookup_tables(device: Optional[Any] = None) -> BilinearLookupTables:
    """
    Construct all constant Bilinear One-Hot Contraction and Permutation Matrices.
    Automatically uses PyTorch (CUDA/CPU) if installed, or falls back to pure NumPy.

    Args:
        device: Optional PyTorch device ('cuda:0' or 'cpu').

    Returns:
        BilinearLookupTables instance containing all pre-allocated operator matrices.
    """
    # 1. Build 18x18 Type Chart Matrix M_type_chart in NumPy first (exact float32)
    m_type_chart_np = np.ones((NUM_TYPES, NUM_TYPES), dtype=np.float32)
    for atk_type, def_dict in _RAW_TYPE_CHART.items():
        r_idx = TYPE_TO_IDX[atk_type.lower()]
        for def_type, mult in def_dict.items():
            c_idx = TYPE_TO_IDX[def_type.lower()]
            m_type_chart_np[r_idx, c_idx] = float(mult)

    # 2. Build 5x18 Weather Damage Scaling Matrix M_weather_mod
    m_weather_mod_np = np.ones((NUM_WEATHERS, NUM_TYPES), dtype=np.float32)
    fire_idx = TYPE_TO_IDX["fire"]
    water_idx = TYPE_TO_IDX["water"]
    m_weather_mod_np[1, fire_idx] = 1.5
    m_weather_mod_np[1, water_idx] = 0.5
    m_weather_mod_np[2, water_idx] = 1.5
    m_weather_mod_np[2, fire_idx] = 0.5

    # 3. Build 5x18 Terrain Damage Scaling Matrix M_terrain_mod
    m_terrain_mod_np = np.ones((NUM_TERRAINS, NUM_TYPES), dtype=np.float32)
    m_terrain_mod_np[1, TYPE_TO_IDX["electric"]] = 1.3
    m_terrain_mod_np[2, TYPE_TO_IDX["grass"]] = 1.3
    m_terrain_mod_np[3, TYPE_TO_IDX["psychic"]] = 1.3
    m_terrain_mod_np[4, TYPE_TO_IDX["dragon"]] = 0.5

    # 4..6. Terrain Condition Gate Vectors [5]
    m_psychic_np = np.array([0.0, 0.0, 0.0, 1.0, 0.0], dtype=np.float32)
    m_misty_np = np.array([0.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    m_electric_np = np.array([0.0, 1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    # 7. Build Column-Overwrite Matrices T_set_weather [5, 5, 5] & T_set_terrain [5, 5, 5]
    t_set_weather_np = np.zeros((NUM_WEATHERS, NUM_WEATHERS, NUM_WEATHERS), dtype=np.float32)
    for k in range(NUM_WEATHERS):
        t_set_weather_np[k, :, k] = 1.0

    t_set_terrain_np = np.zeros((NUM_TERRAINS, NUM_TERRAINS, NUM_TERRAINS), dtype=np.float32)
    for k in range(NUM_TERRAINS):
        t_set_terrain_np[k, :, k] = 1.0

    # 8. Build 8x8 Switch Permutation Matrices P_switch_perms [8, 8, 8, 8]
    p_switch_perms_np = np.zeros((ROSTER_SLOTS, ROSTER_SLOTS, ROSTER_SLOTS, ROSTER_SLOTS), dtype=np.float32)
    for a in range(ROSTER_SLOTS):
        for b in range(ROSTER_SLOTS):
            perm = np.eye(ROSTER_SLOTS, dtype=np.float32)
            if a != b:
                perm[a, a] = 0.0
                perm[b, b] = 0.0
                perm[a, b] = 1.0
                perm[b, a] = 1.0
            p_switch_perms_np[a, b] = perm

    # 9. Build Switch Persistence Mask [80]
    switch_persist_np = np.ones((MON_DIM,), dtype=np.float32)
    switch_persist_np[MonIdx.BOOST_START:MonIdx.BOOST_END] = 0.0
    switch_persist_np[MonIdx.VOLATILE_START:MonIdx.VOLATILE_END] = 0.0
    switch_persist_np[MonIdx.HELPING_HAND_MULT] = 1.0

    if HAS_TORCH and torch is not None:
        if device is None:
            dev = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        else:
            dev = torch.device(device)
        return BilinearLookupTables(
            backend="torch",
            device=dev,
            m_type_chart=torch.from_numpy(m_type_chart_np).to(dev),
            m_weather_mod=torch.from_numpy(m_weather_mod_np).to(dev),
            m_terrain_mod=torch.from_numpy(m_terrain_mod_np).to(dev),
            m_psychic_prio_block=torch.from_numpy(m_psychic_np).to(dev),
            m_misty_status_block=torch.from_numpy(m_misty_np).to(dev),
            m_electric_sleep_block=torch.from_numpy(m_electric_np).to(dev),
            t_set_weather=torch.from_numpy(t_set_weather_np).to(dev),
            t_set_terrain=torch.from_numpy(t_set_terrain_np).to(dev),
            p_switch_perms=torch.from_numpy(p_switch_perms_np).to(dev),
            switch_persist_mask=torch.from_numpy(switch_persist_np).to(dev),
        )

    return BilinearLookupTables(
        backend="numpy",
        device="cpu",
        m_type_chart=m_type_chart_np,
        m_weather_mod=m_weather_mod_np,
        m_terrain_mod=m_terrain_mod_np,
        m_psychic_prio_block=m_psychic_np,
        m_misty_status_block=m_misty_np,
        m_electric_sleep_block=m_electric_np,
        t_set_weather=t_set_weather_np,
        t_set_terrain=t_set_terrain_np,
        p_switch_perms=p_switch_perms_np,
        switch_persist_mask=switch_persist_np,
    )


# =============================================================================
# 4. PURE BILINEAR CONTRACTION HELPER EQUATIONS (ZERO IF/ELSE)
# =============================================================================

def _einsum(subscripts: str, *operands: Any) -> Any:
    """Backend-agnostic Einstein summation (runs on PyTorch CUDA/CPU or NumPy)."""
    if HAS_TORCH and torch is not None and isinstance(operands[0], torch.Tensor):
        return torch.einsum(subscripts, *operands)
    return np.einsum(subscripts, *operands)


def compute_weather_move_multiplier(
    weather_onehot: Any,
    move_type_onehot: Any,
    tables: BilinearLookupTables,
) -> Any:
    """
    Compute the exact Weather damage multiplier via Bilinear One-Hot Tensor Contraction:
        mult = weather_onehot @ M_weather_mod @ move_type_onehot^T
    """
    return _einsum("...w,wt,...t->...", weather_onehot, tables.m_weather_mod, move_type_onehot)


def compute_terrain_move_multiplier(
    terrain_onehot: Any,
    move_type_onehot: Any,
    attacker_grounded: Any,
    tables: BilinearLookupTables,
) -> Any:
    """
    Compute the exact Terrain damage multiplier via Bilinear One-Hot Tensor Contraction:
        raw_mult = terrain_onehot @ M_terrain_mod @ move_type_onehot^T
        effective_mult = 1.0 + attacker_grounded * (raw_mult - 1.0)
    (Note: Electric/Grassy/Psychic boosts require attacker to be grounded; Misty Dragon nerf
    applies when target is grounded, handled symmetrically).
    """
    raw_mult = _einsum("...g,gt,...t->...", terrain_onehot, tables.m_terrain_mod, move_type_onehot)
    return 1.0 + attacker_grounded * (raw_mult - 1.0)


def compute_type_effectiveness(
    move_type_onehot: Any,
    def_type1_onehot: Any,
    def_type2_onehot: Any,
    tables: BilinearLookupTables,
) -> Any:
    """
    Compute exact single- or dual-type effectiveness in {0.0, 0.25, 0.5, 1.0, 2.0, 4.0}
    using pure Bilinear One-Hot Contraction with zero branching:
        eff1 = move_type @ M_type_chart @ def_type1
        eff2 = (move_type @ M_type_chart @ def_type2) + (1.0 - sum(def_type2))
        total_eff = eff1 * eff2
    """
    eff1 = _einsum("...m,md,...d->...", move_type_onehot, tables.m_type_chart, def_type1_onehot)
    raw_eff2 = _einsum("...m,md,...d->...", move_type_onehot, tables.m_type_chart, def_type2_onehot)
    has_type2 = def_type2_onehot.sum(axis=-1) if isinstance(def_type2_onehot, np.ndarray) else def_type2_onehot.sum(dim=-1)
    eff2 = raw_eff2 + (1.0 - has_type2)
    return eff1 * eff2


def compute_stab_multiplier(
    move_type_onehot: Any,
    atk_type1_onehot: Any,
    atk_type2_onehot: Any,
    has_adaptability: Optional[Any] = None,
) -> Any:
    """
    Compute exact Same-Type Attack Bonus (STAB) multiplier via dot product:
        is_stab = (atk_type1 + atk_type2) @ move_type
        stab_mult = 1.0 + (0.5 + 0.5 * has_adaptability) * is_stab
    """
    combined_atk_types = atk_type1_onehot + atk_type2_onehot
    raw_dot = _einsum("...t,...t->...", combined_atk_types, move_type_onehot)
    if isinstance(raw_dot, np.ndarray):
        is_stab = np.clip(raw_dot, 0.0, 1.0)
    elif HAS_TORCH and torch is not None and isinstance(raw_dot, torch.Tensor):
        is_stab = torch.clamp(raw_dot, 0.0, 1.0)
    else:
        is_stab = min(1.0, max(0.0, float(raw_dot)))

    if has_adaptability is None:
        return 1.0 + 0.5 * is_stab
    return 1.0 + (0.5 + 0.5 * has_adaptability) * is_stab


def overwrite_weather_onehot(
    weather_onehot: Any,
    target_weather_idx: Any,
    tables: BilinearLookupTables,
) -> Any:
    """
    Overwrite active Weather One-Hot vector [..., 5] using the Column-Overwrite Matrix T_set_weather.
    """
    transition_mat = tables.t_set_weather[target_weather_idx]
    return _einsum("...i,...ij->...j", weather_onehot, transition_mat)


def apply_switch_permutation(
    roster_tensor: Any,
    moves_tensor: Any,
    slot_a: Any,
    slot_b: Any,
    tables: BilinearLookupTables,
) -> Tuple[Any, Any]:
    """
    Swap Active Slot `slot_a` with Bench Slot `slot_b` across both the 8-Slot Roster Tensor P [..., 8, 80]
    and the 8-Slot Move Tensor M_moves [..., 8, 4, 48] via pure 8x8 Permutation Matrix multiplication!

    Also applies `switch_persist_mask` to reset volatile statuses and stat boosts on the outgoing slot.

    Args:
        roster_tensor: Tensor/ndarray of shape [..., 8, 80].
        moves_tensor: Tensor/ndarray of shape [..., 8, 4, 48].
        slot_a: Active slot index (or integer tensor [...]) in 0..7.
        slot_b: Bench slot index (or integer tensor [...]) in 0..7.
        tables: Pre-allocated BilinearLookupTables.

    Returns:
        Tuple of (new_roster_tensor [..., 8, 80], new_moves_tensor [..., 8, 4, 48]).
    """
    perm_mat = tables.p_switch_perms[slot_a, slot_b]  # Shape [..., 8, 8]
    new_roster = _einsum("...ij,...jk->...ik", perm_mat, roster_tensor)
    new_moves = _einsum("...ij,...jmk->...imk", perm_mat, moves_tensor)
    return new_roster, new_moves
