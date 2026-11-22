# -*- coding: utf-8 -*-
"""Persistent DuckDB OTS + EVs/SPs Roster Database (Zero-AI Ground Truth).

Stores full Regulation M-C Open Team Sheets with exact 66-SP (or cartridge EV)
allocations for both `trainer_1` and `trainer_2` so the GPU Tensor Core Engine
solves exact Nash Equilibria without Bayesian guesswork or LLM calls.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import duckdb

from engine.parser.models import ParsedPokemon, StatSpread
from engine.parser.showdown_parser import parse_showdown_paste
from engine.sp_validator import validate_and_calculate_sp

DEFAULT_DB_PATH = Path("data/replay_coach_ots.duckdb")
DEFAULT_TRAINER_1_PASTE = Path("data/teams/char_y_v4.txt")
DEFAULT_OPPONENT_PASTE = Path("apps/replay_coach/sample_data/matchagotme_ots.txt")


def _canon_species(name: str) -> str:
    """Normalize species name to lowercase alphanumeric root for robust roster matching."""
    base = (name or "").split(",")[0].strip().lower()
    if "-mega" in base:
        base = base.split("-mega")[0]
    return "".join(ch for ch in base if ch.isalnum())


class OTSRosterDatabase:
    """DuckDB-backed persistent store for exact OTS + 66-SP team sheets and analysis cache."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()
        self._seed_defaults()

    def _init_schema(self) -> None:
        """Create persistent DuckDB tables for OTS rosters and turn analysis cache."""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ots_rosters (
                roster_id VARCHAR PRIMARY KEY,
                display_name VARCHAR NOT NULL,
                trainer_hint VARCHAR NOT NULL,
                paste_text VARCHAR NOT NULL,
                species_json VARCHAR NOT NULL,
                updated_at VARCHAR NOT NULL
            );
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_cache (
                cache_key VARCHAR PRIMARY KEY,
                replay_id VARCHAR NOT NULL,
                turn_number INTEGER NOT NULL,
                payload_json VARCHAR NOT NULL,
                created_at VARCHAR NOT NULL
            );
            """
        )

    def _seed_defaults(self) -> None:
        """Pre-seed `treces_gc` (`char_y_v4.txt`) and `MatchaGotMe` OTS if missing."""
        if DEFAULT_TRAINER_1_PASTE.exists() and self.get_roster("treces_gc_char_y_v4") is None:
            self.save_roster(
                roster_id="treces_gc_char_y_v4",
                display_name="treces_gc — Charizard-Y Dual Weather v4",
                trainer_hint="treces_gc",
                paste_text=DEFAULT_TRAINER_1_PASTE.read_text(encoding="utf-8"),
            )
        if DEFAULT_OPPONENT_PASTE.exists() and self.get_roster("matchagotme_camerupt_tr") is None:
            self.save_roster(
                roster_id="matchagotme_camerupt_tr",
                display_name="MatchaGotMe — Camerupt / Raichu-Y Trick Room",
                trainer_hint="MatchaGotMe",
                paste_text=DEFAULT_OPPONENT_PASTE.read_text(encoding="utf-8"),
            )

    def validate_paste(self, paste_text: str) -> Dict[str, Any]:
        """Parse and validate a Showdown paste under Regulation M-C 66-SP rules."""
        pokemon_dict = parse_showdown_paste(paste_text)
        unique_mons: List[ParsedPokemon] = []
        seen_ids = set()
        for mon in pokemon_dict.values():
            if id(mon) not in seen_ids:
                seen_ids.add(id(mon))
                unique_mons.append(mon)
        mons_summary: List[Dict[str, Any]] = []
        warnings: List[str] = []
        for mon in unique_mons:
            sp_dict = mon.spread.to_dict()
            total_sp = mon.spread.total_sp
            if total_sp > 66:
                warnings.append(f"{mon.species}: total SP {total_sp} > 66")
            for stat_k, stat_v in sp_dict.items():
                if stat_v > 32:
                    warnings.append(f"{mon.species}: {stat_k} SP {stat_v} > 32")
            try:
                ok_sp, msg_sp, stats_l50 = validate_and_calculate_sp(
                    mon.species,
                    sp_dict,
                    mon.nature or "Serious",
                )
                if not ok_sp and msg_sp:
                    warnings.append(f"{mon.species}: {msg_sp}")
            except Exception:
                stats_l50 = {}
            mons_summary.append(
                {
                    "species": mon.species,
                    "item": mon.item,
                    "ability": mon.ability,
                    "nature": mon.nature,
                    "spread": sp_dict,
                    "total_sp": total_sp,
                    "moves": list(mon.moves),
                    "stats": stats_l50,
                }
            )
        return {
            "count": len(mons_summary),
            "pokemon": mons_summary,
            "warnings": warnings,
            "valid": len(mons_summary) > 0 and len(warnings) == 0,
        }

    def save_roster(
        self,
        roster_id: str,
        display_name: str,
        trainer_hint: str,
        paste_text: str,
    ) -> Dict[str, Any]:
        """Insert or update an OTS + EVs/SPs roster in DuckDB."""
        pokemon_dict = parse_showdown_paste(paste_text)
        species_list: List[str] = []
        seen_ids = set()
        for mon in pokemon_dict.values():
            if id(mon) not in seen_ids:
                seen_ids.add(id(mon))
                species_list.append(mon.species)
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT OR REPLACE INTO ots_rosters
            (roster_id, display_name, trainer_hint, paste_text, species_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            [
                roster_id.strip(),
                display_name.strip() or roster_id.strip(),
                trainer_hint.strip(),
                paste_text.strip(),
                json.dumps(species_list),
                now,
            ],
        )
        # Invalidate cached turn evaluations because spreads may have changed
        self.conn.execute("DELETE FROM analysis_cache;")
        return self.get_roster(roster_id.strip()) or {}

    def get_roster(self, roster_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single stored roster by ID."""
        row = self.conn.execute(
            """
            SELECT roster_id, display_name, trainer_hint, paste_text, species_json, updated_at
            FROM ots_rosters WHERE roster_id = ?;
            """,
            [roster_id],
        ).fetchone()
        if not row:
            return None
        return {
            "roster_id": row[0],
            "display_name": row[1],
            "trainer_hint": row[2],
            "paste_text": row[3],
            "species": json.loads(row[4]),
            "updated_at": row[5],
        }

    def list_rosters(self) -> List[Dict[str, Any]]:
        """List all stored OTS rosters ordered by most recently updated."""
        rows = self.conn.execute(
            """
            SELECT roster_id, display_name, trainer_hint, paste_text, species_json, updated_at
            FROM ots_rosters ORDER BY updated_at DESC;
            """
        ).fetchall()
        return [
            {
                "roster_id": r[0],
                "display_name": r[1],
                "trainer_hint": r[2],
                "paste_text": r[3],
                "species": json.loads(r[4]),
                "updated_at": r[5],
            }
            for r in rows
        ]

    def match_best_roster(
        self,
        trainer_name: str,
        preview_species: Sequence[str],
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching OTS roster in DuckDB by species overlap & trainer name."""
        target_set = {_canon_species(s) for s in preview_species if s}
        best_score = -1.0
        best_roster: Optional[Dict[str, Any]] = None
        for r in self.list_rosters():
            r_set = {_canon_species(s) for s in r["species"]}
            overlap = len(target_set & r_set)
            name_bonus = 1.5 if r["trainer_hint"].lower() == trainer_name.strip().lower() else 0.0
            score = float(overlap) + name_bonus
            if overlap >= max(1, min(4, len(target_set))) and score > best_score:
                best_score = score
                best_roster = r
        return best_roster

    def get_parsed_sets_by_species(self, paste_text: str) -> Dict[str, ParsedPokemon]:
        """Parse a paste into a canonical-species -> ParsedPokemon lookup dictionary."""
        pokemon_dict = parse_showdown_paste(paste_text)
        out: Dict[str, ParsedPokemon] = {}
        for mon in pokemon_dict.values():
            out[_canon_species(mon.species)] = mon
        return out

    def get_cached_turn(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a previously computed GPU turn audit payload from DuckDB."""
        row = self.conn.execute(
            "SELECT payload_json FROM analysis_cache WHERE cache_key = ?;",
            [cache_key],
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put_cached_turn(
        self,
        cache_key: str,
        replay_id: str,
        turn_number: int,
        payload: Dict[str, Any],
    ) -> None:
        """Persist a GPU turn audit payload in DuckDB."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO analysis_cache
            (cache_key, replay_id, turn_number, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            [
                cache_key,
                replay_id,
                int(turn_number),
                json.dumps(payload),
                datetime.now(timezone.utc).isoformat(),
            ],
        )

    def clear_cache(self) -> None:
        """Clear cached turn analyses."""
        self.conn.execute("DELETE FROM analysis_cache;")
