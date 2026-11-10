#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coach Porygon VGC — MunchStats Tournament Crawler & DuckDB NDJSON Ingestor.

Downloads tournament overview, standings/rosters, and usage payloads from MunchStats,
writes normalized NDJSON (`.jsonl`) archives directly into
`src/engine/data/munchstats/raw/archive/<tournament_slug>/`, and verifies the
ingested dataset immediately through the in-memory DuckDB `VGCDataRegistry`.

Replaces the legacy SQLite (`munchstats.db`) ingestion pipeline completely.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request

ENGINE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ENGINE_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.db_registry import VGCDataRegistry

DATA_DIR = ENGINE_DIR / "data"
MUNCHSTATS_DATA_DIR = DATA_DIR / "munchstats"
RAW_ARCHIVE_DIR = MUNCHSTATS_DATA_DIR / "raw" / "archive"
MUNCHSTATS_BASE_URL = "https://www.munchstats.com"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CoachPorygonVGC/2.0"


def extract_tournament_id(url_or_id: str) -> str:
    """Extract canonical MunchStats tournament token from a URL or ID string."""
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


def fetch_url(
    url: str,
    timeout: int = 15,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes]:
    """Perform an HTTP GET request with Coach Porygon user agent headers."""
    req_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/html",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read()


def crawl_tournament_overview(tournament_id: str) -> Dict[str, Any]:
    """Crawl tournament HTML overview and extract metadata and stage counts."""
    url = f"{MUNCHSTATS_BASE_URL}/tournaments/{urllib.parse.quote(tournament_id)}/all/"
    _, html_bytes = fetch_url(url)
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

    title_match = re.search(
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html_text
    )
    if not title_match:
        title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE)
    if title_match:
        raw_title = title_match.group(1).strip()
        parts = [p.strip() for p in raw_title.split("|")]
        overview["tournament_name"] = parts[-1] if parts else raw_title

    desc_match = re.search(
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html_text
    )
    if desc_match:
        desc_text = desc_match.group(1)
        m = re.search(r"(\d+)\s+teams", desc_text)
        if m:
            overview["total_players"] = int(m.group(1))

    hub_m = re.search(
        r"window\.hubOverview\s*=\s*(.*?);(?=\s*window\.|\s*</script>)",
        html_text,
        re.DOTALL,
    )
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


def crawl_tournament_standings(
    tournament_id: str, day_filter: str = "all"
) -> List[Dict[str, Any]]:
    """Crawl full player standings and 6-Pokémon rosters from MunchStats API."""
    url = (
        f"{MUNCHSTATS_BASE_URL}/tournaments/api/"
        f"{urllib.parse.quote(tournament_id)}/standings?day={urllib.parse.quote(day_filter)}"
    )
    _, payload = fetch_url(url)
    data = json.loads(payload.decode("utf-8"))
    return data if isinstance(data, list) else []


def crawl_tournament_usage(
    tournament_id: str, day_filter: str = "all"
) -> Dict[str, Any]:
    """Crawl usage summary payload from MunchStats API."""
    url = (
        f"{MUNCHSTATS_BASE_URL}/tournaments/api/"
        f"{urllib.parse.quote(tournament_id)}/{urllib.parse.quote(day_filter)}/"
    )
    _, payload = fetch_url(url)
    return json.loads(payload.decode("utf-8"))


def _write_ndjson(
    data: Any,
    output_path: Path,
    key_field_name: str = "species",
    extra_fields: Optional[Dict[str, Any]] = None,
) -> int:
    """Serialize a dict or list payload into normalized NDJSON (`.jsonl`) for DuckDB."""
    count = 0
    with open(output_path, "w", encoding="utf-8") as out:
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, dict):
                    row = dict(val)
                    if key_field_name not in row:
                        row[key_field_name] = key
                else:
                    row = {key_field_name: key, "value": val}
                if extra_fields:
                    row.update(extra_fields)
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    row = dict(item)
                    if extra_fields:
                        row.update(extra_fields)
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1
    return count


def archive_tournament_jsonl(
    tournament_id: str,
    overview: Dict[str, Any],
    standings: List[Dict[str, Any]],
    usage: Dict[str, Any],
    archive_root: Path = RAW_ARCHIVE_DIR,
) -> Tuple[str, Path]:
    """Write `overview.jsonl`, `standings.jsonl`, and `usage.jsonl` for DuckDB auto-globbing."""
    t_name = overview.get("tournament_name") or f"Tournament {tournament_id}"
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", t_name.lower().replace(" ", "_")).strip("_")
    if not slug:
        slug = tournament_id.lower()

    target_dir = archive_root / slug
    target_dir.mkdir(parents=True, exist_ok=True)
    extra = {"tournament_id": slug}

    _write_ndjson(overview, target_dir / "overview.jsonl", key_field_name="species", extra_fields=extra)
    _write_ndjson(standings, target_dir / "standings.jsonl", key_field_name="species", extra_fields=extra)
    _write_ndjson(usage, target_dir / "usage.jsonl", key_field_name="species", extra_fields=extra)

    return slug, target_dir


def ingest_tournament_to_duckdb_archive(
    tournament_id: str,
    archive_root: Path = RAW_ARCHIVE_DIR,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Crawl a MunchStats tournament, save as `.jsonl`, and verify via in-memory DuckDB."""
    clean_id = extract_tournament_id(tournament_id)
    if verbose:
        print(f"[*] Starting MunchStats NDJSON crawl for '{clean_id}'...")

    overview = crawl_tournament_overview(clean_id)
    standings = crawl_tournament_standings(clean_id, day_filter="all")
    usage_all = crawl_tournament_usage(clean_id, day_filter="all")

    slug, target_dir = archive_tournament_jsonl(
        clean_id,
        overview=overview,
        standings=standings,
        usage=usage_all,
        archive_root=archive_root,
    )
    if verbose:
        print(f"  [+] Wrote normalized NDJSON archive: {target_dir}")

    # Mount in-memory DuckDB registry and verify the ingested rows
    registry = VGCDataRegistry()
    team_cnt_rows = registry.query(
        "SELECT COUNT(*) AS n FROM tournament_standings WHERE tournament_id = ?;",
        (slug,),
    )
    top_species_rows = registry.query(
        """
        SELECT species, COUNT(*) AS appearances
        FROM tournament_team_slots
        WHERE tournament_id = ?
        GROUP BY species
        ORDER BY appearances DESC
        LIMIT 5;
        """,
        (slug,),
    )

    return {
        "status": "SUCCESS",
        "tournament_id": clean_id,
        "tournament_slug": slug,
        "tournament_name": overview.get("tournament_name", ""),
        "archive_dir": str(target_dir),
        "duckdb_verified_teams": int(team_cnt_rows[0]["n"]) if team_cnt_rows else 0,
        "duckdb_top_species": top_species_rows,
    }


def main() -> None:
    """CLI entry point for MunchStats NDJSON + DuckDB tournament ingestion."""
    parser = argparse.ArgumentParser(
        description="Crawl MunchStats tournament into DuckDB NDJSON archive"
    )
    parser.add_argument(
        "--tournament-id",
        "-t",
        type=str,
        required=True,
        help="MunchStats tournament URL or ID token",
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    result = ingest_tournament_to_duckdb_archive(
        tournament_id=args.tournament_id,
        verbose=not args.quiet,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
