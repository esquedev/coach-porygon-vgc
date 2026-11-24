# -*- coding: utf-8 -*-
"""Official Smogon Damage Calculator (Pokémon Champions / Reg M-C) Python Bridge.

Executes the vendored, tree-shaken `smogon/damage-calc` Champions offline bundle
strictly in-process inside a hermetic JS sandbox (`mini-racer` V8 or `quickjs`) —
zero Node.js runtime dependency, zero network calls, zero AI.
"""

from .bridge import (
    CalcFieldSpec,
    CalcMoveSpec,
    CalcPokemonSpec,
    CalcSideSpec,
    DamageCalcRequest,
    DamageCalcResult,
    SmogonChampionsCalc,
    SpeedCalcRequest,
    SpeedCalcResult,
    get_champions_calc,
)

__all__ = [
    "CalcFieldSpec",
    "CalcMoveSpec",
    "CalcPokemonSpec",
    "CalcSideSpec",
    "DamageCalcRequest",
    "DamageCalcResult",
    "SmogonChampionsCalc",
    "SpeedCalcRequest",
    "SpeedCalcResult",
    "get_champions_calc",
]
