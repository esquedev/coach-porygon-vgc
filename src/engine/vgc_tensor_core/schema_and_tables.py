# -*- coding: utf-8 -*-
"""Regulation M-C State Tensor Schema & Bilinear One-Hot Lookup Matrices.

Defines the exact tensor dimensions, feature slice indices (`FieldIdx`, `MonIdx`,
`MoveIdx`), and constant linear-algebra operator matrices for the One-Turn VGC
Tensor Engine under `trainer_1` and `trainer_2` semantics:

1. Global Field Tensor `F`: shape `[..., 24]`
2. 8-Slot Unified Roster Tensor `P`: shape `[..., 8, 84]`
   - Slots 0, 1: `trainer_1` Active (`SLOT_TRAINER_1_A`, `SLOT_TRAINER_1_B`)
   - Slots 2, 3: `trainer_1` Bench  (`SLOT_TRAINER_1_BENCH1`, `SLOT_TRAINER_1_BENCH2`)
   - Slots 4, 5: `trainer_2` Active (`SLOT_TRAINER_2_A`, `SLOT_TRAINER_2_B`)
   - Slots 6, 7: `trainer_2` Bench  (`SLOT_TRAINER_2_BENCH1`, `SLOT_TRAINER_2_BENCH2`)
3. 8-Slot Programmatic Move Tensor `M_moves`: shape `[..., 8, 4, 56]`
   - Compiled dynamically on the fly from Showdown's `moves.jsonl` via in-memory
     DuckDB (`VGCDataRegistry`).
   - Includes 56 channels covering Base Power, Accuracy, Priority, Target Type,
     Crit Stage (`willCrit`), 18-Type One-Hot, 3-Category One-Hot, 7 Stat Stage
     Deltas + Chance + Self/Target flag, 7 Status Procs + Chance, Recoil/Drain/Heal,
     Flinch Chance, Protect Type, Switch Mode, Field Op ID, Turn-1 Gate, Sound Flag,
     Weather Sure-Hit, Grassy Priority Boost, Expected Multi-Hit Count (`EXPECTED_HITS`),
     Offensive Stat Override (`Body Press` / `Foul Play`), Defensive Stat Override
     (`Psyshock`), and Substitute Bypass.
"""

from __future__ import annotations

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
WEATHER_TO_IDX: Dict[str, int] = {
    "clear": 0,
    "none": 0,
    "": 0,
    "sun": 1,
    "sunnyday": 1,
    "desolateland": 1,
    "rain": 2,
    "raindance": 2,
    "primordialsea": 2,
    "sand": 3,
    "sandstorm": 3,
    "snow": 4,
    "hail": 4,
    "chillyreception": 4,
}

NUM_TERRAINS: int = 5
CANONICAL_TERRAINS: Tuple[str, ...] = (
    "None",      # 0
    "Electric",  # 1
    "Grassy",    # 2
    "Psychic",   # 3
    "Misty",     # 4
)
TERRAIN_TO_IDX: Dict[str, int] = {
    "none": 0,
    "clear": 0,
    "": 0,
    "electric": 1,
    "electricterrain": 1,
    "grassy": 2,
    "grassyterrain": 2,
    "psychic": 3,
    "psychicterrain": 3,
    "misty": 4,
    "mistyterrain": 4,
}

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
    "healthy": 0,
    "none": 0,
    "": 0,
    "burn": 1,
    "brn": 1,
    "paralyze": 2,
    "par": 2,
    "sleep": 3,
    "slp": 3,
    "freeze": 4,
    "frz": 4,
    "poison": 5,
    "psn": 5,
    "toxic": 6,
    "tox": 6,
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
    LOADED_DICE = 19
    LIGHT_CLAY = 20
    TYPE_BOOST_ITEM = 21
    SCOPE_LENS = 22


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
    ROCK_HEAD = 45
    ROUGH_SKIN = 46
    POISON_TOUCH = 47
    CLEAR_BODY = 48
    FLOWER_VEIL = 49
    EMERGENCY_EXIT = 50
    SKILL_LINK = 51
    JUSTIFIED = 52
    SHIELD_DUST = 53


