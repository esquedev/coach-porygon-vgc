# -*- coding: utf-8 -*-
"""Regulation M-C Turn State & Legal Action Data Models.

Defines the math-ready `TurnState` representation (`trainer_1` and `trainer_2`
active and bench rosters, pre-compiled Mega Evolution stat transitions, and
field modifiers) and the legal action hierarchy (`SingleSlotAction`,
`JointTrainerAction`) for the One-Turn VGC Simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from engine.parser.models import StatSpread


class ActionType(str, Enum):
    """Canonical single-slot action types in VGC Doubles."""

    MOVE = "MOVE"
    SWITCH = "SWITCH"
    PASS = "PASS"


@dataclass(frozen=True)
class TargetRef:
    """Represents the target of a single-slot action in VGC Doubles.

    Attributes:
        domain: Target domain identifier:
            - 'trainer_1': Single slot on trainer_1's side (slot 0 or 1).
            - 'trainer_2': Single slot on trainer_2's side (slot 0 or 1).
            - 'self': The acting Pokémon itself.
            - 'all_adjacent_foes': Spread move hitting both opposing active slots.
            - 'all_adjacent': Spread move hitting partner and both opposing active slots.
            - 'ally_side': Team-wide buff/screen on the actor's side (e.g. Tailwind, Reflect).
            - 'foe_side': Hazard/effect on the opposing side.
            - 'field': Global battlefield effect (e.g. Trick Room, Sunny Day, Haze).
        slot: Active slot index (0 or 1) when `domain` is 'trainer_1' or 'trainer_2',
              otherwise None.
    """

    domain: str
    slot: Optional[int] = None

    def describe(self) -> str:
        """Return a concise human-readable target label."""
        if self.slot is not None:
            return f"{self.domain}[slot={self.slot}]"
        return self.domain


@dataclass(frozen=True)
class CompiledMove:
    """Showdown move metadata resolved from in-memory DuckDB (`moves` view).

    Attributes:
        id: Lowercase alphanumeric Showdown move ID (e.g. 'heatwave').
        name: Canonical display name (e.g. 'Heat Wave').
        type: Elemental type (e.g. 'Fire', 'Grass').
        category: Move category ('Physical', 'Special', 'Status').
        base_power: Base power integer (0 for Status moves).
        accuracy: Move accuracy percentage (100, 90, etc.) or True/101 for never-miss.
        priority: Base priority bracket (-7 to +5).
        target: Showdown targeting rule ('normal', 'allAdjacentFoes', 'allAdjacent',
                'adjacentAlly', 'adjacentAllyOrSelf', 'self', 'allySide', 'all', etc.).
        flags: Dictionary of Showdown mechanical flags (protect, contact, sound, punch, etc.).
        secondary: Secondary effect dictionary (chance, boosts, status, volatileStatus) or None.
        boosts: Direct stat stage changes for Status/self-boosting moves or None.
        drain: Tuple of (numerator, denominator) for HP drain moves or None.
        recoil: Tuple of (numerator, denominator) for recoil moves or None.
    """

    id: str
    name: str
    type: str
    category: str
    base_power: int
    accuracy: int
    priority: int
    target: str
    flags: Dict[str, Any] = field(default_factory=dict)
    secondary: Optional[Dict[str, Any]] = None
    boosts: Optional[Dict[str, int]] = None
    drain: Optional[Tuple[int, int]] = None
    recoil: Optional[Tuple[int, int]] = None


@dataclass
class CompiledPokemonState:
    """Math-ready state of a single Pokémon at the start of a simulated turn.

    Pre-computes both current Level 50 stats and (when holding a valid Mega Stone)
    the target Mega Evolution's Level 50 stats, ability, and typing so the
    One-Turn Simulator can evaluate `mega_evolve=False` vs `mega_evolve=True`
    branches with zero runtime database overhead.
    """

    species: str
    base_species: str
    nickname: Optional[str]
    types: Tuple[str, ...]
    item: Optional[str]
    ability: str
    nature: str
    spread: StatSpread
    level_50_stats: Dict[str, int]
    max_hp: int
    current_hp: int
    current_hp_pct: float = 100.0
    fainted: bool = False
    revealed_in_battle: bool = False

    # Mega Evolution state & pre-compiled transition profile
    is_mega: bool = False
    mega_stone: Optional[str] = None
    can_mega_evolve: bool = False
    mega_target_species: Optional[str] = None
    mega_level_50_stats: Optional[Dict[str, int]] = None
    mega_ability: Optional[str] = None
    mega_types: Optional[Tuple[str, ...]] = None

    # Moves and in-battle volatile state
    moves: Tuple[CompiledMove, ...] = ()
    boosts: Dict[str, int] = field(
        default_factory=lambda: {
            "atk": 0,
            "def": 0,
            "spa": 0,
            "spd": 0,
            "spe": 0,
            "accuracy": 0,
            "evasion": 0,
        }
    )
    status: Optional[str] = None
    active_turns: int = 1
    used_protect_last_turn: bool = False
    last_move_used: Optional[str] = None
    locked_move: Optional[str] = None
    taunt_turns: int = 0
    encore_move: Optional[str] = None


@dataclass
class TrainerSideState:
    """Compiled battle state for one trainer (`trainer_1` or `trainer_2`).

    Tracks the 2 active field slots, the up-to-2 reserve bench slots (forming
    the 4-Pokémon VGC battle roster), the full 6-Pokémon Team Preview dictionary,
    whether the trainer has expended their Mega Evolution for the battle, and
    side-specific field screens/speed modifiers.
    """

    trainer_id: str
    trainer_name: str
    active_slots: Tuple[Optional[CompiledPokemonState], Optional[CompiledPokemonState]] = (None, None)
    bench_slots: Tuple[CompiledPokemonState, ...] = ()
    full_team: Dict[str, CompiledPokemonState] = field(default_factory=dict)
    mega_used: bool = False
    tailwind_active: bool = False
    tailwind_turns: int = 0
    reflect_active: bool = False
    light_screen_active: bool = False
    aurora_veil_active: bool = False

    def get_active_or_bench(self, identifier: str) -> Optional[CompiledPokemonState]:
        """Lookup a compiled Pokémon across active slots, bench slots, or full team."""
        clean = identifier.strip().lower()
        for mon in list(self.active_slots) + list(self.bench_slots) + list(self.full_team.values()):
            if mon is None:
                continue
            if (
                mon.species.lower() == clean
                or mon.base_species.lower() == clean
                or (mon.nickname and mon.nickname.lower() == clean)
            ):
                return mon
        return None


@dataclass
class FieldState:
    """Global battlefield modifiers active at the start of the turn."""

    weather: Optional[str] = None
    terrain: Optional[str] = None
    trick_room_active: bool = False


@dataclass
class TurnState:
    """Complete two-trainer (`trainer_1` vs `trainer_2`) state snapshot for a turn."""

    turn_number: int
    trainer_1: TrainerSideState
    trainer_2: TrainerSideState
    field: FieldState = field(default_factory=FieldState)

    def get_side(self, trainer_id: str) -> TrainerSideState:
        """Retrieve `trainer_1` or `trainer_2` side state by canonical identifier."""
        if trainer_id == "trainer_1":
            return self.trainer_1
        if trainer_id == "trainer_2":
            return self.trainer_2
        raise ValueError(f"Invalid trainer_id '{trainer_id}'. Expected 'trainer_1' or 'trainer_2'.")

    def get_opposing_side(self, trainer_id: str) -> TrainerSideState:
        """Retrieve the opposing trainer's side state."""
        if trainer_id == "trainer_1":
            return self.trainer_2
        if trainer_id == "trainer_2":
            return self.trainer_1
        raise ValueError(f"Invalid trainer_id '{trainer_id}'. Expected 'trainer_1' or 'trainer_2'.")


