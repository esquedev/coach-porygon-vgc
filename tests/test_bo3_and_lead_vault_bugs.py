# -*- coding: utf-8 -*-
"""Regression & security tests for v0.2.1 fixes:
1. Bo3 3-log upload after a prior 2-game match (zero stale 2-game carryover).
2. Lead Lab Vault full 15x15 x 6x6 matrix + Top-3 Turn-1 plays persistence,
   legacy row backward-compatibility, and secure CSV/JSON full-matrix export.
"""
from __future__ import annotations

import csv
import http.client
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading

import pytest

from apps.replay_coach.server import ReplayCoachAppState, make_handler
from engine.solver.lead_matchup_solver import LeadMatchupConfig, LeadMatchupSolver

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_REPLAY = (REPO_ROOT / "apps" / "replay_coach" / "sample_data" / "matchagotme_g1.html").read_text(encoding="utf-8")
SAMPLE_T1 = (REPO_ROOT / "data" / "teams" / "char_y_v4.txt").read_text(encoding="utf-8")
SAMPLE_T2 = (REPO_ROOT / "apps" / "replay_coach" / "sample_data" / "matchagotme_ots.txt").read_text(encoding="utf-8")


def test_bo3_three_log_upload_after_prior_two_game_bundle(tmp_path: Path) -> None:
    """Uploading 3 games after analyzing 2 games previously must cleanly return all 3 games."""
    st = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "bo3_test.duckdb", device="cpu")

    # 1. Simulate a previously loaded 2-game Bo3
    g1 = {"filename": "g1.html", "raw_input": SAMPLE_REPLAY}
    g2 = {"filename": "g2.html", "raw_input": SAMPLE_REPLAY.replace("|turn|1", "|turn|1\n|c|p1|game2", 1)}
    prev2 = st.preview_bo3_bundle(replays=[g1, g2], pov_trainer="treces_gc")
    assert prev2["ok"] and prev2["games_count"] == 2 and len(prev2["games"]) == 2

    # 2. Now preview a brand-new 3-game Bo3
    g3 = {"filename": "g3.html", "raw_input": SAMPLE_REPLAY.replace("|turn|1", "|turn|1\n|c|p1|game3", 1)}
    prev3 = st.preview_bo3_bundle(replays=[g1, g2, g3], pov_trainer="treces_gc")
    assert prev3["ok"] and prev3["games_count"] == 3 and len(prev3["games"]) == 3
    assert [g["game_index"] for g in prev3["games"]] == [1, 2, 3]
    assert len(st.bo3_games) == 3

    # 3. Verify frontend `renderPreviewBanner` & `renderBo3GameTabs` reset stale `state.app.bo3_games`
    js_src = (REPO_ROOT / "apps" / "replay_coach" / "static" / "app.js").read_text(encoding="utf-8")
    assert "state.app.bo3_games = [];" in js_src
    assert "const setupGames = state.bo3GamesMeta || [];" in js_src
    assert "btn-bo3-add-game" in js_src
    assert "replay-add-file-input" in js_src


