# -*- coding: utf-8 -*-
"""Programmatic Showdown-to-Tensor Compiler & 26x26 Matrix Action Pruner.

Compiles any Pokémon Showdown move, roster slot, or `TurnState` (`trainer_1`
and `trainer_2`) on the fly into aligned tensors (`Field` `[24]`, `Roster`
`[8, 84]`, and `Moves` `[8, 4, 56]`) directly from the in-memory DuckDB
`VGCDataRegistry` (`moves`, `pokedex`, `items`, `abilities` views) — with
ZERO hardcoded move catalog.

Also implements the vectorized `26x26` (`676`) Matrix Action Pruner for
`trainer_1` and `trainer_2`:
- `0..3`   : Base Move `0..3` -> Opponent Slot A (or canonical slot for Spread/Self/Field moves)
- `4..7`   : Base Move `0..3` -> Opponent Slot B
- `8..11`  : Base Move `0..3` -> Partner Slot (Helping Hand, Coaching, Beat Up + Justified, Stomping Tantrum fail-double)
- `12..15` : Mega Evolve + Move `0..3` -> Opponent Slot A
- `16..19` : Mega Evolve + Move `0..3` -> Opponent Slot B
- `20..23` : Mega Evolve + Move `0..3` -> Partner Slot
- `24`     : Switch -> Bench Slot 1
- `25`     : Switch -> Bench Slot 2
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from engine.db_registry import VGCDataRegistry, get_registry
from engine.inference.set_inferencer import TYPE_BOOSTING_ITEMS
from engine.inference.tournament_db import (
    TournamentUsageRepository,
    get_tournament_repository,
)
from engine.state.models import CompiledMove, CompiledPokemonState, TurnState

from .schema_and_tables import (
    AbilityID,
    BilinearLookupTables,
    CATEGORY_TO_IDX,
    FIELD_DIM,
    FieldIdx,
    FieldOpID,
    HAS_TORCH,
    ItemID,
    MON_DIM,
    MOVES_PER_MON,
    MOVE_DIM,
    MonIdx,
    MoveIdx,
    OverrideDefStat,
    OverrideOffStat,
    ROSTER_SLOTS,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_1_BENCH1,
    SLOT_TRAINER_1_BENCH2,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    SLOT_TRAINER_2_BENCH1,
    SLOT_TRAINER_2_BENCH2,
    STATUS_TO_IDX,
    TERRAIN_TO_IDX,
    TYPE_TO_IDX,
    TargetType,
    WEATHER_TO_IDX,
    build_bilinear_lookup_tables,
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

CHOICE_BASE_OPP_A_START: int = 0    # 0..3:   Move 0..3 -> Opp Slot A
CHOICE_BASE_OPP_B_START: int = 4    # 4..7:   Move 0..3 -> Opp Slot B
CHOICE_BASE_ALLY_START: int = 8     # 8..11:  Move 0..3 -> Partner
CHOICE_MEGA_OPP_A_START: int = 12   # 12..15: Mega + Move 0..3 -> Opp Slot A
CHOICE_MEGA_OPP_B_START: int = 16   # 16..19: Mega + Move 0..3 -> Opp Slot B
CHOICE_MEGA_ALLY_START: int = 20    # 20..23: Mega + Move 0..3 -> Partner
CHOICE_SWITCH_BENCH1: int = 24      # 24:     Switch -> Bench 1
CHOICE_SWITCH_BENCH2: int = 25      # 25:     Switch -> Bench 2


# =============================================================================
# 2. ITEM & ABILITY ID MAPPINGS
# =============================================================================

ITEM_NAME_TO_ID: Dict[str, ItemID] = {
    "none": ItemID.NONE,
    "": ItemID.NONE,
    "focus sash": ItemID.FOCUS_SASH,
    "focussash": ItemID.FOCUS_SASH,
    "life orb": ItemID.LIFE_ORB,
    "lifeorb": ItemID.LIFE_ORB,
    "sitrus berry": ItemID.SITRUS_BERRY,
    "sitrusberry": ItemID.SITRUS_BERRY,
    "clear amulet": ItemID.CLEAR_AMULET,
    "clearamulet": ItemID.CLEAR_AMULET,
    "covert cloak": ItemID.COVERT_CLOAK,
    "covertcloak": ItemID.COVERT_CLOAK,
    "safety goggles": ItemID.SAFETY_GOGGLES,
    "safetygoggles": ItemID.SAFETY_GOGGLES,
    "assault vest": ItemID.ASSAULT_VEST,
    "assaultvest": ItemID.ASSAULT_VEST,
    "choice scarf": ItemID.CHOICE_SCARF,
    "choicescarf": ItemID.CHOICE_SCARF,
    "choice band": ItemID.CHOICE_BAND,
    "choiceband": ItemID.CHOICE_BAND,
    "choice specs": ItemID.CHOICE_SPECS,
    "choicespecs": ItemID.CHOICE_SPECS,
    "eject button": ItemID.EJECT_BUTTON,
    "ejectbutton": ItemID.EJECT_BUTTON,
    "eject pack": ItemID.EJECT_PACK,
    "ejectpack": ItemID.EJECT_PACK,
    "red card": ItemID.RED_CARD,
    "redcard": ItemID.RED_CARD,
    "booster energy": ItemID.BOOSTER_ENERGY,
    "boosterenergy": ItemID.BOOSTER_ENERGY,
    "leftovers": ItemID.LEFTOVERS,
    "black sludge": ItemID.BLACK_SLUDGE,
    "blacksludge": ItemID.BLACK_SLUDGE,
    "rocky helmet": ItemID.ROCKY_HELMET,
    "rockyhelmet": ItemID.ROCKY_HELMET,
    "loaded dice": ItemID.LOADED_DICE,
    "loadeddice": ItemID.LOADED_DICE,
    "light clay": ItemID.LIGHT_CLAY,
    "lightclay": ItemID.LIGHT_CLAY,
    "mega stone": ItemID.MEGA_STONE,
}
for _tb_item in TYPE_BOOSTING_ITEMS:
    ITEM_NAME_TO_ID[_tb_item.lower()] = ItemID.TYPE_BOOST_ITEM
    ITEM_NAME_TO_ID[_tb_item.lower().replace(" ", "").replace("-", "")] = ItemID.TYPE_BOOST_ITEM


ABILITY_NAME_TO_ID: Dict[str, AbilityID] = {
    "none": AbilityID.NONE,
    "": AbilityID.NONE,
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
    "pure power": AbilityID.HUGE_POWER,
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
    "dazzling": AbilityID.QUEENLY_MAJESTY,
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
    "mind's eye": AbilityID.MINDS_EYE,
    "minds eye": AbilityID.MINDS_EYE,
    "rock head": AbilityID.ROCK_HEAD,
    "rough skin": AbilityID.ROUGH_SKIN,
    "iron barbs": AbilityID.ROUGH_SKIN,
    "poison touch": AbilityID.POISON_TOUCH,
    "clear body": AbilityID.CLEAR_BODY,
    "white smoke": AbilityID.CLEAR_BODY,
    "full metal body": AbilityID.CLEAR_BODY,
    "flower veil": AbilityID.FLOWER_VEIL,
    "emergency exit": AbilityID.EMERGENCY_EXIT,
    "wimp out": AbilityID.EMERGENCY_EXIT,
    "cloud nine": AbilityID.CLOUD_NINE,
    "cloudnine": AbilityID.CLOUD_NINE,
}


# Variable-BP moves where Showdown stores basePower: 0 because BP depends on weight/speed
VARIABLE_BP_DEFAULTS: Dict[str, float] = {
    "lowkick": 80.0,
    "grassknot": 80.0,
    "heavyslam": 80.0,
    "heatcrash": 80.0,
    "gyroball": 80.0,
    "electroball": 80.0,
    "hardpress": 80.0,
    "beatup": 25.0,
}

# Moves whose stat stage changes live inside Showdown's TypeScript `onHit` function callback
# (which gets stripped when converting moves.ts -> moves.jsonl)
ONHIT_CALLBACK_BOOSTS: Dict[str, Tuple[Dict[str, float], float]] = {
    "partingshot": ({"atk": -1.0, "spa": -1.0}, 0.0),  # (boosts, stat_self=0.0 -> target)
    "bellydrum": ({"atk": 6.0}, 1.0),
    "clangoroussoul": ({"atk": 1.0, "def": 1.0, "spa": 1.0, "spd": 1.0, "spe": 1.0}, 1.0),
    "filletaway": ({"atk": 2.0, "spa": 2.0, "spe": 2.0}, 1.0),
}


def _to_id(text: str) -> str:
    """Convert any Showdown string to its canonical lowercase alphanumeric ID."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _parse_structured_field(val: Any) -> Any:
    """Parse a DuckDB column value that may be a Python dict/list or a JSON/JS string.

    DuckDB's `read_ndjson(..., union_by_name=True)` promotes a column to `VARCHAR`
    across all rows if even a single row in `moves.jsonl` had a string value.
    This helper transparently parses JSON strings and truncated JS object literals.
    """
    if val is None or isinstance(val, (dict, list, int, float, bool)):
        return val
    if not isinstance(val, str):
        return val
    s = val.strip()
    if not s or s == "null":
        return None
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s.lstrip("+-").isdigit():
        return int(s)

    # 1. Try standard JSON decoding
    if s.startswith(("{", "[")):
        try:
            return json.loads(s)
        except Exception:
            # 2. Fallback for truncated JS object fragments like "{ protect: 1"
            kv_pairs = re.findall(r"([A-Za-z0-9_]+)\s*:\s*([A-Za-z0-9_'\"+-]+)", s)
            if kv_pairs:
                parsed_dict: Dict[str, Any] = {}
                for k, v in kv_pairs:
                    clean_v = v.strip("'\"")
                    if clean_v.lstrip("+-").isdigit():
                        parsed_dict[k] = int(clean_v)
                    else:
                        parsed_dict[k] = clean_v
                return parsed_dict
            return {}
    return s