class TargetType(IntEnum):
    """Canonical Move Targeting Archetypes in VGC Doubles."""

    SINGLE_FOE = 0          # Single-target attack (directed at Opp_A, Opp_B, or Partner)
    ALL_ADJACENT_FOES = 1   # Opposing spread move (Heat Wave, Dazzling Gleam, Rock Slide, Icy Wind)
    ALL_ADJACENT = 2        # Full-board spread move hitting partner + both foes (Earthquake, Discharge)
    SELF = 3                # Self-targeting status/buff/Protect (Protect, Calm Mind, Swords Dance)
    ALLY = 4                # Partner-targeting support (Helping Hand, Coaching, Aromatic Mist)
    ALLY_SIDE = 5           # Team field support (Reflect, Light Screen, Tailwind, Wide Guard, Quick Guard)
    GLOBAL_FIELD = 6        # Global weather/terrain/room (Sunny Day, Rain Dance, Trick Room, Gravity, Haze)


class FieldOpID(IntEnum):
    """Canonical Field & Tactical Special Operation IDs for `MoveIdx.FIELD_OP_ID`."""

    NONE = 0
    SET_SUN = 1
    SET_RAIN = 2
    SET_SAND = 3
    SET_SNOW = 4
    SET_ELECTRIC_TERRAIN = 6
    SET_GRASSY_TERRAIN = 7
    SET_PSYCHIC_TERRAIN = 8
    SET_MISTY_TERRAIN = 9
    REFLECT = 11
    LIGHT_SCREEN = 12
    TAILWIND = 13
    TRICK_ROOM = 14
    FOLLOW_ME = 15
    HELPING_HAND = 16
    SUCKER_PUNCH = 17
    FAKE_OUT = 18
    AURORA_VEIL = 19
    GRAVITY = 20
    HAZE = 21


class OverrideOffStat(IntEnum):
    """Offensive Stat Override codes for `MoveIdx.OVERRIDE_OFF_STAT`."""

    STANDARD = 0   # Physical uses Attacker Atk; Special uses Attacker SpA
    USER_DEF = 1   # Body Press: uses Attacker Def
    TARGET_ATK = 2 # Foul Play: uses Defender Atk


class OverrideDefStat(IntEnum):
    """Defensive Stat Override codes for `MoveIdx.OVERRIDE_DEF_STAT`."""

    STANDARD = 0   # Physical uses Defender Def; Special uses Defender SpD
    TARGET_DEF = 1 # Psyshock / Psystrike / Secret Sword: Special move using Defender Def


# =============================================================================
# 2. TENSOR SHAPE & FEATURE INDEX SPECIFICATION (`trainer_1` & `trainer_2`)
# =============================================================================

# Roster Slots (8 total in 4v4 VGC Doubles)
ROSTER_SLOTS: int = 8
SLOT_TRAINER_1_A: int = 0
SLOT_TRAINER_1_B: int = 1
SLOT_TRAINER_1_BENCH1: int = 2
SLOT_TRAINER_1_BENCH2: int = 3
SLOT_TRAINER_2_A: int = 4
SLOT_TRAINER_2_B: int = 5
SLOT_TRAINER_2_BENCH1: int = 6
SLOT_TRAINER_2_BENCH2: int = 7


# --- A. Global Field Tensor F: shape [..., 24] ---
FIELD_DIM: int = 24


class FieldIdx:
    """Exact indices for the 24-element Global Field Tensor `F`."""

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

    # 14..18: trainer_1 Side Conditions
    TRAINER_1_TAILWIND_TURNS: int = 14
    TRAINER_1_REFLECT_TURNS: int = 15
    TRAINER_1_LIGHT_SCREEN_TURNS: int = 16
    TRAINER_1_AURORA_VEIL_TURNS: int = 17
    TRAINER_1_MEGA_USED: int = 18

    # 19..23: trainer_2 Side Conditions
    TRAINER_2_TAILWIND_TURNS: int = 19
    TRAINER_2_REFLECT_TURNS: int = 20
    TRAINER_2_LIGHT_SCREEN_TURNS: int = 21
    TRAINER_2_AURORA_VEIL_TURNS: int = 22
    TRAINER_2_MEGA_USED: int = 23


