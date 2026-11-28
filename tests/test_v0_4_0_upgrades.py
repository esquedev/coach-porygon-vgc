# -*- coding: utf-8 -*-
"""Comprehensive v0.4.0 Upgrades Test Suite (Zero Test-Tricking / Real Physics & Concurrency).

Covers all 5 v0.4.0 engineering pillars:
  1. VictoryEquity v2.1 2-Turn Charge-Lock Calibration (Charizard-Mega-Y Sun + Archaludon
     Electro Shot trap vs Rain instant fire vs semi-invulnerable Phantom Force).
  2. Lead Lab Own-Lead x Opp-Lead Playbook Matrix & Batch K=128 Deep Audit Endpoint.
  3. Showdown Opponent Anonymization + Elo Extraction, True Wire Game # Assignment
     (including partial Bo3 uploads), and Embedded Player HTML Scrubbing.
  4. Split DuckDB Own vs. Rival Bases, Archetype Auto-Classification, Legacy Schema
     Migration, Multi-Facet Search API, and 7th Home Hub CTA Card.
  5. Hybrid GPU + Multi-Threaded CPU Dual-End Work-Stealing Turn Scheduler &
     Thread-Safe DuckDB `VGCDataRegistry`.
  6. Regulation M-D Prep Dossier v0.4.0 (Regieleki, Regidrago, Coach Porygon's
     Signature 66-SP Double Fantasy Core Team, V8 JS validation & M-C isolation).
"""
from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List

import duckdb
import numpy as np
import pytest

from apps.replay_coach.ots_db import (
    OTSRosterDatabase,
    classify_team_archetype,
    compute_lead_lab_matchup_hash,
)
from apps.replay_coach.protocol_parser import (
    anonymize_showdown_log_text,
    assign_bo3_game_numbers,
    extract_wire_game_number,
    format_showdown_opponent_label,
    parse_showdown_replay,
)
from apps.replay_coach.server import ReplayCoachAppState, make_handler
from engine.db_registry import get_registry
from engine.solver.hybrid_scheduler import (
    HybridTurnScheduler,
    TurnWorkItem,
    resolve_worker_topology,
)
from engine.solver.lead_matchup_solver import LeadMatchupSolver
from engine.vgc_tensor_core.compiler import (
    CHOICE_BASE_OPP_A_START,
    CHOICE_MEGA_OPP_A_START,
    ShowdownTensorCompiler,
)
from engine.vgc_tensor_core.state_machine import VgcTensorStateMachine
from engine.vgc_tensor_core.victory_equity import EQUITY_ENGINE_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_REPLAY = (REPO_ROOT / "apps" / "replay_coach" / "sample_data" / "matchagotme_g1.html").read_text(encoding="utf-8")
SAMPLE_T1 = (REPO_ROOT / "data" / "teams" / "char_y_v4.txt").read_text(encoding="utf-8")
SAMPLE_T2 = (REPO_ROOT / "apps" / "replay_coach" / "sample_data" / "matchagotme_ots.txt").read_text(encoding="utf-8")

_NATURE_MULT = {
    "Adamant": {"atk": 1.1, "spa": 0.9},
    "Jolly": {"spe": 1.1, "spa": 0.9},
    "Modest": {"spa": 1.1, "atk": 0.9},
    "Timid": {"spe": 1.1, "atk": 0.9},
    "Careful": {"spd": 1.1, "spa": 0.9},
}


