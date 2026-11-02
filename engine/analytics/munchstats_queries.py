# -*- coding: utf-8 -*-
"""
Read-only query helpers for MunchStats tournament data stored in SQLite.

These functions are intentionally small and repository-like:
- they centralize access to the DB
- they keep app code from embedding raw SQL everywhere
- they allow agents and tools to ask for clean, structured results
"""

import sqlite3
from typing import Any, Dict, List, Optional

def fetch_all_tournaments(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tournament_id, tournament_name, total_players, url, crawled_at
        FROM tournaments
        ORDER BY crawled_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]

def fetch_tournament(conn: sqlite3.Connection, tournament_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT tournament_id, tournament_name, total_players, url, crawled_at
        FROM tournaments
        WHERE tournament_id = ?
        """,
        (tournament_id,),
    ).fetchone()
    return dict(row) if row else None

def fetch_stages(conn: sqlite3.Connection, tournament_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tournament_id, stage_label AS label, total_teams
        FROM stages
        WHERE tournament_id = ?
        ORDER BY stage_label
        """,
        (tournament_id,),
    ).fetchall()
    return [dict(r) for r in rows]

def fetch_standings(conn: sqlite3.Connection, tournament_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tournament_id, player_name AS name, placement, wins, losses, day_reached
        FROM standings
        WHERE tournament_id = ?
        ORDER BY placement ASC, player_name ASC
        """,
        (tournament_id,),
    ).fetchall()
    return [dict(r) for r in rows]

def fetch_team_slots(conn: sqlite3.Connection, tournament_id: str, player_name: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT slot_index, pokemon, item, ability, nature, moves_json
        FROM team_slots
        WHERE tournament_id = ? AND player_name = ?
        ORDER BY slot_index ASC
        """,
        (tournament_id, player_name),
    ).fetchall()
    return [dict(r) for r in rows]

def fetch_team_roster(conn: sqlite3.Connection, tournament_id: str, player_name: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT slot_index, pokemon, item, ability, nature, moves_json
        FROM team_slots
        WHERE tournament_id = ? AND player_name = ?
        ORDER BY slot_index ASC
        """,
        (tournament_id, player_name),
    ).fetchall()
    return [dict(r) for r in rows]

def fetch_usage_by_phase(conn: sqlite3.Connection, tournament_id: str, phase: str = "all") -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT species, count, usage_pct
        FROM usage
        WHERE tournament_id = ? AND phase = ?
        ORDER BY usage_pct DESC, count DESC, species ASC
        """,
        (tournament_id, phase),
    ).fetchall()
    return [dict(r) for r in rows]

def fetch_usage_summary(conn: sqlite3.Connection, tournament_id: str) -> Dict[str, List[Dict[str, Any]]]:
    phases = ["all", "day1", "day2", "top16", "top8"]
    result: Dict[str, List[Dict[str, Any]]] = {}
    for phase in phases:
        result[phase] = fetch_usage_by_phase(conn, tournament_id, phase)
    return result

def fetch_top_finalists(conn: sqlite3.Connection, tournament_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT player_name AS name, placement, wins, losses, day_reached
        FROM standings
        WHERE tournament_id = ?
        ORDER BY placement ASC
        LIMIT ?
        """,
        (tournament_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]

def fetch_phase_counts(conn: sqlite3.Connection, tournament_id: str) -> Dict[str, int]:
    rows = conn.execute(
        """
        SELECT phase, COUNT(*) AS count
        FROM usage
        WHERE tournament_id = ?
        GROUP BY phase
        """,
        (tournament_id,),
    ).fetchall()
    return {row["phase"]: int(row["count"]) for row in rows}

def fetch_players_by_day_reached(conn: sqlite3.Connection, tournament_id: str) -> Dict[str, int]:
    rows = conn.execute(
        """
        SELECT day_reached, COUNT(*) AS count
        FROM standings
        WHERE tournament_id = ?
        GROUP BY day_reached
        ORDER BY day_reached
        """,
        (tournament_id,),
    ).fetchall()
    return {row["day_reached"]: int(row["count"]) for row in rows}
