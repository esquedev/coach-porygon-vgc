# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Logical Constraint, Action Pruner & Risk-Reward Engine
==========================================================================

Evaluates candidate Pokémon VGC 4v4 Doubles (Regulation M-C) battle actions through
a dual-mode logical lens, operating both at the symbolic DuckDB level and directly
as vectorized `26x26` tensor masks on `[24]`, `[8, 87]`, and `[8, 4, 59]` board states:

1. **Hard Mechanical Invariants (Physical Failures — Probability 0%, Pruned from Tensor Batch)**:
   - `Fake Out`, `First Impression` when `active_turns >= 1` (0-indexed after lead/switch).
   - Priority moves (`priority > 0`, `Prankster` status, `Grassy Glide` in Grassy Terrain) targeting
     opposing slots when `Armor Tail` / `Queenly Majesty` is active on the opposing side,
     or into grounded foes under `Psychic Terrain`.
   - `Prankster` status moves into `Dark`-type opposing targets.
   - Sound moves into `Soundproof`, status moves into `Good as Gold`, Fire moves into `Flash Fire`,
     Water moves into `Water Absorb` / `Dry Skin`, Electric moves into `Lightning Rod` / `Volt Absorb` /
     `Motor Drive`, Grass moves into `Sap Sipper`, Ground moves into `Earth Eater`.
   - Sleep moves (`Spore`, `Sleep Powder`, `Hypnosis`, `Yawn`, `Sing`)
     into grounded targets under `Electric Terrain` or `Misty Terrain`.
   - Choice-lock (`Choice Scarf`), `Encore`, and `Taunt`.
   - Single-Mega exclusivity (`M[12:24, 12:24] = 0`) and same-bench switch collision (`M[24, 24] = M[25, 25] = 0`).

2. **Soft Tactical Constraints (Continuous Risk / Upside Continuum & Tensor Priors)**:
   - Consecutive `Protect` / `Detect` / `Spiky Shield` / `King's Shield` / `Baneful Bunker`
     decay (`(1/3)^k` success probability -> `risk_score = 0.67` on 2nd use, `0.89+` on 3rd+ use).
   - Sub-85% nominal accuracy risk weighting (modified dynamically by `No Guard`, Rain sure-hit, Snow sure-hit).
   - Type effectiveness & immunity hard-read classification (`0.0x` immunity on active slot only viable as
     a switch-read; `0.25x` double-resist; `2.0x` / `4.0x` super-effective upside scaling).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from ..db_registry import VGCDataRegistry, get_registry
