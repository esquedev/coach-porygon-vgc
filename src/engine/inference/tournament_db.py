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
from dataclasses import dataclass, field
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from engine.db_registry import VGCDataRegistry, get_registry


def _normalize_text(text: str) -> str:
    """Normalize curly apostrophes and excess whitespace from crawled strings."""
    return text.replace("\u2019", "'").replace("\u2018", "'").strip()


def _to_id(text: str) -> str:
    """Convert a Showdown display name to its lowercase alphanumeric ID."""
    return re.sub(r"[^a-z0-9]", "", _normalize_text(text).lower())


@dataclass
class TournamentBuildRecord:
    """Single Pokémon set recorded from a regional tournament team."""

    tournament_id: str
    player_name: str
    placement: int
    day_reached: str
    species: str
    item: str
    ability: str
    nature: str
    moves: Tuple[str, ...]
    teammates: Tuple[str, ...] = ()
    weight: float = 1.0


@dataclass
class SpeciesUsageProfile:
    """Aggregated tournament usage distribution for a canonical species."""

    species: str
    sample_count: int = 0
    total_weight: float = 0.0
    items: Dict[str, float] = field(default_factory=dict)
    abilities: Dict[str, float] = field(default_factory=dict)
    natures: Dict[str, float] = field(default_factory=dict)
    moves: Dict[str, float] = field(default_factory=dict)
    top_builds: List[TournamentBuildRecord] = field(default_factory=list)


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

        if clean_sp.endswith("-M") and clean_sp[:-2] in self.pokedex:
            return clean_sp[:-2]

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

    def _resolve_candidate_species_keys(
        self,
        species: str,
        allow_mega: bool = True,
        require_mega: bool = False,
        forced_mega_stone: Optional[str] = None,
    ) -> List[str]:
        """Determine the list of tournament species keys to query in DuckDB."""
        canon = self.resolve_species_name(species, item=forced_mega_stone, is_mega=require_mega)
        entry = self.pokedex.get(canon, {})
        base_root = str(entry.get("baseSpecies") or canon.split("-Mega")[0])

        candidate_keys: List[str] = []
        if require_mega:
            if forced_mega_stone and forced_mega_stone in self.mega_stone_to_species:
                candidate_keys.append(self.mega_stone_to_species[forced_mega_stone])
            elif "-Mega" in canon:
                candidate_keys.append(canon)
            else:
                candidate_keys.extend(self.base_to_mega_species.get(base_root, []))
        else:
            if canon in self.available_tournament_species:
                candidate_keys.append(canon)
            if base_root not in candidate_keys and base_root in self.available_tournament_species:
                candidate_keys.append(base_root)
            if base_root == "Floette" and "Floette-Eternal" in self.available_tournament_species:
                if "Floette-Eternal" not in candidate_keys:
                    candidate_keys.append("Floette-Eternal")
            if allow_mega:
                for m_sp in self.base_to_mega_species.get(base_root, []):
                    if m_sp not in candidate_keys and m_sp in self.available_tournament_species:
                        candidate_keys.append(m_sp)

        if not candidate_keys and not require_mega:
            for m_sp in self.base_to_mega_species.get(base_root, []):
                if m_sp in self.available_tournament_species:
                    candidate_keys.append(m_sp)

        return candidate_keys

    # ------------------------------------------------------------------
    # Vectorized In-Memory DuckDB Usage Queries
    # ------------------------------------------------------------------

    def query_species_profile(
        self,
        species: str,
        revealed_moves: Iterable[str] = (),
        revealed_item: Optional[str] = None,
        revealed_ability: Optional[str] = None,
        allow_mega: bool = True,
        require_mega: bool = False,
    ) -> SpeciesUsageProfile:
        """Compute conditional tournament usage profile using vectorized in-memory DuckDB SQL."""
        rev_moves = sorted({self.canonical_move_name(m) for m in revealed_moves if m})
        rev_item = _normalize_text(revealed_item) if revealed_item else None
        rev_ability = _normalize_text(revealed_ability) if revealed_ability else None

        candidate_keys = self._resolve_candidate_species_keys(
            species,
            allow_mega=allow_mega,
            require_mega=require_mega,
            forced_mega_stone=rev_item if (rev_item and rev_item in self.mega_stone_to_species) else None,
        )
        canon_sp = self.resolve_species_name(species, item=rev_item, is_mega=require_mega)
        if not candidate_keys:
            return SpeciesUsageProfile(species=canon_sp, sample_count=0)

        num_rev = len(rev_moves)
        mega_stones_list = list(self.mega_stone_to_species.keys()) if not allow_mega else []

        scored_sql = """
            CREATE OR REPLACE TEMP TABLE _tmp_scored AS
            SELECT
                tournament_id,
                player_name,
                placement,
                day_reached,
                species,
                item,
                ability,
                nature,
                moves,
                weight
                * CASE
                    WHEN ? = 0 THEN 1.0
                    WHEN len(list_intersect(moves, ?::VARCHAR[])) = ? THEN 4.0
                    WHEN len(list_intersect(moves, ?::VARCHAR[])) > 0
                        THEN 1.5 + len(list_intersect(moves, ?::VARCHAR[]))
                    ELSE 0.25
                END
                * CASE
                    WHEN ?::VARCHAR IS NULL THEN 1.0
                    WHEN LOWER(item) = LOWER(?::VARCHAR) THEN 3.0
                    ELSE 1.0
                END
                * CASE
                    WHEN ?::VARCHAR IS NULL THEN 1.0
                    WHEN LOWER(ability) = LOWER(?::VARCHAR) THEN 2.0
                    ELSE 1.0
                END AS eff_weight
            FROM tournament_team_slots
            WHERE species IN (SELECT UNNEST(?::VARCHAR[]));
        """
        base_params: Tuple[Any, ...] = (
            num_rev,
            rev_moves,
            num_rev,
            rev_moves,
            rev_moves,
            rev_item,
            rev_item,
            rev_ability,
            rev_ability,
            candidate_keys,
        )
        self.registry.con.execute(scored_sql, base_params)

        # 1. Sample count & total effective weight
        summary_rows = self.registry.query(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(eff_weight), 0.0) AS tot_w FROM _tmp_scored;"
        )
        sample_count = int(summary_rows[0]["cnt"]) if summary_rows else 0
        total_w = float(summary_rows[0]["tot_w"]) if summary_rows else 0.0
        profile = SpeciesUsageProfile(
            species=canon_sp,
            sample_count=sample_count,
            total_weight=total_w,
        )
        if sample_count == 0 or total_w <= 0.0:
            return profile

        # 2. Item frequencies (filtering out Mega Stones if allow_mega is False)
        item_rows = self.registry.query(
            """
            SELECT item, SUM(eff_weight) AS w
            FROM _tmp_scored
            WHERE item != ''
              AND NOT list_contains(?::VARCHAR[], item)
            GROUP BY item
            ORDER BY w DESC;
            """,
            (mega_stones_list,),
        )
        item_tot = sum(float(r["w"]) for r in item_rows) or 1.0
        profile.items = {str(r["item"]): float(r["w"]) / item_tot for r in item_rows}

        # 3. Ability frequencies
        ab_rows = self.registry.query(
            """
            SELECT ability, SUM(eff_weight) AS w
            FROM _tmp_scored
            WHERE ability != ''
            GROUP BY ability
            ORDER BY w DESC;
            """
        )
        ab_tot = sum(float(r["w"]) for r in ab_rows) or 1.0
        profile.abilities = {str(r["ability"]): float(r["w"]) / ab_tot for r in ab_rows}

        # 4. Nature frequencies
        nat_rows = self.registry.query(
            """
            SELECT nature, SUM(eff_weight) AS w
            FROM _tmp_scored
            WHERE nature != ''
            GROUP BY nature
            ORDER BY w DESC;
            """
        )
        nat_tot = sum(float(r["w"]) for r in nat_rows) or 1.0
        profile.natures = {str(r["nature"]): float(r["w"]) / nat_tot for r in nat_rows}

        # 5. Move frequencies (UNNEST in DuckDB)
        move_rows = self.registry.query(
            """
            SELECT mv, SUM(eff_weight) AS w
            FROM (
                SELECT UNNEST(moves) AS mv, eff_weight
                FROM _tmp_scored
            )
            WHERE mv IS NOT NULL AND mv != ''
            GROUP BY mv
            ORDER BY w DESC;
            """
        )
        profile.moves = {
            self.canonical_move_name(str(r["mv"])): float(r["w"]) / total_w for r in move_rows
        }

        # 6. Top 10 full builds
        top_rows = self.registry.query(
            """
            SELECT
                tournament_id,
                player_name,
                placement,
                day_reached,
                species,
                item,
                ability,
                nature,
                moves,
                eff_weight
            FROM _tmp_scored
            ORDER BY eff_weight DESC, placement ASC
            LIMIT 10;
            """
        )
        profile.top_builds = [
            TournamentBuildRecord(
                tournament_id=str(r["tournament_id"]),
                player_name=str(r["player_name"]),
                placement=int(r["placement"]),
                day_reached=str(r["day_reached"]),
                species=str(r["species"]),
                item=str(r["item"]),
                ability=str(r["ability"]),
                nature=str(r["nature"]),
                moves=tuple(self.canonical_move_name(str(m)) for m in (r.get("moves") or [])),
                weight=float(r["eff_weight"]),
            )
            for r in top_rows
        ]

        return profile


_SHARED_REPOSITORY: Optional[TournamentUsageRepository] = None


def get_tournament_repository() -> TournamentUsageRepository:
    """Return a singleton TournamentUsageRepository instance backed by VGCDataRegistry."""
    global _SHARED_REPOSITORY
    if _SHARED_REPOSITORY is None:
        _SHARED_REPOSITORY = TournamentUsageRepository()
    return _SHARED_REPOSITORY
