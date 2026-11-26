#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline Constrained Texel + TD Weight Tuner for the 8-Pillar Victory Equity Engine.

Reads passive feature observations from `data/telemetry/equity_samples.jsonl`, fits the
8 bounded tactical pillar weights via L-BFGS-B minimizing:
    L(w, alpha) = Texel_LogLoss(sigma(alpha * w^T phi), y)
                  + eta_td * MSE(w^T phi, V_2ply)
                  + lambda_reg * ||w - w_0||_2^2
while strictly locking the KO-equivalent material anchor (`w_hp=1.00`, `w_alive=0.75`,
`w_terminal=2.50`), enforcing non-negative safety box bounds, reporting K-fold CV
Brier/LogLoss vs anchor defaults, and gating export on the full `TestAT-10` tactical
calibration puzzle suite (`verify_victory_equity_puzzles`).
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize

from engine.vgc_tensor_core.equity_calibration import verify_victory_equity_puzzles
from engine.vgc_tensor_core.victory_equity import (
    DEFAULT_TUNED_WEIGHTS_PATH,
    EQUITY_ENGINE_VERSION,
    VictoryEquityWeights,
)

DEFAULT_SAMPLES_PATH: Path = Path("data/telemetry/equity_samples.jsonl")

# Strictly locked material anchor (1 Full Healthy KO = 1.75 Equity Points)
LOCKED_ANCHOR_FIELDS: Tuple[str, ...] = ("w_hp", "w_alive", "w_terminal")

