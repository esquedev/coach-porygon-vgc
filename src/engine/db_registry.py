# engine/db_registry.py
import copy
import threading
import duckdb
from pathlib import Path
from typing import Any

# Resolve directories relative to this file
ENGINE_DIR = Path(__file__).resolve().parent
DATA_DIR = ENGINE_DIR / "data"
SHOWDOWN_DIR = DATA_DIR / "showdown"
MUNCHSTATS_ARCHIVE_DIR = DATA_DIR / "munchstats" / "raw" / "archive"


class VGCDataRegistry:
    def __init__(self):
        # In-memory DuckDB session with thread-local cursors for safe multi-threaded execution
        self.con = duckdb.connect(database=":memory:")
        self._cursor_lock = threading.Lock()
        self._thread_local = threading.local()
        self._cache_lock = threading.Lock()
        self._pokemon_cache: dict[str, Any] = {}
        self._move_cache: dict[str, Any] = {}
        self._condition_cache: dict[str, Any] = {}
        self._init_views()

    def _get_cursor(self) -> duckdb.DuckDBPyConnection:
        """Return a thread-local DuckDB cursor so concurrent CPU/GPU workers never collide."""
        cur = getattr(self._thread_local, "cursor", None)
        if cur is None:
            with self._cursor_lock:
                cur = self.con.cursor()
            self._thread_local.cursor = cur
        return cur

    def _init_views(self):
        """Creates unified SQL views across Showdown and all Munchstats tournament archives."""
        
        # 1. Showdown Mechanics Views
        pokedex_path = (SHOWDOWN_DIR / "pokedex.jsonl").as_posix()
        moves_path = (SHOWDOWN_DIR / "moves.jsonl").as_posix()
        items_path = (SHOWDOWN_DIR / "items.jsonl").as_posix()
        abilities_path = (SHOWDOWN_DIR / "abilities.jsonl").as_posix()
        learnsets_path = (SHOWDOWN_DIR / "learnsets.jsonl").as_posix()
        conditions_path = (SHOWDOWN_DIR / "conditions.jsonl").as_posix()

        if Path(pokedex_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW pokedex AS 
                SELECT 
                    id,
                    REPLACE(REPLACE(name, '’', ''''), '‘', '''') AS name,
                    num,
                    types,
                    baseSpecies,
                    baseForme,
                    forme,
                    requiredItem,
                    otherFormes,
                    baseStats,
                    baseStats.hp AS hp,
                    baseStats.atk AS atk,
                    baseStats.def AS def,
                    baseStats.spa AS spa,
                    baseStats.spd AS spd,
                    baseStats.spe AS spe,
                    abilities
                FROM read_ndjson('{pokedex_path}', union_by_name=True);
            """)

        if Path(moves_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW moves AS 
                SELECT *
                FROM read_ndjson('{moves_path}', union_by_name=True);
            """)

        if Path(items_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW items AS 
                SELECT * 
                FROM read_ndjson('{items_path}', union_by_name=True);
            """)

        if Path(abilities_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW abilities AS 
                SELECT * 
                FROM read_ndjson('{abilities_path}', union_by_name=True);
            """)

        if Path(learnsets_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW learnsets AS 
                SELECT id, learnset 
                FROM read_ndjson('{learnsets_path}', union_by_name=True);
            """)

        if Path(conditions_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW conditions AS 
                SELECT * FROM read_ndjson('{conditions_path}', union_by_name=True);
            """)

        # 2. Munchstats Tournament Archives (DuckDB auto-globs every subfolder)
        standings_glob = (MUNCHSTATS_ARCHIVE_DIR / "*" / "standings.jsonl").as_posix()
        usage_glob = (MUNCHSTATS_ARCHIVE_DIR / "*" / "usage.jsonl").as_posix()
        overview_glob = (MUNCHSTATS_ARCHIVE_DIR / "*" / "overview.jsonl").as_posix()

        if MUNCHSTATS_ARCHIVE_DIR.exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW tournament_standings AS 
                SELECT * FROM read_ndjson('{standings_glob}', union_by_name=True);
            """)

            self.con.execute(f"""
                CREATE OR REPLACE VIEW tournament_usage AS 
                SELECT * FROM read_ndjson('{usage_glob}', union_by_name=True);
            """)

            self.con.execute(f"""
                CREATE OR REPLACE VIEW tournament_overview AS 
                SELECT * FROM read_ndjson('{overview_glob}', union_by_name=True);
            """)

            self.con.execute("""
                CREATE OR REPLACE TABLE tournament_team_slots AS
                SELECT
                    t.tournament_id,
                    REPLACE(REPLACE(TRIM(CAST(t.name AS VARCHAR)), '’', ''''), '‘', '''') AS player_name,
                    COALESCE(TRY_CAST(t.placement AS INTEGER), 999) AS placement,
                    COALESCE(CAST(t.day_reached AS VARCHAR), 'all') AS day_reached,
                    CASE
                        WHEN COALESCE(TRY_CAST(t.placement AS INTEGER), 999) <= 8 OR t.day_reached = 'top8' THEN 3.0
                        WHEN COALESCE(TRY_CAST(t.placement AS INTEGER), 999) <= 16 OR t.day_reached = 'top16' THEN 2.25
                        WHEN COALESCE(TRY_CAST(t.placement AS INTEGER), 999) <= 64 OR t.day_reached = 'day2' THEN 1.5
                        ELSE 1.0
                    END AS weight,
                    CASE
                        WHEN REPLACE(REPLACE(TRIM(CAST(u.slot.pokemon AS VARCHAR)), '’', ''''), '‘', '''') = 'Maushold-Three' THEN 'Maushold'
                        ELSE REPLACE(REPLACE(TRIM(CAST(u.slot.pokemon AS VARCHAR)), '’', ''''), '‘', '''')
                    END AS species,
                    CASE
                        WHEN LOWER(REPLACE(REPLACE(TRIM(COALESCE(CAST(u.slot.item AS VARCHAR), '')), '’', ''''), '‘', '''')) = 'choice band'
                             AND LOWER(TRIM(CAST(u.slot.pokemon AS VARCHAR))) LIKE 'indeedee%' THEN 'Choice Scarf'
                        WHEN LOWER(REPLACE(REPLACE(TRIM(COALESCE(CAST(u.slot.item AS VARCHAR), '')), '’', ''''), '‘', '''')) IN (
                            SELECT LOWER(name) FROM items
                        ) THEN REPLACE(REPLACE(TRIM(COALESCE(CAST(u.slot.item AS VARCHAR), '')), '’', ''''), '‘', '''')
                        ELSE ''
                    END AS item,
                    REPLACE(REPLACE(TRIM(COALESCE(CAST(u.slot.ability AS VARCHAR), '')), '’', ''''), '‘', '''') AS ability,
                    COALESCE(NULLIF(TRIM(CAST(u.slot.nature AS VARCHAR)), ''), 'Hardy') AS nature,
                    list_transform(
                        u.slot.moves,
                        lambda m: REPLACE(REPLACE(TRIM(CAST(m AS VARCHAR)), '’', ''''), '‘', '''')
                    ) AS moves
                FROM tournament_standings t,
                UNNEST(t.team) AS u(slot)
                WHERE u.slot.pokemon IS NOT NULL AND TRIM(CAST(u.slot.pokemon AS VARCHAR)) != '';
            """)

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        """Runs arbitrary SQL thread-safely via a per-thread DuckDB cursor and returns dicts."""
        cur = self._get_cursor()
        rel = cur.execute(sql, params)
        cols = [desc[0] for desc in rel.description] if rel.description else []
        return [dict(zip(cols, row)) for row in rel.fetchall()]

    # --- High-Frequency Lookup Helpers (thread-safe read-only caches) ---

    def get_pokemon(self, name_or_id: str) -> dict[str, Any] | None:
        """Fetch a Pokédex entry by canonical ID, display name, or `<name>-<baseForme>` alias."""
        raw_lower = name_or_id.strip().lower()
        clean = "".join(ch for ch in raw_lower if ch.isalnum())
        cache_key = f"{clean}|{raw_lower}"
        with self._cache_lock:
            if cache_key in self._pokemon_cache:
                cached = self._pokemon_cache[cache_key]
                return copy.deepcopy(cached) if cached is not None else None
        res = self.query(
            "SELECT * FROM pokedex WHERE LOWER(id) = ? OR LOWER(name) = ? LIMIT 1;",
            (clean, raw_lower),
        )
        found = res[0] if res else None
        if found is None:
            # Fallback for Showdown baseForme aliases (e.g., 'Maushold-Three' -> 'maushold',
            # 'Palafin-Zero' -> 'palafin', 'Mimikyu-Disguised' -> 'mimikyu').
            res = self.query(
                """
                SELECT * FROM pokedex
                WHERE baseForme IS NOT NULL
                  AND LOWER(id) || LOWER(REGEXP_REPLACE(baseForme, '[^a-zA-Z0-9]', '', 'g')) = ?
                LIMIT 1;
                """,
                (clean,),
            )
            found = res[0] if res else None
        with self._cache_lock:
            self._pokemon_cache[cache_key] = copy.deepcopy(found) if found is not None else None
        return found

    def get_move(self, name_or_id: str) -> dict[str, Any] | None:
        raw_lower = name_or_id.strip().lower()
        clean = raw_lower.replace(" ", "").replace("-", "")
        cache_key = f"{clean}|{raw_lower}"
        with self._cache_lock:
            if cache_key in self._move_cache:
                cached = self._move_cache[cache_key]
                return copy.deepcopy(cached) if cached is not None else None
        res = self.query(
            "SELECT * FROM moves WHERE LOWER(id) = ? OR LOWER(name) = ? LIMIT 1;",
            (clean, raw_lower),
        )
        found = res[0] if res else None
        with self._cache_lock:
            self._move_cache[cache_key] = copy.deepcopy(found) if found is not None else None
        return found

    def get_condition(self, name_or_id: str) -> dict[str, Any] | None:
        """Fetch status/weather/terrain/mechanic condition details."""
        raw_lower = name_or_id.strip().lower()
        clean = raw_lower.replace(" ", "").replace("-", "")
        cache_key = f"{clean}|{raw_lower}"
        with self._cache_lock:
            if cache_key in self._condition_cache:
                cached = self._condition_cache[cache_key]
                return copy.deepcopy(cached) if cached is not None else None
        res = self.query(
            "SELECT * FROM conditions WHERE LOWER(id) = ? OR LOWER(name) = ? LIMIT 1;",
            (clean, raw_lower),
        )
        found = res[0] if res else None
        with self._cache_lock:
            self._condition_cache[cache_key] = copy.deepcopy(found) if found is not None else None
        return found

    def get_tournament_top_cut(self, tournament_id: str = None, top_rank: int = 8) -> list[dict[str, Any]]:
        if tournament_id:
            sql = """
                SELECT * FROM tournament_standings 
                WHERE tournament_id = ? AND placement <= ?
                ORDER BY placement ASC;
            """
            return self.query(sql, (tournament_id, top_rank))
        else:
            sql = """
                SELECT * FROM tournament_standings 
                WHERE placement <= ?
                ORDER BY tournament_id, placement ASC;
            """
            return self.query(sql, (top_rank,))


_registry_instance: VGCDataRegistry | None = None
_registry_init_lock = threading.Lock()

def get_registry() -> VGCDataRegistry:
    """Returns a shared in-memory DuckDB instance across agent calls."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_init_lock:
            if _registry_instance is None:
                _registry_instance = VGCDataRegistry()
    return _registry_instance
