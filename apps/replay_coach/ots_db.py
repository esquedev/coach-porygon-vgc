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
from typing import Any, Dict, List, Optional, Sequence

import duckdb

from engine.parser.models import ParsedPokemon
from engine.parser.showdown_parser import parse_showdown_paste
from engine.sp_validator import validate_and_calculate_sp

DEFAULT_DB_PATH = Path("data/replay_coach_ots.duckdb")
DEFAULT_TRAINER_1_PASTE = Path("data/teams/char_y_v4.txt")
DEFAULT_OPPONENT_PASTE = Path("apps/replay_coach/sample_data/matchagotme_ots.txt")
SLUG_MAP_PATH = Path("assets/slug_map.json")

_CACHED_SLUG_LOOKUP: Optional[Dict[str, Dict[str, str]]] = None


def _norm_slug(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def get_sprite_lookup() -> Dict[str, Dict[str, str]]:
    """Load and cache normalized species & item sprite URLs from `assets/slug_map.json`."""
    global _CACHED_SLUG_LOOKUP
    if _CACHED_SLUG_LOOKUP is not None:
        return _CACHED_SLUG_LOOKUP
    species_map: Dict[str, str] = {}
    items_map: Dict[str, str] = {}
    if SLUG_MAP_PATH.exists():
        try:
            raw = json.loads(SLUG_MAP_PATH.read_text(encoding="utf-8"))
            for k, rel in (raw.get("species") or {}).items():
                url = "/" + str(rel).lstrip("/")
                species_map[k] = url
                species_map[_norm_slug(k)] = url
            for k, rel in (raw.get("items") or {}).items():
                url = "/" + str(rel).lstrip("/")
                items_map[k] = url
                items_map[_norm_slug(k)] = url
        except Exception:
            pass
    _CACHED_SLUG_LOOKUP = {"species": species_map, "items": items_map}
    return _CACHED_SLUG_LOOKUP


def resolve_sprite_urls(species: Optional[str], item: Optional[str] = None) -> Dict[str, Optional[str]]:
    """Resolve local `/assets/...` sprite URLs for a Pokémon species and optional held item."""
    lut = get_sprite_lookup()
    sp_map = lut["species"]
    it_map = lut["items"]
    sp_raw = (species or "").strip()
    sp_url = (
        sp_map.get(sp_raw)
        or sp_map.get(_norm_slug(sp_raw))
        or sp_map.get(_canon_species(sp_raw))
    )
    it_raw = (item or "").strip()
    it_url = (
        (it_map.get(it_raw) or it_map.get(_norm_slug(it_raw)))
        if it_raw and it_raw.lower() != "none"
        else None
    )
    return {"sprite_url": sp_url, "item_sprite_url": it_url}


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
        """Create persistent DuckDB table for OTS rosters."""
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
        """Parse and validate a Showdown paste under Regulation M-C 66-SP or EV-less OTS rules."""
        pokemon_dict = parse_showdown_paste(paste_text)
        unique_mons: List[ParsedPokemon] = []
        seen_ids = set()
        for mon in pokemon_dict.values():
            if id(mon) not in seen_ids:
                seen_ids.add(id(mon))
                unique_mons.append(mon)
        mons_summary: List[Dict[str, Any]] = []
        warnings: List[str] = []
        all_zero_sp = len(unique_mons) > 0 and all(m.spread.total_sp == 0 for m in unique_mons)
        all_66_sp = len(unique_mons) > 0 and all(m.spread.total_sp == 66 for m in unique_mons)
        has_full_ots_metadata = len(unique_mons) > 0 and all(
            bool(m.nature) and bool(m.ability) and len(m.moves) > 0 for m in unique_mons
        )
        if all_66_sp:
            mode = "complete_66sp"
        elif all_zero_sp:
            mode = "evless_ots"
        else:
            mode = "partial_sp"

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
                # EV-less OTS pastes intentionally have 0 SPs until solved by the Bo1/Bo3 inferencer.
                if not ok_sp and msg_sp and not (mode == "evless_ots" and total_sp == 0):
                    warnings.append(f"{mon.species}: {msg_sp}")
            except Exception:
                stats_l50 = {}
            sprites = resolve_sprite_urls(mon.species, mon.item)
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
                    "sprite_url": sprites["sprite_url"],
                    "item_sprite_url": sprites["item_sprite_url"],
                }
            )
        return {
            "count": len(mons_summary),
            "pokemon": mons_summary,
            "warnings": warnings,
            "mode": mode,
            "has_full_ots_metadata": has_full_ots_metadata,
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
        result: List[Dict[str, Any]] = []
        for r in rows:
            sp_list = json.loads(r[4])
            result.append(
                {
                    "roster_id": r[0],
                    "display_name": r[1],
                    "trainer_hint": r[2],
                    "paste_text": r[3],
                    "species": sp_list,
                    "species_sprites": [
                        {"species": sp, "sprite_url": resolve_sprite_urls(sp)["sprite_url"]}
                        for sp in sp_list
                    ],
                    "updated_at": r[5],
                }
            )
        return result

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

    def delete_roster(self, roster_id: str) -> bool:
        """Delete a stored OTS roster by ID."""
        clean_id = (roster_id or "").strip()
        if not clean_id or self.get_roster(clean_id) is None:
            return False
        self.conn.execute("DELETE FROM ots_rosters WHERE roster_id = ?;", [clean_id])
        return True
