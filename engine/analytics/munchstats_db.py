# -*- coding: utf-8 -*-
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tournaments (
    tournament_id TEXT PRIMARY KEY,
    tournament_name TEXT NOT NULL,
    total_players INTEGER DEFAULT 0,
    url TEXT,
    crawled_at TEXT
);

CREATE TABLE IF NOT EXISTS stages (
    tournament_id TEXT NOT NULL,
    stage_label TEXT NOT NULL,
    total_teams INTEGER DEFAULT 0,
    PRIMARY KEY (tournament_id, stage_label)
);

CREATE TABLE IF NOT EXISTS standings (
    tournament_id TEXT NOT NULL,
    player_name TEXT NOT NULL,
    placement INTEGER,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    day_reached TEXT,
    PRIMARY KEY (tournament_id, player_name)
);

CREATE TABLE IF NOT EXISTS team_slots (
    tournament_id TEXT NOT NULL,
    player_name TEXT NOT NULL,
    slot_index INTEGER NOT NULL,
    pokemon TEXT,
    item TEXT,
    ability TEXT,
    nature TEXT,
    moves_json TEXT,
    PRIMARY KEY (tournament_id, player_name, slot_index)
);

CREATE TABLE IF NOT EXISTS usage (
    tournament_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    species TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    usage_pct REAL DEFAULT 0.0,
    PRIMARY KEY (tournament_id, phase, species)
);
"""

def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()

def upsert_tournament(conn: sqlite3.Connection, tournament: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO tournaments (
            tournament_id, tournament_name, total_players, url, crawled_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tournament_id) DO UPDATE SET
            tournament_name = excluded.tournament_name,
            total_players = excluded.total_players,
            url = excluded.url,
            crawled_at = excluded.crawled_at
        """,
        (
            tournament.get("tournament_id"),
            tournament.get("tournament_name") or "",
            int(tournament.get("total_players") or 0),
            tournament.get("url"),
            tournament.get("crawled_at"),
        ),
    )

def upsert_stage(conn: sqlite3.Connection, tournament_id: str, stage: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO stages (tournament_id, stage_label, total_teams)
        VALUES (?, ?, ?)
        ON CONFLICT(tournament_id, stage_label) DO UPDATE SET
            total_teams = excluded.total_teams
        """,
        (
            tournament_id,
            stage.get("label") or "",
            int(stage.get("total_teams") or 0),
        ),
    )

def upsert_standing(conn: sqlite3.Connection, tournament_id: str, standing: Dict[str, Any]) -> None:
    record = standing.get("record") or {}
    conn.execute(
        """
        INSERT INTO standings (
            tournament_id, player_name, placement, wins, losses, day_reached
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(tournament_id, player_name) DO UPDATE SET
            placement = excluded.placement,
            wins = excluded.wins,
            losses = excluded.losses,
            day_reached = excluded.day_reached
        """,
        (
            tournament_id,
            standing.get("name") or "",
            int(standing.get("placement") or 0),
            int(record.get("wins") or 0),
            int(record.get("losses") or 0),
            standing.get("day_reached"),
        ),
    )

def upsert_team_slot(conn: sqlite3.Connection, tournament_id: str, player_name: str, slot_index: int, slot: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO team_slots (
            tournament_id, player_name, slot_index, pokemon, item, ability, nature, moves_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tournament_id, player_name, slot_index) DO UPDATE SET
            pokemon = excluded.pokemon,
            item = excluded.item,
            ability = excluded.ability,
            nature = excluded.nature,
            moves_json = excluded.moves_json
        """,
        (
            tournament_id,
            player_name,
            slot_index,
            slot.get("pokemon") or slot.get("name") or "",
            slot.get("item"),
            slot.get("ability"),
            slot.get("nature"),
            json.dumps(slot.get("moves") or [], ensure_ascii=False),
        ),
    )

def upsert_usage(conn: sqlite3.Connection, tournament_id: str, phase: str, species: str, count: int, usage_pct: float) -> None:
    conn.execute(
        """
        INSERT INTO usage (tournament_id, phase, species, count, usage_pct)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tournament_id, phase, species) DO UPDATE SET
            count = excluded.count,
            usage_pct = excluded.usage_pct
        """,
        (
            tournament_id,
            phase,
            species,
            int(count or 0),
            float(usage_pct or 0.0),
        ),
    )
