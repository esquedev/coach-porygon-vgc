#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-AI Headless CLI for Offline Base64 Regulation M-C Prep Tools.

Generates standalone mobile-ready Base64 HTML reports (Speed Tiers & Damage/KO
Matrix) for ANY 6-Pokémon Regulation M-C 66-SP team using in-memory DuckDB and
the vendored `SmogonChampionsCalc` (`@smogon/calc` Gen 0) — zero AI needed.

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/generate_prep_tools.py \\
        --team data/teams/char_y_v4.txt --top-n 50 --out-dir reports/prep_tools --lang en
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import time
from typing import Optional, Sequence

from engine.prep_tools import build_damage_matrix_html, build_speed_tiers_html


def _slugify(name: str) -> str:
    """Turn a team label into a clean filesystem-safe slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "team").strip()).strip("_").lower()
    return cleaned or "team"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse CLI options and write standalone offline Base64 Prep Tool HTML files."""
    parser = argparse.ArgumentParser(
        description="Coach Porygon VGC — Zero-AI Offline Base64 Prep Tools Generator (Reg M-C)"
    )
    parser.add_argument(
        "--team",
        required=True,
        help="Path to a Regulation M-C 66-SP Showdown paste (.txt)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Optional display title for the team (defaults to filename stem)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        choices=[20, 35, 50],
        help="Regional DuckDB meta depth (default: 50)",
    )
    parser.add_argument(
        "--kind",
        default="both",
        choices=["both", "speed_tiers", "damage_matrix"],
        help="Which prep report(s) to generate (default: both)",
    )
    parser.add_argument(
        "--lang",
        default="en",
        choices=["en", "es"],
        help="Report UI language (default: en)",
    )
    parser.add_argument(
        "--out-dir",
        default="reports/prep_tools",
        help="Output directory for generated standalone Base64 HTML files",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    team_path = Path(args.team)
    if not team_path.is_file():
        print(f"[ERROR] Team paste file not found: {team_path}", file=sys.stderr)
        return 1

    paste_text = team_path.read_text(encoding="utf-8")
    team_name = args.name or team_path.stem
    slug = _slugify(team_name)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.kind in ("both", "speed_tiers"):
        t0 = time.perf_counter()
        html_str, payload = build_speed_tiers_html(
            paste_text=paste_text,
            team_name=team_name,
            top_n=args.top_n,
            lang=args.lang,
        )
        out_path = out_dir / f"speed_tiers_{slug}_top{args.top_n}_mobile.html"
        out_path.write_text(html_str, encoding="utf-8")
        dt_ms = (time.perf_counter() - t0) * 1000.0
        print(
            f"[OK] Speed Tiers   -> {out_path} "
            f"({len(html_str.encode('utf-8')) / 1024:.1f} KB, Top {payload.top_n} / "
            f"{payload.total_teams:,} teams, {dt_ms:.0f} ms)"
        )

    if args.kind in ("both", "damage_matrix"):
        t0 = time.perf_counter()
        html_str, payload = build_damage_matrix_html(
            paste_text=paste_text,
            team_name=team_name,
            top_n=args.top_n,
            lang=args.lang,
        )
        out_path = out_dir / f"damage_calcs_{slug}_top{args.top_n}_mobile.html"
        out_path.write_text(html_str, encoding="utf-8")
        dt_ms = (time.perf_counter() - t0) * 1000.0
        print(
            f"[OK] Damage Matrix -> {out_path} "
            f"({len(html_str.encode('utf-8')) / 1024:.1f} KB, {payload.calc_count:,} exact Smogon calcs -> "
            f"{payload.unique_roll_arrays:,} unique 16-roll arrays, {dt_ms:.0f} ms)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
