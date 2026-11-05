# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Logical Constraint & Risk-Reward Engine
File: engine/tactics/logic_engine.py

Architecture Overview:
----------------------
Evaluates candidate Pokémon battle actions through a dual-mode logical lens:

1. Tier 1 Absolute Physical Invariants (Mechanical Failures — 0.00% Validity):
   - D-01: Fainted Slot Preservation (HP <= 0).
   - D-04: Trapping via Binding Moves (Infestation, Fire Spin) and Active Shadow Tag
           (Mega Gengar), accounting for Ghost-type and mirror exemptions.
   - D-05: Roar/Dragon Tail safe First-Turn-Out tracking (first_action_executed).
   - D-06: Equipment locks (Assault Vest status block, Choice Item move locking).
   - D-07: Volatile locks (Taunt, Encore, Disable).
   - D-08: PP Depletion (PP <= 0).
   - D-12: Redundant Setup at +6 stages (preserved if opposing Sucker Punch is threatened).

2. Tier 2 Column-Nullity Edge Pruners:
   - D-09: Type & Ability Immunity (pruned iff active target AND all bench reserves are immune).
   - D-10: Psychic Terrain Priority Block (pruned iff active target AND all bench reserves
           are grounded, and ally cannot clear terrain. Condition C disabled).
   - D-11: Prankster vs Dark-Type (pruned iff active target AND all bench reserves are Dark).

3. Soft Tactical Priors (Continuous Risk-Reward Continuum):
   - Consecutive Protect decay (~33% on 2nd use, ~11% on >=3rd use).
   - High-risk / high-reward prediction reads into active immunities to catch incoming switches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

try:
    from engine.turn_simulator import (
        BASE_STATS_DB,
        MOVE_DB,
        PROTECT_MOVES,
        get_type_effectiveness_breakdown,
    )
