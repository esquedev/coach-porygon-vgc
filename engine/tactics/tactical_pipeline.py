# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Game-Theoretic Tactical Orchestrator (engine/tactics/tactical_pipeline.py)

Integrates ShowdownParser, TensorEncoder, PayoffBuilder, UncertaintyModel,
TurningPointDetector, ActionPruner (backed by ClientReplaySimulator in engine/turn_simulator.py),
NeuralEvaluator (CUDA GPU / CPU), NashSolver (HiGHS LP), standardized mistake_taxonomy.md
classification, and UnifiedCoachDatabase persistence.

Supports both Turning-Point isolation and All-Turns / Critical-Turns full match
trajectory evaluation (analyzing every turn's V* derivative, Nash strategy, and luck profile).
"""

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from engine.db import DEFAULT_AUDITS_JSONL, UnifiedCoachDatabase
from engine.gpu.payoff_builder import PayoffBuilder
from engine.gpu.tensor_encoder import TensorEncoder
from engine.gpu.uncertainty import UncertaintyModel, UncertaintyProfile
from engine.tactics.action_pruner import ActionPruner, PrunedActionLine
from engine.tactics.nash_solver import (
    NashSolver,
    compute_equity_loss,
)
from engine.tactics.neural_evaluator import NeuralEvaluator
from engine.tactics.showdown_parser import ShowdownParser, TurnSnapshot
from engine.tactics.turning_point_detector import TurningPointDetector


@dataclass
class TurnEvaluation:
    """Complete Game-Theoretic, Nash, and Uncertainty evaluation for a single turn."""

    turn_number: int
    impact_score: float
    reasons: List[str]
    p1_active: List[str]
    p2_active: List[str]
    p1_action_labels: List[str]
    p2_action_labels: List[str]
    payoff_matrix: List[List[float]]
    p1_nash_probs: List[float]
    p2_nash_probs: List[float]
    game_value: float
    delta_v_star: float
    observed_action_idx: int
    observed_action_label: str
    optimal_nash_idx: int
    optimal_nash_label: str
    equity_loss: float
    mistake_code: str
    cognitive_driver: str
    shift_classification: str
    uncertainty: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize single turn evaluation into a dictionary."""
        return {
            "turn_number": self.turn_number,
            "impact_score": self.impact_score,
            "reasons": self.reasons,
            "p1_active": self.p1_active,
            "p2_active": self.p2_active,
            "p1_action_labels": self.p1_action_labels,
            "p2_action_labels": self.p2_action_labels,
            "payoff_matrix": self.payoff_matrix,
            "p1_nash_probs": self.p1_nash_probs,
            "p2_nash_probs": self.p2_nash_probs,
            "game_value": self.game_value,
            "delta_v_star": self.delta_v_star,
            "observed_action_idx": self.observed_action_idx,
            "observed_action": self.observed_action_label,
            "optimal_nash_idx": self.optimal_nash_idx,
            "optimal_nash_action": self.optimal_nash_label,
            "equity_loss": self.equity_loss,
            "mistake_code": self.mistake_code,
            "cognitive_driver": self.cognitive_driver,
            "shift_classification": self.shift_classification,
            "uncertainty": self.uncertainty,
        }


@dataclass
class TacticalAuditResult:
    """Comprehensive output of a Game-Theoretic AGI replay audit across all turns and turning point."""

    audit_id: str
    match_id: str
    p1_name: str
    p2_name: str
    winner: str
    total_turns: int
    turning_point_turn: int
    impact_score: float
    turning_point_reasons: List[str]
    p1_active: List[str]
    p2_active: List[str]
    p1_action_labels: List[str]
    p2_action_labels: List[str]
    payoff_matrix: List[List[float]]
    p1_nash_probs: List[float]
    p2_nash_probs: List[float]
    game_value: float
    observed_action_idx: int
    observed_action_label: str
    optimal_nash_idx: int
    optimal_nash_label: str
    equity_loss: float
    mistake_code: str
    cognitive_driver: str
    execution_time_ms: float = 0.0
    device_used: str = "cpu"
    turn_scores: Dict[int, float] = field(default_factory=dict)
    uncertainty_profile: Dict[str, float] = field(default_factory=dict)
    all_turns_analysis: List[Dict[str, Any]] = field(default_factory=list)
    v_star_trajectory: Dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the TacticalAuditResult into a JSONL/SQLite-compatible dictionary."""
        return {
            "audit_id": self.audit_id,
            "match_id": self.match_id,
            "p1_name": self.p1_name,
            "p2_name": self.p2_name,
            "winner": self.winner,
            "total_turns": self.total_turns,
            "turn": self.turning_point_turn,
            "impact_score": self.impact_score,
            "reasons": self.turning_point_reasons,
            "p1_active": self.p1_active,
            "p2_active": self.p2_active,
            "p1_action_labels": self.p1_action_labels,
            "p2_action_labels": self.p2_action_labels,
            "observed_action": self.observed_action_label,
            "optimal_nash_action": self.optimal_nash_label,
            "game_value": self.game_value,
            "equity_loss": self.equity_loss,
            "mistake_code": self.mistake_code,
            "cognitive_driver": self.cognitive_driver,
            "payoff_matrix": self.payoff_matrix,
            "p1_nash_probs": self.p1_nash_probs,
            "p2_nash_probs": self.p2_nash_probs,
            "execution_time_ms": self.execution_time_ms,
            "device_used": self.device_used,
            "uncertainty_profile": self.uncertainty_profile,
            "all_turns_analysis": self.all_turns_analysis,
            "v_star_trajectory": self.v_star_trajectory,
        }


class TacticalPipeline:
    """
    End-to-end orchestrator for Game-Theoretic VGC replay auditing, single-turn solving,
    and GPU/CPU benchmarking.
    """

    def __init__(
        self,
        db: Optional[UnifiedCoachDatabase] = None,
        device: Optional[str] = None,
    ) -> None:
        """
        Initialize all tactical pipeline components.

        Args:
            db: Optional UnifiedCoachDatabase instance. Creates a new in-memory DB if omitted.
            device: Optional PyTorch device override ('cuda:0', 'cuda', or 'cpu').
        """
        self.parser = ShowdownParser()
        self.detector = TurningPointDetector()
        self.pruner = ActionPruner()
        self.evaluator = NeuralEvaluator(device=device)
        self.payoff_builder = PayoffBuilder(device=device)
        self.tensor_encoder = TensorEncoder(device=device)
        self.uncertainty_model = UncertaintyModel(device=device)
        self.solver = NashSolver()
        self.db = db if db is not None else UnifiedCoachDatabase()

    def _map_observed_action_index(
        self, snapshot: TurnSnapshot, p1_lines: List[PrunedActionLine]
    ) -> int:
        """Map the observed P1 turn actions in snapshot to one of the 5 canonical lines."""
        p1_moves = [a.move for a in snapshot.actions if a.actor_side == "p1"]
        if any(m == "Switch" for m in p1_moves):
            return 4
        if any(m in ("Protect", "Detect", "Quick Guard") for m in p1_moves):
            return 1
        if any(m in ("Tailwind", "Trick Room", "Reflect", "Fake Out") for m in p1_moves):
            return 3
        if snapshot.redirection_active and any(
            m in ("Iron Head", "Stomping Tantrum") for m in p1_moves
        ):
            return 0
        if any(m in ("Heat Wave", "Dazzling Gleam", "Earthquake") for m in p1_moves):
            return 2
        return 0 if len(p1_lines) > 0 else 0

    def _classify_mistake_taxonomy(
        self,
        snapshot: TurnSnapshot,
        observed_idx: int,
        optimal_idx: int,
        equity_loss: float,
        observed_line_risk: str = "Deterministic_Safe",
    ) -> Tuple[str, str]:
        """
        Map board events and Nash deviation to canonical mistake_taxonomy.md error codes
        and cognitive trap drivers, evaluating high-risk/high-reward tournament reads.
        """
        if snapshot.protect_absorptions > 0:
            return "TGT-01", "Tunnel_Vision"
        if snapshot.redirection_active and observed_idx == 0 and optimal_idx == 2:
            return "TGT-02", "Tunnel_Vision"
        if snapshot.mega_evolutions and observed_idx != optimal_idx:
            return "SPD-01", "Format_Divergence"
        if snapshot.terrain.lower() == "psychic":
            has_airborne = any("Flying" in getattr(s, "types", []) for s in snapshot.p1_slots)
            if has_airborne and equity_loss > 0.10:
                return "MEC-02", "Format_Divergence"
            return "MEC-01", "Format_Divergence"
        if observed_idx == 4 and equity_loss > 0.15:
            return "POS-01", "Autopilot"
        if equity_loss <= 0.05:
            if observed_line_risk == "High_Risk_High_Reward":
                return "TGT-01", "Tilt"
            return "TGT-01", "Tunnel_Vision"
        if observed_line_risk == "High_Risk_High_Reward":
            return "POS-02", "Greed"
        return "POS-02", "Greed"

    def solve_turn(
        self,
        snapshot: TurnSnapshot,
        total_turns: int = 1,
        prev_v_star: float = 0.0,
    ) -> TurnEvaluation:
        """
        Solve a single TurnSnapshot: encode tensor, compute GPU payoff matrix,
        quantify 16-roll uncertainty, solve Nash equilibrium, and classify tactical shift.

        Args:
            snapshot: TurnSnapshot to evaluate.
            total_turns: Total turns in match for heuristic weighting.
            prev_v_star: Previous turn's Nash game value v* to compute derivative dV*/dt.

        Returns:
            Populated TurnEvaluation object.
        """
        impact_score, reasons = self.detector.score_turn(snapshot, total_turns)
        p1_lines = self.pruner.prune_side_actions(snapshot, side="p1")
        p2_lines = self.pruner.prune_side_actions(snapshot, side="p2")

        payoff_mat = self.evaluator.evaluate_payoff_matrix(snapshot, p1_lines, p2_lines)
        nash_sol = self.solver.solve(payoff_mat)

        observed_idx = self._map_observed_action_index(snapshot, p1_lines)
        optimal_idx = nash_sol.dominant_p1_idx
        eq_loss = compute_equity_loss(
            payoff_mat, observed_idx, nash_sol.p2_probs, nash_sol.game_value
        )
        observed_risk = getattr(p1_lines[observed_idx], "risk_classification", "Deterministic_Safe")
        mistake_code, cognitive_driver = self._classify_mistake_taxonomy(
            snapshot, observed_idx, optimal_idx, eq_loss, observed_line_risk=observed_risk
        )

        # Quantify 16-roll x Crit x Accuracy uncertainty on the dominant matchup
        dom_p2_idx = nash_sol.dominant_p2_idx
        unc_profile: UncertaintyProfile = self.uncertainty_model.evaluate_turn_uncertainty(
            snapshot, p1_lines[optimal_idx], p2_lines[dom_p2_idx]
        )

        v_star = round(float(nash_sol.game_value), 4)
        delta_v = round(v_star - float(prev_v_star), 4)
        shift_type = self.detector.classify_turn_shift(
            snapshot,
            delta_v_star=delta_v,
            equity_loss=float(eq_loss),
            luck_delta=unc_profile.luck_delta,
        )

        return TurnEvaluation(
            turn_number=snapshot.turn_number,
            impact_score=impact_score,
            reasons=reasons,
            p1_active=[s.species for s in snapshot.p1_slots],
            p2_active=[s.species for s in snapshot.p2_slots],
            p1_action_labels=[line.label for line in p1_lines],
            p2_action_labels=[line.label for line in p2_lines],
            payoff_matrix=payoff_mat.tolist(),
            p1_nash_probs=[round(float(x), 4) for x in nash_sol.p1_probs],
            p2_nash_probs=[round(float(x), 4) for x in nash_sol.p2_probs],
            game_value=v_star,
            delta_v_star=delta_v,
            observed_action_idx=observed_idx,
            observed_action_label=p1_lines[observed_idx].label,
            optimal_nash_idx=optimal_idx,
            optimal_nash_label=p1_lines[optimal_idx].label,
            equity_loss=round(float(eq_loss), 4),
            mistake_code=mistake_code,
            cognitive_driver=cognitive_driver,
            shift_classification=shift_type,
            uncertainty=unc_profile.to_dict(),
        )

    def run_audit(
        self,
        raw_log: str,
        auto_persist: bool = True,
        jsonl_path: Optional[Union[str, Path]] = None,
        analyze_all_turns: bool = True,
    ) -> TacticalAuditResult:
        """
        Execute the Game-Theoretic audit on a raw Showdown battle log.
        Evaluates all turns (or critical turns) as well as isolating the primary Turning Point.

        Args:
            raw_log: Raw plain-text or pipe-delimited Showdown battle log.
            auto_persist: Whether to atomically persist to JSONL and index into SQLite RAM.
            jsonl_path: Optional override path for the .jsonl target file.
            analyze_all_turns: When True (default), computes full Nash & Uncertainty for every turn.

        Returns:
            Populated TacticalAuditResult instance.
        """
        t_start = time.perf_counter()

        # 1. Parse replay
        history = self.parser.parse(raw_log)
        total_turns = len(history.turns)

        # 2. Isolate primary Turning Point
        tp = self.detector.detect(history)

        # 3. Evaluate all turns (or Turning Point) across the battle trajectory
        all_evals: List[TurnEvaluation] = []
        v_star_traj: Dict[int, float] = {}
        prev_v = 0.0
        tp_eval: Optional[TurnEvaluation] = None

        if analyze_all_turns:
            for snap in history.turns:
                t_ev = self.solve_turn(snap, total_turns=total_turns, prev_v_star=prev_v)
                prev_v = t_ev.game_value
                v_star_traj[snap.turn_number] = t_ev.game_value
                all_evals.append(t_ev)
                if snap.turn_number == tp.turn_number:
                    tp_eval = t_ev

        if tp_eval is None:
            tp_eval = self.solve_turn(tp.snapshot, total_turns=total_turns, prev_v_star=0.0)
            v_star_traj[tp.turn_number] = tp_eval.game_value
            all_evals.append(tp_eval)

        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        audit_id = f"AUD-{history.match_id}-T{tp.turn_number}"

        result = TacticalAuditResult(
            audit_id=audit_id,
            match_id=history.match_id,
            p1_name=history.p1_name,
            p2_name=history.p2_name,
            winner=history.winner,
            total_turns=total_turns,
            turning_point_turn=tp.turn_number,
            impact_score=tp.impact_score,
            turning_point_reasons=tp.reasons,
            p1_active=tp_eval.p1_active,
            p2_active=tp_eval.p2_active,
            p1_action_labels=tp_eval.p1_action_labels,
            p2_action_labels=tp_eval.p2_action_labels,
            payoff_matrix=tp_eval.payoff_matrix,
            p1_nash_probs=tp_eval.p1_nash_probs,
            p2_nash_probs=tp_eval.p2_nash_probs,
            game_value=tp_eval.game_value,
            observed_action_idx=tp_eval.observed_action_idx,
            observed_action_label=tp_eval.observed_action_label,
            optimal_nash_idx=tp_eval.optimal_nash_idx,
            optimal_nash_label=tp_eval.optimal_nash_label,
            equity_loss=tp_eval.equity_loss,
            mistake_code=tp_eval.mistake_code,
            cognitive_driver=tp_eval.cognitive_driver,
            execution_time_ms=elapsed_ms,
            device_used=str(self.evaluator.device),
            turn_scores=tp.turn_scores,
            uncertainty_profile=tp_eval.uncertainty,
            all_turns_analysis=[ev.to_dict() for ev in all_evals],
            v_star_trajectory=v_star_traj,
        )

        # Persist to JSONL + SQLite In-Memory
        if auto_persist:
            target = Path(jsonl_path) if jsonl_path is not None else DEFAULT_AUDITS_JSONL
            self.db.append_audit_record(result.to_dict(), target_path=target)

        return result

    def audit_replay(
        self,
        raw_log: str,
        auto_persist: bool = True,
        jsonl_path: Optional[Union[str, Path]] = None,
        analyze_all_turns: bool = True,
    ) -> TacticalAuditResult:
        """Canonical alias for run_audit specified in the physical architecture plan."""
        return self.run_audit(
            raw_log=raw_log,
            auto_persist=auto_persist,
            jsonl_path=jsonl_path,
            analyze_all_turns=analyze_all_turns,
        )

    def run_benchmark(self, raw_log: str, batch_size: int = 64) -> Dict[str, Any]:
        """
        Execute a comprehensive GPU/CPU latency and throughput benchmark across a replay log.

        Args:
            raw_log: Showdown battle log string to extract canonical turn snapshots from.
            batch_size: Number of simultaneous turn boards to benchmark in parallel.

        Returns:
            Dictionary with full match audit latency, per-turn latency, and GPU batch throughput.
        """
        history = self.parser.parse(raw_log)
        tp = self.detector.detect(history)

        t0 = time.perf_counter()
        audit_res = self.run_audit(raw_log, auto_persist=False, analyze_all_turns=True)
        full_match_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        gpu_bench = self.payoff_builder.benchmark_throughput(tp.snapshot, batch_size=batch_size)
        return {
            "status": "OK",
            "match_id": history.match_id,
            "total_turns_analyzed": len(history.turns),
            "full_match_audit_ms": full_match_ms,
            "per_turn_avg_ms": round(full_match_ms / max(1, len(history.turns)), 2),
            "turning_point_turn": audit_res.turning_point_turn,
            "gpu_batch_benchmark": gpu_bench,
        }


def audit_showdown_log(
    raw_log: str,
    auto_persist: bool = True,
    db: Optional[UnifiedCoachDatabase] = None,
    jsonl_path: Optional[Union[str, Path]] = None,
    analyze_all_turns: bool = True,
) -> TacticalAuditResult:
    """
    Master agentic API entry point to audit a Showdown Regulation M-C replay log.

    Args:
        raw_log: Raw Showdown battle log text.
        auto_persist: Whether to write the resulting audit to data/tactical_audits.jsonl
                      and index it in UnifiedCoachDatabase.
        db: Optional existing UnifiedCoachDatabase instance.
        jsonl_path: Optional custom path for JSONL output.
        analyze_all_turns: Whether to evaluate all turns in the battle (default True).

    Returns:
        TacticalAuditResult containing all-turns trajectory, Turning Point, Nash solution,
        UncertaintyProfile, and diagnostics.
    """
    pipeline = TacticalPipeline(db=db)
    return pipeline.run_audit(
        raw_log,
        auto_persist=auto_persist,
        jsonl_path=jsonl_path,
        analyze_all_turns=analyze_all_turns,
    )
