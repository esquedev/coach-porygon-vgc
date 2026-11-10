# -*- coding: utf-8 -*-
"""Coach Porygon VGC — Esports Turn Telemetry Extractor & CSV Logger.

Ingests raw Pokémon Showdown chat logs, extracts turn-by-turn state transitions,
damage dealt/taken, variance events (crits, flinches, misses), active slots,
and writes structured records to CSV with an open `comment` column for coach analysis.
Strictly adheres to `trainer_1` (POV) and `trainer_2` (Opponent) identifiers.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.parser.showdown_parser import parse_showdown_chat_log


@dataclass
class TurnTelemetryRecord:
    """Telemetry record for a single battle turn."""

    match_id: str
    timestamp: str
    turn: int
    trainer_1: str
    trainer_2: str
    trainer_1_active_1: str
    trainer_1_active_2: str
    trainer_2_active_1: str
    trainer_2_active_2: str
    trainer_1_moves: str
    trainer_2_moves: str
    damage_dealt_to_trainer_2: float
    damage_dealt_to_trainer_1: float
    faints_this_turn: str
    variance_events: str
    weather: str
    terrain: str
    field_conditions: str
    winner: str
    comment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for CSV writing."""
        return asdict(self)


def _generate_match_id(raw_log: str) -> str:
    """Generate or extract a canonical match ID from the battle log."""
    m = re.search(r"battle-([a-zA-Z0-9_\-]+)", raw_log)
    if m:
        return f"battle-{m.group(1)}"
    # Generate 12-char SHA-256 fingerprint from cleaned log
    cleaned = re.sub(r"\s+", "", raw_log)
    h = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]
    return f"match-{h}"