# --- B. 8-Slot Unified Roster Tensor P: shape [..., 8, 84] ---
MON_DIM: int = 84


class MonIdx:
    """Exact indices for the 84-Float Per-Pokémon Feature Vector `[..., 8, 84]`."""

    # 0..2 (3 floats): HP Channels
    HP_CUR: int = 0
    HP_MAX: int = 1
    ALIVE_FLAG: int = 2

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

    # 40..57 (18 floats): Secondary Type One-Hot (18 types; sum == 1.0 if dual-type, 0.0 if single-type)
    TYPE2_START: int = 40
    TYPE2_END: int = 58

    # 58..67 (10 floats): Volatile Battle Flags & Counters (Zeroed/Reset on Switch!)
    VOLATILE_START: int = 58
    PROTECT_ACTIVE: int = 58
    WIDE_GUARD_ACTIVE: int = 59
    QUICK_GUARD_ACTIVE: int = 60
    PROTECT_COUNTER: int = 61
    FLINCHED: int = 62
    ACTIVE_TURNS: int = 63        # 0.0 on first active turn (Fake Out / First Impression legal when == 0.0)
    TAUNT_TURNS: int = 64
    ENCORE_TURNS: int = 65
    SUBSTITUTE_HP: int = 66
    HELPING_HAND_MULT: int = 67
    VOLATILE_END: int = 68

    # 68..83 (16 floats): Equipment, Ability, Grounded, Choice Lock & In-Place Mega Evolution 5-Stat Payload
    GROUNDED_FLAG: int = 68
    ITEM_ACTIVE: int = 69
    ITEM_ID: int = 70
    ABILITY_ID: int = 71
    UNBURDEN_ACTIVE: int = 72
    CHOICE_LOCKED_MOVE: int = 73  # -1.0 if unlocked, or 0..3 if locked into move index
    LAST_MOVE_IDX: int = 74       # -1.0 if none, or 0..3 for Encore/Disable tracking
    TOXIC_COUNTER: int = 75
    CAN_MEGA: int = 76
    IS_MEGA: int = 77
    MEGA_STAT_START: int = 78
    MEGA_ATK: int = 78
    MEGA_DEF: int = 79
    MEGA_SPA: int = 80
    MEGA_SPD: int = 81
    MEGA_SPE: int = 82
    MEGA_STAT_END: int = 83
    MEGA_ABILITY_ID: int = 83


# --- C. 8-Slot Programmatic Move Tensor M_moves: shape [..., 8, 4, 56] ---
MOVES_PER_MON: int = 4
MOVE_DIM: int = 56


