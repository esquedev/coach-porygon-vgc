"""
Coach Porygon VGC — Logical Constraint & Risk-Reward Engine
(engine/tactics/logic_engine.py)

Evaluates candidate Pokémon battle actions through a dual-mode logical lens:

1. Hard Mechanical Invariants (Physical Failures — Probability 0%):
   Physical engine impossibilities such as Fake Out on active_turns > 1,
   priority moves into grounded foes under Psychic Terrain, and sleep moves
   failing under Electric or Misty Terrain.

2. Soft Tactical Constraints (Continuous High-Risk / High-Reward Continuum):
   Unconventional or high-variance lines such as consecutive Protect at roughly
   33% success probability on the second use and sharply lower success on later
   consecutive uses. The logic assigns continuous risk-reward priors instead of
   rigid binary pass/fail outcomes.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.turn_simulator import (
    BASE_STATS_DB,
    MOVE_DB,
    PROTECT_MOVES,
    get_type_effectiveness_breakdown,
)

PRIORITY_BLOCKING_ABILITIES = {"Armor Tail", "Queenly Majesty"}
SOUND_MOVES = {
    "Hyper Voice",
    "Parting Shot",
    "Bug Buzz",
    "Snarl",
    "Roar",
    "Disarming Voice",
}
SLEEP_MOVES = {"Hypnosis", "Yawn", "Sleep Powder", "Spore", "Grass Whistle"}
STATUS_ABSORBING_ABILITIES = {"Good as Gold"}
FIRE_ABSORBING_ABILITIES = {"Flash Fire"}
ELECTRIC_ABSORBING_ABILITIES = {"Lightning Rod", "Motor Drive", "Volt Absorb"}


@dataclass
class ConstraintResult:
    """Structured evaluation of a move or action by the logic engine."""

    is_mechanically_valid: bool
    risk_score: float  # 0.0 = safe, 1.0 = extreme risk
    upside_potential: float  # 0.0 = low upside, 1.0 = game-winning blowout
    classification: str
    reasons: List[str] = field(default_factory=list)
    recommended_prior_scale: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-like dictionary representation of this result."""
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
    Expert rule engine for evaluating game invariants, impossible move states,
    and high-risk / high-reward tactical lines in Regulation M-C doubles.
    """

    def __init__(self) -> None:
        """Initialize the constraint engine."""
        pass

    @staticmethod
    def _make_result(
        *,
        is_mechanically_valid: bool,
        risk_score: float,
        upside_potential: float,
        classification: str,
        reasons: Optional[List[str]] = None,
        recommended_prior_scale: float = 1.0,
    ) -> ConstraintResult:
        """Create a standardized ConstraintResult instance."""
        return ConstraintResult(
            is_mechanically_valid=is_mechanically_valid,
            risk_score=risk_score,
            upside_potential=upside_potential,
            classification=classification,
            reasons=list(reasons or []),
            recommended_prior_scale=recommended_prior_scale,
        )

    @staticmethod
    def _resolve_target_types(
        target_species: Optional[str],
        target_types: Optional[List[str]],
    ) -> List[str]:
        """Resolve the target's type list from explicit or fallback data."""
        if target_types:
            return list(target_types)
        if target_species:
            species_entry = BASE_STATS_DB.get(target_species, {})
            return list(species_entry.get("types", ["Normal"]))
        return ["Normal"]

    @staticmethod
    def _resolve_accuracy(
        move_name: str,
        move_data: Dict[str, Any],
        weather: str,
        user_ability: str,
        target_ability: str,
    ) -> float:
        """Resolve accuracy, including weather and ability-based modifiers."""
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
        """Resolve the effective priority value for a move in the current state."""
        priority = int(move_data.get("priority", 0))
        if user_ability == "Prankster" and m_cat == "Status":
            priority += 1
        elif move_name == "Grassy Glide" and terrain == "grassy":
            priority += 1
        return priority

    @staticmethod
    def _evaluate_protect_chain(
        protect_chain_count: int,
        move_name: str,
    ) -> Optional[ConstraintResult]:
        """
        Evaluate repeated Protect usage with a Pokémon-style probability decay.

        This is a tactical heuristic, not a strict legality rule. In official
        Pokémon behavior, each consecutive Protect use after the first reduces the
        success chance by roughly 1/3. Therefore, the second use is ~33%, the
        third is ~11%, the fourth is ~3.7%, and so on. This is modeled as a risk
        heuristic for AI prioritization.
        """
        if move_name not in PROTECT_MOVES:
            return None

        if protect_chain_count <= 0:
            return None

        success_probability = (1.0 / 3.0) ** protect_chain_count
        risk_score = 1.0 - success_probability

        if protect_chain_count == 1:
            return ConstraintResult(
                is_mechanically_valid=True,
                risk_score=0.67,
                upside_potential=0.85,
                classification="High_Risk_High_Reward",
                reasons=[
                    "Consecutive Protect is being used again; official probability decays to ~33% on the second use."
                ],
                recommended_prior_scale=0.40,
            )

        if protect_chain_count >= 2:
            return ConstraintResult(
                is_mechanically_valid=True,
                risk_score=min(0.97, max(0.89, round(risk_score, 3))),
                upside_potential=0.90,
                classification="High_Risk_High_Reward",
                reasons=[
                    f"Protect chain has reached {protect_chain_count} consecutive uses; success probability is ~{success_probability:.2%} and this line is extremely risky."
                ],
                recommended_prior_scale=0.10,
            )

        return None

    def prune_impossible_actions(
        self,
        candidate_actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Filter a list of candidate actions down to those that remain
        mechanically valid after evaluation.
        """
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
    ) -> ConstraintResult:
        """
        Evaluate a single move against physical invariants and tactical
        risk-reward profile.

        Parameters
        ----------
        slot_species:
            The species executing the move.
        move_name:
            The move being evaluated.
        target_species:
            The species targeted by the move, if present.
        active_turns:
            Number of active turns the user has already been active.
        field_state:
            Current battlefield state, including weather and terrain.
        was_protected_last_turn:
            Backward-compatible flag indicating the user protected on the previous turn.
        is_target_airborne:
            Whether the target is airborne at the moment of evaluation.
        user_ability:
            Ability of the user.
        target_ability:
            Ability of the target.
        target_types:
            Explicit target type list, if known.
        opposing_abilities:
            Abilities on the opposing side that may affect move validity.
        is_user_grounded:
            Whether the user is grounded.
        is_target_grounded:
            Explicit grounded state for the target, if known.
        protect_chain_count:
            Number of consecutive Protect uses already used in the current chain.

        Returns
        -------
        ConstraintResult
            An object describing the move's mechanical validity, risk, upside,
            and recommended prior weighting.
        """
        field = field_state or {}
        weather = (field.get("weather") or "").lower()
        terrain = (field.get("terrain") or "").lower()
        move_data = MOVE_DB.get(move_name, {})

        if protect_chain_count < 0:
            protect_chain_count = 0
        if was_protected_last_turn and protect_chain_count == 0:
            protect_chain_count = 1

        if move_name in PROTECT_MOVES:
            protect_result = self._evaluate_protect_chain(
                protect_chain_count=protect_chain_count,
                move_name=move_name,
            )
            if protect_result is not None:
                return protect_result

        target_grounded = (
            is_target_grounded if is_target_grounded is not None else not is_target_airborne
        )
        if field.get("gravity", False):
            target_grounded = True

        m_type = move_data.get("type", "Normal")
        m_cat = move_data.get("cat", "Status")

        # 1. Physical invariant: Fake Out / First Impression may only be used on turn 1.
        if move_name in ("Fake Out", "First Impression") and active_turns > 1:
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"{move_name} fails physically when active turns ({active_turns}) > 1."],
                recommended_prior_scale=0.001,
            )

        m_prio = self._resolve_move_priority(
            move_name=move_name,
            move_data=move_data,
            user_ability=user_ability,
            terrain=terrain,
            m_cat=m_cat,
        )

        # 2. Hard mechanical invariants: priority blocking and terrain interactions.
        if m_prio > 0 and opposing_abilities:
            if any(ability in PRIORITY_BLOCKING_ABILITIES for ability in opposing_abilities):
                return self._make_result(
                    is_mechanically_valid=False,
                    risk_score=1.0,
                    upside_potential=0.0,
                    classification="Mechanically_Invalid",
                    reasons=[
                        f"Priority move {move_name} blocked by opposing Armor Tail or Queenly Majesty."
                    ],
                    recommended_prior_scale=0.001,
                )

        if m_prio > 0 and terrain == "psychic":
            if target_species:
                if target_grounded:
                    return self._make_result(
                        is_mechanically_valid=False,
                        risk_score=1.0,
                        upside_potential=0.0,
                        classification="Mechanically_Invalid",
                        reasons=[
                            f"Priority move {move_name} (priority +{m_prio}) is completely blocked by Psychic Terrain on grounded {target_species}."
                        ],
                        recommended_prior_scale=0.001,
                    )
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=0.15,
                    upside_potential=0.75,
                    classification="Calculated_Risk",
                    reasons=[
                        f"Target {target_species} is airborne and exempt from Psychic Terrain; priority {move_name} connects cleanly."
                    ],
                    recommended_prior_scale=1.0,
                )

        if user_ability == "Prankster" and m_cat == "Status":
            resolved_target_types = self._resolve_target_types(target_species, target_types)
            if resolved_target_types and "Dark" in resolved_target_types:
                return self._make_result(
                    is_mechanically_valid=False,
                    risk_score=1.0,
                    upside_potential=0.0,
                    classification="Mechanically_Invalid",
                    reasons=[
                        f"Prankster {move_name} fails automatically against Dark-type {target_species}."
                    ],
                    recommended_prior_scale=0.001,
                )

        if (move_name in SOUND_MOVES or move_data.get("is_sound")) and target_ability == "Soundproof":
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"Sound move {move_name} is nullified by Soundproof."],
                recommended_prior_scale=0.001,
            )

        if m_cat == "Status" and target_ability in STATUS_ABSORBING_ABILITIES:
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"Status move {move_name} is blocked by Good as Gold."],
                recommended_prior_scale=0.001,
            )

        if m_type == "Fire" and target_ability in FIRE_ABSORBING_ABILITIES:
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"Fire move {move_name} is nullified by Flash Fire."],
                recommended_prior_scale=0.001,
            )

        if move_name in SLEEP_MOVES and target_grounded and terrain in ("electric", "misty"):
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"Sleep move {move_name} fails against grounded target in {terrain} terrain."],
                recommended_prior_scale=0.001,
            )

        # 3. Physical invariant vs hard read: Ground attack into airborne target.
        if m_type == "Ground" and m_cat != "Status" and move_name != "Thousand Arrows":
            if is_target_airborne:
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=0.80,
                    upside_potential=0.90,
                    classification="High_Risk_High_Reward",
                    reasons=[
                        f"Ground attack {move_name} deals 0x into airborne {target_species}; only viable as an aggressive hard read on switch-in."
                    ],
                    recommended_prior_scale=0.20,
                )

        # 4. Accuracy risk pre-computation.
        acc_val = self._resolve_accuracy(
            move_name=move_name,
            move_data=move_data,
            weather=weather,
            user_ability=user_ability,
            target_ability=target_ability,
        )
        is_inaccurate = acc_val < 85.0
        acc_risk = round((100.0 - acc_val) / 100.0, 3) if is_inaccurate else 0.0

        # 5. Type effectiveness breakdown and high-risk targeting.
        if target_species and m_cat != "Status":
            target_types = self._resolve_target_types(target_species, target_types)
            scrappy = user_ability in ("Scrappy", "Mind's Eye")
            breakdown = get_type_effectiveness_breakdown(
                m_type,
                target_types,
                move_name=move_name,
                scrappy=scrappy,
            )
            eff = breakdown["multiplier"]

            if eff == 0.0:
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=0.85,
                    upside_potential=0.85,
                    classification="High_Risk_High_Reward",
                    reasons=[
                        f"{move_name} deals 0.0x immunity into active {target_species}; viable solely as prediction read on opposing switch."
                    ],
                    recommended_prior_scale=0.15,
                )

            if eff <= 0.25:
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=0.55,
                    upside_potential=0.60,
                    classification="Calculated_Risk",
                    reasons=[
                        f"{move_name} hits {target_species} into double resistance (0.25x); sub-optimal unless securing a chip KO or targeting switch."
                    ],
                    recommended_prior_scale=0.50,
                )

            reasons: List[str] = []
            if is_inaccurate:
                reasons.append(f"{move_name} carries accuracy risk ({acc_val}% nominal hit rate).")

            if eff >= 4.0:
                reasons.append(f"{move_name} exploits a devastating 4.0x double weakness on {target_species}.")
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
                reasons.append(f"{move_name} is super effective (2.0x) against {target_species}.")
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

        # Default standard safe execution.
        return self._make_result(
            is_mechanically_valid=True,
            risk_score=0.10,
            upside_potential=0.70,
            classification="Deterministic_Safe",
            reasons=[f"Standard valid execution of {move_name}."],
            recommended_prior_scale=1.0,
        )
