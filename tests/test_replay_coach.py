# -*- coding: utf-8 -*-
"""Unit & Integration Tests for the Standalone Showdown Replay GPU Coach MVP."""
from __future__ import annotations

from pathlib import Path

from apps.replay_coach.ots_db import OTSRosterDatabase
from apps.replay_coach.protocol_parser import parse_showdown_replay
from apps.replay_coach.gpu_coach_engine import GPUReplayCoachEngine, compute_match_summary
from apps.replay_coach.server import ReplayCoachAppState
from engine.telemetry.extractor import CSV_COLUMNS

SAMPLE_REPLAY = Path("apps/replay_coach/sample_data/matchagotme_g1.html")
SAMPLE_T1_PASTE = Path("data/teams/char_y_v4.txt")
SAMPLE_T2_PASTE = Path("apps/replay_coach/sample_data/matchagotme_ots.txt")


def test_ots_database_seeding_and_validation(tmp_path: Path) -> None:
    """Verify DuckDB OTS roster storage, 66-SP validation, and auto-matching."""
    db = OTSRosterDatabase(db_path=tmp_path / "test_ots.duckdb")
    rosters = db.list_rosters()
    assert len(rosters) >= 2

    val_t1 = db.validate_paste(SAMPLE_T1_PASTE.read_text(encoding="utf-8"))
    val_t2 = db.validate_paste(SAMPLE_T2_PASTE.read_text(encoding="utf-8"))
    assert val_t1["valid"] is True and val_t1["count"] == 6
    assert val_t2["valid"] is True and val_t2["count"] == 6

    matched_t2 = db.match_best_roster(
        "MatchaGotMe",
        ["Camerupt", "Incineroar", "Rillaboom", "Farigiraf", "Primarina", "Raichu"],
    )
    assert matched_t2 is not None
    assert matched_t2["roster_id"] == "matchagotme_camerupt_tr"


def test_protocol_parser_lossless_matchagotme_replay(tmp_path: Path) -> None:
    """Verify lossless Showdown wire-protocol parsing on MatchaGotMe vs treces_gc Game 1."""
    db = OTSRosterDatabase(db_path=tmp_path / "test_ots.duckdb")
    t1_sets = db.get_parsed_sets_by_species(SAMPLE_T1_PASTE.read_text(encoding="utf-8"))
    t2_sets = db.get_parsed_sets_by_species(SAMPLE_T2_PASTE.read_text(encoding="utf-8"))

    replay = parse_showdown_replay(
        SAMPLE_REPLAY.read_text(encoding="utf-8"),
        pov_trainer="treces_gc",
        trainer_1_ots_sets=t1_sets,
        trainer_2_ots_sets=t2_sets,
    )

    assert replay.trainer_1_name == "treces_gc"
    assert replay.trainer_2_name == "MatchaGotMe"
    assert replay.pov_is_right_side is True
    assert replay.winner == "treces_gc"
    assert len(replay.turns) == 10

    # Turn 1 start: Intimidate applied, Clear weather, no TR
    t1 = replay.turns[0]
    assert t1.weather is None and t1.trick_room_turns == 0
    assert t1.battle_state.trainer_1.get_pokemon("Charizard").boosts["atk"] == -1
    assert t1.trainer_1_slot_a_action is not None
    assert t1.trainer_1_slot_a_action.move_name == "Weather Ball"
    assert t1.trainer_1_slot_a_action.used_mega is True
    assert t1.trainer_1_slot_b_action is not None
    assert t1.trainer_1_slot_b_action.kind == "switch"
    assert t1.trainer_1_slot_b_action.switch_to_species == "Garchomp"

    # Turn 2 start: Farigiraf EXACT 57% post-Sitrus, Sun=4t, TR=4t, Hazard SpA-1
    t2 = replay.turns[1]
    assert t2.weather == "Sun" and t2.weather_turns == 4
    assert t2.trick_room_turns == 4
    far_t2 = t2.battle_state.trainer_2.get_pokemon("Farigiraf")
    assert far_t2 is not None and abs(far_t2.current_hp_pct - 57.0) < 0.5
    assert far_t2.item is None  # Sitrus consumed on T1
    assert t2.battle_state.trainer_1.get_pokemon("Charizard-Mega-Y").boosts["spa"] == -1

    # Turn 3 start: Drizzle Rain=4t, TR=3t, Camerupt fainted, Primarina entered
    t3 = replay.turns[2]
    assert t3.weather == "Rain" and t3.weather_turns == 4
    assert t3.trick_room_turns == 3

    # Turn 6: Incineroar Fake Out flinched Venusaur
    t6 = replay.turns[5]
    assert t6.trick_room_turns == 0
    assert len(t6.events.flinches) == 1
    assert t6.events.flinches[0]["trainer"] == "trainer_1"

    # Turn 8: Hazard critical hit on Primarina logged
    t8 = replay.turns[7]
    assert any(c["target_trainer"] == "trainer_2" for c in t8.events.crits)


