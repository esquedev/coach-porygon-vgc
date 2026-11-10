# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Logical Constraint, Action Pruner & Risk-Reward Engine
==========================================================================

Evaluates candidate Pokémon VGC 4v4 Doubles (Regulation M-C) battle actions through
a dual-mode logical lens, operating both at the symbolic DuckDB level and directly
as vectorized `26x26` tensor masks on `[24]`, `[8, 84]`, and `[8, 4, 56]` board states:

1. **Hard Mechanical Invariants (Physical Failures — Probability 0%, Pruned from Tensor Batch)**:
   - `Fake Out`, `First Impression`, `Mat Block` when `active_turns >= 1` (0-indexed after lead/switch).
   - Priority moves (`priority > 0`, `Prankster` status, `Grassy Glide` in Grassy Terrain) targeting
     opposing slots when `Armor Tail` / `Queenly Majesty` / `Dazzling` is active on the opposing side,
     or into grounded foes under `Psychic Terrain`.
   - `Prankster` status moves into `Dark`-type opposing targets.
   - Sound moves into `Soundproof`, status moves into `Good as Gold`, Fire moves into `Flash Fire`,
     Water moves into `Storm Drain` / `Water Absorb`, Electric moves into `Lightning Rod` / `Volt Absorb` /
     `Motor Drive`, Grass moves into `Sap Sipper`, Ground moves into `Earth Eater`.
   - Sleep moves (`Spore`, `Sleep Powder`, `Hypnosis`, `Yawn`, `Lovely Kiss`, `Sing`, `Grass Whistle`)
     into grounded targets under `Electric Terrain` or `Misty Terrain`.
   - Choice-lock (`Choice Band`, `Choice Specs`, `Choice Scarf`), `Encore`, `Taunt`, and `Assault Vest`.
   - Single-Mega exclusivity (`M[12:24, 12:24] = 0`) and same-bench switch collision (`M[24, 24] = M[25, 25] = 0`).

2. **Soft Tactical Constraints (Continuous Risk / Upside Continuum & Tensor Priors)**:
   - Consecutive `Protect` / `Detect` / `Spiky Shield` / `King's Shield` / `Silk Trap` / `Baneful Bunker`
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
    ShowdownTensorCompiler,
    _parse_structured_field,
    _to_id,
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

