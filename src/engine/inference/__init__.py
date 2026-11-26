# -*- coding: utf-8 -*-
"""Regulation M-C OTS-Enforced 66-SP Inference & Tournament Repository Package."""

from .set_inferencer import (
    MissingOTSError,
    OpponentSetInferencer,
    PokemonSPInference,
    SeriesSPInferenceReport,
    StatBound,
    apply_stat_stage,
    compute_effective_speed,
)
from .tournament_db import (
    TournamentUsageRepository,
    get_tournament_repository,
)

__all__ = [
    "MissingOTSError",
    "OpponentSetInferencer",
    "PokemonSPInference",
    "SeriesSPInferenceReport",
    "StatBound",
    "TournamentUsageRepository",
    "apply_stat_stage",
    "compute_effective_speed",
    "get_tournament_repository",
]