def test_gpu_coach_engine_ieds_nash_and_commentary(tmp_path: Path) -> None:
    """Verify end-to-end GPU Nash + Strict/Weak IEDS + Zero-AI commentary on Turns 1 & 2."""
    db = OTSRosterDatabase(db_path=tmp_path / "test_ots.duckdb")
    t1_sets = db.get_parsed_sets_by_species(SAMPLE_T1_PASTE.read_text(encoding="utf-8"))
    t2_sets = db.get_parsed_sets_by_species(SAMPLE_T2_PASTE.read_text(encoding="utf-8"))
    replay = parse_showdown_replay(
        SAMPLE_REPLAY.read_text(encoding="utf-8"),
        pov_trainer="treces_gc",
        trainer_1_ots_sets=t1_sets,
        trainer_2_ots_sets=t2_sets,
    )

    engine = GPUReplayCoachEngine(db)
    res_t2 = engine.analyze_turn(replay, turn_number=2, min_prior=0.55, num_mc=64)

    assert res_t2["turn"] == 2
    assert res_t2["ieds"]["t1_total"] >= res_t2["ieds"]["t1_strict"] >= 1
    assert len(res_t2["top_actions"]) >= 1
    assert res_t2["commentary"]["badge"]
    assert len(res_t2["commentary"]["bullets"]) >= 3
    assert "Weather Ball" in res_t2["actual_action"]["desc"]
    assert "Pelipper" in res_t2["actual_action"]["desc"]

    # Every run executes live Tensor Core calculation (no stale turn cache)
    live_logs = []
    res_t2_live = engine.analyze_turn(
        replay, turn_number=2, min_prior=0.0, num_mc=32, log_cb=live_logs.append
    )
    assert res_t2_live["from_cache"] is False
    assert any(e["phase"] == "PHASE_4" for e in live_logs)
    assert not any(e["phase"] == "CACHE_HIT" for e in live_logs)