# Tunable tactical parameters paired with (feature_key, lower_bound, upper_bound)
TUNABLE_SPEC: Tuple[Tuple[str, str, float, float], ...] = (
    ("w_threat", "threat", 0.08, 0.65),
    ("w_malposition", "malposition", 0.06, 0.55),
    ("w_restriction", "restriction", 0.08, 0.60),
    ("w_status", "status", 0.08, 0.60),
    ("w_boost", "boost", 0.04, 0.30),
    ("w_two_turn_prime", "two_turn_prime", 0.06, 0.50),
    ("w_resources", "resources", 0.04, 0.35),
    ("w_field_tempo", "field_tempo", 0.06, 0.55),
)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    clipped = np.clip(x, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def load_equity_samples(path: Path = DEFAULT_SAMPLES_PATH) -> List[Dict[str, Any]]:
    """Load valid JSONL equity training samples from `path`."""
    if not path.exists():
        return []
    samples: List[Dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        phi = obj.get("phi_raw")
        winner = obj.get("winner")
        if not isinstance(phi, dict) or winner not in (0, 1, 0.0, 1.0):
            continue
        samples.append(obj)
    return samples


def _samples_to_arrays(
    samples: Sequence[Dict[str, Any]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert sample dicts into `(phi_locked, phi_tunable, y_win, td_target, td_mask)`."""
    n = len(samples)
    phi_locked = np.zeros((n, 3), dtype=np.float64)
    phi_tun = np.zeros((n, len(TUNABLE_SPEC)), dtype=np.float64)
    y_win = np.zeros(n, dtype=np.float64)
    td_target = np.zeros(n, dtype=np.float64)
    td_mask = np.zeros(n, dtype=bool)

    for idx, rec in enumerate(samples):
        phi = rec["phi_raw"]
        phi_locked[idx, 0] = float(phi.get("hp", 0.0))
        phi_locked[idx, 1] = float(phi.get("alive", 0.0))
        phi_locked[idx, 2] = float(phi.get("terminal", 0.0))
        for j, (_wname, fkey, _lo, _hi) in enumerate(TUNABLE_SPEC):
            phi_tun[idx, j] = float(phi.get(fkey, 0.0))
        y_win[idx] = float(rec["winner"])
        p2v = rec.get("ply2_nash_value")
        if p2v is not None:
            td_target[idx] = float(p2v)
            td_mask[idx] = True
    return phi_locked, phi_tun, y_win, td_target, td_mask


def _evaluate_metrics(
    v_pred: np.ndarray,
    y_true: np.ndarray,
    alpha: float,
) -> Dict[str, float]:
    probs = np.clip(_sigmoid(alpha * v_pred), 1e-7, 1.0 - 1e-7)
    logloss = float(-np.mean(y_true * np.log(probs) + (1.0 - y_true) * np.log(1.0 - probs)))
    brier = float(np.mean((probs - y_true) ** 2))
    return {"log_loss": round(logloss, 5), "brier_score": round(brier, 5)}


def fit_equity_weights_from_samples(
    samples: Sequence[Dict[str, Any]],
    lambda_reg: float = 0.08,
    eta_td: float = 0.25,
    k_folds: int = 5,
    anchor: VictoryEquityWeights = VictoryEquityWeights(),
) -> Tuple[VictoryEquityWeights, Dict[str, Any]]:
    """Fit constrained tactical weights with L-BFGS-B and evaluate K-fold CV metrics."""
    if not samples:
        raise ValueError("Cannot tune equity weights on an empty sample set.")

    phi_locked, phi_tun, y_win, td_target, td_mask = _samples_to_arrays(samples)
    w_locked_vec = np.array([anchor.w_hp, anchor.w_alive, anchor.w_terminal], dtype=np.float64)
    w0_tun = np.array([getattr(anchor, spec[0]) for spec in TUNABLE_SPEC], dtype=np.float64)
    bounds = [(spec[2], spec[3]) for spec in TUNABLE_SPEC] + [(0.25, 4.0)]  # + sigmoid slope alpha

    def _fit_subset(idx_arr: np.ndarray) -> Tuple[np.ndarray, float]:
        pl = phi_locked[idx_arr]
        pt = phi_tun[idx_arr]
        yw = y_win[idx_arr]
        tdt = td_target[idx_arr]
        tdm = td_mask[idx_arr]
        mat_base = pl @ w_locked_vec

        def _obj(theta: np.ndarray) -> float:
            wt = theta[:-1]
            alpha = float(theta[-1])
            v = mat_base + pt @ wt
            probs = np.clip(_sigmoid(alpha * v), 1e-7, 1.0 - 1e-7)
            bce = float(-np.mean(yw * np.log(probs) + (1.0 - yw) * np.log(1.0 - probs)))
            reg = float(lambda_reg) * float(np.sum((wt - w0_tun) ** 2))
            td_loss = 0.0
            if np.any(tdm) and eta_td > 0.0:
                td_loss = float(eta_td) * float(np.mean((v[tdm] - tdt[tdm]) ** 2))
            return bce + td_loss + reg

        x_init = np.concatenate([w0_tun, np.array([1.25], dtype=np.float64)])
        opt = minimize(_obj, x_init, method="L-BFGS-B", bounds=bounds)
        wt_hat = np.clip(opt.x[:-1], [b[0] for b in bounds[:-1]], [b[1] for b in bounds[:-1]])
        alpha_hat = float(np.clip(opt.x[-1], 0.25, 4.0))
        return wt_hat, alpha_hat

    all_idx = np.arange(len(samples))
    wt_full, alpha_full = _fit_subset(all_idx)

    # K-fold cross-validation grouped by match_id if multiple matches exist
    n_samples = len(samples)
    eff_folds = max(2, min(int(k_folds), n_samples)) if n_samples >= 4 else 1
    cv_pred_tuned = np.zeros(n_samples, dtype=np.float64)
    cv_pred_anchor = np.zeros(n_samples, dtype=np.float64)
    cv_alpha_tuned = alpha_full

    if eff_folds >= 2:
        match_ids = [str(s.get("match_id", i)) for i, s in enumerate(samples)]
        unique_matches = list(dict.fromkeys(match_ids))
        if len(unique_matches) >= eff_folds:
            match_to_fold = {mid: i % eff_folds for i, mid in enumerate(unique_matches)}
            fold_assign = np.array([match_to_fold[mid] for mid in match_ids], dtype=np.int64)
        else:
            fold_assign = np.arange(n_samples) % eff_folds

        fold_alphas: List[float] = []
        for fold_i in range(eff_folds):
            val_mask = fold_assign == fold_i
            tr_idx = np.where(~val_mask)[0]
            va_idx = np.where(val_mask)[0]
            if len(tr_idx) == 0 or len(va_idx) == 0:
                continue
            wt_f, alpha_f = _fit_subset(tr_idx)
            fold_alphas.append(alpha_f)
            base_va = phi_locked[va_idx] @ w_locked_vec
            cv_pred_tuned[va_idx] = base_va + phi_tun[va_idx] @ wt_f
            cv_pred_anchor[va_idx] = base_va + phi_tun[va_idx] @ w0_tun
        if fold_alphas:
            cv_alpha_tuned = float(np.mean(fold_alphas))
    else:
        base_all = phi_locked @ w_locked_vec
        cv_pred_tuned = base_all + phi_tun @ wt_full
        cv_pred_anchor = base_all + phi_tun @ w0_tun

    tuned_metrics = _evaluate_metrics(cv_pred_tuned, y_win, cv_alpha_tuned)
    anchor_metrics = _evaluate_metrics(cv_pred_anchor, y_win, cv_alpha_tuned)

    # Assemble strictly locked + bounded VictoryEquityWeights
    w_dict = asdict(anchor)
    w_dict["w_hp"] = float(anchor.w_hp)
    w_dict["w_alive"] = float(anchor.w_alive)
    w_dict["w_terminal"] = float(anchor.w_terminal)
    for j, (wname, _fkey, lo, hi) in enumerate(TUNABLE_SPEC):
        w_dict[wname] = round(float(np.clip(wt_full[j], lo, hi)), 4)

    candidate = VictoryEquityWeights(**w_dict)
    report = {
        "samples_used": int(n_samples),
        "td_samples_used": int(np.sum(td_mask)),
        "k_folds": int(eff_folds),
        "lambda_reg": float(lambda_reg),
        "eta_td": float(eta_td),
        "sigmoid_alpha": round(float(alpha_full), 4),
        "cv_anchor": anchor_metrics,
        "cv_tuned": tuned_metrics,
        "engine_version": EQUITY_ENGINE_VERSION,
    }
    return candidate, report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Constrained Texel/TD tuner for Coach Porygon 8-Pillar Victory Equity weights."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_SAMPLES_PATH, help="JSONL sample log path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_TUNED_WEIGHTS_PATH, help="Output JSON weights path.")
    parser.add_argument("--lambda-reg", type=float, default=0.08, help="L2 shrinkage toward expert anchor.")
    parser.add_argument("--eta-td", type=float, default=0.25, help="TD consistency weight against 2-Ply Nash targets.")
    parser.add_argument("--k-folds", type=int, default=5, help="Number of cross-validation folds.")
    parser.add_argument("--min-samples", type=int, default=50, help="Minimum samples required before exporting.")
    parser.add_argument("--skip-puzzles", action="store_true", help="Skip TestAT-10 tactical puzzle safety gate (not recommended).")
    parser.add_argument("--dry-run", action="store_true", help="Report fit & CV metrics without writing output JSON.")
    args = parser.parse_args(argv)

    samples = load_equity_samples(args.input)
    print(f"[TUNE] Loaded {len(samples)} equity training samples from {args.input}")
    if len(samples) < args.min_samples:
        print(
            f"[TUNE] Not enough samples ({len(samples)} < --min-samples {args.min_samples}). "
            "Analyze more replays in Replay Coach Studio to accumulate passive telemetry."
        )
        return 1

    candidate, report = fit_equity_weights_from_samples(
        samples=samples,
        lambda_reg=args.lambda_reg,
        eta_td=args.eta_td,
        k_folds=args.k_folds,
    )
    print(f"[TUNE] {report['k_folds']}-Fold CV Anchor: {report['cv_anchor']}")
    print(f"[TUNE] {report['k_folds']}-Fold CV Tuned : {report['cv_tuned']}")
    print(f"[TUNE] Candidate Weights: {json.dumps(candidate.to_dict(), indent=2)}")

    if not args.skip_puzzles:
        print("[TUNE] Running TestAT-10 Tactical Calibration Puzzle Safety Gate...")
        puzzle_results = verify_victory_equity_puzzles(candidate)
        failed = [r for r in puzzle_results if not r.passed]
        for r in puzzle_results:
            tag = "PASS" if r.passed else "FAIL"
            print(f"  [{tag}] {r.name}: {r.detail}")
        if failed:
            print(f"[TUNE] ABORTED: {len(failed)} calibration puzzle(s) failed — weights NOT exported.")
            return 2

    if args.dry_run:
        print("[TUNE] Dry-run complete — no file written.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_obj = {
        "engine_version": EQUITY_ENGINE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "report": report,
        "weights": candidate.to_dict(),
    }
    args.output.write_text(json.dumps(export_obj, indent=2) + "\n", encoding="utf-8")
    print(f"[TUNE] Exported verified weights to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
