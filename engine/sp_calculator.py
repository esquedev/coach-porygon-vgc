import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from turn_simulator import BASE_STATS_DB, NATURE_MODS, calculate_level_50_stats

STAT_ORDER = ["hp", "atk", "def", "spa", "spd", "spe"]
STAT_LABELS = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
MAX_TOTAL_SP = 66
MAX_SINGLE_STAT_SP = 32


def ev_to_sp(ev: int) -> int:
    """
    Convert Showdown EV value to Regulation M-C Stat Points (SP).
    EV progression at Level 50 (31 IV):
    0 EV -> 0 SP
    4 EV -> 1 SP
    12 EV -> 2 SP
    20 EV -> 3 SP
    28 EV -> 4 SP
    ...
    252 EV -> 32 SP
    Formula: 1 + (ev - 4) // 8 for ev >= 4.
    """
    if ev < 4:
        return 0
    return min(MAX_SINGLE_STAT_SP, 1 + (int(ev) - 4) // 8)


def sp_to_ev(sp: int) -> int:
    """
    Convert Regulation M-C Stat Points (SP) to Showdown EV value.
    0 SP -> 0 EV
    1 SP -> 4 EV
    2 SP -> 12 EV
    3 SP -> 20 EV
    4 SP -> 28 EV
    ...
    32 SP -> 252 EV
    Formula: 4 + (sp - 1) * 8 for sp >= 1.
    """
    if sp <= 0:
        return 0
    return 4 + (min(MAX_SINGLE_STAT_SP, int(sp)) - 1) * 8


def validate_and_calculate_sp(
    species: str,
    sp_spread: Dict[str, int],
    nature: str = "Hardy"
) -> Tuple[bool, str, Dict[str, int]]:
    """
    Validates a Regulation M-C 66-SP spread and computes final Level 50 stats
    with sequential +10% / -10% Stat Alignment floor rounding.
    """
    normalized_sp = {k: int(sp_spread.get(k, 0)) for k in STAT_ORDER}

    for k, val in normalized_sp.items():
        if val < 0:
            return False, f"[CRITICAL FAILURE]: Negative SP detected in {STAT_LABELS[k]} ({val} SP).", {}
        if val > MAX_SINGLE_STAT_SP:
            return (
                False,
                f"[CRITICAL FAILURE]: {STAT_LABELS[k]} allocation ({val} SP) exceeds the 32 SP single-stat hard cap.",
                {}
            )

    total_sp = sum(normalized_sp.values())
    verification_str = (
        f"{normalized_sp['hp']} HP + {normalized_sp['atk']} Atk + {normalized_sp['def']} Def + "
        f"{normalized_sp['spa']} SpA + {normalized_sp['spd']} SpD + {normalized_sp['spe']} Spe = {total_sp} SP"
    )

    if total_sp != MAX_TOTAL_SP:
        return (
            False,
            f"[HALT & RECALCULATE]: {verification_str} (Deviates from mandatory {MAX_TOTAL_SP} SP budget by {total_sp - MAX_TOTAL_SP:+d} SP).",
            {}
        )

    if nature not in NATURE_MODS:
        return False, f"[CRITICAL FAILURE]: Unknown Stat Alignment / Nature '{nature}'.", {}

    max_hp, other_stats = calculate_level_50_stats(species, normalized_sp, nature)
    final_stats = {"hp": max_hp, **other_stats}
    return True, verification_str, final_stats


def main():
    """CLI entry point for Stat Point calculation and verification."""
    parser = argparse.ArgumentParser(description="Regulation M-C 66-SP Deterministic Validator & Stat Calculator")
    parser.add_argument("--species", type=str, required=True, help="Pokemon species name (e.g., Charizard-Mega-Y)")
    parser.add_argument("--nature", type=str, default="Hardy", help="Stat Alignment nature (e.g., Modest, Timid)")
    parser.add_argument("--hp", type=int, default=0)
    parser.add_argument("--atk", type=int, default=0)
    parser.add_argument("--def", dest="def_sp", type=int, default=0)
    parser.add_argument("--spa", type=int, default=0)
    parser.add_argument("--spd", type=int, default=0)
    parser.add_argument("--spe", type=int, default=0)
    args = parser.parse_args()

    sp_spread = {
        "hp": args.hp,
        "atk": args.atk,
        "def": args.def_sp,
        "spa": args.spa,
        "spd": args.spd,
        "spe": args.spe,
    }

    ok, verification_str, final_stats = validate_and_calculate_sp(args.species, sp_spread, args.nature)
    if not ok:
        print(verification_str)
        sys.exit(1)

    print(f"Mandatory Verification String: {verification_str}")
    print(f"Species: {args.species} | Stat Alignment: {args.nature}")
    print("Level 50 Final Stats (Floor Rounded):")
    print(json.dumps(final_stats, indent=2))


if __name__ == "__main__":
    main()
