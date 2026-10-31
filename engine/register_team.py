#!/usr/bin/env python3
"""
Coach Porygon VGC — Regulation M-C Team Registration Engine
Parses Showdown team export pastes, validates format legality (Items, Species Clause, Item Clause, 66-SP),
calculates Level 50 stats, auto-generates the next sequential Team ID (e.g., T24),
appends to data/Teams.csv, and updates the Trainer Profile.
"""

import argparse
import csv
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
TEAMS_CSV_PATH = REPO_ROOT / "data" / "Teams.csv"
TRAINER_PROFILE_PATH = REPO_ROOT / "data" / "trainer_profile.json"

sys.path.insert(0, str(REPO_ROOT / "engine"))
from sp_calculator import validate_and_calculate_sp, STAT_ORDER, STAT_LABELS, ev_to_sp, MAX_SINGLE_STAT_SP
from validate_roster import validate_roster


def parse_pokemon_block(block: str) -> Optional[Dict]:
    """Parse single Showdown Pokémon paste block extracting species, item, nature, and SP."""
    lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
    if not lines:
        return None

    # Line 1: [Nickname (]Species[)] [([Gender])] [@ Item]
    first_line = lines[0]
    item = ""
    if "@" in first_line:
        name_part, item_part = first_line.split("@", 1)
        item = item_part.strip()
    else:
        name_part = first_line.strip()

    # Handle gender tag (M) / (F)
    name_part = re.sub(r"\s*\([MFmf]\)\s*$", "", name_part).strip()

    # Handle nickname: Nickname (Species)
    match_nick = re.match(r"^(.+?)\s*\((.+?)\)$", name_part)
    if match_nick:
        species = match_nick.group(2).strip()
        nickname = match_nick.group(1).strip()
    else:
        species = name_part.strip()
        nickname = species

    ability = ""
    nature = "Hardy"
    level = 50
    sp_spread = {k: 0 for k in STAT_ORDER}
    moves: List[str] = []

    stat_map = {
        "hp": "hp",
        "atk": "atk",
        "def": "def",
        "spa": "spa",
        "spd": "spd",
        "spe": "spe",
    }

    for line in lines[1:]:
        if line.startswith("Ability:"):
            ability = line.split(":", 1)[1].strip()
        elif line.startswith("Level:"):
            try:
                level = int(line.split(":", 1)[1].strip())
            except ValueError:
                level = 50
        elif line.startswith("SP:") or line.startswith("SPs:") or line.startswith("EVs:") or line.startswith("Stat Points:"):
            raw_evs = line.split(":", 1)[1].strip()
            # e.g. "2 HP / 12 Def / 28 SpA / 24 Spe"
            tokens = raw_evs.split("/")
            for token in tokens:
                token = token.strip()
                m = re.match(r"^(\d+)\s+([A-Za-z]+)$", token)
                if m:
                    val = int(m.group(1))
                    if val > MAX_SINGLE_STAT_SP:
                        val = ev_to_sp(val)
                    stat_key = m.group(2).lower()
                    if stat_key in stat_map:
                        sp_spread[stat_map[stat_key]] = val
        elif line.endswith("Nature"):
            nature_word = line.split()[0].strip()
            nature = nature_word
        elif line.startswith("-") or line.startswith("–"):
            move = line.lstrip("-–").strip()
            if move:
                moves.append(move)

    return {
        "species": species,
        "nickname": nickname,
        "item": item,
        "ability": ability,
        "nature": nature,
        "level": level,
        "sp_spread": sp_spread,
        "moves": moves,
        "raw_block": "\n".join(lines),
    }


def parse_showdown_paste(paste_text: str) -> List[Dict]:
    """Split and parse raw team export into a list of Pokémon dictionaries."""
    raw_blocks = re.split(r"\n\s*\n", paste_text.strip())
    parsed_pokemon = []
    for b in raw_blocks:
        p = parse_pokemon_block(b)
        if p and p["species"]:
            parsed_pokemon.append(p)
    return parsed_pokemon