# =============================================================================
# 3. COMPILED STATE & 26x26 ACTION MASK CONTAINERS
# =============================================================================

@dataclass
class CompiledBattleState:
    """Container for the compiled board state tensors.

    Attributes:
        field_tensor: Tensor/ndarray of shape `[24]` (`FieldIdx`).
        roster_tensor: Tensor/ndarray of shape `[8, 84]` (`MonIdx`).
        moves_tensor: Tensor/ndarray of shape `[8, 4, 56]` (`MoveIdx`).
        backend: 'torch' or 'numpy'.
        device: Active torch.device or 'cpu'.
        slot_species: Tuple of 8 species names corresponding to roster slots 0..7.
        slot_move_names: Tuple of 8 tuples of 4 move names corresponding to `[8, 4]`.
    """

    field_tensor: Any
    roster_tensor: Any
    moves_tensor: Any
    backend: str
    device: Any
    slot_species: Tuple[str, ...] = ()
    slot_move_names: Tuple[Tuple[str, ...], ...] = ()


@dataclass
class SideActionMaskResult:
    """Output of the 26x26 Matrix Action Pruner for `trainer_1` or `trainer_2`.

    Attributes:
        trainer_id: 'trainer_1' or 'trainer_2'.
        slot_a_valid_mask: 1D tensor `[26]` in `{0.0, 1.0}` for Active Slot A.
        slot_b_valid_mask: 1D tensor `[26]` in `{0.0, 1.0}` for Active Slot B.
        slot_a_prior_vec: 1D tensor `[26]` soft risk-reward prior scale for Slot A.
        slot_b_prior_vec: 1D tensor `[26]` soft risk-reward prior scale for Slot B.
        joint_valid_mask: 2D matrix `[26, 26]` in `{0.0, 1.0}` after cross-slot collision masks
                          (Simultaneous Double-Mega Lock + Simultaneous Bench Switch Crash).
        joint_prior_mat: 2D matrix `[26, 26]` = `(slot_a_prior[:, None] * slot_b_prior[None, :]) * joint_valid_mask`.
        valid_coords: 2D integer tensor `[N_valid, 2]` of surviving `(choice_a, choice_b)` coordinates.
    """

    trainer_id: str
    slot_a_valid_mask: Any
    slot_b_valid_mask: Any
    slot_a_prior_vec: Any
    slot_b_prior_vec: Any
    joint_valid_mask: Any
    joint_prior_mat: Any
    valid_coords: Any

    @property
    def num_valid_actions(self) -> int:
        """Return count `N_valid` of legal joint actions out of 676."""
        return int(self.valid_coords.shape[0])


# =============================================================================
# 4. PROGRAMMATIC SHOWDOWN-TO-TENSOR COMPILER (IN-MEMORY DUCKDB BACKED)
# =============================================================================

