#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Flask Web Backend & API Server (Regulation M-C)
Serves the bilingual (EN / ES) Command Center and exposes live endpoints:
- GET  /                           : Redirects to /assets/command_center.html (or /es)
- GET  /es                         : Redirects to /assets/command_center_es.html
- GET  /en                         : Redirects to /assets/command_center_en.html
- GET  /assets/<path:filename>     : Sandboxed static asset delivery (SEC-03 protected)
- GET  /api/sprites/<path:species> : Dynamic sprite resolver for Pokémon Regulation M-C
- GET  /api/items/<path:item>      : Dynamic item & megastone resolver
- GET  /api/health                 : Health check status
- GET  /api/telemetry              : Live workspace database (matches, calcs, teams, Pokédex, MunchStats)
- GET  /api/munchstats/data        : Structured MunchStats metagame datasets
- POST /api/munchstats/crawl       : Processes natural-language prompt or URL, dumps verified records
- POST /api/sync                   : Re-reads CSVs and updates live_telemetry.json
- POST /api/telemetry/ingest       : Thread-safe match telemetry ingestion (5 MB DoS cap)
- POST /api/scouted/ingest         : Ingests verified scouted OTS teams
- GET  /api/status                 : System & GPU/CUDA hardware status
- POST /api/audit                  : Game-Theoretic All-Turns & Turning Point replay audit
- POST /api/gpu-matrix             : GPU Payoff Matrix, Nash equilibrium & Uncertainty profile
- GET  /api/report/<audit_id>      : Print-ready HTML tactical report for an audit ID
- POST /api/benchmark              : PyTorch GPU/CPU throughput & latency benchmark
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import socketserver
import sys
import urllib.parse
from typing import Any, Dict, Optional

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    make_response,
    redirect,
    request,
    send_file,
    send_from_directory,
)
from werkzeug.security import safe_join

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine"))

from ui_generator import load_live_telemetry

try:
    from munchstats_scraper import SCOUTED_CSV, scrape_munchstats_url_or_json
except ImportError:
    SCOUTED_CSV = REPO_ROOT / "data" / "Scouted_Teams.csv"

    def scrape_munchstats_url_or_json(url, save_to_csv=True):
        """Fallback mock for MunchStats live scraper when module is offline."""
        return [{"warning": "MunchStats live scraper offline; falling back to local Scouted_Teams.csv."}]

PORT = 8000
DEFAULT_HOST = "127.0.0.1"
MAX_POST_BODY_BYTES = 5 * 1024 * 1024  # 5 MB cap against memory exhaustion (CWE-400 / SEC-06)
ASSETS_DIR = REPO_ROOT / "assets"
SPRITES_REG_MC_DIR = ASSETS_DIR / "sprites" / "Reg_M-C"
SPRITES_ROOT_DIR = ASSETS_DIR / "sprites"
ITEMS_DIR = ASSETS_DIR / "items"
MEGASTONES_DIR = ASSETS_DIR / "megastones"
DATA_DIR = REPO_ROOT / "data"
MANIFEST_PATH = ASSETS_DIR / "png_manifest.json"

_MANIFEST_CACHE: Optional[Dict[str, Any]] = None


def get_asset_manifest() -> Dict[str, Any]:
    """Retrieve in-memory cached asset manifest to ensure O(1) asset resolution."""
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        if MANIFEST_PATH.is_file():
            try:
                _MANIFEST_CACHE = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            except Exception:
                _MANIFEST_CACHE = {}
        else:
            _MANIFEST_CACHE = {}
    return _MANIFEST_CACHE

RESTRICTED_PATH_PATTERNS = (
    "/.git",
    "/.github",
    "/.agents",
    "/trainer_profile.json",
    "/data/trainer_profile.json",
)

ALLOWED_SCRAPING_DOMAINS = (
    "munchstats.com",
    "www.munchstats.com",
    "bulbapedia.bulbagarden.net",
    "wikidex.net",
    "www.wikidex.net",
    "pikalytics.com",
    "www.pikalytics.com",
    "victoryroad.pro",
    "pokepast.es",
)

BLOCKED_IP_PREFIXES = (
    "127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
    "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.",
    "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168.",
    "169.254.", "0.0.0.0", "localhost"
)


def validate_scraping_target(target: str):
    """Validates that a URL or local file target complies with SSRF and LFI security guardrails (SEC-04)."""
    clean = (target or "").strip()
    lower = clean.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        if not lower.startswith("https://"):
            raise ValueError(
                f"Insecure protocol: External scraping must strictly use HTTPS. Rejecting: {clean}"
            )
        parsed = urllib.parse.urlparse(clean)
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError(f"Invalid URL target: {clean}")

        if any(hostname.startswith(p) or hostname == p for p in BLOCKED_IP_PREFIXES):
            raise ValueError(f"SSRF Shield: Direct IP / loopback requests are forbidden: {hostname}")

        is_allowed = False
        for allowed in ALLOWED_SCRAPING_DOMAINS:
            if hostname == allowed or hostname.endswith("." + allowed):
                is_allowed = True
                break

        if not is_allowed:
            raise ValueError(
                f"SSRF Shield: Domain '{hostname}' is not in the trusted scraping whitelist."
            )
        return True, clean

    # Local file path validation (LFI Shield)
    resolved = (REPO_ROOT / clean).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise PermissionError(f"LFI Path Traversal Shield: Access outside workspace denied: {clean}")
    return False, resolved


def slugify(text: str) -> str:
    """Canonical slug transformation for Pokémon species and item filenames."""
    clean = re.sub(r"\([mfMF]\)", "", str(text or "")).strip().lower()
    clean = re.sub(r"[^a-z0-9]+", "-", clean)
    return clean.strip("-")


