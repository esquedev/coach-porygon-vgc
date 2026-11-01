# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unified Relational & JSONL Persistence Layer (engine/db.py)

Provides an in-memory SQLite relational engine (:memory:) synchronized with
atomic, Git-friendly JSON Lines (.jsonl) storage on disk. Enables sub-millisecond
SQL analytical queries across matches, Game-Theoretic Nash audits, playstyle
diagnostics, and MunchStats metagame priors.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple, Union


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUDITS_JSONL = REPO_ROOT / "data" / "tactical_audits.jsonl"


class UnifiedCoachDatabase:
    """
    In-memory SQLite database engine backed by atomic JSON Lines (.jsonl) persistence.

    Unifies querying across four canonical tables:
    - matches: High-level replay metadata and outcome tracking.
    - tactical_audits: Turning points, 5x5 Nash payoff matrices, mixed strategies, and equity loss.
    - diagnostics: Standardized mistake_taxonomy.md error codes and cognitive trap drivers.
    - munchstats_meta: Species usage frequencies, items, and abilities for Bayesian inference.
    """

    def __init__(self, auto_ingest_path: Optional[Union[str, Path]] = None) -> None:
        """
        Initialize the in-memory SQLite relational schema and optional JSONL ingestion.

        Args:
            auto_ingest_path: Optional path to a .jsonl file to ingest immediately upon startup.
        """
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._initialize_schema()

        if auto_ingest_path is not None:
            path_obj = Path(auto_ingest_path)
            if path_obj.exists():
                self.ingest_jsonl(path_obj)

    def _initialize_schema(self) -> None:
        """Create canonical relational tables and performance indexes in RAM."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS matches (
                    match_id TEXT PRIMARY KEY,
                    p1_name TEXT NOT NULL,
                    p2_name TEXT NOT NULL,
                    winner TEXT,
                    turns INTEGER DEFAULT 0,
                    format TEXT DEFAULT 'VGC 2026 Reg M-C',
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS tactical_audits (
                    audit_id TEXT PRIMARY KEY,
                    match_id TEXT NOT NULL,
                    turn INTEGER NOT NULL,
                    impact_score REAL NOT NULL,
                    p1_active TEXT NOT NULL,
                    p2_active TEXT NOT NULL,
                    observed_action TEXT NOT NULL,
                    optimal_nash_action TEXT NOT NULL,
                    game_value REAL NOT NULL,
                    equity_loss REAL NOT NULL,
                    mistake_code TEXT NOT NULL,
                    cognitive_driver TEXT NOT NULL,
                    payoff_matrix_json TEXT NOT NULL,
                    p1_nash_probs_json TEXT NOT NULL,
                    p2_nash_probs_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (match_id) REFERENCES matches(match_id)
                );

                CREATE TABLE IF NOT EXISTS diagnostics (
                    diag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT NOT NULL,
                    turn INTEGER NOT NULL,
                    mistake_code TEXT NOT NULL,
                    cognitive_driver TEXT NOT NULL,
                    equity_loss REAL NOT NULL,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS munchstats_meta (
                    species TEXT PRIMARY KEY,
                    usage_rate REAL NOT NULL,
                    top_item TEXT,
                    top_ability TEXT,
                    sample_size INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_audits_match_id ON tactical_audits(match_id);
                CREATE INDEX IF NOT EXISTS idx_audits_mistake_code ON tactical_audits(mistake_code);
                CREATE INDEX IF NOT EXISTS idx_audits_turn ON tactical_audits(turn);
                CREATE INDEX IF NOT EXISTS idx_diag_match_id ON diagnostics(match_id);
                CREATE INDEX IF NOT EXISTS idx_diag_mistake_code ON diagnostics(mistake_code);
                CREATE INDEX IF NOT EXISTS idx_meta_species ON munchstats_meta(species);
                """
            )
            self.conn.commit()

    def _insert_record_in_memory(self, record: Dict[str, Any]) -> str:
        """
        Index a single structured audit dictionary into matches, tactical_audits, and diagnostics.

        Args:
            record: Dictionary containing tactical audit telemetry fields.

        Returns:
            The canonical audit_id indexed in SQLite.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        match_id = str(record.get("match_id") or f"M-{int(datetime.now().timestamp())}")
        audit_id = str(record.get("audit_id") or f"AUD-{match_id}-T{record.get('turn', 1)}")
        p1_name = str(record.get("p1_name", "aws_secret"))
        p2_name = str(record.get("p2_name", "Opponent"))
        winner = str(record.get("winner", p1_name))
        turns = int(record.get("total_turns", record.get("turns", 1)))
        turn_num = int(record.get("turn", 1))
        impact_score = float(record.get("impact_score", 0.0))

        p1_active = record.get("p1_active", [])
        if isinstance(p1_active, list):
            p1_active_str = " / ".join(str(x) for x in p1_active)
        else:
            p1_active_str = str(p1_active)

        p2_active = record.get("p2_active", [])
        if isinstance(p2_active, list):
            p2_active_str = " / ".join(str(x) for x in p2_active)
        else:
            p2_active_str = str(p2_active)

        observed_action = str(record.get("observed_action", "Unknown"))
        optimal_nash_action = str(record.get("optimal_nash_action", "Unknown"))
        game_value = float(record.get("game_value", 0.0))
        equity_loss = float(record.get("equity_loss", 0.0))
        mistake_code = str(record.get("mistake_code", "POS-01"))
        cognitive_driver = str(record.get("cognitive_driver", "Autopilot"))

        payoff_matrix = record.get("payoff_matrix", [])
        payoff_json = (
            payoff_matrix if isinstance(payoff_matrix, str) else json.dumps(payoff_matrix)
        )

        p1_probs = record.get("p1_nash_probs", [])
        p1_probs_json = p1_probs if isinstance(p1_probs, str) else json.dumps(p1_probs)

        p2_probs = record.get("p2_nash_probs", [])
        p2_probs_json = p2_probs if isinstance(p2_probs, str) else json.dumps(p2_probs)

        timestamp = str(record.get("timestamp", now_iso))

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO matches (match_id, p1_name, p2_name, winner, turns, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (match_id, p1_name, p2_name, winner, turns, timestamp),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO tactical_audits (
                    audit_id, match_id, turn, impact_score, p1_active, p2_active,
                    observed_action, optimal_nash_action, game_value, equity_loss,
                    mistake_code, cognitive_driver, payoff_matrix_json,
                    p1_nash_probs_json, p2_nash_probs_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    match_id,
                    turn_num,
                    impact_score,
                    p1_active_str,
                    p2_active_str,
                    observed_action,
                    optimal_nash_action,
                    game_value,
                    equity_loss,
                    mistake_code,
                    cognitive_driver,
                    payoff_json,
                    p1_probs_json,
                    p2_probs_json,
                    timestamp,
                ),
            )
            cursor.execute(
                """
                INSERT INTO diagnostics (
                    match_id, turn, mistake_code, cognitive_driver, equity_loss, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    turn_num,
                    mistake_code,
                    cognitive_driver,
                    equity_loss,
                    str(record.get("notes", f"Observed: {observed_action} vs Optimal: {optimal_nash_action}")),
                ),
            )
            self.conn.commit()

        return audit_id

    def ingest_jsonl(self, path: Union[str, Path]) -> int:
        """
        Load a batch of JSON Lines (.jsonl) records into the in-memory SQLite tables.

        Args:
            path: Filesystem path to the .jsonl file.

        Returns:
            Number of valid JSON records ingested.

        Raises:
            FileNotFoundError: If the specified path does not exist.
            ValueError: If a non-empty line contains malformed JSON.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"JSONL file not found: {file_path}")

        count = 0
        with open(file_path, "r", encoding="utf-8") as fh:
            for line_num, raw_line in enumerate(fh, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON at {file_path}:{line_num}: {exc}"
                    ) from exc

                if not isinstance(record, dict):
                    raise ValueError(
                        f"Expected JSON object at {file_path}:{line_num}, got {type(record).__name__}"
                    )
                self._insert_record_in_memory(record)
                count += 1

        return count

    def append_audit_record(
        self,
        record: Dict[str, Any],
        target_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """
        Atomically append a tactical audit record to disk (.jsonl) and index it in SQLite RAM.

        Args:
            record: Structured tactical audit dictionary.
            target_path: Optional override path for the .jsonl file (defaults to data/tactical_audits.jsonl).

        Returns:
            The indexed audit_id string.

        Raises:
            ValueError: If record is not a valid dictionary.
        """
        if not isinstance(record, dict) or not record:
            raise ValueError("Audit record must be a non-empty dictionary.")

        out_path = Path(target_path) if target_path is not None else DEFAULT_AUDITS_JSONL
        out_path.parent.mkdir(parents=True, exist_ok=True)

        audit_id = self._insert_record_in_memory(record)
        serialized = dict(record)
        serialized["audit_id"] = audit_id

        json_line = json.dumps(serialized, ensure_ascii=False) + "\n"
        with self._lock:
            with open(out_path, "a", encoding="utf-8") as fh:
                fh.write(json_line)

        return audit_id

    def upsert_munchstats_meta(
        self,
        species: str,
        usage_rate: float,
        top_item: str = "None",
        top_ability: str = "Unknown",
        sample_size: int = 100,
    ) -> None:
        """
        Insert or update a species metagame entry in munchstats_meta.

        Args:
            species: Canonical Regulation M-C Pokemon species name.
            usage_rate: Usage percentage in [0.0, 1.0].
            top_item: Most common legal item.
            top_ability: Most common ability.
            sample_size: Number of tournament teams sampled.
        """
        if not species or not species.strip():
            raise ValueError("Species name cannot be empty.")
        if not (0.0 <= usage_rate <= 1.0):
            raise ValueError(f"usage_rate must be between 0.0 and 1.0, got {usage_rate}")

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO munchstats_meta (
                    species, usage_rate, top_item, top_ability, sample_size
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (species.strip(), float(usage_rate), top_item, top_ability, int(sample_size)),
            )
            self.conn.commit()

    def query(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """
        Execute a read-only SQL SELECT query against the in-memory relational engine.

        Args:
            sql: SQL SELECT statement.
            params: Positional query parameters to prevent SQL injection.

        Returns:
            List of rows represented as standard Python dictionaries.

        Raises:
            ValueError: If the SQL statement is empty or attempts destructive DDL/DML.
        """
        if not sql or not sql.strip():
            raise ValueError("SQL query cannot be empty.")

        normalized = sql.strip().upper()
        if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
            raise ValueError("UnifiedCoachDatabase.query() only permits SELECT or WITH queries.")

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def close(self) -> None:
        """Close the in-memory SQLite connection cleanly."""
        with self._lock:
            self.conn.close()