def test_studio_pipeline_logs_sprites_inline_ots_and_telemetry_export(tmp_path: Path, monkeypatch) -> None:
    """Verify 10-line per-phase logs, local sprite enrichment, inline OTS binding, match summary, and team CSV export."""
    import apps.replay_coach.server as srv_mod

    monkeypatch.setattr(srv_mod, "TELEMETRY_ROOT", tmp_path / "telemetry")
    db = OTSRosterDatabase(db_path=tmp_path / "studio_ots.duckdb")

    # 1. Sprite enrichment in validate_paste & delete_roster
    val = db.validate_paste(SAMPLE_T1_PASTE.read_text(encoding="utf-8"))
    assert val["valid"] is True
    assert val["pokemon"][0]["sprite_url"] is not None
    assert val["pokemon"][0]["item_sprite_url"] is not None

    db.save_roster("temp_roster", "Temp Roster", "Temp", SAMPLE_T1_PASTE.read_text(encoding="utf-8"))
    assert db.get_roster("temp_roster") is not None
    assert db.delete_roster("temp_roster") is True
    assert db.get_roster("temp_roster") is None

    # 2. Clean boot on Step 1 (replay=None), preview_replay, and inline OTS loading
    state = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "studio_ots.duckdb")
    assert state.replay is None

    raw_html = SAMPLE_REPLAY.read_text(encoding="utf-8")
    prev = state.preview_replay(raw_html, pov_trainer="treces_gc")
    assert prev["trainer_1_name"] == "treces_gc"
    assert prev["trainer_2_name"] == "MatchaGotMe"
    assert prev["num_turns"] == 10
    assert prev["trainer_1_preview"][0]["sprite_url"] is not None

    loaded = state.load_replay(
        raw_input=raw_html,
        pov_trainer="treces_gc",
        t1_paste_text=SAMPLE_T1_PASTE.read_text(encoding="utf-8"),
        t2_paste_text=SAMPLE_T2_PASTE.read_text(encoding="utf-8"),
    )
    assert loaded["active_t1_roster_id"] == "inline_ots"
    assert loaded["active_t2_roster_id"] == "inline_ots"

    # 3. Verify 10-line per-phase live execution log callback on fresh turn run
    live_logs = []
    res_t1 = state.gpu_engine.analyze_turn(
        state.replay,
        turn_number=1,
        num_mc=32,
        force_recompute=True,
        log_cb=live_logs.append,
    )
    emitted_phases = [e["phase"] for e in live_logs if not e.get("in_place")]
    for expected_phase in (
        "COMPILE",
        "PRUNE",
        "PHASE_1",
        "PHASE_2",
        "PHASE_3",
        "PHASE_4",
        "PHASE_5",
        "IEDS",
        "NASH_QRE",
        "VERDICT",
    ):
        assert expected_phase in emitted_phases, f"Missing phase log: {expected_phase}"

    # Verify board slots include local sprites and all 4 bilingual commentary profiles exist
    assert res_t1["board"]["trainer_1"][0]["sprite_url"] is not None
    for prof in ("es_vgc", "en_vgc", "es_scientific", "en_scientific"):
        assert prof in res_t1["commentary_variants"]

    # 4. Verify Match Summary calculation
    summary = compute_match_summary([res_t1])
    assert 0.0 <= summary["accuracy_pct"] <= 100.0
    assert summary["total_turns"] == 1
    assert summary["turning_point_turn"] == 1

    # 5. Verify Team-Scoped Telemetry CSV Export (and idempotent update without duplicate rows)
    exp1 = state.export_match_telemetry_csv("char_y_v4", {1: res_t1}, lang="es", style="vgc")
    assert exp1["ok"] is True
    assert exp1["turns_written"] == 10
    assert exp1["updated_existing"] is False

    exp2 = state.export_match_telemetry_csv("char_y_v4", {1: res_t1}, lang="en", style="scientific")
    assert exp2["ok"] is True
    assert exp2["updated_existing"] is True

    import csv
    csv_file = tmp_path / "telemetry" / "char_y_v4" / "battles_telemetry.csv"
    assert csv_file.exists()
    with open(csv_file, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10
    assert list(rows[0].keys()) == CSV_COLUMNS
    assert "[LEAD_EVAL]" in rows[0]["comment"]
    assert "[NASH_REGRET]" in rows[0]["comment"]


def test_4mode_bilingual_separation_cpu_fallback_and_cancellation(tmp_path: Path) -> None:
    """Verify strict VGC vs Scientific register separation, CPU-only portability, and clean cancellation."""
    import threading
    import pytest
    from engine.terminology import get_term_label
    from engine.vgc_tensor_core.state_machine import AnalysisCancelledError

    # 1. Verify alias resolution & strict VGC vs Scientific terminology
    assert get_term_label("Nash_Eq_Value", lang="es", style="vgc") == "Ventaja del turno"
    assert get_term_label("Nash_Eq_Value", lang="en", style="vgc") == "Turn advantage"
    assert get_term_label("Nash_Eq_Value", lang="en", style="scientific") == "Nash_Eq_Value"
    assert get_term_label("Downside_CVaR_10", lang="es", style="vgc") == "Impacto de mala suerte (peor 10% RNG)"
    assert get_term_label("Downside_CVaR_10", lang="en", style="scientific") == "CVaR_10_RNG_Floor"

    # 2. Verify CPU-only mode initializes and runs cleanly without requiring CUDA
    cpu_state = ReplayCoachAppState(
        preload_sample=False,
        db_path=tmp_path / "cpu_ots.duckdb",
        device="cpu",
    )
    summary = cpu_state.get_state_summary_unlocked()
    assert summary["device_type"] == "cpu"
    assert summary["recommended_k"] == 64

    cpu_state.load_replay(
        raw_input=SAMPLE_REPLAY.read_text(encoding="utf-8"),
        pov_trainer="treces_gc",
        t1_paste_text=SAMPLE_T1_PASTE.read_text(encoding="utf-8"),
        t2_paste_text=SAMPLE_T2_PASTE.read_text(encoding="utf-8"),
    )

    # 3. Verify immediate cancellation via cancel_event
    cancel_ev = threading.Event()
    cancel_ev.set()
    with pytest.raises(AnalysisCancelledError):
        cpu_state.gpu_engine.analyze_turn(
            cpu_state.replay,
            turn_number=1,
            num_mc=32,
            force_recompute=True,
            cancel_event=cancel_ev,
        )

    # 4. Run Turn 2 on CPU and verify all 4 commentary profiles are genuinely distinct
    #    and that VGC modes contain ZERO raw scientific abbreviations!
    res = cpu_state.gpu_engine.analyze_turn(
        cpu_state.replay,
        turn_number=2,
        num_mc=16,
        force_recompute=True,
    )
    cv = res["commentary_variants"]
    es_vgc_blob = cv["es_vgc"]["headline"] + " " + " ".join(b["tag"] + " " + b["text"] for b in cv["es_vgc"]["bullets"])
    en_vgc_blob = cv["en_vgc"]["headline"] + " " + " ".join(b["tag"] + " " + b["text"] for b in cv["en_vgc"]["bullets"])
    es_sci_blob = cv["es_scientific"]["headline"] + " " + " ".join(b["tag"] + " " + b["text"] for b in cv["es_scientific"]["bullets"])
    en_sci_blob = cv["en_scientific"]["headline"] + " " + " ".join(b["tag"] + " " + b["text"] for b in cv["en_scientific"]["bullets"])

    for forbidden_sci in (
        "Nash_Utility_Loss",
        "Downside_CVaR_10",
        "Risk_Adjusted_EV",
        "QRE_Human_Prob",
        "IEDS",
        "CVaR",
        "QRE",
        "Minimax",
        "1-ply",
    ):
        assert forbidden_sci not in es_vgc_blob, f"Scientific token '{forbidden_sci}' leaked into es_vgc!"
        assert forbidden_sci not in en_vgc_blob, f"Scientific token '{forbidden_sci}' leaked into en_vgc!"

    assert es_vgc_blob != en_vgc_blob
    assert es_vgc_blob != es_sci_blob
    assert en_vgc_blob != en_sci_blob
    assert any(tok in es_sci_blob for tok in ("IEDS", "Nash_Eq_Value", "Nash_Utility_Loss", "CVaR_10"))
    assert any(tok in en_sci_blob for tok in ("IEDS", "Nash_Eq_Value", "Nash_Utility_Loss", "CVaR_10"))


def test_bug_report_generation_and_email_link(tmp_path: Path, monkeypatch) -> None:
    """Verify bug log persistence, diagnostic formatting, and direct mailto link to esquedevil94@gmail.com."""
    import apps.replay_coach.server as srv_mod

    monkeypatch.setattr(srv_mod, "BUG_REPORTS_DIR", tmp_path / "bug_logs")
    st = ReplayCoachAppState(preload_sample=False, db_path=tmp_path / "bug_ots.duckdb", device="cpu")
    res = st.create_bug_report(
        user_message="Hurricane was suggested under Sun without Pelipper switch.",
        client_context={
            "active_step": "review",
            "lang": "es",
            "style": "vgc",
            "num_mc": 128,
            "current_turn": 5,
            "recent_pipeline_logs": ["[T5 PHASE_4] simulated"],
        },
    )
    assert res["ok"] is True
    assert res["recipient"] == "esquedevil94@gmail.com"
    assert res["mailto_url"].startswith("mailto:esquedevil94@gmail.com?subject=")
    assert "Hurricane was suggested under Sun" in res["report_text"]
    saved = tmp_path / "bug_logs" / res["filename"]
    assert saved.exists()
    assert "[T5 PHASE_4] simulated" in saved.read_text(encoding="utf-8")


def test_two_ply_lookahead_auto_infer_and_session_analytics(tmp_path: Path, monkeypatch) -> None:
    """Verify Opportunities 3, 4, and 5 end-to-end:
    - Opportunity 3: Selective 2-Ply Lookahead on Strict-IEDS core (`enable_two_ply=True`, `PLY_2` log)
    - Opportunity 4: 1-Click Auto-Infer Opponent OTS from Regional DuckDB (`infer_ots_from_replay`)
    - Opportunity 5: Bo3 / Tournament Session Analytics Dashboard (`get_telemetry_session_summary`)
    """
    import apps.replay_coach.server as srv_mod

    monkeypatch.setattr(srv_mod, "TELEMETRY_ROOT", tmp_path / "telemetry")
    st = ReplayCoachAppState(preload_sample=True, db_path=tmp_path / "opp345_ots.duckdb", device="cpu")
    assert st.replay is not None

    # 1. Opportunity 3: Selective 2-Ply Lookahead on Strict-IEDS core
    res_2ply = st.gpu_engine.analyze_turn(
        st.replay,
        turn_number=2,
        num_mc=16,
        enable_two_ply=True,
    )
    assert res_2ply["two_ply"]["enabled"] is True
    assert res_2ply["two_ply"]["cells_evaluated"] >= 1
    assert any(lg["phase"] == "PLY_2" for lg in res_2ply["pipeline_logs"])

    # 2. Opportunity 4: 1-Click Auto-Infer Opponent OTS from Regional DuckDB
    inf = st.infer_ots_from_replay(raw_input="", side="t2", pov_trainer="treces_gc", use_sample=True)
    assert inf["ok"] is True
    assert inf["side"] == "t2"
    assert inf["inferred_count"] == 6
    assert inf["validation"]["valid"] is True
    assert inf["validation"]["count"] == 6
    for mon in inf["validation"]["pokemon"]:
        assert mon["total_sp"] == 66
        assert len(mon["moves"]) == 4

    # 3. Opportunity 5: Export telemetry + aggregate Bo3 Session Analytics summary
    exp = st.export_match_telemetry_csv(
        team_folder="char_y_test",
        turn_results={2: res_2ply},
        lang="es",
        style="vgc",
    )
    assert exp["ok"] is True
    summary = st.get_telemetry_session_summary(team_folder="char_y_test")
    assert summary["ok"] is True
    assert summary["total_matches"] == 1
    assert summary["total_turns"] == len(st.replay.turns)
    assert len(summary["matches"]) == 1
    assert summary["matches"][0]["trainer_1"] == "treces_gc"
    assert summary["matches"][0]["trainer_2"] == "MatchaGotMe"
    assert summary["avg_accuracy_pct"] is not None
    assert "lead" in summary["mistakes_by_phase"]
    assert "midgame" in summary["mistakes_by_phase"]
    assert "endgame" in summary["mistakes_by_phase"]



