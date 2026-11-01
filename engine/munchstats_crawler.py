#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — MunchStats Tournament Crawler & Raw Ingestion Engine

Extracts complete competitive data from www.munchstats.com tournament hubs:
1. Tournament overview, metadata, stages (Day 1, Day 2, Top Cut), and net movers.
2. Complete usage ranking across phases (All, Day 1, Day 2, Top Cut).
3. Full competitor standings and 6-mon Open Team Sheet rosters with full sets.
4. Curates and registers highest-impact teams into data/Scouted_Teams.csv.

Follows SOLID Principles, OWASP CSV Injection Sanitization, and zero-hallucination standards.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "engine"))

try:
    from engine.repositories import get_excel_serial_timestamp, sanitize_csv_cell
except ImportError:
    from repositories import get_excel_serial_timestamp, sanitize_csv_cell  # type: ignore

DATA_DIR = REPO_ROOT / "data"
SCOUTED_TEAMS_CSV = DATA_DIR / "Scouted_Teams.csv"
MUNCHSTATS_BASE_URL = "https://www.munchstats.com"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CoachPorygonVGC/1.0"


def extract_tournament_id(url_or_id: str) -> str:
    """
    Extracts the canonical tournament identifier from a MunchStats URL or string.

    Examples:
        'https://www.munchstats.com/tournaments/BA002-JL3KVbvivVKNAc/all/' -> 'BA002-JL3KVbvivVKNAc'
        'BA002-JL3KVbvivVKNAc' -> 'BA002-JL3KVbvivVKNAc'
    """
    clean = url_or_id.strip()
    match = re.search(r"/tournaments/([^/?#]+)", clean)
    if match:
        return match.group(1)
    # Direct ID or path token
    token = clean.strip("/").split("/")[-1]
    if token in ("all", "day1", "day2", "top8", "top16"):
        parts = [p for p in clean.strip("/").split("/") if p]
        if len(parts) >= 2:
            return parts[-2]
    return token


def fetch_url(url: str, timeout: int = 15, headers: Optional[Dict[str, str]] = None) -> Tuple[int, bytes]:
    """
    Fetches raw bytes from a URL using urllib with safety timeouts and standard user agent.
    """
    h = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json, text/html"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read()


def crawl_tournament_overview(tournament_id: str) -> Dict[str, Any]:
    """
    Crawls HTML hub page to extract tournament title, player count, stages, and movers.
    """
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

    # Extract Title & Metadata from OpenGraph / meta tags
    title_match = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html_text)
    if not title_match:
        title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE)
    if title_match:
        raw_title = title_match.group(1).strip()
        # Clean title e.g. "Tournaments | MunchStats | 2027 Baltimore Pokémon VGC Regional Championships"
        parts = [p.strip() for p in raw_title.split("|")]
        overview["tournament_name"] = parts[-1] if parts else raw_title

    desc_match = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html_text)
    if desc_match:
        desc_text = desc_match.group(1)
        players_m = re.search(r"(\d+)\s+teams", desc_text)
        if players_m:
            overview["total_players"] = int(players_m.group(1))

    # Extract window.hubOverview javascript payload
    hub_m = re.search(r"window\.hubOverview\s*=\s*(.*?);(?=\s*window\.|\s*</script>)", html_text, re.DOTALL)
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
    """
    Crawls full competitor standings via the REST API endpoint.
    Each item contains player name, rank/placement, record (W/L), day reached, and full 6-mon team sheet.
    """
    url = f"{MUNCHSTATS_BASE_URL}/tournaments/api/{urllib.parse.quote(tournament_id)}/standings?day={urllib.parse.quote(day_filter)}"
    status, payload = fetch_url(url)
    data = json.loads(payload.decode("utf-8"))
    if isinstance(data, list):
        return data
    return []


def crawl_tournament_usage(tournament_id: str, day_filter: str = "all") -> Dict[str, Any]:
    """
    Crawls aggregated species usage via the official REST API endpoint.
    """
    url = f"{MUNCHSTATS_BASE_URL}/tournaments/api/{urllib.parse.quote(tournament_id)}/{urllib.parse.quote(day_filter)}/"
    status, payload = fetch_url(url)
    return json.loads(payload.decode("utf-8"))


