# -*- coding: utf-8 -*-
"""Static game data, type chart, nature modifiers, and Regulation M-C stat formulas."""

from __future__ import annotations

from typing import Dict, Mapping

# ==============================================================================
# REGULATION M-C FORMAT INVARIANTS
# ==============================================================================

STANDARD_IV: int = 31
MAX_TOTAL_SP: int = 66
MAX_SINGLE_STAT_SP: int = 32
MEGA_EVOLUTION_PRIORITY: float = 5.5
TERASTALLIZATION_ALLOWED: bool = False

STAT_ORDER: tuple[str, ...] = ("hp", "atk", "def", "spa", "spd", "spe")

# ==============================================================================
# STATIC GAME DATA & COEFFICIENTS (REGULATION M-C / SHOWDOWN SIM)
# ==============================================================================

TYPE_CHART: Dict[str, Dict[str, float]] = {
    "Normal":   {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
    "Fire":     {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0},
    "Water":    {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0, "Rock": 2.0, "Dragon": 0.5},
    "Grass":    {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0, "Dragon": 0.5, "Steel": 0.5},
    "Electric": {"Water": 2.0, "Electric": 0.5, "Grass": 0.5, "Ground": 0.0, "Flying": 2.0, "Dragon": 0.5},
    "Ice":      {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
    "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5},
    "Poison":   {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
    "Ground":   {"Fire": 2.0, "Electric": 2.0, "Grass": 0.5, "Poison": 2.0, "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
    "Flying":   {"Electric": 0.5, "Grass": 2.0, "Fighting": 2.0, "Bug": 2.0, "Rock": 0.5, "Steel": 0.5},
    "Psychic":  {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0, "Steel": 0.5},
    "Bug":      {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0, "Steel": 0.5, "Fairy": 0.5},
    "Rock":     {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5, "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
    "Ghost":    {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
    "Dragon":   {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
    "Dark":     {"Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5, "Fairy": 0.5},
    "Steel":    {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0, "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
    "Fairy":    {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5},
}

NATURE_MODS: Dict[str, Dict[str, float]] = {
    "Adamant": {"atk": 1.1, "spa": 0.9}, "Bold":    {"def": 1.1, "atk": 0.9},
    "Brave":   {"atk": 1.1, "spe": 0.9}, "Calm":    {"spd": 1.1, "atk": 0.9},
    "Careful": {"spd": 1.1, "spa": 0.9}, "Modest":  {"spa": 1.1, "atk": 0.9},
    "Quiet":   {"spa": 1.1, "spe": 0.9}, "Timid":   {"spe": 1.1, "atk": 0.9},
    "Jolly":   {"spe": 1.1, "spa": 0.9}, "Impish":  {"def": 1.1, "spa": 0.9},
    "Relaxed": {"def": 1.1, "spe": 0.9}, "Sassy":   {"spd": 1.1, "spe": 0.9},
    "Naive":   {"spe": 1.1, "spd": 0.9}, "Hasty":   {"spe": 1.1, "def": 0.9},
    "Lonely":  {"atk": 1.1, "def": 0.9}, "Mild":    {"spa": 1.1, "def": 0.9},
    "Gentle":  {"spd": 1.1, "def": 0.9}, "Rash":    {"spa": 1.1, "spd": 0.9},
    "Naughty": {"atk": 1.1, "spd": 0.9}, "Lax":     {"def": 1.1, "spd": 0.9},
    "Hardy":   {}, "Serious": {}, "Bashful": {}, "Quirky": {}, "Docile": {},
}

STAT_LABELS: Dict[str, str] = {
    "hp": "HP",
    "atk": "Attack",
    "def": "Defense",
    "spa": "Sp. Atk",
    "spd": "Sp. Def",
    "spe": "Speed",
    "accuracy": "accuracy",
    "evasion": "evasion",
}


def trunc(n: float, bits: int = 0) -> int:
    """Truncate float to integer with optional bit masking."""
    res = int(n)
    if bits:
        res = res & ((1 << bits) - 1)
    return res


def compute_champions_level_50_stats(
    base_stats: Mapping[str, int],
    sp_dict: Mapping[str, int],
    nature: str = "Hardy",
) -> Dict[str, int]:
    """Compute exact Level 50 stats under Regulation M-C (mandatory 31 IVs, 1:1 66-SP scaling).

    Formula (Champions Level 50):
    - HP   = Base_HP + SP_HP + 15 + 60  (or 1 if Base_HP == 1)
    - Stat = floor((Base_Stat + SP_Stat + 15 + 5) * NatureMult)
    """
    iv_half = STANDARD_IV // 2  # 15
    mods = NATURE_MODS.get(nature or "Hardy", {})

    base_hp = int(base_stats.get("hp", 80))
    sp_hp = int(sp_dict.get("hp", 0))
    hp_stat = 1 if base_hp == 1 else base_hp + sp_hp + iv_half + 60

    result: Dict[str, int] = {"hp": hp_stat}
    for stat_name in ("atk", "def", "spa", "spd", "spe"):
        sp_val = int(sp_dict.get(stat_name, sp_dict.get("def_" if stat_name == "def" else stat_name, 0)))
        raw = int(base_stats.get(stat_name, 80)) + sp_val + iv_half + 5
        mod = mods.get(stat_name, 1.0)
        if mod > 1.0:
            result[stat_name] = trunc(trunc(raw * 110, 16) / 100)
        elif mod < 1.0:
            result[stat_name] = trunc(trunc(raw * 90, 16) / 100)
        else:
            result[stat_name] = raw
    return result
