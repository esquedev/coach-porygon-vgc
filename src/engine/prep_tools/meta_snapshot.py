# -*- coding: utf-8 -*-
"""Zero-AI Regulation M-C Meta Snapshot & Sprite Base64 Registry.

Queries in-memory DuckDB (`VGCDataRegistry`) for regional tournament usage,
nature distributions, legal Reg M-C items (Focus Sash, Sitrus Berry, Resist
Berries, Terrain Seeds, Choice Scarf, Mega Stones), and exact Pokémon Champions
Level 50 stat formulas (mandatory 31 IVs, <= 66 SP, <= 32 SP per stat).

Strictly pure domain logic with zero HTTP/UI server dependencies.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from engine.db_registry import get_registry

REPO_ROOT = Path(__file__).resolve().parents[3]
SLUG_MAP_PATH = REPO_ROOT / "assets" / "slug_map.json"

# Regulation M-C speed-doubling abilities (all verified in Champions pokedex/abilities)
SPEED_DOUBLER_ABILITIES: Tuple[str, ...] = (
    "Chlorophyll",
    "Swift Swim",
    "Sand Rush",
    "Slush Rush",
    "Surge Surfer",
    "Unburden",
)

# Terrain Seeds legal in Regulation M-C -> (trigger_terrain, boosted_stat)
TERRAIN_SEED_EFFECTS: Dict[str, Tuple[str, str]] = {
    "Grassy Seed": ("grassy", "def"),
    "Electric Seed": ("electric", "def"),
    "Psychic Seed": ("psychic", "spd"),
    "Misty Seed": ("misty", "spd"),
}

# Nature stat modifiers: nature_name -> (boosted_stat, lowered_stat)
NATURE_MODS: Dict[str, Tuple[str, str]] = {
    "Lonely": ("atk", "def"),
    "Brave": ("atk", "spe"),
    "Adamant": ("atk", "spa"),
    "Naughty": ("atk", "spd"),
    "Bold": ("def", "atk"),
    "Relaxed": ("def", "spe"),
    "Impish": ("def", "spa"),
    "Lax": ("def", "spd"),
    "Timid": ("spe", "atk"),
    "Hasty": ("spe", "def"),
    "Jolly": ("spe", "spa"),
    "Naive": ("spe", "spd"),
    "Modest": ("spa", "atk"),
    "Mild": ("spa", "def"),
    "Quiet": ("spa", "spe"),
    "Rash": ("spa", "spd"),
    "Calm": ("spd", "atk"),
    "Gentle": ("spd", "def"),
    "Sassy": ("spd", "spe"),
    "Careful": ("spd", "spa"),
}

PLUS_SPE_NATURES: Set[str] = {"Timid", "Hasty", "Jolly", "Naive", "Naïve"}
MINUS_SPE_NATURES: Set[str] = {"Brave", "Relaxed", "Quiet", "Sassy"}
PLUS_DEF_NATURES: Set[str] = {"Bold", "Relaxed", "Impish", "Lax"}
PLUS_SPD_NATURES: Set[str] = {"Calm", "Gentle", "Sassy", "Careful"}

# Type-halving Resist Berries (types are still verified from DuckDB items.naturalGift)
RESIST_BERRY_NAMES: Set[str] = {
    "Occa Berry",
    "Passho Berry",
    "Wacan Berry",
    "Rindo Berry",
    "Yache Berry",
    "Chople Berry",
    "Kebia Berry",
    "Shuca Berry",
    "Coba Berry",
    "Payapa Berry",
    "Tanga Berry",
    "Charti Berry",
    "Kasib Berry",
    "Haban Berry",
    "Colbur Berry",
    "Babiri Berry",
    "Chilan Berry",
    "Roseli Berry",
}

# Fallback tiny 1x1 transparent PNG data URI (zero broken <img> tags offline)
FALLBACK_SPRITE_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

# 7 strictly legal Regulation M-C defender bulk profiles (all <= 66 SP, <= 32 single stat, 31 IVs)
BULK_PROFILE_SPECS: Tuple[Tuple[str, str, int, int, int, str], ...] = (
    ("min0", "Min Bulk (0 HP / 0 Def / 0 SpD)", 0, 0, 0, "Serious"),
    ("hp32", "HP Invested (32 HP / 0 Def / 0 SpD)", 32, 0, 0, "Serious"),
    ("bal", "Balanced (32 HP / 18 Def / 16 SpD)", 32, 18, 16, "Serious"),
    ("balDef", "+Def Bulky (32 HP / 18+ Def / 16 SpD)", 32, 18, 16, "Bold"),
    ("balSpd", "+SpD Bulky (32 HP / 18 Def / 16+ SpD)", 32, 18, 16, "Calm"),
    ("maxDef", "Max +Def (32 HP / 32+ Def / 2 SpD)", 32, 32, 2, "Bold"),
    ("maxSpd", "Max +SpD (32 HP / 2 Def / 32+ SpD)", 32, 2, 32, "Calm"),
)


def calc_champions_hp(base_hp: int, sp: int = 0) -> int:
    """Compute exact Regulation M-C Level 50 HP (mandatory 31 IV, 0 <= SP <= 32)."""
    clamped_sp = max(0, min(32, int(sp)))
    if int(base_hp) == 1:
        return 1
    return int(base_hp) + clamped_sp + 75


def calc_champions_stat(base_val: int, sp: int = 0, nature_mult: float = 1.0) -> int:
    """Compute exact Regulation M-C Level 50 non-HP stat (mandatory 31 IV, 0 <= SP <= 32)."""
    clamped_sp = max(0, min(32, int(sp)))
    return int(math.floor((int(base_val) + clamped_sp + 20) * float(nature_mult)))


def get_nature_multiplier(nature_name: Optional[str], stat_key: str) -> float:
    """Return 1.1, 0.9, or 1.0 for a Pokémon nature and stat key."""
    clean = (nature_name or "Serious").replace("ï", "i").strip()
    pair = NATURE_MODS.get(clean)
    if not pair:
        return 1.0
    if pair[0] == stat_key:
        return 1.1
    if pair[1] == stat_key:
        return 0.9
    return 1.0


def calc_all_champions_stats(
    base_stats: Dict[str, int],
    sp_map: Dict[str, int],
    nature: str = "Serious",
) -> Dict[str, int]:
    """Compute all six Level 50 Champions stats under mandatory 31 IVs."""
    return {
        "hp": calc_champions_hp(base_stats["hp"], sp_map.get("hp", 0)),
        "atk": calc_champions_stat(
            base_stats["atk"], sp_map.get("atk", 0), get_nature_multiplier(nature, "atk")
        ),
        "def": calc_champions_stat(
            base_stats["def"], sp_map.get("def", sp_map.get("def_", 0)), get_nature_multiplier(nature, "def")
        ),
        "spa": calc_champions_stat(
            base_stats["spa"], sp_map.get("spa", 0), get_nature_multiplier(nature, "spa")
        ),
        "spd": calc_champions_stat(
            base_stats["spd"], sp_map.get("spd", 0), get_nature_multiplier(nature, "spd")
        ),
        "spe": calc_champions_stat(
            base_stats["spe"], sp_map.get("spe", 0), get_nature_multiplier(nature, "spe")
        ),
    }


def _norm_key(text: str) -> str:
    """Normalize a Pokémon/item name to lowercase alphanumeric characters."""
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


@dataclass(frozen=True)
class DefenderBulkProfile:
    """One strictly legal Regulation M-C defensive spread (`sum(SP) <= 66`, 31 IVs)."""

    key: str
    label: str
    hp_sp: int
    def_sp: int
    spd_sp: int
    nature: str
    hp: int
    def_stat: int
    spd_stat: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON embedding inside portable HTML reports."""
        return {
            "key": self.key,
            "label": self.label,
            "hpSp": self.hp_sp,
            "defSp": self.def_sp,
            "spdSp": self.spd_sp,
            "nature": self.nature,
            "hp": self.hp,
            "def": self.def_stat,
            "spd": self.spd_stat,
        }


