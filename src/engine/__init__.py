# -*- coding: utf-8 -*-
"""Coach Porygon VGC engine package."""

from .damage_calc import SmogonChampionsCalc, get_champions_calc
from .game_rules import NATURE_MODS, STAT_LABELS, TYPE_CHART
from .inference import (
    MissingOTSError,
    OpponentSetInferencer,
    SeriesSPInferenceReport,
)
from .solver import (
    TurnEquilibriumResult,
    solve_turn_equilibrium,
    solve_zero_sum_nash,
)

__all__ = [
    "MissingOTSError",
    "NATURE_MODS",
    "OpponentSetInferencer",
    "STAT_LABELS",
    "SeriesSPInferenceReport",
    "SmogonChampionsCalc",
    "TYPE_CHART",
    "TurnEquilibriumResult",
    "get_champions_calc",
    "solve_turn_equilibrium",
    "solve_zero_sum_nash",
]
