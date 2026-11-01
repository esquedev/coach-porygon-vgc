# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Logical Constraint & Risk-Reward Engine (engine/tactics/logic_engine.py)

Evaluates candidate Pokémon battle actions through a dual-mode logical lens:
1. Hard Mechanical Invariants (Physical Failures — Probability 0%):
   Physical engine impossibilities (Fake Out on active_turns > 1, priority into grounded foes
   under Psychic Terrain, Hypnosis under Electric Terrain).
2. Soft Tactical Constraints (Continuous High-Risk / High-Reward Continuum):
   Unconventional or high-variance lines (consecutive Protect at ~33% success, dry switches,
   attacks into apparent resistances anticipating a switch-in). Assigns continuous risk-reward
   prior weights rather than binary 0/100 hard deletion.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from engine.turn_simulator import (
    BASE_STATS_DB,
    MOVE_DB,
    PROTECT_MOVES,
    TYPE_CHART,
    get_type_effectiveness,
    get_type_effectiveness_breakdown,
)


@dataclass
class ConstraintResult:
    """Represents the structured evaluation of an action by the Logical Constraint Engine."""

    is_mechanically_valid: bool
    risk_score: float  # 0.0 (Safe) to 1.0 (Extreme risk)
    upside_potential: float  # 0.0 (Minimal) to 1.0 (Game-winning blowout)
    classification: str  # Deterministic_Safe, Calculated_Risk, High_Risk_High_Reward, Mechanically_Invalid
    reasons: List[str] = field(default_factory=list)
    recommended_prior_scale: float = 1.0  # Multiplier applied to tactical_prior in ActionPruner

    def to_dict(self) -> Dict[str, Any]:
        """Convert constraint result to a dictionary representation."""
        return {
            "is_mechanically_valid": self.is_mechanically_valid,
            "risk_score": round(self.risk_score, 3),
            "upside_potential": round(self.upside_potential, 3),
            "classification": self.classification,
            "reasons": list(self.reasons),
            "recommended_prior_scale": round(self.recommended_prior_scale, 3),
        }


