#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coach Porygon VGC v2 — Headless Bo1 / Bo3 OTS 66-SP & Tensor Core CLI.

Unifies the complete Regulation M-C Zero-AI analysis pipeline in a single CLI:
1. Parses 1 to 3 Pokémon Showdown replays (`.html`, `.log`, `.txt`) via the
   lossless wire-protocol parser (`apps.replay_coach.protocol_parser`).
2. Pools Turn-0 ability order, same-priority speed order, exact integer HP hits,
   defensive bulk matrices, and recoil/berry/residual HP ticks across the series.
3. Solves exact clamped 66-SP opponent bounds `[min_sp, max_sp]` and global
   optimal defaults via the vendored offline `smogon/damage-calc` Champions engine
   (`engine.inference.OpponentSetInferencer`).
4. Evaluates every turn with the GPU/CPU Linear Algebra Tensor Core (`GPUReplayCoachEngine`)
   using discrete SplitMix64 RNG rollouts (`--rng-samples`), Strict/Weak IEDS,
   optional Selective 2-Ply Lookahead (`--two-ply`), Zero-Sum Nash, Logit QRE,
   and 4-profile bilingual (`ES`/`EN` × `VGC`/`Scientific`) deterministic coaching.
5. Renders responsive native GitHub Flavored Markdown (GFM) tables and optionally
   exports turn records to `data/telemetry/<team>/battles_telemetry.csv`.

