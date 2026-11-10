# -*- coding: utf-8 -*-
"""Regulation M-C Legal Action Enumerator for VGC Doubles.

Enumerates all legal single-slot (`SingleSlotAction`) and joint 2-slot
(`JointTrainerAction`) decisions for `trainer_1` and `trainer_2` from a
compiled `TurnState`.

Key Mechanics Enforced:
1. Showdown Doubles Move Targeting (`normal` -> both foes + ally partner for
   synergies like Beat Up + Justified or Stomping Tantrum fail-doubling,
   `allAdjacentFoes`, `allAdjacent`, `adjacentAlly`, `adjacentAllyOrSelf`,
   `self`, `allySide`, `foeSide`, `all`).
2. Mega Evolution Branching: When a Pokémon holds a valid Mega Stone and its
   trainer has not yet Mega Evolved, generates both `mega_evolve=False` and
   `mega_evolve=True` variants for every legal move (enabling delayed weather/terrain
   control with Mega Charizard Y / Mega Raichu X or holding Mega against Fake Out).
3. Joint 2-Slot Constraints:
   - At most one slot per trainer may Mega Evolve in a joint turn.
   - Both active slots cannot switch into the same reserve bench Pokémon.
4. Turn-1 & Item/Volatile Restrictions:
   - `Fake Out`, `First Impression`, and `Mat Block` require `active_turns == 1`.
   - `Assault Vest` and `Taunt` block `Status` category moves.
   - `Choice Band`, `Choice Specs`, `Choice Scarf`, and `Encore` enforce move locks.
"""

from __future__ import annotations

from typing import List, Optional, Set

from .models import (
    ActionType,
    CompiledMove,
    CompiledPokemonState,
    JointTrainerAction,
    SingleSlotAction,
    TargetRef,
    TrainerSideState,
    TurnState,
)

FIRST_TURN_ONLY_MOVES: Set[str] = {
    "Fake Out",
    "First Impression",
    "Mat Block",
}

PROTECT_MOVES: Set[str] = {
    "Protect",
    "Detect",
    "Spiky Shield",
    "King's Shield",
    "Baneful Bunker",
    "Silk Trap",
    "Burning Bulwark",
    "Wide Guard",
    "Quick Guard",
}


