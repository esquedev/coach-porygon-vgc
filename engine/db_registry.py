# engine/db_registry.py
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
        # In-memory DuckDB session (ultra-fast, zero-lock)
        self.con = duckdb.connect(database=":memory:")
        self._init_views()

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
                    name,
                    num,
                    types,
                    baseStats.hp AS hp,
                    baseStats.atk AS atk,
                    baseStats.def AS def,
                    baseStats.spa AS spa,
                    baseStats.spd AS spd,
                    baseStats.spe AS spe,
                    abilities
                FROM read_ndjson('{pokedex_path}');
            """)

        if Path(moves_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW moves AS 
                SELECT 
                    id,
                    name,
                    basePower,
                    accuracy,
                    priority,
                    category,
                    type,
                    target
                FROM read_ndjson('{moves_path}');
            """)

        if Path(items_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW items AS 
                SELECT id, name, desc 
                FROM read_ndjson('{items_path}');
            """)

        if Path(abilities_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW abilities AS 
                SELECT id, name, desc, shortDesc 
                FROM read_ndjson('{abilities_path}');
            """)

        if Path(learnsets_path).exists():
            self.con.execute(f"""
                CREATE OR REPLACE VIEW learnsets AS 
                SELECT id, learnset 
                FROM read_ndjson('{learnsets_path}');
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

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        """Runs arbitrary SQL and returns results as a list of dicts."""
        rel = self.con.execute(sql, params)
        cols = [desc[0] for desc in rel.description] if rel.description else []
        return [dict(zip(cols, row)) for row in rel.fetchall()]

    # --- High-Frequency Lookup Helpers ---

    def get_pokemon(self, name_or_id: str) -> dict[str, Any] | None:
        clean = name_or_id.strip().lower().replace(" ", "").replace("-", "")
        res = self.query(
            "SELECT * FROM pokedex WHERE LOWER(id) = ? OR LOWER(name) = ? LIMIT 1;",
            (clean, name_or_id.strip().lower())
        )
        return res[0] if res else None

    def get_move(self, name_or_id: str) -> dict[str, Any] | None:
        clean = name_or_id.strip().lower().replace(" ", "").replace("-", "")
        res = self.query(
            "SELECT * FROM moves WHERE LOWER(id) = ? OR LOWER(name) = ? LIMIT 1;",
            (clean, name_or_id.strip().lower())
        )
        return res[0] if res else None

    def get_condition(self, name_or_id: str) -> dict[str, Any] | None:
        """Fetch status/weather/terrain/mechanic condition details."""
        clean = name_or_id.strip().lower().replace(" ", "").replace("-", "")
        res = self.query(
            "SELECT * FROM conditions WHERE LOWER(id) = ? OR LOWER(name) = ? LIMIT 1;",
            (clean, name_or_id.strip().lower())
        )
        return res[0] if res else None

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