def _make_mon(
    species: str,
    moves: List[str],
    ability: str,
    item: str = "none",
    nature: str = "Modest",
    sp: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    reg = get_registry()
    row = reg.get_pokemon(species)
    assert row is not None, f"Species '{species}' missing from DuckDB pokedex"
    base = row["baseStats"]
    sp_d = sp or {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32}
    nm = _NATURE_MULT.get(nature, {})
    hp_max = int(base["hp"]) + int(sp_d.get("hp", 0)) + 75
    stats = {
        k: int((int(base[k]) + int(sp_d.get(k, 0)) + 20) * float(nm.get(k, 1.0)))
        for k in ("atk", "def", "spa", "spd", "spe")
    }
    return {
        "species": species,
        "types": list(row["types"]),
        "hp_max": hp_max,
        "hp_cur": hp_max,
        "stats": stats,
        "ability": ability,
        "item": item,
        "moves": list(moves),
    }


def _make_bo3_wire_html(game_num: int, ts_epoch: int, replay_id: str) -> str:
    text = re.sub(r"\|t\|\d+", f"|t|{ts_epoch}", SAMPLE_REPLAY, count=1)
    text = re.sub(r'value="[^"]*"', f'value="{replay_id}"', text, count=1)
    # Strip any pre-existing |uhtml|bestof| lines (e.g. Game 1 in SAMPLE_REPLAY) before injecting target Game N
    text = re.sub(r"^\|uhtml\|bestof\|.*$", "", text, flags=re.MULTILINE)
    bestof_line = f"|uhtml|bestof|<h2><strong>Game {game_num}</strong> of <a href=\"/game-bestof3-test\">a best-of-3</a></h2>"
    return text.replace("|start", f"{bestof_line}\n|start", 1)


# =============================================================================
# 1. VICTORY EQUITY v2.1 2-TURN CHARGE-LOCK CALIBRATION
# =============================================================================


def test_charge_lock_calibration_charizard_sun_electro_shot_vs_rain_and_phantom_force() -> None:
    """Verify VictoryEquity v2.1 penalizes exposed 2-turn Electro Shot charging under Sun
    while preserving full reward for Rain instant-fire Electro Shot & semi-invulnerable Phantom Force."""
    assert EQUITY_ENGINE_VERSION == "v2_1_8pillar"
    sm = VgcTensorStateMachine(backend="torch", device="cpu")
    tc = ShowdownTensorCompiler(tables=sm.tables, device="cpu")

    # Scenario A: Charizard (Mega-Y Drought Sun) + Archaludon (Electro Shot) vs Incineroar + Primarina
    t1_sun = [
        _make_mon("Charizard", ["Heat Wave", "Weather Ball", "Solar Beam", "Protect"], "Blaze", "Charizardite Y", "Timid"),
        _make_mon("Archaludon", ["Electro Shot", "Dragon Pulse", "Flash Cannon", "Protect"], "Stamina", "Assault Vest", "Modest", {"hp": 20, "def": 14, "spa": 32}),
        _make_mon("Pelipper", ["Hurricane", "Weather Ball", "Wide Guard", "Protect"], "Drizzle", "Focus Sash", "Modest"),
        _make_mon("Venusaur", ["Sludge Bomb", "Earth Power", "Sleep Powder", "Protect"], "Chlorophyll", "Life Orb", "Modest"),
    ]
    t2_opp = [
        _make_mon("Incineroar", ["Flare Blitz", "Knock Off", "Parting Shot", "Protect"], "Intimidate", "Sitrus Berry", "Careful", {"hp": 32, "def": 16, "spd": 18}),
        _make_mon("Primarina", ["Hyper Voice", "Moonblast", "Haze", "Protect"], "Liquid Voice", "Leftovers", "Modest", {"hp": 32, "spa": 20, "def": 14}),
        _make_mon("Rillaboom", ["Grassy Glide", "Wood Hammer", "High Horsepower", "Protect"], "Grassy Surge", "Assault Vest", "Adamant", {"hp": 32, "atk": 32, "spd": 2}),
        _make_mon("Garchomp", ["Stomping Tantrum", "Dragon Claw", "Rock Slide", "Protect"], "Rough Skin", "Life Orb", "Jolly", {"hp": 2, "atk": 32, "spe": 32}),
    ]
    comp_sun = tc.compile_battle_state(t1_sun + t2_opp, field_spec={"weather": "none", "weather_turns": 0})
    # Mega Charizard-Y Heat Wave + Archaludon (Electro Shot vs Dragon Pulse vs Flash Cannon)
    a1_sun = np.array([
        [CHOICE_MEGA_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 0],  # Mega-Y + Electro Shot (exposed charge!)
        [CHOICE_MEGA_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 1],  # Mega-Y + Dragon Pulse (immediate)
        [CHOICE_MEGA_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 2],  # Mega-Y + Flash Cannon (immediate)
    ], dtype=np.int64)
    a2_sun = np.array([[CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 0]], dtype=np.int64)
    res_sun = sm.step(
        F=comp_sun.field_tensor,
        P=comp_sun.roster_tensor,
        M_moves=comp_sun.moves_tensor,
        trainer_1_choices=a1_sun,
        trainer_2_choices=a2_sun,
        num_mc_samples=32,
        rng_seed=42040,
        resolve_lead_entry_abilities=False,
    )
    u_sun = res_sun.stats.risk_adjusted_utility.detach().cpu().numpy()[:, 0]
    assert float(u_sun[1]) > float(u_sun[0]) + 0.35, f"Dragon Pulse ({u_sun[1]:.3f}) must beat Sun-charged Electro Shot ({u_sun[0]:.3f})"
    assert float(u_sun[2]) > float(u_sun[0]) + 0.35, f"Flash Cannon ({u_sun[2]:.3f}) must beat Sun-charged Electro Shot ({u_sun[0]:.3f})"

    # Scenario B: Active Rain (non-Mega) -> Electro Shot fires INSTANTLY with +1 SpA & 130 BP!
    comp_rain = tc.compile_battle_state(t1_sun + t2_opp, field_spec={"weather": "rain", "weather_turns": 5})
    a1_rain = np.array([
        [CHOICE_BASE_OPP_A_START + 3, CHOICE_BASE_OPP_A_START + 0],  # Zard Protect + Rain Electro Shot (instant!)
        [CHOICE_BASE_OPP_A_START + 3, CHOICE_BASE_OPP_A_START + 1],  # Zard Protect + Dragon Pulse
    ], dtype=np.int64)
    res_rain = sm.step(
        F=comp_rain.field_tensor,
        P=comp_rain.roster_tensor,
        M_moves=comp_rain.moves_tensor,
        trainer_1_choices=a1_rain,
        trainer_2_choices=a2_sun,
        num_mc_samples=32,
        rng_seed=42040,
        resolve_lead_entry_abilities=False,
    )
    u_rain = res_rain.stats.risk_adjusted_utility.detach().cpu().numpy()[:, 0]
    assert float(u_rain[0]) > float(u_rain[1]), (
        f"Rain instant Electro Shot ({u_rain[0]:.3f}) must outperform Dragon Pulse ({u_rain[1]:.3f})"
    )

    # Scenario C: Semi-invulnerable Phantom Force vanish turn is NOT penalized as an exposed charge-lock
    t1_pf = [
        _make_mon("Dragapult", ["Phantom Force", "Dragon Darts", "U-turn", "Protect"], "Clear Body", "Choice Band", "Jolly", {"hp": 2, "atk": 32, "spe": 32}),
        t1_sun[1], t1_sun[2], t1_sun[3],
    ]
    comp_pf = tc.compile_battle_state(t1_pf + t2_opp, field_spec={"weather": "none", "weather_turns": 0})
    a1_pf = np.array([[CHOICE_BASE_OPP_A_START + 0, CHOICE_BASE_OPP_A_START + 3]], dtype=np.int64)
    res_pf = sm.step(
        F=comp_pf.field_tensor,
        P=comp_pf.roster_tensor,
        M_moves=comp_pf.moves_tensor,
        trainer_1_choices=a1_pf,
        trainer_2_choices=a2_sun,
        num_mc_samples=16,
        rng_seed=42040,
        resolve_lead_entry_abilities=False,
    )
    # Dragapult must vanish intact (SEMI_INVULN == 1.0) and take zero damage from opponent attacks
    from engine.vgc_tensor_core.schema_and_tables import MonIdx
    pf_p = res_pf.P.detach().cpu().numpy()
    assert float(np.mean(pf_p[0, 0, :, 0, MonIdx.SEMI_INVULN])) == 1.0
    assert float(np.mean(pf_p[0, 0, :, 0, MonIdx.HP_CUR])) == float(pf_p[0, 0, 0, 0, MonIdx.HP_MAX])


# =============================================================================
# 2. LEAD LAB OWN-LEAD x OPP-LEAD PLAYBOOK & BATCH DEEP AUDIT
# =============================================================================


def test_lead_lab_deep_turn1_batch_endpoint_and_playbook_ui(tmp_path: Path) -> None:
    """Verify POST /api/lead-lab/deep-turn1-batch audits multiple Own x Opp pairs with
    canonical caching and zero absent Pokémon, and verify Playbook DOM hooks exist."""
    st = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "ll_batch.duckdb", device="cpu")
    solver = LeadMatchupSolver(device="cpu")
    pool1 = solver._precompile_team_pool(SAMPLE_T1, trainer_id="trainer_1", require_explicit_spreads=False)
    pool2 = solver._precompile_team_pool(SAMPLE_T2, trainer_id="trainer_2", require_explicit_spreads=False)
    m_hash = compute_lead_lab_matchup_hash(SAMPLE_T1, SAMPLE_T2, preset="fast")

    st._lead_jobs["job_batch"] = {
        "job_id": "job_batch",
        "t1_paste": SAMPLE_T1,
        "t2_paste": SAMPLE_T2,
        "matchup_hash": m_hash,
        "sprites": {},
    }
    m1_a, m1_b = pool1.modes[0], pool1.modes[5]
    m2_a = pool2.modes[0]
    pairs = [
        {
            "mode_1_idx": m1_a.mode_idx, "mode_2_idx": m2_a.mode_idx,
            "lead_1": list(m1_a.lead_species), "bench_1": list(m1_a.bench_species),
            "lead_2": list(m2_a.lead_species), "bench_2": list(m2_a.bench_species),
        },
        {
            "mode_1_idx": m1_b.mode_idx, "mode_2_idx": m2_a.mode_idx,
            "lead_1": list(m1_b.lead_species), "bench_1": list(m1_b.bench_species),
            "lead_2": list(m2_a.lead_species), "bench_2": list(m2_a.bench_species),
        },
    ]

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(st))
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=180)
        body = json.dumps({"job_id": "job_batch", "pairs": pairs, "num_mc": 16})
        conn.request("POST", "/api/lead-lab/deep-turn1-batch", body=body, headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert data["ok"] is True
        assert data["count"] == 2
        assert len(data["audits"]) == 2
        for item, req_p in zip(data["audits"], pairs):
            assert set(item["mode_1"]["lead_species"]) == set(req_p["lead_1"])
            assert len(item["top_actions"]) >= 1
            absent = set(pool1.display_species) - (set(req_p["lead_1"]) | set(req_p["bench_1"]))
            for act in item["top_actions"]:
                for ab in absent:
                    assert ab not in act["desc"], f"Absent mon '{ab}' leaked in batch audit: {act['desc']}"

        # Second call hits canonical DuckDB cache!
        conn.request("POST", "/api/lead-lab/deep-turn1-batch", body=body, headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"})
        resp2 = conn.getresponse()
        data2 = json.loads(resp2.read().decode("utf-8"))
        assert resp2.status == 200
        assert all(r["from_vault_cache"] is True for r in data2["audits"])
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    index_html = (REPO_ROOT / "apps" / "replay_coach" / "static" / "index.html").read_text(encoding="utf-8")
    for dom_id in ("ll-playbook-panel", "btn-ll-deep-batch", "ll-drill-own-switcher"):
        assert f'id="{dom_id}"' in index_html, f"Missing Lead Lab Playbook DOM id: {dom_id}"


# =============================================================================
# 3. SHOWDOWN ANONYMIZATION + ELO, TRUE WIRE GAME # & EMBED SCRUBBING
# =============================================================================


def test_showdown_anonymization_elo_true_wire_game_numbers_and_embed_scrub(tmp_path: Path, monkeypatch) -> None:
    """Verify opponent anonymization to 'Showdown Opponent (Elo N)', true wire Game #
    preservation on partial Bo3 uploads (e.g., Game 2 + Game 3), and embedded player scrub."""
    import apps.replay_coach.server as srv_mod
    monkeypatch.setattr(srv_mod, "TELEMETRY_ROOT", tmp_path / "telemetry")

    assert format_showdown_opponent_label(1229) == "Showdown Opponent (Elo 1229)"
    assert format_showdown_opponent_label(None) == "Showdown Opponent (Unrated)"

    # Low-level parser keeps raw name by default, anonymizes when requested
    raw_parsed = parse_showdown_replay(SAMPLE_REPLAY, pov_trainer="treces_gc", anonymize_opponent=False)
    assert raw_parsed.trainer_2_name == "MatchaGotMe"
    assert raw_parsed.trainer_2_elo == 1229

    anon_parsed = parse_showdown_replay(SAMPLE_REPLAY, pov_trainer="treces_gc", anonymize_opponent=True)
    assert anon_parsed.trainer_1_name == "treces_gc"
    assert anon_parsed.trainer_2_name == "Showdown Opponent (Elo 1229)"
    assert anon_parsed.raw_trainer_2_name == "MatchaGotMe"
    assert anon_parsed.is_anonymized_opponent is True

    # True wire Game # assignment on partial Bo3 (Game 2 & Game 3 ONLY -> must NOT become [1, 2]!)
    g2_html = _make_bo3_wire_html(2, 1795600500, "gen9vgc-2002")
    g3_html = _make_bo3_wire_html(3, 1795600900, "gen9vgc-2003")
    assert extract_wire_game_number(g2_html) == 2
    assert extract_wire_game_number(g3_html) == 3

    partial = [
        {"filename": "match_g3.html", "raw_input": g3_html},
        {"filename": "match_g2.html", "raw_input": g2_html},
    ]
    assert assign_bo3_game_numbers([partial[1], partial[0]]) == [2, 3]

    st = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "anon_bo3.duckdb", device="cpu")
    prev = st.preview_bo3_bundle(replays=partial, pov_trainer="treces_gc")
    assert prev["trainer_1_name"] == "treces_gc"
    assert prev["trainer_2_name"] == "Showdown Opponent (Elo 1229)"
    assert prev["trainer_2_elo"] == 1229
    assert [g["game_index"] for g in prev["games"]] == [2, 3]

    loaded = st.load_bo3_bundle(
        replays=partial,
        pov_trainer="treces_gc",
        t1_paste_text=SAMPLE_T1,
        t2_paste_text=SAMPLE_T2,
    )
    assert loaded["replay"]["trainer_2_name"] == "Showdown Opponent (Elo 1229)"
    assert [g["game_index"] for g in loaded["bo3_games"]] == [2, 3]
    assert loaded["replay"]["game_index"] == 2
    assert loaded["replay"]["wire_game_number"] == 2

    # Embedded Showdown replay player HTML MUST scrub opponent nickname (keeping POV name intact)
    scrubbed_html = st.render_official_showdown_player_html()
    assert "MatchaGotMe" not in scrubbed_html
    assert "Showdown Opponent (Elo 1229)" in scrubbed_html
    assert "treces_gc" in scrubbed_html

    # Direct utility test (including |uhtml|bestof| scoreboard & <title> scrubbing!)
    opp_wire_slot = "p1" if anon_parsed.pov_is_right_side else "p2"
    scrubbed_direct = anonymize_showdown_log_text(
        SAMPLE_REPLAY, opp_wire_slot, "MatchaGotMe", "Showdown Opponent (Elo 1229)"
    )
    assert "MatchaGotMe" not in scrubbed_direct
    assert "Showdown Opponent (Elo 1229)" in scrubbed_direct


# =============================================================================
# 4. SPLIT DUCKDB OWN VS. RIVAL BASES, ARCHETYPE SEARCH & 7TH HUB CTA CARD
# =============================================================================


def test_split_duckdb_own_vs_rival_migration_search_api_and_hub_cta(tmp_path: Path) -> None:
    """Verify idempotent migration from legacy 6-col schema, automatic archetype classification,
    Own vs Rival filtering via GET /api/rosters/search & POST /api/rosters/update-meta, and 7th CTA."""
    # 1. Create a legacy 6-column DuckDB database first and verify non-destructive migration!
    legacy_db_path = tmp_path / "legacy_v03.duckdb"
    con = duckdb.connect(str(legacy_db_path))
    con.execute(
        """
        CREATE TABLE ots_rosters (
            roster_id VARCHAR PRIMARY KEY,
            display_name VARCHAR NOT NULL,
            trainer_hint VARCHAR NOT NULL,
            paste_text VARCHAR NOT NULL,
            species_json VARCHAR NOT NULL,
            updated_at VARCHAR NOT NULL
        );
        """
    )
    con.execute(
        "INSERT INTO ots_rosters VALUES (?, ?, ?, ?, ?, ?)",
        [
            "legacy_user_team",
            "Legacy Char-Y Squad",
            "treces_gc",
            SAMPLE_T1,
            json.dumps(["Charizard", "Pelipper", "Archaludon", "Garchomp", "Raichu", "Venusaur"]),
            "2026-11-01T00:00:00Z",
        ],
    )
    con.close()

    # Open with v0.4.0 OTSRosterDatabase -> migrates cleanly & preserves legacy row!
    db = OTSRosterDatabase(db_path=legacy_db_path)
    migrated = db.get_roster("legacy_user_team")
    assert migrated is not None
    assert migrated["team_scope"] == "own"
    assert migrated["regulation"] == "Reg M-C"
    assert migrated["archetype"] in ("Sun / Weather", "Dual Weather", "Balance", "Rain")

    # Built-in rival seed is anonymized & classified as Trick Room!
    rival_seed = db.get_roster("matchagotme_camerupt_tr")
    assert rival_seed is not None
    assert rival_seed["team_scope"] == "rival"
    assert "MatchaGotMe" not in rival_seed["trainer_hint"]
    assert rival_seed["opponent_elo"] == 1229
    assert "Trick Room" in rival_seed["archetype"]

    # Archetype auto-classifier checks
    assert classify_team_archetype(SAMPLE_T2) == "Trick Room"
    assert "Sun" in classify_team_archetype(SAMPLE_T1) or "Weather" in classify_team_archetype(SAMPLE_T1)

    # Showdown ladder rival import MUST auto-anonymize nickname!
    db.save_roster(
        roster_id="ladder_rival_1",
        display_name="Ladder TR",
        trainer_hint="SecretLadderNick99",
        paste_text=SAMPLE_T2,
        team_scope="rival",
        regulation="Reg M-C",
        source_type="showdown_ladder",
        opponent_elo=1640,
    )
    saved_r = db.get_roster("ladder_rival_1")
    assert saved_r is not None
    assert saved_r["trainer_hint"] == "Showdown Opponent (Elo 1640)"
    assert "SecretLadderNick99" not in saved_r["trainer_hint"]

    # HTTP Search & Update-Meta endpoints
    st = ReplayCoachAppState(preload_sample=False, db_path=legacy_db_path, device="cpu")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(st))
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/api/rosters/search?scope=rival&archetype=Trick+Room&min_elo=1500", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        res = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert res["ok"] is True
        assert [r["roster_id"] for r in res["rosters"]] == ["ladder_rival_1"]

        # Move legacy team to Reg M-D + rival via POST /api/rosters/update-meta
        upd_body = json.dumps({
            "roster_id": "legacy_user_team",
            "team_scope": "rival",
            "regulation": "Reg M-D",
            "archetype": "Dual Weather",
            "opponent_elo": 1710,
        })
        conn.request("POST", "/api/rosters/update-meta", body=upd_body, headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"})
        resp2 = conn.getresponse()
        res2 = json.loads(resp2.read().decode("utf-8"))
        assert resp2.status == 200
        assert res2["ok"] is True
        assert res2["updated"]["team_scope"] == "rival"
        assert res2["updated"]["regulation"] == "Reg M-D"
        assert res2["updated"]["opponent_elo"] == 1710
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    index_html = (REPO_ROOT / "apps" / "replay_coach" / "static" / "index.html").read_text(encoding="utf-8")
    for dom_id in ("nav-hub-team-db", "cta-card-team-db", "view-team-db", "setup-compute-mode"):
        assert f'id="{dom_id}"' in index_html, f"Missing v0.4.0 Hub/Scheduler DOM id: {dom_id}"


# =============================================================================
# 5. HYBRID GPU + MULTI-CPU SCHEDULER & THREAD-SAFE DUCKDB REGISTRY
# =============================================================================


def test_hybrid_scheduler_dual_end_stealing_cancellation_and_thread_safe_duckdb(tmp_path: Path) -> None:
    """Verify HybridTurnScheduler dual-end cost routing, critical-path makespan guard,
    instant cancellation, thread-safe DuckDB registry, and real parallel replay execution."""
    # 1. Topology resolution invariants (Multi-Core CPU scales to 2..3 parallel CPU workers alongside CUDA!)
    topo_hyb_10 = resolve_worker_topology(mode="auto", has_cuda=True, total_turns=10, cpu_count=16)
    assert topo_hyb_10["use_gpu"] is True and topo_hyb_10["cpu_workers"] == 2

    topo_hyb_225 = resolve_worker_topology(mode="auto", has_cuda=True, total_turns=225, cpu_count=16)
    assert topo_hyb_225["use_gpu"] is True and topo_hyb_225["cpu_workers"] == 3

    topo_cpu = resolve_worker_topology(mode="cpu_parallel", has_cuda=True, total_turns=10, cpu_count=16)
    assert topo_cpu["use_gpu"] is False and topo_cpu["cpu_workers"] == 4

    topo_gpu = resolve_worker_topology(mode="gpu_only", has_cuda=True, total_turns=10, cpu_count=16)
    assert topo_gpu["use_gpu"] is True and topo_gpu["cpu_workers"] == 0

    # 2. Dual-end stealing order + makespan guard prevents CPU from stealing the heaviest turn
    items = [
        TurnWorkItem(turn_number=1, estimated_cost=800_000.0, b1=200, b2=100),
        TurnWorkItem(turn_number=2, estimated_cost=500_000.0, b1=120, b2=100),
        TurnWorkItem(turn_number=3, estimated_cost=200_000.0, b1=80, b2=60),
        TurnWorkItem(turn_number=4, estimated_cost=200_000.0, b1=80, b2=60),
        TurnWorkItem(turn_number=5, estimated_cost=8_000.0, b1=20, b2=10),
    ]
    sched = HybridTurnScheduler(mode="auto", has_cuda=True, cpu_count=8, cpu_slowdown_factor=4.0)

    def _mock_gpu(it: TurnWorkItem, lbl: str) -> str:
        time.sleep(0.03)
        return f"{lbl}:{it.turn_number}"

    def _mock_cpu(it: TurnWorkItem, wi: int, lbl: str) -> str:
        time.sleep(0.01)
        return f"{lbl}:{it.turn_number}"

    res_map, stats = sched.execute(items, gpu_runner=_mock_gpu, cpu_runner=_mock_cpu)
    assert set(res_map.keys()) == {1, 2, 3, 4, 5}
    assert stats.worker_turn_map[1] == "GPU"  # Heaviest MUST go to GPU!
    assert stats.worker_turn_map[5].startswith("CPU-W")  # Lightest stolen by CPU!
    assert stats.gpu_turns >= 2 and stats.cpu_turns >= 1

    # 3. Instant cancellation stops remaining turns
    cancel_ev = threading.Event()
    cancel_ev.set()
    res_cancel, stats_cancel = sched.execute(items, gpu_runner=_mock_gpu, cpu_runner=_mock_cpu, cancel_event=cancel_ev)
    assert len(res_cancel) == 0 and stats_cancel.gpu_turns == 0 and stats_cancel.cpu_turns == 0

    # 4. Thread-safe DuckDB `VGCDataRegistry` stress check (8 concurrent reader threads!)
    reg = get_registry()
    errors: List[Exception] = []

    def _reader(tid: int) -> None:
        try:
            for sp in ("Charizard", "Garchomp", "Pelipper", "Incineroar", "Primarina", "Raichu"):
                row = reg.get_pokemon(sp)
                assert row is not None and row["name"]
            rows = reg.query("SELECT name FROM pokedex LIMIT 5;")
            assert len(rows) == 5
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_reader, args=(i,)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert not errors, f"Concurrent VGCDataRegistry raised errors: {errors}"

    # 5. Thread-local RNG tile context isolation check (concurrent workers MUST never leak tile offsets!)
    from engine.vgc_tensor_core.rng_engine import _get_active_tile_context, rng_tile_context

    rng_leaks: List[Any] = []
    barrier = threading.Barrier(2)

    def _tile_worker(offset: int) -> None:
        with rng_tile_context(offset, offset * 2, 128, 128):
            barrier.wait()
            seen = _get_active_tile_context()
            if seen != (offset, offset * 2, 128, 128):
                rng_leaks.append((offset, seen))
            barrier.wait()
        if _get_active_tile_context() is not None:
            rng_leaks.append(("post_exit", _get_active_tile_context()))

    tw1 = threading.Thread(target=_tile_worker, args=(16,))
    tw2 = threading.Thread(target=_tile_worker, args=(48,))
    tw1.start(); tw2.start(); tw1.join(); tw2.join()
    assert not rng_leaks, f"RNG tile context leaked across threads: {rng_leaks}"
    assert _get_active_tile_context() is None

    # 6. Real multi-worker CPU execution on turns 9..10 of sample replay
    st = ReplayCoachAppState(preload_sample=True, db_path=tmp_path / "par_replay.duckdb", device="cpu")
    results, par_stats = st.gpu_engine.analyze_match_parallel(
        st.replay,
        start_turn=9,
        num_mc=16,
        compute_mode="cpu_parallel",
    )
    assert [r["turn"] for r in results] == [9, 10]
    assert par_stats.cpu_turns == 2
    assert all(r["compute_worker"].startswith("CPU-W") for r in results)
    assert _get_active_tile_context() is None


# =============================================================================
# 6. REGULATION M-D DOSSIER v0.4.0 (REGIS + SIGNATURE 66-SP TEAM + ISOLATION)
# =============================================================================


def test_reg_md_dossier_v0_4_0_regis_signature_team_and_mc_isolation() -> None:
    """Verify Regieleki, Regidrago, Coach Porygon's 66-SP Signature M-D Team,
    Champions item legality, V8 JS compilation, and strict Reg M-C asset isolation."""
    py_mini_racer = pytest.importorskip("py_mini_racer")
    dossier_path = REPO_ROOT / "reports" / "reg_md_meta_scout.html"
    assert dossier_path.is_file()
    content = dossier_path.read_text(encoding="utf-8")

    # All 8 tabs incl. Coach Porygon Signature Hero Tab
    for required_id in (
        'id="panel-signature"',
        'id="panel-calcs"',
        'id="panel-shift"',
        'id="panel-speed"',
        'id="panel-playbooks"',
        'id="panel-checker"',
        'id="panel-tiers"',
        'id="panel-blueprints"',
    ):
        assert required_id in content, f"Missing v0.4.0 Dossier panel: {required_id}"

    # Regieleki, Regidrago & full Signature Team present with zero broken sprites / zero Tera Blast
    for sp in ("Regieleki", "Regidrago", "Heatran-Mega", "Amoonguss", "Primarina", "Incineroar"):
        assert sp in content
    assert 'src=""' not in content
    assert "Tera Blast" not in content
    assert content.count("data:image/png;base64,") >= 200

    # Verify Signature Team Showdown paste uses ONLY Champions-legal items & 66-SP spreads
    m_pre = re.search(r'<pre class="sig-paste-pre">(.*?)</pre>', content, re.DOTALL)
    assert m_pre is not None
    sig_paste = m_pre.group(1)
    assert "Safety Goggles" not in sig_paste
    assert "Choice Specs" not in sig_paste
    for expected_line in (
        "Heatran @ Heatranite",
        "Regidrago @ Dragon Fang",
        "Regieleki @ Focus Sash",
        "Amoonguss @ Rocky Helmet",
        "Primarina @ Leftovers",
        "Incineroar @ Sitrus Berry",
    ):
        assert expected_line in sig_paste

    # Programmatically check COACH_PORYGON_SIGNATURE_TEAM 66-SP invariants
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen_md", REPO_ROOT / "scripts" / "generate_reg_md_meta_report.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sig_roster = mod.COACH_PORYGON_SIGNATURE_TEAM["roster"]
    assert len(sig_roster) == 6
    for mon in sig_roster:
        vals = list(mon["sp"].values())
        assert sum(vals) == 66, f"{mon['species']} SP sum != 66"
        assert all(0 <= v <= 32 for v in vals), f"{mon['species']} SP out of [0, 32]"

    # Embedded JS compiles cleanly under V8
    m_js = re.search(r"<script>(.*?)</script>", content, re.DOTALL)
    assert m_js is not None
    ctx = py_mini_racer.MiniRacer()
    ctx.eval("new Function(" + repr(m_js.group(1)) + ");")

    # Strict Regulation M-C isolation: Regieleki & Regidrago MUST NOT appear in assets/slug_map.json
    slug_map = json.loads((REPO_ROOT / "assets" / "slug_map.json").read_text(encoding="utf-8"))
    species_keys = {k.lower() for k in (slug_map.get("species") or {}).keys()}
    for rumored in ("regieleki", "regidrago", "amoonguss", "flamigo", "porygon-z", "latios-mega", "terrakion"):
        assert rumored not in species_keys, f"Rumored M-D species '{rumored}' leaked into slug_map.json!"
    assert (REPO_ROOT / "assets" / "sprites" / "Reg_M-D_rumored" / "regieleki.png").is_file()
    assert (REPO_ROOT / "assets" / "sprites" / "Reg_M-D_rumored" / "regidrago.png").is_file()


# =============================================================================
# 7. SINGLE-EXECUTION SCHEDULING, HARDWARE ATTRIBUTION & POST-JOIN ORDERED LOGS
# =============================================================================


def test_barrier_ordered_log_reconstruction_single_execution_and_hardware_tags(tmp_path: Path) -> None:
    """Verify every turn & Lead Lab cell executes strictly once across parallel workers,
    every log entry carries hardware attribution, and /api/analyze/stream waits for all
    workers to finish before emitting the strictly ordered reconstructed log."""
    # 1. HybridTurnScheduler strictly deduplicates & executes each turn AT MOST ONCE
    dup_items = [
        TurnWorkItem(turn_number=1, estimated_cost=500_000.0, b1=100, b2=100),
        TurnWorkItem(turn_number=1, estimated_cost=500_000.0, b1=100, b2=100),  # duplicate!
        TurnWorkItem(turn_number=2, estimated_cost=120_000.0, b1=50, b2=50),
        TurnWorkItem(turn_number=3, estimated_cost=20_000.0, b1=20, b2=20),
        TurnWorkItem(turn_number=3, estimated_cost=20_000.0, b1=20, b2=20),   # duplicate!
    ]
    call_counter: Dict[int, int] = {}
    cnt_lock = threading.Lock()
    sched = HybridTurnScheduler(mode="cpu_parallel", has_cuda=False, cpu_count=8)

    def _run_once(it: TurnWorkItem, wi: int, w_lbl: str) -> Dict[str, Any]:
        time.sleep(0.01)
        with cnt_lock:
            call_counter[it.turn_number] = call_counter.get(it.turn_number, 0) + 1
        return {
            "turn": it.turn_number,
            "compute_worker": w_lbl,
            "hardware_device": "CPU (PyTorch)",
            "pipeline_logs": [
                {"turn": it.turn_number, "phase": "COMPILE", "compute_worker": w_lbl, "hardware_device": "CPU (PyTorch)", "messages": {"es_vgc": f"T{it.turn_number}"}},
                {"turn": it.turn_number, "phase": "VERDICT", "compute_worker": w_lbl, "hardware_device": "CPU (PyTorch)", "messages": {"es_vgc": f"T{it.turn_number} OK"}},
            ],
        }

    res_map, st_stats = sched.execute(dup_items, gpu_runner=lambda it, l: _run_once(it, 0, l), cpu_runner=_run_once)
    assert sorted(res_map.keys()) == [1, 2, 3]
    assert call_counter == {1: 1, 2: 1, 3: 1}
    assert st_stats.execution_counts == {1: 1, 2: 1, 3: 1}
    assert all(st_stats.hardware_turn_map[t].startswith("CPU-W") for t in (1, 2, 3))

    # 2. Post-join ordered log reconstruction guarantees contiguous ascending turns (0, 1, 2, 3) with hardware tags
    from apps.replay_coach.gpu_coach_engine import GPUReplayCoachEngine
    ordered_res = [res_map[t] for t in sorted(res_map.keys())]
    reconstructed = GPUReplayCoachEngine.reconstruct_ordered_match_logs(ordered_res, sched_stats=st_stats, gpu_device_name="Mock GPU")
    assert reconstructed[0]["phase"] == "SCHEDULER"
    assert reconstructed[0]["compute_worker"] == "BALANCER"
    turn_seq = [int(e["turn"]) for e in reconstructed if int(e["turn"]) > 0]
    assert turn_seq == sorted(turn_seq), f"Reconstructed log turns out of order: {turn_seq}"
    # Verify turn transitions occur strictly once per turn (no repeated turn headers!)
    transitions = []
    for tn in turn_seq:
        if not transitions or transitions[-1] != tn:
            transitions.append(tn)
    assert transitions == [1, 2, 3], f"Turn headers repeated or disordered: {transitions}"
    assert all(e.get("compute_worker") and e.get("hardware_device") for e in reconstructed)

    # 3. Live HTTP SSE /api/analyze/stream waits until all workers join, emits zero mid-flight disordered `log` events,
    #    and delivers ordered turns + hardware-tagged reconstructed_logs inside `done`!
    app_st = ReplayCoachAppState(preload_sample=True, db_path=tmp_path / "sse_ordered.duckdb", device="cpu")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app_st))
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        conn.request("GET", "/api/analyze/stream?start_turn=9&num_mc=16&compute_mode=cpu_parallel", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        raw_sse = resp.read().decode("utf-8")
        assert resp.status == 200
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    events: List[tuple[str, Dict[str, Any]]] = []
    for chunk in raw_sse.strip().split("\n\n"):
        ev_name = ""
        ev_data = ""
        for ln in chunk.splitlines():
            if ln.startswith("event:"):
                ev_name = ln.split(":", 1)[1].strip()
            elif ln.startswith("data:"):
                ev_data = ln.split(":", 1)[1].strip()
        if ev_name and ev_data:
            events.append((ev_name, json.loads(ev_data)))

    ev_names = [e[0] for e in events]
    assert "scheduler" in ev_names
    assert "worker_progress" in ev_names
    assert "done" in ev_names
    assert "log" not in ev_names, "Interleaved live `log` events must not be streamed mid-flight!"

    done_payload = next(p for n, p in events if n == "done")
    assert [int(t["turn"]) for t in done_payload["ordered_turns"]] == [9, 10]
    assert done_payload["scheduler_stats"]["execution_counts"] == {"9": 1, "10": 1}
    rec_logs = done_payload["reconstructed_logs"]
    assert rec_logs[0]["phase"] == "SCHEDULER"
    rec_turns = [int(e["turn"]) for e in rec_logs if int(e["turn"]) > 0]
    assert rec_turns == sorted(rec_turns)
    rec_headers: List[int] = []
    for tn in rec_turns:
        if not rec_headers or rec_headers[-1] != tn:
            rec_headers.append(tn)
    assert rec_headers == [9, 10]
    assert all(str(e.get("compute_worker", "")).startswith("CPU-W") and e.get("hardware_device") for e in rec_logs if int(e["turn"]) > 0)

    # Verify skip_turns prevents re-executing already-completed turns
    res_skip, st_skip = app_st.gpu_engine.analyze_match_parallel(
        app_st.replay, start_turn=9, num_mc=16, compute_mode="cpu_parallel", skip_turns=[10]
    )
    assert [int(r["turn"]) for r in res_skip] == [9]
    assert st_skip.execution_counts == {9: 1}

    # 4. LeadMatchupSolver CPU parallel & Hybrid GPU+CPU Dual-End Work-Stealing execute every cell strictly once and tag hardware!
    four_mon_t1 = "\n\n".join(SAMPLE_T1.strip().split("\n\n")[:4])
    four_mon_t2 = "\n\n".join(SAMPLE_T2.strip().split("\n\n")[:4])
    from engine.solver.lead_matchup_solver import LeadMatchupConfig, HAS_TORCH
    import torch

    ll_solver = LeadMatchupSolver(device="cpu")
    ll_cfg = LeadMatchupConfig(
        preset="fast",
        device="cpu",
        compute_mode="cpu_parallel",
        num_rng_samples=4,
        cap_stay=6,
        cap_switch_per_mon=2,
        tile_size=12,
        require_explicit_spreads=False,
    )
    seen_pairs: List[tuple[int, int]] = []
    ll_res = ll_solver.solve_90x90_matchup(
        four_mon_t1,
        four_mon_t2,
        config=ll_cfg,
        progress_cb=lambda c: seen_pairs.append((int(c["lead_1_idx"]), int(c["lead_2_idx"]))),
    )
    assert len(seen_pairs) == 36
    assert len(set(seen_pairs)) == 36, "Duplicate Lead Lab cell computed!"
    assert sum(ll_res.worker_cell_counts.values()) == 36
    assert ll_res.compute_mode == "cpu_parallel"
    assert ll_res.hardware_device_name
    for row in ll_res.heatmap_cells:
        for cell in row:
            assert str(cell.get("compute_worker", "")).startswith("CPU-W")
            assert cell.get("hardware_device")

    if HAS_TORCH and torch.cuda.is_available():
        hyb_solver = LeadMatchupSolver(device="cuda")
        hyb_cfg = LeadMatchupConfig(
            preset="fast",
            device="cuda",
            compute_mode="auto",
            num_rng_samples=4,
            cap_stay=6,
            cap_switch_per_mon=2,
            tile_size=12,
            require_explicit_spreads=False,
        )
        hyb_seen: List[tuple[int, int]] = []
        hyb_res = hyb_solver.solve_90x90_matchup(
            four_mon_t1,
            four_mon_t2,
            config=hyb_cfg,
            progress_cb=lambda c: hyb_seen.append((int(c["lead_1_idx"]), int(c["lead_2_idx"]))),
        )
        assert len(hyb_seen) == 36
        assert len(set(hyb_seen)) == 36, "Duplicate Hybrid Lead Lab cell computed!"
        assert hyb_res.compute_mode in ("auto", "hybrid")
        assert sum(hyb_res.worker_cell_counts.values()) == 36
        assert hyb_res.worker_cell_counts.get("GPU", 0) >= 1, f"Expected GPU cells in Hybrid Lead Lab: {hyb_res.worker_cell_counts}"
        cpu_total_stolen = sum(v for k, v in hyb_res.worker_cell_counts.items() if k.startswith("CPU-W"))
        active_cpu_workers = [k for k, v in hyb_res.worker_cell_counts.items() if k.startswith("CPU-W") and v >= 1]
        assert cpu_total_stolen >= 2, f"Expected multi-CPU stolen cells in Hybrid Lead Lab: {hyb_res.worker_cell_counts}"
        assert len(active_cpu_workers) >= 2, f"Expected >=2 concurrent CPU workers stealing cells: {hyb_res.worker_cell_counts}"
        # GPU pops (0,0) from the left; CPU workers steal (5,5), (5,4), ... from the right!
        assert hyb_res.heatmap_cells[0][0]["compute_worker"] == "GPU"
        assert str(hyb_res.heatmap_cells[5][5]["compute_worker"]).startswith("CPU-W")

    # 5. Showdown replay player loads local /vendor/replay-embed.js primary with BattleScene/BattleMoveAnims readiness poller & pendingMessages queue
    player_html = app_st.render_official_showdown_player_html()
    assert 'src="/vendor/replay-embed.js"' in player_html
    assert "pendingMessages" in player_html
    assert "singleTurnTarget" in player_html
    vendor_embed = (REPO_ROOT / "apps" / "replay_coach" / "vendor" / "replay-embed.js").read_text(encoding="utf-8")
    assert "bootReplaysWhenReady" in vendor_embed
    assert "window.BattleScene" in vendor_embed and "window.BattleMoveAnims" in vendor_embed

    # 6. UI DOM hooks exist (including Lead Lab Hybrid scheduler selector & live worker strip)
    index_html = (REPO_ROOT / "apps" / "replay_coach" / "static" / "index.html").read_text(encoding="utf-8")
    app_js = (REPO_ROOT / "apps" / "replay_coach" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="live-workers-strip"' in index_html
    assert 'id="ll-compute-mode"' in index_html
    assert 'id="ll-workers-strip"' in index_html
    assert "reconstructed_logs" in app_js and "workerHardwareClass" in app_js and "renderLeadLabWorkersStrip" in app_js