class LegalActionEnumerator:
    """Enumerates legal single-slot and joint 2-slot actions for `trainer_1` and `trainer_2`."""

    def __init__(
        self,
        allow_consecutive_protect: bool = False,
        include_switches: bool = True,
    ) -> None:
        """Initialize the legal action enumerator.

        Args:
            allow_consecutive_protect: If False (default), prunes `Protect` / `Detect`
                variants when `used_protect_last_turn` is True (except `Wide Guard` /
                `Quick Guard` which do not decay in consecutive success rate).
            include_switches: If True (default), enumerates `SWITCH` actions into
                available unfainted bench slots in the 4-Pokémon battle roster.
        """
        self.allow_consecutive_protect: bool = allow_consecutive_protect
        self.include_switches: bool = include_switches

    # ------------------------------------------------------------------
    # Single-Slot Enumeration
    # ------------------------------------------------------------------

    def enumerate_slot_actions(
        self,
        turn_state: TurnState,
        trainer_id: str,
        slot_idx: int,
        include_switches: Optional[bool] = None,
    ) -> List[SingleSlotAction]:
        """Enumerate all legal actions for a single active slot (0 or 1).

        Args:
            turn_state: Current compiled `TurnState`.
            trainer_id: 'trainer_1' or 'trainer_2'.
            slot_idx: Active slot index (0 or 1).
            include_switches: Optional override for `self.include_switches`.

        Returns:
            List of legal `SingleSlotAction` instances for `(trainer_id, slot_idx)`.
        """
        if slot_idx not in (0, 1):
            raise ValueError(f"slot_idx must be 0 or 1, got {slot_idx}")

        my_side = turn_state.get_side(trainer_id)
        opp_side = turn_state.get_opposing_side(trainer_id)
        actor = my_side.active_slots[slot_idx]

        if actor is None or actor.fainted:
            return [
                SingleSlotAction(
                    trainer_id=trainer_id,
                    actor_slot=slot_idx,
                    actor_species="None",
                    action_type=ActionType.PASS,
                )
            ]

        actions: List[SingleSlotAction] = []

        # Determine whether Mega Evolution branching applies to this Pokémon
        can_mega_now = bool(
            actor.can_mega_evolve
            and not actor.is_mega
            and not my_side.mega_used
        )
        mega_variants = [False, True] if can_mega_now else [False]

        # 1. Enumerate Legal Moves + Targets + Mega Toggle
        legal_moves = self._filter_legal_moves(actor)
        for move in legal_moves:
            targets = self._resolve_move_targets(
                move=move,
                trainer_id=trainer_id,
                actor_slot=slot_idx,
                my_side=my_side,
                opp_side=opp_side,
            )
            for target_ref in targets:
                for mega_flag in mega_variants:
                    actions.append(
                        SingleSlotAction(
                            trainer_id=trainer_id,
                            actor_slot=slot_idx,
                            actor_species=actor.species,
                            action_type=ActionType.MOVE,
                            move_name=move.name,
                            target=target_ref,
                            mega_evolve=mega_flag,
                        )
                    )

        # 2. Enumerate Legal Bench Switches
        do_switches = self.include_switches if include_switches is None else include_switches
        if do_switches:
            for bench_mon in my_side.bench_slots:
                if not bench_mon.fainted and bench_mon.current_hp > 0:
                    actions.append(
                        SingleSlotAction(
                            trainer_id=trainer_id,
                            actor_slot=slot_idx,
                            actor_species=actor.species,
                            action_type=ActionType.SWITCH,
                            switch_in_species=bench_mon.species,
                            mega_evolve=False,
                        )
                    )

        # Fallback if all moves were locked/disabled and no bench switch is available
        if not actions:
            actions.append(
                SingleSlotAction(
                    trainer_id=trainer_id,
                    actor_slot=slot_idx,
                    actor_species=actor.species,
                    action_type=ActionType.MOVE,
                    move_name="Struggle",
                    target=TargetRef(opp_side.trainer_id, 0),
                    mega_evolve=False,
                )
            )

        return actions

    def _filter_legal_moves(self, actor: CompiledPokemonState) -> List[CompiledMove]:
        """Filter `actor.moves` by Turn-1, Choice lock, Encore, Assault Vest, and Taunt rules."""
        legal: List[CompiledMove] = []

        for move in actor.moves:
            # 1. Encore lock overrides everything else
            if actor.encore_move and move.name.lower() != actor.encore_move.lower():
                continue

            # 2. Choice item lock
            if actor.locked_move and move.name.lower() != actor.locked_move.lower():
                continue

            # 3. Turn-1-only moves (Fake Out, First Impression, Mat Block)
            if move.name in FIRST_TURN_ONLY_MOVES and actor.active_turns > 1:
                continue

            # 4. Assault Vest blocks Status moves
            if actor.item == "Assault Vest" and move.category == "Status":
                continue

            # 5. Taunt blocks Status moves
            if actor.taunt_turns > 0 and move.category == "Status":
                continue

            # 6. Consecutive Protect check (Wide Guard & Quick Guard do not decay in Gen 9)
            if (
                not self.allow_consecutive_protect
                and actor.used_protect_last_turn
                and move.name in PROTECT_MOVES
                and move.name not in ("Wide Guard", "Quick Guard")
            ):
                continue

            legal.append(move)

        return legal

    def _resolve_move_targets(
        self,
        move: CompiledMove,
        trainer_id: str,
        actor_slot: int,
        my_side: TrainerSideState,
        opp_side: TrainerSideState,
    ) -> List[TargetRef]:
        """Resolve all legal Showdown Doubles targets for `move`."""
        target_type = move.target
        partner_slot = 1 - actor_slot
        partner_mon = my_side.active_slots[partner_slot]
        partner_alive = partner_mon is not None and not partner_mon.fainted

        opp_id = opp_side.trainer_id
        opp_alive_slots = [
            idx
            for idx in (0, 1)
            if opp_side.active_slots[idx] is not None
            and not opp_side.active_slots[idx].fainted  # type: ignore[union-attr]
        ]

        # 1. Single-target any adjacent Pokémon ('normal', 'any')
        # Includes both alive opposing slots AND the ally partner slot (for Beat Up + Justified,
        # Stomping Tantrum fail-doubling, Pollen Puff healing, Weakness Policy self-procs, etc.)
        if target_type in ("normal", "any"):
            targets: List[TargetRef] = [
                TargetRef(opp_id, opp_idx) for opp_idx in opp_alive_slots
            ]
            if partner_alive:
                targets.append(TargetRef(trainer_id, partner_slot))
            return targets

        # 2. Single-target opposing Pokémon only ('adjacentFoe')
        if target_type == "adjacentFoe":
            return [TargetRef(opp_id, opp_idx) for opp_idx in opp_alive_slots]

        # 3. Single-target ally partner only ('adjacentAlly', e.g. Helping Hand, Coaching)
        if target_type == "adjacentAlly":
            if partner_alive:
                return [TargetRef(trainer_id, partner_slot)]
            return []

        # 4. Ally or Self ('adjacentAllyOrSelf', e.g. Acupressure)
        if target_type == "adjacentAllyOrSelf":
            targets = [TargetRef(trainer_id, actor_slot)]
            if partner_alive:
                targets.append(TargetRef(trainer_id, partner_slot))
            return targets

        # 5. Spread targeting both opposing active slots ('allAdjacentFoes')
        if target_type == "allAdjacentFoes":
            return [TargetRef("all_adjacent_foes", None)]

        # 6. Spread targeting partner + both opposing active slots ('allAdjacent')
        if target_type == "allAdjacent":
            return [TargetRef("all_adjacent", None)]

        # 7. Self-targeting status/buff moves ('self', e.g. Protect, Swords Dance, Minimize)
        if target_type == "self":
            return [TargetRef("self", None)]

        # 8. Team-side support ('allySide', 'allyTeam', e.g. Tailwind, Reflect, Light Screen)
        if target_type in ("allySide", "allyTeam"):
            return [TargetRef("ally_side", None)]

        # 9. Opposing side hazard/effect ('foeSide')
        if target_type == "foeSide":
            return [TargetRef("foe_side", None)]

        # 10. Global field moves ('all', 'scripted', 'randomNormal')
        return [TargetRef("field", None)]

    # ------------------------------------------------------------------
    # Joint 2-Slot Enumeration
    # ------------------------------------------------------------------

    def enumerate_joint_actions(
        self,
        turn_state: TurnState,
        trainer_id: str,
        include_switches: Optional[bool] = None,
    ) -> List[JointTrainerAction]:
        """Enumerate all legal joint 2-slot actions (`slot_0 × slot_1`) for `trainer_id`.

        Enforces joint VGC constraints:
        1. At most one active slot can Mega Evolve in a single turn:
           `not (a0.mega_evolve and a1.mega_evolve)`
        2. Both active slots cannot switch into the same reserve bench Pokémon:
           `not (a0.action_type == SWITCH and a1.action_type == SWITCH and a0.switch_in_species == a1.switch_in_species)`
        """
        slot_0_actions = self.enumerate_slot_actions(
            turn_state=turn_state,
            trainer_id=trainer_id,
            slot_idx=0,
            include_switches=include_switches,
        )
        slot_1_actions = self.enumerate_slot_actions(
            turn_state=turn_state,
            trainer_id=trainer_id,
            slot_idx=1,
            include_switches=include_switches,
        )

        joint_actions: List[JointTrainerAction] = []
        for a0 in slot_0_actions:
            for a1 in slot_1_actions:
                # Rule 1: Cannot Mega Evolve both slots on the same turn
                if a0.mega_evolve and a1.mega_evolve:
                    continue

                # Rule 2: Cannot switch both slots into the exact same bench Pokémon
                if (
                    a0.action_type == ActionType.SWITCH
                    and a1.action_type == ActionType.SWITCH
                    and a0.switch_in_species == a1.switch_in_species
                ):
                    continue

                joint_actions.append(
                    JointTrainerAction(
                        trainer_id=trainer_id,
                        slot_0_action=a0,
                        slot_1_action=a1,
                    )
                )

        return joint_actions

