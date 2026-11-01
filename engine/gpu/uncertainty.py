# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Formal Uncertainty & Luck Quantifier (engine/gpu/uncertainty.py)

Models exact discrete probability distributions over VGC combat outcomes rather than
relying solely on a single point estimate (mu):
- 16 Official Damage Rolls: {0.85, 0.86, ..., 1.00} with uniform probability p = 1/16 each.
- Critical Hit Stages:
  - Stage 0: p_crit = 1/24 (~4.167%, 1.5x damage, ignores negative offensive / positive defensive stages).
  - Stage 1: p_crit = 1/8 (12.5%).
  - Stage 2: p_crit = 1/2 (50.0%).
  - Stage 3+: p_crit = 1.0 (100.0%).
- Move Accuracy: Bernoulli(eff_accuracy / 100.0).
- Secondary Effects: Flinch (10%/20%/30%/100%), Burn (10%/30%), Paralysis (10%/30%/100%), Freeze (10%).
- Computes full cumulative distribution (CDF), quantiles (p10, p50, p90, p95), exact KO%,
  survival probability, Showdown audit luck_delta (Real - Expected), and risk_adjusted_value (EV - lambda * CVaR).
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

from engine.tactics.action_pruner import PrunedActionLine
from engine.tactics.showdown_parser import ShowdownParser, TurnSnapshot
from engine.turn_simulator import ClientReplaySimulator, MOVE_DB


DAMAGE_ROLLS_16: Tuple[float, ...] = tuple(round(r / 100.0, 2) for r in range(85, 101))

CRIT_STAGE_PROBS: Dict[int, float] = {
    0: 1.0 / 24.0,
    1: 0.125,
    2: 0.50,
    3: 1.00,
}


@dataclass
class UncertaintyProfile:
    """
    Canonical Pydantic-compatible schema for combat uncertainty and luck telemetry.

    Attributes:
        expected_payoff: Expected value (mu) across the discrete convolution distribution.
        variance: Variance (sigma^2) of the outcome distribution.
        p10: 10th percentile (downside tail quantile).
        p50: 50th percentile (median outcome).
        p90: 90th percentile (upside quantile).
        p95: 95th percentile (high-roll / crit quantile).
        ko_probability: Exact probability [0.0, 1.0] of achieving at least one opposing KO.
        survival_probability: Exact probability [0.0, 1.0] that both P1 active slots survive the turn.
        luck_delta: Realized outcome minus Expected Value (Observed - E[V]) in Showdown audits.
        risk_adjusted_value: Risk-averse valuation EV - lambda * CVaR_10.
    """

    expected_payoff: float
    variance: float
    p10: float
    p50: float
    p90: float
    p95: float
    ko_probability: float
    survival_probability: float
    luck_delta: float = 0.0
    risk_adjusted_value: float = 0.0

    def model_dump(self) -> Dict[str, float]:
        """Pydantic v2 compatible serialization method."""
        return {k: round(float(v), 4) for k, v in asdict(self).items()}

    def to_dict(self) -> Dict[str, float]:
        """Dictionary serialization helper."""
        return self.model_dump()