def extract_turn_telemetry(
    raw_log: str,
    pov_trainer: Optional[str] = None,
    user_team_paste: Optional[str] = None,
) -> List[TurnTelemetryRecord]:
    """Parse a raw Showdown log and extract turn-by-turn telemetry records.

    Parameters:
        raw_log: Raw Pokémon Showdown battle chat log text.
        pov_trainer: Username of the POV trainer (trainer_1). If omitted, inferred.
        user_team_paste: Optional team paste for the POV trainer.

    Returns:
        List of TurnTelemetryRecord instances, one for each turn played.
    """
    battle = parse_showdown_chat_log(
        raw_log,
        pov_trainer=pov_trainer,
        user_team_paste=user_team_paste,
    )

    match_id = _generate_match_id(raw_log)
    iso_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    trainer_1_name = battle.trainer_1.trainer_name or "trainer_1"
    trainer_2_name = battle.trainer_2.trainer_name or "trainer_2"
    winner_name = battle.winner or "Ongoing"

    # Split log by turns to extract turn-specific moves and damage
    lines = [line.strip() for line in raw_log.splitlines() if line.strip()]

    # Tracking state
    current_turn = 0
    t1_active: List[str] = list(battle.trainer_1.leads) if battle.trainer_1.leads else []
    t2_active: List[str] = list(battle.trainer_2.leads) if battle.trainer_2.leads else []

    # Map of turn_num -> dict of aggregated events
    turn_data: Dict[int, Dict[str, Any]] = {}

    def get_turn_entry(t_num: int) -> Dict[str, Any]:
        if t_num not in turn_data:
            turn_data[t_num] = {
                "t1_active_1": t1_active[0] if len(t1_active) > 0 else "",
                "t1_active_2": t1_active[1] if len(t1_active) > 1 else "",
                "t2_active_1": t2_active[0] if len(t2_active) > 0 else "",
                "t2_active_2": t2_active[1] if len(t2_active) > 1 else "",
                "t1_moves": [],
                "t2_moves": [],
                "dmg_to_t2": 0.0,
                "dmg_to_t1": 0.0,
                "faints": [],
                "variance": [],
                "weather": "None",
                "terrain": "None",
                "field_conditions": [],
            }
        return turn_data[t_num]

    last_active_attacker: Optional[str] = None
    last_attacker_is_t2 = False

    cur_weather = "None"
    cur_terrain = "None"
    t1_tailwind = False
    t2_tailwind = False
    trick_room = False
    t1_screens: Set[str] = set()
    t2_screens: Set[str] = set()

    for line in lines:
        # Turn marker
        m_turn = re.match(r"^Turn\s+(\d+)", line)
        if m_turn:
            current_turn = int(m_turn.group(1))
            entry = get_turn_entry(current_turn)
            # Snapshot active slots at start of turn
            entry["t1_active_1"] = t1_active[0] if len(t1_active) > 0 else ""
            entry["t1_active_2"] = t1_active[1] if len(t1_active) > 1 else ""
            entry["t2_active_1"] = t2_active[0] if len(t2_active) > 0 else ""
            entry["t2_active_2"] = t2_active[1] if len(t2_active) > 1 else ""
            entry["weather"] = cur_weather
            entry["terrain"] = cur_terrain
            continue

        if current_turn == 0:
            # Check pre-turn 1 leads
            m_go = re.match(r"^Go!\s+(.+?)!", line)
            if m_go:
                mon = m_go.group(1).split("(")[-1].replace(")", "").strip()
                if mon not in t1_active:
                    t1_active.append(mon)

            m_sent = re.match(r"^(.+?)\s+sent out\s+(.+?)!", line)
            if m_sent:
                trainer_p = m_sent.group(1).strip().replace("☆", "")
                mon = m_sent.group(2).split("(")[-1].replace(")", "").strip()
                if trainer_p.lower() == trainer_1_name.lower():
                    if mon not in t1_active:
                        t1_active.append(mon)
                else:
                    if mon not in t2_active:
                        t2_active.append(mon)

        entry = get_turn_entry(current_turn if current_turn > 0 else 1)

        # Weather / Terrain announcements
        if "The sunlight turned harsh" in line:
            cur_weather = "Sun"
        elif "started to rain" in line or "Rain continues" in line:
            cur_weather = "Rain"
        elif "sandstorm kicked up" in line:
            cur_weather = "Sand"
        elif "Grass grew to cover the battlefield" in line:
            cur_terrain = "Grassy"
        elif "surged across the battlefield" in line:
            cur_terrain = "Electric"
        elif "Mist swirled" in line:
            cur_terrain = "Misty"

        # Field Conditions
        if "Tailwind blew from behind your team" in line:
            t1_tailwind = True
        elif "Tailwind blew from behind the opposing team" in line:
            t2_tailwind = True
        elif "The tailwind petered out" in line:
            t1_tailwind = False
            t2_tailwind = False
        elif "twisted the dimensions" in line:
            trick_room = not trick_room
        elif "Light Screen" in line and "rose" in line:
            if "opposing" in line:
                t2_screens.add("Light Screen")
            else:
                t1_screens.add("Light Screen")
        elif "Reflect" in line and "rose" in line:
            if "opposing" in line:
                t2_screens.add("Reflect")
            else:
                t1_screens.add("Reflect")

        # Switches during battle
        m_switch = re.match(r"^(.+?)\s+sent out\s+(.+?)!", line)
        if m_switch and current_turn > 0:
            trainer_p = m_switch.group(1).strip().replace("☆", "")
            mon = m_switch.group(2).split("(")[-1].replace(")", "").strip()
            is_t1 = trainer_p.lower() == trainer_1_name.lower()
            if is_t1:
                if len(t1_active) >= 2:
                    t1_active.pop(0)
                t1_active.append(mon)
                entry["t1_moves"].append(f"Switch -> {mon}")
            else:
                if len(t2_active) >= 2:
                    t2_active.pop(0)
                t2_active.append(mon)
                entry["t2_moves"].append(f"Switch -> {mon}")
            continue

        # Move execution
        m_move = re.search(r"^(?:The opposing\s+)?(.+?)\s+used\s+(.+?)!", line)
        if m_move:
            mon_nick = m_move.group(1).strip()
            mv_name = m_move.group(2).strip()
            is_opp = line.startswith("The opposing ")
            last_attacker_is_t2 = is_opp
            last_active_attacker = mon_nick
            if is_opp:
                entry["t2_moves"].append(f"{mon_nick}: {mv_name}")
            else:
                entry["t1_moves"].append(f"{mon_nick}: {mv_name}")
            continue

        # Damage observations
        m_dmg = re.search(r"\((?:The opposing\s+)?(.+?)\s+lost\s+(\d+(?:\.\d+)?)%\s+of its health!\)", line)
        if m_dmg:
            target_mon = m_dmg.group(1).strip()
            pct_lost = float(m_dmg.group(2))
            is_opp_target = "The opposing " in line
            if is_opp_target:
                # trainer_1 dealt damage to trainer_2
                entry["dmg_to_t2"] += pct_lost
            else:
                # trainer_2 dealt damage to trainer_1
                entry["dmg_to_t1"] += pct_lost
            continue

        # Faints
        m_faint = re.search(r"^(?:The opposing\s+)?(.+?)\s+fainted!", line)
        if m_faint:
            fainted_mon = m_faint.group(1).strip()
            is_opp_faint = line.startswith("The opposing ")
            team_label = "trainer_2" if is_opp_faint else "trainer_1"
            entry["faints"].append(f"{team_label}: {fainted_mon}")
            continue

        # RNG Variance Events
        if "A critical hit!" in line:
            entry["variance"].append("Critical Hit")
        elif "flinched" in line:
            m_flinch = re.search(r"^(?:The opposing\s+)?(.+?)\s+flinched", line)
            target = m_flinch.group(1) if m_flinch else "target"
            entry["variance"].append(f"Flinch on {target}")
        elif "paralyzed! It may be unable to move!" in line or "is paralyzed! It can't move!" in line:
            entry["variance"].append("Paralysis")
        elif "is frozen solid!" in line:
            entry["variance"].append("Frozen Solid")
        elif "avoided the attack!" in line or "missed!" in line:
            entry["variance"].append("Attack Missed")

    # Build final TurnTelemetryRecord list sorted by turn
    records: List[TurnTelemetryRecord] = []
    max_turns = max(turn_data.keys()) if turn_data else 0

    for t_idx in range(1, max_turns + 1):
        if t_idx not in turn_data:
            continue
        d = turn_data[t_idx]

        conds: List[str] = []
        if t1_tailwind:
            conds.append("T1_Tailwind")
        if t2_tailwind:
            conds.append("T2_Tailwind")
        if trick_room:
            conds.append("Trick_Room")
        if t1_screens:
            conds.append(f"T1_{'+'.join(sorted(t1_screens))}")
        if t2_screens:
            conds.append(f"T2_{'+'.join(sorted(t2_screens))}")

        records.append(
            TurnTelemetryRecord(
                match_id=match_id,
                timestamp=iso_now,
                turn=t_idx,
                trainer_1=trainer_1_name,
                trainer_2=trainer_2_name,
                trainer_1_active_1=d["t1_active_1"],
                trainer_1_active_2=d["t1_active_2"],
                trainer_2_active_1=d["t2_active_1"],
                trainer_2_active_2=d["t2_active_2"],
                trainer_1_moves="; ".join(d["t1_moves"]) if d["t1_moves"] else "None",
                trainer_2_moves="; ".join(d["t2_moves"]) if d["t2_moves"] else "None",
                damage_dealt_to_trainer_2=round(d["dmg_to_t2"], 1),
                damage_dealt_to_trainer_1=round(d["dmg_to_t1"], 1),
                faints_this_turn="; ".join(d["faints"]) if d["faints"] else "None",
                variance_events="; ".join(d["variance"]) if d["variance"] else "None",
                weather=d["weather"],
                terrain=d["terrain"],
                field_conditions="; ".join(conds) if conds else "Neutral",
                winner=winner_name,
                comment="",
            )
        )

    return records


