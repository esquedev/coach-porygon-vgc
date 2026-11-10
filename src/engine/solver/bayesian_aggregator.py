# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Bayesian Top-K Opponent Hypothesis Aggregator & Turn Advisor
================================================================================

Bridges `OpponentSetInferencer` (DuckDB tournament usage + live battle speed/damage
constraints), `TurnStateCompiler`, `ShowdownTensorCompiler`, `VgcTensorStateMachine`,
and the Game-Theoretic Equilibrium Solver (`game_theory.py`).

When `trainer_2`'s items, 66-SP spreads, or moves are only partially revealed:
1. Generates the Top-$M$ joint opponent team hypotheses $\\{(H_m, w_m)\\}_{m=1}^M$
   ($\\sum_m w_m = 1$) respecting Regulation M-C Single-Mega-Per-Team rules.
2. Simulates `num_simulations` discrete-RNG turns per hypothesis on `VgcTensorStateMachine`.
3. Solves each hypothesis's Nash & Quantal Response Equilibrium and aggregates
   the posterior-weighted risk-resilient utilities, bad-luck `CVaR_10` floors,
   KO probabilities, and optimal action mix into a unified `BayesianTurnAdvice`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from engine.inference.set_inferencer import (
    InferredSetCandidate,
    OpponentSetInferencer,
    TeamInferenceReport,
)
from engine.parser.models import ParsedBattle, ParsedPokemon
from engine.state.models import TurnState
from engine.state.state_compiler import TurnStateCompiler
from engine.vgc_tensor_core.compiler import CompiledBattleState, ShowdownTensorCompiler
from engine.vgc_tensor_core.logic_engine import PrunedSideActionTensorMask
from engine.vgc_tensor_core.state_machine import StepResult, VgcTensorStateMachine

from .game_theory import (
    ActionRecommendation,
    TurnEquilibriumResult,
    _to_numpy,
    decode_joint_action,
    format_equilibrium_coach_report,
    solve_turn_equilibrium,
)


@dataclass(frozen=True)
class OpponentHypothesisEvaluation:
    """Simulation and equilibrium evaluation for a single opponent team hypothesis $H_m$."""

    hypothesis_index: int
    posterior_weight: float
    summary_label: str
    turn_state: TurnState
    compiled_state: CompiledBattleState
    mask_trainer_1: PrunedSideActionTensorMask
    mask_trainer_2: PrunedSideActionTensorMask
    step_result: StepResult
    equilibrium: TurnEquilibriumResult