@dataclass(frozen=True)
class MetaPokemonEntry:
    """Aggregated regional tournament entry from DuckDB for Speed Tiers & Damage Matrix."""

    rank: int
    species: str
    usage_pct: float
    count: int
    top32_count: int
    base_stats: Dict[str, int]
    types: Tuple[str, ...]
    sprite_key: str
    top_ability: str
    top_ability_pct: float
    has_bulletproof_alt: bool
    bulletproof_pct: float
    plus_spe_pct: float
    neu_spe_pct: float
    minus_spe_pct: float
    has_plus_spe: bool
    has_neu_spe: bool
    has_minus_spe: bool
    scarf_pct: float
    has_scarf: bool
    doubler_ability: Optional[str]
    doubler_pct: float
    top_natures: Tuple[Dict[str, Any], ...]
    top_items: Tuple[Dict[str, Any], ...]
    top_item: Optional[str]
    top_item_pct: float
    default_item: Optional[str]
    sitrus_pct: float
    sash_pct: float
    resist_berry: Optional[str]
    resist_berry_type: Optional[str]
    resist_berry_pct: float
    terrain_seed: Optional[str]
    terrain_seed_terrain: Optional[str]
    terrain_seed_stat: Optional[str]
    terrain_seed_pct: float
    speeds: Dict[str, int]
    meta_bulk_key: str
    profiles: Dict[str, DefenderBulkProfile] = field(default_factory=dict)


