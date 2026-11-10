# -*- coding: utf-8 -*-
"""Regulation M-C Data Models for Showdown Battle & Team Parser.

Provides structured, PEP 484-annotated data models for Pokémon Showdown
client chat logs (Bo1 & Bo3) and team sheets under Regulation M-C.
Strictly adheres to trainer_1 (POV / primary) and trainer_2 (opponent)
naming semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class StatSpread:
    """Regulation M-C Stat Point (SP) spread for Level 50 Pokémon.

    Enforces the Regulation M-C 66-SP total budget and 32-SP single stat cap.
    Provides utility conversions between raw Stat Points and standard cartridge EVs.
    """

    hp: int = 0
    atk: int = 0
    def_: int = 0
    spa: int = 0
    spd: int = 0
    spe: int = 0

    @property
    def total_sp(self) -> int:
        """Calculate total SP allocated across all stats."""
        return self.hp + self.atk + self.def_ + self.spa + self.spd + self.spe

    def to_dict(self) -> Dict[str, int]:
        """Convert spread to dictionary representation with canonical stat names."""
        return {
            "hp": self.hp,
            "atk": self.atk,
            "def": self.def_,
            "spa": self.spa,
            "spd": self.spd,
            "spe": self.spe,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, int]) -> StatSpread:
        """Construct StatSpread from a dictionary supporting 'def' and 'def_' keys."""
        return cls(
            hp=int(d.get("hp", 0)),
            atk=int(d.get("atk", 0)),
            def_=int(d.get("def", d.get("def_", 0))),
            spa=int(d.get("spa", 0)),
            spd=int(d.get("spd", 0)),
            spe=int(d.get("spe", 0)),
        )

    @classmethod
    def from_evs_or_sp(cls, d: Dict[str, int]) -> StatSpread:
        """Parse stats that may be raw Regulation M-C SPs (<=32) or cartridge EVs (>32).

        In Showdown's Gen 9 Champions Reg M-C format, the 'EVs:' line directly
        contains Stat Points (e.g. '2 HP / 12 Def / 28 SpA / 24 Spe'). If any
        value exceeds 32, it represents standard cartridge EVs (4..252) and is
        converted via the standard Level 50 formula: 1 + (ev - 4) // 8.
        """
        is_cartridge_ev = any(v > 32 for v in d.values())
        if is_cartridge_ev:
            def ev_to_sp(ev: int) -> int:
                if ev < 4:
                    return 0
                return min(32, 1 + (int(ev) - 4) // 8)

            return cls(
                hp=ev_to_sp(d.get("hp", 0)),
                atk=ev_to_sp(d.get("atk", 0)),
                def_=ev_to_sp(d.get("def", d.get("def_", 0))),
                spa=ev_to_sp(d.get("spa", 0)),
                spd=ev_to_sp(d.get("spd", 0)),
                spe=ev_to_sp(d.get("spe", 0)),
            )
        return cls.from_dict(d)


@dataclass
class ParsedPokemon:
    """Represents a Pokémon entity parsed from an Open Team Sheet, team paste, or observed battle actions.

    Attributes:
        species: Canonical species name (e.g. 'Charizard', 'Arcanine-Hisui').
        base_species: Root species before Mega Evolution or forme alterations.
        nickname: Battle nickname if distinct from species.
        item: Held item name (e.g. 'Charizardite Y', 'Life Orb').
        ability: Assigned or observed ability (e.g. 'Drought', 'Grassy Surge').
        nature: Stat alignment nature (e.g. 'Timid', 'Jolly').
        level: Battle level (fixed to 50 under Regulation M-C).
        gender: Gender character ('M', 'F', None).
        spread: StatSpread instance representing the Regulation M-C SP allocation.
        ivs: Individual Values dictionary (standard 31 across all stats).
        moves: List of move names known or observed.
        is_mega: Whether the Pokémon has Mega Evolved in battle.
        mega_stone: Associated Mega Stone name if verified.
        current_hp_pct: Current remaining HP percentage (0.0 to 100.0).
        fainted: Whether the Pokémon has fainted.
        revealed_in_battle: True if the Pokémon was brought onto the active field.
        boosts: Active stat stage modifications (-6 to +6).
        status: Major status condition if inflicted ('brn', 'par', 'slp', 'psn', 'tox', 'frz').
    """

    species: str
    base_species: str = ""
    nickname: Optional[str] = None
    item: Optional[str] = None
    ability: Optional[str] = None
    nature: Optional[str] = None
    level: int = 50
    gender: Optional[str] = None
    spread: StatSpread = field(default_factory=StatSpread)
    ivs: Dict[str, int] = field(
        default_factory=lambda: {
            "hp": 31,
            "atk": 31,
            "def": 31,
            "spa": 31,
            "spd": 31,
            "spe": 31,
        }
    )
    moves: List[str] = field(default_factory=list)
    is_mega: bool = False
    mega_stone: Optional[str] = None
    current_hp_pct: float = 100.0
    fainted: bool = False
    revealed_in_battle: bool = False
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
    active_turns: int = 0
    used_protect_last_turn: bool = False
    last_move_used: Optional[str] = None


@dataclass
class ParsedTeam:
    """Represents a trainer's roster, preview lineup, leads, and active sets.

    Attributes:
        trainer_name: Display name of the trainer.
        team_preview: List of 6 species shown during team preview.
        battle_roster: List of species brought to the battle (max 4 in VGC doubles).
        leads: Tuple of the 2 Pokémon sent out as leads.
        active_slots: List of currently active species on the field (up to 2).
        pokemon_sets: Dictionary mapping species/nickname to ParsedPokemon sets.
    """

    trainer_name: str
    team_preview: List[str] = field(default_factory=list)
    battle_roster: List[str] = field(default_factory=list)
    leads: Tuple[str, ...] = ()
    active_slots: List[str] = field(default_factory=list)
    pokemon_sets: Dict[str, ParsedPokemon] = field(default_factory=dict)

    def get_pokemon(self, identifier: str) -> Optional[ParsedPokemon]:
        """Lookup Pokémon by species, nickname, or canonical root species name."""
        if identifier in self.pokemon_sets:
            return self.pokemon_sets[identifier]
        clean_id = identifier.strip().lower()
        for key, pkm in self.pokemon_sets.items():
            if key.lower() == clean_id or pkm.species.lower() == clean_id:
                return pkm
            if pkm.nickname and pkm.nickname.lower() == clean_id:
                return pkm
            if pkm.base_species and pkm.base_species.lower() == clean_id:
                return pkm
            if pkm.species.split("-")[0].lower() == clean_id:
                return pkm
        return None


@dataclass
class SpeedObservation:
    """Observed turn order between two Pokémon moving in the same priority bracket.

    Provides empirical speed bounds (e.g. faster_mon.effective_speed >= slower_mon.effective_speed).

    Attributes:
        faster_mon: Identifier/species of Pokémon that moved first.
        slower_mon: Identifier/species of Pokémon that moved second.
        turn: Turn number where order was observed.
        priority: Priority bracket of both moves.
        faster_move: Move executed by the faster Pokémon.
        slower_move: Move executed by the slower Pokémon.
        weather: Active weather during the turn.
        terrain: Active terrain during the turn.
        tailwind_active_faster: Whether Tailwind was active on faster Pokémon's side.
        tailwind_active_slower: Whether Tailwind was active on slower Pokémon's side.
        trick_room_active: Whether Trick Room was inverted during the turn.
        notes: Contextual notes (e.g. Speed tie candidate, ability boosts).
    """

    faster_mon: str
    slower_mon: str
    turn: int
    priority: int
    faster_move: str
    slower_move: str
    weather: Optional[str] = None
    terrain: Optional[str] = None
    tailwind_active_faster: bool = False
    tailwind_active_slower: bool = False
    trick_room_active: bool = False
    notes: str = ""


@dataclass
class DamageObservation:
    """Observed damage percentage taken from an attack event.

    Used by the engine to infer defensive/offensive Stat Point allocations.

    Attributes:
        attacker: Pokémon that executed the attack.
        defender: Pokémon that received the damage.
        move: Move name.
        damage_pct: Percentage of maximum HP lost (e.g. 75.0, 97.0).
        turn: Turn number of the attack.
        weather: Active weather during the attack.
        terrain: Active terrain during the attack.
        attacker_boosts: Stat boosts of the attacker at time of execution.
        defender_boosts: Stat boosts of the defender at time of execution.
        is_crit: Whether the attack was reported as a critical hit.
        effectiveness: Effectiveness descriptor ('super_effective', 'resisted', 'neutral', 'immune').
        hits: Number of times the move hit (for multi-hit moves like Dual Wingbeat).
    """

    attacker: str
    defender: str
    move: str
    damage_pct: float
    turn: int
    weather: Optional[str] = None
    terrain: Optional[str] = None
    attacker_boosts: Dict[str, int] = field(default_factory=dict)
    defender_boosts: Dict[str, int] = field(default_factory=dict)
    is_crit: bool = False
    effectiveness: Optional[str] = None
    hits: int = 1


@dataclass
class ParsedBattle:
    """Complete parsed match state and telemetry between trainer_1 and trainer_2.

    Attributes:
        format: Showdown format header (e.g. '[Gen 9 Champions] VGC 2026 Reg M-C').
        is_bo3: Whether this match was played in a Best-of-3 series.
        game_number: Game index if part of a Best-of-3 series (e.g. 1, 2, 3).
        trainer_1: ParsedTeam for the POV / user trainer.
        trainer_2: ParsedTeam for the opposing trainer.
        turns_played: Total turns executed in the match.
        winner: Name of winning trainer or None.
        forfeit: True if match ended due to a forfeit.
        speed_observations: Chronological list of empirical speed comparisons.
        damage_observations: Chronological list of empirical damage observations.
        weather: Last observed active weather.
        terrain: Last observed active terrain.
        trainer_1_rating: Tuple of (pre_rating, post_rating) for trainer_1 if reported.
        trainer_2_rating: Tuple of (pre_rating, post_rating) for trainer_2 if reported.
    """

    format: str = "[Gen 9 Champions] VGC 2026 Reg M-C"
    is_bo3: bool = False
    game_number: Optional[int] = None
    trainer_1: ParsedTeam = field(
        default_factory=lambda: ParsedTeam(trainer_name="trainer_1")
    )
    trainer_2: ParsedTeam = field(
        default_factory=lambda: ParsedTeam(trainer_name="trainer_2")
    )
    turns_played: int = 0
    winner: Optional[str] = None
    forfeit: bool = False
    speed_observations: List[SpeedObservation] = field(default_factory=list)
    damage_observations: List[DamageObservation] = field(default_factory=list)
    weather: Optional[str] = None
    terrain: Optional[str] = None
    trainer_1_tailwind: bool = False
    trainer_2_tailwind: bool = False
    trick_room: bool = False
    trainer_1_rating: Optional[Tuple[int, int]] = None
    trainer_2_rating: Optional[Tuple[int, int]] = None

