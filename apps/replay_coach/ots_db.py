# -*- coding: utf-8 -*-
"""Persistent DuckDB OTS + EVs/SPs Roster Database (Zero-AI Ground Truth).

Stores full Regulation M-C Open Team Sheets with exact 66-SP (or cartridge EV)
allocations for both `trainer_1` and `trainer_2` so the GPU Tensor Core Engine
solves exact Nash Equilibria without Bayesian guesswork or LLM calls.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Sequence

import duckdb

from engine.parser.models import ParsedPokemon
from engine.parser.showdown_parser import parse_showdown_paste
from engine.sp_validator import validate_and_calculate_sp
from engine.vgc_tensor_core.victory_equity import EQUITY_ENGINE_VERSION

DEFAULT_DB_PATH = Path("data/replay_coach_ots.duckdb")
DEFAULT_TRAINER_1_PASTE = Path("data/teams/char_y_v4.txt")
DEFAULT_OPPONENT_PASTE = Path("apps/replay_coach/sample_data/matchagotme_ots.txt")
SLUG_MAP_PATH = Path("assets/slug_map.json")
SEED_ROSTER_IDS = frozenset({"treces_gc_char_y_v4", "matchagotme_camerupt_tr"})

KNOWN_ARCHETYPES: tuple[str, ...] = (
    "Dual Weather",
    "Sun",
    "Rain",
    "Sand",
    "Snow",
    "Trick Room",
    "Tailwind / Hyper Offense",
    "Psychic Terrain",
    "Grassy Balance",
    "Goodstuffs / Balance",
)
KNOWN_REGULATIONS: tuple[str, ...] = ("Reg M-C", "Reg M-D", "Custom")


def classify_team_archetype(paste_text: str) -> str:
    """Deterministically classify a 6-Pokémon VGC team paste into a canonical archetype."""
    text = (paste_text or "").strip()
    if not text:
        return "Goodstuffs / Balance"
    try:
        mons = list(parse_showdown_paste(text).values())
    except Exception:
        mons = []
    if not mons:
        return "Goodstuffs / Balance"

    seen: set[int] = set()
    abilities: set[str] = set()
    items: set[str] = set()
    moves: set[str] = set()
    species_l: set[str] = set()
    for m in mons:
        if id(m) in seen:
            continue
        seen.add(id(m))
        species_l.add((m.species or "").lower())
        if m.ability:
            abilities.add(m.ability.strip().lower())
        if m.item:
            items.add(m.item.strip().lower())
        for mv in (m.moves or []):
            moves.add(str(mv).strip().lower())

    has_sun = (
        "drought" in abilities
        or "charizardite y" in items
        or "sunny day" in moves
        or "torkoal" in species_l
    )
    has_rain = (
        "drizzle" in abilities
        or "rain dance" in moves
        or "pelipper" in species_l
        or "politoed" in species_l
    )
    has_sand = "sand stream" in abilities or "tyranitar" in species_l or "hippowdon" in species_l
    has_snow = "snow warning" in abilities or "aurora veil" in moves
    has_tr = "trick room" in moves
    has_tw = "tailwind" in moves
    has_psy = "psychic surge" in abilities or "expanding force" in moves
    has_grassy = "grassy surge" in abilities

    if has_sun and has_rain:
        return "Dual Weather"
    if has_tr and not has_tw:
        return "Trick Room"
    if has_sun:
        return "Sun"
    if has_rain:
        return "Rain"
    if has_sand:
        return "Sand"
    if has_snow:
        return "Snow"
    if has_psy:
        return "Psychic Terrain"
    if has_tw:
        return "Tailwind / Hyper Offense"
    if has_grassy:
        return "Grassy Balance"
    return "Goodstuffs / Balance"

_CACHED_SLUG_LOOKUP: Optional[Dict[str, Dict[str, str]]] = None


def _norm_slug(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def canonical_mode_key(lead_species: Sequence[str], bench_species: Sequence[str]) -> str:
    """Build an order-invariant species key (`leadA+leadB|benchA+benchB`) for deep-audit caching."""
    l_toks = sorted(_norm_slug(s) for s in (lead_species or []) if s)
    b_toks = sorted(_norm_slug(s) for s in (bench_species or []) if s)
    return f"{'+'.join(l_toks)}|{'+'.join(b_toks)}"


def canonical_deep_audit_cell_key(
    lead_1: Sequence[str],
    bench_1: Sequence[str],
    lead_2: Sequence[str],
    bench_2: Sequence[str],
) -> str:
    """Build canonical species-grounded deep-audit cell key immune to paste slot reordering."""
    return f"{canonical_mode_key(lead_1, bench_1)}__{canonical_mode_key(lead_2, bench_2)}"


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


def canonicalize_team_paste(paste_text: str) -> str:
    """Build an order-invariant, whitespace-normalized canonical signature for a Showdown paste."""
    text = (paste_text or "").strip()
    if not text:
        return ""
    try:
        mons = parse_showdown_paste(text)
    except Exception:
        return " ".join(text.split()).lower()
    unique: List[ParsedPokemon] = []
    seen_ids = set()
    for mon in mons.values():
        if id(mon) not in seen_ids:
            seen_ids.add(id(mon))
            unique.append(mon)
    if not unique:
        return " ".join(text.split()).lower()
    entries: List[str] = []
    for mon in unique:
        sp = mon.spread.to_dict()
        moves = sorted(_norm_slug(mv) for mv in (mon.moves or []))
        entries.append(
            "|".join(
                [
                    _norm_slug(mon.species),
                    _norm_slug(mon.item or ""),
                    _norm_slug(mon.ability or ""),
                    _norm_slug(mon.nature or ""),
                    ",".join(f"{k}:{int(sp.get(k, 0))}" for k in ("hp", "atk", "def", "spa", "spd", "spe")),
                    ",".join(moves),
                ]
            )
        )
    entries.sort()
    return "\n".join(entries)


def compute_lead_lab_matchup_hash(
    t1_paste: str,
    t2_paste: str,
    preset: str,
    engine_version: str = EQUITY_ENGINE_VERSION,
) -> str:
    """Compute canonical SHA-256 matchup hash for `(trainer_1, trainer_2, preset, engine_version)`."""
    c1 = canonicalize_team_paste(t1_paste)
    c2 = canonicalize_team_paste(t2_paste)
    raw = f"{str(engine_version).strip()}||{str(preset or 'balanced').strip().lower()}||{c1}||VS||{c2}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _compute_paste_pair_key(t1_paste: str, t2_paste: str, preset: str) -> str:
    """Engine-version-independent key used to detect outdated Vault entries after equity upgrades."""
    c1 = canonicalize_team_paste(t1_paste)
    c2 = canonicalize_team_paste(t2_paste)
    raw = f"{str(preset or 'balanced').strip().lower()}||{c1}||VS||{c2}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class OTSRosterDatabase:
    """DuckDB-backed persistent store for exact OTS + 66-SP team sheets and Lead Lab Matchup Vault."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_lock = threading.RLock()
        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()
        self._seed_defaults()

    def _init_schema(self) -> None:
        """Create persistent DuckDB tables for OTS rosters and Lead Lab Matchup Vault."""
        with self._db_lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ots_rosters (
                    roster_id VARCHAR PRIMARY KEY,
                    display_name VARCHAR NOT NULL,
                    trainer_hint VARCHAR NOT NULL,
                    paste_text VARCHAR NOT NULL,
                    species_json VARCHAR NOT NULL,
                    updated_at VARCHAR NOT NULL,
                    team_scope VARCHAR NOT NULL DEFAULT 'own',
                    archetype VARCHAR NOT NULL DEFAULT '',
                    regulation VARCHAR NOT NULL DEFAULT 'Reg M-C',
                    source_type VARCHAR NOT NULL DEFAULT 'personal',
                    opponent_elo INTEGER,
                    notes VARCHAR NOT NULL DEFAULT ''
                );
                """
            )
            # Idempotent forward schema migration for existing DuckDB databases
            existing_cols = {
                str(r[1]).lower()
                for r in self.conn.execute("PRAGMA table_info('ots_rosters');").fetchall()
            }
            for col_name, col_ddl in (
                ("team_scope", "VARCHAR NOT NULL DEFAULT 'own'"),
                ("archetype", "VARCHAR NOT NULL DEFAULT ''"),
                ("regulation", "VARCHAR NOT NULL DEFAULT 'Reg M-C'"),
                ("source_type", "VARCHAR NOT NULL DEFAULT 'personal'"),
                ("opponent_elo", "INTEGER"),
                ("notes", "VARCHAR NOT NULL DEFAULT ''"),
            ):
                if col_name not in existing_cols:
                    self.conn.execute(f"ALTER TABLE ots_rosters ADD COLUMN {col_name} {col_ddl};")

            # Backfill archetype & normalize seed/rival scopes cleanly for pre-v0.4.0 rows
            rows_backfill = self.conn.execute(
                "SELECT roster_id, paste_text, archetype, team_scope, trainer_hint FROM ots_rosters;"
            ).fetchall()
            for r_id, p_txt, arch, sc, t_hint in rows_backfill:
                updates: Dict[str, Any] = {}
                if not str(arch or "").strip():
                    updates["archetype"] = classify_team_archetype(str(p_txt or ""))
                if str(r_id) == "matchagotme_camerupt_tr" and str(sc or "") == "own":
                    updates["team_scope"] = "rival"
                    updates["source_type"] = "showdown_ladder"
                    updates["opponent_elo"] = 1229
                    updates["display_name"] = "Showdown Opponent (Elo 1229) — Trick Room"
                    updates["trainer_hint"] = "Showdown Opponent (Elo 1229)"
                if updates:
                    sets_sql = ", ".join(f"{k} = ?" for k in updates.keys())
                    self.conn.execute(
                        f"UPDATE ots_rosters SET {sets_sql} WHERE roster_id = ?;",
                        list(updates.values()) + [r_id],
                    )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_lab_runs (
                    run_id VARCHAR PRIMARY KEY,
                    matchup_hash VARCHAR NOT NULL,
                    t1_name VARCHAR NOT NULL,
                    t2_name VARCHAR NOT NULL,
                    t1_species_json VARCHAR NOT NULL,
                    t2_species_json VARCHAR NOT NULL,
                    t1_paste VARCHAR NOT NULL,
                    t2_paste VARCHAR NOT NULL,
                    preset VARCHAR NOT NULL,
                    engine_version VARCHAR NOT NULL,
                    global_nash_value DOUBLE NOT NULL,
                    top_t1_bring_json VARCHAR NOT NULL,
                    top_t2_threat_json VARCHAR NOT NULL,
                    payload_json VARCHAR NOT NULL,
                    tags VARCHAR NOT NULL DEFAULT '',
                    elapsed_s DOUBLE NOT NULL DEFAULT 0.0,
                    created_at VARCHAR NOT NULL
                );
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_lab_deep_audits (
                    audit_key VARCHAR PRIMARY KEY,
                    matchup_hash VARCHAR NOT NULL,
                    t1_mode_key VARCHAR NOT NULL,
                    t2_mode_key VARCHAR NOT NULL,
                    engine_version VARCHAR NOT NULL,
                    payload_json VARCHAR NOT NULL,
                    created_at VARCHAR NOT NULL
                );
                """
            )

            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dismissed_seed_rosters (
                    roster_id VARCHAR PRIMARY KEY,
                    dismissed_at VARCHAR NOT NULL
                );
                """
            )

    def _seed_defaults(self) -> None:
        """Pre-seed `treces_gc` (`char_y_v4.txt`) and `MatchaGotMe` OTS unless user deleted them."""
        with self._db_lock:
            dismissed_rows = self.conn.execute("SELECT roster_id FROM dismissed_seed_rosters;").fetchall()
            dismissed = {str(r[0]) for r in dismissed_rows}
        if (
            "treces_gc_char_y_v4" not in dismissed
            and DEFAULT_TRAINER_1_PASTE.exists()
            and self.get_roster("treces_gc_char_y_v4") is None
        ):
            self.save_roster(
                roster_id="treces_gc_char_y_v4",
                display_name="treces_gc — Charizard-Y Dual Weather v4",
                trainer_hint="treces_gc",
                paste_text=DEFAULT_TRAINER_1_PASTE.read_text(encoding="utf-8"),
                team_scope="own",
                archetype="Dual Weather",
                regulation="Reg M-C",
                source_type="personal",
            )
        if (
            "matchagotme_camerupt_tr" not in dismissed
            and DEFAULT_OPPONENT_PASTE.exists()
            and self.get_roster("matchagotme_camerupt_tr") is None
        ):
            self.save_roster(
                roster_id="matchagotme_camerupt_tr",
                display_name="Showdown Opponent (Elo 1229) — Trick Room",
                trainer_hint="Showdown Opponent (Elo 1229)",
                paste_text=DEFAULT_OPPONENT_PASTE.read_text(encoding="utf-8"),
                team_scope="rival",
                archetype="Trick Room",
                regulation="Reg M-C",
                source_type="showdown_ladder",
                opponent_elo=1229,
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
        team_scope: str = "own",
        archetype: str = "",
        regulation: str = "Reg M-C",
        source_type: str = "personal",
        opponent_elo: Optional[int] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Insert or update an OTS + EVs/SPs roster in DuckDB with Own/Rival scope & archetype metadata."""
        pokemon_dict = parse_showdown_paste(paste_text)
        species_list: List[str] = []
        seen_ids = set()
        for mon in pokemon_dict.values():
            if id(mon) not in seen_ids:
                seen_ids.add(id(mon))
                species_list.append(mon.species)
        now = datetime.now(timezone.utc).isoformat()
        clean_id = roster_id.strip()
        scope_clean = "rival" if str(team_scope or "").strip().lower() in ("rival", "opponent", "enemy", "t2") else "own"
        src_clean = str(source_type or ("showdown_ladder" if scope_clean == "rival" else "personal")).strip().lower()
        if src_clean not in ("personal", "showdown_ladder", "tournament"):
            src_clean = "showdown_ladder" if scope_clean == "rival" else "personal"
        arch_clean = str(archetype or "").strip() or classify_team_archetype(paste_text)
        reg_clean = str(regulation or "Reg M-C").strip() or "Reg M-C"
        elo_clean: Optional[int] = None
        if opponent_elo is not None and str(opponent_elo).strip() != "":
            try:
                ev = int(opponent_elo)
                if ev > 0:
                    elo_clean = ev
            except (TypeError, ValueError):
                pass
        notes_clean = str(notes or "").strip()[:300]

        # Enforce Showdown Opponent privacy legend whenever saving a Showdown ladder rival team
        hint_clean = trainer_hint.strip()
        disp_clean = display_name.strip() or clean_id
        if src_clean == "showdown_ladder" and scope_clean == "rival":
            anon_lbl = f"Showdown Opponent (Elo {elo_clean})" if elo_clean else "Showdown Opponent (Unrated)"
            hint_clean = anon_lbl
            if "showdown opponent" not in disp_clean.lower():
                disp_clean = f"{anon_lbl} — {arch_clean}"

        with self._db_lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO ots_rosters
                (roster_id, display_name, trainer_hint, paste_text, species_json, updated_at,
                 team_scope, archetype, regulation, source_type, opponent_elo, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                [
                    clean_id,
                    disp_clean,
                    hint_clean,
                    paste_text.strip(),
                    json.dumps(species_list),
                    now,
                    scope_clean,
                    arch_clean,
                    reg_clean,
                    src_clean,
                    elo_clean,
                    notes_clean,
                ],
            )
            if clean_id in SEED_ROSTER_IDS:
                self.conn.execute("DELETE FROM dismissed_seed_rosters WHERE roster_id = ?;", [clean_id])
        return self.get_roster(clean_id) or {}

    def _row_to_roster_dict(self, r: Sequence[Any], include_sprites: bool = False) -> Dict[str, Any]:
        sp_list = json.loads(r[4])
        elo_val = int(r[10]) if r[10] is not None else None
        scope_val = str(r[6] or "own")
        src_val = str(r[9] or "personal")
        out: Dict[str, Any] = {
            "roster_id": str(r[0]),
            "display_name": str(r[1]),
            "trainer_hint": str(r[2]),
            "paste_text": str(r[3]),
            "species": sp_list,
            "updated_at": str(r[5]),
            "team_scope": scope_val,
            "archetype": str(r[7] or "") or classify_team_archetype(str(r[3])),
            "regulation": str(r[8] or "Reg M-C"),
            "source_type": src_val,
            "opponent_elo": elo_val,
            "notes": str(r[11] or ""),
            "source_legend": (
                (f"Showdown Opponent · Elo {elo_val}" if elo_val else "Showdown Opponent · Unrated")
                if src_val == "showdown_ladder"
                else ("Tournament Archive" if src_val == "tournament" else "Personal Roster")
            ),
        }
        if include_sprites:
            out["species_sprites"] = [
                {"species": sp, "sprite_url": resolve_sprite_urls(sp)["sprite_url"]}
                for sp in sp_list
            ]
        return out

    def get_roster(self, roster_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single stored roster by ID."""
        row = self.conn.execute(
            """
            SELECT roster_id, display_name, trainer_hint, paste_text, species_json, updated_at,
                   team_scope, archetype, regulation, source_type, opponent_elo, notes
            FROM ots_rosters WHERE roster_id = ?;
            """,
            [roster_id],
        ).fetchone()
        if not row:
            return None
        return self._row_to_roster_dict(row, include_sprites=False)

    def list_rosters(self, team_scope: Optional[str] = None) -> List[Dict[str, Any]]:
        """List stored OTS rosters (optionally filtered by `own` / `rival`) ordered by most recently updated."""
        scope_f = str(team_scope or "").strip().lower()
        if scope_f in ("own", "rival"):
            rows = self.conn.execute(
                """
                SELECT roster_id, display_name, trainer_hint, paste_text, species_json, updated_at,
                       team_scope, archetype, regulation, source_type, opponent_elo, notes
                FROM ots_rosters WHERE team_scope = ? ORDER BY updated_at DESC;
                """,
                [scope_f],
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT roster_id, display_name, trainer_hint, paste_text, species_json, updated_at,
                       team_scope, archetype, regulation, source_type, opponent_elo, notes
                FROM ots_rosters ORDER BY updated_at DESC;
                """
            ).fetchall()
        return [self._row_to_roster_dict(r, include_sprites=True) for r in rows]

    def search_rosters(
        self,
        scope: str = "",
        archetype: str = "",
        regulation: str = "",
        source_type: str = "",
        q: str = "",
        min_elo: Optional[int] = None,
        max_elo: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Multi-facet search across Own & Rival DuckDB rosters by scope, archetype, regulation, Elo & Pokémon."""
        all_rows = self.list_rosters()
        sc_f = str(scope or "").strip().lower()
        arch_f = str(archetype or "").strip().lower()
        reg_f = str(regulation or "").strip().lower()
        src_f = str(source_type or "").strip().lower()
        tokens = [t for t in str(q or "").strip().lower().split() if t]

        matched: List[Dict[str, Any]] = []
        own_count = 0
        rival_count = 0
        archetypes_present: set[str] = set()
        regulations_present: set[str] = set()

        for r in all_rows:
            if r["team_scope"] == "rival":
                rival_count += 1
            else:
                own_count += 1
            if r["archetype"]:
                archetypes_present.add(r["archetype"])
            if r["regulation"]:
                regulations_present.add(r["regulation"])

            if sc_f in ("own", "rival") and r["team_scope"] != sc_f:
                continue
            if arch_f and arch_f != "all" and arch_f not in r["archetype"].lower():
                continue
            if reg_f and reg_f != "all" and reg_f != r["regulation"].lower():
                continue
            if src_f and src_f != "all" and src_f != r["source_type"].lower():
                continue
            if min_elo is not None and (r["opponent_elo"] is None or int(r["opponent_elo"]) < int(min_elo)):
                continue
            if max_elo is not None and (r["opponent_elo"] is None or int(r["opponent_elo"]) > int(max_elo)):
                continue
            if tokens:
                hay = " ".join(
                    [
                        r["display_name"],
                        r["trainer_hint"],
                        r["archetype"],
                        r["regulation"],
                        r["notes"],
                        " ".join(r["species"]),
                        r["paste_text"],
                    ]
                ).lower()
                if not all(tok in hay for tok in tokens):
                    continue
            matched.append(r)

        return {
            "ok": True,
            "total_count": len(all_rows),
            "own_count": own_count,
            "rival_count": rival_count,
            "matched_count": len(matched),
            "archetypes": sorted(archetypes_present | set(KNOWN_ARCHETYPES)),
            "regulations": sorted(regulations_present | set(KNOWN_REGULATIONS)),
            "rosters": matched,
        }

    def update_roster_meta(
        self,
        roster_id: str,
        display_name: Optional[str] = None,
        team_scope: Optional[str] = None,
        archetype: Optional[str] = None,
        regulation: Optional[str] = None,
        opponent_elo: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update editable metadata (`team_scope`, `archetype`, `regulation`, `notes`, `opponent_elo`) on a roster."""
        existing = self.get_roster(roster_id)
        if existing is None:
            return None
        return self.save_roster(
            roster_id=existing["roster_id"],
            display_name=display_name if display_name is not None else existing["display_name"],
            trainer_hint=existing["trainer_hint"],
            paste_text=existing["paste_text"],
            team_scope=team_scope if team_scope is not None else existing["team_scope"],
            archetype=archetype if archetype is not None else existing["archetype"],
            regulation=regulation if regulation is not None else existing["regulation"],
            source_type=existing["source_type"],
            opponent_elo=opponent_elo if opponent_elo is not None else existing["opponent_elo"],
            notes=notes if notes is not None else existing["notes"],
        )

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
        """Delete a stored OTS roster by ID (persisting dismissal for built-in seed rosters)."""
        clean_id = (roster_id or "").strip()
        with self._db_lock:
            if not clean_id or self.get_roster(clean_id) is None:
                return False
            self.conn.execute("DELETE FROM ots_rosters WHERE roster_id = ?;", [clean_id])
            if clean_id in SEED_ROSTER_IDS:
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO dismissed_seed_rosters (roster_id, dismissed_at)
                    VALUES (?, ?);
                    """,
                    [clean_id, now],
                )
            return True

    # =========================================================================
    # LEAD LAB DUCKDB MATCHUP VAULT (90x90 RUNS + K=128 DEEP TURN-1 AUDITS)
    # =========================================================================

    def _extract_paste_species(self, paste_text: str) -> List[str]:
        try:
            pokemon_dict = parse_showdown_paste(paste_text or "")
            out: List[str] = []
            seen = set()
            for mon in pokemon_dict.values():
                if id(mon) not in seen:
                    seen.add(id(mon))
                    out.append(mon.species)
            return out
        except Exception:
            return []

    def save_lead_lab_run(
        self,
        t1_name: str,
        t2_name: str,
        t1_paste: str,
        t2_paste: str,
        preset: str,
        result_payload: Dict[str, Any],
        tags: str = "",
        engine_version: str = EQUITY_ENGINE_VERSION,
    ) -> Dict[str, Any]:
        """Persist a completed `90x90` Lead Lab matchup sweep into DuckDB `lead_lab_runs`."""
        preset_norm = str(preset or "balanced").strip().lower()
        eng_ver = str(engine_version or EQUITY_ENGINE_VERSION).strip()
        m_hash = compute_lead_lab_matchup_hash(t1_paste, t2_paste, preset_norm, engine_version=eng_ver)
        run_id = m_hash

        t1_species = list(result_payload.get("t1_species") or self._extract_paste_species(t1_paste))
        t2_species = list(result_payload.get("t2_species") or self._extract_paste_species(t2_paste))
        global_v = float(result_payload.get("global_game_value", 0.0))
        elapsed_s = float(result_payload.get("elapsed_s", 0.0))
        top_t1_list = result_payload.get("trainer_1_top_brings") or []
        top_t2_list = result_payload.get("trainer_2_top_brings") or []
        top_t1 = top_t1_list[0] if top_t1_list else {}
        top_t2 = top_t2_list[0] if top_t2_list else {}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._db_lock:
            existing_tags = ""
            if not (tags or "").strip():
                prev = self.conn.execute(
                    "SELECT tags FROM lead_lab_runs WHERE run_id = ?;",
                    [run_id],
                ).fetchone()
                if prev and prev[0]:
                    existing_tags = str(prev[0])
            final_tags = (tags or "").strip() or existing_tags

            self.conn.execute(
                """
                INSERT OR REPLACE INTO lead_lab_runs (
                    run_id, matchup_hash, t1_name, t2_name,
                    t1_species_json, t2_species_json, t1_paste, t2_paste,
                    preset, engine_version, global_nash_value,
                    top_t1_bring_json, top_t2_threat_json, payload_json,
                    tags, elapsed_s, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                [
                    run_id,
                    m_hash,
                    (t1_name or "Team 1 (trainer_1)").strip(),
                    (t2_name or "Team 2 (trainer_2)").strip(),
                    json.dumps(t1_species, ensure_ascii=False),
                    json.dumps(t2_species, ensure_ascii=False),
                    (t1_paste or "").strip(),
                    (t2_paste or "").strip(),
                    preset_norm,
                    eng_ver,
                    global_v,
                    json.dumps(top_t1, ensure_ascii=False),
                    json.dumps(top_t2, ensure_ascii=False),
                    json.dumps(result_payload, ensure_ascii=False),
                    final_tags,
                    elapsed_s,
                    now,
                ],
            )
            cached_keys = self.list_cached_deep_audit_keys(m_hash)

        return {
            "run_id": run_id,
            "matchup_hash": m_hash,
            "t1_name": (t1_name or "Team 1 (trainer_1)").strip(),
            "t2_name": (t2_name or "Team 2 (trainer_2)").strip(),
            "t1_species": t1_species,
            "t2_species": t2_species,
            "preset": preset_norm,
            "engine_version": eng_ver,
            "global_nash_value": round(global_v, 4),
            "top_t1_bring": top_t1,
            "top_t2_threat": top_t2,
            "tags": final_tags,
            "elapsed_s": round(elapsed_s, 2),
            "created_at": now,
            "cached_deep_audit_keys": cached_keys,
        }

    def lookup_lead_lab_run(
        self,
        t1_paste: str,
        t2_paste: str,
        preset: str,
        engine_version: str = EQUITY_ENGINE_VERSION,
    ) -> Optional[Dict[str, Any]]:
        """Instant cache-hit lookup for `(t1_paste, t2_paste, preset)` (detecting outdated equity versions)."""
        preset_norm = str(preset or "balanced").strip().lower()
        eng_ver = str(engine_version or EQUITY_ENGINE_VERSION).strip()
        m_hash = compute_lead_lab_matchup_hash(t1_paste, t2_paste, preset_norm, engine_version=eng_ver)

        with self._db_lock:
            row = self.conn.execute(
                """
                SELECT run_id, matchup_hash, t1_name, t2_name, t1_species_json, t2_species_json,
                       preset, engine_version, global_nash_value, top_t1_bring_json, top_t2_threat_json,
                       tags, elapsed_s, created_at
                FROM lead_lab_runs
                WHERE matchup_hash = ?
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                [m_hash],
            ).fetchone()

            is_outdated = False
            if row is None:
                # Check if an older engine version saved this exact matchup + preset
                pair_key = _compute_paste_pair_key(t1_paste, t2_paste, preset_norm)
                candidates = self.conn.execute(
                    """
                    SELECT run_id, matchup_hash, t1_name, t2_name, t1_species_json, t2_species_json,
                           preset, engine_version, global_nash_value, top_t1_bring_json, top_t2_threat_json,
                           tags, elapsed_s, created_at, t1_paste, t2_paste
                    FROM lead_lab_runs
                    WHERE preset = ?
                    ORDER BY created_at DESC
                    LIMIT 120;
                    """,
                    [preset_norm],
                ).fetchall()
                for cand in candidates:
                    if _compute_paste_pair_key(str(cand[14]), str(cand[15]), preset_norm) == pair_key:
                        row = cand[:14]
                        is_outdated = str(cand[7]) != eng_ver
                        break

            if row is None:
                return None

            deep_keys = self.list_cached_deep_audit_keys(str(row[1]))
            return {
                "found": True,
                "run_id": str(row[0]),
                "matchup_hash": str(row[1]),
                "t1_name": str(row[2]),
                "t2_name": str(row[3]),
                "t1_species": json.loads(row[4]),
                "t2_species": json.loads(row[5]),
                "preset": str(row[6]),
                "engine_version": str(row[7]),
                "is_outdated": bool(is_outdated or str(row[7]) != eng_ver),
                "global_nash_value": round(float(row[8]), 4),
                "top_t1_bring": json.loads(row[9]),
                "top_t2_threat": json.loads(row[10]),
                "tags": str(row[11] or ""),
                "elapsed_s": round(float(row[12] or 0.0), 2),
                "created_at": str(row[13]),
                "cached_deep_audit_count": len(deep_keys),
            }

    def search_lead_lab_runs(
        self,
        q: str = "",
        t1_name: str = "",
        advantage: str = "",
        limit: int = 50,
        current_engine_version: str = EQUITY_ENGINE_VERSION,
    ) -> Dict[str, Any]:
        """Multi-facet search across saved Lead Lab matchups by species, team name, tags, and Nash advantage."""
        with self._db_lock:
            total_row = self.conn.execute("SELECT COUNT(*) FROM lead_lab_runs;").fetchone()
            total_count = int(total_row[0]) if total_row else 0
            t1_rows = self.conn.execute(
                "SELECT DISTINCT t1_name FROM lead_lab_runs ORDER BY t1_name ASC;"
            ).fetchall()
            t1_teams = [str(r[0]) for r in t1_rows if r and r[0]]

            clauses: List[str] = []
            params: List[Any] = []
            if (t1_name or "").strip():
                clauses.append("t1_name = ?")
                params.append(t1_name.strip())
            adv = str(advantage or "").strip().lower()
            if adv == "win":
                clauses.append("global_nash_value >= 0.08")
            elif adv == "even":
                clauses.append("ABS(global_nash_value) < 0.08")
            elif adv == "lose":
                clauses.append("global_nash_value <= -0.08")

            for tok in (q or "").strip().lower().split():
                clauses.append(
                    "LOWER(t1_name || ' ' || t2_name || ' ' || t1_species_json || ' ' || t2_species_json || ' ' || tags || ' ' || preset) LIKE ?"
                )
                params.append(f"%{tok}%")

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            lim = max(1, min(200, int(limit or 50)))
            rows = self.conn.execute(
                f"""
                SELECT run_id, matchup_hash, t1_name, t2_name, t1_species_json, t2_species_json,
                       preset, engine_version, global_nash_value, top_t1_bring_json, top_t2_threat_json,
                       tags, elapsed_s, created_at
                FROM lead_lab_runs
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                params + [lim],
            ).fetchall()

            deep_counts_rows = self.conn.execute(
                "SELECT matchup_hash, COUNT(*) FROM lead_lab_deep_audits GROUP BY matchup_hash;"
            ).fetchall()
            deep_counts = {str(r[0]): int(r[1]) for r in deep_counts_rows}

        runs: List[Dict[str, Any]] = []
        for r in rows:
            t1_sp = json.loads(r[4])
            t2_sp = json.loads(r[5])
            top1 = json.loads(r[9]) if r[9] else {}
            top2 = json.loads(r[10]) if r[10] else {}
            m_hash = str(r[1])
            eng_v = str(r[7])
            runs.append(
                {
                    "run_id": str(r[0]),
                    "matchup_hash": m_hash,
                    "t1_name": str(r[2]),
                    "t2_name": str(r[3]),
                    "t1_species": t1_sp,
                    "t2_species": t2_sp,
                    "t1_species_sprites": [
                        {"species": sp, "sprite_url": resolve_sprite_urls(sp)["sprite_url"]}
                        for sp in t1_sp
                    ],
                    "t2_species_sprites": [
                        {"species": sp, "sprite_url": resolve_sprite_urls(sp)["sprite_url"]}
                        for sp in t2_sp
                    ],
                    "preset": str(r[6]),
                    "engine_version": eng_v,
                    "is_outdated": eng_v != current_engine_version,
                    "global_nash_value": round(float(r[8]), 4),
                    "top_t1_bring": top1,
                    "top_t2_threat": top2,
                    "tags": str(r[11] or ""),
                    "elapsed_s": round(float(r[12] or 0.0), 2),
                    "created_at": str(r[13]),
                    "cached_deep_audit_count": deep_counts.get(m_hash, 0),
                }
            )

        return {
            "runs": runs,
            "total_count": total_count,
            "matched_count": len(runs),
            "t1_teams": t1_teams,
            "current_engine_version": current_engine_version,
        }

    def load_lead_lab_run(
        self,
        run_id: str,
        current_engine_version: str = EQUITY_ENGINE_VERSION,
    ) -> Optional[Dict[str, Any]]:
        """Load the complete saved `90x90` Lead Lab payload, pastes, and cached deep-audit keys."""
        clean_id = (run_id or "").strip()
        if not clean_id:
            return None
        with self._db_lock:
            row = self.conn.execute(
                """
                SELECT run_id, matchup_hash, t1_name, t2_name, t1_species_json, t2_species_json,
                       t1_paste, t2_paste, preset, engine_version, global_nash_value,
                       payload_json, tags, elapsed_s, created_at
                FROM lead_lab_runs
                WHERE run_id = ?;
                """,
                [clean_id],
            ).fetchone()
            if row is None:
                return None
            m_hash = str(row[1])
            cached_keys = self.list_cached_deep_audit_keys(m_hash)

        payload = json.loads(row[11])
        eng_v = str(row[9])
        return {
            "run_id": str(row[0]),
            "matchup_hash": m_hash,
            "t1_name": str(row[2]),
            "t2_name": str(row[3]),
            "t1_species": json.loads(row[4]),
            "t2_species": json.loads(row[5]),
            "t1_paste": str(row[6]),
            "t2_paste": str(row[7]),
            "preset": str(row[8]),
            "engine_version": eng_v,
            "is_outdated": eng_v != current_engine_version,
            "global_nash_value": round(float(row[10]), 4),
            "payload": payload,
            "tags": str(row[12] or ""),
            "elapsed_s": round(float(row[13] or 0.0), 2),
            "created_at": str(row[14]),
            "cached_deep_audit_keys": cached_keys,
        }

    def update_lead_lab_tags(self, run_id: str, tags: str) -> bool:
        """Update user tags/notes on a saved Lead Lab matchup run."""
        clean_id = (run_id or "").strip()
        if not clean_id:
            return False
        with self._db_lock:
            exists = self.conn.execute(
                "SELECT 1 FROM lead_lab_runs WHERE run_id = ?;",
                [clean_id],
            ).fetchone()
            if not exists:
                return False
            self.conn.execute(
                "UPDATE lead_lab_runs SET tags = ? WHERE run_id = ?;",
                [str(tags or "").strip()[:240], clean_id],
            )
            return True

    def delete_lead_lab_run(self, run_id: str) -> bool:
        """Delete a saved Lead Lab matchup run and all associated cached deep audits."""
        clean_id = (run_id or "").strip()
        if not clean_id:
            return False
        with self._db_lock:
            row = self.conn.execute(
                "SELECT matchup_hash FROM lead_lab_runs WHERE run_id = ?;",
                [clean_id],
            ).fetchone()
            if not row:
                return False
            m_hash = str(row[0])
            self.conn.execute("DELETE FROM lead_lab_runs WHERE run_id = ?;", [clean_id])
            self.conn.execute("DELETE FROM lead_lab_deep_audits WHERE matchup_hash = ?;", [m_hash])
            return True

    def get_cached_deep_audit(
        self,
        matchup_hash: str,
        t1_mode_key: str,
        t2_mode_key: str,
        engine_version: str = EQUITY_ENGINE_VERSION,
        expected_lead_1: Optional[Sequence[str]] = None,
        expected_bench_1: Optional[Sequence[str]] = None,
        expected_lead_2: Optional[Sequence[str]] = None,
        expected_bench_2: Optional[Sequence[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a cached `K=128` deep Turn-1 audit validated against expected species identity."""
        audit_key = f"{matchup_hash}:{t1_mode_key}:{t2_mode_key}"
        with self._db_lock:
            row = self.conn.execute(
                """
                SELECT payload_json, created_at
                FROM lead_lab_deep_audits
                WHERE audit_key = ? AND engine_version = ?;
                """,
                [audit_key, str(engine_version or EQUITY_ENGINE_VERSION).strip()],
            ).fetchone()
            if not row:
                return None
            payload = json.loads(row[0])
            # Strict species-identity guard: never serve a cached deep audit for mismatched Pokémon!
            if expected_lead_1:
                m1_saved = payload.get("mode_1") or {}
                if (
                    canonical_mode_key(m1_saved.get("lead_species") or [], m1_saved.get("bench_species") or [])
                    != canonical_mode_key(expected_lead_1, expected_bench_1 or [])
                ):
                    return None
            if expected_lead_2:
                m2_saved = payload.get("mode_2") or {}
                if (
                    canonical_mode_key(m2_saved.get("lead_species") or [], m2_saved.get("bench_species") or [])
                    != canonical_mode_key(expected_lead_2, expected_bench_2 or [])
                ):
                    return None
            payload["from_vault_cache"] = True
            payload["cached_at"] = str(row[1])
            payload["audit_cell_key"] = f"{t1_mode_key}__{t2_mode_key}"
            return payload

    def save_cached_deep_audit(
        self,
        matchup_hash: str,
        t1_mode_key: str,
        t2_mode_key: str,
        payload: Dict[str, Any],
        engine_version: str = EQUITY_ENGINE_VERSION,
    ) -> str:
        """Cache a computed `K=128` deep Turn-1 audit in DuckDB `lead_lab_deep_audits`."""
        audit_key = f"{matchup_hash}:{t1_mode_key}:{t2_mode_key}"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._db_lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO lead_lab_deep_audits (
                    audit_key, matchup_hash, t1_mode_key, t2_mode_key,
                    engine_version, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                [
                    audit_key,
                    str(matchup_hash),
                    str(t1_mode_key),
                    str(t2_mode_key),
                    str(engine_version or EQUITY_ENGINE_VERSION).strip(),
                    json.dumps(payload, ensure_ascii=False),
                    now,
                ],
            )
        return f"{t1_mode_key}__{t2_mode_key}"

    def list_cached_deep_audit_keys(self, matchup_hash: str) -> List[str]:
        """Return list of `'<t1_mode_key>__<t2_mode_key>'` keys cached for `matchup_hash`."""
        if not matchup_hash:
            return []
        with self._db_lock:
            rows = self.conn.execute(
                """
                SELECT t1_mode_key, t2_mode_key
                FROM lead_lab_deep_audits
                WHERE matchup_hash = ?;
                """,
                [str(matchup_hash)],
            ).fetchall()
        return [f"{str(r[0])}__{str(r[1])}" for r in rows]
