# -*- coding: utf-8 -*-
"""Unit & Integration Tests for the Standalone Showdown Replay GPU Coach MVP."""
from __future__ import annotations

from pathlib import Path

from apps.replay_coach.ots_db import OTSRosterDatabase
from apps.replay_coach.protocol_parser import parse_showdown_replay
from apps.replay_coach.gpu_coach_engine import GPUReplayCoachEngine

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

    # Cache hit on second call
    res_t2_cached = engine.analyze_turn(replay, turn_number=2, min_prior=0.55, num_mc=64)
    assert res_t2_cached["from_cache"] is True