def alnum_key(text: str) -> str:
    """Alphanumeric key transformation without hyphens."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def resolve_sprite_path(species: str, is_shiny: bool = False) -> Path | None:
    """
    Dynamically resolves the authentic sprite PNG path for a Pokémon name or alias.
    Checks assets/sprites/Reg_M-C/ first, falling back to assets/sprites/.
    Utilizes in-memory manifest cache for O(1) lookups with comprehensive form resolution.
    """
    raw = re.sub(r"\.(?:png|svg|webp|jpe?g)$", "", str(species or "").strip(), flags=re.I)
    clean = raw.split("@")[0].strip()
    check_shiny = is_shiny or bool(re.search(r"\bshiny\b", clean, re.I))
    is_female = bool(re.search(r"\(f\)|-f$|-female$", clean, re.I))
    is_male = bool(re.search(r"\(m\)|-m$|-male$", clean, re.I))
    stripped = re.sub(r"\bshiny\b", "", clean, flags=re.I)
    stripped = re.sub(r"\([mfMF]\)", "", stripped).strip()
    slug = slugify(stripped)
    alnum = alnum_key(stripped)

    assets_canon = ASSETS_DIR.resolve()

    # 1. Fast path: In-memory Manifest Lookup
    if not check_shiny:
        manifest = get_asset_manifest()
        species_map = manifest.get("species", {})
        for lookup_key in (raw, clean, stripped, slug, alnum):
            if lookup_key in species_map:
                rel = species_map[lookup_key]
                cand = (REPO_ROOT / rel).resolve()
                if cand.is_file() and os.path.commonpath([str(assets_canon), str(cand)]) == str(assets_canon):
                    return cand

    candidates = []

    # 2. Gender differentiated candidates
    if is_female:
        candidates.extend([f"{slug}-female", f"{slug}-f", f"{slug}female", f"{alnum}-female"])
        if "basculegion" in slug:
            candidates.insert(0, "basculegion-female")
        if "indeedee" in slug:
            candidates.insert(0, "indeedee-female")
        if "meowstic" in slug:
            candidates.insert(0, "meowstic-female")
        if "pyroar" in slug:
            candidates.insert(0, "pyroar-female")
    elif is_male:
        candidates.extend([f"{slug}-male", f"{slug}-m", f"{slug}male", f"{alnum}-male"])
        if "indeedee" in slug:
            candidates.insert(0, "indeedee-male")
        if "basculegion" in slug:
            candidates.insert(0, "basculegion-male")
        if "meowstic" in slug:
            candidates.insert(0, "meowstic-male")
        if "pyroar" in slug:
            candidates.insert(0, "pyroar-male")

    # 3. Specialized Form Mappings
    if "tauros" in slug:
        if "aqua" in slug:
            candidates.extend(["tauros-paldean-aqua", "tauros-aqua"])
        elif "blaze" in slug:
            candidates.extend(["tauros-paldean-blaze", "tauros-blaze"])
        elif "combat" in slug or slug == "paldean-tauros":
            candidates.extend(["tauros-paldean-combat", "tauros-combat"])
        elif slug == "tauros":
            candidates.append("tauros")

    if "lycanroc" in slug:
        if "midnight" in slug:
            candidates.extend(["lycanroc-midnight"])
        elif "dusk" in slug:
            candidates.extend(["lycanroc-dusk"])
        elif "midday" in slug or slug == "lycanroc":
            candidates.extend(["lycanroc"])

    if "toxtricity" in slug:
        if "low-key" in slug or "lowkey" in slug:
            candidates.extend(["toxtricity-low-key"])
        elif "amped" in slug or slug == "toxtricity":
            candidates.extend(["toxtricity"])

    if "florges" in slug:
        for col in ["blue", "orange", "white", "yellow"]:
            if col in slug:
                candidates.extend([f"florges-{col}"])
        if "red" in slug or slug == "florges":
            candidates.extend(["florges"])

    if "squawkabilly" in slug:
        for col in ["blue", "white", "yellow"]:
            if col in slug:
                candidates.extend([f"squawkabilly-{col}"])
        if "green" in slug or slug == "squawkabilly":
            candidates.extend(["squawkabilly"])

    if "gourgeist" in slug:
        if "small" in slug:
            candidates.extend(["gourgeist-small"])
        elif "large" in slug:
            candidates.extend(["gourgeist-large"])
        elif "jumbo" in slug or "super" in slug:
            candidates.extend(["gourgeist-super"])
        elif slug == "gourgeist":
            candidates.extend(["gourgeist"])

    if "furfrou" in slug:
        for trim in ["dandy", "debutante", "diamond", "heart", "kabuki", "la-reine", "matron", "pharaoh", "star"]:
            if trim in slug or trim.replace("-", "") in slug:
                candidates.extend([f"furfrou-{trim}"])
        if slug == "furfrou":
            candidates.extend(["furfrou"])

    # 4. Standard slug and alnum keys
    candidates.extend([slug, alnum])

    # 5. Regional forms permutations
    for reg in ["alolan", "hisuian", "galarian", "paldean"]:
        if slug.startswith(f"{reg}-"):
            candidates.append(slug.replace(f"{reg}-", "") + f"-{reg}")
        if slug.endswith(f"-{reg}"):
            candidates.append(f"{reg}-" + slug.replace(f"-{reg}", ""))

    # 6. Rotom appliances
    if "rotom" in slug:
        for app in ["wash", "heat", "frost", "fan", "mow"]:
            if app in slug:
                candidates.extend([f"rotom-{app}", f"{app}-rotom"])

    # 7. Mega normalization permutations
    if "mega" in slug:
        m_x = re.match(r"^(?:mega-)?([a-z0-9]+)-(?:mega-)?([xyz])$", slug)
        if m_x:
            b, s = m_x.group(1), m_x.group(2)
            candidates.extend([f"{b}-mega-{s}", f"{b}-mega{s}", f"{b}{s}-mega", f"mega-{b}-{s}"])
        if slug.startswith("mega-"):
            candidates.append(slug[5:] + "-mega")
        elif slug.endswith("-mega"):
            candidates.append("mega-" + slug[:-5])

    # 8. Base species fallback
    base_slug = slug
    if base_slug.startswith("mega-"):
        base_slug = base_slug[5:]
    for reg in ("alolan", "hisuian", "galarian", "paldean"):
        if base_slug.startswith(f"{reg}-"):
            base_slug = base_slug[len(reg) + 1:]
    for suffix_token in ("-mega", "-alolan", "-hisuian", "-galarian", "-paldean"):
        if suffix_token in base_slug:
            base_slug = base_slug.split(suffix_token, 1)[0]
    if base_slug.endswith(("-x", "-y", "-z")):
        base_slug = base_slug[:-2]
    if base_slug and base_slug not in candidates:
        candidates.append(base_slug)

    for c in candidates:
        if not c:
            continue
        stems = [f"{c}-shiny", f"{c}shiny"] if check_shiny else [c]
        for s in stems:
            for p in [SPRITES_REG_MC_DIR / f"{s}.png", SPRITES_ROOT_DIR / f"{s}.png"]:
                canon_p = p.resolve()
                if canon_p.is_file() and os.path.commonpath([str(assets_canon), str(canon_p)]) == str(assets_canon):
                    return canon_p

    return None


def generate_anatomical_battle_crest_svg(species_name: str) -> str:
    """Generates an authentic dual-type vector battle crest SVG if a raster sprite is missing."""
    clean = str(species_name or "Unknown").split("@")[0].strip()
    is_mega = "mega" in clean.lower()
    c1 = "#38bdf8"
    c2 = "#ec4899"
    badge_corona = (
        '<polygon points="60,6 70,22 88,14 84,32 102,34 90,48 104,60 90,72 102,86 '
        '84,88 88,106 70,98 60,114 50,98 32,106 36,88 18,86 30,48 18,34 36,32 32,14 50,22" '
        f'fill="{c1}" fill-opacity="0.25" stroke="{c1}" stroke-width="1.5"/>'
        if is_mega
        else ""
    )
    return f"""<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="48" fill="{c1}" fill-opacity="0.12"/>
  {badge_corona}
  <path d="M32,86 C32,68 44,62 60,62 C76,62 88,68 88,86 L94,104 C94,108 26,108 26,104 Z" fill="{c1}" stroke="#0f172a" stroke-width="2"/>
  <ellipse cx="60" cy="90" rx="14" ry="12" fill="{c2}" fill-opacity="0.85"/>
  <circle cx="60" cy="46" r="18" fill="{c1}" stroke="#0f172a" stroke-width="2"/>
  <polygon points="46,42 54,44 48,48" fill="#ffffff"/><circle cx="50" cy="45" r="1.5" fill="#0f172a"/>
  <polygon points="74,42 66,44 72,48" fill="#ffffff"/><circle cx="70" cy="45" r="1.5" fill="#0f172a"/>
  <polygon points="52,56 60,66 68,56" fill="{c2}" stroke="#0f172a" stroke-width="1.5"/>