@dataclass(frozen=True)
class TopNMetaSnapshot:
    """Deterministic Regulation M-C regional meta snapshot extracted from DuckDB."""

    total_teams: int
    top_n: int
    entries: Tuple[MetaPokemonEntry, ...]


_SNAPSHOT_CACHE_LOCK = threading.Lock()
_SNAPSHOT_CACHE: Dict[int, TopNMetaSnapshot] = {}
_SLUG_MAP_CACHE: Optional[Dict[str, Dict[str, str]]] = None
_BASE64_SPRITE_CACHE: Dict[str, str] = {}


def load_slug_map() -> Dict[str, Dict[str, str]]:
    """Load and cache `assets/slug_map.json` for deterministic local sprite lookup."""
    global _SLUG_MAP_CACHE
    if _SLUG_MAP_CACHE is not None:
        return _SLUG_MAP_CACHE
    species_map: Dict[str, str] = {}
    items_map: Dict[str, str] = {}
    if SLUG_MAP_PATH.is_file():
        raw = json.loads(SLUG_MAP_PATH.read_text(encoding="utf-8"))
        for k, rel in (raw.get("species") or {}).items():
            species_map[str(k)] = str(rel)
            species_map[_norm_key(str(k))] = str(rel)
        for k, rel in (raw.get("items") or {}).items():
            items_map[str(k)] = str(rel)
            items_map[_norm_key(str(k))] = str(rel)
    _SLUG_MAP_CACHE = {"species": species_map, "items": items_map}
    return _SLUG_MAP_CACHE


def load_sprite_base64(species_name: str) -> str:
    """Resolve a Pokémon's local PNG via `assets/slug_map.json` and return a Base64 data URI."""
    key = (species_name or "").strip()
    if key in _BASE64_SPRITE_CACHE:
        return _BASE64_SPRITE_CACHE[key]

    smap = load_slug_map()["species"]
    rel = smap.get(key) or smap.get(_norm_key(key))
    if not rel and "-Mega" in key:
        base_only = key.split("-Mega")[0]
        rel = smap.get(base_only) or smap.get(_norm_key(base_only))

    if rel:
        img_path = REPO_ROOT / rel.lstrip("/")
        if img_path.is_file():
            encoded = base64.b64encode(img_path.read_bytes()).decode("ascii")
            uri = f"data:image/png;base64,{encoded}"
            _BASE64_SPRITE_CACHE[key] = uri
            return uri

    _BASE64_SPRITE_CACHE[key] = FALLBACK_SPRITE_DATA_URI
    return FALLBACK_SPRITE_DATA_URI


def load_sprites_dict(species_names: Sequence[str]) -> Dict[str, str]:
    """Build a deduplicated `{species_name: data_uri}` mapping for offline HTML embedding."""
    out: Dict[str, str] = {}
    for name in species_names:
        clean = (name or "").strip()
        if clean and clean not in out:
            out[clean] = load_sprite_base64(clean)
    return out