@dataclass(frozen=True)
class BayesianTurnAdvice:
    """End-to-end Bayesian & Game-Theoretic recommendation for `trainer_1`'s next turn.

    Attributes:
        num_hypotheses: Number of opponent build hypotheses $M$ evaluated.
        num_simulations_per_hypothesis: Discrete RNG repetitions $K$ simulated per hypothesis.
        recommendations: Ranked list of `ActionRecommendation` objects for `trainer_1`
            blended across all $M$ opponent hypotheses.
        hypothesis_evaluations: Individual `OpponentHypothesisEvaluation` results per hypothesis.
        posterior_faint_prob_for_best: Expected KO probability per roster slot `[8]` when
            `trainer_1` plays `best_recommendation` against `trainer_2`'s Nash counter-strategy.
        posterior_survival_prob_for_best: Expected survival probability per roster slot `[8]`
            when `trainer_1` plays `best_recommendation`.
    """

    num_hypotheses: int
    num_simulations_per_hypothesis: int
    recommendations: List[ActionRecommendation]
    hypothesis_evaluations: List[OpponentHypothesisEvaluation] = field(default_factory=list)
    posterior_faint_prob_for_best: np.ndarray = field(default_factory=lambda: np.zeros(8, dtype=np.float32))
    posterior_survival_prob_for_best: np.ndarray = field(default_factory=lambda: np.ones(8, dtype=np.float32))

    @property
    def best_recommendation(self) -> ActionRecommendation:
        """Return the #1 Bayesian + Risk-Resilient dominant strategy for `trainer_1`."""
        return self.recommendations[0]

    def format_report(self, max_recommendations: int = 5) -> str:
        """Format a complete Coach Porygon VGC advisory report."""
        lines: List[str] = []
        lines.append("=" * 96)
        lines.append(
            f"COACH PORYGON VGC — BAYESIAN TOP-{self.num_hypotheses} HYPOTHESIS & RISK-RESILIENT ADVISOR "
            f"(K={self.num_simulations_per_hypothesis} sims/hyp)"
        )
        lines.append("=" * 96)
        if len(self.hypothesis_evaluations) > 1:
            lines.append("OPPONENT (TRAINER_2) SET HYPOTHESES EVALUATED:")
            for h in self.hypothesis_evaluations:
                lines.append(
                    f"  [H{h.hypothesis_index + 1}] Weight={h.posterior_weight * 100.0:5.1f}% | "
                    f"NashVal={h.equilibrium.nash.game_value:+.3f} | {h.summary_label}"
                )
            lines.append("-" * 96)

        lines.append("BAYESIAN RISK-RESILIENT RECOMMENDATIONS FOR TRAINER_1:")
        for rank, rec in enumerate(self.recommendations[:max_recommendations], start=1):
            lines.append(f"  #{rank} [{rec.choice_pair[0]:2d}, {rec.choice_pair[1]:2d}] {rec.description}")
            lines.append(
                f"      RiskEV(Nash)={rec.expected_risk_utility_vs_nash:+.3f} | "
                f"MeanEV={rec.expected_mean_utility_vs_nash:+.3f} | "
                f"BadLuckFloor(CVaR10)={rec.expected_cvar_10_vs_nash:+.3f} | "
                f"WinTurn%={rec.win_turn_prob_vs_nash * 100.0:5.1f}% | "
                f"NashMix={rec.nash_probability * 100.0:4.1f}% | "
                f"QREMix={rec.qre_probability * 100.0:4.1f}%"
            )
            lines.append(
                f"      Worst Counter ({rec.worst_case_counter_utility:+.3f}): {rec.worst_case_counter_description}"
            )

        if self.hypothesis_evaluations:
            slot_sp = self.hypothesis_evaluations[0].compiled_state.slot_species
            lines.append("-" * 96)
            lines.append("EXPECTED SLOT SURVIVAL / KO ODDS ON #1 RECOMMENDED ACTION:")
            for s_idx in (0, 1, 4, 5):
                sp_name = slot_sp[s_idx] if len(slot_sp) > s_idx and slot_sp[s_idx] else f"Slot{s_idx}"
                side_tag = "trainer_1" if s_idx < 4 else "trainer_2"
                ko_pct = float(self.posterior_faint_prob_for_best[s_idx]) * 100.0
                surv_pct = float(self.posterior_survival_prob_for_best[s_idx]) * 100.0
                lines.append(
                    f"  Slot {s_idx} ({side_tag} - {sp_name:16s}): Survival={surv_pct:5.1f}% | KO={ko_pct:5.1f}%"
                )
        lines.append("=" * 96)
        return "\n".join(lines)