from .compiler import (
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
    CompiledBattleState,
    _parse_structured_field,
)
from .schema_and_tables import (
    AbilityID,
    BilinearLookupTables,
    FieldIdx,
    HAS_TORCH,
    ItemID,
    MOVES_PER_MON,
    MonIdx,
    MoveIdx,
    NUM_TYPES,
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
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray

PRIORITY_BLOCKING_ABILITIES = {"Armor Tail", "Queenly Majesty"}
SOUND_MOVES = {
    "Hyper Voice",
    "Parting Shot",
    "Bug Buzz",
    "Snarl",
    "Roar",
    "Alluring Voice",
    "Torch Song",
    "Boomburst",
    "Perish Song",
    "Clangorous Soul",
}
SLEEP_MOVES = {"Hypnosis", "Yawn", "Sleep Powder", "Spore", "Sing"}
PROTECT_MOVES = {
    "Protect",
    "Detect",
    "Spiky Shield",
    "King's Shield",
    "Baneful Bunker",
    "Endure",
    "Wide Guard",
    "Quick Guard",
}
STATUS_ABSORBING_ABILITIES = {"Good as Gold"}
FIRE_ABSORBING_ABILITIES = {"Flash Fire"}
ELECTRIC_ABSORBING_ABILITIES = {"Lightning Rod", "Motor Drive", "Volt Absorb"}
WATER_ABSORBING_ABILITIES = {"Water Absorb", "Dry Skin"}
GRASS_ABSORBING_ABILITIES = {"Sap Sipper"}
GROUND_ABSORBING_ABILITIES = {"Levitate", "Earth Eater", "Eelevate"}


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


@dataclass(frozen=True)
class PrunedSideActionTensorMask:
    """Vectorized `26x26` logical constraint and pruning output for a trainer side (`trainer_1` or `trainer_2`).

    Attributes:
        trainer_id: `'trainer_1'` or `'trainer_2'`.
        valid_mask_26x26: `[26, 26]` binary mask (`1.0` = mechanically valid, `0.0` = pruned).
        prior_matrix_26x26: `[26, 26]` recommended tactical prior scale matrix.
        risk_matrix_26x26: `[26, 26]` composite risk score matrix in `[0.0, 1.0]`.
        upside_matrix_26x26: `[26, 26]` composite upside potential matrix in `[0.0, 1.0]`.
        pruned_choices: `[N_valid, 2]` integer coordinates `(choice_slot_a, choice_slot_b)` of
            all surviving legal joint actions for this trainer.
    """

    trainer_id: str
    valid_mask_26x26: TensorOrArray
    prior_matrix_26x26: TensorOrArray
    risk_matrix_26x26: TensorOrArray
    upside_matrix_26x26: TensorOrArray
    pruned_choices: TensorOrArray


class LogicalConstraintEngine:
    """Expert rule & tensor pruning engine for evaluating game invariants, impossible move states,
    and high-risk / high-reward tactical lines in Regulation M-C doubles.
    """

    def __init__(
        self,
        registry: Optional[VGCDataRegistry] = None,
        tables: Optional[BilinearLookupTables] = None,
    ) -> None:
        """Initialize the constraint engine with in-memory DuckDB registry and bilinear type tables."""
        self.registry: VGCDataRegistry = registry or get_registry()
        self.tables: BilinearLookupTables = tables or build_bilinear_lookup_tables(device="cpu")
        self._type_chart_np: np.ndarray = (
            self.tables.m_type_chart.detach().cpu().numpy()
            if (HAS_TORCH and hasattr(self.tables.m_type_chart, "detach"))
            else np.asarray(self.tables.m_type_chart)
        )

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

    def _resolve_target_types(
        self,
        target_species: Optional[str],
        target_types: Optional[List[str]],
    ) -> List[str]:
        """Resolve the target's type list from explicit list or in-memory DuckDB `pokedex` view."""
        if target_types:
            return list(target_types)
        if target_species:
            dex_entry = self.registry.get_pokemon(target_species)
            if dex_entry and dex_entry.get("types"):
                parsed = _parse_structured_field(dex_entry["types"])
                if isinstance(parsed, list) and parsed:
                    return [str(t) for t in parsed]
        return ["Normal"]

    def _lookup_move_data(self, move_name: str) -> Dict[str, Any]:
        """Fetch move schema from in-memory DuckDB `moves` view."""
        entry = self.registry.get_move(move_name)
        if not entry:
            return {}
        flags_obj = _parse_structured_field(entry.get("flags"))
        flags = flags_obj if isinstance(flags_obj, dict) else {}
        return {
            "name": entry.get("name", move_name),
            "type": entry.get("type", "Normal"),
            "cat": entry.get("category", "Status"),
            "accuracy": _parse_structured_field(entry.get("accuracy")),
            "priority": int(entry.get("priority") or 0),
            "is_sound": bool(flags.get("sound")) or (move_name in SOUND_MOVES),
            "status": entry.get("status"),
            "is_charge": bool(flags.get("charge")),
        }

    def _compute_type_effectiveness(
        self,
        move_type: str,
        target_types: List[str],
        move_name: str = "",
        scrappy: bool = False,
    ) -> float:
        """Compute exact cartridge type effectiveness multiplier using `BilinearLookupTables`."""
        m_idx = TYPE_TO_IDX.get(str(move_name and move_type or "Normal").lower(), 0)
        mult = 1.0
        for t_str in target_types:
            t_lower = str(t_str).lower()
            t_idx = TYPE_TO_IDX.get(t_lower, 0)
            eff = float(self._type_chart_np[m_idx, t_idx])
            if scrappy and t_lower == "ghost" and str(move_type).lower() in ("normal", "fighting"):
                eff = 1.0
            if move_name == "Freeze-Dry" and t_lower == "water":
                eff = 2.0
            mult *= eff
        return mult

    @staticmethod
    def _resolve_accuracy(
        move_name: str,
        move_data: Dict[str, Any],
        weather: str,
        user_ability: str,
        target_ability: str,
    ) -> float:
        """Resolve nominal accuracy in `[0.0, 100.0]`, including weather and ability modifiers."""
        raw_acc = move_data.get("accuracy", 100)
        try:
            acc_val = float(raw_acc) if raw_acc not in (True, "true", "True", None, "--") else 100.0
            if acc_val <= 1.01:
                acc_val = min(100.0, acc_val * 100.0)
        except (TypeError, ValueError):
            acc_val = 100.0

        if user_ability == "No Guard" or target_ability == "No Guard":
            return 100.0
        if weather == "rain" and move_name in ("Thunder", "Hurricane"):
            return 100.0
        if weather == "sun" and move_name in ("Thunder", "Hurricane"):
            return 50.0
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
        """Resolve effective priority value for a move in the current state."""
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
        """Evaluate repeated Protect usage with official `(1/3)^k` probability decay."""
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
                recommended_prior_scale=0.33,
            )

        return ConstraintResult(
            is_mechanically_valid=True,
            risk_score=min(0.97, max(0.89, round(risk_score, 3))),
            upside_potential=0.90,
            classification="High_Risk_High_Reward",
            reasons=[
                f"Protect chain has reached {protect_chain_count} consecutive uses; "
                f"success probability is ~{success_probability:.2%} and this line is extremely risky."
            ],
            recommended_prior_scale=0.11,
        )

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
        """Evaluate a single move against physical invariants and tactical risk-reward profile."""
        field_dict = field_state or {}
        weather = str(field_dict.get("weather") or "").lower()
        terrain = str(field_dict.get("terrain") or "").lower()
        move_data = self._lookup_move_data(move_name)

        # Dynamic Cloud Nine weather suppression check
        all_abilities = [user_ability, target_ability] + (opposing_abilities or [])
        has_cloud_nine = any(str(ab).lower() in ("cloud nine", "cloudnine") for ab in all_abilities)
        if has_cloud_nine:
            weather = "clear"

        # Dynamic Weather Ball typing adaptation
        if move_name == "Weather Ball":
            if weather == "sun":
                move_data = dict(move_data, type="Fire")
            elif weather == "rain":
                move_data = dict(move_data, type="Water")
            elif weather == "sand":
                move_data = dict(move_data, type="Rock")
            elif weather == "snow":
                move_data = dict(move_data, type="Ice")
            else:
                move_data = dict(move_data, type="Normal")

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
        if field_dict.get("gravity", False):
            target_grounded = True

        m_type = str(move_data.get("type", "Normal"))
        m_cat = str(move_data.get("cat", "Status"))

        # 1. Physical invariant: Fake Out / First Impression only on first active turn
        if move_name in ("Fake Out", "First Impression") and active_turns > 1:
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"{move_name} fails physically when active turns ({active_turns}) > 1."],
                recommended_prior_scale=0.0,
            )

        # Two-turn charging move evaluation on Turn 1 (deals 0 damage on charge turn)
        if move_data.get("is_charge"):
            if move_name in ("Solar Beam", "Solar Blade"):
                if weather != "sun":
                    cloud_note = " (suppressed by Cloud Nine)" if has_cloud_nine else ""
                    return self._make_result(
                        is_mechanically_valid=True,
                        risk_score=0.95,
                        upside_potential=0.10,
                        classification="High_Risk",
                        reasons=[
                            f"{move_name} requires a charging turn without Harsh Sunlight{cloud_note}; deals 0 damage on Turn 1."
                        ],
                        recommended_prior_scale=0.05,
                    )
            elif move_name == "Electro Shot":
                if weather != "rain":
                    cloud_note = " (suppressed by Cloud Nine)" if has_cloud_nine else ""
                    return self._make_result(
                        is_mechanically_valid=True,
                        risk_score=0.90,
                        upside_potential=0.20,
                        classification="High_Risk",
                        reasons=[
                            f"Electro Shot requires a charging turn without Rain{cloud_note}; deals 0 damage on Turn 1."
                        ],
                        recommended_prior_scale=0.10,
                    )
            else:
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=0.90,
                    upside_potential=0.25,
                    classification="High_Risk",
                    reasons=[
                        f"{move_name} requires a charging turn on Turn 1; deals 0 damage on Turn 1."
                    ],
                    recommended_prior_scale=0.10,
                )

        m_prio = self._resolve_move_priority(
            move_name=move_name,
            move_data=move_data,
            user_ability=user_ability if is_user_grounded or move_name != "Grassy Glide" else "",
            terrain=terrain if is_user_grounded else "none",
            m_cat=m_cat,
        )

        # 2. Hard mechanical invariants: priority blocking & Psychic Terrain
        if m_prio > 0 and opposing_abilities:
            if any(ability in PRIORITY_BLOCKING_ABILITIES for ability in opposing_abilities):
                return self._make_result(
                    is_mechanically_valid=False,
                    risk_score=1.0,
                    upside_potential=0.0,
                    classification="Mechanically_Invalid",
                    reasons=[
                        f"Priority move {move_name} blocked by opposing Armor Tail, Queenly Majesty, or Dazzling."
                    ],
                    recommended_prior_scale=0.0,
                )

        if m_prio > 0 and terrain == "psychic" and target_species:
            if target_grounded:
                return self._make_result(
                    is_mechanically_valid=False,
                    risk_score=1.0,
                    upside_potential=0.0,
                    classification="Mechanically_Invalid",
                    reasons=[
                        f"Priority move {move_name} (+{m_prio}) is blocked by Psychic Terrain on grounded {target_species}."
                    ],
                    recommended_prior_scale=0.0,
                )
            return self._make_result(
                is_mechanically_valid=True,
                risk_score=0.15,
                upside_potential=0.75,
                classification="Calculated_Risk",
                reasons=[
                    f"Target {target_species} is airborne and exempt from Psychic Terrain; priority {move_name} connects."
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
                    recommended_prior_scale=0.0,
                )

        if (move_name in SOUND_MOVES or move_data.get("is_sound")) and target_ability == "Soundproof":
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"Sound move {move_name} is nullified by Soundproof."],
                recommended_prior_scale=0.0,
            )

        if m_cat == "Status" and target_ability in STATUS_ABSORBING_ABILITIES:
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"Status move {move_name} is blocked by Good as Gold."],
                recommended_prior_scale=0.0,
            )

        if m_type == "Fire" and target_ability in FIRE_ABSORBING_ABILITIES:
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"Fire move {move_name} is nullified by {target_ability}."],
                recommended_prior_scale=0.0,
            )

        if (move_name in SLEEP_MOVES or move_data.get("status") == "slp") and target_grounded and terrain in ("electric", "misty"):
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"Sleep move {move_name} fails against grounded target in {terrain} terrain."],
                recommended_prior_scale=0.0,
            )

        # 3. Ground attack into airborne target
        if m_type == "Ground" and m_cat != "Status" and move_name != "Thousand Arrows":
            if not target_grounded:
                return self._make_result(
                    is_mechanically_valid=True,
                    risk_score=0.80,
                    upside_potential=0.90,
                    classification="High_Risk_High_Reward",
                    reasons=[
                        f"Ground attack {move_name} deals 0x into airborne {target_species}; only viable as hard read on switch."
                    ],
                    recommended_prior_scale=0.20,
                )

        # 4. Accuracy risk
        acc_val = self._resolve_accuracy(
            move_name=move_name,
            move_data=move_data,
            weather=weather,
            user_ability=user_ability,
            target_ability=target_ability,
        )
        is_inaccurate = acc_val < 85.0
        acc_risk = round((100.0 - acc_val) / 100.0, 3) if is_inaccurate else 0.0

        # 5. Type effectiveness breakdown
        if target_species and m_cat != "Status":
            resolved_types = self._resolve_target_types(target_species, target_types)
            scrappy = user_ability == "Scrappy"
            eff = self._compute_type_effectiveness(
                m_type,
                resolved_types,
                move_name=move_name,
                scrappy=scrappy,
            )

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
                        f"{move_name} hits {target_species} into double resistance (0.25x)."
                    ],
                    recommended_prior_scale=0.50,
                )

            reasons: List[str] = []
            if is_inaccurate:
                reasons.append(f"{move_name} carries accuracy risk ({acc_val:.0f}% nominal hit rate).")

            if eff >= 4.0:
                reasons.append(f"{move_name} exploits a 4.0x double weakness on {target_species}.")
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
                reasons=[f"{move_name} carries accuracy risk ({acc_val:.0f}% nominal hit rate)."],
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

    def evaluate_candidate_action(
        self,
        move_name: str,
        user_species: str = "",
        user_types: Optional[List[str]] = None,
        user_ability: str = "",
        target_species: Optional[str] = None,
        target_types: Optional[List[str]] = None,
        target_ability: str = "",
        weather: Optional[str] = None,
        opposing_abilities: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ConstraintResult:
        """Convenience wrapper for candidate action evaluation matching the symbolic constraint API."""
        field_state = {"weather": weather} if weather else None
        return self.evaluate_slot_action(
            slot_species=user_species,
            move_name=move_name,
            target_species=target_species,
            field_state=field_state,
            user_ability=user_ability,
            target_ability=target_ability,
            target_types=target_types,
            opposing_abilities=opposing_abilities,
            **kwargs,
        )

    # =========================================================================
    # VECTORIZED TENSOR MASK & ACTION PRUNER (26x26 PER TRAINER SIDE)
    # =========================================================================

    def _compute_slot_26_constraints_numpy(
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
        prune_zero_effect_attacks_when_no_bench: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Compute `[26]` validity, prior, risk, and upside vectors for a single active slot."""
        valid_26 = np.zeros((26,), dtype=np.float32)
        prior_26 = np.zeros((26,), dtype=np.float32)
        risk_26 = np.ones((26,), dtype=np.float32)
        upside_26 = np.zeros((26,), dtype=np.float32)

        user_vec = p_np[user_slot]
        if user_vec[MonIdx.ALIVE_FLAG] <= 0.0:
            return valid_26, prior_26, risk_26, upside_26

        # Hard Mechanical Invariant: Forced Recharge Turn (Hyper Beam, Giga Impact, Blast Burn, etc.)
        # Pokémon cannot click any move, cannot Mega Evolve, and cannot voluntarily switch out.
        if user_vec[MonIdx.MUST_RECHARGE] > 0.5:
            valid_26[0] = 1.0
            prior_26[0] = 1.0
            risk_26[0] = 0.0
            upside_26[0] = 0.0
            return valid_26, prior_26, risk_26, upside_26

        moves_4 = m_np[user_slot]  # [4, 59]
        partner_vec = p_np[partner_slot]
        opp_a_vec = p_np[opp_a_slot]
        opp_b_vec = p_np[opp_b_slot]

        # Check if opponent has any alive bench Pokémon (if not, a 0x immunity attack cannot even be a switch read!)
        opp_bench1_slot = SLOT_TRAINER_2_BENCH1 if opp_a_slot == SLOT_TRAINER_2_A else SLOT_TRAINER_1_BENCH1
        opp_bench2_slot = SLOT_TRAINER_2_BENCH2 if opp_a_slot == SLOT_TRAINER_2_A else SLOT_TRAINER_1_BENCH2
        opp_has_alive_bench = (
            p_np[opp_bench1_slot, MonIdx.ALIVE_FLAG] > 0.0
            or p_np[opp_bench2_slot, MonIdx.ALIVE_FLAG] > 0.0
        )

        w_onehot = f_np[FieldIdx.WEATHER_START:FieldIdx.WEATHER_END]
        t_onehot = f_np[FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END]
        is_rain = float(w_onehot[WEATHER_TO_IDX["rain"]])
        is_snow = float(w_onehot[WEATHER_TO_IDX["snow"]])
        is_sun = float(w_onehot[WEATHER_TO_IDX["sun"]])
        is_sand = float(w_onehot[WEATHER_TO_IDX["sand"]])

        # Dynamic Cloud Nine check across active slots
        is_cloud_nine = any(
            vec[MonIdx.ALIVE_FLAG] > 0.0 and int(round(float(vec[MonIdx.ABILITY_ID]))) == AbilityID.CLOUD_NINE
            for vec in (user_vec, partner_vec, opp_a_vec, opp_b_vec)
        )
        if is_cloud_nine:
            is_rain = 0.0
            is_snow = 0.0
            is_sun = 0.0
            is_sand = 0.0
        is_psychic_terrain = float(t_onehot[TERRAIN_TO_IDX["psychic"]])
        is_grassy_terrain = float(t_onehot[TERRAIN_TO_IDX["grassy"]])
        is_elec_or_misty_terrain = float(
            t_onehot[TERRAIN_TO_IDX["electric"]] + t_onehot[TERRAIN_TO_IDX["misty"]]
        )
        gravity_active = 1.0 if f_np[FieldIdx.GRAVITY_TURNS] > 0.0 else 0.0

        active_turns = float(user_vec[MonIdx.ACTIVE_TURNS])
        protect_count = float(user_vec[MonIdx.PROTECT_COUNTER])
        taunt_active = 1.0 if user_vec[MonIdx.TAUNT_TURNS] > 0.0 else 0.0
        throat_chop_active = 1.0 if user_vec[MonIdx.THROAT_CHOP_TURNS] > 0.0 else 0.0
        charged_move_idx = int(round(float(user_vec[MonIdx.CHARGED_MOVE_IDX]))) - 1  # -1 if none, 0..3 if charged
        encore_active = 1.0 if user_vec[MonIdx.ENCORE_TURNS] > 0.0 else 0.0
        last_move_idx = int(round(float(user_vec[MonIdx.LAST_MOVE_IDX])))
        choice_lock_idx = int(round(float(user_vec[MonIdx.CHOICE_LOCKED_MOVE])))
        from .schema_and_tables import FieldOpID as _FopIDInit
        user_has_tantrum = any(
            int(round(float(moves_4[k_m, MoveIdx.FIELD_OP_ID]))) == int(_FopIDInit.STOMPING_TANTRUM)
            for k_m in range(MOVES_PER_MON)
        )
        user_ab = int(round(float(user_vec[MonIdx.ABILITY_ID])))
        can_mega_gate = (
            1.0
            if (
                user_vec[MonIdx.CAN_MEGA] > 0.0
                and user_vec[MonIdx.IS_MEGA] <= 0.0
                and side_mega_used <= 0.0
            )
            else 0.0
        )

        opp_a_alive = opp_a_vec[MonIdx.ALIVE_FLAG] > 0.0
        opp_b_alive = opp_b_vec[MonIdx.ALIVE_FLAG] > 0.0
        partner_alive = partner_vec[MonIdx.ALIVE_FLAG] > 0.0

        opp_a_ab = int(round(float(opp_a_vec[MonIdx.ABILITY_ID]))) if opp_a_alive else 0
        opp_b_ab = int(round(float(opp_b_vec[MonIdx.ABILITY_ID]))) if opp_b_alive else 0
        opp_blocks_prio = (
            1.0
            if (
                opp_a_ab in (AbilityID.ARMOR_TAIL, AbilityID.QUEENLY_MAJESTY)
                or opp_b_ab in (AbilityID.ARMOR_TAIL, AbilityID.QUEENLY_MAJESTY)
            )
            else 0.0
        )

        # Full-OTS pre-checks for Wide Guard, Quick Guard, and Shadow Tag
        opp_bench_slots = (opp_bench1_slot, opp_bench2_slot)
        opp_all_alive_slots = [
            s for s in (opp_a_slot, opp_b_slot, opp_bench1_slot, opp_bench2_slot)
            if p_np[s, MonIdx.ALIVE_FLAG] > 0.0
        ]
        opp_can_have_psychic_terrain = is_psychic_terrain > 0.5 or any(
            int(round(float(p_np[s, MonIdx.ABILITY_ID]))) == AbilityID.PSYCHIC_SURGE
            or (
                p_np[s, MonIdx.CAN_MEGA] > 0.0
                and int(round(float(p_np[s, MonIdx.MEGA_ABILITY_ID]))) == AbilityID.PSYCHIC_SURGE
            )
            for s in opp_all_alive_slots
        )
        opp_can_have_grassy_terrain = is_grassy_terrain > 0.5 or any(
            int(round(float(p_np[s, MonIdx.ABILITY_ID]))) == AbilityID.GRASSY_SURGE
            or (
                p_np[s, MonIdx.CAN_MEGA] > 0.0
                and int(round(float(p_np[s, MonIdx.MEGA_ABILITY_ID]))) == AbilityID.GRASSY_SURGE
            )
            for s in opp_all_alive_slots
        )

        opp_has_spread_threat = False
        opp_has_prio_threat = False
        for opp_act_s in (opp_a_slot, opp_b_slot):
            if p_np[opp_act_s, MonIdx.ALIVE_FLAG] <= 0.0:
                continue
            if p_np[opp_act_s, MonIdx.MUST_RECHARGE] > 0.5:
                continue
            opp_s_vec = p_np[opp_act_s]
            opp_s_ab = int(round(float(opp_s_vec[MonIdx.ABILITY_ID])))
            opp_s_can_mega = opp_s_vec[MonIdx.CAN_MEGA] > 0.0 and opp_s_vec[MonIdx.IS_MEGA] <= 0.0
            opp_s_mega_ab = int(round(float(opp_s_vec[MonIdx.MEGA_ABILITY_ID]))) if opp_s_can_mega else opp_s_ab
            opp_s_act_turns = float(opp_s_vec[MonIdx.ACTIVE_TURNS])
            opp_s_full_hp = opp_s_vec[MonIdx.HP_CUR] >= opp_s_vec[MonIdx.HP_MAX]

            for opp_m_i in range(MOVES_PER_MON):
                omv = m_np[opp_act_s, opp_m_i]
                if omv[MoveIdx.BASE_POWER] <= 0.0 and omv[MoveIdx.CAT_STATUS] <= 0.5:
                    continue
                if omv[MoveIdx.FIRST_TURN_ONLY] > 0.5 and opp_s_act_turns > 0.0:
                    continue
                otgt = int(round(float(omv[MoveIdx.TARGET_TYPE])))
                if otgt in (int(TargetType.ALL_ADJACENT_FOES), int(TargetType.ALL_ADJACENT)):
                    opp_has_spread_threat = True
                elif (
                    opp_can_have_psychic_terrain
                    and omv[MoveIdx.TYPE_START + TYPE_TO_IDX["psychic"]] > 0.5
                    and omv[MoveIdx.CAT_SPECIAL] > 0.5
                    and abs(float(omv[MoveIdx.BASE_POWER]) - 80.0) < 0.5
                ):
                    opp_has_spread_threat = True

                # Quick Guard only blocks foe-targeting moves with effective priority > 0
                if otgt in (
                    int(TargetType.SINGLE_FOE),
                    int(TargetType.ALL_ADJACENT_FOES),
                    int(TargetType.ALL_ADJACENT),
                ):
                    oprio = float(omv[MoveIdx.PRIORITY])
                    if omv[MoveIdx.CAT_STATUS] > 0.5 and (
                        opp_s_ab == AbilityID.PRANKSTER or opp_s_mega_ab == AbilityID.PRANKSTER
                    ):
                        oprio += 1.0
                    elif (
                        omv[MoveIdx.TYPE_START + TYPE_TO_IDX["flying"]] > 0.5
                        and opp_s_full_hp
                        and (opp_s_ab == AbilityID.GALE_WINGS or opp_s_mega_ab == AbilityID.GALE_WINGS)
                    ):
                        oprio += 1.0
                    elif omv[MoveIdx.GRASSY_PRIO_BOOST] > 0.5 and opp_can_have_grassy_terrain:
                        oprio += 1.0
                    if oprio > 0.0:
                        opp_has_prio_threat = True

        target_slots = (opp_a_vec, opp_b_vec, partner_vec)

        for mega_mode in (0, 1):
            if mega_mode == 1 and can_mega_gate <= 0.0:
                continue
            eff_user_ab = int(round(float(user_vec[MonIdx.MEGA_ABILITY_ID]))) if mega_mode == 1 else user_ab
            user_has_mold_breaker = eff_user_ab == AbilityID.MOLD_BREAKER

            for tgt_bucket, raw_tgt_vec in enumerate(target_slots):
                for m_idx in range(MOVES_PER_MON):
                    choice_idx = (mega_mode * 12) + (tgt_bucket * 4) + m_idx
                    m_vec = moves_4[m_idx]

                    # Skip empty/dummy move slot if base_power == 0 and status == 0
                    if (
                        m_vec[MoveIdx.BASE_POWER] <= 0.0
                        and m_vec[MoveIdx.CAT_STATUS] <= 0.5
                    ):
                        continue

                    target_type = int(round(float(m_vec[MoveIdx.TARGET_TYPE])))
                    is_status = m_vec[MoveIdx.CAT_STATUS] > 0.5
                    protect_type = float(m_vec[MoveIdx.PROTECT_TYPE])

                    # Wide Guard / Quick Guard Full-OTS Zero-Effect Invariants
                    if protect_type == 2.0 and not opp_has_spread_threat:
                        continue
                    if protect_type == 3.0 and not opp_has_prio_threat:
                        continue

                    # 1. Target Bucket Routing & Target Alive Gate
                    if target_type in (
                        TargetType.SELF,
                        TargetType.ALLY_SIDE,
                        TargetType.GLOBAL_FIELD,
                    ):
                        if tgt_bucket != 0:
                            continue
                        tgt_vec = user_vec
                    elif target_type == TargetType.ALL_ADJACENT_FOES:
                        if tgt_bucket != 0 or not (opp_a_alive or opp_b_alive):
                            continue
                        tgt_vec = opp_a_vec if opp_a_alive else opp_b_vec
                    elif target_type == TargetType.ALL_ADJACENT:
                        if tgt_bucket != 0 or not (opp_a_alive or opp_b_alive or partner_alive):
                            continue
                        tgt_vec = (
                            opp_a_vec
                            if opp_a_alive
                            else (opp_b_vec if opp_b_alive else partner_vec)
                        )
                    elif target_type == TargetType.ALLY:
                        if tgt_bucket != 2 or not partner_alive:
                            continue
                        tgt_vec = partner_vec
                    else:
                        if raw_tgt_vec[MonIdx.ALIVE_FLAG] <= 0.0:
                            continue
                        tgt_vec = raw_tgt_vec

                    tgt_ab = 0 if user_has_mold_breaker else int(round(float(tgt_vec[MonIdx.ABILITY_ID])))
                    raw_tgt_ab = int(round(float(tgt_vec[MonIdx.ABILITY_ID])))
                    tgt_has_lev_like = raw_tgt_ab in (AbilityID.LEVITATE, AbilityID.EELEVATE)
                    tgt_has_iron_ball = (
                        tgt_vec[MonIdx.ITEM_ACTIVE] > 0.5
                        and int(round(float(tgt_vec[MonIdx.ITEM_ID]))) == int(ItemID.IRON_BALL)
                    )
                    tgt_grounded = (
                        1.0
                        if (
                            gravity_active > 0.0
                            or tgt_has_iron_ball
                            or (tgt_vec[MonIdx.GROUNDED_FLAG] > 0.0)
                            or (user_has_mold_breaker and tgt_has_lev_like)
                        )
                        else 0.0
                    )
                    tgt_type1 = tgt_vec[MonIdx.TYPE1_START:MonIdx.TYPE1_END]
                    tgt_type2 = tgt_vec[MonIdx.TYPE2_START:MonIdx.TYPE2_END]
                    tgt_is_dark = float(tgt_type1[TYPE_TO_IDX["dark"]] + tgt_type2[TYPE_TO_IDX["dark"]])

                    # 2. Choice Lock / Encore / Taunt / Throat Chop / 2-Turn Charged Hard Gates
                    if charged_move_idx >= 0 and m_idx != charged_move_idx:
                        continue
                    if choice_lock_idx >= 0 and m_idx != choice_lock_idx:
                        continue
                    if encore_active > 0.0 and last_move_idx >= 0 and m_idx != last_move_idx:
                        continue
                    if is_status and taunt_active > 0.0:
                        continue
                    if m_vec[MoveIdx.IS_SOUND_MOVE] > 0.5 and throat_chop_active > 0.0:
                        continue

                    # 3. Turn-1 Gate (Fake Out / First Impression)
                    if m_vec[MoveIdx.FIRST_TURN_ONLY] > 0.5 and active_turns > 0.0:
                        continue

                    # Resolve effective move type (accounting for Weather Ball, Liquid Voice, Aerilate, Pixilate, Refrigerate)
                    w_code = m_vec[MoveIdx.WEATHER_SURE_HIT]
                    if w_code == 1.0:
                        m_type_vec = np.zeros(NUM_TYPES, dtype=np.float32)
                        if is_sun > 0.5:
                            m_type_vec[TYPE_TO_IDX["fire"]] = 1.0
                        elif is_rain > 0.5:
                            m_type_vec[TYPE_TO_IDX["water"]] = 1.0
                        elif is_sand > 0.5:
                            m_type_vec[TYPE_TO_IDX["rock"]] = 1.0
                        elif is_snow > 0.5:
                            m_type_vec[TYPE_TO_IDX["ice"]] = 1.0
                        else:
                            m_type_vec[TYPE_TO_IDX["normal"]] = 1.0
                    elif eff_user_ab == AbilityID.LIQUID_VOICE and m_vec[MoveIdx.IS_SOUND_MOVE] > 0.5:
                        m_type_vec = np.zeros(NUM_TYPES, dtype=np.float32)
                        m_type_vec[TYPE_TO_IDX["water"]] = 1.0
                    elif (
                        m_vec[MoveIdx.TYPE_START + TYPE_TO_IDX["normal"]] > 0.5
                        and eff_user_ab in (AbilityID.AERILATE, AbilityID.PIXILATE, AbilityID.REFRIGERATE, AbilityID.DRAGONIZE)
                    ):
                        m_type_vec = np.zeros(NUM_TYPES, dtype=np.float32)
                        if eff_user_ab == AbilityID.AERILATE:
                            m_type_vec[TYPE_TO_IDX["flying"]] = 1.0
                        elif eff_user_ab == AbilityID.PIXILATE:
                            m_type_vec[TYPE_TO_IDX["fairy"]] = 1.0
                        elif eff_user_ab == AbilityID.DRAGONIZE:
                            m_type_vec[TYPE_TO_IDX["dragon"]] = 1.0
                        else:
                            m_type_vec[TYPE_TO_IDX["ice"]] = 1.0
                    else:
                        m_type_vec = m_vec[MoveIdx.TYPE_START:MoveIdx.TYPE_END]

                    # 4. Effective Priority Resolution
                    eff_prio = float(m_vec[MoveIdx.PRIORITY])
                    if eff_user_ab == AbilityID.PRANKSTER and is_status:
                        eff_prio += 1.0
                    elif (
                        eff_user_ab == AbilityID.GALE_WINGS
                        and m_type_vec[TYPE_TO_IDX["flying"]] > 0.5
                        and user_vec[MonIdx.HP_CUR] >= user_vec[MonIdx.HP_MAX]
                    ):
                        eff_prio += 1.0
                    elif (
                        m_vec[MoveIdx.GRASSY_PRIO_BOOST] > 0.5
                        and is_grassy_terrain > 0.5
                        and user_vec[MonIdx.GROUNDED_FLAG] > 0.5
                    ):
                        eff_prio += 1.0

                    # 5. Priority Blocking, Psychic Terrain, Prankster vs Dark & Ability Immunities
                    # Unified Switch-Read Rule: single-target immunities are only hard-pruned when
                    # the opponent has no alive bench (`not opp_has_alive_bench`).
                    can_hard_prune_single_target = (
                        prune_zero_effect_attacks_when_no_bench and not opp_has_alive_bench
                    )
                    is_single_targeted_at_foe = target_type == TargetType.SINGLE_FOE and tgt_bucket in (0, 1)
                    if is_single_targeted_at_foe and can_hard_prune_single_target:
                        if eff_prio > 0.0:
                            if opp_blocks_prio > 0.5 and not user_has_mold_breaker:
                                continue
                            if is_psychic_terrain > 0.5 and tgt_grounded > 0.5:
                                continue

                        # 6. Prankster vs Dark-Type Target Invariant
                        if (
                            eff_user_ab == AbilityID.PRANKSTER
                            and is_status
                            and tgt_is_dark > 0.5
                        ):
                            continue

                        # 7. Soundproof, Bulletproof, Good as Gold, Elemental Absorb & Terrain Sleep Invariants
                        from .schema_and_tables import FieldOpID as _FopID
                        m_fop = int(round(float(m_vec[MoveIdx.FIELD_OP_ID])))
                        if m_vec[MoveIdx.IS_SOUND_MOVE] > 0.5 and tgt_ab == AbilityID.SOUNDPROOF:
                            continue
                        if m_fop in (int(_FopID.FLAG_BULLET), int(_FopID.FLAG_PULSE_BULLET)) and tgt_ab == AbilityID.BULLETPROOF:
                            continue
                        if is_status and tgt_ab == AbilityID.GOOD_AS_GOLD:
                            continue
                        if m_fop == int(_FopID.TAUNT) and tgt_ab == AbilityID.OBLIVIOUS and not user_has_mold_breaker:
                            continue
                        if m_type_vec[TYPE_TO_IDX["fire"]] > 0.5 and tgt_ab == AbilityID.FLASH_FIRE:
                            continue
                        if m_type_vec[TYPE_TO_IDX["water"]] > 0.5 and tgt_ab in (
                            AbilityID.WATER_ABSORB,
                            AbilityID.DRY_SKIN,
                        ):
                            continue
                        if m_type_vec[TYPE_TO_IDX["electric"]] > 0.5 and tgt_ab in (
                            AbilityID.VOLT_ABSORB,
                            AbilityID.MOTOR_DRIVE,
                            AbilityID.LIGHTNING_ROD,
                        ):
                            continue
                        if m_type_vec[TYPE_TO_IDX["grass"]] > 0.5 and tgt_ab == AbilityID.SAP_SIPPER:
                            continue
                        if m_type_vec[TYPE_TO_IDX["ground"]] > 0.5 and tgt_ab == AbilityID.EARTH_EATER:
                            continue
                        is_sleep_move = (
                            m_vec[MoveIdx.SEC_STATUS_START + STATUS_TO_IDX["sleep"]] > 0.5
                            and m_vec[MoveIdx.SEC_STATUS_CHANCE] >= 1.0
                            and is_status
                        )
                        if is_sleep_move and tgt_grounded > 0.5 and is_elec_or_misty_terrain > 0.5:
                            continue

                    # 8. Soft Tactical Risk-Reward Evaluation
                    prior_scale = 1.0
                    risk_val = 0.10
                    upside_val = 0.70

                    if m_vec[MoveIdx.PROTECT_TYPE] == 1.0 and protect_count >= 1.0:
                        succ_prob = (1.0 / 3.0) ** protect_count
                        risk_val = min(0.97, 1.0 - succ_prob)
                        upside_val = 0.85 if protect_count == 1.0 else 0.90
                        prior_scale = 0.33 if protect_count == 1.0 else 0.11

                    # Two-turn charging move evaluation (Turn 1: deals 0 damage if must charge)
                    is_solar_charge = (w_code == 10.0) and (is_sun <= 0.5)
                    is_electro_charge = (w_code == 20.0) and (is_rain <= 0.5)
                    is_general_charge = (w_code == 30.0)
                    must_charge = is_solar_charge or is_electro_charge or is_general_charge
                    if must_charge:
                        prior_scale = 0.05 if w_code == 10.0 else 0.10
                        risk_val = 0.95 if w_code == 10.0 else 0.90
                        upside_val = 0.10

                    acc_val = float(m_vec[MoveIdx.ACCURACY])
                    if eff_user_ab == AbilityID.NO_GUARD or tgt_ab == AbilityID.NO_GUARD:
                        acc_val = 1.0
                    elif m_vec[MoveIdx.WEATHER_SURE_HIT] == 2.0 and is_rain > 0.5:
                        acc_val = 1.0
                    elif m_vec[MoveIdx.WEATHER_SURE_HIT] == 2.0 and is_sun > 0.5:
                        acc_val = 0.50
                    elif m_vec[MoveIdx.WEATHER_SURE_HIT] == 4.0 and is_snow > 0.5:
                        acc_val = 1.0
                    acc_val = min(1.0, max(0.0, acc_val))

                    if not is_status:
                        from .schema_and_tables import FieldOpID as _FopIDDmg
                        m_fop_dmg = int(round(float(m_vec[MoveIdx.FIELD_OP_ID])))
                        eff1 = float(m_type_vec @ self._type_chart_np @ tgt_type1)
                        raw_eff2 = float(m_type_vec @ self._type_chart_np @ tgt_type2)
                        eff2 = raw_eff2 + (1.0 - float(np.sum(tgt_type2)))
                        if m_fop_dmg == int(_FopIDDmg.FREEZE_DRY):
                            if tgt_type1[TYPE_TO_IDX["water"]] > 0.5:
                                eff1 = 2.0
                            if tgt_type2[TYPE_TO_IDX["water"]] > 0.5:
                                eff2 = 2.0
                        eff_total = eff1 * eff2

                        # Scrappy bypasses Ghost immunity on Normal/Fighting moves
                        if eff_user_ab == AbilityID.SCRAPPY and (
                            m_type_vec[TYPE_TO_IDX["normal"]] > 0.5
                            or m_type_vec[TYPE_TO_IDX["fighting"]] > 0.5
                        ):
                            if tgt_type1[TYPE_TO_IDX["ghost"]] > 0.5 or tgt_type2[TYPE_TO_IDX["ghost"]] > 0.5:
                                eff_total = max(1.0, eff_total)

                        if m_type_vec[TYPE_TO_IDX["ground"]] > 0.5 and tgt_grounded <= 0.0:
                            eff_total = 0.0
                        if (
                            (m_type_vec[TYPE_TO_IDX["fire"]] > 0.5 and tgt_ab == AbilityID.FLASH_FIRE)
                            or (
                                m_type_vec[TYPE_TO_IDX["water"]] > 0.5
                                and tgt_ab in (AbilityID.WATER_ABSORB, AbilityID.DRY_SKIN)
                            )
                            or (
                                m_type_vec[TYPE_TO_IDX["electric"]] > 0.5
                                and tgt_ab in (AbilityID.VOLT_ABSORB, AbilityID.MOTOR_DRIVE, AbilityID.LIGHTNING_ROD)
                            )
                            or (m_type_vec[TYPE_TO_IDX["grass"]] > 0.5 and tgt_ab == AbilityID.SAP_SIPPER)
                            or (m_type_vec[TYPE_TO_IDX["ground"]] > 0.5 and tgt_ab == AbilityID.EARTH_EATER)
                        ):
                            eff_total = 0.0

                        # If single-targeting foe with 0.0x move AND opponent has no bench to switch in, prune!
                        if (
                            prune_zero_effect_attacks_when_no_bench
                            and is_single_targeted_at_foe
                            and eff_total == 0.0
                            and not opp_has_alive_bench
                        ):
                            continue

                        if tgt_bucket == 2:
                            # Intentional ally-immunity miss priming for Stomping Tantrum / Temper Flare (75 -> 150 BP next turn!)
                            if eff_total == 0.0 and user_has_tantrum:
                                prior_scale = 0.55
                                risk_val = 0.35
                                upside_val = 0.80
                            else:
                                prior_scale = 0.20
                                risk_val = 0.65
                                upside_val = 0.75
                        else:
                            if eff_total == 0.0:
                                prior_scale = 0.15
                                risk_val = 0.85
                                upside_val = 0.85
                            elif eff_total <= 0.25:
                                prior_scale = 0.50
                                risk_val = 0.55
                                upside_val = 0.60
                            elif eff_total >= 4.0:
                                prior_scale = 1.35 * acc_val
                                risk_val = max(0.05, 1.0 - acc_val if acc_val < 0.85 else 0.05)
                                upside_val = 0.95
                            elif eff_total >= 2.0:
                                prior_scale = 1.20 * acc_val
                                risk_val = max(0.10, 1.0 - acc_val if acc_val < 0.85 else 0.10)
                                upside_val = 0.85
                            elif acc_val < 0.85:
                                prior_scale = acc_val
                                risk_val = 1.0 - acc_val
                                upside_val = 0.80
                    elif acc_val < 0.85:
                        prior_scale *= acc_val
                        risk_val = max(risk_val, 1.0 - acc_val)
                        upside_val = 0.80

                    if mega_mode == 1:
                        prior_scale *= 1.10
                        upside_val = min(1.0, upside_val + 0.05)

                    valid_26[choice_idx] = 1.0
                    prior_26[choice_idx] = round(float(prior_scale), 4)
                    risk_26[choice_idx] = round(float(risk_val), 4)
                    upside_26[choice_idx] = round(float(upside_val), 4)

        # Shadow Tag switch lock: blocks voluntary switches on non-Ghost / non-Shadow-Tag slots
        opp_has_shadow_tag = (
            opp_a_ab == AbilityID.SHADOW_TAG or opp_b_ab == AbilityID.SHADOW_TAG
        )
        user_is_ghost = (
            user_vec[MonIdx.TYPE1_START + TYPE_TO_IDX["ghost"]] > 0.5
            or user_vec[MonIdx.TYPE2_START + TYPE_TO_IDX["ghost"]] > 0.5
        )
        is_trapped_by_shadow_tag = (
            opp_has_shadow_tag
            and not user_is_ghost
            and user_ab != AbilityID.SHADOW_TAG
        )

        if not is_trapped_by_shadow_tag:
            if p_np[bench1_slot, MonIdx.ALIVE_FLAG] > 0.0:
                valid_26[CHOICE_SWITCH_BENCH1] = 1.0
                prior_26[CHOICE_SWITCH_BENCH1] = 0.65
                risk_26[CHOICE_SWITCH_BENCH1] = 0.25
                upside_26[CHOICE_SWITCH_BENCH1] = 0.65
            if p_np[bench2_slot, MonIdx.ALIVE_FLAG] > 0.0:
                valid_26[CHOICE_SWITCH_BENCH2] = 1.0
                prior_26[CHOICE_SWITCH_BENCH2] = 0.65
                risk_26[CHOICE_SWITCH_BENCH2] = 0.25
                upside_26[CHOICE_SWITCH_BENCH2] = 0.65

        return valid_26, prior_26, risk_26, upside_26

    def prune_side_26x26_tensor_actions(
        self,
        state: CompiledBattleState,
        trainer_id: str = "trainer_1",
        min_prior_threshold: float = 0.0,
    ) -> PrunedSideActionTensorMask:
        """Compute the `26x26` logical validity, prior, risk, and upside matrices and prune non-viable actions.

        Args:
            state: `CompiledBattleState` containing `field_tensor [24]`, `roster_tensor [8, 87]`,
                and `moves_tensor [8, 4, 59]`.
            trainer_id: `'trainer_1'` or `'trainer_2'`.
            min_prior_threshold: Ignored (permanently locked to `0.0` to guarantee zero heuristic pruning;
                only strictly mathematical/mechanical zero-effect actions are pruned).

        Returns:
            `PrunedSideActionTensorMask` with `[N_valid, 2]` pruned choice pairs.
        """
        # Lock min_prior_threshold permanently to 0.0 (no heuristic pruning)
        min_prior_threshold = 0.0
        if trainer_id not in ("trainer_1", "trainer_2"):
            raise ValueError(f"trainer_id must be 'trainer_1' or 'trainer_2', got '{trainer_id}'")

        if state.backend == "torch" and HAS_TORCH and isinstance(state.roster_tensor, torch.Tensor):
            f_np = state.field_tensor.detach().cpu().numpy()
            p_np = state.roster_tensor.detach().cpu().numpy()
            m_np = state.moves_tensor.detach().cpu().numpy()
            dev = state.roster_tensor.device
            use_torch = True
        else:
            f_np = np.asarray(state.field_tensor)
            p_np = np.asarray(state.roster_tensor)
            m_np = np.asarray(state.moves_tensor)
            dev = "cpu"
            use_torch = False

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

        val_a, pri_a, rsk_a, ups_a = self._compute_slot_26_constraints_numpy(
            f_np, p_np, m_np, slot_a, slot_b, opp_a, opp_b, bench1, bench2, mega_used
        )
        val_b, pri_b, rsk_b, ups_b = self._compute_slot_26_constraints_numpy(
            f_np, p_np, m_np, slot_b, slot_a, opp_a, opp_b, bench1, bench2, mega_used
        )

        # Fallback if a slot has zero valid actions (e.g. fainted or struggled): allow index 0
        if np.sum(val_a) <= 0.0:
            val_a[0] = 1.0
            pri_a[0] = 0.01
        if np.sum(val_b) <= 0.0:
            val_b[0] = 1.0
            pri_b[0] = 0.01

        joint_valid = np.outer(val_a, val_b).astype(np.float32)

        # Cross-Slot Invariant 1: Simultaneous Double-Mega Lock (12..23 x 12..23 -> 0.0)
        joint_valid[12:24, 12:24] = 0.0

        # Cross-Slot Invariant 2: Simultaneous Switch Crash into Same Bench Pokémon
        joint_valid[CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH1] = 0.0
        joint_valid[CHOICE_SWITCH_BENCH2, CHOICE_SWITCH_BENCH2] = 0.0

        # Cross-Slot Invariant 3: Helping Hand + Partner Status / Switch / Recharge Zero-Effect Pruning
        from .schema_and_tables import FieldOpID
        slot_a_recharging = p_np[slot_a, MonIdx.MUST_RECHARGE] > 0.5
        slot_b_recharging = p_np[slot_b, MonIdx.MUST_RECHARGE] > 0.5
        for c_a in range(24):
            m_a = m_np[slot_a, (c_a % 12) % 4]
            if int(round(float(m_a[MoveIdx.FIELD_OP_ID]))) == int(FieldOpID.HELPING_HAND):
                if slot_b_recharging:
                    joint_valid[c_a, :] = 0.0
                    continue
                joint_valid[c_a, CHOICE_SWITCH_BENCH1] = 0.0
                joint_valid[c_a, CHOICE_SWITCH_BENCH2] = 0.0
                for c_b in range(24):
                    m_b = m_np[slot_b, (c_b % 12) % 4]
                    if m_b[MoveIdx.CAT_STATUS] > 0.5 or m_b[MoveIdx.BASE_POWER] <= 0.0:
                        joint_valid[c_a, c_b] = 0.0

        for c_b in range(24):
            m_b = m_np[slot_b, (c_b % 12) % 4]
            if int(round(float(m_b[MoveIdx.FIELD_OP_ID]))) == int(FieldOpID.HELPING_HAND):
                if slot_a_recharging:
                    joint_valid[:, c_b] = 0.0
                    continue
                joint_valid[CHOICE_SWITCH_BENCH1, c_b] = 0.0
                joint_valid[CHOICE_SWITCH_BENCH2, c_b] = 0.0
                for c_a in range(24):
                    m_a = m_np[slot_a, (c_a % 12) % 4]
                    if m_a[MoveIdx.CAT_STATUS] > 0.5 or m_a[MoveIdx.BASE_POWER] <= 0.0:
                        joint_valid[c_a, c_b] = 0.0

        if np.sum(joint_valid) <= 0.0:
            joint_valid[0, 0] = 1.0

        joint_prior = (np.outer(pri_a, pri_b) * joint_valid).astype(np.float32)

        # Composite joint risk = 1 - (1 - risk_a)*(1 - risk_b) on valid cells
        joint_risk = ((1.0 - np.outer(1.0 - rsk_a, 1.0 - rsk_b)) * joint_valid).astype(np.float32)
        joint_upside = (0.5 * (ups_a[:, None] + ups_b[None, :]) * joint_valid).astype(np.float32)

        coords_np = np.argwhere(joint_valid > 0.5).astype(np.int64)

        if use_torch and HAS_TORCH:
            return PrunedSideActionTensorMask(
                trainer_id=trainer_id,
                valid_mask_26x26=torch.from_numpy(joint_valid).to(dev),
                prior_matrix_26x26=torch.from_numpy(joint_prior).to(dev),
                risk_matrix_26x26=torch.from_numpy(joint_risk).to(dev),
                upside_matrix_26x26=torch.from_numpy(joint_upside).to(dev),
                pruned_choices=torch.from_numpy(coords_np).to(dev),
            )

        return PrunedSideActionTensorMask(
            trainer_id=trainer_id,
            valid_mask_26x26=joint_valid,
            prior_matrix_26x26=joint_prior,
            risk_matrix_26x26=joint_risk,
            upside_matrix_26x26=joint_upside,
            pruned_choices=coords_np,
        )

