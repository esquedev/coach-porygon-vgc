#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Game-Theoretic AGI CLI Entry Point (main.py)

Executes the end-to-end simultaneous Nash equilibrium tactical audit pipeline
over a Showdown Regulation M-C replay log or the built-in demonstration fixture.
Usage:
    python main.py --demo
    python main.py --log tests/data/sample_showdown_mc_log.txt
"""

import argparse
from pathlib import Path
import sys
from typing import List, Optional

from engine.db import UnifiedCoachDatabase
from engine.tactics.tactical_pipeline import TacticalAuditResult, audit_showdown_log


REPO_ROOT = Path(__file__).resolve().parent
DEMO_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


def format_telemetry_report(result: TacticalAuditResult) -> str:
    """
    Render a high-density tactical telemetry report for terminal display.

    Args:
        result: Populated TacticalAuditResult from audit_showdown_log.

    Returns:
        Formatted multi-line report string.
    """
    lines: List[str] = [
        "=" * 82,
        "  COACH PORYGON VGC — GAME-THEORETIC AGI TACTICAL AUDIT (REGULATION M-C)",
        "=" * 82,
        f"  Audit ID         : {result.audit_id}",
        f"  Matchup          : {result.p1_name} vs. {result.p2_name} (Winner: {result.winner})",
        f"  Compute Device   : {result.device_used.upper()} | Total Latency: {result.execution_time_ms:.2f} ms",
        "-" * 82,
        f"  [1] TURNING POINT ISOLATION: TURN {result.turning_point_turn} / {result.total_turns} "
        f"(Impact Score: {result.impact_score:.1f} pts)",
        f"      Active Board : P1 [{' / '.join(result.p1_active)}] vs. P2 [{' / '.join(result.p2_active)}]",
    ]
    for reason in result.turning_point_reasons:
        lines.append(f"      * {reason}")

    lines.append("-" * 82)
    lines.append("  [2] SIMULTANEOUS 5x5 PAYOFF MATRIX (Simulador Oficial VGC + GPU ValueNet):")
    header = "      P1 \\ P2      | " + " | ".join(f"  L{j}  " for j in range(5))
    lines.append(header)
    lines.append("      " + "-" * (len(header) - 6))
    for i, row in enumerate(result.payoff_matrix):
        row_str = " | ".join(f"{val:+6.3f}" for val in row)
        lines.append(f"      P1 Line L{i}   | {row_str}")

    lines.append("-" * 82)
    lines.append("  [3] VON NEUMANN MIXED-STRATEGY NASH EQUILIBRIUM (HiGHS LP Solver):")
    lines.append(f"      Game Value (v*) : {result.game_value:+.4f} Win-Equity")
    for i, (label, prob) in enumerate(zip(result.p1_action_labels, result.p1_nash_probs)):
        marker = " <-- [NASH OPTIMAL]" if i == result.optimal_nash_idx else ""
        obs_marker = " <-- [OBSERVED]" if i == result.observed_action_idx else ""
        lines.append(f"      [L{i}] p={prob:6.2%} : {label}{marker}{obs_marker}")

    lines.append("-" * 82)
    lines.append("  [4] PLAYSTYLE DIAGNOSTIC & COGNITIVE LEAK TAXONOMY:")
    lines.append(f"      Observed Play   : {result.observed_action_label}")
    lines.append(f"      Optimal Nash    : {result.optimal_nash_label}")
    lines.append(f"      Equity Loss     : {result.equity_loss:.4f} (Delta Equity = v* - V_real)")
    lines.append(f"      Mistake Code    : {result.mistake_code}")
    lines.append(f"      Cognitive Driver: {result.cognitive_driver}")
    lines.append("=" * 82)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """
    Parse CLI arguments and run the Game-Theoretic replay audit.

    Args:
        argv: Optional list of CLI arguments.

    Returns:
        Exit status code (0 for success, 1 for error).
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Coach Porygon VGC — Game-Theoretic AGI Replay Auditor (Regulation M-C)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run tactical audit on the canonical Regulation M-C fixture log.",
    )
    parser.add_argument(
        "--log",
        type=str,
        default=None,
        help="Path to a Showdown Regulation M-C battle log file.",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Run in read-only mode without appending to data/tactical_audits.jsonl.",
    )
    args = parser.parse_args(argv)

    log_path = Path(args.log) if args.log else DEMO_LOG_PATH
    if not log_path.exists():
        print(f"[ERROR] Battle log file not found: {log_path}", file=sys.stderr)
        return 1

    raw_log = log_path.read_text(encoding="utf-8")
    db = UnifiedCoachDatabase()
    result = audit_showdown_log(
        raw_log,
        auto_persist=not args.no_persist,
        db=db,
    )
    print(format_telemetry_report(result))
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