class MoveIdx:
    """Exact indices for the 56-Float Programmatic Move Vector `[..., 8, 4, 56]`."""

    # 0..4 (5 floats): Core Numeric Parameters
    BASE_POWER: int = 0
    ACCURACY: int = 1             # [0.0, 1.0] or 1.01 for never-miss moves (accuracy: true)
    PRIORITY: int = 2             # [-7.0 to +5.0]
    TARGET_TYPE: int = 3          # TargetType enum float (0..6)
    CRIT_STAGE: int = 4           # 0.0 standard, 1.0 high-crit, 3.0 guaranteed (willCrit: true)

    # 5..22 (18 floats): Move Type One-Hot (18 canonical types)
    TYPE_START: int = 5
    TYPE_END: int = 23

    # 23..25 (3 floats): Move Category One-Hot [Physical, Special, Status]
    CAT_START: int = 23
    CAT_PHYSICAL: int = 23
    CAT_SPECIAL: int = 24
    CAT_STATUS: int = 25
    CAT_END: int = 26

    # 26..34 (9 floats): Primary/Secondary Stat Stage Deltas [Atk, Def, SpA, SpD, Spe, Acc, Eva]
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
    STAT_DELTA_SELF: int = 34     # 1.0 if applied to self/ally, 0.0 if applied to target

    # 35..42 (8 floats): Status Infliction One-Hot [Healthy(None), Burn, Paralyze, Sleep, Freeze, Poison, Toxic]
    SEC_STATUS_START: int = 35
    SEC_STATUS_END: int = 42
    SEC_STATUS_CHANCE: int = 42   # Probability [0.0, 1.0] of inflicting status

    # 43..51 (9 floats): Recoil, Drain, Flinch & Matrix Pruner Invariant Flags
    RECOIL_PCT: int = 43          # +fraction for recoil (0.33), -fraction for drain/heal (-0.75, -0.50)
    FLINCH_CHANCE: int = 44       # Probability [0.0, 1.0] of flinching target
    PROTECT_TYPE: int = 45        # 0.0 None, 1.0 Standard Protect, 2.0 Wide Guard, 3.0 Quick Guard
    SWITCH_MODE: int = 46         # 0.0 None, 1.0 Voluntary Self-Pivot, 2.0 Forced Foe Switch
    FIELD_OP_ID: int = 47         # FieldOpID enum float
    FIRST_TURN_ONLY: int = 48     # 1.0 for Fake Out / First Impression / Mat Block
    IS_SOUND_MOVE: int = 49       # 1.0 when flags.sound == 1
    WEATHER_SURE_HIT: int = 50    # 0.0 None, 2.0 Rain sure-hit, 4.0 Snow sure-hit
    GRASSY_PRIO_BOOST: int = 51   # 1.0 for Grassy Glide

    # 52..55 (4 floats): Multi-Hit & Stat Override Channels from DuckDB moves.jsonl
    EXPECTED_HITS: int = 52       # 1.0 default, 2.0 Dual Wingbeat, 3.0 Surging Strikes, 3.1 [2..5] multi-hit
    OVERRIDE_OFF_STAT: int = 53   # OverrideOffStat (0.0 standard, 1.0 Body Press Def, 2.0 Foul Play Target Atk)
    OVERRIDE_DEF_STAT: int = 54   # OverrideDefStat (0.0 standard, 1.0 Psyshock/Psystrike/Secret Sword Def)
    BYPASS_SUB: int = 55          # 1.0 when flags.bypasssub == 1 or flags.sound == 1


# =============================================================================
# 3. BILINEAR ONE-HOT LOOKUP & PERMUTATION MATRICES
# =============================================================================