Example:
    PYTHONPATH=src:. .venv/bin/python scripts/coach_bo3.py \
        --team data/teams/char_y_v4.txt \
        --replays apps/replay_coach/sample_data/matchagotme_g1.html \
        --rng-samples 128 --lang en --style vgc
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
for _p in (str(SRC_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apps.replay_coach.gpu_coach_engine import GPUReplayCoachEngine, compute_match_summary
from apps.replay_coach.ots_db import OTSRosterDatabase, _canon_species
from apps.replay_coach.protocol_parser import ParsedReplay, parse_showdown_replay
from apps.replay_coach.server import ReplayCoachAppState
from engine.inference.set_inferencer import (
    MissingOTSError,
    OpponentSetInferencer,
    STAT_KEYS,
    SeriesSPInferenceReport,
)
from engine.parser import parse_showdown_paste


def _auto_detect_pov(
    raw_replay: str,
    t1_sets: Dict[str, Any],
    explicit_pov: Optional[str],
) -> Optional[str]:
    """Infer `trainer_1` username from team-preview species overlap when `--pov` is omitted."""
    if explicit_pov:
        return explicit_pov
    prelim = parse_showdown_replay(raw_replay, game_index=1)
    t1_norm = {_canon_species(m.base_species or m.species) for m in t1_sets.values()}
    ov1 = len(t1_norm & {_canon_species(s) for s in prelim.trainer_1_preview})
    ov2 = len(t1_norm & {_canon_species(s) for s in prelim.trainer_2_preview})
    return prelim.trainer_2_name if ov2 > ov1 else prelim.trainer_1_name


def _format_sp_bounds_gfm(report: SeriesSPInferenceReport) -> str:
    """Render inferred opponent 66-SP clamped bounds as a native GFM Markdown table."""
    lines: List[str] = [
        f"## Inferred Opponent 66-SP Sheet — `{report.trainer_2_name}` "
        f"({report.games_pooled} game(s) · {report.total_smogon_calcs} Smogon Champions calcs · {report.elapsed_ms:.0f}ms)",
        "",
        "| Pokémon | Nature & Item | HP | Atk | Def | SpA | SpD | Spe | Key Evidence |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for inf in report.pokemon_inferences.values():
        cells: List[str] = []
        ev_snippets: List[str] = []
        for sk in STAT_KEYS:
            b = inf.bounds[sk]
            if b.locked:
                cells.append(f"**{b.default_sp}** (🔒)")
            elif b.status == "bounded":
                cells.append(f"**{b.default_sp}** `[{b.min_sp}..{b.max_sp}]`")
            else:
                cells.append(f"{b.default_sp}")
            for ev in b.evidence[:1]:
                if ev not in ev_snippets:
                    ev_snippets.append(ev)
        ev_str = "; ".join(ev_snippets[:2]) if ev_snippets else "Unobserved (VGC role prior)"
        ev_str = ev_str.replace("|", "/")
        nat_item = f"{inf.nature} · {inf.item or 'No Item'}"
        lines.append(
            f"| **{inf.base_species}** | {nat_item} | "
            + " | ".join(cells)
            + f" | {ev_str} |"
        )
    return "\n".join(lines)


def _format_game_audit_gfm(
    game_index: int,
    filename: str,
    replay: ParsedReplay,
    turn_results: List[Dict[str, Any]],
    lang: str,
    style: str,
) -> str:
    """Render per-game Tensor Core Nash/IEDS audit results as a native GFM Markdown table."""
    profile = f"{lang}_{style}"
    summary = compute_match_summary(turn_results)
    res_tag = (
        "WIN"
        if replay.winner and replay.winner.lower() == replay.trainer_1_name.lower()
        else ("LOSS" if replay.winner else "UNKNOWN")
    )
    lines: List[str] = [
        f"## Game {game_index} — `{replay.trainer_1_name}` vs. `{replay.trainer_2_name}` "
        f"({res_tag} · `{filename}` · Accuracy **{summary['accuracy_pct']:.1f}%** · "
        f"Turning Point: **T{summary['turning_point_turn']}**)",
        "",
        "| Turn | Verdict | Played (`trainer_1`) | #1 Optimal Line | Regret | Worst 10% RNG | Coaching Takeaway |",
        "| :---: | :---: | :--- | :--- | :---: | :---: | :--- |",
    ]
    for tr in turn_results:
        act = tr.get("actual_action") or {}
        top = (tr.get("top_actions") or [act])[0]
        com_vars = tr.get("commentary_variants") or {}
        com = com_vars.get(profile) or tr.get("commentary") or {}
        verdict = f"`{com.get('symbol', '')}` {com.get('badge', '')}".strip()
        played = str(act.get("desc") or "—").replace("|", "/")
        best = str(top.get("desc") or "—").replace("|", "/")
        regret = f"{float(act.get('nash_regret', 0.0)):.3f}"
        cvar = f"{float(act.get('cvar10', 0.0)):+.2f}"
        headline = str(com.get("headline") or "").replace("|", "/")
        lines.append(
            f"| **T{tr['turn']}** | {verdict} | {played} | {best} | {regret} | {cvar} | {headline} |"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for `scripts/coach_bo3.py`."""
    parser = argparse.ArgumentParser(
        prog="coach_bo3.py",
        description="Coach Porygon VGC v2 — Headless Bo1/Bo3 OTS 66-SP & Tensor Core CLI",
    )
    parser.add_argument(
        "--team",
        required=True,
        help="Path to trainer_1 66-SP Showdown paste (e.g. data/teams/char_y_v4.txt)",
    )
    parser.add_argument(
        "--replays",
        required=True,
        nargs="+",
        help="1 to 3 Showdown replay files (.html, .log, .txt) from a Bo1 match or Bo3 series",
    )
    parser.add_argument(
        "--opp-ots",
        default=None,
        help="Optional path to trainer_2 EV-less or full OTS paste (auto-extracted from |showteam| if omitted)",
    )
    parser.add_argument(
        "--pov",
        default=None,
        help="Optional trainer_1 Showdown username (auto-detected from --team preview overlap if omitted)",
    )
    parser.add_argument(
        "--rng-samples",
        type=int,
        default=128,
        help="Discrete RNG cartridge rollouts per matchup cell (default: 128)",
    )
    parser.add_argument(
        "--two-ply",
        action="store_true",
        help="Enable selective 2-Ply lookahead on the Strict-IEDS surviving core",
    )
    parser.add_argument(
        "--turns",
        type=int,
        nargs="*",
        default=None,
        help="Optional subset of turn numbers to analyze (default: all turns)",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Compute backend: auto (CUDA if available, else CPU), cuda, or cpu",
    )
    parser.add_argument(
        "--lang",
        default="en",
        choices=["es", "en"],
        help="Coaching output language (default: en)",
    )
    parser.add_argument(
        "--style",
        default="vgc",
        choices=["vgc", "scientific"],
        help="Terminology register: vgc (plain coaching) or scientific (math notation)",
    )
    parser.add_argument(
        "--export-csv",
        default=None,
        help="Optional team folder name to export telemetry to data/telemetry/<team>/battles_telemetry.csv",
    )
    parser.add_argument(
        "--save-opp-paste",
        default=None,
        help="Optional path to save the solved opponent 66-SP Showdown paste",
    )
    parser.add_argument(
        "--no-sim",
        action="store_true",
        help="Only run the OTS 66-SP constraint solver and skip Tensor Core turn simulation",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Execute the headless Bo1/Bo3 OTS 66-SP solver and Tensor Core match audit."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    team_path = Path(args.team)
    if not team_path.is_file():
        print(f"ERROR: Team paste not found: {team_path}", file=sys.stderr)
        return 2

    replay_paths = [Path(p) for p in args.replays[:3]]
    for rp in replay_paths:
        if not rp.is_file():
            print(f"ERROR: Replay file not found: {rp}", file=sys.stderr)
            return 2

    t1_paste_text = team_path.read_text(encoding="utf-8")
    t1_sets_raw = parse_showdown_paste(t1_paste_text)
    t1_sets_canon = {_canon_species(m.species): m for m in t1_sets_raw.values()}

    raw_replays = [rp.read_text(encoding="utf-8") for rp in replay_paths]
    resolved_pov = _auto_detect_pov(raw_replays[0], t1_sets_raw, args.pov)

    # Pass 1: Parse all replays with exact trainer_1 sets to pool Bo1/Bo3 observations
    prelim_replays: List[ParsedReplay] = []
    t2_showteam_pooled: Dict[str, Any] = {}
    for idx, raw_txt in enumerate(raw_replays, 1):
        pr = parse_showdown_replay(
            raw_txt,
            pov_trainer=resolved_pov,
            trainer_1_ots_sets=t1_sets_canon,
            game_index=idx,
        )
        prelim_replays.append(pr)
        for k, v in (pr.trainer_2_showteam_ots or {}).items():
            if k not in t2_showteam_pooled:
                t2_showteam_pooled[k] = v

    if args.opp_ots:
        opp_path = Path(args.opp_ots)
        if not opp_path.is_file():
            print(f"ERROR: Opponent OTS file not found: {opp_path}", file=sys.stderr)
            return 2
        t2_ots_raw = parse_showdown_paste(opp_path.read_text(encoding="utf-8"))
        t2_ots_sets = {_canon_species(m.species): m for m in t2_ots_raw.values()}
    else:
        t2_ots_sets = t2_showteam_pooled

    # Step 1: Solve exact clamped 66-SP opponent bounds via vendored Smogon Champions calc
    inferencer = OpponentSetInferencer()
    try:
        report = inferencer.infer_series(
            trainer_1_sets=t1_sets_raw,
            trainer_2_ots_sets=t2_ots_sets,
            replays=prelim_replays,
            trainer_1_name=prelim_replays[0].trainer_1_name,
            trainer_2_name=prelim_replays[0].trainer_2_name,
        )
    except MissingOTSError as exc:
        print(f"ERROR [MISSING OTS]: {exc}", file=sys.stderr)
        return 3

    print(_format_sp_bounds_gfm(report))
    print()

    solved_t2_paste = report.build_paste()
    if args.save_opp_paste:
        out_p = Path(args.save_opp_paste)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(solved_t2_paste + "\n", encoding="utf-8")
        print(f"Saved solved opponent 66-SP paste -> `{out_p}`\n")

    if args.no_sim:
        return 0

    # Step 2: Re-parse replays with solved 66-SP opponent sets & run Tensor Core audit
    t2_solved_raw = parse_showdown_paste(solved_t2_paste)
    t2_solved_canon = {_canon_species(m.species): m for m in t2_solved_raw.values()}

    with tempfile.TemporaryDirectory(prefix="porygon_cli_") as tmp_dir:
        tmp_db = Path(tmp_dir) / "cli_ots.duckdb"
        ots_db = OTSRosterDatabase(db_path=tmp_db)
        gpu_engine = GPUReplayCoachEngine(ots_db=ots_db, device=args.device)
        app_state = ReplayCoachAppState(preload_sample=False, db_path=tmp_db, device=args.device) if args.export_csv else None

        turn_filter = set(args.turns) if args.turns else None
        for idx, (rp, raw_txt) in enumerate(zip(replay_paths, raw_replays), 1):
            final_replay = parse_showdown_replay(
                raw_txt,
                pov_trainer=resolved_pov,
                trainer_1_ots_sets=t1_sets_canon,
                trainer_2_ots_sets=t2_solved_canon,
                game_index=idx,
            )
            results: List[Dict[str, Any]] = []
            results_by_turn: Dict[int, Dict[str, Any]] = {}
            for snap in final_replay.turns:
                if turn_filter is not None and snap.turn_number not in turn_filter:
                    continue
                res = gpu_engine.analyze_turn(
                    final_replay,
                    turn_number=snap.turn_number,
                    num_mc=max(8, int(args.rng_samples)),
                    enable_two_ply=bool(args.two_ply),
                )
                results.append(res)
                results_by_turn[snap.turn_number] = res

            if results:
                print(
                    _format_game_audit_gfm(
                        game_index=idx,
                        filename=rp.name,
                        replay=final_replay,
                        turn_results=results,
                        lang=args.lang,
                        style=args.style,
                    )
                )
                print()

            if app_state is not None and results_by_turn:
                app_state.replay = final_replay
                exp = app_state.export_match_telemetry_csv(
                    team_folder=args.export_csv,
                    turn_results=results_by_turn,
                    lang=args.lang,
                    style=args.style,
                )
                print(
                    f"Exported Game {idx} telemetry ({exp['turns_written']} turns) -> `{exp['csv_path']}`\n"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