def test_lead_lab_vault_preserves_full_matrix_top3_plays_and_secure_export(tmp_path: Path) -> None:
    """Verify full 15x15 x 6x6 matrix, Top-3 Turn-1 plays, legacy normalization, and CSV/JSON export."""
    st = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "vault_full.duckdb", device="cpu")

    # Build a fast compact 4-mon / 5-mon or synthetic full 6-mon result via real LeadMatchupSolver
    solver = LeadMatchupSolver(device="cpu")
    pool1 = solver._precompile_team_pool(SAMPLE_T1, trainer_id="trainer_1", require_explicit_spreads=True)
    pool2 = solver._precompile_team_pool(SAMPLE_T2, trainer_id="trainer_2", require_explicit_spreads=False)
    p12, p21 = solver._compute_pairwise_pressure(pool1, pool2)
    cfg = LeadMatchupConfig(preset="fast", num_rng_samples=4, cap_stay=6, cap_switch_per_mon=1, device="cpu", require_explicit_spreads=False)

    cell00 = solver._evaluate_lead_pair_factored(
        pool_t1=pool1,
        pool_t2=pool2,
        lead_1_idx=0,
        lead_2_idx=0,
        pressure_12=p12,
        pressure_21=p21,
        config=cfg,
        cancel_event=None,
    )
    cell00.pop("_raw_sub_scores", None)
    assert "sub_t1_top_plays" in cell00 and "sub_t2_top_plays" in cell00
    assert len(cell00["sub_t1_top_plays"]) == 6 and len(cell00["sub_t1_top_plays"][0]) == 6
    assert 1 <= len(cell00["sub_t1_top_plays"][0][0]) <= 3
    assert 1 <= len(cell00["sub_t2_top_plays"][0][0]) <= 3

    # Save a legacy-shaped Vault payload (missing t1_leads / payoff_matrix) to prove backward-compat normalization
    legacy_payload = {
        "trainer_1_species": list(pool1.display_species),
        "trainer_2_species": list(pool2.display_species),
        "trainer_1_leads": [cell00["lead_1"]],
        "trainer_2_leads": [cell00["lead_2"]],
        "modes_t1": [m.to_dict() for m in pool1.modes[:6]],
        "modes_t2": [m.to_dict() for m in pool2.modes[:6]],
        "global_game_value": cell00["score"],
        "trainer_1_top_brings": [{"rank": 1, "mode_idx": 0, "lead_idx": 0, "bench_idx": 0, "lead_species": cell00["lead_1"], "bench_species": cell00["best_t1_bench"], "nash_weight": 1.0, "ev_vs_opp_nash": cell00["score"], "worst_case_floor": cell00["score"]}],
        "trainer_2_top_brings": [{"rank": 1, "mode_idx": 0, "lead_idx": 0, "bench_idx": 0, "lead_species": cell00["lead_2"], "bench_species": cell00["best_t2_bench"], "opp_nash_weight": 1.0, "best_counter_mode_idx": 0, "best_counter_lead": cell00["lead_1"], "best_counter_bench": cell00["best_t1_bench"], "best_counter_score": cell00["score"]}],
        "heatmap_cells": [[cell00]],
        "elapsed_s": 1.2,
        "total_modes_evaluated": 36,
    }
    saved = st.ots_db.save_lead_lab_run(
        t1_name="=CMD|EvilTeam",
        t2_name="MatchaGotMe",
        t1_paste=SAMPLE_T1,
        t2_paste=SAMPLE_T2,
        preset="fast",
        result_payload=legacy_payload,
    )
    loaded = st.load_lead_lab_vault_run(saved["run_id"])
    res = loaded["result"]
    assert res["t1_leads"] == [cell00["lead_1"]]
    assert res["t2_leads"] == [cell00["lead_2"]]
    assert len(res["payoff_matrix"]) == 6 and len(res["payoff_matrix"][0]) == 6
    assert res["heatmap_cells"][0][0]["sub_t1_top_plays"] == cell00["sub_t1_top_plays"]

    # Verify HTTP /api/lead-lab/vault/export (CSV + JSON + Host security check)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(st))
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        # Legitimate CSV export
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", f"/api/lead-lab/vault/export?run_id={saved['run_id']}&format=csv", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        csv_bytes = resp.read()
        assert resp.status == 200
        assert resp.getheader("X-Content-Type-Options") == "nosniff"
        rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
        assert len(rows) == 1 + 36  # header + 6x6 bench pairs
        assert "t1_top3_plays" in rows[0] and rows[1][8] != ""
        conn.close()

        # Legitimate JSON export
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", f"/api/lead-lab/vault/export?run_id={saved['run_id']}&format=json", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        jdoc = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert len(jdoc["result"]["payoff_matrix"]) == 6
        conn.close()

        # DNS rebinding blocked on export endpoint too
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", f"/api/lead-lab/vault/export?run_id={saved['run_id']}&format=json", headers={"Host": "evil.example"})
        resp = conn.getresponse()
        _ = resp.read()
        assert resp.status == 403
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
