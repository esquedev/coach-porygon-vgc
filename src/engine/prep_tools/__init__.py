# -*- coding: utf-8 -*-
"""Zero-AI Offline Base64 Mobile Prep Tools for Pokémon Champions Regulation M-C.

Public pure-domain API consumed by both the headless CLI (`scripts/generate_prep_tools.py`)
and the Replay Coach Studio topbar `"Prep Tools"` view (`apps/replay_coach/server.py`).
"""
from __future__ import annotations

from engine.prep_tools.damage_matrix_builder import (
    DamageMatrixPayload,
    build_damage_matrix_payload,
)
from engine.prep_tools.html_renderer import (
    build_damage_matrix_html,
    build_speed_tiers_html,
    render_damage_matrix_html,
    render_speed_tiers_html,
)
from engine.prep_tools.meta_snapshot import (
    BULK_PROFILE_SPECS,
    DefenderBulkProfile,
    MetaPokemonEntry,
    TopNMetaSnapshot,
    calc_champions_hp,
    calc_champions_stat,
    get_top_n_meta_snapshot,
    load_sprites_dict,
)
from engine.prep_tools.speed_tiers_builder import (
    SpeedTiersPayload,
    build_speed_tiers_payload,
)

__all__ = [
    "BULK_PROFILE_SPECS",
    "DamageMatrixPayload",
    "DefenderBulkProfile",
    "MetaPokemonEntry",
    "SpeedTiersPayload",
    "TopNMetaSnapshot",
    "build_damage_matrix_html",
    "build_damage_matrix_payload",
    "build_speed_tiers_html",
    "build_speed_tiers_payload",
    "calc_champions_hp",
    "calc_champions_stat",
    "get_top_n_meta_snapshot",
    "load_sprites_dict",
    "render_damage_matrix_html",
    "render_speed_tiers_html",
]