CSV_COLUMNS: List[str] = [
    "match_id",
    "timestamp",
    "turn",
    "trainer_1",
    "trainer_2",
    "trainer_1_active_1",
    "trainer_1_active_2",
    "trainer_2_active_1",
    "trainer_2_active_2",
    "trainer_1_moves",
    "trainer_2_moves",
    "damage_dealt_to_trainer_2",
    "damage_dealt_to_trainer_1",
    "faints_this_turn",
    "variance_events",
    "weather",
    "terrain",
    "field_conditions",
    "winner",
    "comment",
]


def save_telemetry_to_csv(
    records: List[TurnTelemetryRecord],
    csv_path: str | Path = "data/telemetry/battles_telemetry.csv",
    append: bool = True,
) -> Path:
    """Save or append turn telemetry records to a target CSV file."""
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = path.exists() and path.stat().st_size > 0
    mode = "a" if append and file_exists else "w"

    with open(path, mode=mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists or mode == "w":
            writer.writeheader()
        for r in records:
            writer.writerow(r.to_dict())

    return path


def update_telemetry_comment(
    csv_path: str | Path,
    match_id: str,
    turn: int,
    comment: str,
) -> bool:
    """Update or inject a comment for a specific turn in an existing CSV file."""
    path = Path(csv_path)
    if not path.is_file():
        return False

    rows: List[Dict[str, Any]] = []
    updated = False

    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("match_id") == match_id and int(row.get("turn", 0)) == int(turn):
                row["comment"] = comment
                updated = True
            rows.append(row)

    if updated:
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    return updated


def batch_update_comments(
    csv_path: str | Path,
    match_id: str,
    comments_by_turn: Dict[int, str],
) -> int:
    """Batch update comments for multiple turns belonging to a match_id."""
    path = Path(csv_path)
    if not path.is_file():
        return 0

    rows: List[Dict[str, Any]] = []
    update_count = 0

    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("match_id") == match_id:
                t_num = int(row.get("turn", 0))
                if t_num in comments_by_turn:
                    row["comment"] = comments_by_turn[t_num]
                    update_count += 1
            rows.append(row)

    if update_count > 0:
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    return update_count

