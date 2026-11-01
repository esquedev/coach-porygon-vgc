#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Telemetry & Competitive Log Engine
Adheres to SOLID Principles & PEP 8 via Repository Pattern.
Safely logs personal matches, scouted tournaments, and damage benchmarks to CSV.
"""

import argparse
import csv
import json
from pathlib import Path
import sys
import threading
from typing import Any, Dict, List, Optional, Union

# Enable engine package import
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from engine.repositories import (
        DATA_DIR,
        CsvDamageCalcRepository,
        CsvDiagnosticsRepository,
        CsvMatchRepository,
        IDamageCalcRepository,
        IDiagnosticsRepository,
        IMatchRepository,
        get_excel_serial_timestamp,
        sanitize_csv_cell,
    )
except ImportError:
    from repositories import (  # type: ignore
        DATA_DIR,
        CsvDamageCalcRepository,
        CsvDiagnosticsRepository,
        CsvMatchRepository,
        IDamageCalcRepository,
        IDiagnosticsRepository,
        IMatchRepository,
        get_excel_serial_timestamp,
        sanitize_csv_cell,
    )

MAX_PAYLOAD_BYTES = 1_048_576  # 1 MB hard cap against memory exhaustion (CWE-400)

RAW_MATCHES_CSV = DATA_DIR / "Raw_Matches.csv"
PLAYSTYLE_DIAGNOSTICS_CSV = DATA_DIR / "Playstyle_Diagnostics.csv"
SCOUTED_RAW_MATCHES_CSV = DATA_DIR / "Scouted_Raw_Matches.csv"
DAMAGE_CALCS_CSV = DATA_DIR / "Damage_Calculations.csv"

RAW_MATCHES_COLS = CsvMatchRepository.HEADERS
PLAYSTYLE_COLS = CsvDiagnosticsRepository.HEADERS
DAMAGE_CALC_COLS = CsvDamageCalcRepository.HEADERS

SCOUTED_MATCHES_COLS = [
    "Timestamp", "Scouted_Match_ID", "Scouted_Team_ID", "Player_Name",
    "Opponent_Name", "Tournament_Stage", "Result", "Turns", "Player_Mega",
    "Opponent_Mega", "Player_Lead_1", "Player_Lead_2", "Player_Back_1",
    "Player_Back_2", "Opponent_Lead_1", "Opponent_Lead_2", "Speed_Control_Active",
    "First_Blood_Side", "MVP_Pokemon", "Key_Turn_Notes"
]


def load_json_payload_safely(payload_arg: str) -> Union[dict, list]:
    """Safely parses either an inline JSON string or a JSON file path with size bounds."""
    stripped = payload_arg.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        if len(stripped.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("Payload exceeds 1 MB maximum size limit.")
        return json.loads(stripped)

    candidate_path = Path(payload_arg).resolve()
    if not candidate_path.exists() or not candidate_path.is_file():
        raise ValueError("Payload must be valid JSON or an existing JSON file path.")
    if candidate_path.stat().st_size > MAX_PAYLOAD_BYTES:
        raise ValueError(f"Payload file '{candidate_path.name}' exceeds 1 MB maximum size limit.")
    return json.loads(candidate_path.read_text(encoding="utf-8"))


def get_next_numeric_id(csv_path: Path, id_col_index: int = 1) -> float:
    """Computes next sequential numeric ID in given CSV file."""
    if not csv_path.exists():
        return 1.0
    max_id = 0.0
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) > id_col_index and row[id_col_index].strip():
                try:
                    max_id = max(max_id, float(row[id_col_index]))
                except ValueError:
                    continue
    return max_id + 1.0


_CSV_WRITE_LOCK = threading.RLock()


def append_csv_row(csv_path: Path, headers: List[str], row_dict: Dict[str, Union[str, float, int]]) -> None:
    """Appends sanitized row dictionary to CSV path in a thread-safe atomic manner (SEC-07)."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with _CSV_WRITE_LOCK:
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(headers)
            writer.writerow([sanitize_csv_cell(row_dict.get(col, "")) for col in headers])


