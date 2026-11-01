# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Game-Theoretic Tactical Orchestrator (engine/tactics/tactical_pipeline.py)

Integrates ShowdownParser, TurningPointDetector, ActionPruner (backed by
ClientReplaySimulator in engine/turn_simulator.py), NeuralEvaluator (RTX 3060 GPU),
NashSolver (HiGHS LP), standardized mistake_taxonomy.md classification, and
UnifiedCoachDatabase persistence.
"""

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from engine.db import DEFAULT_AUDITS_JSONL, UnifiedCoachDatabase
from engine.tactics.action_pruner import ActionPruner, PrunedActionLine
from engine.tactics.nash_solver import (
    NashSolver,
    compute_equity_loss,
)
from engine.tactics.neural_evaluator import NeuralEvaluator
from engine.tactics.showdown_parser import ShowdownParser, TurnSnapshot
from engine.tactics.turning_point_detector import TurningPointDetector


@dataclass
class TacticalAuditResult:
    """Comprehensive output of a Game-Theoretic AGI replay audit."""

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
        }


class TacticalPipeline:
    """
    End-to-end orchestrator for Game-Theoretic VGC replay auditing.
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
            device: Optional PyTorch device override ('cuda:0' or 'cpu').
        """
        self.parser = ShowdownParser()
        self.detector = TurningPointDetector()
        self.pruner = ActionPruner()
        self.evaluator = NeuralEvaluator(device=device)
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
        # If redirection was active on opponent side and a single-target move was redirected
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
    ) -> Tuple[str, str]:
        """
        Map board events and Nash deviation to canonical mistake_taxonomy.md error codes
        and cognitive trap drivers.
        """
        if snapshot.protect_absorptions > 0:
            return "TGT-01", "Tunnel_Vision"
        if snapshot.redirection_active and observed_idx == 0 and optimal_idx == 2:
            return "TGT-02", "Tunnel_Vision"
        if snapshot.mega_evolutions and observed_idx != optimal_idx:
            return "SPD-01", "Format_Divergence"
        if snapshot.terrain.lower() == "psychic":
            return "MEC-01", "Format_Divergence"
        if observed_idx == 4 and equity_loss > 0.15:
            return "POS-01", "Autopilot"
        if equity_loss <= 0.05:
            return "TGT-01", "Tunnel_Vision"
        return "POS-02", "Greed"

    def run_audit(
        self,
        raw_log: str,
        auto_persist: bool = True,
        jsonl_path: Optional[Union[str, Path]] = None,
    ) -> TacticalAuditResult:
        """
        Execute the 7-stage Game-Theoretic audit on a raw Showdown battle log.

        Args:
            raw_log: Raw plain-text or pipe-delimited Showdown battle log.
            auto_persist: Whether to atomically persist to JSONL and index into SQLite RAM.
            jsonl_path: Optional override path for the .jsonl target file.

        Returns:
            Populated TacticalAuditResult instance.
        """
        t_start = time.perf_counter()

        # 1. Parse replay
        history = self.parser.parse(raw_log)

        # 2. Isolate Turning Point
        tp = self.detector.detect(history)
        snap = tp.snapshot

        # 3. Prune joint action space (81 -> 5x5)
        p1_lines = self.pruner.prune_side_actions(snap, side="p1")
        p2_lines = self.pruner.prune_side_actions(snap, side="p2")

        # 4. Evaluate 5x5 payoff matrix via ClientReplaySimulator + GPU ValueNet
        payoff_mat = self.evaluator.evaluate_payoff_matrix(snap, p1_lines, p2_lines)

        # 5. Solve Simultaneous Mixed-Strategy Nash Equilibrium (HiGHS LP)
        nash_sol = self.solver.solve(payoff_mat)

        observed_idx = self._map_observed_action_index(snap, p1_lines)
        optimal_idx = nash_sol.dominant_p1_idx
        eq_loss = compute_equity_loss(
            payoff_mat, observed_idx, nash_sol.p2_probs, nash_sol.game_value
        )

        # 6. Map to mistake_taxonomy.md
        mistake_code, cognitive_driver = self._classify_mistake_taxonomy(
            snap, observed_idx, optimal_idx, eq_loss
        )

        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        audit_id = f"AUD-{history.match_id}-T{tp.turn_number}"

        result = TacticalAuditResult(
            audit_id=audit_id,
            match_id=history.match_id,
            p1_name=history.p1_name,
            p2_name=history.p2_name,
            winner=history.winner,
            total_turns=len(history.turns),
            turning_point_turn=tp.turn_number,
            impact_score=tp.impact_score,
            turning_point_reasons=tp.reasons,
            p1_active=[s.species for s in snap.p1_slots],
            p2_active=[s.species for s in snap.p2_slots],
            p1_action_labels=[line.label for line in p1_lines],
            p2_action_labels=[line.label for line in p2_lines],
            payoff_matrix=payoff_mat.tolist(),
            p1_nash_probs=[round(float(x), 4) for x in nash_sol.p1_probs],
            p2_nash_probs=[round(float(x), 4) for x in nash_sol.p2_probs],
            game_value=round(float(nash_sol.game_value), 4),
            observed_action_idx=observed_idx,
            observed_action_label=p1_lines[observed_idx].label,
            optimal_nash_idx=optimal_idx,
            optimal_nash_label=p1_lines[optimal_idx].label,
            equity_loss=round(float(eq_loss), 4),
            mistake_code=mistake_code,
            cognitive_driver=cognitive_driver,
            execution_time_ms=elapsed_ms,
            device_used=str(self.evaluator.device),
            turn_scores=tp.turn_scores,
        )

        # 7. Persist to JSONL + SQLite In-Memory
        if auto_persist:
            target = Path(jsonl_path) if jsonl_path is not None else DEFAULT_AUDITS_JSONL
            self.db.append_audit_record(result.to_dict(), target_path=target)

        return result


def audit_showdown_log(
    raw_log: str,
    auto_persist: bool = True,
    db: Optional[UnifiedCoachDatabase] = None,
    jsonl_path: Optional[Union[str, Path]] = None,
) -> TacticalAuditResult:
    """
    Master agentic API entry point to audit a Showdown Regulation M-C replay log.

    Args:
        raw_log: Raw Showdown battle log text.
        auto_persist: Whether to write the resulting audit to data/tactical_audits.jsonl
                      and index it in UnifiedCoachDatabase.
        db: Optional existing UnifiedCoachDatabase instance.
        jsonl_path: Optional custom path for JSONL output.

    Returns:
        TacticalAuditResult containing the Turning Point, 5x5 Nash solution, and diagnostics.
    """
    pipeline = TacticalPipeline(db=db)
    return pipeline.run_audit(raw_log, auto_persist=auto_persist, jsonl_path=jsonl_path)
