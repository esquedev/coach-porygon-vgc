# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Heuristic Turning Point Detector (engine/tactics/turning_point_detector.py)

Automatically isolates the critical mid-game inflection turn where positional
collapse or decisive board swing occurred prior to the endgame clean-up phase.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from engine.tactics.showdown_parser import BattleHistory, TurnSnapshot


@dataclass
class TurningPointResult:
    """Result of the turning point heuristic evaluation across a BattleHistory."""

    turn_number: int
    impact_score: float
    snapshot: TurnSnapshot
    reasons: List[str] = field(default_factory=list)
    turn_scores: Dict[int, float] = field(default_factory=dict)


class TurningPointDetector:
    """
    Heuristic evaluator that scores each turn in a BattleHistory to isolate the Turning Point.

    Scoring Matrix:
    - Total turn HP delta > 40%: +30.0 pts (+10.0 pts if > 150% multi-slot swing)
    - Knockouts (KOs) of active pieces: +25.0 pts per KO
    - Offensive attacks absorbed by Protect/Detect or Redirection (Rage Powder/Follow Me): +20.0 pts
    - Climate/Terrain override or mid-game Mega Evolution speed/aura swing: +15.0 pts
    """

    def score_turn(self, snapshot: TurnSnapshot, total_turns: int) -> tuple[float, List[str]]:
        """
        Compute the heuristic impact score and diagnostic reasons for a single turn.

        Args:
            snapshot: TurnSnapshot to evaluate.
            total_turns: Total number of turns in the battle.

        Returns:
            Tuple of (numeric_score, list_of_reasons).
        """
        score = 0.0
        reasons: List[str] = []

        total_hp_delta = sum(snapshot.hp_deltas.values())
        if total_hp_delta > 0.40:
            score += 30.0
            reasons.append(f"High HP swing ({total_hp_delta * 100:.1f}% > 40%): +30 pts")
        if total_hp_delta > 1.50:
            score += 10.0
            reasons.append(f"Massive multi-slot damage trade ({total_hp_delta * 100:.1f}%): +10 pts")

        num_kos = len(snapshot.kos)
        if num_kos > 0:
            ko_pts = 25.0 * num_kos
            score += ko_pts
            reasons.append(f"{num_kos} central KO(s) ({', '.join(snapshot.kos)}): +{ko_pts:.0f} pts")

        if snapshot.protect_absorptions > 0 or snapshot.redirection_active:
            score += 20.0
            if snapshot.protect_absorptions > 0:
                reasons.append(
                    f"Offensive attack absorbed by Protect ({snapshot.protect_absorptions}x): +20 pts"
                )
            else:
                reasons.append("Active redirection (Rage Powder / Follow Me) tactical pivot: +20 pts")

        if snapshot.weather_changed or snapshot.terrain_changed:
            score += 15.0
            reasons.append(f"Climate/Terrain control shift ({snapshot.weather}): +15 pts")

        if snapshot.mega_evolutions and snapshot.turn_number > 1:
            score += 15.0
            reasons.append(
                f"Mid-game Mega Evolution activation ({', '.join(snapshot.mega_evolutions)}): +15 pts"
            )

        # Discount final clean-up turn if battle has >= 4 turns
        if total_turns >= 4 and snapshot.turn_number == total_turns:
            score *= 0.5
            reasons.append("Endgame cleanup discount (x0.5)")

        return round(score, 2), reasons

    def detect(self, history: BattleHistory) -> TurningPointResult:
        """
        Identify the primary turning point turn across a BattleHistory.

        Args:
            history: Reconstructed BattleHistory from ShowdownParser.

        Returns:
            TurningPointResult isolating the highest-impact turn before endgame.

        Raises:
            ValueError: If history contains no turns.
        """
        if not history or not history.turns:
            raise ValueError("Cannot detect turning point on an empty BattleHistory.")

        total_turns = len(history.turns)
        best_snapshot = history.turns[0]
        best_score = -1.0
        best_reasons: List[str] = []
        turn_scores: Dict[int, float] = {}

        for snap in history.turns:
            sc, r_list = self.score_turn(snap, total_turns)
            turn_scores[snap.turn_number] = sc
            if sc > best_score:
                best_score = sc
                best_snapshot = snap
                best_reasons = r_list

        return TurningPointResult(
            turn_number=best_snapshot.turn_number,
            impact_score=best_score,
            snapshot=best_snapshot,
            reasons=best_reasons,
            turn_scores=turn_scores,
        )

    def classify_turn_shift(
        self,
        snapshot: TurnSnapshot,
        delta_v_star: float = 0.0,
        equity_loss: float = 0.0,
        luck_delta: float = 0.0,
    ) -> str:
        """
        Classify the primary driver of a turn's board value derivative (dV*/dt):
        - 'Blunder' (Error Tactico): High player equity_loss (> 0.12) vs Nash optimal.
        - 'Luck_Swing' (Impacto de la Suerte): High absolute luck_delta (|luck_delta| > 0.18).
        - 'Brilliant_Read' (Prediccion Brillante): Positive dV* with zero equity loss and active Protect/Redirection/Mega pivot.
        - 'Standard_Trade' (Intercambio Estandar): Normal positional progression.

        Args:
            snapshot: TurnSnapshot of the turn being classified.
            delta_v_star: Derivative of game value V*(t) - V*(t-1).
            equity_loss: Player 1 deviation from Nash equilibrium (v* - V_real).
            luck_delta: Realized outcome minus expected payoff.

        Returns:
            Canonical classification string.
        """
        if equity_loss > 0.12:
            return "Blunder"
        if abs(luck_delta) > 0.18:
            return "Luck_Swing"
        if delta_v_star >= 0.10 or snapshot.protect_absorptions > 0 or snapshot.redirection_active or snapshot.mega_evolutions:
            if equity_loss <= 0.05:
                return "Brilliant_Read"
        return "Standard_Trade"


def detect_turning_point(history: BattleHistory) -> TurningPointResult:
    """
    Convenience entry point to detect the turning point in a BattleHistory.

    Args:
        history: Reconstructed BattleHistory from ShowdownParser.

    Returns:
        TurningPointResult for the decisive inflection turn.
    """
    detector = TurningPointDetector()
    return detector.detect(history)
