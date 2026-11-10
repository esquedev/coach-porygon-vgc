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

    def format_report(
        self,
        verbosity: str = "coach",
        max_recommendations: int = 5,
    ) -> str:
        """Format the advisory report at the requested verbosity / detail level.

        Args:
            verbosity: Detail level:
                - `'coach'` (default): Plain English, intuitive tactical summary for
                  the everyday player. No math jargon.
                - `'standard'`: Balanced tactical breakdown with probabilities, opponent
                  hypotheses, and top ranked plays.
                - `'scientific'`: Full mathematical and algorithmic transparency, explicitly
                  documenting all 5 pipeline steps, formulas, tensor dimensions, RNG distributions,
                  CVaR tail risk, and equilibrium proofs.
            max_recommendations: Maximum number of ranked recommendations to list.
        """
        v = str(verbosity or "coach").lower().strip()
        if v in ("simple", "brief", "casual", "player"):
            v = "coach"
        elif v in ("nerd", "full", "audit", "deep", "verbose"):
            v = "scientific"
        elif v not in ("coach", "standard", "scientific"):
            v = "coach"

        if v == "coach":
            return self._format_coach_report(max_recommendations)
        elif v == "scientific":
            return self._format_scientific_report(max_recommendations)
        return self._format_standard_report(max_recommendations)

    def _format_coach_report(self, max_recommendations: int = 5) -> str:
        """Generate a clean, plain-English coach summary for everyday players."""
        lines: List[str] = []
        best = self.best_recommendation
        first_h = self.hypothesis_evaluations[0] if self.hypothesis_evaluations else None
        slot_sp = first_h.compiled_state.slot_species if first_h else ()

        lines.append("=" * 88)
        lines.append("COACH PORYGON VGC — TURN COACH ADVICE (MATCH PLAY)")
        lines.append("=" * 88)

        # 1. Recommended Play
        lines.append("🎯 RECOMMENDED PLAY FOR THIS TURN:")
        lines.append(f"   👉 {best.description}")
        lines.append("")

        # 2. Why this play
        win_pct = best.win_turn_prob_vs_nash * 100.0
        lines.append("💡 WHY THIS PLAY:")
        lines.append(f"   • Win Probability: You have a {win_pct:.1f}% chance of coming out ahead this turn.")
        if best.nash_probability > 0.05:
            lines.append(
                f"   • Game-Theoretic Optimal: Our solver gives this play {best.nash_probability * 100.0:.1f}% "
                f"weight in the unexploitable game plan."
            )
        else:
            lines.append("   • Solid Security Floor: Protects you from opponent traps while advancing board position.")

        # Specific KO callouts
        t2_a_ko = float(self.posterior_faint_prob_for_best[4]) * 100.0
        t2_b_ko = float(self.posterior_faint_prob_for_best[5]) * 100.0
        t1_a_surv = float(self.posterior_survival_prob_for_best[0]) * 100.0
        t1_b_surv = float(self.posterior_survival_prob_for_best[1]) * 100.0

        sp_t2_a = slot_sp[4] if len(slot_sp) > 4 and slot_sp[4] else "Opponent Slot A"
        sp_t2_b = slot_sp[5] if len(slot_sp) > 5 and slot_sp[5] else "Opponent Slot B"
        sp_t1_a = slot_sp[0] if len(slot_sp) > 0 and slot_sp[0] else "Your Slot A"
        sp_t1_b = slot_sp[1] if len(slot_sp) > 1 and slot_sp[1] else "Your Slot B"

        if t2_a_ko > 50.0:
            lines.append(f"   • Pressure: High threat of knocking out {sp_t2_a} ({t2_a_ko:.1f}% KO chance).")
        if t2_b_ko > 50.0:
            lines.append(f"   • Pressure: High threat of knocking out {sp_t2_b} ({t2_b_ko:.1f}% KO chance).")
        lines.append(f"   • Team Safety: {sp_t1_a} has {t1_a_surv:.1f}% survival; {sp_t1_b} has {t1_b_surv:.1f}% survival.")
        lines.append("")

        # 3. What could go wrong (Worst-case counter)
        lines.append("⚠️ WHAT COULD GO WRONG (THE RISK):")
        lines.append(f"   • Hardest Opponent Counter: {best.worst_case_counter_description}")
        lines.append(
            f"   • Bad-Luck Floor (Worst 10% RNG): {best.expected_cvar_10_vs_nash:+.3f} utility "
            f"(even with misses or low damage rolls, this play minimizes downside risk)."
        )
        lines.append("")

        # 4. Opponent's most likely response
        if first_h and first_h.equilibrium.top_opponent_actions:
            lines.append("🔮 OPPONENT'S MOST LIKELY MOVE:")
            for rank, (_, _, desc_j, q_n, q_q) in enumerate(first_h.equilibrium.top_opponent_actions[:2], start=1):
                prob = max(q_n, q_q) * 100.0
                lines.append(f"   {rank}. (~{prob:.1f}% likelihood): {desc_j}")
            lines.append("")

        # 5. Field Survival & KO Odds
        lines.append("📊 FIELD SURVIVAL & KO PROBABILITIES:")
        lines.append(f"   • {sp_t1_a:16s} (You) : {t1_a_surv:5.1f}% Survives | {100.0 - t1_a_surv:5.1f}% KO Risk")
        lines.append(f"   • {sp_t1_b:16s} (You) : {t1_b_surv:5.1f}% Survives | {100.0 - t1_b_surv:5.1f}% KO Risk")
        lines.append(f"   • {sp_t2_a:16s} (Foe) : {100.0 - t2_a_ko:5.1f}% Survives | {t2_a_ko:5.1f}% KO Chance")
        lines.append(f"   • {sp_t2_b:16s} (Foe) : {100.0 - t2_b_ko:5.1f}% Survives | {t2_b_ko:5.1f}% KO Chance")
        lines.append("")

        # 6. Alternate Recommendations
        if len(self.recommendations) > 1:
            lines.append("🔄 BACKUP OPTIONS:")
            for rank, rec in enumerate(self.recommendations[1:max_recommendations], start=2):
                lines.append(
                    f"   #{rank} {rec.description} "
                    f"(Win: {rec.win_turn_prob_vs_nash * 100.0:.1f}%, Risk Score: {rec.expected_risk_utility_vs_nash:+.3f})"
                )
            lines.append("")

        lines.append("⚙️ CALCULATION AUDIT:")
        lines.append(
            f"   Simulated across {self.num_hypotheses} opponent build hypothesis(es) with "
            f"{self.num_simulations_per_hypothesis} discrete dice rolls per matchup."
        )
        lines.append("   (Tip: Run with --verbosity scientific to view full mathematical proofs and damage formulas).")
        lines.append("=" * 88)
        return "\n".join(lines)

    def _format_standard_report(self, max_recommendations: int = 5) -> str:
        """Generate the standard balanced tactical report."""
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

    def _format_scientific_report(self, max_recommendations: int = 5) -> str:
        """Generate the complete mathematical, algorithmic, and process audit report."""
        lines: List[str] = []
        first_h = self.hypothesis_evaluations[0] if self.hypothesis_evaluations else None
        b1_count = len(self.recommendations)
        b2_count = first_h.mask_trainer_2.pruned_choices.shape[0] if first_h else 0
        total_cells = b1_count * b2_count
        total_timelines = self.num_hypotheses * total_cells * self.num_simulations_per_hypothesis
        slot_sp = first_h.compiled_state.slot_species if first_h else ()

        lines.append("=" * 100)
        lines.append("COACH PORYGON VGC — COMPREHENSIVE MATHEMATICAL & PROCESS AUDIT REPORT")
        lines.append("=" * 100)
        lines.append(
            f"Execution Profile: {self.num_hypotheses} Opponent Hypothesis(es) | "
            f"Evaluated Matrix [{b1_count} x {b2_count}] ({total_cells} joint action pairs) | "
            f"K={self.num_simulations_per_hypothesis} MC threads/cell | "
            f"Total Simulated Timelines: {total_timelines:,}"
        )
        lines.append("=" * 100)

        # ---------------------------------------------------------------------
        # STEP 1: INGESTION & STAT ENGINE
        # ---------------------------------------------------------------------
        lines.append("🔬 STEP 1: INGESTION & 66-SP REGULATION M-C STAT PIPELINE")
        lines.append("  • Champions Stat Scaling (Level 50, mandatory 31 IVs, max 66 SP total, max 32 SP/stat):")
        lines.append("      HP   = floor(((2 * Base_HP + 31 + floor(SP_HP / 4)) * 50) / 100) + 60")
        lines.append("      Stat = floor((floor(((2 * Base_Stat + 31 + floor(SP_Stat / 4)) * 50) / 100) + 5) * Nature_Mult)")
        lines.append("  • In-Memory DuckDB Registry (`VGCDataRegistry`):")
        lines.append("      - Mechanistic base data queried dynamically from `pokedex` and `moves` views.")
        lines.append("      - Regional tournament usage weights queried from `tournament_team_slots` and `tournament_usage`.")
        lines.append("  • Bayesian Opponent Set Hypotheses:")
        for h in self.hypothesis_evaluations:
            lines.append(
                f"      [H{h.hypothesis_index + 1}] Weight w_{h.hypothesis_index + 1} = {h.posterior_weight * 100.0:5.2f}% | "
                f"Build: {h.summary_label}"
            )
        lines.append("-" * 100)

        # ---------------------------------------------------------------------
        # STEP 2: COMBINATORIC ACTION SPACE & PRUNING
        # ---------------------------------------------------------------------
        lines.append("🔬 STEP 2: COMBINATORIC ACTION SPACE & LOGICAL CONSTRAINT PRUNING")
        lines.append("  • Theoretical Unconstrained Action Space:")
        lines.append("      - Per-Pokémon Choice Tensor: 26 discrete actions (12 standard moves, 12 Mega moves, 2 bench switches).")
        lines.append("      - Per-Player Joint Action Space: 26 x 26 = 676 combinations.")
        lines.append("      - Full 2-Player Matchup Matrix: 676 x 676 = 456,976 cell evaluations.")
        lines.append("  • Constraint Elimination via `LogicalConstraintEngine`:")
        lines.append("      [!] Double-Protect Failure: consecutive Protect exponential decay ((1/3)^chain).")
        lines.append("      [!] Fake Out Turn Expiration: suppressed if active_turns > 0.")
        lines.append("      [!] Prankster Immunity: status moves into Dark-types blocked.")
        lines.append("      [!] Bench Collision Gate: simultaneous switches into identical bench slots forbidden.")
        lines.append("      [!] Single-Mega-Per-Side: simultaneous active mega evolutions strictly masked.")
        lines.append(
            f"  • Post-Pruning Dimension: trainer_1 B1 = {b1_count} actions (out of 676) | "
            f"trainer_2 B2 = {b2_count} actions (out of 676)."
        )
        lines.append("-" * 100)

        # ---------------------------------------------------------------------
        # STEP 3: DISCRETE-RNG VECTORIZED SIMULATION
        # ---------------------------------------------------------------------
        lines.append("🔬 STEP 3: DISCRETE-RNG DUAL-DRAW SPINNING-WHEEL & 5-PHASE CASCADE")
        lines.append("  • Dual-Draw Spinning-Wheel on [0, 100) with Counter-Based SplitMix64 Scrambling:")
        lines.append("      - Trigger condition: ((dart - window_start) % 100.0) < threshold_pct")
        lines.append("      - Completely eliminates top-of-distribution miss clustering; yields exact uniform miss distributions.")
        lines.append("  • Discrete Event Resolvers (Independent RNG Streams per Timeline):")
        lines.append("      - Accuracy: Move-specific accuracy scaled by stage ratios max(3, 3+b)/max(3, 3-b).")
        lines.append("      - Cartridge Critical Hits: Stage 0 (1/24 ~ 4.17%), Stage 1 (12.5%), Stage 2 (50.0%), Stage 3 (100.0%).")
        lines.append("      - 16 Cartridge Damage Rolls: Discrete uniform draw from {85, 86, ..., 100} / 100.0.")
        lines.append("      - Multi-Hit Counts: Standard (35% 2, 35% 3, 15% 4, 15% 5) vs Loaded Dice (50% 4, 50% 5).")
        lines.append("      - Mechanics: Focus Sash 1-HP clamp, Beat Up + Justified boost, recoil, Life Orb, secondary status.")
        lines.append("-" * 100)

        # ---------------------------------------------------------------------
        # STEP 4: DOWNSIDE RISK & CVAR_10
        # ---------------------------------------------------------------------
        lines.append("🔬 STEP 4: RISK-RESILIENT METRICS & BAD-LUCK FLOOR (CVaR_10)")
        lines.append("  • Expected Utility: E[U] = (1 / K) * sum_{k=1}^K U_k")
        lines.append("  • Worst 10% Tail Risk (Conditional Value at Risk):")
        lines.append("      CVaR_0.10[U] = (1 / (0.10 * K)) * sum_{k=1}^{floor(0.10 * K)} U_{(k)}  (where U_(1) <= ... <= U_(K))")
        lines.append("  • Risk-Adjusted Optimization Objective (lambda = 0.25):")
        lines.append("      U_risk = (1 - lambda) * E[U] + lambda * CVaR_0.10[U] = 0.75 * Mean + 0.25 * CVaR_10")
        lines.append("      (Guarantees that high-variance coin-flips do not dominate consistent safe strategies).")
        lines.append("-" * 100)

        # ---------------------------------------------------------------------
        # STEP 5: GAME-THEORETIC EQUILIBRIUM SOLVERS
        # ---------------------------------------------------------------------
        lines.append("🔬 STEP 5: GAME-THEORETIC SOLVERS (IEDS, ZERO-SUM NASH, LOGIT QRE)")
        if first_h:
            eq = first_h.equilibrium
            lines.append("  • Iterated Elimination of Dominated Strategies (IEDS):")
            lines.append(
                f"      - trainer_1: {eq.ieds.num_trainer_1_surviving} surviving, "
                f"{len(eq.ieds.eliminated_trainer_1)} strictly/weakly dominated actions eliminated."
            )
            lines.append(
                f"      - trainer_2: {eq.ieds.num_trainer_2_surviving} surviving, "
                f"{len(eq.ieds.eliminated_trainer_2)} strictly/weakly dominated actions eliminated."
            )
            lines.append(f"      - Convergence achieved in {eq.ieds.rounds_executed} recursive round(s).")
            lines.append("  • Zero-Sum Minimax / Nash Equilibrium (max_p min_q p^T U_risk q):")
            lines.append(
                f"      - Equilibrium Game Value v* = {eq.nash.game_value:+.4f} | "
                f"Security Level (Maximin) = {eq.nash.pure_maximin_value:+.4f} | "
                f"Ceiling (Minimax) = {eq.nash.pure_minimax_value:+.4f}"
            )
            lines.append(
                f"      - Solver Engine: {eq.nash.solver_used} (Exploitability Gap = {eq.nash.exploitability_gap:.6f})"
            )
            lines.append("  • Logit Quantal Response Equilibrium (Human Showdown Behavioral Model):")
            lines.append(
                f"      - Inverse Rationality Temperature beta = {eq.qre.rationality_beta:.1f} | "
                f"Expected Value E_QRE = {eq.qre.expected_value:+.4f} | "
                f"Fixed-point iterations = {eq.qre.iterations_run}"
            )
            lines.append("      - Probability formula: q_j proportional to exp(-beta * (p^T U_risk)_j)")
        lines.append("-" * 100)

        # ---------------------------------------------------------------------
        # STEP 6: RANKED ACTION BREAKDOWN
        # ---------------------------------------------------------------------
        lines.append("🔬 STEP 6: RANKED JOINT ACTION EVALUATION TABLE (TOP RECOMMENDATIONS)")
        lines.append(
            f"{'Rk':<3} | {'Idx':<7} | {'Action Description':<52} | "
            f"{'RiskEV':<7} | {'MeanEV':<7} | {'CVaR10':<7} | {'Win%':<6} | {'Nash%':<6} | {'QRE%':<6}"
        )
        lines.append("-" * 115)
        for rank, rec in enumerate(self.recommendations[:max_recommendations], start=1):
            pair_str = f"[{rec.choice_pair[0]:2d},{rec.choice_pair[1]:2d}]"
            short_desc = rec.description[:52]
            lines.append(
                f"#{rank:<2} | {pair_str:<7} | {short_desc:<52} | "
                f"{rec.expected_risk_utility_vs_nash:+6.3f} | {rec.expected_mean_utility_vs_nash:+6.3f} | "
                f"{rec.expected_cvar_10_vs_nash:+6.3f} | {rec.win_turn_prob_vs_nash * 100.0:5.1f}% | "
                f"{rec.nash_probability * 100.0:5.1f}% | {rec.qre_probability * 100.0:5.1f}%"
            )
            lines.append(
                f"     Worst Counter ({rec.worst_case_counter_utility:+.3f}): {rec.worst_case_counter_description}"
            )

        lines.append("-" * 100)
        lines.append("EXPECTED SLOT SURVIVAL & KO DISTRIBUTIONS FOR #1 ACTION:")
        for s_idx in (0, 1, 4, 5):
            sp_name = slot_sp[s_idx] if len(slot_sp) > s_idx and slot_sp[s_idx] else f"Slot{s_idx}"
            side_tag = "trainer_1" if s_idx < 4 else "trainer_2"
            ko_pct = float(self.posterior_faint_prob_for_best[s_idx]) * 100.0
            surv_pct = float(self.posterior_survival_prob_for_best[s_idx]) * 100.0
            lines.append(
                f"  Slot {s_idx} ({side_tag} - {sp_name:16s}): Survival = {surv_pct:5.1f}% | "
                f"KO Probability = {ko_pct:5.1f}%"
            )
        lines.append("=" * 100)
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
