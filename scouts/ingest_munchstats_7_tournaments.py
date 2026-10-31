#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — MunchStats 7-Regional Tournament Ingestion Pipeline
Crawls official tournament data from MunchStats for:
1. Puebla Regional (PB002-r871Zfmc4WQbIO)
2. Nice Regional (NC002-zBMwK69ABS7RRV)
3. Louisville Regional (LO002-drfp6esCSpyU3s)
4. Recife Regional (RE002-wN97aUf4Psz0ZJ)
5. Frankfurt Regional (FR002-fiunEHp9wx4mh4)
6. Brisbane Regional (BR002-IU5yO1W76UpdyA)
7. Baltimore Regional (BA002-JL3KVbvivVKNAc)

Stores structured outputs in:
- data/Tournament_Meta.json (Mode 6 Schema)
- data/Munchstats_Aggregate_Meta.json
- data/Scouted_Teams.csv (Top Cut rosters with STxx IDs)
"""

import csv
import datetime
import json
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SCOUTED_CSV = DATA_DIR / "Scouted_Teams.csv"
TOURNAMENT_META_JSON = DATA_DIR / "Tournament_Meta.json"
AGGREGATE_META_JSON = DATA_DIR / "Munchstats_Aggregate_Meta.json"
STANDINGS_DIR = DATA_DIR / "munchstats_standings"
STANDINGS_DIR.mkdir(parents=True, exist_ok=True)

TOURNAMENTS = [
    {
        "id": "PB002-r871Zfmc4WQbIO",
        "name": "2027 Puebla Pokémon VGC Regional Championships",
        "date": "2026-10-24",
        "location": "Puebla, Mexico",
        "short_id": "TM_PUEBLA_2027"
    },
    {
        "id": "NC002-zBMwK69ABS7RRV",
        "name": "2027 Nice Pokémon VGC Regional Championships",
        "date": "2026-10-17",
        "location": "Nice, France",
        "short_id": "TM_NICE_2027"
    },
    {
        "id": "LO002-drfp6esCSpyU3s",
        "name": "2027 Louisville Pokémon VGC Regional Championships",
        "date": "2026-10-09",
        "location": "Louisville, USA",
        "short_id": "TM_LOUISVILLE_2027"
    },
    {
        "id": "RE002-wN97aUf4Psz0ZJ",
        "name": "2027 Recife Pokémon VGC Regional Championships",
        "date": "2026-10-03",
        "location": "Recife, Brazil",
        "short_id": "TM_RECIFE_2027"
    },
    {
        "id": "FR002-fiunEHp9wx4mh4",
        "name": "2027 Frankfurt Pokémon VGC Regional Championships",
        "date": "2026-09-26",
        "location": "Frankfurt, Germany",
        "short_id": "TM_FRANKFURT_2027"
    },
    {
        "id": "BR002-IU5yO1W76UpdyA",
        "name": "2027 Brisbane Pokémon VGC Regional Championships",
        "date": "2026-09-26",
        "location": "Brisbane, Australia",
        "short_id": "TM_BRISBANE_2027"
    },
    {
        "id": "BA002-JL3KVbvivVKNAc",
        "name": "2027 Baltimore Pokémon VGC Regional Championships",
        "date": "2026-09-18",
        "location": "Baltimore, USA",
        "short_id": "TM_BALTIMORE_2027"
    }
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CoachPorygon/1.0"}


def fetch_url_json(url: str, retries: int = 3, timeout: int = 15):
    """Fetch JSON payload with retries and custom headers."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            if attempt == retries - 1:
                print(f"[ERROR] Failed fetching {url}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5)


def infer_archetype_from_team(team: list) -> str:
    """Classifies competitive archetype from list of dict or strings."""
    names = []
    for m in team:
        if isinstance(m, dict):
            names.append(m.get("species", "") or m.get("name", ""))
            if m.get("item"):
                names.append(m.get("item", ""))
        else:
            names.append(str(m))
    text = " ".join(names).lower()

    if any(k in text for k in ["pelipper", "politoed"]) and "archaludon" in text:
        return "Rain Archaludon Offense"
    if any(k in text for k in ["pelipper", "politoed"]):
        return "Rain Offense"
    if any(k in text for k in ["torkoal", "ninetales"]) or "charizardite y" in text or "charizard-mega-y" in text:
        return "Sun Hyper Offense"
    if "staraptor" in text and ("raichu" in text or "sneasler" in text):
        return "Tailwind Fast Pivot Offense"
    if "staraptor" in text:
        return "Tailwind Hyper Offense"
    if any(k in text for k in ["tyranitar", "hippowdon"]) and "excadrill" in text:
        return "Sand Rush Offense"
    if any(k in text for k in ["tyranitar", "hippowdon"]):
        return "Sand Balance"
    if "indeedee" in text and any(k in text for k in ["armarouge", "gardevoir", "hatterene"]):
        return "Psychic Terrain Offense"
    if any(k in text for k in ["farigiraf", "hatterene", "dusclops"]) and any(k in text for k in ["rhyperior", "torkoal", "conkeldurr"]):
        return "Trick Room Offense"
    if "ceruledge" in text and "rillaboom" in text:
        return "Grassy Seed Flash Fire Balance"
    if any(k in text for k in ["incineroar", "rillaboom", "milotic", "grimmsnarl"]):
        return "Pivoting Balance"
    return "Standard Meta Balance"


def get_next_scouted_team_id(csv_path: Path = SCOUTED_CSV) -> str:
    """Returns next sequential STxx ID."""
    if not csv_path.exists():
        return "ST01"
    max_num = 0
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            m = re.match(r"^ST(\d+)$", row[0].strip(), re.IGNORECASE)
            if m:
                val = int(m.group(1))
                if val > max_num:
                    max_num = val
    return f"ST{max_num + 1:02d}"


def get_excel_serial_timestamp() -> float:
    """Compute current excel serial timestamp float."""
    epoch = datetime.datetime(1899, 12, 30, tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    return round((now - epoch).total_seconds() / 86400.0, 5)


def sanitize_csv_cell(val: str) -> str:
    """Neutralize formula injection prefixes."""
    s = str(val or "").strip()
    if s.startswith(("=", "+", "-", "@")):
        return f"'{s}"
    return s


def run_pipeline():
    """Runs the complete ingestion and meta analysis for all 7 tournaments."""
    print("=" * 70)
    print("COACH PORYGON VGC — MUNCHSTATS 7-REGIONAL CRAWLER & INGESTION")
    print("=" * 70)

    all_tournament_meta = []
    _cross_species_counter = Counter()
    cross_species_weighted_counts = Counter()
    cross_mega_counter = Counter()
    cross_archetype_counter = Counter()
    total_competitors = 0

    top_cut_scouted_rows = []

    for t_info in TOURNAMENTS:
        tid = t_info["id"]
        t_name = t_info["name"]
        print(f"\n[CRAWLING] {t_name} ({tid})...")

        # 1. Fetch Overview & Pokemon usage
        meta_url = f"https://www.munchstats.com/tournaments/api/{tid}/all/"
        meta_data = fetch_url_json(meta_url)
        if not meta_data:
            print(f"[SKIP] Could not load meta data for {tid}")
            continue

        total_teams = meta_data.get("total_teams", 0)
        total_competitors += total_teams
        p_names = meta_data.get("pokemon_names", [])

        # 2. Fetch Standings
        standings_url = f"https://www.munchstats.com/tournaments/api/{tid}/standings?day=all"
        standings_data = fetch_url_json(standings_url)
        if standings_data:
            standings_file = STANDINGS_DIR / f"{t_info['short_id']}_standings.json"
            standings_file.write_text(json.dumps(standings_data, indent=2), encoding="utf-8")
            print(f"  * Cached {len(standings_data)} standings to {standings_file.name}")

        # Parse usage stats
        usage_stats = []
        for row in p_names:
            sp_name = row[0]
            pct = float(row[1])
            count = int(round(pct * total_teams / 100.0))
            usage_stats.append({
                "species": sp_name,
                "usage_pct": pct,
                "count": count
            })
            cross_species_weighted_counts[sp_name] += count
            if "mega" in sp_name.lower():
                cross_mega_counter[sp_name] += count

        # Extract top 8 and champion
        top_8_trainers = []
        champion_entry = None
        if standings_data:
            for s in standings_data:
                place = s.get("placement")
                _day_reached = s.get("day_reached", "")
                team_list = s.get("team", [])
                arch = infer_archetype_from_team(team_list)
                cross_archetype_counter[arch] += 1

                trainer_item = {
                    "player": s.get("name", "Unknown"),
                    "placement": f"{place}{'st' if place==1 else 'nd' if place==2 else 'rd' if place==3 else 'th'} Place" if isinstance(place, int) else str(place),
                    "numeric_place": place if isinstance(place, int) else 999,
                    "record": s.get("record", {}),
                    "archetype": arch,
                    "roster": [
                        f"{m.get('name') or m.get('species')} @ {m.get('item', 'No Item')}"
                        for m in team_list
                    ],
                    "raw_team": team_list
                }
                if place == 1 and not champion_entry:
                    champion_entry = trainer_item

                if isinstance(place, int) and place <= 8:
                    top_8_trainers.append(trainer_item)
                    top_cut_scouted_rows.append((t_name, trainer_item))

        top_8_trainers.sort(key=lambda x: x["numeric_place"])

        # Determine dominant megas in this regional
        reg_megas = [u for u in usage_stats if "mega" in u["species"].lower()]
        reg_megas.sort(key=lambda x: x["usage_pct"], reverse=True)

        meta_package = {
            "tournament_id": t_info["short_id"],
            "munchstats_id": tid,
            "tournament_name": t_name,
            "date": t_info["date"],
            "location": t_info["location"],
            "division": "Masters",
            "total_players": total_teams,
            "top_cut_size": len(top_8_trainers) if top_8_trainers else 8,
            "champion": champion_entry,
            "top_8_teams": top_8_trainers,
            "dominant_megas": [
                {"mega": m["species"], "usage_pct": m["usage_pct"], "count": m["count"]}
                for m in reg_megas[:6]
            ],
            "usage_stats": usage_stats[:25],
            "overview_stages": meta_data.get("overview", {}).get("stages", []),
            "overview_movers": meta_data.get("overview", {}).get("movers", [])
        }
        all_tournament_meta.append(meta_package)
        print(f"  * Ingested: {t_name} | {total_teams} players | Top Mega: {reg_megas[0]['species'] if reg_megas else 'None'} ({reg_megas[0]['usage_pct'] if reg_megas else 0}%)")

    # 3. Save Tournament_Meta.json
    TOURNAMENT_META_JSON.write_text(json.dumps(all_tournament_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[SUCCESS] Written {len(all_tournament_meta)} regional tournament packages to {TOURNAMENT_META_JSON}")

    # 4. Save Aggregate Meta JSON
    aggregate_meta = {
        "crawled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_tournaments": len(all_tournament_meta),
        "total_players": total_competitors,
        "tournaments": [
            {"id": t["tournament_id"], "name": t["tournament_name"], "players": t["total_players"], "date": t["date"]}
            for t in all_tournament_meta
        ],
        "top_species_weighted_usage": [
            {
                "rank": rank,
                "species": sp,
                "total_count": count,
                "weighted_usage_pct": round((count / total_competitors) * 100.0, 2)
            }
            for rank, (sp, count) in enumerate(cross_species_weighted_counts.most_common(35), 1)
        ],
        "dominant_megas_ranking": [
            {
                "rank": rank,
                "mega": mega,
                "total_count": count,
                "weighted_usage_pct": round((count / total_competitors) * 100.0, 2)
            }
            for rank, (mega, count) in enumerate(cross_mega_counter.most_common(12), 1)
        ],
        "top_archetypes": [
            {
                "archetype": arch,
                "count": count
            }
            for arch, count in cross_archetype_counter.most_common(10)
        ]
    }
    AGGREGATE_META_JSON.write_text(json.dumps(aggregate_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SUCCESS] Written aggregate meta across {total_competitors} competitors to {AGGREGATE_META_JSON}")

    # 5. Ingest Top Cut Rosters into Scouted_Teams.csv
    # Read existing IDs in Scouted_Teams.csv to avoid duplicate entries
    existing_players_tournaments = set()
    if SCOUTED_CSV.exists():
        with open(SCOUTED_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p = row.get("Player_Name", "").strip().lower()
                tour = row.get("Tournament", "").strip().lower()
                existing_players_tournaments.add((p, tour))

    next_id_num = 1
    if SCOUTED_CSV.exists() and SCOUTED_CSV.stat().st_size > 0:
        with open(SCOUTED_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    m = re.match(r"^ST(\d+)$", row[0].strip(), re.I)
                    if m:
                        next_id_num = max(next_id_num, int(m.group(1)) + 1)

    new_scouted_entries = 0
    date_val = get_excel_serial_timestamp()

    with open(SCOUTED_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for t_name, item in top_cut_scouted_rows:
            key = (item["player"].strip().lower(), t_name.strip().lower())
            if key in existing_players_tournaments:
                continue

            st_id = f"ST{next_id_num:02d}"
            next_id_num += 1

            roster = item["roster"]
            slots = (roster[:6] + [""] * 6)[:6]

            # Construct Showdown export
            showdown_lines = []
            for mon in item.get("raw_team", []):
                sp = mon.get("species") or mon.get("name")
                it = mon.get("item")
                ab = mon.get("ability")
                moves = mon.get("moves", [])
                showdown_lines.append(f"{sp} @ {it}")
                if ab: showdown_lines.append(f"Ability: {ab}")
                for mv in moves: showdown_lines.append(f"- {mv}")
                showdown_lines.append("")

            row = [
                st_id,
                sanitize_csv_cell(item["player"]),
                sanitize_csv_cell(t_name),
                date_val,
                sanitize_csv_cell(item["placement"]),
                sanitize_csv_cell(slots[0]),
                sanitize_csv_cell(slots[1]),
                sanitize_csv_cell(slots[2]),
                sanitize_csv_cell(slots[3]),
                sanitize_csv_cell(slots[4]),
                sanitize_csv_cell(slots[5]),
                sanitize_csv_cell("\n".join(showdown_lines)),
                sanitize_csv_cell(item["archetype"]),
                sanitize_csv_cell(f"Official Top Cut Finish ({item['placement']}) at {t_name}.")
            ]
            writer.writerow(row)
            existing_players_tournaments.add(key)
            new_scouted_entries += 1

    print(f"[SUCCESS] Appended {new_scouted_entries} verified Top Cut scouted teams into {SCOUTED_CSV}")
    print("=" * 70)


if __name__ == "__main__":
    run_pipeline()