def log_personal_match_to_csv(
    params: Dict[str, Any],
    match_repo: Optional[IMatchRepository] = None,
    diag_repo: Optional[IDiagnosticsRepository] = None
) -> Dict[str, Any]:
    """
    Appends a personal match to Raw_Matches.csv and Playstyle_Diagnostics.csv via Repository.
    Supports dependency injection for side-effect-free testing.
    """
    if match_repo is None:
        match_repo = CsvMatchRepository(RAW_MATCHES_CSV)
    if diag_repo is None:
        diag_repo = CsvDiagnosticsRepository(PLAYSTYLE_DIAGNOSTICS_CSV)

    ts = get_excel_serial_timestamp()
    match_id = match_repo.get_next_id()

    start_r = float(params.get("startRating", params.get("Start_Rating", 0)) or 0)
    end_r = float(params.get("endRating", params.get("End_Rating", 0)) or 0)
    net_r = end_r - start_r

    domain = params.get("misplayDomain", params.get("Mistake_Domain", "NONE"))
    code = params.get("misplayCode", params.get("Mistake_Code", "NONE"))
    turn = params.get("misplayTurn", params.get("Turn_Occurred", "0"))
    fix = params.get("deterministicFix", params.get("Deterministic_Fix", "NONE"))

    if code and code != "NONE":
        misplay_type = f"[CAT:{domain}|Turn:{turn}|Code:{code}|Detail:{fix}]"
    else:
        misplay_type = params.get("Misplay_Type", "None")

    raw_row = {
        "Timestamp": ts,
        "Match_ID": match_id,
        "Team_ID": params.get("teamId", params.get("Team_ID", "")),
        "Opponent": params.get("opponent", params.get("Opponent", "")),
        "Start_Rating": start_r,
        "End_Rating": end_r,
        "Net_Rating": net_r,
        "Result": params.get("result", params.get("Result", "")),
        "Turns": float(params.get("turns", params.get("Turns", 0)) or 0),
        "Enemy_Archetype": params.get("archetype", params.get("Enemy_Archetype", "")),
        "User_Mega": params.get("userMega", params.get("User_Mega", "None")),
        "Enemy_Mega": params.get("enemyMega", params.get("Enemy_Mega", "None")),
        "User_Lead_1": params.get("lead1", params.get("User_Lead_1", "")),
        "User_Lead_2": params.get("lead2", params.get("User_Lead_2", "")),
        "User_Back_1": params.get("back1", params.get("User_Back_1", "")),
        "User_Back_2": params.get("back2", params.get("User_Back_2", "")),
        "Enemy_Lead_1": params.get("enemyLead1", params.get("Enemy_Lead_1", "")),
        "Enemy_Lead_2": params.get("enemyLead2", params.get("Enemy_Lead_2", "")),
        "Speed_Control_Active": params.get("speedControl", params.get("Speed_Control_Active", "None")),
        "First_Blood_Side": params.get("firstBlood", params.get("First_Blood_Side", "")),
        "MVP_Pokemon": params.get("mvpMon", params.get("MVP_Pokemon", "")),
        "MVP_Move": params.get("mvpMove", params.get("MVP_Move", "")),
        "Misplay_Type": misplay_type,
        "Key_RNG_Event": params.get("rng", params.get("Key_RNG_Event", "None")),
        "Core_Lesson": params.get("lesson", params.get("Core_Lesson", "")),
        "Commentary": params.get("commentary", params.get("Commentary", ""))
    }

    match_repo.log_match(raw_row)

    diag_logged = False
    if code and code != "NONE":
        diag_row = {
            "Timestamp": ts,
            "Match_ID": match_id,
            "Format_Type": params.get("format", params.get("Format_Type", "Bo1_Ladder")),
            "Series_Game": params.get("game", params.get("Series_Game", "G1")),
            "Team_ID": raw_row["Team_ID"],
            "Opponent_Archetype": raw_row["Enemy_Archetype"],
            "Risk_Profile": params.get("riskProfile", params.get("Risk_Profile", "Normal")),
            "Decision_Pacing": params.get("pacing", params.get("Decision_Pacing", "Deliberate")),
            "Mistake_Domain": domain,
            "Mistake_Code": code,
            "Turn_Occurred": turn,
            "VP_Delta_Lost": float(params.get("vpLost", params.get("VP_Delta_Lost", 0)) or 0),
            "Root_Cognitive_Trap": params.get("trap", params.get("Root_Cognitive_Trap", "Autopilot")),
            "Deterministic_Fix": fix,
            "Eradication_Status": "Active"
        }
        diag_repo.log_diagnostic(diag_row)
        diag_logged = True

    return {
        "status": "LOGGED_PERSONAL_MATCH",
        "Match_ID": int(match_id),
        "Team_ID": raw_row["Team_ID"],
        "Result": raw_row["Result"],
        "Net_Rating": net_r,
        "Playstyle_Diagnostics_Logged": diag_logged,
        "Files_Updated": ["data/Raw_Matches.csv"] + (
            ["data/Playstyle_Diagnostics.csv"] if diag_logged else []
        )
    }


