#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Game-Theoretic AGI CLI Entry Point & Pipeline Orchestrator (main.py)

Executes the end-to-end simultaneous Nash equilibrium tactical audit pipeline,
PyTorch CUDA/CPU tensor payoff evaluation, uncertainty modeling, HTML/PDF report
generation, and GPU throughput benchmarking.

Usage:
    python main.py --demo
    python main.py --log tests/data/sample_showdown_mc_log.txt
    python main.py --demo --mode gpu --device cuda --format json
    python main.py audit tests/data/sample_showdown_mc_log.txt --format html --output-dir reports
    python main.py benchmark-gpu --device cuda
"""

import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional

from engine.db import UnifiedCoachDatabase
from engine.tactics.tactical_pipeline import (
    TacticalAuditResult,
    TacticalPipeline,
    audit_showdown_log,
)
from engine.ui_generator import render_tactical_audit_html


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

    if result.uncertainty_profile:
        up = result.uncertainty_profile
        lines.append("-" * 82)
        lines.append("  [5] UNCERTAINTY & LUCK PROFILE (16 Rolls x Crit x Accuracy):")
        lines.append(
            f"      Quantiles       : P10={up.get('p10', 0.0):+.4f} | "
            f"P50={up.get('p50', 0.0):+.4f} | P90={up.get('p90', 0.0):+.4f} | "
            f"P95={up.get('p95', 0.0):+.4f}"
        )
        lines.append(
            f"      Probabilities   : KO={up.get('ko_probability', 0.0):6.2%} | "
            f"Survival={up.get('survival_probability', 0.0):6.2%} | "
            f"Luck Delta={up.get('luck_delta', 0.0):+.4f}"
        )

    if result.all_turns_analysis:
        lines.append("-" * 82)
        lines.append("  [6] ALL-TURNS WIN-EQUITY TRAJECTORY (V*):")
        for t_eval in result.all_turns_analysis:
            lines.append(
                f"      Turn {t_eval.get('turn_number', 0):2d} | "
                f"V*={t_eval.get('game_value', 0.0):+.4f} "
                f"(dV*={t_eval.get('delta_v_star', 0.0):+.4f}) | "
                f"Class={t_eval.get('shift_classification', 'Standard_Trade'):14s} | "
                f"Code={t_eval.get('mistake_code', 'POS-01')}"
            )

    lines.append("=" * 82)
    return "\n".join(lines)


def _export_audit_output(
    result: TacticalAuditResult,
    fmt: str,
    output_dir: Optional[str],
) -> None:
    """
    Export audit result to JSON, HTML, or PDF when requested via CLI flags.

    Args:
        result: Populated TacticalAuditResult.
        fmt: Output format ('text', 'json', 'html', 'pdf').
        output_dir: Target output directory path string, if provided.
    """
    payload = result.to_dict()
    if fmt == "json":
        json_text = json.dumps(payload, indent=2, ensure_ascii=False)
        if output_dir:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{result.audit_id}.json"
            out_path.write_text(json_text, encoding="utf-8")
            print(f"[EXPORT] JSON audit saved to: {out_path}")
        else:
            print(json_text)
    elif fmt in ("html", "pdf"):
        html_doc = render_tactical_audit_html(payload)
        out_dir = Path(output_dir) if output_dir else (REPO_ROOT / "reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"{result.audit_id}.html"
        html_path.write_text(html_doc, encoding="utf-8")
        print(format_telemetry_report(result))
        print(f"[EXPORT] HTML tactical report saved to: {html_path}")
        if fmt == "pdf":
            try:
                from engine.pdf_exporter import export_html_to_pdf
                pdf_path = out_dir / f"{result.audit_id}.pdf"
                export_html_to_pdf(str(html_path), str(pdf_path))
                print(f"[EXPORT] PDF tactical report saved to: {pdf_path}")
            except Exception as exc:
                print(f"[WARN] PDF export fallback (HTML generated at {html_path}): {exc}")
    else:
        print(format_telemetry_report(result))


def main(argv: Optional[List[str]] = None) -> int:
    """
    Parse CLI arguments and run the Game-Theoretic replay audit or subcommand.

    Args:
        argv: Optional list of CLI arguments.

    Returns:
        Exit status code (0 for success, 1 for error).
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    raw_args = list(argv) if argv is not None else sys.argv[1:]

    # Detect positional subcommand if present
    subcommand: Optional[str] = None
    subcommand_target: Optional[str] = None
    valid_subcommands = {"audit", "eval-turn", "benchmark-gpu", "serve-ui"}
    if raw_args and raw_args[0] in valid_subcommands:
        subcommand = raw_args.pop(0)
        if raw_args and not raw_args[0].startswith("-"):
            subcommand_target = raw_args.pop(0)

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
    parser.add_argument(
        "--mode",
        type=str,
        choices=["classic", "gpu", "hybrid", "report", "benchmark"],
        default="hybrid",
        help="Execution pipeline mode (classic|gpu|hybrid|report|benchmark).",
    )
    parser.add_argument(
        "--device",
        type=str,
        choices=["auto", "cuda", "cpu"],
        default="auto",
        help="Compute device preference (auto|cuda|cpu).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional directory for saving exported JSON/HTML/PDF reports.",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["text", "json", "html", "pdf"],
        default="text",
        help="Output format (text|json|html|pdf).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for serve-ui mode (default: 8000).",
    )
    args = parser.parse_args(raw_args)

    device_pref = None if args.device == "auto" else args.device

    # Handle benchmark subcommand or mode
    if subcommand == "benchmark-gpu" or args.mode == "benchmark":
        pipeline = TacticalPipeline(device=device_pref)
        raw_bench_log = DEMO_LOG_PATH.read_text(encoding="utf-8")
        metrics = pipeline.run_benchmark(raw_log=raw_bench_log, batch_size=32)
        print(json.dumps(metrics, indent=2))
        return 0

    # Handle serve-ui subcommand
    if subcommand == "serve-ui":
        from engine.ui_server import run_server
        run_server(port=args.port)
        return 0

    log_target = subcommand_target or args.log
    log_path = Path(log_target) if log_target else DEMO_LOG_PATH
    if not log_path.exists():
        print(f"[ERROR] Battle log file not found: {log_path}", file=sys.stderr)
        return 1

    raw_log = log_path.read_text(encoding="utf-8")
    db = UnifiedCoachDatabase()
    pipeline = TacticalPipeline(db=db, device=device_pref)
    result = pipeline.run_audit(
        raw_log,
        auto_persist=not args.no_persist,
    )

    out_fmt = "html" if args.mode == "report" and args.format == "text" else args.format
    _export_audit_output(result, fmt=out_fmt, output_dir=args.output_dir)
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