@dataclass(frozen=True)
class BilinearLookupTables:
    """Pre-allocated operator matrices for branchless Bilinear One-Hot Tensor Contractions."""

    backend: str
    device: Any
    m_type_chart: Any
    m_weather_mod: Any
    m_terrain_mod: Any
    m_psychic_prio_block: Any
    m_misty_status_block: Any
    m_electric_sleep_block: Any
    t_set_weather: Any
    t_set_terrain: Any
    p_switch_perms: Any
    switch_persist_mask: Any


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
    """Construct all constant Bilinear One-Hot Contraction and 8x8 Switch Permutation Matrices."""
    m_type_chart_np = np.ones((NUM_TYPES, NUM_TYPES), dtype=np.float32)
    for atk_type, def_dict in _RAW_TYPE_CHART.items():
        r_idx = TYPE_TO_IDX[atk_type.lower()]
        for def_type, mult in def_dict.items():
            c_idx = TYPE_TO_IDX[def_type.lower()]
            m_type_chart_np[r_idx, c_idx] = float(mult)

    m_weather_mod_np = np.ones((NUM_WEATHERS, NUM_TYPES), dtype=np.float32)
    fire_idx = TYPE_TO_IDX["fire"]
    water_idx = TYPE_TO_IDX["water"]
    m_weather_mod_np[1, fire_idx] = 1.5
    m_weather_mod_np[1, water_idx] = 0.5
    m_weather_mod_np[2, water_idx] = 1.5
    m_weather_mod_np[2, fire_idx] = 0.5

    m_terrain_mod_np = np.ones((NUM_TERRAINS, NUM_TYPES), dtype=np.float32)
    m_terrain_mod_np[1, TYPE_TO_IDX["electric"]] = 1.3
    m_terrain_mod_np[2, TYPE_TO_IDX["grass"]] = 1.3
    m_terrain_mod_np[3, TYPE_TO_IDX["psychic"]] = 1.3
    m_terrain_mod_np[4, TYPE_TO_IDX["dragon"]] = 0.5

    m_psychic_np = np.array([0.0, 0.0, 0.0, 1.0, 0.0], dtype=np.float32)
    m_misty_np = np.array([0.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    m_electric_np = np.array([0.0, 1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    t_set_weather_np = np.zeros((NUM_WEATHERS, NUM_WEATHERS, NUM_WEATHERS), dtype=np.float32)
    for k in range(NUM_WEATHERS):
        t_set_weather_np[k, :, k] = 1.0

    t_set_terrain_np = np.zeros((NUM_TERRAINS, NUM_TERRAINS, NUM_TERRAINS), dtype=np.float32)
    for k in range(NUM_TERRAINS):
        t_set_terrain_np[k, :, k] = 1.0

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
# 4. PURE BILINEAR CONTRACTION HELPER EQUATIONS
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
    """Compute exact Weather damage multiplier via Bilinear One-Hot Tensor Contraction."""
    return _einsum("...w,wt,...t->...", weather_onehot, tables.m_weather_mod, move_type_onehot)


def compute_terrain_move_multiplier(
    terrain_onehot: Any,
    move_type_onehot: Any,
    attacker_grounded: Any,
    tables: BilinearLookupTables,
) -> Any:
    """Compute exact Terrain damage multiplier via Bilinear One-Hot Tensor Contraction."""
    raw_mult = _einsum("...g,gt,...t->...", terrain_onehot, tables.m_terrain_mod, move_type_onehot)
    return 1.0 + attacker_grounded * (raw_mult - 1.0)


def compute_type_effectiveness(
    move_type_onehot: Any,
    def_type1_onehot: Any,
    def_type2_onehot: Any,
    tables: BilinearLookupTables,
) -> Any:
    """Compute exact single- or dual-type effectiveness in `{0.0, 0.25, 0.5, 1.0, 2.0, 4.0}`."""
    eff1 = _einsum("...m,md,...d->...", move_type_onehot, tables.m_type_chart, def_type1_onehot)
    raw_eff2 = _einsum("...m,md,...d->...", move_type_onehot, tables.m_type_chart, def_type2_onehot)
    has_type2 = (
        def_type2_onehot.sum(axis=-1)
        if isinstance(def_type2_onehot, np.ndarray)
        else def_type2_onehot.sum(dim=-1)
    )
    eff2 = raw_eff2 + (1.0 - has_type2)
    return eff1 * eff2


def compute_stab_multiplier(
    move_type_onehot: Any,
    atk_type1_onehot: Any,
    atk_type2_onehot: Any,
    has_adaptability: Optional[Any] = None,
) -> Any:
    """Compute exact Same-Type Attack Bonus (STAB) multiplier via dot product."""
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
    """Overwrite active Weather One-Hot vector `[..., 5]` using `T_set_weather`."""
    transition_mat = tables.t_set_weather[target_weather_idx]
    return _einsum("...i,...ij->...j", weather_onehot, transition_mat)


def apply_switch_permutation(
    roster_tensor: Any,
    moves_tensor: Any,
    slot_a: Any,
    slot_b: Any,
    tables: BilinearLookupTables,
) -> Tuple[Any, Any]:
    """Swap Active Slot `slot_a` with Bench Slot `slot_b` across `P` `[..., 8, 84]` and `M_moves` `[..., 8, 4, 56]`."""
    perm_mat = tables.p_switch_perms[slot_a, slot_b]
    new_roster = _einsum("...ij,...jk->...ik", perm_mat, roster_tensor)
    new_moves = _einsum("...ij,...jmk->...imk", perm_mat, moves_tensor)
    return new_roster, new_moves