def get_max_scouted_team_id_num(csv_path: Path = SCOUTED_TEAMS_CSV) -> int:
    """Returns the maximum numeric ST identifier found in the CSV (e.g. 64 for ST64)."""
    if not csv_path.exists():
        return 0
    max_num = 0
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0]:
                continue
            match = re.match(r"^ST(\d+)$", row[0].strip())
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    return max_num


def get_next_scouted_team_id(csv_path: Path = SCOUTED_TEAMS_CSV) -> str:
    """Returns the next sequential scouted team ID (e.g. ST65, ST66)."""
    return f"ST{get_max_scouted_team_id_num(csv_path) + 1:02d}"


def determine_archetype_label(roster_species: List[str]) -> str:
    """Derives a descriptive competitive VGC archetype from roster members."""
    lower_set = {s.lower() for s in roster_species if s}

    is_rain = any(k in lower_set for k in ["pelipper", "politoed", "basculegion", "archaludon", "raichu-mega-x"])
    is_sun = any(k in lower_set for k in ["torkoal", "charizard-mega-y", "venusaur", "walking wake"])
    is_sand = any(k in lower_set for k in ["tyranitar", "tyranitar-mega", "excadrill", "hippowdon"])
    is_trick_room = any(k in lower_set for k in ["farigiraf", "ursaluna", "armarouge", "indeedee-f", "dusclops"])
    is_psyspam = any(k in lower_set for k in ["indeedee", "indeedee-f"]) and any(k in lower_set for k in ["armarouge", "alakazam", "gardevoir"])

    if is_rain and any(k in lower_set for k in ["sneasler", "raichu-mega-x"]):
        return "Rain Electric Seed Offense"
    if is_rain:
        return "Rain Archaludon Offense"
    if is_sand:
        return "Sand Rush Physical Offense"
    if is_sun and is_trick_room:
        return "Sun Trick Room Offense"
    if is_sun:
        return "Sun Mega Charizard Offense"
    if is_psyspam:
        return "Psychic Terrain Expanding Force"
    if is_trick_room:
        return "Trick Room Hard Offense"
    if any(k in lower_set for k in ["kingambit", "gholdengo", "incineroar", "rillaboom"]):
        return "Goodstuffs Pivot Balance"
    return "Standard Competitive Balance"


def build_showdown_export(team_slots: List[Dict[str, Any]]) -> str:
    """Formats team slots into Showdown import/export paste."""
    lines = []
    for slot in team_slots:
        mon = slot.get("pokemon") or slot.get("name") or "Unknown"
        item = slot.get("item")
        ability = slot.get("ability")
        moves = slot.get("moves") or []
        nature = slot.get("nature")

        header = f"{mon} @ {item}" if item else mon
        lines.append(header)
        if ability:
            lines.append(f"Ability: {ability}")
        if nature:
            lines.append(f"{nature} Nature")
        for m in moves:
            lines.append(f"- {m}")
        lines.append("")
    return "\n".join(lines).strip()