def log_scouted_match_to_csv(params: Dict[str, Any]) -> Dict[str, Any]:
    """Appends a scouted tournament match directly to data/Scouted_Raw_Matches.csv."""
    ts = get_excel_serial_timestamp()
    scouted_id = get_next_numeric_id(SCOUTED_RAW_MATCHES_CSV, id_col_index=1)

    row = {
        "Timestamp": ts,
        "Scouted_Match_ID": scouted_id,
        "Scouted_Team_ID": params.get("teamId", params.get("Scouted_Team_ID", "")),
        "Player_Name": params.get("player", params.get("Player_Name", "")),
        "Opponent_Name": params.get("opponent", params.get("Opponent_Name", "")),
        "Tournament_Stage": params.get("stage", params.get("Tournament_Stage", "Swiss")),
        "Result": params.get("result", params.get("Result", "")),
        "Turns": float(params.get("turns", params.get("Turns", 0)) or 0),
        "Player_Mega": params.get("playerMega", params.get("Player_Mega", "None")),
        "Opponent_Mega": params.get("oppMega", params.get("Opponent_Mega", "None")),
        "Player_Lead_1": params.get("lead1", params.get("Player_Lead_1", "")),
        "Player_Lead_2": params.get("lead2", params.get("Player_Lead_2", "")),
        "Player_Back_1": params.get("back1", params.get("Player_Back_1", "")),
        "Player_Back_2": params.get("back2", params.get("Player_Back_2", "")),
        "Opponent_Lead_1": params.get("oppLead1", params.get("Opponent_Lead_1", "")),
        "Opponent_Lead_2": params.get("oppLead2", params.get("Opponent_Lead_2", "")),
        "Speed_Control_Active": params.get("speedControl", params.get("Speed_Control_Active", "None")),
        "First_Blood_Side": params.get("firstBlood", params.get("First_Blood_Side", "")),
        "MVP_Pokemon": params.get("mvpMon", params.get("MVP_Pokemon", "")),
        "Key_Turn_Notes": params.get("notes", params.get("Key_Turn_Notes", ""))
    }
    append_csv_row(SCOUTED_RAW_MATCHES_CSV, SCOUTED_MATCHES_COLS, row)
    return {
        "status": "LOGGED_SCOUTED_MATCH",
        "Scouted_Match_ID": int(scouted_id),
        "Scouted_Team_ID": row["Scouted_Team_ID"],
        "Files_Updated": ["data/Scouted_Raw_Matches.csv"]
    }


def log_damage_calcs_to_csv(
    rows: List[Dict[str, Any]],
    calc_repo: Optional[IDamageCalcRepository] = None
) -> Dict[str, Any]:
    """Appends damage calculation rows to data/Damage_Calculations.csv via Repository."""
    if calc_repo is None:
        calc_repo = CsvDamageCalcRepository(DAMAGE_CALCS_CSV)

    logged_ids = []
    for r in rows:
        calc_id = r.get("Calc_ID", "CALC_NEW")
        row = {
            "Calc_ID": calc_id,
            "Attacker_Species": r.get("Attacker_Species", ""),
            "Attacker_Spread": r.get("Attacker_Spread", r.get("Attacker_SP", "")),
            "Attacker_Modifiers": r.get("Attacker_Modifiers", r.get("Attacker_Mods", "None")),
            "Move_Name": r.get("Move_Name", ""),
            "Defender_Species": r.get("Defender_Species", ""),
            "Defender_Spread": r.get("Defender_Spread", r.get("Defender_SP", "")),
            "Defender_Modifiers": r.get("Defender_Modifiers", r.get("Defender_Mods", "None")),
            "Min_Dmg_Pct": r.get("Min_Dmg_Pct", ""),
            "Max_Dmg_Pct": r.get("Max_Dmg_Pct", ""),
            "KO_Threshold": r.get("KO_Threshold", ""),
            "Damage_Rolls": r.get("Damage_Rolls", ""),
            "Strategic_Context": r.get("Strategic_Context", ""),
            "Raw_Showdown_Text": r.get("Raw_Showdown_Text", r.get("Raw_Text", ""))
        }
        calc_repo.log_calculation(row)
        logged_ids.append(calc_id)

    return {
        "status": "LOGGED_DAMAGE_CALCS",
        "Calc_IDs": logged_ids,
        "Files_Updated": ["data/Damage_Calculations.csv"]
    }


def main():
    """CLI entry point for match logging and playstyle diagnostics."""
    parser = argparse.ArgumentParser(description="Coach Porygon VGC Direct CSV Telemetry Logger")
    parser.add_argument("--mode", choices=["personal", "scouted", "calc", "tsv"], required=True)
    parser.add_argument("--payload", type=str, required=True, help="JSON string or path to JSON payload file")
    args = parser.parse_args()

    data = load_json_payload_safely(args.payload)

    if args.mode == "personal":
        if not isinstance(data, dict):
            raise ValueError("Personal match payload must be a JSON object.")
        res = log_personal_match_to_csv(data)
    elif args.mode == "scouted":
        if not isinstance(data, dict):
            raise ValueError("Scouted match payload must be a JSON object.")
        res = log_scouted_match_to_csv(data)
    else:
        rows = data if isinstance(data, list) else [data]
        res = log_damage_calcs_to_csv(rows)

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