def get_next_team_id(teams_csv_path: Path) -> str:
    """Determine next available sequential Team ID (Txx) from Teams.csv."""
    if not teams_csv_path.exists():
        return "T01"

    max_num = 0
    with open(teams_csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            tid = row[0].strip()
            m = re.match(r"^T(\d+)$", tid)
            if m:
                val = int(m.group(1))
                if val > max_num:
                    max_num = val

    return f"T{max_num + 1:02d}"


def update_trainer_profile(new_team_id: str) -> None:
    """Update trainer_profile.json with newly registered team ID."""
    if not TRAINER_PROFILE_PATH.exists():
        return
    try:
        data = json.loads(TRAINER_PROFILE_PATH.read_text(encoding="utf-8"))
        data["last_team_id"] = new_team_id
        TRAINER_PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[WARN]: Could not update trainer profile: {e}", file=sys.stderr)


def register_team(
    paste_text: str,
    team_name: Optional[str] = None,
    status: str = "Active",
    force: bool = False
) -> Dict:
    """Validate, assign next ID, and persist new team to data/Teams.csv."""
    parsed = parse_showdown_paste(paste_text)
    if not parsed:
        raise ValueError("[ERROR]: No valid Pokemon sets parsed from paste.")

    if len(parsed) != 6 and not force:
        print(f"[WARNING]: Paste contains {len(parsed)} Pokemon (standard roster is 6).", file=sys.stderr)

    # 1. Full Pre-Flight Legality Audit (Items, Item Clause, Species Clause, 66-SP)
    audit = validate_roster(paste_text)
    if not audit["is_valid"] and not force:
        err_msg = "\n".join(f"  * {err}" for err in audit["errors"])
        raise ValueError(f"Roster Legality Validation Failed:\n{err_msg}")

    # Determine team ID
    team_id = get_next_team_id(TEAMS_CSV_PATH)

    # Derive team name if omitted
    if not team_name:
        core_names = [p["species"].replace("Mega-", "").replace("-Mega", "") for p in parsed[:3]]
        team_name = " ".join(core_names) + " Core"

    date_str = datetime.date.today().isoformat()

    # Format slots Pokemon_1 to Pokemon_6
    slots = [""] * 6
    for i, p in enumerate(parsed[:6]):
        item_str = f" @ {p['item']}" if p["item"] else ""
        slots[i] = f"{p['species']}{item_str}"

    clean_export = "\n\n".join(p["raw_block"] for p in parsed)

    header = [
        "Team_ID", "Team_Name", "Date_Registered", "Status",
        "Pokemon_1", "Pokemon_2", "Pokemon_3", "Pokemon_4", "Pokemon_5", "Pokemon_6",
        "Showdown_Export", "Total_Matches", "Wins", "Win_Rate"
    ]

    file_exists = TEAMS_CSV_PATH.exists() and TEAMS_CSV_PATH.stat().st_size > 0

    with open(TEAMS_CSV_PATH, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(header)
        writer.writerow([
            team_id,
            team_name,
            date_str,
            status,
            slots[0],
            slots[1],
            slots[2],
            slots[3],
            slots[4],
            slots[5],
            clean_export,
            0,
            0,
            "0%"
        ])

    update_trainer_profile(team_id)

    return {
        "team_id": team_id,
        "team_name": team_name,
        "date_registered": date_str,
        "slots": slots,
        "audit": audit,
    }


def main():
    """CLI entry point for Showdown paste registration."""
    parser = argparse.ArgumentParser(description="Register a Showdown Team Paste into Coach Porygon VGC (Teams.csv)")
    parser.add_argument("--paste", type=str, help="Showdown team paste text")
    parser.add_argument("--file", type=str, help="Path to text file containing Showdown team paste")
    parser.add_argument("--name", type=str, default=None, help="Descriptive name for the team (e.g., 'Charizard Y Sun Offense')")
    parser.add_argument("--status", type=str, default="Active", choices=["Active", "Retired", "Testing"])
    parser.add_argument("--force", action="store_true", help="Bypass SP/item legality validation errors")
    args = parser.parse_args()

    paste_content = ""
    if args.paste:
        paste_content = args.paste
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"[ERROR]: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        paste_content = file_path.read_text(encoding="utf-8")
    else:
        if not sys.stdin.isatty():
            paste_content = sys.stdin.read()
        else:
            print("[INPUT REQUIRED]: Provide Showdown paste via --paste, --file, or pipe via stdin.")
            sys.exit(1)

    try:
        res = register_team(paste_content, team_name=args.name, status=args.status, force=args.force)
        print("=" * 70)
        print(f"SUCCESS: Team registered as [{res['team_id']}] — {res['team_name']}")
        print(f"Status: {args.status} | Date: {res['date_registered']}")
        print("=" * 70)
        print("Roster Summary (Legality & 66-SP Validated):")
        for s in res["audit"]["slots"]:
            types_str = "/".join(s["verified_types"]) if s["verified_types"] else "Unverified"
            stats_str = ", ".join(f"{k.upper()}: {v}" for k, v in s["final_stats"].items()) if s["final_stats"] else "N/A"
            moves_str = ", ".join(f"{m['move']} [{m['classification']}]" for m in s["moves"])
            print(f"  Slot {s['slot']}: {s['species']} [{types_str}] @ {s['item'] or 'None'} ({s['nature']})")
            print(f"          SP: {s['verification_str']}")
            print(f"          L50: {stats_str}")
            print(f"          Moves: {moves_str}")
        print("=" * 70)
        print(f"Updated data/Teams.csv and set last_team_id='{res['team_id']}' in data/trainer_profile.json.")
    except Exception as e:
        print(f"[REGISTRATION ERROR]: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