def populate_scouted_teams(
    standings: List[Dict[str, Any]],
    tournament_name: str,
    max_teams: int = 16,
    csv_path: Path = SCOUTED_TEAMS_CSV
) -> List[Dict[str, Any]]:
    """
    Registers the highest placing teams (Top 8 / Top 16) and top archetype clusters
    into data/Scouted_Teams.csv with CSV injection immunity and sequential STxx IDs.
    """
    if not standings:
        return []

    # 1. Existing rosters to prevent redundant duplicates
    existing_rosters = set()
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mons = [row.get(f"Pokemon_{i}", "").split("@")[0].strip().lower() for i in range(1, 7)]
                mons_clean = tuple(sorted([m for m in mons if m]))
                if mons_clean:
                    existing_rosters.add(mons_clean)

    # 2. Candidate selection: Prioritize Top Cut (1 to 16)
    candidates = []
    # Sort by placement ascending (1st place first)
    sorted_standings = sorted(standings, key=lambda x: int(x.get("placement") or 9999))

    for entry in sorted_standings:
        placement = int(entry.get("placement") or 9999)
        team = entry.get("team") or []
        if len(team) < 6:
            continue
        roster_names = tuple(sorted([(m.get("pokemon") or "").strip().lower() for m in team if m.get("pokemon")]))
        if not roster_names or len(roster_names) < 4:
            continue

        if roster_names in existing_rosters:
            continue

        candidates.append(entry)
        existing_rosters.add(roster_names)
        if len(candidates) >= max_teams:
            break

    # 3. Append to Scouted_Teams.csv
    registered = []
    date_serial = get_excel_serial_timestamp()

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0

    fieldnames = [
        "Scouted_Team_ID", "Player_Name", "Tournament", "Date_Scouted", "Placement",
        "Pokemon_1", "Pokemon_2", "Pokemon_3", "Pokemon_4", "Pokemon_5", "Pokemon_6",
        "Showdown_Export", "Archetype", "Notes"
    ]

    curr_id_num = get_max_scouted_team_id_num(csv_path)

    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        for cand in candidates:
            curr_id_num += 1
            next_id = f"ST{curr_id_num:02d}"
            player_name = cand.get("name") or "Tournament Competitor"
            placement_num = cand.get("placement", "")
            rec = cand.get("record") or {}
            rec_str = f" ({rec.get('wins', 0)}-{rec.get('losses', 0)})" if rec else ""
            placement_label = f"Rank {placement_num}{rec_str}" if placement_num else "Top Cut"

            team = cand.get("team", [])
            mon_cols = {}
            species_list = []
            for idx in range(1, 7):
                if idx - 1 < len(team):
                    m = team[idx - 1]
                    p_name = m.get("pokemon") or "Unknown"
                    p_item = m.get("item")
                    species_list.append(p_name)
                    mon_cols[f"Pokemon_{idx}"] = f"{p_name} @ {p_item}" if p_item else p_name
                else:
                    mon_cols[f"Pokemon_{idx}"] = ""

            archetype = determine_archetype_label(species_list)
            showdown_export = build_showdown_export(team)
            notes = f"Official Play! Pokémon Top Cut finish at {tournament_name}. Ingested via MunchStats Crawler."

            row = {
                "Scouted_Team_ID": next_id,
                "Player_Name": sanitize_csv_cell(player_name),
                "Tournament": sanitize_csv_cell(tournament_name),
                "Date_Scouted": date_serial,
                "Placement": sanitize_csv_cell(placement_label),
                "Showdown_Export": sanitize_csv_cell(showdown_export),
                "Archetype": sanitize_csv_cell(archetype),
                "Notes": sanitize_csv_cell(notes),
            }
            for k, v in mon_cols.items():
                row[k] = sanitize_csv_cell(v)

            writer.writerow(row)
            registered.append({
                "id": next_id,
                "player": player_name,
                "placement": placement_label,
                "archetype": archetype,
                "roster": species_list
            })

    return registered


