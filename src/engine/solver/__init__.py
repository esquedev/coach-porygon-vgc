# -*- coding: utf-8 -*-
"""Coach Porygon VGC — Pure Game-Theoretic Equilibrium Solver (IEDS, Zero-Sum Nash LP, QRE)."""

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

from .lead_matchup_solver import (
    BringModeSpec,
    LeadMatchupConfig,
    LeadMatchupResult,
    LeadMatchupSolver,
)

__all__ = [
    "ActionRecommendation",
    "BringModeSpec",
    "DominatedActionRecord",
    "IEDSResult",
    "LeadMatchupConfig",
    "LeadMatchupResult",
    "LeadMatchupSolver",
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