def query_pokedex_entry(species_name: str) -> Optional[Dict[str, Any]]:
    """Fetch exact base stats, types, abilities, and requiredItem from DuckDB `pokedex`."""
    reg = get_registry()
    clean = (species_name or "").replace("\u2019", "'").strip()
    rows = reg.query(
        """
        SELECT name, baseSpecies, forme, requiredItem, types, abilities,
               hp, atk, def, spa, spd, spe
        FROM pokedex
        WHERE LOWER(name) = LOWER(?)
        LIMIT 1
        """,
        [clean],
    )
    if not rows:
        norm = _norm_key(clean)
        rows = reg.query(
            """
            SELECT name, baseSpecies, forme, requiredItem, types, abilities,
                   hp, atk, def, spa, spd, spe
            FROM pokedex
            WHERE LOWER(id) = ?
            LIMIT 1
            """,
            [norm],
        )
    if not rows:
        return None
    row = rows[0]
    types_raw = row.get("types") or []
    abilities_raw = row.get("abilities") or {}
    abilities_list: List[str] = []
    if isinstance(abilities_raw, dict):
        for slot_k in ("0", "1", "H", "S"):
            val = abilities_raw.get(slot_k)
            if val:
                abilities_list.append(str(val))
    elif isinstance(abilities_raw, (list, tuple)):
        abilities_list = [str(v) for v in abilities_raw if v]
    return {
        "name": str(row["name"]),
        "baseSpecies": str(row.get("baseSpecies") or row["name"]),
        "forme": row.get("forme"),
        "requiredItem": row.get("requiredItem"),
        "types": [str(t) for t in types_raw],
        "abilities": abilities_list,
        "baseStats": {
            "hp": int(row["hp"]),
            "atk": int(row["atk"]),
            "def": int(row["def"]),
            "spa": int(row["spa"]),
            "spd": int(row["spd"]),
            "spe": int(row["spe"]),
        },
    }


