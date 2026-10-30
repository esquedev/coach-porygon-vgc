import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Union

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MAX_PAYLOAD_BYTES = 1_048_576  # 1 MB hard cap against memory exhaustion (CWE-400)

RAW_MATCHES_CSV = DATA_DIR / "Raw_Matches.csv"
PLAYSTYLE_DIAGNOSTICS_CSV = DATA_DIR / "Playstyle_Diagnostics.csv"
SCOUTED_RAW_MATCHES_CSV = DATA_DIR / "Scouted_Raw_Matches.csv"
DAMAGE_CALCS_CSV = DATA_DIR / "Damage_Calculations.csv"

RAW_MATCHES_COLS = [
    "Timestamp", "Match_ID", "Team_ID", "Opponent", "Start_Rating", "End_Rating",
    "Net_Rating", "Result", "Turns", "Enemy_Archetype", "User_Mega", "Enemy_Mega",
    "User_Lead_1", "User_Lead_2", "User_Back_1", "User_Back_2", "Enemy_Lead_1",
    "Enemy_Lead_2", "Speed_Control_Active", "First_Blood_Side", "MVP_Pokemon",
    "MVP_Move", "Misplay_Type", "Key_RNG_Event", "Core_Lesson", "Commentary"
]

PLAYSTYLE_COLS = [
    "Timestamp", "Match_ID", "Format_Type", "Series_Game", "Team_ID",
    "Opponent_Archetype", "Risk_Profile", "Decision_Pacing", "Mistake_Domain",
    "Mistake_Code", "Turn_Occurred", "VP_Delta_Lost", "Root_Cognitive_Trap",
    "Deterministic_Fix", "Eradication_Status"
]

SCOUTED_MATCHES_COLS = [
    "Timestamp", "Scouted_Match_ID", "Scouted_Team_ID", "Player_Name",
    "Opponent_Name", "Tournament_Stage", "Result", "Turns", "Player_Mega",
    "Opponent_Mega", "Player_Lead_1", "Player_Lead_2", "Player_Back_1",
    "Player_Back_2", "Opponent_Lead_1", "Opponent_Lead_2", "Speed_Control_Active",
    "First_Blood_Side", "MVP_Pokemon", "Key_Turn_Notes"
]

DAMAGE_CALC_COLS = [
    "Calc_ID", "Attacker_Species", "Attacker_Spread", "Attacker_Modifiers",
    "Move_Name", "Defender_Species", "Defender_Spread", "Defender_Modifiers",
    "Min_Dmg_Pct", "Max_Dmg_Pct", "KO_Threshold", "Damage_Rolls",
    "Strategic_Context", "Raw_Showdown_Text"
]

# Matches safe signed numbers or Showdown stat stage prefixes (e.g. "-18.0", "+2 SpA", "-1 boost")
_SAFE_SIGNED_PREFIX_RE = re.compile(r"^[+-]\d+(\.\d+)?(\s|$)")


def sanitize_csv_cell(val: Union[str, float, int]) -> Union[str, float, int]:
    """
    Neutralizes CSV Formula / DDE Injection (OWASP A03 / CWE-1236) on untrusted strings
    while preserving legitimate numeric values and Showdown stage modifiers (e.g. '-1 boost').
    """
    if isinstance(val, (int, float)):
        return val
    s = str(val)
    if not s:
        return s
    if s[0] in ("=", "@", "\t", "\r"):
        return f"'{s}"
    if s[0] in ("+", "-"):
        if not _SAFE_SIGNED_PREFIX_RE.match(s) or "|" in s or "!" in s:
            return f"'{s}"
    return s


def load_json_payload_safely(payload_arg: str) -> Union[dict, list]:
    """
    Safely parses either an inline JSON string or a JSON file path with size bounds.
    """
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


def get_excel_serial_timestamp() -> float:
    """Returns current UTC time as an Excel/Sheets serial timestamp (days since 1899-12-30)."""
    epoch = datetime(1899, 12, 30, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return round((now - epoch).total_seconds() / 86400.0, 11)


def get_next_numeric_id(csv_path: Path, id_col_index: int = 1) -> float:
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


def append_csv_row(csv_path: Path, headers: List[str], row_dict: Dict[str, Union[str, float, int]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(headers)
        writer.writerow([sanitize_csv_cell(row_dict.get(col, "")) for col in headers])


def log_personal_match_to_csv(params: Dict[str, str]) -> Dict[str, object]:
    """
    Appends a personal match directly to:
      1. data/Raw_Matches.csv
      2. data/Playstyle_Diagnostics.csv (if a misplay code is recorded)
    """
    ts = get_excel_serial_timestamp()
    match_id = get_next_numeric_id(RAW_MATCHES_CSV, id_col_index=1)

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

    append_csv_row(RAW_MATCHES_CSV, RAW_MATCHES_COLS, raw_row)

    # Append to Playstyle_Diagnostics.csv if a misplay code was logged
    diag_logged = False
    if code and code != "NONE":
        diag_row = {
            "Timestamp": ts,
            "Match_ID": match_id,
            "Format_Type": params.get("formatType", params.get("Format_Type", "Bo1_Ladder")),
            "Series_Game": params.get("seriesGame", params.get("Series_Game", "Bo1_Single")),
            "Team_ID": raw_row["Team_ID"],
            "Opponent_Archetype": raw_row["Enemy_Archetype"],
            "Risk_Profile": params.get("riskProfile", params.get("Risk_Profile", "Minimax")),
            "Decision_Pacing": params.get("pacing", params.get("Decision_Pacing", "Calculated_15-45s")),
            "Mistake_Domain": domain,
            "Mistake_Code": code,
            "Turn_Occurred": float(turn or 0),
            "VP_Delta_Lost": float(params.get("vpDelta", params.get("VP_Delta_Lost", 0)) or 0),
            "Root_Cognitive_Trap": params.get("cognitiveTrap", params.get("Root_Cognitive_Trap", "NONE")),
            "Deterministic_Fix": fix,
            "Eradication_Status": params.get("Eradication_Status", "Remediating")
        }
        append_csv_row(PLAYSTYLE_DIAGNOSTICS_CSV, PLAYSTYLE_COLS, diag_row)
        diag_logged = True

    return {
        "status": "LOGGED_PERSONAL_MATCH",
        "Match_ID": int(match_id),
        "Team_ID": raw_row["Team_ID"],
        "Result": raw_row["Result"],
        "Net_Rating": net_r,
        "Playstyle_Diagnostics_Logged": diag_logged,
        "Files_Updated": ["data/Raw_Matches.csv"]
        + (["data/Playstyle_Diagnostics.csv"] if diag_logged else [])
    }


def log_scouted_match_to_csv(params: Dict[str, str]) -> Dict[str, object]:
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


def log_damage_calcs_to_csv(rows: List[Dict[str, str]]) -> Dict[str, object]:
    """Appends one or more damage calculation rows directly to data/Damage_Calculations.csv."""
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
        append_csv_row(DAMAGE_CALCS_CSV, DAMAGE_CALC_COLS, row)
        logged_ids.append(calc_id)
    return {
        "status": "LOGGED_DAMAGE_CALCS",
        "Calc_IDs": logged_ids,
        "Files_Updated": ["data/Damage_Calculations.csv"]
    }


def main():
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