class LogicalConstraintEngine:
    """
    Expert rule engine evaluating game invariants, cartridge failure preconditions,
    and high-risk / high-reward tactical profiles in Regulation M-C doubles.
    """

    def __init__(self) -> None:
        """Initialize LogicalConstraintEngine."""
        pass

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
    ) -> ConstraintResult:
        """
        Evaluate single move execution against physical invariants and risk-reward profile.

        Args:
            slot_species: Species executing the action.
            move_name: Name of the move.
            target_species: Species being targeted, if any.
            active_turns: Number of continuous turns the user slot has been active.
            field_state: Dictionary containing 'weather', 'terrain', etc.
            was_protected_last_turn: Whether the user slot executed Protect successfully last turn.
            is_target_airborne: Whether the target is airborne (Flying type, Levitate, Air Balloon).
            user_ability: Ability of the executing slot.
            target_ability: Revealed or scouted ability of the target.

        Returns:
            Populated ConstraintResult with validity, risk score, upside, and classification.
        """
        f = field_state or {}
        weather = (f.get("weather") or "").lower()
        terrain = (f.get("terrain") or "").lower()
        move_data = MOVE_DB.get(move_name, {})

        # 1. Physical Invariant: Fake Out / First Impression Turn 1 Restriction
        if move_name in ("Fake Out", "First Impression") and active_turns > 1:
            return ConstraintResult(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"{move_name} fails physically when active turns ({active_turns}) > 1."],
                recommended_prior_scale=0.001,
            )

        # 2. Soft Constraint: Consecutive Protect Execution (High-Risk, High-Reward)
        if move_name in PROTECT_MOVES and was_protected_last_turn:
            return ConstraintResult(
                is_mechanically_valid=True,
                risk_score=0.67,  # ~33% success chance
                upside_potential=0.85,
                classification="High_Risk_High_Reward",
                reasons=[
                    "Consecutive Protect carries ~33% success probability; viable as high-risk/high-reward line under lethal threat."
                ],
                recommended_prior_scale=0.40,
            )

        # 3. Physical Invariant: Priority Move into Grounded Target under Psychic Terrain
        m_prio = int(move_data.get("priority", 0))
        if user_ability == "Prankster" and move_data.get("cat") == "Status":
            m_prio += 1
        elif move_name == "Grassy Glide" and terrain == "grassy":
            m_prio += 1

        if m_prio > 0 and terrain == "psychic":
            if target_species:
                if not is_target_airborne:
                    return ConstraintResult(
                        is_mechanically_valid=False,
                        risk_score=1.0,
                        upside_potential=0.0,
                        classification="Mechanically_Invalid",
                        reasons=[
                            f"Priority move {move_name} (priority +{m_prio}) is completely blocked by Psychic Terrain on grounded {target_species}."
                        ],
                        recommended_prior_scale=0.001,
                    )
                else:
                    return ConstraintResult(
                        is_mechanically_valid=True,
                        risk_score=0.15,
                        upside_potential=0.75,
                        classification="Calculated_Risk",
                        reasons=[
                            f"Target {target_species} is airborne and exempt from Psychic Terrain; priority {move_name} connects cleanly."
                        ],
                        recommended_prior_scale=1.0,
                    )

        # 4. Physical Invariant vs Hard Read: Ground Attack into Airborne Target
        m_type = move_data.get("type", "Normal")
        m_cat = move_data.get("cat", "Status")
        if m_type == "Ground" and m_cat != "Status" and move_name != "Thousand Arrows":
            if is_target_airborne:
                return ConstraintResult(
                    is_mechanically_valid=True,
                    risk_score=0.80,
                    upside_potential=0.90,  # If opponent switches to grounded partner, massive upside
                    classification="High_Risk_High_Reward",
                    reasons=[
                        f"Ground attack {move_name} deals 0x into airborne {target_species}; only viable as an aggressive hard read on switch-in."
                    ],
                    recommended_prior_scale=0.20,
                )

        # 5. Accuracy Risk Pre-computation
        raw_acc = move_data.get("accuracy", 100)
        try:
            acc_val = float(raw_acc) if raw_acc not in (True, None, "--") else 100.0
        except (ValueError, TypeError):
            acc_val = 100.0

        if user_ability == "No Guard" or target_ability == "No Guard":
            acc_val = 100.0
        elif weather == "rain" and move_name in ("Thunder", "Hurricane", "Bleakwind Storm"):
            acc_val = 100.0
        elif weather == "snow" and move_name == "Blizzard":
            acc_val = 100.0

        is_inaccurate = acc_val < 85.0
        acc_risk = round((100.0 - acc_val) / 100.0, 3) if is_inaccurate else 0.0

        # 6. Type Effectiveness Breakdown & High-Risk Targeting
        if target_species and m_cat != "Status":
            tgt_entry = BASE_STATS_DB.get(target_species, {})
            tgt_types = list(tgt_entry.get("types", ["Normal"]))
            scrappy = user_ability in ("Scrappy", "Mind's Eye")
            breakdown = get_type_effectiveness_breakdown(m_type, tgt_types, move_name=move_name, scrappy=scrappy)
            eff = breakdown["multiplier"]

            if eff == 0.0:
                return ConstraintResult(
                    is_mechanically_valid=True,
                    risk_score=0.85,
                    upside_potential=0.85,
                    classification="High_Risk_High_Reward",
                    reasons=[
                        f"{move_name} deals 0.0x immunity into active {target_species}; viable solely as prediction read on opposing switch."
                    ],
                    recommended_prior_scale=0.15,
                )
            elif eff <= 0.25:
                return ConstraintResult(
                    is_mechanically_valid=True,
                    risk_score=0.55,
                    upside_potential=0.60,
                    classification="Calculated_Risk",
                    reasons=[
                        f"{move_name} hits {target_species} into double resistance (0.25x); sub-optimal unless securing a chip KO or targeting switch."
                    ],
                    recommended_prior_scale=0.50,
                )

            reasons = []
            if is_inaccurate:
                reasons.append(f"{move_name} carries accuracy risk ({acc_val}% nominal hit rate).")

            if eff >= 4.0:
                reasons.append(f"{move_name} exploits a devastating 4.0x double weakness on {target_species}.")
                prior_scale = 1.35 * (acc_val / 100.0)
                classification = "Calculated_Risk" if is_inaccurate else "Deterministic_Safe"
                return ConstraintResult(
                    is_mechanically_valid=True,
                    risk_score=max(0.05, acc_risk),
                    upside_potential=0.95,
                    classification=classification,
                    reasons=reasons,
                    recommended_prior_scale=round(prior_scale, 3),
                )
            elif eff >= 2.0:
                reasons.append(f"{move_name} is super effective (2.0x) against {target_species}.")
                prior_scale = 1.20 * (acc_val / 100.0)
                classification = "Calculated_Risk" if is_inaccurate else "Deterministic_Safe"
                return ConstraintResult(
                    is_mechanically_valid=True,
                    risk_score=max(0.10, acc_risk),
                    upside_potential=0.85,
                    classification=classification,
                    reasons=reasons,
                    recommended_prior_scale=round(prior_scale, 3),
                )

        if is_inaccurate:
            return ConstraintResult(
                is_mechanically_valid=True,
                risk_score=acc_risk,
                upside_potential=0.80,
                classification="Calculated_Risk",
                reasons=[f"{move_name} carries accuracy risk ({acc_val}% nominal hit rate)."],
                recommended_prior_scale=round(acc_val / 100.0, 3),
            )

        # Default standard safe execution
        return ConstraintResult(
            is_mechanically_valid=True,
            risk_score=0.10,
            upside_potential=0.70,
            classification="Deterministic_Safe",
            reasons=[f"Standard valid execution of {move_name}."],
            recommended_prior_scale=1.0,
        )


# Backward-compatible and semantic alias
LogicEngine = LogicalConstraintEngine
