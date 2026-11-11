#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Battle Telemetry Dumper
===========================================

Ingests a raw Pokémon Showdown battle chat log, extracts turn-by-turn state
transitions, damage percentages, active slots, and variance events, and dumps
records into a structured CSV with an open `comment` column for coach analysis.

Usage:
    python3 scripts/dump_battle_telemetry.py --log battle.log [OPTIONS]
    python3 scripts/dump_battle_telemetry.py --log "Battle started..." --paste team.txt --output data/telemetry/my_matches.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional

# Ensure src/ is in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.telemetry import (
    batch_update_comments,
    extract_turn_telemetry,
    save_telemetry_to_csv,
    update_telemetry_comment,
)


def _read_input(value: Optional[str]) -> str:
    """Read value directly if it's text, or from file if it matches an existing file path."""
    if not value:
        return ""
    path = Path(value)
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            sys.stderr.write(f"Warning: Failed reading file {value}: {e}\n")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="dump_battle_telemetry",
        description="Dump Pokémon Showdown battle turns to CSV with an open comment column for tactical coaching.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--log",
        "-l",
        required=True,
        help="Path to Showdown battle log file or raw chat log text.",
    )
    parser.add_argument(
        "--paste",
        "-p",
        default=None,
        help="Optional path to user team paste file or raw paste string. Auto-detects data/teams/char_y_v3.txt if omitted.",
    )
    parser.add_argument(
        "--pov",
        "-u",
        default=None,
        help="POV trainer username (trainer_1). If omitted, inferred automatically.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data/telemetry/battles_telemetry.csv",
        help="Output CSV destination path.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the target CSV file instead of appending to it.",
    )
    parser.add_argument(
        "--comment",
        "-c",
        default="",
        help="Optional initial comment to attach to all extracted turns.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Main execution routine."""
    parser = build_parser()
    args = parser.parse_args(argv)

    raw_log = _read_input(args.log).strip()
    if not raw_log:
        sys.stderr.write("Error: Battle log is empty or could not be read.\n")
        return 1

    team_paste = _read_input(args.paste).strip() if args.paste else ""
    if not team_paste:
        default_paste_path = REPO_ROOT / "data" / "teams" / "char_y_v3.txt"
        if default_paste_path.is_file():
            team_paste = default_paste_path.read_text(encoding="utf-8").strip()

    records = extract_turn_telemetry(
        raw_log=raw_log,
        pov_trainer=args.pov,
        user_team_paste=team_paste if team_paste else None,
    )

    if not records:
        sys.stderr.write("Warning: No active turns were parsed from the battle log.\n")
        return 1

    if args.comment:
        for r in records:
            r.comment = args.comment

    out_path = save_telemetry_to_csv(
        records=records,
        csv_path=args.output,
        append=not args.overwrite,
    )

    print("=" * 80)
    print(f"COACH PORYGON VGC — BATTLE TELEMETRY DUMPED ({len(records)} TURNS)")
    print("=" * 80)
    print(f"Match ID:   {records[0].match_id}")
    print(f"Timestamp:  {records[0].timestamp}")
    print(f"Trainer 1:  {records[0].trainer_1}")
    print(f"Trainer 2:  {records[0].trainer_2}")
    print(f"Winner:     {records[0].winner}")
    print(f"CSV Path:   {out_path.resolve()}")
    print("-" * 80)
    print(f"{'Turn':<5} | {'Active (T1)':<24} | {'Active (T2)':<24} | {'Dmg Dealt':<10} | {'Dmg Taken':<10} | {'Variance'}")
    print("-" * 80)
    for r in records:
        t1_act = f"{r.trainer_1_active_1}, {r.trainer_1_active_2}".strip(", ")
        t2_act = f"{r.trainer_2_active_1}, {r.trainer_2_active_2}".strip(", ")
        print(f"{r.turn:<5} | {t1_act:<24} | {t2_act:<24} | {r.damage_dealt_to_trainer_2:<10.1f} | {r.damage_dealt_to_trainer_1:<10.1f} | {r.variance_events}")
    print("=" * 80)

    # Auto-sync Team Preview Playbook with the updated telemetry CSV
    try:
        paste_file = Path(args.paste) if (args.paste and Path(args.paste).is_file()) else (REPO_ROOT / "data" / "teams" / "char_y_v3.txt")
        if paste_file.is_file():
            from generate_team_preview_playbook import refresh_playbook
            team_stem = paste_file.stem
            html_out = REPO_ROOT / "reports" / f"{team_stem}_playbook.html"
            md_out = REPO_ROOT / "reports" / f"{team_stem}_cheatsheet.md"
            refresh_playbook(paste_file, html_out, md_out, out_path)
            print(f"[Auto-Sync] Refreshed Playbook '{html_out.name}' with live telemetry ({out_path.name}).")
    except Exception as exc:
        sys.stderr.write(f"Note: Playbook auto-sync skipped ({exc}).\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

