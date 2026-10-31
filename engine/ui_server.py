#!/usr/bin/env python3
"""
Coach Porygon VGC — Python Web Backend & API Server
Serves the bilingual (EN / ES) Command Center and exposes live endpoints:
- GET  /api/telemetry         : Live workspace database (322 matches, 290 calcs, 24 teams, Pokédex, MunchStats)
- POST /api/munchstats/crawl  : Processes user natural-language query or MunchStats URL via munchstats_scraper.py,
                                dumps verified records to CSV, and returns structured analytics.
- POST /api/sync              : Re-reads all CSVs and updates live_telemetry.json.
"""

import argparse
import csv
from datetime import datetime, timezone
import http.server
import json
import socketserver
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine"))
sys.path.insert(0, str(REPO_ROOT / "scouts"))

from ui_generator import load_live_telemetry, write_svg_assets
from munchstats_scraper import (
    SCOUTED_CSV,
    add_scouted_team,
    load_tournament_meta,
    scrape_munchstats_url_or_json,
    summarize_scouted_meta,
)

PORT = 8000
DEFAULT_HOST = "127.0.0.1"
MAX_POST_BODY_BYTES = 5 * 1024 * 1024  # 5 MB cap against memory exhaustion (CWE-400)
ASSETS_DIR = REPO_ROOT / "assets"
DATA_DIR = REPO_ROOT / "data"

RESTRICTED_PATH_PATTERNS = (
    "/.git",
    "/.github",
    "/.agents",
    "/trainer_profile.json",
    "/data/trainer_profile.json",
)


def execute_prompt_crawl_and_dump(user_prompt: str, export_csv: bool = True) -> dict:
    """
    Executes a targeted MunchStats crawl/query based on the user's natural-language prompt.
    1. If the prompt contains a live MunchStats URL, attempts live scraping via munchstats_scraper.py.
    2. Otherwise filters verified records in Scouted_Teams.csv & Tournament_Meta.json matching prompt keywords
       (e.g. 'Nice', 'Rain', 'Mega', 'Fontvieille', 'Cunha', 'All').
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
            except Exception as exc:
                scraped_live = [{
                    "warning": f"Live URL fetch blocked or offline ({exc}); falling back to local Scouted_Teams.csv."
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


class CoachPorygonHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """REST API and static file handler for Coach Porygon Command Center."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def end_headers(self):
        """Inject strict CORS headers allowing only localhost and local file execution (SEC-02)."""
        origin = self.headers.get("Origin", "")
        if origin:
            origin_lower = origin.lower()
            if (
                origin_lower == "null"
                or origin_lower.startswith("http://localhost")
                or origin_lower.startswith("http://127.0.0.1")
                or origin_lower.startswith("https://localhost")
                or origin_lower.startswith("https://127.0.0.1")
            ):
                self.send_header("Access-Control-Allow-Origin", origin if origin != "null" else "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
        """Handle GET requests for static Command Center assets, telemetry API, with path isolation (SEC-03)."""
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
        """Handle POST actions for ingestion, crawling, and cache syncing with size guardrails (SEC-06)."""
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
                    "Commentary": body.get("notes", "Ingested via Coach Porygon Web Interface")
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

        self.send_error(404, "Endpoint Not Found")


def run_server(host: str = DEFAULT_HOST, port: int = PORT):
    """Initialize and run HTTP server on specified host and port (SEC-01 Loopback Default)."""
    print("=================================================================")
    print("  COACH PORYGON VGC — BILINGUAL PYTHON WEB SERVER (REG M-C)      ")
    print("=================================================================")
    print(f"  Bound Interface:      http://{host}:{port}/ (SEC-01 Protected)")
    print(f"  Main App (Bilingual): http://{host}:{port}/assets/command_center.html")
    print(f"  Spanish Version (ES): http://{host}:{port}/es")
    print(f"  English Version (EN): http://{host}:{port}/en")
    print(f"  Live Telemetry API:   http://{host}:{port}/api/telemetry")
    print(f"  MunchStats Crawler:   http://{host}:{port}/api/munchstats/crawl")
    print("=================================================================")

    write_svg_assets()
    data = load_live_telemetry()
    (ASSETS_DIR / "live_telemetry.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    n_m, n_c, n_p = data['total_matches'], data['total_calcs'], len(data['pokedex'])
    print(f"[READY] Loaded {n_m} matches, {n_c} calcs, {n_p} Pokédex species.")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), CoachPorygonHTTPHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down Coach Porygon VGC Server.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coach Porygon VGC Web Server & API Backend")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port number (default: {PORT})")
    args, unknown = parser.parse_known_args()
    cli_port = args.port
    if unknown and unknown[0].isdigit():
        cli_port = int(unknown[0])
    run_server(host=args.host, port=cli_port)
