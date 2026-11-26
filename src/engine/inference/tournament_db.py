# -*- coding: utf-8 -*-
"""Regulation M-C Tournament Telemetry & Showdown Mechanics Repository (In-Memory DuckDB).

Powered directly by `VGCDataRegistry` (`src/engine/db_registry.py`), executing
vectorized SQL queries against the in-memory DuckDB views (`pokedex`, `moves`,
`items`, `learnsets`, `tournament_standings`, and the materialized
`tournament_team_slots` table).

Handles canonical resolution between base species, regional formes, and Mega Evolution
formes (e.g., 'Charizard' + 'Charizardite Y' -> 'Charizard-Mega-Y', 'Starmie' -> 'Starmie-Mega'),
and computes placement-weighted conditional usage distributions via DuckDB SQL.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Dict, List, Optional, Set

from engine.db_registry import VGCDataRegistry, get_registry


def _normalize_text(text: str) -> str:
    """Normalize curly apostrophes and excess whitespace from crawled strings."""
    return text.replace("\u2019", "'").replace("\u2018", "'").strip()


def _to_id(text: str) -> str:
    """Convert a Showdown display name to its lowercase alphanumeric ID."""
    return re.sub(r"[^a-z0-9]", "", _normalize_text(text).lower())


class TournamentUsageRepository:
    """In-memory DuckDB repository querying `VGCDataRegistry` views and tables."""

    def __init__(self, registry: Optional[VGCDataRegistry] = None) -> None:
        self.registry: VGCDataRegistry = registry or get_registry()

        self.pokedex: Dict[str, Dict[str, Any]] = {}
        self._id_to_species_name: Dict[str, str] = {}
        self.mega_stone_to_species: Dict[str, str] = {}
        self.base_to_mega_species: Dict[str, List[str]] = defaultdict(list)

        self.moves: Dict[str, Dict[str, Any]] = {}
        self._id_to_move_name: Dict[str, str] = {}
        self.items: Dict[str, Dict[str, Any]] = {}
        self.learnsets: Dict[str, Set[str]] = {}
        self.available_tournament_species: Set[str] = set()
        self.total_tournament_teams: int = 0

        self._load_indices_from_duckdb()

    # ------------------------------------------------------------------
    # In-Memory DuckDB Index Initialization
    # ------------------------------------------------------------------

    def _load_indices_from_duckdb(self) -> None:
        """Query in-memory DuckDB views to build fast canonical lookup indices."""
        # 1. Pokedex view
        dex_rows = self.registry.query("SELECT * FROM pokedex;")
        for row in dex_rows:
            name = _normalize_text(str(row.get("name") or ""))
            if not name:
                continue
            entry = dict(row)
            if not isinstance(entry.get("baseStats"), dict):
                entry["baseStats"] = {
                    "hp": int(row.get("hp") or 80),
                    "atk": int(row.get("atk") or 80),
                    "def": int(row.get("def") or 80),
                    "spa": int(row.get("spa") or 80),
                    "spd": int(row.get("spd") or 80),
                    "spe": int(row.get("spe") or 80),
                }
            self.pokedex[name] = entry
            self._id_to_species_name[_to_id(name)] = name
            if row.get("id"):
                self._id_to_species_name[_to_id(str(row["id"]))] = name

            req_item = row.get("requiredItem")
            if req_item:
                clean_item = _normalize_text(str(req_item))
                self.mega_stone_to_species[clean_item] = name
                self.mega_stone_to_species[_to_id(clean_item)] = name

            base_sp = row.get("baseSpecies")
            forme_str = str(row.get("forme") or "")
            if base_sp and ("Mega" in name or forme_str.startswith("Mega")):
                clean_base = _normalize_text(str(base_sp))
                if name not in self.base_to_mega_species[clean_base]:
                    self.base_to_mega_species[clean_base].append(name)

        # 2. Moves view
        move_rows = self.registry.query("SELECT * FROM moves;")
        for row in move_rows:
            name = _normalize_text(str(row.get("name") or ""))
            if not name:
                continue
            self.moves[name] = dict(row)
            self._id_to_move_name[_to_id(name)] = name
            if row.get("id"):
                self._id_to_move_name[_to_id(str(row["id"]))] = name

        # 3. Items view
        item_rows = self.registry.query("SELECT * FROM items;")
        for row in item_rows:
            name = _normalize_text(str(row.get("name") or ""))
            if name:
                self.items[name] = dict(row)

        # 4. Learnsets view
        learnset_rows = self.registry.query("SELECT id, learnset FROM learnsets;")
        for row in learnset_rows:
            sp_id = _to_id(str(row.get("id") or ""))
            raw_learnset = row.get("learnset")
            if sp_id and isinstance(raw_learnset, dict):
                canonical_moves: Set[str] = set()
                for move_id, val in raw_learnset.items():
                    if val is not None:
                        m_name = self._id_to_move_name.get(_to_id(str(move_id)))
                        if m_name:
                            canonical_moves.add(m_name)
                self.learnsets[sp_id] = canonical_moves

        # 5. Tournament counts & distinct species from DuckDB
        cnt_rows = self.registry.query("SELECT COUNT(*) AS n FROM tournament_standings;")
        if cnt_rows:
            self.total_tournament_teams = int(cnt_rows[0]["n"])

        sp_rows = self.registry.query("SELECT DISTINCT species FROM tournament_team_slots;")
        self.available_tournament_species = {str(r["species"]) for r in sp_rows if r.get("species")}

    # ------------------------------------------------------------------
    # Canonical Lookup Helpers
    # ------------------------------------------------------------------

    def canonical_move_name(self, raw_move: str) -> str:
        """Resolve a move string to its canonical Showdown move name."""
        clean = _normalize_text(raw_move)
        if clean in self.moves:
            return clean
        return self._id_to_move_name.get(_to_id(clean), clean)

    def resolve_species_name(
        self,
        species: str,
        item: Optional[str] = None,
        is_mega: bool = False,
    ) -> str:
        """Resolve a raw or chat-log species name to its canonical Pokédex species name."""
        clean_sp = _normalize_text(species)

        if item:
            clean_item = _normalize_text(item)
            mega_sp = self.mega_stone_to_species.get(clean_item) or self.mega_stone_to_species.get(
                _to_id(clean_item)
            )
            if mega_sp and is_mega:
                return mega_sp

        if clean_sp.startswith("Mega "):
            stripped = clean_sp[len("Mega ") :].strip()
            if item:
                mega_sp = self.mega_stone_to_species.get(_normalize_text(item))
                if mega_sp:
                    return mega_sp
            candidate = f"{stripped}-Mega"
            if candidate in self.pokedex:
                return candidate
            megas = self.base_to_mega_species.get(stripped, [])
            if megas:
                return megas[0]

        if clean_sp in self.pokedex:
            if is_mega and "-Mega" not in clean_sp:
                base_root = self.pokedex[clean_sp].get("baseSpecies") or clean_sp
                megas = self.base_to_mega_species.get(str(base_root), [])
                if len(megas) == 1:
                    return megas[0]
            return clean_sp

        by_id = self._id_to_species_name.get(_to_id(clean_sp))
        if by_id:
            return by_id

        if clean_sp.endswith("-M"):
            stripped_m = clean_sp[:-2]
            if stripped_m in self.pokedex:
                return stripped_m
            by_id_m = self._id_to_species_name.get(_to_id(stripped_m))
            if by_id_m:
                return by_id_m

        return clean_sp

    def get_pokedex_entry(
        self,
        species: str,
        item: Optional[str] = None,
        is_mega: bool = False,
    ) -> Dict[str, Any]:
        """Return the Pokédex dictionary for the resolved species."""
        resolved = self.resolve_species_name(species, item=item, is_mega=is_mega)
        if resolved in self.pokedex:
            return self.pokedex[resolved]
        by_id = self._id_to_species_name.get(_to_id(resolved))
        if by_id and by_id in self.pokedex:
            return self.pokedex[by_id]
        return {
            "name": resolved,
            "types": ["Normal"],
            "baseStats": {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80},
            "abilities": {"0": "Illuminate"},
        }

    def get_base_stats(
        self,
        species: str,
        item: Optional[str] = None,
        is_mega: bool = False,
    ) -> Dict[str, int]:
        """Return Level 50 base stats dictionary {'hp', 'atk', 'def', 'spa', 'spd', 'spe'}."""
        entry = self.get_pokedex_entry(species, item=item, is_mega=is_mega)
        stats = entry.get("baseStats", {})
        return {
            "hp": int(stats.get("hp", 80)),
            "atk": int(stats.get("atk", 80)),
            "def": int(stats.get("def", 80)),
            "spa": int(stats.get("spa", 80)),
            "spd": int(stats.get("spd", 80)),
            "spe": int(stats.get("spe", 80)),
        }

    def get_move_entry(self, move_name: str) -> Dict[str, Any]:
        """Return Showdown move metadata dictionary."""
        canon = self.canonical_move_name(move_name)
        return self.moves.get(
            canon,
            {
                "name": canon,
                "basePower": 0,
                "accuracy": 100,
                "category": "Status",
                "type": "Normal",
                "priority": 0,
            },
        )


_SHARED_REPOSITORY: Optional[TournamentUsageRepository] = None


def get_tournament_repository() -> TournamentUsageRepository:
    """Return a singleton TournamentUsageRepository instance backed by VGCDataRegistry."""
    global _SHARED_REPOSITORY
    if _SHARED_REPOSITORY is None:
        _SHARED_REPOSITORY = TournamentUsageRepository()
    return _SHARED_REPOSITORY