def crawl_and_dump_munchstats(
    url_or_id: str,
    output_base_dir: Optional[Path] = None,
    populate_scouted: bool = True,
    max_scouted: int = 16,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Executes the complete end-to-end MunchStats tournament ingestion pipeline:
    1. Extracts Tournament ID and fetches overview, stages, and movers.
    2. Fetches full player standings and sets.
    3. Fetches usage across phases.
    4. Dumps raw JSON and CSV tables into data/munchstats/raw/{tournament_slug}/.
    5. Optionally registers top teams in data/Scouted_Teams.csv.
    """
    t_id = extract_tournament_id(url_or_id)
    if verbose:
        print(f"[*] Starting MunchStats Ingestion for Tournament ID: {t_id}")

    # 1. Overview & Metadata
    overview = crawl_tournament_overview(t_id)
    t_name = overview.get("tournament_name") or f"Tournament {t_id}"
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", t_name.lower().replace(" ", "_")).strip("_")
    if not slug:
        slug = t_id.lower()

    if verbose:
        print(f"  [+] Tournament: {t_name} (Total Teams: {overview.get('total_players')})")

    # 2. Standings & Roster Sets
    if verbose:
        print("  [+] Fetching full competitor standings and rosters...")
    standings = crawl_tournament_standings(t_id, day_filter="all")
    if verbose:
        print(f"  [+] Successfully parsed {len(standings)} competitor rosters.")

    # 3. Usage Stats
    if verbose:
        print("  [+] Fetching aggregated usage statistics across phases...")
    usage_all = crawl_tournament_usage(t_id, day_filter="all")
    day_options = usage_all.get("day_options", ["all"])

    phase_usage: Dict[str, Any] = {"all": usage_all}
    for day in day_options:
        if day != "all":
            try:
                phase_usage[day] = crawl_tournament_usage(t_id, day_filter=day)
            except Exception as exc:
                if verbose:
                    print(f"    [-] Notice: Phase '{day}' skipped ({exc})")

    # 4. Prepare Destination Dumps
    target_dir = (output_base_dir or (DATA_DIR / "munchstats" / "raw" / slug))
    target_dir.mkdir(parents=True, exist_ok=True)

    # 4a. Write overview.json
    overview_path = target_dir / "overview.json"
    overview_path.write_text(json.dumps(overview, indent=2, ensure_ascii=False), encoding="utf-8")

    # 4b. Write standings.json & standings.csv
    standings_json_path = target_dir / "standings.json"
    standings_json_path.write_text(json.dumps(standings, indent=2, ensure_ascii=False), encoding="utf-8")

    standings_csv_path = target_dir / "standings.csv"
    with open(standings_csv_path, "w", encoding="utf-8", newline="") as f:
        s_writer = csv.writer(f)
        s_writer.writerow([
            "Placement", "Player_Name", "Record", "Day_Reached",
            "Pokemon_1", "Pokemon_2", "Pokemon_3", "Pokemon_4", "Pokemon_5", "Pokemon_6"
        ])
        for p in standings:
            rec = p.get("record") or {}
            rec_str = f"{rec.get('wins', 0)}-{rec.get('losses', 0)}" if rec else ""
            team = p.get("team") or []
            p_mons = []
            for slot in team[:6]:
                p_name = slot.get("pokemon") or slot.get("name") or ""
                p_item = slot.get("item")
                p_mons.append(f"{p_name} @ {p_item}" if p_item else p_name)
            while len(p_mons) < 6:
                p_mons.append("")
            s_writer.writerow([
                sanitize_csv_cell(str(p.get("placement", ""))),
                sanitize_csv_cell(p.get("name", "")),
                sanitize_csv_cell(rec_str),
                sanitize_csv_cell(p.get("day_reached", "")),
                *[sanitize_csv_cell(m) for m in p_mons]
            ])

    # 4c. Write usage.json & usage.csv
    usage_json_path = target_dir / "usage.json"
    usage_json_path.write_text(json.dumps(phase_usage, indent=2, ensure_ascii=False), encoding="utf-8")

    # Compile unified usage CSV across Day 1, Day 2, and Top Cut
    stage_d1 = next((s for s in overview.get("stages", []) if s.get("label") == "Day 1"), {})
    stage_d2 = next((s for s in overview.get("stages", []) if s.get("label") == "Day 2"), {})
    stage_tc = next((s for s in overview.get("stages", []) if "Top" in s.get("label", "")), {})

    d1_map = {r["name"]: r for r in stage_d1.get("rows", [])}
    d2_map = {r["name"]: r for r in stage_d2.get("rows", [])}
    tc_map = {r["name"]: r for r in stage_tc.get("rows", [])}

    all_species = list(dict.fromkeys(
        [p[0] for p in usage_all.get("pokemon_names", [])] +
        list(d1_map.keys()) + list(d2_map.keys()) + list(tc_map.keys())
    ))

    usage_csv_path = target_dir / "usage.csv"
    with open(usage_csv_path, "w", encoding="utf-8", newline="") as f:
        u_writer = csv.writer(f)
        u_writer.writerow([
            "Species", "Overall_Usage_Pct", "Day1_Count", "Day1_Usage_Pct",
            "Day2_Count", "Day2_Usage_Pct", "TopCut_Count", "TopCut_Usage_Pct", "Conversion_Rate_Pct"
        ])
        for sp in all_species:
            d1_entry = d1_map.get(sp, {})
            d2_entry = d2_map.get(sp, {})
            tc_entry = tc_map.get(sp, {})

            d1_count = d1_entry.get("count", 0)
            d2_count = d2_entry.get("count", 0)
            tc_count = tc_entry.get("count", 0)

            d1_pct = d1_entry.get("usage_pct", 0.0)
            d2_pct = d2_entry.get("usage_pct", 0.0)
            tc_pct = tc_entry.get("usage_pct", 0.0)

            overall_pct = next((p[1] for p in usage_all.get("pokemon_names", []) if p[0] == sp), d1_pct)

            conv_rate = (d2_count / d1_count * 100.0) if d1_count > 0 else 0.0

            u_writer.writerow([
                sanitize_csv_cell(sp),
                sanitize_csv_cell(f"{overall_pct}%"),
                sanitize_csv_cell(str(d1_count)),
                sanitize_csv_cell(f"{d1_pct}%"),
                sanitize_csv_cell(str(d2_count)),
                sanitize_csv_cell(f"{d2_pct}%"),
                sanitize_csv_cell(str(tc_count)),
                sanitize_csv_cell(f"{tc_pct}%"),
                sanitize_csv_cell(f"{conv_rate:.2f}%")
            ])

    if verbose:
        print(f"  [+] Data successfully dumped to: {target_dir}")

    # 5. Populate Scouted_Teams.csv (if requested)
    scouted_registered = []
    if populate_scouted and standings:
        scouted_registered = populate_scouted_teams(
            standings=standings,
            tournament_name=t_name,
            max_teams=max_scouted,
            csv_path=SCOUTED_TEAMS_CSV
        )
        if verbose:
            print(f"  [+] Registered {len(scouted_registered)} top-tier teams into data/Scouted_Teams.csv.")

    return {
        "status": "SUCCESS",
        "tournament_id": t_id,
        "tournament_name": t_name,
        "slug": slug,
        "total_players": overview.get("total_players", len(standings)),
        "output_dir": str(target_dir),
        "standings_count": len(standings),
        "scouted_teams_registered": len(scouted_registered),
        "files": {
            "overview_json": str(overview_path),
            "standings_json": str(standings_json_path),
            "standings_csv": str(standings_csv_path),
            "usage_json": str(usage_json_path),
            "usage_csv": str(usage_csv_path),
        }
    }


def main():
    """CLI entry point for MunchStats tournament crawling and ingestion."""
    parser = argparse.ArgumentParser(
        description="Coach Porygon VGC — MunchStats Tournament Crawler & Raw Ingestion Engine"
    )
    parser.add_argument("--url", "-u", type=str, help="Full MunchStats tournament URL.")
    parser.add_argument("--tournament-id", "-t", type=str, help="MunchStats Tournament ID.")
    parser.add_argument("--output-dir", "-o", type=str, default=None, help="Custom output directory.")
    parser.add_argument("--no-scouted-teams", action="store_true", help="Skip populating data/Scouted_Teams.csv.")
    parser.add_argument("--max-scouted", type=int, default=16, help="Maximum teams to register in Scouted_Teams.csv.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode.")

    args = parser.parse_args()
    target_input = args.url or args.tournament_id
    if not target_input:
        parser.print_help()
        sys.exit(1)

    result = crawl_and_dump_munchstats(
        url_or_id=target_input,
        output_base_dir=Path(args.output_dir) if args.output_dir else None,
        populate_scouted=not args.no_scouted_teams,
        max_scouted=args.max_scouted,
        verbose=not args.quiet
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
