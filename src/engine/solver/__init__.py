# -*- coding: utf-8 -*-
"""Coach Porygon VGC — Game-Theoretic Equilibrium Solver & Bayesian Turn Advisor."""

from .bayesian_aggregator import (
    BayesianTurnAdvice,
    CoachTurnAdvisor,
    OpponentHypothesisEvaluation,
)
from .game_theory import (
    ActionRecommendation,
    DominatedActionRecord,
    IEDSResult,
    QuantalResponseResult,
    TurnEquilibriumResult,
    ZeroSumNashResult,
    decode_joint_action,
    decode_slot_choice,
    format_equilibrium_coach_report,
    run_iterated_dominance_elimination,
    solve_quantal_response,
    solve_turn_equilibrium,
    solve_zero_sum_nash,
)

__all__ = [
    "ActionRecommendation",
    "BayesianTurnAdvice",
    "CoachTurnAdvisor",
    "DominatedActionRecord",
    "IEDSResult",
    "OpponentHypothesisEvaluation",
    "QuantalResponseResult",
    "TurnEquilibriumResult",
    "ZeroSumNashResult",
    "decode_joint_action",
    "decode_slot_choice",
    "format_equilibrium_coach_report",
    "run_iterated_dominance_elimination",
    "solve_quantal_response",
    "solve_turn_equilibrium",
    "solve_zero_sum_nash",
]

