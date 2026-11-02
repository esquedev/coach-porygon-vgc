from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Stat engine constants
# ---------------------------------------------------------------------------

BASE_STATS_DB: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Core integer helpers
# ---------------------------------------------------------------------------


def trunc(n: float, bits: int = 0) -> int:
    """Truncate float to integer with optional bit masking."""
    res = int(n)
    if bits:
        res = res & ((1 << bits) - 1)
    return res


# ---------------------------------------------------------------------------
# Stat formula helpers
# ---------------------------------------------------------------------------

def get_stage_multiplier(stage: int) -> float:
    """Compute stat stage multiplier (-6 to +6)."""
    stage = max(-6, min(6, stage))
    return (2 + stage) / 2.0 if stage >= 0 else 2.0 / (2 - stage)


def apply_stat_boost(stat: int, boost: int) -> int:
    """Exact port of Showdown Pokemon#calculateStat / getStat boost table."""
    boost = max(-6, min(6, int(boost)))
    if boost >= 0:
        return trunc(stat * (2 + boost) / 2)
    return trunc(stat * 2 / (2 - boost))


def calculate_level_50_stats(
    species: str,
    sp: dict,
    nature: str,
    ivs: Optional[dict] = None
) -> Tuple[int, Dict[str, int]]:
    """
    Exact port of Showdown Champions Scripts stat formula.
    Returns (max_hp, stats_dict).
    """
    base = BASE_STATS_DB.get(species, {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80})
    mods = NATURE_MODS.get(nature, {})

    hp_sp = int(sp.get("hp", 0))
    max_hp = 1 if base["hp"] == 1 else int(base["hp"]) + hp_sp + 75

    stats: Dict[str, int] = {}
    for s in ["atk", "def", "spa", "spd", "spe"]:
        s_sp = int(sp.get(s, 0))
        raw = int(base[s]) + s_sp + 20
        mod = mods.get(s, 1.0)
        if mod > 1.0:
            stats[s] = trunc(trunc(raw * 110, 16) / 100)
        elif mod < 1.0:
            stats[s] = trunc(trunc(raw * 90, 16) / 100)
        else:
            stats[s] = raw

    return max_hp, stats


__all__ = [
    "BASE_STATS_DB",
    "NATURE_MODS",
    "trunc",
    "get_stage_multiplier",
    "apply_stat_boost",
    "calculate_level_50_stats",
]