</svg>"""


def execute_prompt_crawl_and_dump(user_prompt: str, export_csv: bool = True) -> dict:
    """
    Executes a targeted MunchStats crawl/query based on the user's natural-language prompt.
    1. If the prompt contains a live MunchStats URL, attempts live scraping via munchstats_scraper.py.
    2. Otherwise filters verified records in Scouted_Teams.csv & Tournament_Meta.json matching prompt keywords.
    3. Dumps the resulting verified dataset to `data/MunchStats_Query_Dump.csv` and returns analytics.
    """
    prompt_clean = (user_prompt or "").strip()
    lower_q = prompt_clean.lower()

    scraped_live = []
    if "http://" in lower_q or "https://" in lower_q:
        words = prompt_clean.split()
        url = next((w for w in words if w.startswith("http://") or w.startswith("https://")), None)
        if url:
            try:
                scraped_live = scrape_munchstats_url_or_json(url, save_to_csv=True)
            except Exception:
                scraped_live = [{
                    "warning": "Live URL fetch blocked or offline; falling back to local Scouted_Teams.csv."
                }]

    # Read verified rows from data/Scouted_Teams.csv
    rows = []
    if SCOUTED_CSV.exists():
        with open(SCOUTED_CSV, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    # Filter rows by prompt keywords if specific filter terms are given
    matched_rows = []
    for r in rows:
        blob = " ".join([
            r.get("Scouted_Team_ID", ""),
            r.get("Player_Name", ""),
            r.get("Tournament", ""),
            r.get("Placement", ""),
            r.get("Archetype", ""),
            r.get("Notes", ""),
            *(r.get(f"Pokemon_{i}", "") for i in range(1, 7))
        ]).lower()
        has_kw = any(tok in blob for tok in lower_q.split() if len(tok) >= 3)
        is_broad = any(k in lower_q for k in ("nice", "munchstats", "todo", "all"))
        if not lower_q or has_kw or is_broad:
            matched_rows.append(r)

    if not matched_rows:
        matched_rows = rows

    total_teams = len(matched_rows)
    species_counter = Counter()
    mega_counter = Counter()
    arch_counter = Counter()
    role_map = {}

    for r in matched_rows:
        st_id = r.get("Scouted_Team_ID", "")
        arch = r.get("Archetype", "Unknown")
        arch_counter[f"{arch} ({st_id})"] += 1
        for i in range(1, 7):
            mon_raw = r.get(f"Pokemon_{i}", "").strip()
            if not mon_raw:
                continue
            species_counter[mon_raw] += 1
            role_map[mon_raw] = f"{st_id} ({r.get('Player_Name', '')}) — {arch}"
            if "ite" in mon_raw.lower() or "mega" in mon_raw.lower():
                mega_counter[mon_raw] += 1

    usage_stats = [
        {
            "species": sp,
            "count": c,
            "usage_pct": round((c / max(1, total_teams)) * 100.0, 1),
            "role": role_map.get(sp, "Verified OTS Slot")
        }
        for sp, c in species_counter.most_common(18)
    ]

    dominant_megas = [
        {
            "mega": m,
            "count": c,
            "share_pct": round((c / max(1, total_teams)) * 100.0, 1)
        }
        for m, c in mega_counter.most_common(8)
    ]

    top_archetypes = [
        {
            "archetype": a,
            "count": c,
            "share_pct": round((c / max(1, total_teams)) * 100.0, 1)
        }
        for a, c in arch_counter.most_common(8)
    ]

    dump_csv_path = DATA_DIR / "MunchStats_Query_Dump.csv"
    if export_csv:
        with open(dump_csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            headers = [
                "Query_Prompt", "Scouted_Team_ID", "Player_Name", "Tournament",
                "Placement", "Archetype", "Pokemon_1", "Pokemon_2", "Pokemon_3",
                "Pokemon_4", "Pokemon_5", "Pokemon_6"
            ]
            writer.writerow(headers)
            for r in matched_rows:
                writer.writerow([
                    prompt_clean,
                    r.get("Scouted_Team_ID", ""),
                    r.get("Player_Name", ""),
                    r.get("Tournament", ""),
                    r.get("Placement", ""),
                    r.get("Archetype", ""),
                    r.get("Pokemon_1", ""),
                    r.get("Pokemon_2", ""),
                    r.get("Pokemon_3", ""),
                    r.get("Pokemon_4", ""),
                    r.get("Pokemon_5", ""),
                    r.get("Pokemon_6", ""),
                ])

    fresh_telemetry = load_live_telemetry()
    (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(fresh_telemetry, indent=2), encoding="utf-8")

    return {
        "status": "OK",
        "query": prompt_clean,
        "matched_teams_count": total_teams,
        "dumped_csv": str(dump_csv_path.relative_to(REPO_ROOT)),
        "scraped_live": scraped_live,
        "analytics": {
            "tournament_name": "2027 Nice Regional Championships (Verified Scouted Records)",
            "date": "Verified OTS Data",
            "division": "Masters",
            "total_players": total_teams,
            "top_cut_size": total_teams,
            "usage_stats": usage_stats,
            "dominant_megas": dominant_megas,
            "top_archetypes": top_archetypes,
            "matched_rosters": matched_rows,
        },
        "telemetry": fresh_telemetry,
    }


def compute_comprehensive_spread_analytics(payload: dict) -> dict:
    """
    Computes comprehensive Regulation M-C Level 50 stats, Speed Ladder ranking,
    and 16+ real-time offensive and defensive damage calculations vs top meta threats.
    """
    from engine.turn_simulator import (
        ClientReplaySimulator, calculate_level_50_stats, BASE_STATS_DB, MOVE_DB
    )
    from engine.sp_calculator import validate_and_calculate_sp

    species = str(payload.get("species", "Charizard-Mega-Y")).strip()
    sp_in = payload.get("sp") or {}
    sp_spread = {
        "hp": int(sp_in.get("hp", payload.get("hp", 0))),
        "atk": int(sp_in.get("atk", payload.get("atk", 0))),
        "def": int(sp_in.get("def", payload.get("def_sp", payload.get("def", 0)))),
        "spa": int(sp_in.get("spa", payload.get("spa", 0))),
        "spd": int(sp_in.get("spd", payload.get("spd", 0))),
        "spe": int(sp_in.get("spe", payload.get("spe", 0))),
    }
    nature = str(payload.get("nature", "Modest")).capitalize()
    item = str(payload.get("item", "Life Orb")).strip()
    ability = str(payload.get("ability", "")).strip()
    boosts = payload.get("boosts") or {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    for k in ("atk", "def", "spa", "spd", "spe"):
        boosts[k] = int(boosts.get(k, 0))

    field_in = payload.get("field") or {}
    weather = str(field_in.get("weather", payload.get("weather", "none"))).lower()
    weather = None if weather in ("none", "") else weather
    terrain = str(field_in.get("terrain", payload.get("terrain", "none"))).lower()
    terrain = None if terrain in ("none", "") else terrain

    tailwind = bool(field_in.get("tailwind", payload.get("tailwind", False)))
    helping_hand = bool(field_in.get("helping_hand", payload.get("helping_hand", False)))
    reflect = bool(field_in.get("reflect", payload.get("reflect", False)))
    light_screen = bool(field_in.get("light_screen", payload.get("light_screen", False)))
    friend_guard = bool(field_in.get("friend_guard", payload.get("friend_guard", False)))

    # Calculate Level 50 stats with sequential floor rounding
    ok, sp_verif, final_stats = validate_and_calculate_sp(species, sp_spread, nature=nature)
    if not ok:
        hp_val, st_val = calculate_level_50_stats(species, sp_spread, nature=nature)
        final_stats = {"hp": hp_val, **st_val}
        total_sp = sum(sp_spread.values())
        sp_verif = (
            f"{sp_spread['hp']} HP + {sp_spread['atk']} Atk + {sp_spread['def']} Def + "
            f"{sp_spread['spa']} SpA + {sp_spread['spd']} SpD + {sp_spread['spe']} Spe = {total_sp} SP"
        )

    user_base = BASE_STATS_DB.get(species, {"types": ["Normal"]})
    user_types = list(user_base.get("types", ["Normal"]))

    # Speed Tier Analysis
    raw_spe = final_stats.get("spe", 80)
    effective_spe = raw_spe
    if tailwind:
        effective_spe *= 2
    if item == "Choice Scarf":
        effective_spe = int(effective_spe * 1.5)
    spe_boost = boosts.get("spe", 0)
    if spe_boost > 0:
        effective_spe = int(effective_spe * (2 + spe_boost) / 2)
    elif spe_boost < 0:
        effective_spe = int(effective_spe * 2 / (2 - spe_boost))

    from engine.db import UnifiedCoachDatabase

    db_inst = UnifiedCoachDatabase()
    sql_speed_benchmarks = db_inst.get_speed_benchmarks(limit=15)
    sql_threats = db_inst.get_unsupervised_threats(limit=12)
    db_inst.close()

    if sql_speed_benchmarks:
        speed_benchmarks = [
            {
                "name": b["name"],
                "speed": int(b["spe"]),
                "tier": f"Tier ({b['tier']}) — {b['usage_pct']}% Regional Usage",
            }
            for b in sql_speed_benchmarks
        ]
    else:
        speed_benchmarks = [
            {"name": "Raichu-Mega-Y (Timid 32 SP)", "speed": 200, "tier": "Tier 1: Fast"},
            {"name": "Salamence-Mega (Timid 32 SP)", "speed": 189, "tier": "Tier 1: Fast"},
            {"name": "Sneasler (Adamant 32 SP)", "speed": 172, "tier": "Tier 2: High Speed"},
            {"name": "Charizard-Mega-Y (Modest 32 SP)", "speed": 152, "tier": "Tier 3: Mid Speed"},
            {"name": "Rillaboom (Adamant 32 SP)", "speed": 137, "tier": "Tier 3: Mid Speed"},
            {"name": "Archaludon (Calm 0 SP)", "speed": 105, "tier": "Tier 4: Bulky"},
            {"name": "Gholdengo (Modest 0 SP)", "speed": 104, "tier": "Tier 4: Bulky"},
            {"name": "Incineroar (Careful 0 SP)", "speed": 80, "tier": "Tier 5: Slow Pivot"},
            {"name": "Kingambit (Adamant 0 SP)", "speed": 70, "tier": "Tier 6: Trick Room"},
        ]

    speed_ladder = []
    for b in speed_benchmarks:
        status = "OUTSPEEDS" if effective_spe > b["speed"] else ("TIE" if effective_spe == b["speed"] else "UNDERSPEEDS")
        speed_ladder.append({
            "target": b["name"],
            "target_speed": b["speed"],
            "tier": b["tier"],
            "status": status,
            "delta": effective_spe - b["speed"],
        })

    if sql_threats:
        meta_threats = [
            {
                "species": t["species"],
                "types": t["types"],
                "role": t["cluster_label"],
                "threat_score": t["threat_score"],
                "usage_pct": t["usage_pct"],
                "item": t["item"],
                "ability": t["ability"],
                "nature": t["nature"],
                "sp": t["sp_spread"],
                "move": t["move"],
                "bp": t["bp"],
                "cat": t["cat"],
                "type": t["mtype"],
            }
            for t in sql_threats
        ]
    else:
        meta_threats = [
            {"species": "Rillaboom", "types": ["Grass"], "role": "APEX_META_PILLAR", "threat_score": 99.5, "usage_pct": 50.35, "item": "Miracle Seed", "ability": "Grassy Surge", "nature": "Adamant", "sp": {"hp": 2, "atk": 32, "spe": 32}, "move": "Grassy Glide", "bp": 55, "cat": "Physical", "type": "Grass"},
            {"species": "Sneasler", "types": ["Fighting", "Poison"], "role": "APEX_META_PILLAR", "threat_score": 94.8, "usage_pct": 38.85, "item": "White Herb", "ability": "Unburden", "nature": "Adamant", "sp": {"hp": 2, "atk": 32, "spe": 32}, "move": "Close Combat", "bp": 120, "cat": "Physical", "type": "Fighting"},
            {"species": "Incineroar", "types": ["Fire", "Dark"], "role": "APEX_META_PILLAR", "threat_score": 87.3, "usage_pct": 34.1, "item": "Sitrus Berry", "ability": "Intimidate", "nature": "Careful", "sp": {"hp": 32, "def": 12, "spd": 22}, "move": "Flare Blitz", "bp": 120, "cat": "Physical", "type": "Fire"},
            {"species": "Kingambit", "types": ["Dark", "Steel"], "role": "APEX_META_PILLAR", "threat_score": 76.5, "usage_pct": 23.67, "item": "Chople Berry", "ability": "Defiant", "nature": "Adamant", "sp": {"hp": 32, "atk": 32, "def": 2}, "move": "Kowtow Cleave", "bp": 85, "cat": "Physical", "type": "Dark"},
            {"species": "Charizard-Mega-Y", "types": ["Fire", "Flying"], "role": "WALLBREAKER_NUKE", "threat_score": 68.8, "usage_pct": 16.96, "item": "Charizardite Y", "ability": "Drought", "nature": "Modest", "sp": {"hp": 2, "spa": 32, "spe": 32}, "move": "Heat Wave", "bp": 95, "cat": "Special", "type": "Fire"},
            {"species": "Raichu-Mega-Y", "types": ["Electric"], "role": "APEX_META_PILLAR", "threat_score": 67.5, "usage_pct": 25.8, "item": "Raichunite Y", "ability": "Lightning Rod", "nature": "Timid", "sp": {"hp": 2, "spa": 32, "spe": 32}, "move": "Zap Cannon", "bp": 120, "cat": "Special", "type": "Electric"},
            {"species": "Gholdengo", "types": ["Steel", "Ghost"], "role": "APEX_META_PILLAR", "threat_score": 67.2, "usage_pct": 25.24, "item": "Life Orb", "ability": "Good as Gold", "nature": "Modest", "sp": {"hp": 32, "spa": 32, "spd": 2}, "move": "Shadow Ball", "bp": 80, "cat": "Special", "type": "Ghost"},
            {"species": "Archaludon", "types": ["Steel", "Dragon"], "role": "SWISS_GATEKEEPER", "threat_score": 65.3, "usage_pct": 17.22, "item": "Leftovers", "ability": "Stamina", "nature": "Calm", "sp": {"hp": 32, "def": 12, "spd": 22}, "move": "Electro Shot", "bp": 130, "cat": "Special", "type": "Electric"},
            {"species": "Floette-Mega", "types": ["Fairy"], "role": "WALLBREAKER_NUKE", "threat_score": 62.6, "usage_pct": 13.07, "item": "Floettite", "ability": "Flower Veil", "nature": "Modest", "sp": {"hp": 2, "spa": 32, "spe": 32}, "move": "Dazzling Gleam", "bp": 80, "cat": "Special", "type": "Fairy"},
            {"species": "Garchomp", "types": ["Dragon", "Ground"], "role": "WALLBREAKER_NUKE", "threat_score": 61.4, "usage_pct": 12.0, "item": "Choice Scarf", "ability": "Rough Skin", "nature": "Adamant", "sp": {"hp": 2, "atk": 32, "spe": 32}, "move": "Dragon Claw", "bp": 80, "cat": "Physical", "type": "Dragon"},
        ]

    primary_type = user_types[0] if user_types else "Normal"
    is_special = final_stats.get("spa", 0) >= final_stats.get("atk", 0)

    type_to_move = {
        "Fire": ("Heat Wave", "Special", 95) if is_special else ("Flare Blitz", "Physical", 120),
        "Water": ("Hydro Pump", "Special", 110) if is_special else ("Wave Crash", "Physical", 120),
        "Grass": ("Energy Ball", "Special", 90) if is_special else ("Wood Hammer", "Physical", 120),
        "Electric": ("Thunderbolt", "Special", 90) if is_special else ("Wild Charge", "Physical", 90),
        "Dragon": ("Draco Meteor", "Special", 130) if is_special else ("Dragon Claw", "Physical", 80),
        "Steel": ("Make It Rain", "Special", 120) if is_special else ("Iron Head", "Physical", 80),
        "Dark": ("Dark Pulse", "Special", 80) if is_special else ("Knock Off", "Physical", 65),
        "Ghost": ("Shadow Ball", "Special", 80) if is_special else ("Poltergeist", "Physical", 110),
        "Fairy": ("Moonblast", "Special", 95) if is_special else ("Play Rough", "Physical", 90),
        "Fighting": ("Aura Sphere", "Special", 80) if is_special else ("Close Combat", "Physical", 120),
        "Psychic": ("Expanding Force", "Special", 80) if is_special else ("Zen Headbutt", "Physical", 80),
        "Rock": ("Power Gem", "Special", 80) if is_special else ("Rock Slide", "Physical", 75),
        "Ground": ("Earth Power", "Special", 90) if is_special else ("Earthquake", "Physical", 100),
        "Flying": ("Hurricane", "Special", 110) if is_special else ("Brave Bird", "Physical", 120),
        "Ice": ("Blizzard", "Special", 110) if is_special else ("Icicle Crash", "Physical", 85),
        "Poison": ("Sludge Bomb", "Special", 90) if is_special else ("Gunk Shot", "Physical", 120),
        "Bug": ("Bug Buzz", "Special", 90) if is_special else ("U-turn", "Physical", 70),
        "Normal": ("Hyper Voice", "Special", 90) if is_special else ("Double-Edge", "Physical", 120),
    }

    user_move_info = type_to_move.get(primary_type, ("Hyper Voice", "Special", 90))
    user_move_data = MOVE_DB.get(user_move_info[0], {
        "name": user_move_info[0], "bp": user_move_info[2], "type": primary_type, "cat": user_move_info[1], "flags": []
    })

    sim_field = {"weather": weather, "terrain": terrain}
    side_p1 = {"player": "p1", "reflect_turns": 5 if reflect else 0, "light_screen_turns": 5 if light_screen else 0, "friend_guard": friend_guard}
    side_p2 = {"player": "p2"}

    calculations = []

    # 1. Offensive Calculations (User attacks 10 threats)
    for t in meta_threats[:10]:
        t_sp = t["sp"]
        t_nature = t["nature"]
        t_hp, t_stats = calculate_level_50_stats(t["species"], t_sp, t_nature)
        state_off = {
            "field": sim_field,
            "slots": {
                "p1a": {"species": species, "types": user_types, "ability": ability, "item": item, "sp_spread": sp_spread, "nature": nature, "boosts": boosts, "helping_hand_mult": 1.5 if helping_hand else 1.0},
                "p2a": {"species": t["species"], "types": t["types"], "ability": t["ability"], "item": t["item"], "sp_spread": t_sp, "nature": t_nature, "boosts": {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}}
            },
            "p1": side_p1, "p2": side_p2
        }
        sim_off = ClientReplaySimulator(state_off, {})
        d_min, p_min, eff, _ = sim_off.calculate_damage_full(sim_off.state["slots"]["p1a"], sim_off.state["slots"]["p2a"], user_move_data, is_spread=False, roll=0.85)
        d_max, p_max, _, _ = sim_off.calculate_damage_full(sim_off.state["slots"]["p1a"], sim_off.state["slots"]["p2a"], user_move_data, is_spread=False, roll=1.00)

        c_type = "Guaranteed OHKO" if p_min >= 100 else ("Probable OHKO" if p_max >= 100 else ("Guaranteed 2HKO" if p_min >= 50 else ("2HKO Roll" if p_max >= 50 else "3HKO+")))
        mod_tokens = []
        if weather: mod_tokens.append(f"Clima: {weather.capitalize()}")
        if terrain: mod_tokens.append(f"Terreno: {terrain.capitalize()}")
        if item: mod_tokens.append(item)
        if helping_hand: mod_tokens.append("Helping Hand (+50%)")
        if eff > 1.0: mod_tokens.append(f"Supereficaz ({eff:.1f}x)")
        elif eff < 1.0 and eff > 0: mod_tokens.append(f"Resistido ({eff:.2f}x)")

        calculations.append({
            "direction": "Offensive",
            "attacker": species,
            "defender": t["species"],
            "threat_role": t.get("role", "APEX_META_PILLAR"),
            "threat_score": t.get("threat_score", 80.0),
            "usage_pct": t.get("usage_pct", 20.0),
            "move": user_move_data["name"],
            "category": user_move_data.get("cat", "Special"),
            "move_type": user_move_data.get("type", primary_type),
            "min_pct": p_min,
            "max_pct": p_max,
            "min_dmg": d_min,
            "max_dmg": d_max,
            "defender_max_hp": t_hp,
            "calc_type": c_type,
            "modifiers": " • ".join(mod_tokens) if mod_tokens else "Neutral",
            "effectiveness": eff,
        })

    # 2. Defensive Calculations (10 threats attack User)
    for t in meta_threats[:10]:
        t_sp = t["sp"]
        t_nature = t["nature"]
        t_mv_data = MOVE_DB.get(t["move"], {
            "name": t["move"], "bp": t.get("bp", 100), "power": t.get("bp", 100), "type": t["type"], "cat": t["cat"], "flags": []
        })
        state_def = {
            "field": sim_field,
            "slots": {
                "p1a": {"species": species, "types": user_types, "ability": ability, "item": item, "sp_spread": sp_spread, "nature": nature, "boosts": boosts, "current_hp_pct": 100.0},
                "p2a": {"species": t["species"], "types": t["types"], "ability": t["ability"], "item": t["item"], "sp_spread": t_sp, "nature": t_nature, "boosts": {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}}
            },
            "p1": side_p1, "p2": side_p2
        }
        sim_def = ClientReplaySimulator(state_def, {})
        d_min, p_min, eff, _ = sim_def.calculate_damage_full(sim_def.state["slots"]["p2a"], sim_def.state["slots"]["p1a"], t_mv_data, is_spread=False, roll=0.85)
        d_max, p_max, _, _ = sim_def.calculate_damage_full(sim_def.state["slots"]["p2a"], sim_def.state["slots"]["p1a"], t_mv_data, is_spread=False, roll=1.00)

        c_type = "Guaranteed Survival" if p_max < 100 else ("OHKO Threat" if p_min >= 100 else "Survival Roll")
        mod_tokens = []
        if weather: mod_tokens.append(f"Clima: {weather.capitalize()}")
        if terrain: mod_tokens.append(f"Terreno: {terrain.capitalize()}")
        if t["item"]: mod_tokens.append(f"Ítem Rival: {t['item']}")
        if reflect and t_mv_data.get("cat") == "Physical": mod_tokens.append("Reflect (-33%)")
        if light_screen and t_mv_data.get("cat") == "Special": mod_tokens.append("Light Screen (-33%)")
        if eff > 1.0: mod_tokens.append(f"Supereficaz ({eff:.1f}x)")
        elif eff < 1.0 and eff > 0: mod_tokens.append(f"Resistido ({eff:.2f}x)")

        calculations.append({
            "direction": "Defensive",
            "attacker": t["species"],
            "defender": species,
            "threat_role": t.get("role", "APEX_META_PILLAR"),
            "threat_score": t.get("threat_score", 80.0),
            "usage_pct": t.get("usage_pct", 20.0),
            "move": t_mv_data["name"],
            "category": t_mv_data.get("cat", "Physical"),
            "move_type": t_mv_data.get("type", t["type"]),
            "min_pct": p_min,
            "max_pct": p_max,
            "min_dmg": d_min,
            "max_dmg": d_max,
            "defender_max_hp": final_stats.get("hp", 100),
            "calc_type": c_type,
            "modifiers": " • ".join(mod_tokens) if mod_tokens else "Neutral",
            "effectiveness": eff,
        })

    return {
        "status": "OK",
        "species": species,
        "nature": nature,
        "item": item,
        "ability": ability,
        "sp_spread": sp_spread,
        "total_sp": sum(sp_spread.values()),
        "sp_verification": sp_verif,
        "is_legal_budget": ok,
        "stats": final_stats,
        "speed_analysis": {
            "raw_speed": raw_spe,
            "effective_speed": effective_spe,
            "tailwind_speed": raw_spe * 2,
            "scarf_speed": int(raw_spe * 1.5),
            "plus1_speed": int(raw_spe * 1.5),
            "ladder": speed_ladder,
        },
        "total_calculations": len(calculations),
        "calculations": calculations,
        "unsupervised_threats": meta_threats,
    }


def create_app(data_dir: Optional[Path] = None) -> Flask:
    """Application factory creating the Coach Porygon VGC Flask web app."""
    app = Flask(__name__, static_folder=None)
    app.config["DATA_DIR"] = Path(data_dir) if data_dir else DATA_DIR

    @app.before_request
    def check_security_guardrails():
        """Enforces DoS payload size limits (SEC-06) and path traversal protection (SEC-03)."""
        # 1. DoS Guard: Cap incoming request body size at 5 MB
        if request.content_length and request.content_length > MAX_POST_BODY_BYTES:
            abort(413, description=f"Payload Too Large: Exceeds {MAX_POST_BODY_BYTES} byte limit")

        # 2. Path Traversal & Sensitive Resource Shield (SEC-03)
        path_lower = request.path.lower()
        if any(res in path_lower for res in RESTRICTED_PATH_PATTERNS) or "/." in path_lower:
            abort(403, description="Access Denied: Restricted System Resource")

    @app.after_request
    def apply_security_headers(response: Response) -> Response:
        """Injects strict CORS policies (SEC-01 & SEC-02) and cache controls."""
        origin = request.headers.get("Origin", "")
        if origin:
            # CodeQL remediation for HTTP Response Splitting (CWE-113)
            clean_origin = origin.replace("\r", "").replace("\n", "").strip()
            if clean_origin.lower() == "null":
                response.headers["Access-Control-Allow-Origin"] = "*"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            elif clean_origin.startswith("vscode-webview://"):
                response.headers["Access-Control-Allow-Origin"] = clean_origin
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            else:
                try:
                    parsed_origin = urllib.parse.urlsplit(clean_origin)
                    scheme = (parsed_origin.scheme or "").lower()
                    hostname = (parsed_origin.hostname or "").lower()
                    port = parsed_origin.port
                    if scheme in ("http", "https") and hostname in ("localhost", "127.0.0.1"):
                        safe_origin = f"{scheme}://{hostname}" + (f":{port}" if port is not None else "")
                        response.headers["Access-Control-Allow-Origin"] = safe_origin
                        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
                except Exception:
                    pass
        else:
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/", methods=["GET"])
    @app.route("/index.html", methods=["GET"])
    def index():
        """Serves default master Command Center."""
        return redirect("/assets/command_center.html")

    @app.route("/es", methods=["GET"])
    def command_center_es():
        """Serves Spanish Command Center."""
        return redirect("/assets/command_center_es.html")

    @app.route("/en", methods=["GET"])
    def command_center_en():
        """Serves English Command Center."""
        return redirect("/assets/command_center_en.html")

    @app.route("/assets/<path:filename>", methods=["GET"])
    def serve_static_asset(filename: str):
        """Sandboxed static asset delivery with directory traversal containment (SEC-03)."""
        fn_lower = filename.lower()
        if any(res in fn_lower for res in RESTRICTED_PATH_PATTERNS) or "/." in fn_lower or ".." in filename:
            abort(403, description="Access Denied: Restricted System Resource")

        assets_canon = ASSETS_DIR.resolve()
        safe_str = safe_join(str(assets_canon), filename)
        if safe_str is None:
            abort(403, description="Access Denied: Path Traversal Attempt")

        safe_path = Path(safe_str).resolve()
        if os.path.commonpath([str(assets_canon), str(safe_path)]) != str(assets_canon):
            abort(403, description="Access Denied: Path Traversal Attempt")

        if not safe_path.is_file():
            abort(404, description="Asset Not Found")

        rel_name = safe_path.relative_to(assets_canon).as_posix()
        manifest = get_asset_manifest()
        rel_key = safe_path.relative_to(REPO_ROOT).as_posix()
        digest = manifest.get("sha256_digests", {}).get(rel_key)
        if not digest and safe_path.is_file():
            digest = hashlib.sha256(safe_path.read_bytes()).hexdigest()

        if digest:
            etag = f'"{digest}"'
            if_none_match = request.headers.get("If-None-Match")
            if if_none_match and etag in if_none_match:
                resp = Response(status=304)
                resp.headers["ETag"] = etag
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp

        resp = send_from_directory(assets_canon, rel_name)
        if digest:
            resp.headers["ETag"] = f'"{digest}"'
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    @app.route("/api/sprites/<path:species>", methods=["GET"])
    def api_get_sprite(species: str):
        """
        Dynamic Pokémon sprite resolver endpoint.
        Returns matching 128x128 PNG from Reg_M-C or dynamic vector crest if uncatalogued.
        Query args: ?shiny=1 or ?shiny=true
        """
        clean_raw = re.sub(r"\.(?:png|svg|webp|jpe?g)$", "", species, flags=re.I)
        clean_species = re.sub(r"[^a-zA-Z0-9_\-() ]", "", clean_raw.replace("+", " ")).strip()
        is_shiny = request.args.get("shiny", "").lower() in ("1", "true", "yes")
        sprite_file = resolve_sprite_path(clean_species, is_shiny=is_shiny)
        assets_canon = ASSETS_DIR.resolve()
        if sprite_file and sprite_file.is_file():
            canon_sprite = sprite_file.resolve()
            if os.path.commonpath([str(assets_canon), str(canon_sprite)]) == str(assets_canon):
                manifest = get_asset_manifest()
                rel_key = canon_sprite.relative_to(REPO_ROOT).as_posix()
                digest = manifest.get("sha256_digests", {}).get(rel_key)
                if not digest:
                    digest = hashlib.sha256(canon_sprite.read_bytes()).hexdigest()
                etag = f'"{digest}"'

                if_none_match = request.headers.get("If-None-Match")
                if if_none_match and etag in if_none_match:
                    resp = Response(status=304)
                    resp.headers["ETag"] = etag
                    resp.headers["Cache-Control"] = "public, max-age=86400"
                    return resp

                resp = send_file(canon_sprite, mimetype="image/png")
                resp.headers["ETag"] = etag
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp

        # Fallback to dynamic SVG battle crest
        svg_code = generate_anatomical_battle_crest_svg(clean_species)
        resp = Response(svg_code, mimetype="image/svg+xml; charset=utf-8")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    @app.route("/api/items/<path:item>", methods=["GET"])
    def api_get_item(item: str):
        """Dynamic item & megastone icon resolver endpoint with ETag caching."""
        clean_item = re.sub(r"\.(?:png|svg|webp|jpe?g)$", "", item, flags=re.I)
        slug = re.sub(r"[^a-z0-9\-]", "", slugify(clean_item))
        if not slug:
            abort(404, description="Item Icon Not Found")

        assets_canon = ASSETS_DIR.resolve()
        manifest = get_asset_manifest()
        items_map = manifest.get("items", {})
        megas_map = manifest.get("megastones", {})

        target_path: Optional[Path] = None
        for key in (item, slug):
            if key in items_map:
                p = (REPO_ROOT / items_map[key]).resolve()
                if p.is_file() and os.path.commonpath([str(assets_canon), str(p)]) == str(assets_canon):
                    target_path = p
                    break
            if key in megas_map:
                p = (REPO_ROOT / megas_map[key]).resolve()
                if p.is_file() and os.path.commonpath([str(assets_canon), str(p)]) == str(assets_canon):
                    target_path = p
                    break

        if not target_path:
            cand_paths = [
                ITEMS_DIR / f"{slug}.png",
                ITEMS_DIR / f"{slug}.svg",
                MEGASTONES_DIR / f"{slug}.png",
                MEGASTONES_DIR / f"{slug}.svg",
            ]
            for p in cand_paths:
                canon_p = p.resolve()
                if canon_p.is_file() and os.path.commonpath([str(assets_canon), str(canon_p)]) == str(assets_canon):
                    target_path = canon_p
                    break

        if not target_path:
            abort(404, description="Item Icon Not Found")

        rel_key = target_path.relative_to(REPO_ROOT).as_posix()
        digest = manifest.get("sha256_digests", {}).get(rel_key)
        if not digest:
            digest = hashlib.sha256(target_path.read_bytes()).hexdigest()
        etag = f'"{digest}"'

        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and etag in if_none_match:
            resp = Response(status=304)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp

        mime = "image/png" if target_path.suffix == ".png" else "image/svg+xml; charset=utf-8"
        resp = send_file(target_path, mimetype=mime)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    @app.route("/api/health", methods=["GET"])
    def api_health():
        """Health check endpoint exposing live system status and telemetry metrics."""
        data = load_live_telemetry(data_dir=app.config.get("DATA_DIR"))
        return jsonify({
            "status": "UP",
            "version": "1.0.0",
            "total_matches": data.get("total_matches", 0),
            "teams_count": data.get("teams_count", 0),
            "scouted_count": len(data.get("scouted", [])),
            "tournaments_count": len(data.get("tournaments", [])),
        })

    @app.route("/api/telemetry", methods=["GET"])
    def api_telemetry():
        """Returns live workspace telemetry snapshot."""
        data = load_live_telemetry(data_dir=app.config.get("DATA_DIR"))
        return jsonify(data)

    @app.route("/api/munchstats/data", methods=["GET"])
    def api_munchstats_data():
        """Returns structured MunchStats metagame datasets."""
        data = load_live_telemetry(data_dir=app.config.get("DATA_DIR"))
        return jsonify({
            "tournaments": data.get("tournaments", []),
            "overview": data.get("munchstats_overview", []),
            "usage": data.get("munchstats_usage", []),
            "top_teams": data.get("munchstats_top_teams", []),
        })

    @app.route("/api/munchstats/crawl", methods=["POST"])
    def api_munchstats_crawl():
        """Executes natural-language prompt crawl and query dump."""
        body = request.get_json(silent=True) or {}
        prompt_q = body.get("prompt", "") or body.get("tournament_id", "Nice 2027")
        result = execute_prompt_crawl_and_dump(prompt_q, export_csv=True)
        return jsonify(result)

    @app.route("/api/sync", methods=["POST"])
    def api_sync():
        """Re-reads CSVs and updates live_telemetry.json."""
        telemetry = load_live_telemetry()
        (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
        return jsonify({"status": "SYNCED", "telemetry": telemetry})

    @app.route("/api/telemetry/ingest", methods=["POST"])
    def api_telemetry_ingest():
        """Ingests personal match telemetry row into Raw_Matches.csv."""
        body = request.get_json(silent=True) or {}
        try:
            import telemetry as tel_module
            m_id = body.get("id", f"M{(len(load_live_telemetry().get('raw_matches', [])) + 1)}")
            opp = body.get("opponent", "Competitive Opponent")
            res = body.get("result", "Win")
            turns = float(body.get("turns", 5))
            row = {
                "Timestamp": datetime.now(timezone.utc).isoformat(),
                "Match_ID": m_id,
                "Team_ID": body.get("team_id", "T01"),
                "Opponent": opp,
                "Start_Rating": "1500",
                "End_Rating": "1515" if res.lower() == "win" else "1485",
                "Net_Rating": "15" if res.lower() == "win" else "-15",
                "Result": res,
                "Turns": turns,
                "Enemy_Archetype": body.get("archetype", "Goodstuff / Balance"),
                "User_Mega": body.get("user_mega", "Charizard-Mega-Y"),
                "Enemy_Mega": body.get("enemy_mega", "Kangaskhan-Mega"),
                "User_Lead_1": "Charizard",
                "User_Lead_2": "Indeedee-F",
                "User_Back_1": "Armarouge",
                "User_Back_2": "Kingambit",
                "Enemy_Lead_1": "Incineroar",
                "Enemy_Lead_2": "Rillaboom",
                "Speed_Control_Active": "None",
                "First_Blood_Side": "User" if res.lower() == "win" else "Enemy",
                "MVP_Pokemon": "Charizard-Mega-Y" if res.lower() == "win" else "None",
                "MVP_Move": "Heat Wave" if res.lower() == "win" else "None",
                "Misplay_Type": "None" if res.lower() == "win" else "POS-01",
                "Key_RNG_Event": "None",
                "Core_Lesson": f"Telemetry Live Log for {m_id}",
                "Commentary": body.get("notes", "Ingested via Coach Porygon Web Interface"),
            }
            tel_module.append_csv_row(DATA_DIR / "Raw_Matches.csv", tel_module.RAW_MATCHES_COLS, row)
        except Exception as e:
            print(f"[WARN] Ingest error: {e}")

        fresh = load_live_telemetry()
        (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(fresh, indent=2), encoding="utf-8")
        return jsonify({"status": "INGESTED", "telemetry": fresh})

    @app.route("/api/scouted/ingest", methods=["POST"])
    def api_scouted_ingest():
        """Ingests verified scouted OTS team into Scouted_Teams.csv."""
        body = request.get_json(silent=True) or {}
        try:
            scouted_path = DATA_DIR / "Scouted_Teams.csv"
            existing = []
            if scouted_path.exists():
                with open(scouted_path, "r", encoding="utf-8") as f:
                    existing = list(csv.DictReader(f))
            new_id = body.get("id") or f"ST{str(len(existing) + 1).zfill(2)}"
            mons = body.get("mons", [])
            while len(mons) < 6:
                mons.append("")
            row = {
                "Scouted_Team_ID": new_id,
                "Player_Name": body.get("player", "Unknown Player"),
                "Tournament": body.get("tournament", "Custom OTS Session"),
                "Date_Scouted": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "Placement": body.get("placement", "Ingesta en Sesión"),
                "Pokemon_1": mons[0],
                "Pokemon_2": mons[1],
                "Pokemon_3": mons[2],
                "Pokemon_4": mons[3],
                "Pokemon_5": mons[4],
                "Pokemon_6": mons[5],
                "Showdown_Export": body.get("export", ""),
                "Archetype": body.get("archetype", "Balance"),
                "Notes": body.get("notes", "Ingested via Command Center Web"),
            }
            with open(scouted_path, "a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "Scouted_Team_ID", "Player_Name", "Tournament", "Date_Scouted",
                    "Placement", "Pokemon_1", "Pokemon_2", "Pokemon_3",
                    "Pokemon_4", "Pokemon_5", "Pokemon_6", "Showdown_Export",
                    "Archetype", "Notes"
                ])
                writer.writerow(row)
        except Exception as e:
            print(f"[WARN] Scouted ingest error: {e}")

        fresh = load_live_telemetry()
        (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(fresh, indent=2), encoding="utf-8")
        return jsonify({"status": "INGESTED", "team_id": new_id, "telemetry": fresh})

    @app.route("/api/status", methods=["GET"])
    def api_status():
        """Returns GPU/CUDA availability, device info, and live system telemetry status."""
        cuda_available = False
        device_name = "cpu"
        try:
            import torch
            cuda_available = bool(torch.cuda.is_available())
            if cuda_available:
                device_name = f"cuda:0 ({torch.cuda.get_device_name(0)})"
        except Exception:
            pass
        data = load_live_telemetry(data_dir=app.config.get("DATA_DIR"))
        return jsonify({
            "status": "ONLINE",
            "version": "1.0.0",
            "cuda_available": cuda_available,
            "device": device_name,
            "total_matches": data.get("total_matches", 0),
            "teams_count": data.get("teams_count", 0),
        })

    @app.route("/api/audit", methods=["POST"])
    def api_audit():
        """Executes a full Game-Theoretic tactical audit (All-Turns + Turning Point + Uncertainty)."""
        body = request.get_json(silent=True) or {}
        raw_log = body.get("log", "") or body.get("raw_log", "")
        persist = bool(body.get("persist", False))
        device_pref = body.get("device", None)
        if not raw_log:
            demo_path = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"
            raw_log = demo_path.read_text(encoding="utf-8") if demo_path.exists() else ""
        from engine.tactics.tactical_pipeline import TacticalPipeline
        pipeline = TacticalPipeline(device=device_pref)
        result = pipeline.run_audit(raw_log, auto_persist=persist)
        return jsonify(result.to_dict())

    @app.route("/api/gpu-matrix", methods=["POST"])
    def api_gpu_matrix():
        """Evaluates the GPU payoff matrix, Nash equilibrium, and UncertaintyProfile for a turn."""
        body = request.get_json(silent=True) or {}
        raw_log = body.get("log", "") or body.get("raw_log", "")
        turn_num = body.get("turn", None)
        device_pref = body.get("device", None)
        if not raw_log:
            demo_path = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"
            raw_log = demo_path.read_text(encoding="utf-8") if demo_path.exists() else ""
        from engine.tactics.tactical_pipeline import TacticalPipeline
        pipeline = TacticalPipeline(device=device_pref)
        parsed = pipeline.parser.parse_log(raw_log)
        target_snap = parsed.turns[0] if parsed.turns else None
        if turn_num is not None:
            for snap in parsed.turns:
                if snap.turn_number == int(turn_num):
                    target_snap = snap
                    break
        elif parsed.turns:
            tp = pipeline.detector.detect(parsed)
            target_snap = tp.snapshot
        if target_snap is None:
            return jsonify({"error": "No valid turns found in battle log"}), 400
        turn_eval = pipeline.solve_turn(target_snap, total_turns=len(parsed.turns))
        return jsonify(turn_eval.to_dict())

    @app.route("/api/report/<string:audit_id>", methods=["GET"])
    def api_report(audit_id: str):
        """Renders a print-ready HTML tactical audit report for a stored or demo audit ID."""
        import html
        from engine.ui_generator import render_tactical_audit_html
        clean_id = html.escape(re.sub(r"[^a-zA-Z0-9_\-]", "", audit_id))
        audit_dict = None
        data = load_live_telemetry(data_dir=app.config.get("DATA_DIR"))
        for entry in data.get("tactical_audits", []):
            if str(entry.get("audit_id", "")) == clean_id:
                audit_dict = entry
                break
        if audit_dict is None:
            demo_path = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"
            raw_log = demo_path.read_text(encoding="utf-8") if demo_path.exists() else ""
            from engine.tactics.tactical_pipeline import TacticalPipeline
            pipeline = TacticalPipeline()
            res = pipeline.run_audit(raw_log, auto_persist=False)
            audit_dict = res.to_dict()
            if clean_id:
                audit_dict["audit_id"] = clean_id
        html_doc = render_tactical_audit_html(audit_dict)
        return Response(html_doc, mimetype="text/html; charset=utf-8")

    @app.route("/api/benchmark", methods=["GET", "POST"])
    def api_benchmark():
        """Runs the vectorized PyTorch GPU/CPU payoff matrix benchmark and returns telemetry."""
        body = request.get_json(silent=True) or {}
        batch_size = int(body.get("batch_size", 32))
        device_pref = body.get("device", None)
        demo_path = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"
        raw_log = body.get("log") or (demo_path.read_text(encoding="utf-8") if demo_path.exists() else "")
        from engine.tactics.tactical_pipeline import TacticalPipeline
        pipeline = TacticalPipeline(device=device_pref)
        metrics = pipeline.run_benchmark(raw_log=raw_log, batch_size=batch_size)
        return jsonify(metrics)

    @app.route("/api/meta/feed", methods=["GET"])
    def api_meta_feed():
        """Returns live tournament metagame intelligence feed across all regional tournaments."""
        from engine.db import UnifiedCoachDatabase
        db_inst = UnifiedCoachDatabase()
        feed = db_inst.get_meta_feed(data_dir=app.config.get("DATA_DIR"))
        db_inst.close()
        return jsonify(feed)

    @app.route("/api/meta/threats", methods=["GET"])
    def api_meta_threats():
        """Returns unsupervised neural autoencoder + clustering metagame threats from in-memory SQLite."""
        from engine.db import UnifiedCoachDatabase
        limit = int(request.args.get("limit", 20))
        db_inst = UnifiedCoachDatabase()
        threats = db_inst.get_unsupervised_threats(limit=limit)
        archetypes = db_inst.get_unsupervised_archetypes(limit=8)
        benchmarks = db_inst.get_speed_benchmarks(limit=16)
        db_inst.close()
        return jsonify({
            "status": "OK",
            "storage_engine": "sqlite3(:memory:) <- data/munchstats_threats.jsonl",
            "model": "Unsupervised Neural Autoencoder (16->10->4->10->16) + K-Means Clustering",
            "count": len(threats),
            "threats": threats,
            "archetypes": archetypes,
            "speed_benchmarks": benchmarks,
        })

    @app.route("/api/flashcards/enhanced", methods=["GET"])
    def api_flashcards_enhanced():
        """Returns 50 persistent flashcards enriched with 4-slot board state and payoff simulation logs."""
        from engine.db import UnifiedCoachDatabase
        db_inst = UnifiedCoachDatabase()
        cards = db_inst.get_enhanced_flashcards(data_dir=app.config.get("DATA_DIR"))
        db_inst.close()
        return jsonify({"status": "OK", "count": len(cards), "flashcards": cards})

    @app.route("/api/calc/spread", methods=["GET", "POST"])
    def api_calc_spread():
        """
        Calculates Regulation M-C Level 50 stats, Speed Ladder ranking,
        and 16+ real-time offensive and defensive damage calculations vs top meta threats.
        """
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
        else:
            payload = request.args.to_dict()
        result = compute_comprehensive_spread_analytics(payload)
        return jsonify(result)

    return app


# Global Flask application instance
app = create_app()


class CoachPorygonHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """
    Backward-compatible REST API and static file handler for Coach Porygon Command Center.
    Maintained for unit tests that dispatch simulated requests through in-memory MockSockets.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def end_headers(self):
        """Inject strict CORS headers allowing only localhost and local file execution (SEC-02)."""
        origin = self.headers.get("Origin", "")
        if origin:
            clean_origin = origin.replace("\r", "").replace("\n", "").strip()
            if clean_origin.lower() == "null":
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            elif clean_origin.startswith("vscode-webview://"):
                self.send_header("Access-Control-Allow-Origin", clean_origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            else:
                try:
                    parsed_origin = urllib.parse.urlsplit(clean_origin)
                    scheme = (parsed_origin.scheme or "").lower()
                    hostname = (parsed_origin.hostname or "").lower()
                    port = parsed_origin.port
                    if scheme in ("http", "https") and hostname in ("localhost", "127.0.0.1"):
                        safe_origin = f"{scheme}://{hostname}" + (f":{port}" if port is not None else "")
                        self.send_header("Access-Control-Allow-Origin", safe_origin)
                        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                        self.send_header("Access-Control-Allow-Headers", "Content-Type")
                except Exception:
                    pass
        else:
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        """Respond to preflight CORS checks."""
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        """Handle GET requests for static Command Center assets and telemetry API (SEC-03)."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Sensitive Resource & Path Traversal Shield (SEC-03)
        path_lower = path.lower()
        if any(res in path_lower for res in RESTRICTED_PATH_PATTERNS) or "/." in path_lower:
            self.send_error(403, "Access Denied: Restricted System Resource")
            return

        if path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/assets/command_center.html")
            self.end_headers()
            return
        if path == "/es":
            self.send_response(302)
            self.send_header("Location", "/assets/command_center_es.html")
            self.end_headers()
            return
        if path == "/en":
            self.send_response(302)
            self.send_header("Location", "/assets/command_center_en.html")
            self.end_headers()
            return

        if path.startswith("/api/sprites/"):
            species_raw = path.replace("/api/sprites/", "").split("?")[0].strip()
            clean_raw = re.sub(r"\.(?:png|svg|webp|jpe?g)$", "", species_raw, flags=re.I)
            clean_species = re.sub(r"[^a-zA-Z0-9_\-() ]", "", clean_raw.replace("+", " ")).strip()
            params = urllib.parse.parse_qs(parsed.query)
            is_shiny = "shiny" in params and params["shiny"][0].lower() in ("1", "true")
            sprite_file = resolve_sprite_path(clean_species, is_shiny=is_shiny)
            assets_canon = ASSETS_DIR.resolve()
            if sprite_file and sprite_file.is_file():
                canon_sprite = sprite_file.resolve()
                if os.path.commonpath([str(assets_canon), str(canon_sprite)]) == str(assets_canon):
                    manifest = get_asset_manifest()
                    rel_key = canon_sprite.relative_to(REPO_ROOT).as_posix()
                    digest = manifest.get("sha256_digests", {}).get(rel_key)
                    if not digest:
                        digest = hashlib.sha256(canon_sprite.read_bytes()).hexdigest()
                    etag = f'"{digest}"'

                    if_none_match = self.headers.get("If-None-Match")
                    if if_none_match and etag in if_none_match:
                        self.send_response(304)
                        self.send_header("ETag", etag)
                        self.send_header("Cache-Control", "public, max-age=86400")
                        self.end_headers()
                        return

                    payload = canon_sprite.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("ETag", etag)
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
            svg_code = generate_anatomical_battle_crest_svg(clean_species).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(svg_code)))
            self.end_headers()
            self.wfile.write(svg_code)
            return

        if path == "/api/health":
            data = load_live_telemetry()
            payload = json.dumps({
                "status": "UP",
                "version": "1.0.0",
                "total_matches": data.get("total_matches", 0),
                "teams_count": data.get("teams_count", 0),
                "scouted_count": len(data.get("scouted", [])),
                "tournaments_count": len(data.get("tournaments", [])),
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/munchstats/data":
            data = load_live_telemetry()
            payload = json.dumps({
                "tournaments": data.get("tournaments", []),
                "overview": data.get("munchstats_overview", []),
                "usage": data.get("munchstats_usage", []),
                "top_teams": data.get("munchstats_top_teams", []),
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/meta/feed":
            from engine.db import UnifiedCoachDatabase
            db_inst = UnifiedCoachDatabase()
            feed = db_inst.get_meta_feed()
            db_inst.close()
            payload = json.dumps(feed, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path.startswith("/api/meta/threats"):
            from engine.db import UnifiedCoachDatabase
            params = urllib.parse.parse_qs(parsed.query)
            limit = int(params.get("limit", [20])[0])
            db_inst = UnifiedCoachDatabase()
            threats = db_inst.get_unsupervised_threats(limit=limit)
            archetypes = db_inst.get_unsupervised_archetypes(limit=8)
            benchmarks = db_inst.get_speed_benchmarks(limit=16)
            db_inst.close()
            payload = json.dumps({
                "status": "OK",
                "storage_engine": "sqlite3(:memory:) <- data/munchstats_threats.jsonl",
                "model": "Unsupervised Neural Autoencoder (16->10->4->10->16) + K-Means Clustering",
                "count": len(threats),
                "threats": threats,
                "archetypes": archetypes,
                "speed_benchmarks": benchmarks,
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/flashcards/enhanced":
            from engine.db import UnifiedCoachDatabase
            db_inst = UnifiedCoachDatabase()
            cards = db_inst.get_enhanced_flashcards()
            db_inst.close()
            payload = json.dumps({"status": "OK", "count": len(cards), "flashcards": cards}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path.startswith("/api/calc/spread"):
            params = urllib.parse.parse_qs(parsed.query)
            payload_dict = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
            result = compute_comprehensive_spread_analytics(payload_dict)
            payload = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/telemetry":
            data = load_live_telemetry()
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        super().do_GET()

    def do_POST(self):
        """Handle POST actions for ingestion, crawling, and cache syncing (SEC-06)."""
        parsed = urllib.parse.urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0) or 0)

        # DoS Shield: Cap request body size at 5 MB (SEC-06)
        if content_len > MAX_POST_BODY_BYTES:
            self.send_error(413, f"Payload Too Large: Exceeds {MAX_POST_BODY_BYTES} byte limit")
            return

        body_raw = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            body = json.loads(body_raw)
        except Exception:
            body = {}

        if parsed.path == "/api/calc/spread":
            result = compute_comprehensive_spread_analytics(body)
            payload = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/api/munchstats/crawl":
            prompt_q = body.get("prompt", "") or body.get("tournament_id", "Nice 2027")
            result = execute_prompt_crawl_and_dump(prompt_q, export_csv=True)
            payload = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/api/sync":
            telemetry = load_live_telemetry()
            (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
            msg = {"status": "SYNCED", "telemetry": telemetry}
            payload = json.dumps(msg, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/api/telemetry/ingest":
            try:
                import telemetry as tel_module
                m_id = body.get("id", f"M{(len(load_live_telemetry().get('raw_matches', [])) + 1)}")
                opp = body.get("opponent", "Competitive Opponent")
                res = body.get("result", "Win")
                turns = float(body.get("turns", 5))
                row = {
                    "Timestamp": datetime.now(timezone.utc).isoformat(),
                    "Match_ID": m_id,
                    "Team_ID": body.get("team_id", "T01"),
                    "Opponent": opp,
                    "Start_Rating": "1500",
                    "End_Rating": "1515" if res.lower() == "win" else "1485",
                    "Net_Rating": "15" if res.lower() == "win" else "-15",
                    "Result": res,
                    "Turns": turns,
                    "Enemy_Archetype": body.get("archetype", "Goodstuff / Balance"),
                    "User_Mega": body.get("user_mega", "Charizard-Mega-Y"),
                    "Enemy_Mega": body.get("enemy_mega", "Kangaskhan-Mega"),
                    "User_Lead_1": "Charizard",
                    "User_Lead_2": "Indeedee-F",
                    "User_Back_1": "Armarouge",
                    "User_Back_2": "Kingambit",
                    "Enemy_Lead_1": "Incineroar",
                    "Enemy_Lead_2": "Rillaboom",
                    "Speed_Control_Active": "None",
                    "First_Blood_Side": "User" if res.lower() == "win" else "Enemy",
                    "MVP_Pokemon": "Charizard-Mega-Y" if res.lower() == "win" else "None",
                    "MVP_Move": "Heat Wave" if res.lower() == "win" else "None",
                    "Misplay_Type": "None" if res.lower() == "win" else "POS-01",
                    "Key_RNG_Event": "None",
                    "Core_Lesson": f"Telemetry Live Log for {m_id}",
                    "Commentary": body.get("notes", "Ingested via Coach Porygon Web Interface"),
                }
                tel_module.append_csv_row(DATA_DIR / "Raw_Matches.csv", tel_module.RAW_MATCHES_COLS, row)
            except Exception as e:
                print(f"[WARN] Ingest error: {e}")

            fresh = load_live_telemetry()
            (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(fresh, indent=2), encoding="utf-8")
            msg = {"status": "INGESTED", "telemetry": fresh}
            payload = json.dumps(msg, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/api/scouted/ingest":
            try:
                scouted_path = DATA_DIR / "Scouted_Teams.csv"
                existing = []
                if scouted_path.exists():
                    with open(scouted_path, "r", encoding="utf-8") as f:
                        existing = list(csv.DictReader(f))
                new_id = body.get("id") or f"ST{str(len(existing) + 1).zfill(2)}"
                mons = body.get("mons", [])
                while len(mons) < 6:
                    mons.append("")
                row = {
                    "Scouted_Team_ID": new_id,
                    "Player_Name": body.get("player", "Unknown Player"),
                    "Tournament": body.get("tournament", "Custom OTS Session"),
                    "Date_Scouted": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "Placement": body.get("placement", "Ingesta en Sesión"),
                    "Pokemon_1": mons[0],
                    "Pokemon_2": mons[1],
                    "Pokemon_3": mons[2],
                    "Pokemon_4": mons[3],
                    "Pokemon_5": mons[4],
                    "Pokemon_6": mons[5],
                    "Showdown_Export": body.get("export", ""),
                    "Archetype": body.get("archetype", "Balance"),
                    "Notes": body.get("notes", "Ingested via Command Center Web"),
                }
                with open(scouted_path, "a", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        "Scouted_Team_ID", "Player_Name", "Tournament", "Date_Scouted",
                        "Placement", "Pokemon_1", "Pokemon_2", "Pokemon_3",
                        "Pokemon_4", "Pokemon_5", "Pokemon_6", "Showdown_Export",
                        "Archetype", "Notes"
                    ])
                    writer.writerow(row)
            except Exception as e:
                print(f"[WARN] Scouted ingest error: {e}")

            fresh = load_live_telemetry()
            (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(fresh, indent=2), encoding="utf-8")
            msg = {"status": "INGESTED", "team_id": new_id, "telemetry": fresh}
            payload = json.dumps(msg, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_error(404, "Endpoint Not Found")


def run_server(host: str = DEFAULT_HOST, port: int = PORT):
    """Initialize and run Flask web server on specified host and port (SEC-01 Protected)."""
    print("=================================================================")
    print("  COACH PORYGON VGC — BILINGUAL FLASK WEB SERVER (REG M-C)       ")
    print("=================================================================")
    print(f"  Bound Interface:      http://{host}:{port}/ (SEC-01 Protected)")
    print(f"  Main App (Bilingual): http://{host}:{port}/assets/command_center.html")
    print(f"  Spanish Version (ES): http://{host}:{port}/es")
    print(f"  English Version (EN): http://{host}:{port}/en")
    print(f"  Live Telemetry API:   http://{host}:{port}/api/telemetry")
    print(f"  MunchStats Crawler:   http://{host}:{port}/api/munchstats/crawl")
    print(f"  Dynamic Sprites API:  http://{host}:{port}/api/sprites/<species>")
    print("=================================================================")

    data = load_live_telemetry()
    (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    n_m, n_c, n_p = data["total_matches"], data["total_calcs"], len(data["pokedex"])
    print(f"[READY] Loaded {n_m} matches, {n_c} calcs, {n_p} Pokédex species.")

    app.run(host=host, port=port, debug=False, use_reloader=False)


def main():
    """CLI Entry point for Coach Porygon Flask server."""
    parser = argparse.ArgumentParser(description="Coach Porygon VGC Flask Server & API Backend")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port number (default: {PORT})")
    args, unknown = parser.parse_known_args()
    cli_port = args.port
    if unknown and unknown[0].isdigit():
        cli_port = int(unknown[0])
    run_server(host=args.host, port=cli_port)


if __name__ == "__main__":
    main()