PRIORITY_BLOCKING_ABILITIES = {"Armor Tail", "Queenly Majesty", "Dazzling"}
SOUND_MOVES = {
    "Hyper Voice",
    "Parting Shot",
    "Bug Buzz",
    "Snarl",
    "Roar",
    "Disarming Voice",
    "Alluring Voice",
    "Torch Song",
    "Boomburst",
    "Perish Song",
    "Clangorous Soul",
}
SLEEP_MOVES = {"Hypnosis", "Yawn", "Sleep Powder", "Spore", "Grass Whistle", "Lovely Kiss", "Sing", "Dark Void"}
PROTECT_MOVES = {
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
STATUS_ABSORBING_ABILITIES = {"Good as Gold"}
FIRE_ABSORBING_ABILITIES = {"Flash Fire", "Well-Baked Body"}
ELECTRIC_ABSORBING_ABILITIES = {"Lightning Rod", "Motor Drive", "Volt Absorb"}
WATER_ABSORBING_ABILITIES = {"Water Absorb", "Storm Drain", "Dry Skin"}
GRASS_ABSORBING_ABILITIES = {"Sap Sipper"}
GROUND_ABSORBING_ABILITIES = {"Levitate", "Earth Eater"}


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
        if weather == "rain" and move_name in (
            "Thunder",
            "Hurricane",
            "Bleakwind Storm",
            "Wildbolt Storm",
            "Sandsear Storm",
        ):
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

    def prune_impossible_actions(
        self,
        candidate_actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter a list of candidate actions down to those that remain mechanically valid."""
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
        """Evaluate a single move against physical invariants and tactical risk-reward profile."""
        field_dict = field_state or {}
        weather = str(field_dict.get("weather") or "").lower()
        terrain = str(field_dict.get("terrain") or "").lower()
        move_data = self._lookup_move_data(move_name)

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

        # 1. Physical invariant: Fake Out / First Impression / Mat Block only on first active turn
        if move_name in ("Fake Out", "First Impression", "Mat Block") and active_turns > 1:
            return self._make_result(
                is_mechanically_valid=False,
                risk_score=1.0,
                upside_potential=0.0,
                classification="Mechanically_Invalid",
                reasons=[f"{move_name} fails physically when active turns ({active_turns}) > 1."],
                recommended_prior_scale=0.0,
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
            scrappy = user_ability in ("Scrappy", "Mind's Eye")
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

        moves_4 = m_np[user_slot]  # [4, 56]
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
        is_psychic_terrain = float(t_onehot[TERRAIN_TO_IDX["psychic"]])
        is_grassy_terrain = float(t_onehot[TERRAIN_TO_IDX["grassy"]])
        is_elec_or_misty_terrain = float(
            t_onehot[TERRAIN_TO_IDX["electric"]] + t_onehot[TERRAIN_TO_IDX["misty"]]
        )
        gravity_active = 1.0 if f_np[FieldIdx.GRAVITY_TURNS] > 0.0 else 0.0

        active_turns = float(user_vec[MonIdx.ACTIVE_TURNS])
        protect_count = float(user_vec[MonIdx.PROTECT_COUNTER])
        taunt_active = 1.0 if user_vec[MonIdx.TAUNT_TURNS] > 0.0 else 0.0
        encore_active = 1.0 if user_vec[MonIdx.ENCORE_TURNS] > 0.0 else 0.0
        last_move_idx = int(round(float(user_vec[MonIdx.LAST_MOVE_IDX])))
        choice_lock_idx = int(round(float(user_vec[MonIdx.CHOICE_LOCKED_MOVE])))
        has_assault_vest = (
            1.0
            if (
                user_vec[MonIdx.ITEM_ACTIVE] > 0.0
                and int(round(float(user_vec[MonIdx.ITEM_ID]))) == ItemID.ASSAULT_VEST
            )
            else 0.0
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

        opp_a_ab = int(round(float(opp_a_vec[MonIdx.ABILITY_ID]))) if opp_a_vec[MonIdx.ALIVE_FLAG] > 0.0 else 0
        opp_b_ab = int(round(float(opp_b_vec[MonIdx.ABILITY_ID]))) if opp_b_vec[MonIdx.ALIVE_FLAG] > 0.0 else 0
        opp_blocks_prio = (
            1.0
            if (
                opp_a_ab in (AbilityID.ARMOR_TAIL, AbilityID.QUEENLY_MAJESTY)
                or opp_b_ab in (AbilityID.ARMOR_TAIL, AbilityID.QUEENLY_MAJESTY)
            )
            else 0.0
        )

        target_slots = (opp_a_vec, opp_b_vec, partner_vec)

        for mega_mode in (0, 1):
            if mega_mode == 1 and can_mega_gate <= 0.0:
                continue
            eff_user_ab = int(round(float(user_vec[MonIdx.MEGA_ABILITY_ID]))) if mega_mode == 1 else user_ab

            for tgt_bucket, tgt_vec in enumerate(target_slots):
                if tgt_vec[MonIdx.ALIVE_FLAG] <= 0.0:
                    continue

                tgt_ab = int(round(float(tgt_vec[MonIdx.ABILITY_ID])))
                tgt_grounded = 1.0 if (gravity_active > 0.0 or tgt_vec[MonIdx.GROUNDED_FLAG] > 0.0) else 0.0
                tgt_type1 = tgt_vec[MonIdx.TYPE1_START:MonIdx.TYPE1_END]
                tgt_type2 = tgt_vec[MonIdx.TYPE2_START:MonIdx.TYPE2_END]
                tgt_is_dark = float(tgt_type1[TYPE_TO_IDX["dark"]] + tgt_type2[TYPE_TO_IDX["dark"]])

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

                    # 8. Soft Tactical Risk-Reward Evaluation
                    prior_scale = 1.0
                    risk_val = 0.10
                    upside_val = 0.70

                    if m_vec[MoveIdx.PROTECT_TYPE] >= 1.0 and protect_count >= 1.0:
                        succ_prob = (1.0 / 3.0) ** protect_count
                        risk_val = min(0.97, 1.0 - succ_prob)
                        upside_val = 0.85 if protect_count == 1.0 else 0.90
                        prior_scale = 0.33 if protect_count == 1.0 else 0.11

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
                        eff1 = float(m_type_vec @ self._type_chart_np @ tgt_type1)
                        raw_eff2 = float(m_type_vec @ self._type_chart_np @ tgt_type2)
                        eff2 = raw_eff2 + (1.0 - float(np.sum(tgt_type2)))
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

                        # If single-targeting foe with 0.0x move AND opponent has no bench to switch in, prune!
                        if (
                            prune_zero_effect_attacks_when_no_bench
                            and is_single_targeted_at_foe
                            and eff_total == 0.0
                            and not opp_has_alive_bench
                        ):
                            continue

                        if tgt_bucket == 2:
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
            state: `CompiledBattleState` containing `field_tensor [24]`, `roster_tensor [8, 84]`,
                and `moves_tensor [8, 4, 56]`.
            trainer_id: `'trainer_1'` or `'trainer_2'`.
            min_prior_threshold: Optional soft-pruning floor on `joint_prior_mat` (default `0.0`
                keeps all mechanically valid actions; set e.g. `0.05` to also prune extreme low-prior reads).

        Returns:
            `PrunedSideActionTensorMask` with `[N_valid, 2]` pruned choice pairs.
        """
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

        joint_prior = (np.outer(pri_a, pri_b) * joint_valid).astype(np.float32)
        if min_prior_threshold > 0.0:
            pruned_by_prior = (joint_prior >= min_prior_threshold).astype(np.float32)
            if np.sum(pruned_by_prior) > 0:
                joint_valid = joint_valid * pruned_by_prior
                joint_prior = joint_prior * joint_valid

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

