# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Command Line Interface (CLI)
================================================

Command-line entry point to evaluate single-turn VGC Doubles game states,
generate Bayesian opponent hypotheses, run Monte Carlo discrete-RNG tensor
simulations, and compute risk-resilient Nash / Quantal Response recommendations.

Usage:
    python3 -m engine.cli --paste team.txt --log battle.log [OPTIONS]
    python3 -m engine.cli --paste "Charizard @ ..." --log "Battle started..." [OPTIONS]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional

from engine.parser import parse_showdown_chat_log
from engine.solver import CoachTurnAdvisor


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
        prog="coach-porygon",
        description="Coach Porygon VGC — Single-Turn Discrete-RNG & Game-Theoretic Turn Advisor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--paste",
        "-p",
        required=True,
        help="Path to team paste file or raw Pokémon Showdown team paste string.",
    )
    parser.add_argument(
        "--log",
        "-l",
        required=True,
        help="Path to battle log file or raw Pokémon Showdown chat log string.",
    )
    parser.add_argument(
        "--pov",
        "-u",
        default=None,
        help="Your Pokémon Showdown username (POV trainer). If omitted, inferred automatically.",
    )
    parser.add_argument(
        "--sims",
        "-s",
        type=int,
        default=256,
        help="Number of discrete-RNG Monte Carlo simulations per opponent hypothesis.",
    )
    parser.add_argument(
        "--hypotheses",
        "-m",
        type=int,
        default=3,
        help="Maximum number of posterior-weighted opponent set hypotheses to evaluate.",
    )
    parser.add_argument(
        "--top-k",
        "-k",
        type=int,
        default=5,
        help="Number of top recommended joint actions to display.",
    )
    parser.add_argument(
        "--risk-lambda",
        "-r",
        type=float,
        default=0.25,
        help="Weight on worst 10 percent bad-luck tail (CVaR_10) in risk-adjusted utility (0.0 to 1.0).",
    )
    parser.add_argument(
        "--beta",
        "-b",
        type=float,
        default=4.0,
        help="Rationality inverse temperature for Logit Quantal Response Equilibrium (QRE).",
    )
    parser.add_argument(
        "--min-prior",
        type=float,
        default=0.60,
        help="Pruning threshold for 26x26 action matrix (0.0 keeps all legal actions).",
    )
    parser.add_argument(
        "--verbosity",
        "-v",
        choices=["coach", "standard", "scientific"],
        default="coach",
        help="Detail level for explanation output: 'coach' (plain English, non-nerd), 'standard' (tactical breakdown), or 'scientific' (full mathematical & process audit).",
    )
    parser.add_argument(
        "--backend",
        choices=["torch", "numpy"],
        default="torch",
        help="Tensor execution backend.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Optional file path to save the generated advisor report.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI execution routine."""
    parser = build_parser()
    args = parser.parse_args(argv)

    team_paste = _read_input(args.paste).strip()
    chat_log = _read_input(args.log).strip()

    if not team_paste:
        sys.stderr.write("Error: Team paste is empty.\n")
        return 1
    if not chat_log:
        sys.stderr.write("Error: Battle log is empty.\n")
        return 1

    battle = parse_showdown_chat_log(
        chat_log,
        pov_trainer=args.pov,
        user_team_paste=team_paste,
    )

    advisor = CoachTurnAdvisor(
        backend=args.backend,
        risk_aversion_lambda=args.risk_lambda,
        rationality_beta=args.beta,
    )

    advice = advisor.advise_battle(
        battle=battle,
        max_hypotheses=args.hypotheses,
        num_simulations=args.sims,
        min_prior_threshold=args.min_prior,
        top_k_recommendations=args.top_k,
    )

    report_text = advice.format_report(
        verbosity=args.verbosity,
        max_recommendations=args.top_k,
    )
    print(report_text)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")
        print(f"\n[Saved report to {out_path}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