@dataclass(frozen=True)
class SingleSlotAction:
    """Represents a single active slot's chosen action for the turn.

    Attributes:
        trainer_id: 'trainer_1' or 'trainer_2'.
        actor_slot: Active slot index (0 or 1).
        actor_species: Species name of the Pokémon occupying `actor_slot`.
        action_type: ActionType.MOVE, ActionType.SWITCH, or ActionType.PASS.
        move_name: Canonical move name when `action_type == ActionType.MOVE`.
        target: TargetRef specifying target side/slot when `action_type == ActionType.MOVE`.
        mega_evolve: True if the Pokémon triggers Mega Evolution before executing its move.
        switch_in_species: Bench species switching into `actor_slot` when `action_type == ActionType.SWITCH`.
    """

    trainer_id: str
    actor_slot: int
    actor_species: str
    action_type: ActionType
    move_name: Optional[str] = None
    target: Optional[TargetRef] = None
    mega_evolve: bool = False
    switch_in_species: Optional[str] = None

    def describe(self) -> str:
        """Return a concise human-readable description of this single-slot action."""
        if self.action_type == ActionType.PASS:
            return f"{self.trainer_id}[{self.actor_slot}:{self.actor_species}] PASS"
        if self.action_type == ActionType.SWITCH:
            return f"{self.trainer_id}[{self.actor_slot}:{self.actor_species}] SWITCH -> {self.switch_in_species}"
        mega_tag = " [MEGA]" if self.mega_evolve else ""
        target_str = f" -> {self.target.describe()}" if self.target else ""
        return f"{self.trainer_id}[{self.actor_slot}:{self.actor_species}]{mega_tag} MOVE {self.move_name}{target_str}"


@dataclass(frozen=True)
class JointTrainerAction:
    """Represents a legal joint 2-slot decision for a single trainer in VGC Doubles.

    Enforces joint VGC constraints:
    - At most one slot can Mega Evolve (`not (slot_0_action.mega_evolve and slot_1_action.mega_evolve)`).
    - Both slots cannot switch into the same reserve bench Pokémon simultaneously.
    """

    trainer_id: str
    slot_0_action: SingleSlotAction
    slot_1_action: SingleSlotAction

    def describe(self) -> str:
        """Return a concise summary of both slots' actions."""
        return f"({self.slot_0_action.describe()} || {self.slot_1_action.describe()})"

