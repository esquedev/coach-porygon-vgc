#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — MunchStats crawler and SQLite ingestion pipeline.

Runtime philosophy:
- Crawl raw tournament data from MunchStats
- Normalize into canonical SQLite tables
- Optionally archive raw JSON for provenance/debugging
- Do not write Scouted_Teams.csv or Showdown exports in the production path
"""

import argparse
import json
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

from munchstats_db import connect, init_schema, upsert_standing, upsert_stage, upsert_team_slot, upsert_tournament, upsert_usage

DATA_DIR = REPO_ROOT / "data"
MUNCHSTATS_DATA_DIR = DATA_DIR / "munchstats"
RAW_ARCHIVE_DIR = MUNCHSTATS_DATA_DIR / "raw" / "archive"
MUNCHSTATS_DB_PATH = MUNCHSTATS_DATA_DIR / "munchstats.db"
MUNCHSTATS_BASE_URL = "https://www.munchstats.com"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CoachPorygonVGC/1.0"

def extract_tournament_id(url_or_id: str) -> str:
    clean = url_or_id.strip()
    match = re.search(r"/tournaments/([^/?#]+)", clean)
    if match:
        return match.group(1)
    token = clean.strip("/").split("/")[-1]
    if token in ("all", "day1", "day2", "top8", "top16"):
        parts = [p for p in clean.strip("/").split("/") if p]
        if len(parts) >= 2:
            return parts[-2]
    return token

def fetch_url(url: str, timeout: int = 15, headers: Optional[Dict[str, str]] = None) -> Tuple[int, bytes]:
    h = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json, text/html"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read()

def crawl_tournament_overview(tournament_id: str) -> Dict[str, Any]:
    url = f"{MUNCHSTATS_BASE_URL}/tournaments/{urllib.parse.quote(tournament_id)}/all/"
    status, html_bytes = fetch_url(url)
    html_text = html_bytes.decode("utf-8", errors="ignore")

    overview: Dict[str, Any] = {
        "tournament_id": tournament_id,
        "url": url,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "tournament_name": "",
        "total_players": 0,
        "stages": [],
        "movers": [],
    }

    title_match = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html_text)
    if not title_match:
        title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE)
    if title_match:
        raw_title = title_match.group(1).strip()
        parts = [p.strip() for p in raw_title.split("|")]
        overview["tournament_name"] = parts[-1] if parts else raw_title

    desc_match = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html_text)
    if desc_match:
        desc_text = desc_match.group(1)
        m = re.search(r"(\\d+)\\s+teams", desc_text)
        if m:
            overview["total_players"] = int(m.group(1))

    hub_m = re.search(r"window\\.hubOverview\\s*=\\s*(.*?);(?=\\s*window\\.|\\s*</script>)", html_text, re.DOTALL)
    if hub_m:
        try:
            hub_data = json.loads(hub_m.group(1))
            overview["stages"] = hub_data.get("stages", [])
            overview["movers"] = hub_data.get("movers", [])
            if not overview["total_players"] and overview["stages"]:
                for st in overview["stages"]:
                    if st.get("label") == "Day 1" and st.get("total_teams"):
                        overview["total_players"] = st.get("total_teams")
        except json.JSONDecodeError:
            pass

    return overview

def crawl_tournament_standings(tournament_id: str, day_filter: str = "all") -> List[Dict[str, Any]]:
    url = f"{MUNCHSTATS_BASE_URL}/tournaments/api/{urllib.parse.quote(tournament_id)}/standings?day={urllib.parse.quote(day_filter)}"
    status, payload = fetch_url(url)
    data = json.loads(payload.decode("utf-8"))
    if isinstance(data, list):
        return data
    return []

def crawl_tournament_usage(tournament_id: str, day_filter: str = "all") -> Dict[str, Any]:
    url = f"{MUNCHSTATS_BASE_URL}/tournaments/api/{urllib.parse.quote(tournament_id)}/{urllib.parse.quote(day_filter)}/"
    status, payload = fetch_url(url)
    return json.loads(payload.decode("utf-8"))

def archive_raw_json(tournament_id: str, overview: Dict[str, Any], standings: List[Dict[str, Any]], usage: Dict[str, Any]) -> Path:
    t_name = overview.get("tournament_name") or f"Tournament {tournament_id}"
    slug = re.sub(r"[^a-zA-Z0-9_\\-]+", "_", t_name.lower().replace(" ", "_")).strip("_")
    if not slug:
        slug = tournament_id.lower()

    target_dir = RAW_ARCHIVE_DIR / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "overview.json").write_text(json.dumps(overview, indent=2, ensure_ascii=False), encoding="utf-8")
    (target_dir / "standings.json").write_text(json.dumps(standings, indent=2, ensure_ascii=False), encoding="utf-8")
    (target_dir / "usage.json").write_text(json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8")

    return target_dir

def ingest_tournament_to_sqlite(
    tournament_id: str,
    db_path: str | Path = MUNCHSTATS_DB_PATH,
    archive_raw_json_flag: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    if verbose:
        print(f"[*] Starting MunchStats ingest for {tournament_id}")

    overview = crawl_tournament_overview(tournament_id)
    standings = crawl_tournament_standings(tournament_id, day_filter="all")
    usage_all = crawl_tournament_usage(tournament_id, day_filter="all")

    if archive_raw_json_flag:
        archive_dir = archive_raw_json(tournament_id, overview, standings, usage_all)
        if verbose:
            print(f"  [+] Archived raw JSON under: {archive_dir}")

    conn = connect(db_path)
    init_schema(conn)

    upsert_tournament(conn, overview)

    for stage in overview.get("stages", []):
        upsert_stage(conn, tournament_id, stage)

    for entry in standings:
        upsert_standing(conn, tournament_id, entry)

        for idx, slot in enumerate(entry.get("team") or []):
            upsert_team_slot(conn, tournament_id, entry.get("name") or "", idx, slot)

    day_options = usage_all.get("day_options", ["all"])
    phase_usage = {"all": usage_all}
    for day in day_options:
        if day == "all":
            continue
        try:
            phase_usage[day] = crawl_tournament_usage(tournament_id, day_filter=day)
        except Exception:
            pass

    for phase, payload in phase_usage.items():
        for item in payload.get("pokemon_names", []):
            if len(item) < 2:
                continue
            species = str(item[0])
            count = int(item[1]) if isinstance(item[1], (int, float)) else 0
            usage_pct = float(item[1]) if isinstance(item[1], (int, float)) else 0.0
            upsert_usage(conn, tournament_id, phase, species, count, usage_pct)

    conn.commit()
    conn.close()

    return {
        "status": "SUCCESS",
        "tournament_id": tournament_id,
        "tournament_name": overview.get("tournament_name", ""),
        "db_path": str(db_path),
        "archive_dir": str(RAW_ARCHIVE_DIR / re.sub(r"[^a-zA-Z0-9_\\-]+", "_", (overview.get("tournament_name") or f"Tournament {tournament_id}").lower().replace(" ", "_")).strip("_") or tournament_id.lower()),
    }

def main():
    parser = argparse.ArgumentParser(description="MunchStats SQLite ingestion")
    parser.add_argument("--tournament-id", "-t", type=str, required=True)
    parser.add_argument("--db-path", "-d", type=str, default=str(MUNCHSTATS_DB_PATH))
    parser.add_argument("--no-archive", action="store_true")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    result = ingest_tournament_to_sqlite(
        tournament_id=args.tournament_id,
        db_path=args.db_path,
        archive_raw_json_flag=not args.no_archive,
        verbose=not args.quiet,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