except ImportError:
    BASE_STATS_DB: Dict[str, Dict[str, Any]] = {}
    MOVE_DB: Dict[str, Dict[str, Any]] = {}
    PROTECT_MOVES: Set[str] = {
        "Protect", "Detect", "Wide Guard", "Quick Guard",
        "Spiky Shield", "Baneful Bunker", "Silk Trap", "Burning Bulwark"
    }

    def get_type_effectiveness_breakdown(
        move_type: str,
        target_types: Sequence[str],
        move_name: str = "",
        scrappy: bool = False,
    ) -> Dict[str, float]:
        """Fallback type effectiveness evaluator if turn_simulator is unlinked."""
        raw_chart: Dict[str, Dict[str, float]] = {
            "Normal": {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
            "Fire": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0},
            "Water": {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0, "Rock": 2.0, "Dragon": 0.5},
            "Grass": {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0, "Dragon": 0.5, "Steel": 0.5},
            "Electric": {"Water": 2.0, "Grass": 0.5, "Electric": 0.5, "Ground": 0.0, "Flying": 2.0, "Dragon": 0.5},
            "Ice": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
            "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5},
            "Poison": {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
            "Ground": {"Fire": 2.0, "Grass": 0.5, "Electric": 2.0, "Poison": 2.0, "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
            "Flying": {"Grass": 2.0, "Electric": 0.5, "Fighting": 2.0, "Bug": 2.0, "Rock": 0.5, "Steel": 0.5},
            "Psychic": {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0, "Steel": 0.5},
            "Bug": {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0, "Steel": 0.5, "Fairy": 0.5},
            "Rock": {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5, "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
            "Ghost": {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
            "Dragon": {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
            "Dark": {"Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5, "Fairy": 0.5},
            "Steel": {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0, "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
            "Fairy": {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5},
        }
        multiplier = 1.0
        for def_t in target_types:
            if scrappy and move_type in ("Normal", "Fighting") and def_t == "Ghost":
                sub_mult = 1.0
            else:
                sub_mult = raw_chart.get(move_type, {}).get(def_t, 1.0)
            multiplier *= sub_mult
        return {"multiplier": multiplier}


# -----------------------------------------------------------------------------
# Regulation M-C Mechanical Classifications & Ability Sets
# -----------------------------------------------------------------------------

SOUND_MOVES: Set[str] = {
    "Hyper Voice", "Parting Shot", "Bug Buzz",
    "Snarl", "Roar", "Disarming Voice", "Relic Song"
}

SLEEP_MOVES: Set[str] = {
    "Hypnosis", "Yawn", "Sleep Powder", "Spore", "Grass Whistle"
}

STATUS_ABSORBING_ABILITIES: Set[str] = {"Good as Gold"}
FIRE_ABSORBING_ABILITIES: Set[str] = {"Flash Fire", "Well-Baked Body"}
ELECTRIC_ABSORBING_ABILITIES: Set[str] = {"Lightning Rod", "Motor Drive", "Volt Absorb"}
WATER_ABSORBING_ABILITIES: Set[str] = {"Water Absorb", "Storm Drain", "Dry Skin"}
GRASS_ABSORBING_ABILITIES: Set[str] = {"Sap Sipper"}
GROUND_ABSORBING_ABILITIES: Set[str] = {"Earth Eater"}

CHOICE_ITEMS: Set[str] = {
    "Choice Band", "Choice Scarf", "Choice Specs",
    "choiceband", "choicescarf", "choicespecs"
}

BINDING_MOVES: Set[str] = {
    "Infestation", "Fire Spin", "Magma Storm", "Sand Tomb",
    "Wrap", "Bind", "Clamp", "Snap Trap", "Thunder Cage", "Whirlpool"
}


# -----------------------------------------------------------------------------
# Structured Context Containers
# -----------------------------------------------------------------------------

@dataclass
class ConstraintResult:
    """Structured evaluation of a candidate battle action."""
    is_mechanically_valid: bool
    risk_score: float
    upside_potential: float
    classification: str
    reasons: List[str] = field(default_factory=list)
    recommended_prior_scale: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert evaluation result into a standardized dictionary."""
        return {
            "is_mechanically_valid": self.is_mechanically_valid,
            "risk_score": round(self.risk_score, 3),
            "upside_potential": round(self.upside_potential, 3),
            "classification": self.classification,
            "reasons": list(self.reasons),
            "recommended_prior_scale": round(self.recommended_prior_scale, 3),
        }


@dataclass
class BattlerContext:
    """Complete mechanical snapshot of an active or bench Pokémon."""
    species: str = "MissingNo"
    types: List[str] = field(default_factory=lambda: ["Normal"])
    ability: str = ""
    item: str = ""
    hp_cur: float = 100.0
    hp_max: float = 100.0
    is_grounded: bool = True
    is_mega: bool = False
    first_action_executed: bool = False
    is_trapped_by_binding: bool = False
    taunt_turns: int = 0
    encore_move: Optional[str] = None
    disable_move: Optional[str] = None
    choice_locked_move: Optional[str] = None
    stat_stages: Dict[str, int] = field(default_factory=dict)
    protect_chain_count: int = 0


@dataclass
class TargetSlotContext:
    """Represents an active defender slot and its eligible bench reserves."""
    active: BattlerContext
    bench: List[BattlerContext] = field(default_factory=list)

    @property
    def all_candidates(self) -> List[BattlerContext]:
        """Return the active occupant alongside all alive bench reserves."""
        return [self.active] + [b for b in self.bench if b.hp_cur > 0.0]


# -----------------------------------------------------------------------------
# Domain Engine Implementation
# -----------------------------------------------------------------------------

class LogicalConstraintEngine:
    """
    Expert rule engine enforcing Regulation M-C physical invariants and
    column-nullity pruning for competitive VGC doubles.
    """

    def __init__(self) -> None:
        """Initialize the logical constraint engine."""
        pass

    @staticmethod
    def _make_result(
        *,
        is_mechanically_valid: bool,
        classification: str,
        risk_score: float = 0.0,
        upside_potential: float = 1.0,
        reasons: Optional[List[str]] = None,
        recommended_prior_scale: float = 1.0,
    ) -> ConstraintResult:
        """Construct a standardized ConstraintResult."""
        return ConstraintResult(
            is_mechanically_valid=is_mechanically_valid,
            risk_score=risk_score,
            upside_potential=upside_potential,
            classification=classification,
            reasons=list(reasons or []),
            recommended_prior_scale=recommended_prior_scale,
        )

    @staticmethod
    def _resolve_accuracy(
        move_name: str,
        move_data: Dict[str, Any],
        weather: str,
        user_ability: str,
        target_ability: str,
    ) -> float:
        """Resolve nominal move accuracy factoring in weather and No Guard."""
        raw_acc = move_data.get("accuracy", 100)
        try:
            acc_val = float(raw_acc) if raw_acc not in (True, None, "--") else 100.0
        except (TypeError, ValueError):
            acc_val = 100.0

        if user_ability == "No Guard" or target_ability == "No Guard":
            return 100.0
        if weather == "rain" and move_name in ("Thunder", "Hurricane", "Bleakwind Storm"):
            return 100.0
        if weather == "snow" and move_name == "Blizzard":
            return 100.0
        return acc_val

    @staticmethod
    def _resolve_move_priority(
        move_name: str,
        move_data: Dict[str, Any],
        user_ability: str,
        terrain: str,
        m_cat: str,
    ) -> int:
        """Resolve effective move priority under active abilities and field terrain."""
        priority = int(move_data.get("priority", 0))
        if user_ability == "Prankster" and m_cat == "Status":
            priority += 1
        elif move_name == "Grassy Glide" and terrain == "grassy":
            priority += 1
        return priority

    def _evaluate_protect_chain(
        self,
        protect_chain_count: int,
        move_name: str,
    ) -> Optional[ConstraintResult]:
        """Evaluate consecutive Protect usage under official (1/3)^k decay."""
        if move_name not in PROTECT_MOVES or protect_chain_count <= 0:
            return None

        success_probability = (1.0 / 3.0) ** protect_chain_count
        risk_score = 1.0 - success_probability

        if protect_chain_count == 1:
            return self._make_result(
                is_mechanically_valid=True,
                classification="High_Risk_High_Reward",
                risk_score=0.67,
                upside_potential=0.85,
                reasons=["Consecutive Protect selected; success decays to ~33%."],
                recommended_prior_scale=0.40,
            )

        if protect_chain_count >= 2:
            return self._make_result(
                is_mechanically_valid=True,
                classification="High_Risk_High_Reward",
                risk_score=min(0.97, max(0.89, round(risk_score, 3))),
                upside_potential=0.90,
                reasons=[f"Protect chain at {protect_chain_count} uses; ~{success_probability:.2%} success rate."],
                recommended_prior_scale=0.10,
            )
        return None

    def _check_immunity(
        self,
        move_name: str,
        move_type: str,
        m_cat: str,
        user: BattlerContext,
        candidate: BattlerContext,
    ) -> bool:
        """Determine if a candidate target has 100% mechanical immunity to an attack."""
        if candidate.hp_cur <= 0.0:
            return True

        if m_cat == "Status":
            if candidate.ability == "Good as Gold":
                return True
            return False

        scrappy_active = user.ability in ("Scrappy", "Mind's Eye")
        eff = get_type_effectiveness_breakdown(
            move_type, candidate.types, move_name=move_name, scrappy=scrappy_active
        )
        if eff.get("multiplier", 1.0) == 0.0:
            return True

        # Ground vs Flying / Levitate immunity
        if move_type == "Ground" and not candidate.is_grounded and move_name != "Thousand Arrows":
            return True

        # Defensive ability nullification (bypassed by Mold Breaker)
        if user.ability not in ("Mold Breaker", "Teravolt", "Turboblaze"):
            if move_type == "Fire" and candidate.ability in FIRE_ABSORBING_ABILITIES:
                return True
            if move_type == "Electric" and candidate.ability in ELECTRIC_ABSORBING_ABILITIES:
                return True
            if move_type == "Water" and candidate.ability in WATER_ABSORBING_ABILITIES:
                return True
            if move_type == "Grass" and candidate.ability in GRASS_ABSORBING_ABILITIES:
                return True
            if move_type == "Ground" and candidate.ability in GROUND_ABSORBING_ABILITIES:
                return True
            if (move_name in SOUND_MOVES or MOVE_DB.get(move_name, {}).get("is_sound")) and candidate.ability == "Soundproof":
                return True

        return False

    def is_trapped(
        self,
        user: BattlerContext,
        opposing_active: Sequence[BattlerContext],
    ) -> bool:
        """
        D-04: Evaluate Regulation M-C trapping invariants.
        Ghost-types are universally exempt from all switch-prevention effects.
        Shadow Tag (Mega Gengar) and partial binding (Infestation/Fire Spin) are verified.
        """
        # Ghost typing guarantees escape from all trapping mechanics
        if any(t.lower() == "ghost" for t in user.types):
            return False

        # Partial-trapping / binding moves (Infestation, Fire Spin, Sand Tomb)
        if user.is_trapped_by_binding:
            return True

        # Shadow Tag verification (Mega Gengar)
        for opp in opposing_active:
            if opp.hp_cur <= 0.0:
                continue

            # In Regulation M-C, Shadow Tag is active if Mega Gengar is active on the field
            has_shadow_tag = (
                opp.ability == "Shadow Tag"
                or (opp.is_mega and "gengar" in opp.species.lower())
            )

            # Shadow Tag users can switch freely against opposing Shadow Tag
            if has_shadow_tag and user.ability != "Shadow Tag":
                return True

        return False

    def evaluate_action(
        self,
        user: BattlerContext,
        move_name: str,
        target: Optional[TargetSlotContext] = None,
        field_state: Optional[Dict[str, Any]] = None,
        opposing_active_battlers: Optional[Sequence[BattlerContext]] = None,
        opposing_active_moves: Optional[Sequence[str]] = None,
        ally_can_clear_terrain: bool = False,
        is_switch_action: bool = False,
        move_pp: int = 5,
    ) -> ConstraintResult:
        """
        Evaluate a candidate battle action against physical invariants and
        column-nullity pruning rules.
        """
        field_state = field_state or {}
        weather = (field_state.get("weather") or "").lower()
        terrain = (field_state.get("terrain") or "").lower()
        move_data = MOVE_DB.get(move_name, {})
        m_type = move_data.get("type", "Normal")
        m_cat = move_data.get("cat", "Status")
        opp_battlers = opposing_active_battlers or []

        # =====================================================================
        # TIER 1: ABSOLUTE PHYSICAL INVARIANTS (UNCONDITIONAL DISCARDS)
        # =====================================================================

        # D-01: Dead Slot (mon is fainted)
        if user.hp_cur <= 0.0:
            return self._make_result(
                is_mechanically_valid=False,
                classification="Mechanically_Invalid",
                reasons=[f"{user.species} is fainted and cannot act."]
            )

        # Switch Action Invariants
        if is_switch_action:
            # D-04: Hard Trapping (Infestation binding & active Mega Gengar Shadow Tag)
            if self.is_trapped(user, opp_battlers):
                return self._make_result(
                    is_mechanically_valid=False,
                    classification="Mechanically_Invalid",
                    reasons=[f"{user.species} is trapped by Shadow Tag / binding and cannot switch."]
                )
            # Switches are legal; choice locks reset upon pivot
            return self._make_result(
                is_mechanically_valid=True,
                classification="Deterministic_Safe",
                recommended_prior_scale=0.65,
            )

        # D-08: PP Exhaustion
        if move_pp <= 0:
            return self._make_result(
                is_mechanically_valid=False,
                classification="Mechanically_Invalid",
                reasons=[f"{move_name} has 0 PP remaining."]
            )

        # D-05: First-Turn-Out Expiration (Fake Out / First Impression)
        # Correctly legal if dragged in by Roar/Dragon Tail and yet to execute an action
        if move_name in ("Fake Out", "First Impression") and user.first_action_executed:
            return self._make_result(
                is_mechanically_valid=False,
                classification="Mechanically_Invalid",
                reasons=[f"{move_name} fails because {user.species} has already executed an action."]
            )

        # D-06: Equipment Constraints (Assault Vest & Choice Items)
        if user.item in ("Assault Vest", "assaultvest") and m_cat == "Status":
            return self._make_result(
                is_mechanically_valid=False,
                classification="Mechanically_Invalid",
                reasons=[f"Assault Vest prevents selecting Status move {move_name}."]
            )

        if user.item in CHOICE_ITEMS and user.choice_locked_move and move_name != user.choice_locked_move:
            return self._make_result(
                is_mechanically_valid=False,
                classification="Mechanically_Invalid",
                reasons=[f"{user.item} locks {user.species} into {user.choice_locked_move}."]
            )

        # D-07: Status & Volatile Locks (Taunt, Encore, Disable)
        if user.taunt_turns > 0 and m_cat == "Status":
            return self._make_result(
                is_mechanically_valid=False,
                classification="Mechanically_Invalid",
                reasons=[f"Taunt prevents selecting Status move {move_name}."]
            )
        if user.encore_move and move_name != user.encore_move:
            return self._make_result(
                is_mechanically_valid=False,
                classification="Mechanically_Invalid",
                reasons=[f"Encore locks {user.species} into {user.encore_move}."]
            )
        if user.disable_move and move_name == user.disable_move:
            return self._make_result(
                is_mechanically_valid=False,
                classification="Mechanically_Invalid",
                reasons=[f"{move_name} is currently Disabled."]
            )

        # D-12: Hard Cap Redundancy & Sucker Punch Bluffing
        if m_cat == "Status" and str(move_data.get("target", "")).lower() == "self":
            stat_deltas = move_data.get("stat_deltas", {})
            if stat_deltas:
                all_capped = all(
                    delta > 0 and user.stat_stages.get(stat.lower(), 0) >= 6
                    for stat, delta in stat_deltas.items()
                )
                if all_capped:
                    opp_moves = opposing_active_moves or []
                    # Preserve action as a valid tactical bluff if opponent threatens Sucker Punch
                    if "Sucker Punch" not in opp_moves:
                        return self._make_result(
                            is_mechanically_valid=False,
                            classification="Mechanically_Invalid",
                            reasons=[f"{move_name} is redundant at +6 stages and no Sucker Punch threat exists."]
                        )

        # Priority resolution
        m_prio = self._resolve_move_priority(move_name, move_data, user.ability, terrain, m_cat)

        # Consecutive Protect probability decay heuristic
        if move_name in PROTECT_MOVES:
            protect_result = self._evaluate_protect_chain(user.protect_chain_count, move_name)
            if protect_result is not None:
                return protect_result

        # =====================================================================
        # TIER 2: COLUMN-NULLITY INVARIANTS (ROSTER & SWITCH-IN AUDIT)
        # =====================================================================
        if target is not None:
            # D-09: Universal Type & Ability Immunity Invariance
            all_immune = all(
                self._check_immunity(move_name, m_type, m_cat, user, candidate)
                for candidate in target.all_candidates
            )
            if all_immune:
                return self._make_result(
                    is_mechanically_valid=False,
                    classification="Mechanically_Invalid",
                    reasons=[f"All active and bench targets in slot are immune to {move_name}."]
                )

            # D-10: Universal Priority Block Invariance (Psychic Terrain)
            # Condition C (Armor Tail / Queenly Majesty) is explicitly DISABLED
            if m_prio > 0 and terrain == "psychic" and not ally_can_clear_terrain:
                all_grounded = all(candidate.is_grounded for candidate in target.all_candidates)
                if all_grounded:
                    return self._make_result(
                        is_mechanically_valid=False,
                        classification="Mechanically_Invalid",
                        reasons=[f"Psychic Terrain blocks priority {move_name} across all candidates."]
                    )

            # D-11: Universal Prankster vs. Dark-Type Invariance
            if user.ability == "Prankster" and m_cat == "Status":
                all_dark = all(
                    any(t.lower() == "dark" for t in candidate.types)
                    for candidate in target.all_candidates
                )
                if all_dark:
                    return self._make_result(
                        is_mechanically_valid=False,
                        classification="Mechanically_Invalid",
                        reasons=[f"Prankster {move_name} fails against Dark-type across all candidates."]
                    )

            # Terrain Sleep Block (Electric / Misty Terrain)
            if move_name in SLEEP_MOVES and terrain in ("electric", "misty"):
                all_grounded = all(candidate.is_grounded for candidate in target.all_candidates)
                if all_grounded:
                    return self._make_result(
                        is_mechanically_valid=False,
                        classification="Mechanically_Invalid",
                        reasons=[f"Sleep move {move_name} is universally blocked by {terrain} terrain."]
                    )

        # =====================================================================
        # TIER 3: SOFT TACTICAL PRIORS (VALID HEURISTIC SCORING)
        # =====================================================================
        target_ability = target.active.ability if target else ""
        acc_val = self._resolve_accuracy(move_name, move_data, weather, user.ability, target_ability)
        is_inaccurate = acc_val < 85.0
        acc_risk = round((100.0 - acc_val) / 100.0, 3) if is_inaccurate else 0.0

        if target is not None and m_cat != "Status":
            scrappy_active = user.ability in ("Scrappy", "Mind's Eye")
            breakdown = get_type_effectiveness_breakdown(
                m_type, target.active.types, move_name=move_name, scrappy=scrappy_active
            )
            eff = breakdown.get("multiplier", 1.0)

            # Ground move targeting airborne mon in active slot
            if m_type == "Ground" and not target.active.is_grounded and move_name != "Thousand Arrows":
                eff = 0.0

            # Single-target attack into active immunity (viable as an aggressive switch-read)
            if eff == 0.0:
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=0.85,
                    upside_potential=0.85,
                    classification="High_Risk_High_Reward",
                    reasons=[f"{move_name} deals 0x to active {target.active.species}; viable solely as prediction read on opposing switch."],
                    recommended_prior_scale=0.15,
                )

            if eff <= 0.25:
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=0.55,
                    upside_potential=0.60,
                    classification="Calculated_Risk",
                    reasons=[f"{move_name} hits {target.active.species} into double resistance (0.25x)."],
                    recommended_prior_scale=0.50,
                )

            reasons: List[str] = []
            if is_inaccurate:
                reasons.append(f"{move_name} carries accuracy risk ({acc_val}% nominal hit rate).")

            if eff >= 4.0:
                reasons.append(f"{move_name} exploits a 4.0x double weakness on {target.active.species}.")
                prior_scale = 1.35 * (acc_val / 100.0)
                classification = "Calculated_Risk" if is_inaccurate else "Deterministic_Safe"
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=max(0.05, acc_risk),
                    upside_potential=0.95,
                    classification=classification,
                    reasons=reasons,
                    recommended_prior_scale=round(prior_scale, 3),
                )

            if eff >= 2.0:
                reasons.append(f"{move_name} is super effective (2.0x) against {target.active.species}.")
                prior_scale = 1.20 * (acc_val / 100.0)
                classification = "Calculated_Risk" if is_inaccurate else "Deterministic_Safe"
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=max(0.10, acc_risk),
                    upside_potential=0.85,
                    classification=classification,
                    reasons=reasons,
                    recommended_prior_scale=round(prior_scale, 3),
                )

        if is_inaccurate:
            return self._make_result(
                is_mechanically_valid=True,
                risk_score=acc_risk,
                upside_potential=0.80,
                classification="Calculated_Risk",
                reasons=[f"{move_name} carries accuracy risk ({acc_val}% nominal hit rate)."],
                recommended_prior_scale=round(acc_val / 100.0, 3),
            )

        return self._make_result(
            is_mechanically_valid=True,
            risk_score=0.10,
            upside_potential=0.70,
            classification="Deterministic_Safe",
            reasons=[f"Standard valid execution of {move_name}."],
            recommended_prior_scale=1.0,
        )

    def prune_impossible_actions(
        self,
        candidate_actions: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter candidate action specifications, retaining only mechanically valid choices."""
        valid_actions: List[Dict[str, Any]] = []
        for action_kwargs in candidate_actions:
            result = self.evaluate_slot_action(**action_kwargs)
            if result.is_mechanically_valid:
                valid_actions.append(action_kwargs)
        return valid_actions

    def evaluate_slot_action(
        self,
        slot_species: str,
        move_name: str,
        target_species: Optional[str] = None,
        active_turns: int = 1,
        field_state: Optional[Dict[str, Any]] = None,
        was_protected_last_turn: bool = False,
        is_target_airborne: bool = False,
        user_ability: str = "",
        target_ability: str = "",
        target_types: Optional[List[str]] = None,
        opposing_abilities: Optional[List[str]] = None,
        is_user_grounded: bool = True,
        is_target_grounded: Optional[bool] = None,
        protect_chain_count: int = 0,
        first_action_executed: Optional[bool] = None,
        user_item: str = "",
        choice_locked_move: Optional[str] = None,
        is_trapped_by_binding: bool = False,
        is_switch_action: bool = False,
        target_bench_candidates: Optional[Sequence[Dict[str, Any]]] = None,
        opposing_active_moves: Optional[Sequence[str]] = None,
        opposing_active_battlers: Optional[Sequence[Dict[str, Any]]] = None,
        ally_can_clear_terrain: bool = False,
        user_hp_cur: float = 100.0,
        move_pp: int = 5,
        user_stat_stages: Optional[Dict[str, int]] = None,
        user_taunt_turns: int = 0,
        user_encore_move: Optional[str] = None,
        user_disable_move: Optional[str] = None,
    ) -> ConstraintResult:
        """Backward-compatible procedural adapter mapping into evaluate_action."""
        user_types_resolved = list(BASE_STATS_DB.get(slot_species, {}).get("types", ["Normal"]))

        # First action executed resolution (D-05)
        action_executed = (
            first_action_executed
            if first_action_executed is not None
            else (active_turns > 1)
        )

        effective_protect_chain = protect_chain_count
        if was_protected_last_turn and effective_protect_chain == 0:
            effective_protect_chain = 1

        user_ctx = BattlerContext(
            species=slot_species,
            types=user_types_resolved,
            ability=user_ability,
            item=user_item,
            hp_cur=user_hp_cur,
            is_grounded=is_user_grounded,
            first_action_executed=action_executed,
            is_trapped_by_binding=is_trapped_by_binding,
            taunt_turns=user_taunt_turns,
            encore_move=user_encore_move,
            disable_move=user_disable_move,
            choice_locked_move=choice_locked_move,
            stat_stages=dict(user_stat_stages or {}),
            protect_chain_count=effective_protect_chain,
        )

        target_ctx: Optional[TargetSlotContext] = None
        if target_species is not None:
            t_types = (
                list(target_types)
                if target_types
                else list(BASE_STATS_DB.get(target_species, {}).get("types", ["Normal"]))
            )
            t_grounded = (
                is_target_grounded
                if is_target_grounded is not None
                else not is_target_airborne
            )
            active_target = BattlerContext(
                species=target_species,
                types=t_types,
                ability=target_ability,
                is_grounded=t_grounded,
            )

            bench_targets: List[BattlerContext] = []
            if target_bench_candidates:
                for b_spec in target_bench_candidates:
                    b_types = list(b_spec.get("types", ["Normal"]))
                    bench_targets.append(
                        BattlerContext(
                            species=b_spec.get("species", "Reserve"),
                            types=b_types,
                            ability=b_spec.get("ability", ""),
                            item=b_spec.get("item", ""),
                            hp_cur=float(b_spec.get("hp_cur", 100.0)),
                            is_grounded=bool(b_spec.get("is_grounded", True)),
                        )
                    )

            target_ctx = TargetSlotContext(active=active_target, bench=bench_targets)

        opp_battlers: List[BattlerContext] = []
        if opposing_active_battlers:
            for opp_data in opposing_active_battlers:
                opp_battlers.append(
                    BattlerContext(
                        species=opp_data.get("species", "Opponent"),
                        types=list(opp_data.get("types", ["Normal"])),
                        ability=opp_data.get("ability", ""),
                        hp_cur=float(opp_data.get("hp_cur", 100.0)),
                        is_mega=bool(opp_data.get("is_mega", False)),
                    )
                )
        elif opposing_abilities:
            for ab in opposing_abilities:
                opp_battlers.append(
                    BattlerContext(
                        species="OpponentMon",
                        ability=ab,
                        is_mega=("gengar" in ab.lower() or "shadow tag" in ab.lower()),
                    )
                )

        return self.evaluate_action(
            user=user_ctx,
            move_name=move_name,
            target=target_ctx,
            field_state=field_state,
            opposing_active_battlers=opp_battlers,
            opposing_active_moves=opposing_active_moves,
            ally_can_clear_terrain=ally_can_clear_terrain,
            is_switch_action=is_switch_action,
            move_pp=move_pp,
        )