class CoachTurnAdvisor:
    """End-to-end Single-Turn VGC Decision Engine combining DuckDB Set Inference,
    Discrete-RNG Tensor Simulation, and Game-Theoretic Equilibrium Solving.
    """

    def __init__(
        self,
        backend: str = "torch",
        device: Any = None,
        risk_aversion_lambda: float = 0.25,
        rationality_beta: float = 4.0,
    ) -> None:
        self.state_compiler = TurnStateCompiler()
        self.inferencer = OpponentSetInferencer(repo=self.state_compiler.repo)
        self.tensor_compiler = ShowdownTensorCompiler(
            registry=self.state_compiler.registry,
            backend=backend,
            device=device,
        )
        self.state_machine = VgcTensorStateMachine(
            backend=backend,
            device=device,
            risk_aversion_lambda=risk_aversion_lambda,
        )
        self.rationality_beta = float(rationality_beta)

    def generate_opponent_hypotheses(
        self,
        battle: ParsedBattle,
        max_hypotheses: int = 3,
    ) -> List[Tuple[TurnState, float, str]]:
        """Generate up to `max_hypotheses` posterior-weighted `TurnState` hypotheses for `trainer_2`.

        Varying builds are drawn for `trainer_2`'s active slots from `OpponentSetInferencer`
        while enforcing Regulation M-C Single-Mega-Per-Team rules.
        """
        battle_base = copy.deepcopy(battle)
        t2_report: Optional[TeamInferenceReport] = self.inferencer.infer_battle(battle_base)

        if max_hypotheses <= 1 or t2_report is None or not t2_report.candidates_by_species:
            ts = self.state_compiler.compile_turn_state(battle_base, run_inference=False)
            label = self._describe_trainer_2_active_sets(ts)
            return [(ts, 1.0, label)]

        # Identify trainer_2's active species (up to 2)
        active_idents = (
            list(battle_base.trainer_2.active_slots)
            if battle_base.trainer_2.active_slots
            else list(battle_base.trainer_2.leads)
        )
        active_cand_lists: List[Tuple[str, List[InferredSetCandidate]]] = []
        for ident in active_idents[:2]:
            for sp_key, cands in t2_report.candidates_by_species.items():
                if sp_key.lower() == ident.lower() or ident.lower().startswith(sp_key.lower()):
                    if cands:
                        active_cand_lists.append((sp_key, cands[:max_hypotheses]))
                    break

        if not active_cand_lists:
            ts = self.state_compiler.compile_turn_state(battle_base, run_inference=False)
            return [(ts, 1.0, self._describe_trainer_2_active_sets(ts))]

        # Build joint combinations across active_cand_lists and rank by product of posterior probabilities
        combos: List[Tuple[float, Dict[str, ParsedPokemon]]] = []
        if len(active_cand_lists) == 1:
            sp_a, cands_a = active_cand_lists[0]
            for c_a in cands_a:
                combos.append((max(1e-4, float(c_a.posterior_probability)), {sp_a: c_a.pokemon}))
        else:
            (sp_a, cands_a), (sp_b, cands_b) = active_cand_lists[0], active_cand_lists[1]
            for c_a in cands_a:
                for c_b in cands_b:
                    # Enforce Single-Mega-Per-Team across the two active candidates
                    if c_a.pokemon.mega_stone and c_b.pokemon.mega_stone:
                        continue
                    w = max(1e-4, float(c_a.posterior_probability)) * max(
                        1e-4, float(c_b.posterior_probability)
                    )
                    combos.append((w, {sp_a: c_a.pokemon, sp_b: c_b.pokemon}))

        combos.sort(key=lambda pair: pair[0], reverse=True)
        selected = combos[:max_hypotheses]
        if not selected:
            ts = self.state_compiler.compile_turn_state(battle_base, run_inference=False)
            return [(ts, 1.0, self._describe_trainer_2_active_sets(ts))]

        total_w = sum(w for w, _ in selected)
        hypotheses: List[Tuple[TurnState, float, str]] = []
        for raw_w, override_map in selected:
            b_copy = copy.deepcopy(battle_base)
            for sp_key, pkm_cand in override_map.items():
                b_copy.trainer_2.pokemon_sets[sp_key] = copy.deepcopy(pkm_cand)
            ts_m = self.state_compiler.compile_turn_state(b_copy, run_inference=False)
            norm_w = float(raw_w / max(1e-12, total_w))
            hypotheses.append((ts_m, norm_w, self._describe_trainer_2_active_sets(ts_m)))

        return hypotheses

    @staticmethod
    def _describe_trainer_2_active_sets(turn_state: TurnState) -> str:
        """Create a compact summary string of `trainer_2`'s active Pokémon builds."""
        parts: List[str] = []
        for mon in turn_state.trainer_2.active_slots:
            if mon is None:
                continue
            item_s = mon.item or "NoItem"
            ab_s = mon.ability or "UnknownAbility"
            nat_s = mon.nature or "Hardy"
            parts.append(f"{mon.species} @ {item_s} ({ab_s}, {nat_s})")
        return " + ".join(parts) if parts else "trainer_2 default roster"

    def advise_turn_state(
        self,
        turn_state: TurnState,
        num_simulations: int = 256,
        min_prior_threshold: float = 0.0,
        rng_seed: int = 42,
        top_k_recommendations: int = 10,
    ) -> BayesianTurnAdvice:
        """Run single-state discrete-RNG simulation and equilibrium solving on a `TurnState`."""
        compiled = self.tensor_compiler.compile_turn_state(turn_state)
        mask_t1, mask_t2, step_res = self.state_machine.simulate_pruned_turn(
            compiled_state=compiled,
            num_simulations=num_simulations,
            min_prior_threshold=min_prior_threshold,
            rng_seed=rng_seed,
        )
        eq_res = solve_turn_equilibrium(
            compiled_state=compiled,
            mask_trainer_1=mask_t1,
            mask_trainer_2=mask_t2,
            step_result=step_res,
            rationality_beta=self.rationality_beta,
            top_k=top_k_recommendations,
        )
        h_eval = OpponentHypothesisEvaluation(
            hypothesis_index=0,
            posterior_weight=1.0,
            summary_label=self._describe_trainer_2_active_sets(turn_state),
            turn_state=turn_state,
            compiled_state=compiled,
            mask_trainer_1=mask_t1,
            mask_trainer_2=mask_t2,
            step_result=step_res,
            equilibrium=eq_res,
        )

        best_i = eq_res.best_recommendation.action_index
        q_nash = eq_res.nash.trainer_2_strategy
        faint_np = np.asarray(_to_numpy(step_res.faint_prob), dtype=np.float64)  # [B1, B2, 8]
        best_faint = np.einsum("j,js->s", q_nash, faint_np[best_i]).astype(np.float32)

        return BayesianTurnAdvice(
            num_hypotheses=1,
            num_simulations_per_hypothesis=num_simulations,
            recommendations=eq_res.recommendations,
            hypothesis_evaluations=[h_eval],
            posterior_faint_prob_for_best=best_faint,
            posterior_survival_prob_for_best=(1.0 - best_faint).astype(np.float32),
        )

    def advise_battle(
        self,
        battle: ParsedBattle,
        max_hypotheses: int = 3,
        num_simulations: int = 256,
        min_prior_threshold: float = 0.0,
        rng_seed: int = 42,
        top_k_recommendations: int = 10,
    ) -> BayesianTurnAdvice:
        """Evaluate up to `max_hypotheses` inferred opponent builds and return Bayesian-blended advice."""
        hypotheses = self.generate_opponent_hypotheses(battle, max_hypotheses=max_hypotheses)
        if len(hypotheses) == 1:
            return self.advise_turn_state(
                turn_state=hypotheses[0][0],
                num_simulations=num_simulations,
                min_prior_threshold=min_prior_threshold,
                rng_seed=rng_seed,
                top_k_recommendations=top_k_recommendations,
            )

        # Compile first hypothesis to establish canonical trainer_1 pruned action space
        first_ts, _, _ = hypotheses[0]
        first_compiled = self.tensor_compiler.compile_turn_state(first_ts)
        canon_mask_t1 = self.state_machine.logic_engine.prune_side_26x26_tensor_actions(
            first_compiled, trainer_id="trainer_1", min_prior_threshold=min_prior_threshold
        )
        t1_choices_np = np.asarray(_to_numpy(canon_mask_t1.pruned_choices), dtype=np.int64)
        B1 = int(t1_choices_np.shape[0])

        # Accumulators across M hypotheses for each trainer_1 action i in 0..B1-1
        agg_nash_prob = np.zeros(B1, dtype=np.float64)
        agg_qre_prob = np.zeros(B1, dtype=np.float64)
        agg_risk_nash = np.zeros(B1, dtype=np.float64)
        agg_risk_qre = np.zeros(B1, dtype=np.float64)
        agg_mean_nash = np.zeros(B1, dtype=np.float64)
        agg_cvar_nash = np.zeros(B1, dtype=np.float64)
        agg_win_nash = np.zeros(B1, dtype=np.float64)
        agg_faint_slots = np.zeros((B1, 8), dtype=np.float64)

        worst_counter_val = np.full(B1, np.inf, dtype=np.float64)
        worst_counter_desc = ["" for _ in range(B1)]
        survived_any_ieds = np.zeros(B1, dtype=bool)

        eval_list: List[OpponentHypothesisEvaluation] = []

        for m_idx, (ts_m, weight_m, label_m) in enumerate(hypotheses):
            comp_m = self.tensor_compiler.compile_turn_state(ts_m)
            mask_t2_m = self.state_machine.logic_engine.prune_side_26x26_tensor_actions(
                comp_m, trainer_id="trainer_2", min_prior_threshold=min_prior_threshold
            )
            step_m = self.state_machine.step(
                F=comp_m.field_tensor,
                P=comp_m.roster_tensor,
                M_moves=comp_m.moves_tensor,
                trainer_1_choices=canon_mask_t1.pruned_choices,
                trainer_2_choices=mask_t2_m.pruned_choices,
                num_mc_samples=num_simulations,
                rng_seed=rng_seed + m_idx * 1009,
            )
            eq_m = solve_turn_equilibrium(
                compiled_state=comp_m,
                mask_trainer_1=canon_mask_t1,
                mask_trainer_2=mask_t2_m,
                step_result=step_m,
                rationality_beta=self.rationality_beta,
                top_k=B1,
            )
            eval_list.append(
                OpponentHypothesisEvaluation(
                    hypothesis_index=m_idx,
                    posterior_weight=weight_m,
                    summary_label=label_m,
                    turn_state=ts_m,
                    compiled_state=comp_m,
                    mask_trainer_1=canon_mask_t1,
                    mask_trainer_2=mask_t2_m,
                    step_result=step_m,
                    equilibrium=eq_m,
                )
            )

            # Map eq_m recommendations back by action_index i
            for rec in eq_m.recommendations:
                i = rec.action_index
                agg_nash_prob[i] += weight_m * rec.nash_probability
                agg_qre_prob[i] += weight_m * rec.qre_probability
                agg_risk_nash[i] += weight_m * rec.expected_risk_utility_vs_nash
                agg_risk_qre[i] += weight_m * rec.expected_risk_utility_vs_qre
                agg_mean_nash[i] += weight_m * rec.expected_mean_utility_vs_nash
                agg_cvar_nash[i] += weight_m * rec.expected_cvar_10_vs_nash
                agg_win_nash[i] += weight_m * rec.win_turn_prob_vs_nash
                if rec.survived_ieds:
                    survived_any_ieds[i] = True
                if rec.worst_case_counter_utility < worst_counter_val[i]:
                    worst_counter_val[i] = rec.worst_case_counter_utility
                    worst_counter_desc[i] = f"[H{m_idx + 1}] {rec.worst_case_counter_description}"

            q_nash_m = eq_m.nash.trainer_2_strategy
            faint_m = np.asarray(_to_numpy(step_m.faint_prob), dtype=np.float64)  # [B1, B2_m, 8]
            agg_faint_slots += weight_m * np.einsum("j,ijs->is", q_nash_m, faint_m)

        # Build blended ActionRecommendation list
        blended_recs: List[ActionRecommendation] = []
        for i in range(B1):
            pair_i = (int(t1_choices_np[i, 0]), int(t1_choices_np[i, 1]))
            desc_i = decode_joint_action(first_compiled, "trainer_1", pair_i)
            comp_score = (
                0.55 * float(agg_risk_nash[i])
                + 0.30 * float(agg_risk_qre[i])
                + 0.15 * float(worst_counter_val[i])
                + 0.25 * float(agg_nash_prob[i])
                + (0.05 if survived_any_ieds[i] else -0.25)
            )
            blended_recs.append(
                ActionRecommendation(
                    action_index=i,
                    choice_pair=pair_i,
                    description=desc_i,
                    survived_ieds=bool(survived_any_ieds[i]),
                    nash_probability=float(agg_nash_prob[i]),
                    qre_probability=float(agg_qre_prob[i]),
                    expected_risk_utility_vs_nash=float(agg_risk_nash[i]),
                    expected_risk_utility_vs_qre=float(agg_risk_qre[i]),
                    expected_mean_utility_vs_nash=float(agg_mean_nash[i]),
                    expected_cvar_10_vs_nash=float(agg_cvar_nash[i]),
                    worst_case_counter_utility=float(worst_counter_val[i]),
                    worst_case_counter_description=worst_counter_desc[i],
                    win_turn_prob_vs_nash=float(agg_win_nash[i]),
                    composite_score=comp_score,
                )
            )

        blended_recs.sort(key=lambda r: r.composite_score, reverse=True)
        best_i = blended_recs[0].action_index
        best_faint = agg_faint_slots[best_i].astype(np.float32)

        return BayesianTurnAdvice(
            num_hypotheses=len(hypotheses),
            num_simulations_per_hypothesis=num_simulations,
            recommendations=blended_recs[: max(1, min(top_k_recommendations, B1))],
            hypothesis_evaluations=eval_list,
            posterior_faint_prob_for_best=best_faint,
            posterior_survival_prob_for_best=(1.0 - best_faint).astype(np.float32),
        )