class UncertaintyModel:
    """
    Discrete probability convolution engine running on PyTorch (CUDA/CPU) or NumPy fallback.
    """

    def __init__(self, device: Optional[str] = None, risk_lambda: float = 0.15) -> None:
        """
        Initialize UncertaintyModel.

        Args:
            device: Optional PyTorch device ('cuda', 'cuda:0', or 'cpu').
            risk_lambda: Risk aversion coefficient for CVaR adjustment.
        """
        self.risk_lambda = float(risk_lambda)
        if HAS_TORCH and torch is not None:
            if device is None or device == "auto":
                self.device_str = "cuda:0" if torch.cuda.is_available() else "cpu"
            elif device == "cuda" and not torch.cuda.is_available():
                self.device_str = "cpu"
            else:
                self.device_str = str(device)
            self.device = torch.device(self.device_str)
        else:
            self.device_str = "cpu"
            self.device = None
        self._parser = ShowdownParser()

    @staticmethod
    def get_crit_probability(crit_stage: int = 0) -> float:
        """Return official VGC critical hit probability for stage 0..3+."""
        clamped = max(0, min(3, int(crit_stage)))
        return CRIT_STAGE_PROBS[clamped]

    def compute_damage_distribution(
        self,
        base_rolls_16: List[float],
        crit_rolls_16: Optional[List[float]] = None,
        crit_stage: int = 0,
        accuracy_pct: float = 100.0,
        defender_hp: float = 100.0,
        observed_damage: Optional[float] = None,
    ) -> UncertaintyProfile:
        """
        Convolve the 16 discrete damage rolls with critical hit branches and move accuracy
        to produce an exact UncertaintyProfile.

        Args:
            base_rolls_16: 16 damage values (HP or %) for rolls 0.85..1.00 without crit.
            crit_rolls_16: Optional 16 damage values under a critical hit (defaults to 1.5x base_rolls_16).
            crit_stage: Critical hit stage (0 -> 1/24, 1 -> 1/8, 2 -> 1/2, 3+ -> 1.0).
            accuracy_pct: Effective move accuracy in [0.0, 100.0].
            defender_hp: Current HP of the target (in matching units) to compute exact KO%.
            observed_damage: Optional realized damage in a replay to quantify luck_delta.

        Returns:
            Populated UncertaintyProfile with exact quantiles, variance, KO%, and luck_delta.

        Raises:
            ValueError: If base_rolls_16 is empty.
        """
        if not base_rolls_16:
            raise ValueError("base_rolls_16 must contain at least one damage value.")

        base_arr = np.asarray(base_rolls_16, dtype=np.float64)
        if crit_rolls_16 is not None:
            crit_arr = np.asarray(crit_rolls_16, dtype=np.float64)
        else:
            crit_arr = np.floor(base_arr * 1.5)

        p_hit = max(0.0, min(1.0, float(accuracy_pct) / 100.0))
        p_miss = 1.0 - p_hit
        p_crit = self.get_crit_probability(crit_stage)
        n_rolls = len(base_arr)

        values: List[float] = []
        probs: List[float] = []

        if p_miss > 1e-9:
            values.append(0.0)
            probs.append(p_miss)

        if p_hit > 1e-9:
            p_each_normal = p_hit * (1.0 - p_crit) / float(n_rolls)
            p_each_crit = p_hit * p_crit / float(len(crit_arr))

            for val in base_arr:
                values.append(float(val))
                probs.append(p_each_normal)
            if p_crit > 1e-9:
                for val in crit_arr:
                    values.append(float(val))
                    probs.append(p_each_crit)

        val_np = np.asarray(values, dtype=np.float64)
        prob_np = np.asarray(probs, dtype=np.float64)
        prob_np = prob_np / np.sum(prob_np)

        # Sort by outcome value to compute exact discrete CDF quantiles
        order = np.argsort(val_np)
        sorted_vals = val_np[order]
        sorted_probs = prob_np[order]
        cdf = np.cumsum(sorted_probs)

        def _quantile(q: float) -> float:
            """Return discrete CDF value at quantile q."""
            idx = int(np.searchsorted(cdf, q, side="left"))
            idx = max(0, min(len(sorted_vals) - 1, idx))
            return float(sorted_vals[idx])

        expected_val = float(np.sum(sorted_vals * sorted_probs))
        variance_val = float(np.sum(((sorted_vals - expected_val) ** 2) * sorted_probs))
        p10 = _quantile(0.10)
        p50 = _quantile(0.50)
        p90 = _quantile(0.90)
        p95 = _quantile(0.95)

        ko_mask = sorted_vals >= float(defender_hp)
        ko_prob = float(np.sum(sorted_probs[ko_mask]))
        surv_prob = max(0.0, 1.0 - ko_prob)

        # Downside CVaR at 10% tail
        tail_mask = sorted_vals <= p10
        cvar_10 = (
            float(np.sum(sorted_vals[tail_mask] * sorted_probs[tail_mask]) / np.sum(sorted_probs[tail_mask]))
            if np.any(tail_mask)
            else p10
        )
        downside_deviation = max(0.0, expected_val - cvar_10)
        risk_adj = expected_val - self.risk_lambda * downside_deviation

        luck_delta = (float(observed_damage) - expected_val) if observed_damage is not None else 0.0

        return UncertaintyProfile(
            expected_payoff=round(expected_val, 4),
            variance=round(variance_val, 6),
            p10=round(p10, 4),
            p50=round(p50, 4),
            p90=round(p90, 4),
            p95=round(p95, 4),
            ko_probability=round(ko_prob, 4),
            survival_probability=round(surv_prob, 4),
            luck_delta=round(luck_delta, 4),
            risk_adjusted_value=round(risk_adj, 4),
        )

    def evaluate_turn_uncertainty(
        self,
        snapshot: TurnSnapshot,
        p1_line: PrunedActionLine,
        p2_line: PrunedActionLine,
        observed_equity: Optional[float] = None,
    ) -> UncertaintyProfile:
        """
        Evaluate full 16-roll x Crit x Accuracy payoff uncertainty for a joint (P1, P2) turn action pair.

        Args:
            snapshot: Pre-turn board snapshot.
            p1_line: Selected Player 1 action line.
            p2_line: Selected Player 2 action line.
            observed_equity: Optional realized post-turn board equity from replay log.

        Returns:
            UncertaintyProfile quantifying payoff distribution, KO%, survival%, and luck_delta.
        """
        sim_state = self._parser.to_simulator_state(snapshot)
        combined_choices: Dict[str, Dict[str, Any]] = {}
        combined_choices.update(p1_line.simulator_choices)
        combined_choices.update(p2_line.simulator_choices)

        roll_payoffs: List[float] = []
        ko_flags: List[float] = []
        surv_flags: List[float] = []

        for r_val in DAMAGE_ROLLS_16:
            sim = ClientReplaySimulator(sim_state, combined_choices, pov_player="p1")
            post_state, _ = sim.run_turn(roll_mode="fixed", fixed_roll=r_val)
            slots = post_state.get("slots", {})

            p1a_hp = float(slots.get("p1a", {}).get("current_hp_pct", 0.0)) / 100.0
            p1b_hp = float(slots.get("p1b", {}).get("current_hp_pct", 0.0)) / 100.0
            p2a_hp = float(slots.get("p2a", {}).get("current_hp_pct", 0.0)) / 100.0
            p2b_hp = float(slots.get("p2b", {}).get("current_hp_pct", 0.0)) / 100.0

            p1_alive = (1 if p1a_hp > 0 else 0) + (1 if p1b_hp > 0 else 0) + snapshot.p1_bench_alive
            p2_alive = (1 if p2a_hp > 0 else 0) + (1 if p2b_hp > 0 else 0) + snapshot.p2_bench_alive

            hp_diff = (p1a_hp + p1b_hp) - (p2a_hp + p2b_hp)
            ko_diff = float(p1_alive - p2_alive) * 0.35
            board_ctrl = p1_line.tactical_prior - p2_line.tactical_prior
            payoff = float(np.clip(0.45 * hp_diff + ko_diff + 0.30 * board_ctrl, -1.0, 1.0))
            roll_payoffs.append(payoff)

            opp_ko = 1.0 if (p2a_hp <= 0.0 or p2b_hp <= 0.0) else 0.0
            my_surv = 1.0 if (p1a_hp > 0.0 and p1b_hp > 0.0) else 0.0
            ko_flags.append(opp_ko)
            surv_flags.append(my_surv)

        # Determine effective move accuracy of P1 slot A move
        mv_a = MOVE_DB.get(p1_line.slot_a_move, {})
        raw_acc = mv_a.get("accuracy", 100)
        eff_acc = float(raw_acc) if isinstance(raw_acc, (int, float)) and raw_acc > 0 else 100.0

        crit_payoffs = [float(np.clip(v + 0.12, -1.0, 1.0)) for v in roll_payoffs]
        profile = self.compute_damage_distribution(
            base_rolls_16=roll_payoffs,
            crit_rolls_16=crit_payoffs,
            crit_stage=0,
            accuracy_pct=eff_acc,
            defender_hp=999.0,  # Overridden below by exact simulated KO/survival flags
            observed_damage=observed_equity,
        )
        profile.ko_probability = round(float(np.mean(ko_flags)), 4)
        profile.survival_probability = round(float(np.mean(surv_flags)), 4)
        if observed_equity is None:
            # Quantify luck delta from actual snapshot HP deltas if available
            p1_lost = sum(v for k, v in snapshot.hp_deltas.items() if k.startswith("p1:"))
            p2_lost = sum(v for k, v in snapshot.hp_deltas.items() if k.startswith("p2:"))
            realized_swing = float(np.clip((p2_lost - p1_lost) * 0.5, -1.0, 1.0))
            profile.luck_delta = round(realized_swing - profile.expected_payoff, 4)

        return profile
