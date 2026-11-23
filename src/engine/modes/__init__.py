# -*- coding: utf-8 -*-
"""Regulation M-C Team Modes, Lead Combinatorics & Preview Playbook Engine.

Provides mathematical analysis of 4-mon modes (15 combinations) and lead pairs
(15 unordered, 30 ordered) for any 6-Pokémon team paste against regional
tournament usage distributions and canonical meta archetypes.
"""

from .mode_analyzer import (
    LeadEvaluation,
    LeadPair,
    ModeEvaluation,
    TeamMemberData,
    TeamMode,
    TeamModeAnalyzer,
)
from .archetype_matcher import (
    ArchetypeMatchupPlan,
    TournamentArchetype,
    TournamentArchetypeMatcher,
)

__all__ = [
    "LeadEvaluation",
    "LeadPair",
    "ModeEvaluation",
    "TeamMemberData",
    "TeamMode",
    "TeamModeAnalyzer",
    "ArchetypeMatchupPlan",
    "TournamentArchetype",
    "TournamentArchetypeMatcher",
]