class ShowdownTensorCompiler:
    """Programmatically compiles moves, Pokémon slots, and `TurnState` into tensors via DuckDB."""

    def __init__(
        self,
        tables: Optional[BilinearLookupTables] = None,
        registry: Optional[VGCDataRegistry] = None,
        repo: Optional[TournamentUsageRepository] = None,
        device: Any = None,
        backend: Optional[str] = None,
    ) -> None:
        self.tables: BilinearLookupTables = tables or build_bilinear_lookup_tables(device=device)
        self.backend: str = backend or self.tables.backend
        self.device: Any = self.tables.device
        self.registry: VGCDataRegistry = registry or get_registry()
        self.repo: TournamentUsageRepository = repo or get_tournament_repository()

        # Index all Showdown move rows from in-memory DuckDB `moves` view
        self._moves_by_id: Dict[str, Dict[str, Any]] = {}
        self._move_vector_cache: Dict[str, np.ndarray] = {}
        self._load_duckdb_moves()

    def _load_duckdb_moves(self) -> None:
        """Load all move definitions from the in-memory DuckDB `moves` view."""
        rows = self.registry.query("SELECT * FROM moves;")
        for r in rows:
            m_id = _to_id(r.get("id") or r.get("name") or "")
            m_name = _to_id(r.get("name") or "")
            if m_id:
                self._moves_by_id[m_id] = dict(r)
            if m_name and m_name not in self._moves_by_id:
                self._moves_by_id[m_name] = dict(r)

    # -------------------------------------------------------------------------
    # Programmatic On-The-Fly Move Vector Compilation (`[56]` floats)
    # -------------------------------------------------------------------------

    def compile_move_vector(self, move_spec: Any) -> np.ndarray:
        """Compile any move name, `CompiledMove`, or dict into a 56-float `MoveIdx` vector on the fly.

        Queries Showdown's `moves` view in DuckDB and translates its structured
        fields (`basePower`, `accuracy`, `priority`, `type`, `category`, `target`,
        `flags`, `boosts`, `self`, `secondary`, `secondaries`, `status`,
        `volatileStatus`, `sideCondition`, `pseudoWeather`, `weather`, `terrain`,
        `selfSwitch`, `forceSwitch`, `drain`, `recoil`, `heal`, `critRatio`,
        `willCrit`, `stallingMove`, `multihit`, `overrideOffensiveStat`,
        `overrideDefensiveStat`) into the 56-channel `MoveIdx` representation.
        """
        if isinstance(move_spec, CompiledMove):
            move_name = move_spec.name
            overrides: Dict[str, Any] = {}
        elif isinstance(move_spec, dict):
            move_name = str(move_spec.get("name") or move_spec.get("id") or "")
            overrides = move_spec
        elif isinstance(move_spec, str):
            move_name = move_spec
            overrides = {}
        else:
            move_name = ""
            overrides = {}

        move_id = _to_id(move_name)
        if not overrides and move_id in self._move_vector_cache:
            return self._move_vector_cache[move_id].copy()

        raw_row = self._moves_by_id.get(move_id)
        if raw_row is None and move_name:
            queried = self.registry.get_move(move_name)
            if queried:
                raw_row = dict(queried)
                self._moves_by_id[move_id] = raw_row

        row = dict(raw_row) if raw_row else {"id": move_id, "name": move_name}
        vec = self._compile_move_row_to_vector(row, overrides=overrides)

        if not overrides and move_id:
            self._move_vector_cache[move_id] = vec.copy()
        return vec

    def compile_all_showdown_moves(self) -> Dict[str, np.ndarray]:
        """Programmatically compile all 564 Showdown moves in DuckDB into 56-float vectors."""
        result: Dict[str, np.ndarray] = {}
        for m_id, row in self._moves_by_id.items():
            canonical_name = str(row.get("name") or m_id)
            result[canonical_name] = self.compile_move_vector(canonical_name)
        return result

    def _compile_move_row_to_vector(
        self,
        row: Dict[str, Any],
        overrides: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """Programmatically construct the 56-float `MoveIdx` vector from a DuckDB `moves` row."""
        vec = np.zeros((MOVE_DIM,), dtype=np.float32)
        ovr = overrides or {}
        move_id = _to_id(row.get("id") or row.get("name") or "")

        # 1. Base Power (0)
        raw_bp = ovr.get("bp", ovr.get("basePower", row.get("basePower", 0)))
        bp_val = float(raw_bp or 0.0)
        if bp_val == 0.0 and move_id in VARIABLE_BP_DEFAULTS:
            bp_val = VARIABLE_BP_DEFAULTS[move_id]
        vec[MoveIdx.BASE_POWER] = bp_val

        # 2. Accuracy (1): 1.01 for `accuracy: true` (never-miss), else [0.0, 1.0]
        if "acc" in ovr:
            acc_val = float(ovr["acc"])
        else:
            raw_acc = _parse_structured_field(row.get("accuracy"))
            if raw_acc is True or str(raw_acc).lower() == "true":
                acc_val = 1.01
            else:
                try:
                    num_acc = float(raw_acc)
                    acc_val = num_acc / 100.0 if num_acc > 1.0 else num_acc
                except (TypeError, ValueError):
                    acc_val = 1.0
        vec[MoveIdx.ACCURACY] = acc_val

        # 3. Priority (2)
        raw_prio = ovr.get("prio", ovr.get("priority", row.get("priority", 0)))
        vec[MoveIdx.PRIORITY] = float(raw_prio or 0.0)

        # 4. Target Type (3)
        if "target" in ovr and isinstance(ovr["target"], (int, float, TargetType)):
            target_enum = TargetType(int(ovr["target"]))
        else:
            raw_target = str(ovr.get("target", row.get("target") or "normal"))
            target_enum = self._map_showdown_target(raw_target)
        vec[MoveIdx.TARGET_TYPE] = float(target_enum)

        # 5. Crit Stage (4): `willCrit: true` -> 3.0 (100% crit), `critRatio: N` -> N - 1
        will_crit = _parse_structured_field(row.get("willCrit"))
        if "crit_stage" in ovr:
            vec[MoveIdx.CRIT_STAGE] = float(ovr["crit_stage"])
        elif will_crit is True:
            vec[MoveIdx.CRIT_STAGE] = 3.0
        elif row.get("critRatio") is not None:
            try:
                vec[MoveIdx.CRIT_STAGE] = max(0.0, float(int(row["critRatio"]) - 1))
            except (TypeError, ValueError):
                vec[MoveIdx.CRIT_STAGE] = 0.0

        # 6. Move Type One-Hot (5..22)
        t_name = str(ovr.get("type", row.get("type") or "Normal")).lower()
        t_idx = TYPE_TO_IDX.get(t_name, 0)
        vec[MoveIdx.TYPE_START + t_idx] = 1.0

        # 7. Move Category One-Hot (23..25)
        c_name = str(ovr.get("cat", ovr.get("category", row.get("category") or "Status"))).lower()
        c_idx = CATEGORY_TO_IDX.get(c_name, 2)
        vec[MoveIdx.CAT_START + c_idx] = 1.0

        # Parse structured nested objects from DuckDB row
        flags_obj = _parse_structured_field(row.get("flags"))
        flags: Dict[str, Any] = flags_obj if isinstance(flags_obj, dict) else {}

        boosts_obj = _parse_structured_field(row.get("boosts"))
        primary_boosts: Dict[str, Any] = boosts_obj if isinstance(boosts_obj, dict) else {}

        self_obj = _parse_structured_field(row.get("self"))
        self_dict: Dict[str, Any] = self_obj if isinstance(self_obj, dict) else {}

        self_boost_obj = _parse_structured_field(row.get("selfBoost"))
        self_boost_dict: Dict[str, Any] = self_boost_obj if isinstance(self_boost_obj, dict) else {}

        sec_obj = _parse_structured_field(row.get("secondary"))
        secondary: Dict[str, Any] = sec_obj if isinstance(sec_obj, dict) else {}

        secs_obj = _parse_structured_field(row.get("secondaries"))
        secondaries_list: List[Dict[str, Any]] = (
            [s for s in secs_obj if isinstance(s, dict)]
            if isinstance(secs_obj, list)
            else ([] if not secondary else [secondary])
        )

        # 8. Stat Stage Deltas (26..34)
        stat_deltas: Dict[str, float] = {}
        stat_chance: float = 0.0
        stat_self: float = 0.0

        if "stat_deltas" in ovr and isinstance(ovr["stat_deltas"], dict):
            stat_deltas = {str(k): float(v) for k, v in ovr["stat_deltas"].items()}
            stat_chance = float(ovr.get("stat_chance", 1.0))
            stat_self = float(ovr.get("stat_self", 0.0))
        elif primary_boosts:
            stat_deltas = self._extract_stat_deltas_dict(primary_boosts)
            stat_chance = 1.0
            raw_t = str(row.get("target") or "normal")
            stat_self = 1.0 if raw_t in ("self", "allySide", "allyTeam", "allies") else 0.0
        elif isinstance(self_dict.get("boosts"), dict):
            stat_deltas = self._extract_stat_deltas_dict(self_dict["boosts"])
            stat_chance = 1.0
            stat_self = 1.0
        elif isinstance(self_boost_dict.get("boosts"), dict):
            stat_deltas = self._extract_stat_deltas_dict(self_boost_dict["boosts"])
            stat_chance = 1.0
            stat_self = 1.0
        elif move_id in ONHIT_CALLBACK_BOOSTS:
            cb_boosts, cb_self = ONHIT_CALLBACK_BOOSTS[move_id]
            stat_deltas = dict(cb_boosts)
            stat_chance = 1.0
            stat_self = cb_self
        else:
            for sec_item in secondaries_list:
                if isinstance(sec_item.get("boosts"), dict):
                    stat_deltas = self._extract_stat_deltas_dict(sec_item["boosts"])
                    stat_chance = float(sec_item.get("chance", 100)) / 100.0
                    stat_self = 0.0
                    break
                sec_self = _parse_structured_field(sec_item.get("self"))
                if isinstance(sec_self, dict) and isinstance(sec_self.get("boosts"), dict):
                    stat_deltas = self._extract_stat_deltas_dict(sec_self["boosts"])
                    stat_chance = float(sec_item.get("chance", 100)) / 100.0
                    stat_self = 1.0
                    break

        stat_keys = ("atk", "def", "spa", "spd", "spe", "acc", "eva")
        for s_i, s_k in enumerate(stat_keys):
            if s_k in stat_deltas:
                vec[MoveIdx.STAT_DELTA_START + s_i] = float(stat_deltas[s_k])
        vec[MoveIdx.STAT_DELTA_CHANCE] = stat_chance
        vec[MoveIdx.STAT_DELTA_SELF] = stat_self

        # 9. Status Infliction One-Hot (35..42)
        sec_status_name = "healthy"
        sec_status_chance = 0.0

        if "sec_status" in ovr:
            sec_status_name = str(ovr["sec_status"]).lower()
            sec_status_chance = float(ovr.get("sec_chance", 1.0))
        elif row.get("status"):
            sec_status_name = str(row["status"]).lower()
            sec_status_chance = 1.0
        else:
            for sec_item in secondaries_list:
                if sec_item.get("status"):
                    sec_status_name = str(sec_item["status"]).lower()
                    sec_status_chance = float(sec_item.get("chance", 100)) / 100.0
                    break

        st_idx = STATUS_TO_IDX.get(sec_status_name, 0)
        vec[MoveIdx.SEC_STATUS_START + st_idx] = 1.0
        vec[MoveIdx.SEC_STATUS_CHANCE] = sec_status_chance

        # 10. Recoil, Drain & Direct Heal (43)
        recoil_pct = 0.0
        if "recoil_pct" in ovr:
            recoil_pct = float(ovr["recoil_pct"])
        else:
            recoil_arr = _parse_structured_field(row.get("recoil"))
            drain_arr = _parse_structured_field(row.get("drain"))
            heal_arr = _parse_structured_field(row.get("heal"))
            if (
                isinstance(recoil_arr, (list, tuple))
                and len(recoil_arr) == 2
                and float(recoil_arr[1]) > 0
            ):
                recoil_pct = round(float(recoil_arr[0]) / float(recoil_arr[1]), 4)
            elif row.get("mindBlownRecoil") or move_id in ("mindblown", "steelbeam", "chloroblast"):
                recoil_pct = 0.50
            elif (
                isinstance(drain_arr, (list, tuple))
                and len(drain_arr) == 2
                and float(drain_arr[1]) > 0
            ):
                recoil_pct = -round(float(drain_arr[0]) / float(drain_arr[1]), 4)
            elif (
                isinstance(heal_arr, (list, tuple))
                and len(heal_arr) == 2
                and float(heal_arr[1]) > 0
            ):
                recoil_pct = -round(float(heal_arr[0]) / float(heal_arr[1]), 4)
        vec[MoveIdx.RECOIL_PCT] = recoil_pct

        # 11. Flinch Chance (44)
        flinch_chance = 0.0
        if "flinch_chance" in ovr:
            flinch_chance = float(ovr["flinch_chance"])
        else:
            for sec_item in secondaries_list:
                if str(sec_item.get("volatileStatus") or "").lower() == "flinch":
                    flinch_chance = float(sec_item.get("chance", 100)) / 100.0
                    break
        vec[MoveIdx.FLINCH_CHANCE] = flinch_chance

        # 12. Protect Type (45): 1.0 Standard Protect, 2.0 Wide Guard, 3.0 Quick Guard
        side_cond = str(row.get("sideCondition") or "").lower()
        vol_status = str(row.get("volatileStatus") or "").lower()
        stalling = _parse_structured_field(row.get("stallingMove"))
        if "protect_type" in ovr:
            vec[MoveIdx.PROTECT_TYPE] = float(ovr["protect_type"])
        elif move_id == "wideguard" or side_cond == "wideguard":
            vec[MoveIdx.PROTECT_TYPE] = 2.0
        elif move_id == "quickguard" or side_cond == "quickguard":
            vec[MoveIdx.PROTECT_TYPE] = 3.0
        elif stalling is True or vol_status in (
            "protect",
            "detect",
            "spikyshield",
            "kingsshield",
            "banefulbunker",
            "silktrap",
            "burningbulwark",
            "maxguard",
        ):
            vec[MoveIdx.PROTECT_TYPE] = 1.0

        # 13. Switch Mode (46): 1.0 Self-Pivot, 2.0 Forced Foe Switch
        self_switch = _parse_structured_field(row.get("selfSwitch"))
        force_switch = _parse_structured_field(row.get("forceSwitch"))
        if "switch_mode" in ovr:
            vec[MoveIdx.SWITCH_MODE] = float(ovr["switch_mode"])
        elif self_switch is True or (isinstance(self_switch, str) and self_switch):
            vec[MoveIdx.SWITCH_MODE] = 1.0
        elif force_switch is True or (isinstance(force_switch, str) and force_switch):
            vec[MoveIdx.SWITCH_MODE] = 2.0

        # 14. Field Op ID (47)
        if "field_op" in ovr:
            vec[MoveIdx.FIELD_OP_ID] = float(ovr["field_op"])
        else:
            vec[MoveIdx.FIELD_OP_ID] = float(
                self._resolve_field_op_id(
                    move_id=move_id,
                    weather=str(row.get("weather") or "").lower(),
                    terrain=str(row.get("terrain") or "").lower(),
                    side_cond=side_cond,
                    pseudo_weather=str(row.get("pseudoWeather") or "").lower(),
                    vol_status=vol_status,
                )
            )

        # 15. First Turn Only (48), Sound Move (49), Weather Sure-Hit (50), Grassy Priority Boost (51)
        vec[MoveIdx.FIRST_TURN_ONLY] = float(
            ovr.get(
                "first_turn_only",
                1.0 if move_id in ("fakeout", "firstimpression", "matblock") else 0.0,
            )
        )
        is_sound = 1.0 if flags.get("sound") else 0.0
        vec[MoveIdx.IS_SOUND_MOVE] = float(ovr.get("is_sound", is_sound))

        weather_op = 0.0
        if move_id in ("thunder", "hurricane", "bleakwindstorm", "wildboltstorm", "sandsearstorm"):
            weather_op = 2.0  # Rain sure-hit
        elif move_id == "blizzard":
            weather_op = 4.0  # Snow sure-hit
        elif move_id == "weatherball":
            weather_op = 1.0  # Weather Ball adaptive
        elif flags.get("charge"):
            if move_id in ("solarbeam", "solarblade"):
                weather_op = 10.0  # Skips charge in Sun
            elif move_id == "electroshot":
                weather_op = 20.0  # Skips charge in Rain
            else:
                weather_op = 30.0  # General 2-turn move (charges on Turn 1)
        vec[MoveIdx.WEATHER_SURE_HIT] = float(ovr.get("weather_sure_hit", weather_op))

        vec[MoveIdx.GRASSY_PRIO_BOOST] = float(
            ovr.get("grassy_prio_boost", 1.0 if move_id == "grassyglide" else 0.0)
        )

        # 16. Expected Multi-Hit Count (52)
        multihit_val = _parse_structured_field(row.get("multihit"))
        expected_hits = 1.0
        if isinstance(multihit_val, int):
            expected_hits = float(multihit_val)
        elif isinstance(multihit_val, (list, tuple)) and len(multihit_val) == 2:
            lo, hi = int(multihit_val[0]), int(multihit_val[1])
            if lo == 2 and hi == 5:
                expected_hits = 3.1  # Exact cartridge EV: 0.35*2 + 0.35*3 + 0.15*4 + 0.15*5
            else:
                expected_hits = 0.5 * (lo + hi)
        elif move_id == "beatup":
            expected_hits = 4.0
        elif move_id == "populationbomb":
            expected_hits = 10.0
        vec[MoveIdx.EXPECTED_HITS] = float(ovr.get("expected_hits", expected_hits))

        # 17. Offensive & Defensive Stat Overrides (53, 54) & Bypass Substitute (55)
        off_stat = str(row.get("overrideOffensiveStat") or "").lower()
        off_pkm = str(row.get("overrideOffensivePokemon") or "").lower()
        if off_stat == "def" or move_id == "bodypress":
            vec[MoveIdx.OVERRIDE_OFF_STAT] = float(OverrideOffStat.USER_DEF)
        elif off_pkm == "target" or move_id == "foulplay":
            vec[MoveIdx.OVERRIDE_OFF_STAT] = float(OverrideOffStat.TARGET_ATK)
        else:
            vec[MoveIdx.OVERRIDE_OFF_STAT] = float(OverrideOffStat.STANDARD)

        def_stat = str(row.get("overrideDefensiveStat") or "").lower()
        if def_stat == "def" or move_id in ("psyshock", "psystrike", "secretsword"):
            vec[MoveIdx.OVERRIDE_DEF_STAT] = float(OverrideDefStat.TARGET_DEF)
        else:
            vec[MoveIdx.OVERRIDE_DEF_STAT] = float(OverrideDefStat.STANDARD)

        vec[MoveIdx.BYPASS_SUB] = 1.0 if (flags.get("bypasssub") or is_sound > 0.5) else 0.0

        return vec

    @staticmethod
    def _map_showdown_target(raw_target: str) -> TargetType:
        """Map Showdown's `target` string to the canonical `TargetType` enum."""
        t = raw_target.strip()
        if t in ("normal", "any", "adjacentFoe", "randomNormal"):
            return TargetType.SINGLE_FOE
        if t == "allAdjacentFoes":
            return TargetType.ALL_ADJACENT_FOES
        if t == "allAdjacent":
            return TargetType.ALL_ADJACENT
        if t == "self":
            return TargetType.SELF
        if t in ("adjacentAlly", "adjacentAllyOrSelf"):
            return TargetType.ALLY
        if t in ("allySide", "allyTeam", "allies", "foeSide"):
            return TargetType.ALLY_SIDE
        return TargetType.GLOBAL_FIELD

    @staticmethod
    def _extract_stat_deltas_dict(boosts_dict: Dict[str, Any]) -> Dict[str, float]:
        """Normalize Showdown boost keys (`accuracy` -> `acc`, `evasion` -> `eva`)."""
        out: Dict[str, float] = {}
        key_map = {
            "atk": "atk",
            "def": "def",
            "spa": "spa",
            "spd": "spd",
            "spe": "spe",
            "accuracy": "acc",
            "acc": "acc",
            "evasion": "eva",
            "eva": "eva",
        }
        for k, v in boosts_dict.items():
            mapped = key_map.get(str(k).lower())
            if mapped and v is not None:
                try:
                    out[mapped] = float(v)
                except (TypeError, ValueError):
                    pass
        return out

    @staticmethod
    def _resolve_field_op_id(
        move_id: str,
        weather: str,
        terrain: str,
        side_cond: str,
        pseudo_weather: str,
        vol_status: str,
    ) -> FieldOpID:
        """Resolve `FieldOpID` programmatically from Showdown move attributes."""
        if move_id == "fakeout":
            return FieldOpID.FAKE_OUT
        if move_id in ("suckerpunch", "thunderclap", "upperhand"):
            return FieldOpID.SUCKER_PUNCH
        if vol_status in ("followme", "ragepowder") or move_id in ("followme", "ragepowder"):
            return FieldOpID.FOLLOW_ME
        if vol_status == "helpinghand" or move_id == "helpinghand":
            return FieldOpID.HELPING_HAND
        if side_cond == "reflect" or move_id == "reflect":
            return FieldOpID.REFLECT
        if side_cond == "lightscreen" or move_id == "lightscreen":
            return FieldOpID.LIGHT_SCREEN
        if side_cond == "auroraveil" or move_id == "auroraveil":
            return FieldOpID.AURORA_VEIL
        if side_cond == "tailwind" or move_id == "tailwind":
            return FieldOpID.TAILWIND
        if pseudo_weather == "trickroom" or move_id == "trickroom":
            return FieldOpID.TRICK_ROOM
        if pseudo_weather == "gravity" or move_id == "gravity":
            return FieldOpID.GRAVITY
        if move_id in ("haze", "clearsmog"):
            return FieldOpID.HAZE
        if weather in ("sunnyday", "sun", "desolateland"):
            return FieldOpID.SET_SUN
        if weather in ("raindance", "rain", "primordialsea"):
            return FieldOpID.SET_RAIN
        if weather in ("sandstorm", "sand"):
            return FieldOpID.SET_SAND
        if weather in ("snow", "hail", "chillyreception") or move_id == "chillyreception":
            return FieldOpID.SET_SNOW
        if terrain in ("electricterrain", "electric"):
            return FieldOpID.SET_ELECTRIC_TERRAIN
        if terrain in ("grassyterrain", "grassy"):
            return FieldOpID.SET_GRASSY_TERRAIN
        if terrain in ("psychicterrain", "psychic"):
            return FieldOpID.SET_PSYCHIC_TERRAIN
        if terrain in ("mistyterrain", "misty"):
            return FieldOpID.SET_MISTY_TERRAIN
        return FieldOpID.NONE

    # -------------------------------------------------------------------------
    # Compilation from `TurnState` (`trainer_1` and `trainer_2`)
    # -------------------------------------------------------------------------

    def compile_turn_state(self, turn_state: TurnState) -> CompiledBattleState:
        """Compile a `TurnState` (`trainer_1` vs `trainer_2`) directly into `[24]`, `[8, 84]`, and `[8, 4, 56]` tensors."""
        f_np = np.zeros((FIELD_DIM,), dtype=np.float32)

        # Weather & Terrain One-Hot
        w_key = str(turn_state.field.weather or "clear").lower()
        w_idx = WEATHER_TO_IDX.get(w_key, 0)
        f_np[FieldIdx.WEATHER_START + w_idx] = 1.0
        f_np[FieldIdx.WEATHER_TURNS] = 5.0 if w_idx > 0 else 0.0

        t_key = str(turn_state.field.terrain or "none").lower()
        t_idx = TERRAIN_TO_IDX.get(t_key, 0)
        f_np[FieldIdx.TERRAIN_START + t_idx] = 1.0
        f_np[FieldIdx.TERRAIN_TURNS] = 5.0 if t_idx > 0 else 0.0

        f_np[FieldIdx.TRICK_ROOM_TURNS] = 4.0 if turn_state.field.trick_room_active else 0.0
        f_np[FieldIdx.GRAVITY_TURNS] = 0.0

        # trainer_1 side conditions
        t1 = turn_state.trainer_1
        f_np[FieldIdx.TRAINER_1_TAILWIND_TURNS] = (
            float(t1.tailwind_turns or 4.0) if t1.tailwind_active else 0.0
        )
        f_np[FieldIdx.TRAINER_1_REFLECT_TURNS] = 5.0 if t1.reflect_active else 0.0
        f_np[FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS] = 5.0 if t1.light_screen_active else 0.0
        f_np[FieldIdx.TRAINER_1_AURORA_VEIL_TURNS] = 5.0 if t1.aurora_veil_active else 0.0
        f_np[FieldIdx.TRAINER_1_MEGA_USED] = 1.0 if t1.mega_used else 0.0

        # trainer_2 side conditions
        t2 = turn_state.trainer_2
        f_np[FieldIdx.TRAINER_2_TAILWIND_TURNS] = (
            float(t2.tailwind_turns or 4.0) if t2.tailwind_active else 0.0
        )
        f_np[FieldIdx.TRAINER_2_REFLECT_TURNS] = 5.0 if t2.reflect_active else 0.0
        f_np[FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS] = 5.0 if t2.light_screen_active else 0.0
        f_np[FieldIdx.TRAINER_2_AURORA_VEIL_TURNS] = 5.0 if t2.aurora_veil_active else 0.0
        f_np[FieldIdx.TRAINER_2_MEGA_USED] = 1.0 if t2.mega_used else 0.0

        # Assemble 8 slots: [trainer_1 A, trainer_1 B, trainer_1 Bench1, trainer_1 Bench2,
        #                    trainer_2 A, trainer_2 B, trainer_2 Bench1, trainer_2 Bench2]
        ordered_mons: List[Optional[CompiledPokemonState]] = [
            t1.active_slots[0],
            t1.active_slots[1],
            t1.bench_slots[0] if len(t1.bench_slots) > 0 else None,
            t1.bench_slots[1] if len(t1.bench_slots) > 1 else None,
            t2.active_slots[0],
            t2.active_slots[1],
            t2.bench_slots[0] if len(t2.bench_slots) > 0 else None,
            t2.bench_slots[1] if len(t2.bench_slots) > 1 else None,
        ]

        p_np = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        m_np = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)
        slot_species_list: List[str] = []
        slot_moves_list: List[Tuple[str, ...]] = []

        for s_idx, mon in enumerate(ordered_mons):
            p_np[s_idx], m_np[s_idx], sp_name, mv_names = self.compile_pokemon_from_state(mon)
            slot_species_list.append(sp_name)
            slot_moves_list.append(mv_names)

        if self.backend == "torch" and torch is not None:
            return CompiledBattleState(
                field_tensor=torch.from_numpy(f_np).to(self.device),
                roster_tensor=torch.from_numpy(p_np).to(self.device),
                moves_tensor=torch.from_numpy(m_np).to(self.device),
                backend="torch",
                device=self.device,
                slot_species=tuple(slot_species_list),
                slot_move_names=tuple(slot_moves_list),
            )

        return CompiledBattleState(
            field_tensor=f_np,
            roster_tensor=p_np,
            moves_tensor=m_np,
            backend="numpy",
            device="cpu",
            slot_species=tuple(slot_species_list),
            slot_move_names=tuple(slot_moves_list),
        )

    def compile_pokemon_from_state(
        self,
        mon: Optional[CompiledPokemonState],
    ) -> Tuple[np.ndarray, np.ndarray, str, Tuple[str, ...]]:
        """Compile a `CompiledPokemonState` into its 84-float `MonIdx` vector and `[4, 56]` `MoveIdx` matrix."""
        p_vec = np.zeros((MON_DIM,), dtype=np.float32)
        m_mat = np.zeros((MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

        if mon is None or mon.fainted or mon.current_hp <= 0:
            p_vec[MonIdx.STATUS_HEALTHY] = 1.0
            p_vec[MonIdx.TYPE1_START] = 1.0
            p_vec[MonIdx.HELPING_HAND_MULT] = 1.0
            p_vec[MonIdx.CHOICE_LOCKED_MOVE] = -1.0
            p_vec[MonIdx.LAST_MOVE_IDX] = -1.0
            return p_vec, m_mat, (mon.species if mon else "None"), ("Protect",) * 4

        p_vec[MonIdx.HP_CUR] = float(mon.current_hp)
        p_vec[MonIdx.HP_MAX] = float(max(1, mon.max_hp))
        p_vec[MonIdx.ALIVE_FLAG] = 1.0

        p_vec[MonIdx.STAT_ATK] = float(mon.level_50_stats.get("atk", 100))
        p_vec[MonIdx.STAT_DEF] = float(mon.level_50_stats.get("def", 100))
        p_vec[MonIdx.STAT_SPA] = float(mon.level_50_stats.get("spa", 100))
        p_vec[MonIdx.STAT_SPD] = float(mon.level_50_stats.get("spd", 100))
        p_vec[MonIdx.STAT_SPE] = float(mon.level_50_stats.get("spe", 100))

        boost_map = {
            "atk": mon.boosts.get("atk", 0),
            "def": mon.boosts.get("def", 0),
            "spa": mon.boosts.get("spa", 0),
            "spd": mon.boosts.get("spd", 0),
            "spe": mon.boosts.get("spe", 0),
            "acc": mon.boosts.get("accuracy", mon.boosts.get("acc", 0)),
            "eva": mon.boosts.get("evasion", mon.boosts.get("eva", 0)),
        }
        for b_i, b_k in enumerate(("atk", "def", "spa", "spd", "spe", "acc", "eva")):
            p_vec[MonIdx.BOOST_START + b_i] = float(boost_map[b_k])

        st_idx = STATUS_TO_IDX.get(str(mon.status or "healthy").lower(), 0)
        p_vec[MonIdx.STATUS_START + st_idx] = 1.0

        types = mon.types or ("Normal",)
        t1_idx = TYPE_TO_IDX.get(str(types[0]).lower(), 0)
        p_vec[MonIdx.TYPE1_START + t1_idx] = 1.0
        if len(types) >= 2 and str(types[1]).lower() != str(types[0]).lower():
            t2_idx = TYPE_TO_IDX.get(str(types[1]).lower(), 0)
            p_vec[MonIdx.TYPE2_START + t2_idx] = 1.0

        # Volatiles: note that in MonIdx, ACTIVE_TURNS == 0.0 represents Turn 1 on the field
        # (Whereas in CompiledPokemonState, active_turns == 1 represents Turn 1 on the field)
        p_vec[MonIdx.PROTECT_ACTIVE] = 0.0
        p_vec[MonIdx.PROTECT_COUNTER] = 1.0 if mon.used_protect_last_turn else 0.0
        p_vec[MonIdx.FLINCHED] = 0.0
        p_vec[MonIdx.ACTIVE_TURNS] = float(max(0, mon.active_turns - 1))
        p_vec[MonIdx.TAUNT_TURNS] = float(mon.taunt_turns)
        p_vec[MonIdx.ENCORE_TURNS] = 1.0 if mon.encore_move else 0.0
        p_vec[MonIdx.SUBSTITUTE_HP] = 0.0
        p_vec[MonIdx.HELPING_HAND_MULT] = 1.0

        # Item & Ability IDs
        item_raw = str(mon.item or "").strip()
        item_lower = item_raw.lower()
        if mon.mega_stone or item_raw in self.repo.mega_stone_to_species:
            item_id = ItemID.MEGA_STONE
        else:
            item_id = ITEM_NAME_TO_ID.get(
                item_lower,
                ITEM_NAME_TO_ID.get(_to_id(item_lower), ItemID.NONE),
            )

        ability_lower = str(mon.ability or "none").strip().lower()
        ability_id = ABILITY_NAME_TO_ID.get(ability_lower, AbilityID.NONE)

        is_flying = any(str(t).lower() == "flying" for t in types)
        is_levitate = ability_id == AbilityID.LEVITATE
        p_vec[MonIdx.GROUNDED_FLAG] = 0.0 if (is_flying or is_levitate) else 1.0
        p_vec[MonIdx.ITEM_ACTIVE] = 1.0 if item_id != ItemID.NONE else 0.0
        p_vec[MonIdx.ITEM_ID] = float(item_id)
        p_vec[MonIdx.ABILITY_ID] = float(ability_id)
        p_vec[MonIdx.UNBURDEN_ACTIVE] = 0.0
        p_vec[MonIdx.TOXIC_COUNTER] = 1.0

        # Compile up to 4 moves programmatically on the fly
        move_names: List[str] = []
        for m_i in range(MOVES_PER_MON):
            if m_i < len(mon.moves):
                mv_name = mon.moves[m_i].name
            else:
                mv_name = "Protect"
            move_names.append(mv_name)
            m_mat[m_i] = self.compile_move_vector(mv_name)

        # Resolve locked_move and last_move_used indices (0..3 or -1.0)
        locked_idx = -1.0
        if mon.locked_move:
            for idx, m_name in enumerate(move_names):
                if m_name.lower() == mon.locked_move.lower():
                    locked_idx = float(idx)
                    break
        last_idx = -1.0
        target_last = mon.encore_move or mon.last_move_used
        if target_last:
            for idx, m_name in enumerate(move_names):
                if m_name.lower() == target_last.lower():
                    last_idx = float(idx)
                    break

        p_vec[MonIdx.CHOICE_LOCKED_MOVE] = locked_idx
        p_vec[MonIdx.LAST_MOVE_IDX] = last_idx

        # Mega Evolution payload
        p_vec[MonIdx.CAN_MEGA] = 1.0 if mon.can_mega_evolve else 0.0
        p_vec[MonIdx.IS_MEGA] = 1.0 if mon.is_mega else 0.0

        mega_stats = mon.mega_level_50_stats or mon.level_50_stats
        p_vec[MonIdx.MEGA_ATK] = float(mega_stats.get("atk", p_vec[MonIdx.STAT_ATK]))
        p_vec[MonIdx.MEGA_DEF] = float(mega_stats.get("def", p_vec[MonIdx.STAT_DEF]))
        p_vec[MonIdx.MEGA_SPA] = float(mega_stats.get("spa", p_vec[MonIdx.STAT_SPA]))
        p_vec[MonIdx.MEGA_SPD] = float(mega_stats.get("spd", p_vec[MonIdx.STAT_SPD]))
        p_vec[MonIdx.MEGA_SPE] = float(mega_stats.get("spe", p_vec[MonIdx.STAT_SPE]))

        mega_ab_lower = str(mon.mega_ability or mon.ability or "none").strip().lower()
        p_vec[MonIdx.MEGA_ABILITY_ID] = float(ABILITY_NAME_TO_ID.get(mega_ab_lower, ability_id))

        return p_vec, m_mat, mon.species, tuple(move_names)

    def compile_pokemon_slot(self, mon_spec: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
        """Compile a single Pokémon specification dictionary into its 84-float Roster Vector (`MonIdx`)
        and its [4, 56] Move Matrix (`MoveIdx`).
        """
        p_vec = np.zeros((MON_DIM,), dtype=np.float32)
        m_mat = np.zeros((MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

        if not mon_spec:
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
        """Compile a full 8-slot VGC battle state into aligned Field [24], Roster [8, 84],
        and Moves [8, 4, 56] tensors on the active device.
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

        f_np[FieldIdx.TRAINER_1_TAILWIND_TURNS] = float(f_spec.get("trainer_1_tailwind_turns", f_spec.get("p1_tailwind_turns", 0.0)))
        f_np[FieldIdx.TRAINER_1_REFLECT_TURNS] = float(f_spec.get("trainer_1_reflect_turns", f_spec.get("p1_reflect_turns", 0.0)))
        f_np[FieldIdx.TRAINER_1_LIGHT_SCREEN_TURNS] = float(f_spec.get("trainer_1_light_screen_turns", f_spec.get("p1_light_screen_turns", 0.0)))
        f_np[FieldIdx.TRAINER_1_AURORA_VEIL_TURNS] = float(f_spec.get("trainer_1_aurora_veil_turns", f_spec.get("p1_aurora_veil_turns", 0.0)))
        f_np[FieldIdx.TRAINER_1_MEGA_USED] = float(f_spec.get("trainer_1_mega_used", f_spec.get("p1_mega_used", 0.0)))

        f_np[FieldIdx.TRAINER_2_TAILWIND_TURNS] = float(f_spec.get("trainer_2_tailwind_turns", f_spec.get("p2_tailwind_turns", 0.0)))
        f_np[FieldIdx.TRAINER_2_REFLECT_TURNS] = float(f_spec.get("trainer_2_reflect_turns", f_spec.get("p2_reflect_turns", 0.0)))
        f_np[FieldIdx.TRAINER_2_LIGHT_SCREEN_TURNS] = float(f_spec.get("trainer_2_light_screen_turns", f_spec.get("p2_light_screen_turns", 0.0)))
        f_np[FieldIdx.TRAINER_2_AURORA_VEIL_TURNS] = float(f_spec.get("trainer_2_aurora_veil_turns", f_spec.get("p2_aurora_veil_turns", 0.0)))
        f_np[FieldIdx.TRAINER_2_MEGA_USED] = float(f_spec.get("trainer_2_mega_used", f_spec.get("p2_mega_used", 0.0)))

        p_np = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        m_np = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

        species_list = []
        moves_list_all = []
        for s_idx in range(ROSTER_SLOTS):
            spec = roster_specs[s_idx] if s_idx < len(roster_specs) else {}
            p_np[s_idx], m_np[s_idx] = self.compile_pokemon_slot(spec)
            species_list.append(str(spec.get("species", spec.get("name", ""))))
            moves_list_all.append(tuple(str(m) for m in spec.get("moves", [])))

        if self.backend == "torch" and torch is not None:
            return CompiledBattleState(
                field_tensor=torch.from_numpy(f_np).to(self.device),
                roster_tensor=torch.from_numpy(p_np).to(self.device),
                moves_tensor=torch.from_numpy(m_np).to(self.device),
                backend="torch",
                device=self.device,
                slot_species=tuple(species_list),
                slot_move_names=tuple(moves_list_all),
            )

        return CompiledBattleState(
            field_tensor=f_np,
            roster_tensor=p_np,
            moves_tensor=m_np,
            backend="numpy",
            device="cpu",
            slot_species=tuple(species_list),
            slot_move_names=tuple(moves_list_all),
        )

    # =========================================================================
    # 5. VECTORIZED 26x26 MATRIX ACTION PRUNER (`trainer_1` & `trainer_2`)
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
        """Compute the 26-element Hard Validity Mask `{0.0, 1.0}` and Soft Tactical Prior Vector."""
        valid_26 = np.zeros((SLOT_CHOICES,), dtype=np.float32)
        prior_26 = np.ones((SLOT_CHOICES,), dtype=np.float32)

        user_vec = p_np[user_slot]
        if user_vec[MonIdx.ALIVE_FLAG] <= 0.0:
            return valid_26, prior_26

        moves_4 = m_np[user_slot]  # Shape [4, 56]
        partner_vec = p_np[partner_slot]
        opp_a_vec = p_np[opp_a_slot]
        opp_b_vec = p_np[opp_b_slot]

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

        active_turns = user_vec[MonIdx.ACTIVE_TURNS]
        protect_count = user_vec[MonIdx.PROTECT_COUNTER]
        taunt_active = 1.0 if user_vec[MonIdx.TAUNT_TURNS] > 0.0 else 0.0
        encore_active = 1.0 if user_vec[MonIdx.ENCORE_TURNS] > 0.0 else 0.0
        last_move_idx = int(round(user_vec[MonIdx.LAST_MOVE_IDX]))
        choice_lock_idx = int(round(user_vec[MonIdx.CHOICE_LOCKED_MOVE]))
        has_assault_vest = (
            1.0
            if (
                user_vec[MonIdx.ITEM_ACTIVE] > 0.0
                and int(round(user_vec[MonIdx.ITEM_ID])) == ItemID.ASSAULT_VEST
            )
            else 0.0
        )
        user_ab = int(round(user_vec[MonIdx.ABILITY_ID]))
        can_mega_gate = (
            1.0
            if (
                user_vec[MonIdx.CAN_MEGA] > 0.0
                and user_vec[MonIdx.IS_MEGA] <= 0.0
                and side_mega_used <= 0.0
            )
            else 0.0
        )

        opp_a_ab = int(round(opp_a_vec[MonIdx.ABILITY_ID])) if opp_a_vec[MonIdx.ALIVE_FLAG] > 0.0 else 0
        opp_b_ab = int(round(opp_b_vec[MonIdx.ABILITY_ID])) if opp_b_vec[MonIdx.ALIVE_FLAG] > 0.0 else 0
        opp_blocks_prio = (
            1.0
            if (
                opp_a_ab in (AbilityID.ARMOR_TAIL, AbilityID.QUEENLY_MAJESTY)
                or opp_b_ab in (AbilityID.ARMOR_TAIL, AbilityID.QUEENLY_MAJESTY)
            )
            else 0.0
        )

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

                    # 1. Target Bucket Routing Gate
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

                    # 3. Turn-1 Gate (Fake Out / First Impression / Mat Block)
                    if m_vec[MoveIdx.FIRST_TURN_ONLY] > 0.5 and active_turns > 0.0:
                        continue

                    # 4. Effective Priority Resolution
                    eff_prio = float(m_vec[MoveIdx.PRIORITY])
                    if eff_user_ab == AbilityID.PRANKSTER and is_status:
                        eff_prio += 1.0
                    elif (
                        m_vec[MoveIdx.GRASSY_PRIO_BOOST] > 0.5
                        and is_grassy_terrain > 0.5
                        and user_vec[MonIdx.GROUNDED_FLAG] > 0.5
                    ):
                        eff_prio += 1.0

                    # 5. Priority Blocking & Psychic Terrain Invariants on Opposing Targets
                    is_single_targeted_at_foe = target_type == TargetType.SINGLE_FOE and tgt_bucket in (0, 1)
                    if is_single_targeted_at_foe and eff_prio > 0.0:
                        if opp_blocks_prio > 0.5:
                            continue
                        if is_psychic_terrain > 0.5 and tgt_grounded > 0.5:
                            continue

                    # 6. Prankster vs Dark-Type Target Invariant
                    if (
                        is_single_targeted_at_foe
                        and eff_user_ab == AbilityID.PRANKSTER
                        and is_status
                        and tgt_is_dark > 0.5
                    ):
                        continue

                    # 7. Soundproof, Good as Gold, Flash Fire & Terrain Sleep Invariants
                    if is_single_targeted_at_foe or target_type in (
                        TargetType.ALL_ADJACENT_FOES,
                        TargetType.ALL_ADJACENT,
                    ):
                        if (
                            m_vec[MoveIdx.IS_SOUND_MOVE] > 0.5
                            and tgt_ab == AbilityID.SOUNDPROOF
                            and target_type == TargetType.SINGLE_FOE
                        ):
                            continue
                        if (
                            is_status
                            and tgt_ab == AbilityID.GOOD_AS_GOLD
                            and target_type == TargetType.SINGLE_FOE
                        ):
                            continue
                        m_type_onehot = m_vec[MoveIdx.TYPE_START:MoveIdx.TYPE_END]
                        if (
                            m_type_onehot[TYPE_TO_IDX["fire"]] > 0.5
                            and tgt_ab == AbilityID.FLASH_FIRE
                            and target_type == TargetType.SINGLE_FOE
                        ):
                            continue
                        is_sleep_move = (
                            m_vec[MoveIdx.SEC_STATUS_START + STATUS_TO_IDX["sleep"]] > 0.5
                            and m_vec[MoveIdx.SEC_STATUS_CHANCE] >= 1.0
                            and is_status
                        )
                        if is_sleep_move and tgt_grounded > 0.5 and is_elec_or_misty_terrain > 0.5:
                            continue

                    valid_26[choice_idx] = 1.0

                    # --- Soft Tactical Prior Calculation ---
                    prior_scale = 1.0

                    if m_vec[MoveIdx.PROTECT_TYPE] == 1.0 and protect_count >= 1.0:
                        prior_scale = 0.40 if protect_count == 1.0 else 0.10

                    acc_val = float(m_vec[MoveIdx.ACCURACY])
                    if eff_user_ab == AbilityID.NO_GUARD or tgt_ab == AbilityID.NO_GUARD:
                        acc_val = 1.0
                    elif m_vec[MoveIdx.WEATHER_SURE_HIT] == 2.0 and is_rain > 0.5:
                        acc_val = 1.0
                    elif m_vec[MoveIdx.WEATHER_SURE_HIT] == 4.0 and is_snow > 0.5:
                        acc_val = 1.0
                    acc_val = min(1.0, max(0.0, acc_val))

                    if not is_status:
                        m_type_vec = m_vec[MoveIdx.TYPE_START:MoveIdx.TYPE_END]
                        eff1 = float(m_type_vec @ m_chart_np @ tgt_type1)
                        raw_eff2 = float(m_type_vec @ m_chart_np @ tgt_type2)
                        eff2 = raw_eff2 + (1.0 - float(np.sum(tgt_type2)))
                        eff_total = eff1 * eff2

                        if m_type_vec[TYPE_TO_IDX["ground"]] > 0.5 and tgt_grounded <= 0.0:
                            eff_total = 0.0

                        if tgt_bucket == 2:
                            # Partner self-targeting (Beat Up + Justified, Stomping Tantrum fail-double, etc.)
                            prior_scale = 0.20
                        else:
                            if eff_total == 0.0:
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

                    if mega_mode == 1:
                        prior_scale *= 1.10

                    prior_26[choice_idx] = round(float(prior_scale), 4)

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
        trainer_id: str = "trainer_1",
        side: Optional[str] = None,
        **kwargs: Any,
    ) -> SideActionMaskResult:
        """Compute the full `26x26` Hard Validity Mask, Tactical Prior Matrix, and `[N_valid, 2]` coordinates.

        Args:
            state: `CompiledBattleState` from `compile_turn_state` or `compile_battle_state`.
            trainer_id: `'trainer_1'` or `'trainer_2'`.
        """
        if side is not None:
            trainer_id = "trainer_1" if str(side).lower() in ("trainer_1", "p1") else "trainer_2"
        elif "side" in kwargs:
            trainer_id = "trainer_1" if str(kwargs["side"]).lower() in ("trainer_1", "p1") else "trainer_2"

        if trainer_id not in ("trainer_1", "trainer_2"):
            raise ValueError(
                f"trainer_id must be 'trainer_1' or 'trainer_2', got '{trainer_id}'"
            )

        if state.backend == "torch" and torch is not None:
            f_np = state.field_tensor.detach().cpu().numpy()
            p_np = state.roster_tensor.detach().cpu().numpy()
            m_np = state.moves_tensor.detach().cpu().numpy()
        else:
            f_np = state.field_tensor
            p_np = state.roster_tensor
            m_np = state.moves_tensor

        if trainer_id == "trainer_1":
            slot_a, slot_b = SLOT_TRAINER_1_A, SLOT_TRAINER_1_B
            bench1, bench2 = SLOT_TRAINER_1_BENCH1, SLOT_TRAINER_1_BENCH2
            opp_a, opp_b = SLOT_TRAINER_2_A, SLOT_TRAINER_2_B
            mega_used = float(f_np[FieldIdx.TRAINER_1_MEGA_USED])
        else:
            slot_a, slot_b = SLOT_TRAINER_2_A, SLOT_TRAINER_2_B
            bench1, bench2 = SLOT_TRAINER_2_BENCH1, SLOT_TRAINER_2_BENCH2
            opp_a, opp_b = SLOT_TRAINER_1_A, SLOT_TRAINER_1_B
            mega_used = float(f_np[FieldIdx.TRAINER_2_MEGA_USED])

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

        # 4. Joint Tactical Prior Matrix
        joint_prior = (np.outer(prior_a, prior_b) * joint_valid).astype(np.float32)

        # 5. Extract compressed [N_valid, 2] coordinates of surviving legal joint actions
        coords_np = np.argwhere(joint_valid > 0.5).astype(np.int64)

        if state.backend == "torch" and torch is not None:
            return SideActionMaskResult(
                trainer_id=trainer_id,
                slot_a_valid_mask=torch.from_numpy(valid_a).to(self.device),
                slot_b_valid_mask=torch.from_numpy(valid_b).to(self.device),
                slot_a_prior_vec=torch.from_numpy(prior_a).to(self.device),
                slot_b_prior_vec=torch.from_numpy(prior_b).to(self.device),
                joint_valid_mask=torch.from_numpy(joint_valid).to(self.device),
                joint_prior_mat=torch.from_numpy(joint_prior).to(self.device),
                valid_coords=torch.from_numpy(coords_np).to(self.device),
            )

        return SideActionMaskResult(
            trainer_id=trainer_id,
            slot_a_valid_mask=valid_a,
            slot_b_valid_mask=valid_b,
            slot_a_prior_vec=prior_a,
            slot_b_prior_vec=prior_b,
            joint_valid_mask=joint_valid,
            joint_prior_mat=joint_prior,
            valid_coords=coords_np,
        )
