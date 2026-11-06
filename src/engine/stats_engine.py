from __future__ import annotations

from typing import Any, Dict, Tuple

from engine.game_rules import NATURE_MODS

# ---------------------------------------------------------------------------
# Stat engine constants
# ---------------------------------------------------------------------------

BASE_STATS_DB: Dict[str, Dict[str, Any]] = {}

# Champions requires every Pokémon to use 31 IVs. The Level 50 formula below
# folds the IV contribution into its constants: 31 // 2 = 15, plus 60 for HP
# and 5 for other stats. Do not add 31 directly to the calculated stats.
STANDARD_IV = 31


# ---------------------------------------------------------------------------
# Core integer helper
# ---------------------------------------------------------------------------


def trunc(n: float, bits: int = 0) -> int:
    """Truncate float to integer with optional bit masking."""
    res = int(n)
    if bits:
        res = res & ((1 << bits) - 1)
    return res


# ---------------------------------------------------------------------------
# Level 50 stat calculation
# ---------------------------------------------------------------------------


def calculate_level_50_stats(
    species: str,
    sp: dict,
    nature: str,
) -> Tuple[int, Dict[str, int]]:
    """Calculate Champions Level 50 stats using the mandatory 31 IV baseline.

    Returns ``(max_hp, other_stats)``. IVs are not an argument because
    Champions requires ``STANDARD_IV`` for every stat.
    """
    base = BASE_STATS_DB.get(
        species,
        {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80},
    )
    mods = NATURE_MODS.get(nature, {})
    iv_contribution = STANDARD_IV // 2

    hp_sp = int(sp.get("hp", 0))
    max_hp = (
        1
        if base["hp"] == 1
        else int(base["hp"]) + hp_sp + iv_contribution + 60
    )

    stats: Dict[str, int] = {}
    for stat_name in ("atk", "def", "spa", "spd", "spe"):
        stat_sp = int(sp.get(stat_name, 0))
        raw = int(base[stat_name]) + stat_sp + iv_contribution + 5
        modifier = mods.get(stat_name, 1.0)
        if modifier > 1.0:
            stats[stat_name] = trunc(trunc(raw * 110, 16) / 100)
        elif modifier < 1.0:
            stats[stat_name] = trunc(trunc(raw * 90, 16) / 100)
        else:
            stats[stat_name] = raw

    return max_hp, stats


__all__ = [
    "BASE_STATS_DB",
    "STANDARD_IV",
    "NATURE_MODS",
    "trunc",
    "calculate_level_50_stats",
]
