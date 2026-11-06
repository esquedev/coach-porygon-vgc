# engine/game_rules.py
from __future__ import annotations

from typing import Dict

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
    "Fairy":    {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5}
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
    "Hardy":   {}, "Serious": {}, "Bashful": {}, "Quirky": {}, "Docile": {}
}

STAT_LABELS = {
    "atk": "Attack", "def": "Defense", "spa": "Sp. Atk",
    "spd": "Sp. Def", "spe": "Speed", "accuracy": "accuracy", "evasion": "evasion"
}