def resolve_mega_form_for_item(base_species: str, item_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Resolve the exact Champions Mega / Z-Mega form for a Pokémon holding `item_name` via DuckDB."""
    if not item_name or item_name.lower() == "none":
        return None
    reg = get_registry()
    rows = reg.query(
        """
        SELECT name, baseSpecies, forme, requiredItem, types, abilities,
               hp, atk, def, spa, spd, spe
        FROM pokedex
        WHERE LOWER(requiredItem) = LOWER(?)
        LIMIT 5
        """,
        [item_name.strip()],
    )
    if not rows:
        return None
    norm_base = _norm_key(base_species)
    chosen = rows[0]
    for r in rows:
        cand_base = _norm_key(str(r.get("baseSpecies") or r.get("name") or ""))
        if cand_base == norm_base or norm_base.startswith(cand_base):
            chosen = r
            break
    # Verify species actually matches this Mega Stone (prevent e.g. Pikachu holding Charizardite Y)
    chosen_base = _norm_key(str(chosen.get("baseSpecies") or ""))
    if chosen_base and chosen_base != norm_base and not norm_base.startswith(chosen_base):
        return None
    return query_pokedex_entry(str(chosen["name"]))


def _load_resist_berry_type_map() -> Dict[str, str]:
    """Query DuckDB `items` for exact Resist Berry -> halved move type mappings."""
    reg = get_registry()
    rows = reg.query(
        "SELECT name, naturalGift FROM items WHERE isBerry = true;"
    )
    out: Dict[str, str] = {}
    for row in rows:
        name = str(row.get("name") or "")
        if name in RESIST_BERRY_NAMES:
            ng = row.get("naturalGift")
            if isinstance(ng, dict) and ng.get("type"):
                out[name] = str(ng["type"])
    return out


def _choose_meta_bulk_key(
    base_stats: Dict[str, int],
    plus_def_pct: float,
    plus_spd_pct: float,
    plus_spe_pct: float,
    sash_pct: float,
    sitrus_pct: float,
) -> str:
    """Infer a grounded Regulation M-C default bulk profile from DuckDB nature & item stats."""
    if plus_def_pct >= 30.0 and plus_def_pct >= plus_spd_pct:
        return "balDef"
    if plus_spd_pct >= 30.0:
        return "balSpd"
    if sash_pct >= 35.0:
        return "min0"
    if plus_spe_pct >= 35.0 and base_stats["spe"] >= 95:
        return "min0"
    if sitrus_pct >= 30.0 or (plus_def_pct + plus_spd_pct) >= 25.0:
        return "bal"
    if base_stats["spe"] >= 115 and base_stats["hp"] <= 95:
        return "min0"
    return "hp32"


def _build_legal_bulk_profiles(base_stats: Dict[str, int]) -> Dict[str, DefenderBulkProfile]:
    """Construct all 7 strictly legal Regulation M-C bulk profiles (`<= 66 SP`, 31 IVs)."""
    profiles: Dict[str, DefenderBulkProfile] = {}
    for key, label, hp_sp, def_sp, spd_sp, nature in BULK_PROFILE_SPECS:
        assert hp_sp + def_sp + spd_sp <= 66, f"Illegal SP budget in {key}"
        assert 0 <= hp_sp <= 32 and 0 <= def_sp <= 32 and 0 <= spd_sp <= 32
        hp_val = calc_champions_hp(base_stats["hp"], hp_sp)
        def_val = calc_champions_stat(
            base_stats["def"], def_sp, get_nature_multiplier(nature, "def")
        )
        spd_val = calc_champions_stat(
            base_stats["spd"], spd_sp, get_nature_multiplier(nature, "spd")
        )
        profiles[key] = DefenderBulkProfile(
            key=key,
            label=label,
            hp_sp=hp_sp,
            def_sp=def_sp,
            spd_sp=spd_sp,
            nature=nature,
            hp=hp_val,
            def_stat=def_val,
            spd_stat=spd_val,
        )
    return profiles


def get_top_n_meta_snapshot(top_n: int = 50) -> TopNMetaSnapshot:
    """Query DuckDB for the Top-N Regulation M-C regional meta snapshot (cached in-memory)."""
    clamped_n = max(1, min(100, int(top_n)))
    with _SNAPSHOT_CACHE_LOCK:
        if clamped_n in _SNAPSHOT_CACHE:
            return _SNAPSHOT_CACHE[clamped_n]

    reg = get_registry()
    total_row = reg.query("SELECT COUNT(*) AS cnt FROM tournament_standings;")
    total_teams = int(total_row[0]["cnt"]) if total_row else 0

    legal_items_rows = reg.query("SELECT name FROM items;")
    legal_item_names: Set[str] = {str(r["name"]) for r in legal_items_rows if r.get("name")}
    resist_berry_types = _load_resist_berry_type_map()

    top_species_rows = reg.query(
        """
        SELECT species,
               COUNT(*) AS cnt,
               SUM(CASE WHEN placement <= 32 THEN 1 ELSE 0 END) AS t32
        FROM tournament_team_slots
        GROUP BY species
        ORDER BY cnt DESC, species ASC
        LIMIT ?
        """,
        [clamped_n],
    )

    species_list = [str(r["species"]) for r in top_species_rows]
    if not species_list:
        snap = TopNMetaSnapshot(total_teams=total_teams, top_n=clamped_n, entries=())
        with _SNAPSHOT_CACHE_LOCK:
            _SNAPSHOT_CACHE[clamped_n] = snap
        return snap

    placeholders = ",".join("?" for _ in species_list)

    # Aggregate natures, items, abilities in 3 clean grouped SQL queries
    nature_rows = reg.query(
        f"""
        SELECT species, nature, COUNT(*) AS cnt
        FROM tournament_team_slots
        WHERE species IN ({placeholders}) AND nature IS NOT NULL AND nature != ''
        GROUP BY species, nature
        ORDER BY species, cnt DESC
        """,
        species_list,
    )
    item_rows = reg.query(
        f"""
        SELECT species, item, COUNT(*) AS cnt
        FROM tournament_team_slots
        WHERE species IN ({placeholders}) AND item IS NOT NULL AND item != ''
        GROUP BY species, item
        ORDER BY species, cnt DESC
        """,
        species_list,
    )
    ability_rows = reg.query(
        f"""
        SELECT species, ability, COUNT(*) AS cnt
        FROM tournament_team_slots
        WHERE species IN ({placeholders}) AND ability IS NOT NULL AND ability != ''
        GROUP BY species, ability
        ORDER BY species, cnt DESC
        """,
        species_list,
    )

    natures_by_sp: Dict[str, List[Tuple[str, int]]] = {}
    for r in nature_rows:
        natures_by_sp.setdefault(str(r["species"]), []).append((str(r["nature"]), int(r["cnt"])))

    items_by_sp: Dict[str, List[Tuple[str, int]]] = {}
    for r in item_rows:
        it = str(r["item"])
        # Strict Anti-Hallucination filter: only items present in DuckDB Reg M-C items catalog
        if it in legal_item_names:
            items_by_sp.setdefault(str(r["species"]), []).append((it, int(r["cnt"])))

    abilities_by_sp: Dict[str, List[Tuple[str, int]]] = {}
    for r in ability_rows:
        abilities_by_sp.setdefault(str(r["species"]), []).append((str(r["ability"]), int(r["cnt"])))

    entries: List[MetaPokemonEntry] = []
    for rank_idx, sp_row in enumerate(top_species_rows, 1):
        species = str(sp_row["species"])
        cnt = int(sp_row["cnt"])
        t32 = int(sp_row["t32"] or 0)
        usage_pct = round((cnt / total_teams) * 100.0, 2) if total_teams > 0 else 0.0

        dex = query_pokedex_entry(species)
        if dex is None:
            continue
        base_stats = dex["baseStats"]
        types_tup = tuple(dex["types"])

        # Natures breakdown
        nat_list = natures_by_sp.get(species, [])
        nat_total = sum(c for _, c in nat_list) or 1
        plus_spe_c = sum(c for n, c in nat_list if n in PLUS_SPE_NATURES)
        minus_spe_c = sum(c for n, c in nat_list if n in MINUS_SPE_NATURES)
        neu_spe_c = nat_total - plus_spe_c - minus_spe_c
        plus_def_c = sum(c for n, c in nat_list if n in PLUS_DEF_NATURES)
        plus_spd_c = sum(c for n, c in nat_list if n in PLUS_SPD_NATURES)

        plus_spe_pct = round(plus_spe_c * 100.0 / nat_total, 1)
        neu_spe_pct = round(neu_spe_c * 100.0 / nat_total, 1)
        minus_spe_pct = round(minus_spe_c * 100.0 / nat_total, 1)
        plus_def_pct = round(plus_def_c * 100.0 / nat_total, 1)
        plus_spd_pct = round(plus_spd_c * 100.0 / nat_total, 1)

        top_natures = tuple(
            {"name": n.replace("Naïve", "Naive"), "pct": round(c * 100.0 / nat_total, 1)}
            for n, c in nat_list[:4]
        )

        # Abilities breakdown
        ab_list = abilities_by_sp.get(species, [])
        ab_total = sum(c for _, c in ab_list) or 1
        if ab_list:
            top_ab, top_ab_c = ab_list[0]
            top_ab_pct = round(top_ab_c * 100.0 / ab_total, 1)
        else:
            top_ab = dex["abilities"][0] if dex["abilities"] else "None"
            top_ab_pct = 100.0

        bp_c = sum(c for a, c in ab_list if a == "Bulletproof")
        bp_pct = round(bp_c * 100.0 / ab_total, 1)
        has_bp_alt = bp_pct >= 3.0 and top_ab != "Bulletproof"

        doubler_ab: Optional[str] = None
        doubler_pct = 0.0
        for a, c in ab_list:
            if a in SPEED_DOUBLER_ABILITIES:
                pct_val = round(c * 100.0 / ab_total, 1)
                if pct_val >= 5.0:
                    doubler_ab = a
                    doubler_pct = pct_val
                    break

        # Legal Reg M-C Items breakdown
        it_list = items_by_sp.get(species, [])
        it_total = sum(c for _, c in it_list) or 1
        top_items = tuple(
            {"name": it, "pct": round(c * 100.0 / it_total, 1)}
            for it, c in it_list[:4]
        )
        top_item = it_list[0][0] if it_list else None
        top_item_pct = round(it_list[0][1] * 100.0 / it_total, 1) if it_list else 0.0

        scarf_pct = round(sum(c for it, c in it_list if it == "Choice Scarf") * 100.0 / it_total, 1)
        sitrus_pct = round(sum(c for it, c in it_list if it == "Sitrus Berry") * 100.0 / it_total, 1)
        sash_pct = round(sum(c for it, c in it_list if it == "Focus Sash") * 100.0 / it_total, 1)

        resist_berry: Optional[str] = None
        resist_berry_type: Optional[str] = None
        resist_berry_pct = 0.0
        for it, c in it_list:
            if it in resist_berry_types:
                pct_val = round(c * 100.0 / it_total, 1)
                if pct_val >= 5.0:
                    resist_berry = it
                    resist_berry_type = resist_berry_types[it]
                    resist_berry_pct = pct_val
                    break

        terrain_seed: Optional[str] = None
        terrain_seed_terrain: Optional[str] = None
        terrain_seed_stat: Optional[str] = None
        terrain_seed_pct = 0.0
        for it, c in it_list:
            if it in TERRAIN_SEED_EFFECTS:
                pct_val = round(c * 100.0 / it_total, 1)
                if pct_val >= 5.0:
                    terrain_seed = it
                    terrain_seed_terrain, terrain_seed_stat = TERRAIN_SEED_EFFECTS[it]
                    terrain_seed_pct = pct_val
                    break

        # Choose most tactically impactful default simulated item (strictly Reg M-C legal)
        default_item = top_item
        if default_item not in (
            "Sitrus Berry",
            "Focus Sash",
            resist_berry,
            terrain_seed,
        ):
            if sitrus_pct >= 25.0:
                default_item = "Sitrus Berry"
            elif sash_pct >= 25.0:
                default_item = "Focus Sash"
            elif resist_berry and resist_berry_pct >= 20.0:
                default_item = resist_berry
            elif terrain_seed and terrain_seed_pct >= 20.0:
                default_item = terrain_seed

        # Exact Champions Level 50 speed brackets (mandatory 31 IVs!)
        b_spe = base_stats["spe"]
        speeds = {
            "minus0": calc_champions_stat(b_spe, 0, 0.9),
            "neu0": calc_champions_stat(b_spe, 0, 1.0),
            "neu32": calc_champions_stat(b_spe, 32, 1.0),
            "plus32": calc_champions_stat(b_spe, 32, 1.1),
        }

        profiles = _build_legal_bulk_profiles(base_stats)
        meta_bulk_key = _choose_meta_bulk_key(
            base_stats=base_stats,
            plus_def_pct=plus_def_pct,
            plus_spd_pct=plus_spd_pct,
            plus_spe_pct=plus_spe_pct,
            sash_pct=sash_pct,
            sitrus_pct=sitrus_pct,
        )

        entries.append(
            MetaPokemonEntry(
                rank=rank_idx,
                species=dex["name"],
                usage_pct=usage_pct,
                count=cnt,
                top32_count=t32,
                base_stats=base_stats,
                types=types_tup,
                sprite_key=dex["name"],
                top_ability=top_ab,
                top_ability_pct=top_ab_pct,
                has_bulletproof_alt=has_bp_alt,
                bulletproof_pct=bp_pct,
                plus_spe_pct=plus_spe_pct,
                neu_spe_pct=neu_spe_pct,
                minus_spe_pct=minus_spe_pct,
                has_plus_spe=plus_spe_pct >= 4.0,
                has_neu_spe=neu_spe_pct >= 4.0,
                has_minus_spe=minus_spe_pct >= 4.0,
                scarf_pct=scarf_pct,
                has_scarf=scarf_pct >= 8.0,
                doubler_ability=doubler_ab,
                doubler_pct=doubler_pct,
                top_natures=top_natures,
                top_items=top_items,
                top_item=top_item,
                top_item_pct=top_item_pct,
                default_item=default_item,
                sitrus_pct=sitrus_pct,
                sash_pct=sash_pct,
                resist_berry=resist_berry,
                resist_berry_type=resist_berry_type,
                resist_berry_pct=resist_berry_pct,
                terrain_seed=terrain_seed,
                terrain_seed_terrain=terrain_seed_terrain,
                terrain_seed_stat=terrain_seed_stat,
                terrain_seed_pct=terrain_seed_pct,
                speeds=speeds,
                meta_bulk_key=meta_bulk_key,
                profiles=profiles,
            )
        )

    snap = TopNMetaSnapshot(total_teams=total_teams, top_n=clamped_n, entries=tuple(entries))
    with _SNAPSHOT_CACHE_LOCK:
        _SNAPSHOT_CACHE[clamped_n] = snap
    return snap
