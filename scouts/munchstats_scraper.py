#!/usr/bin/env python3
"""
Coach Porygon VGC — MunchStats Tournament Scraper & Scouted Teams Ingestion Engine
Handles tournament scouting, natural language / plain text roster ingestion,
MunchStats tournament parsing (RK9 / Limitless), core clustering, and Mode 4 lookups.
"""

import argparse
import csv
import datetime
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

REPO_ROOT = Path(__file__).resolve().parent.parent
TEAMS_CSV = REPO_ROOT / "data" / "Teams.csv"
SCOUTED_CSV = REPO_ROOT / "data" / "Scouted_Teams.csv"
POKEMON_CSV = REPO_ROOT / "data" / "MC_Available_Pokemon.csv"
ITEMS_CSV = REPO_ROOT / "data" / "Regulation_MC_Items.csv"
TOURNAMENT_META_JSON = REPO_ROOT / "data" / "Tournament_Meta.json"

sys.path.insert(0, str(REPO_ROOT / "engine"))
try:
    from telemetry import get_excel_serial_timestamp, sanitize_csv_cell
    from validate_roster import parse_showdown_paste, validate_roster
except ImportError:
    get_excel_serial_timestamp = lambda: round((datetime.datetime.now(datetime.timezone.utc) - datetime.datetime(1899, 12, 30, tzinfo=datetime.timezone.utc)).total_seconds() / 86400.0, 5)
    sanitize_csv_cell = lambda x: x
    parse_showdown_paste = None
    validate_roster = None

SCOUTED_TEAMS_COLS = [
    "Scouted_Team_ID", "Player_Name", "Tournament", "Date_Scouted", "Placement",
    "Pokemon_1", "Pokemon_2", "Pokemon_3", "Pokemon_4", "Pokemon_5", "Pokemon_6",
    "Showdown_Export", "Archetype", "Notes"
]


# ==============================================================================
# 1. Team ID Resolution & Matching (Mode 4 Compatibility)
# ==============================================================================

def normalize_species_set(roster: List[str]) -> Set[str]:
    """Normalize species list into a frozenset of canonical lowercase IDs."""
    cleaned = set()
    for mon in roster:
        if not mon or not mon.strip():
            continue
        base = mon.split("@")[0].replace("(M)", "").replace("(F)", "").strip().lower()
        if base:
            cleaned.add(base)
    return cleaned


def extract_row_roster(row: Dict[str, str]) -> List[str]:
    """Extract 6 roster Pokémon names from a MunchStats tournament CSV row."""
    if "Pokemon_1" in row:
        return [row.get(f"Pokemon_{i}", "") for i in range(1, 7) if row.get(f"Pokemon_{i}", "")]
    if "Roster" in row:
        return [m.strip() for m in row["Roster"].split("/") if m.strip()]
    return []


def resolve_team_id_by_roster(active_mons: List[str]) -> Tuple[str, List[Dict[str, str]]]:
    """
    Searches Teams.csv (T01-Txx) and Scouted_Teams.csv (ST01-STxx) for an exact
    or subset match against the provided active Pokémon roster.
    """
    query_set = normalize_species_set(active_mons)
    candidates: List[Dict[str, str]] = []

    for csv_path in [TEAMS_CSV, SCOUTED_CSV]:
        if not csv_path.exists():
            continue
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_mons = extract_row_roster(row)
                team_mons = normalize_species_set(raw_mons)
                if not team_mons or not query_set:
                    continue
                matched = True
                for q in query_set:
                    base_q = q.replace("mega ", "").split("-")[0].strip()
                    if not any(q in tm or base_q in tm for tm in team_mons):
                        matched = False
                        break
                if matched:
                    team_id = row.get("Team_ID") or row.get("Scouted_Team_ID") or "Unknown"
                    archetype = row.get("Archetype") or row.get("Team_Name") or row.get("Player_Name") or "Unknown"
                    candidates.append({
                        "Team_ID": team_id,
                        "Archetype": archetype,
                        "Roster": " / ".join(m.split("@")[0].strip() for m in raw_mons)
                    })

    if len(candidates) == 1:
        return "SINGLE_MATCH", candidates
    if len(candidates) > 1:
        return "AMBIGUOUS_MATCH", candidates
    return "ZERO_MATCH", []


# ==============================================================================
# 2. Automated Sequential ID Generation & Scouted CSV Management
# ==============================================================================

def get_next_scouted_team_id(csv_path: Path = SCOUTED_CSV) -> str:
    """Returns the next sequential scouted team ID (e.g., ST01, ST02)."""
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


def infer_archetype(pokemon_list: List[str]) -> str:
    """Heuristically determines competitive archetype from a list of species names."""
    names = " ".join(pokemon_list).lower()
    if any(k in names for k in ["pelipper", "politoed"]) and "archaludon" in names:
        return "Rain Archaludon Offense"
    if any(k in names for k in ["pelipper", "politoed"]):
        return "Rain Offense"
    if any(k in names for k in ["torkoal", "ninetales"]) or "charizard-mega-y" in names or "charizardite y" in names:
        return "Sun Balance"
    if any(k in names for k in ["tyranitar", "hippowdon"]) and "excadrill" in names:
        return "Sand Rush Offense"
    if any(k in names for k in ["tyranitar", "hippowdon"]):
        return "Sand Balance"
    if "indeedee" in names and any(k in names for k in ["armarouge", "gardevoir", "hatterene"]):
        return "Psychic Terrain Offense"
    if any(k in names for k in ["farigiraf", "hatterene", "dusclops"]) and any(k in names for k in ["torkoal", "rhyperior", "conkeldurr"]):
        return "Trick Room Offense"
    if any(k in names for k in ["whimsicott", "tornadus", "talonflame", "staraptor"]):
        return "Tailwind Hyper Offense"
    if any(k in names for k in ["grimmsnarl", "incineroar", "rillaboom", "milotic"]):
        return "Pivoting Balance"
    return "Competitive Balance"


# ==============================================================================
# 3. Plain Text & Natural Language Scouted Team Ingestion
# ==============================================================================

def parse_plain_text_scouted_entry(text: str) -> Dict[str, Union[str, List[str]]]:
    """
    Parses flexible natural text or semi-structured pastes containing:
    Player: [Name]
    Tournament: [Tournament Name]
    Placement: [Placement]
    Archetype: [Archetype] (Optional)
    Notes: [Notes] (Optional)
    Followed by either a 6-mon Showdown paste or a comma/line-separated roster list.
    """
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    metadata: Dict[str, str] = {
        "player": "Unknown Competitor",
        "tournament": "Sanctioned Tournament",
        "placement": "Top Cut",
        "archetype": "",
        "notes": "",
    }

    roster_lines: List[str] = []

    for line in lines:
        lower = line.lower()
        if lower.startswith("player:") or lower.startswith("competitor:") or lower.startswith("trainer:"):
            metadata["player"] = line.split(":", 1)[1].strip()
        elif lower.startswith("tournament:") or lower.startswith("event:") or lower.startswith("regional:"):
            metadata["tournament"] = line.split(":", 1)[1].strip()
        elif lower.startswith("placement:") or lower.startswith("finish:") or lower.startswith("rank:"):
            metadata["placement"] = line.split(":", 1)[1].strip()
        elif lower.startswith("archetype:") or lower.startswith("core:"):
            metadata["archetype"] = line.split(":", 1)[1].strip()
        elif lower.startswith("notes:") or lower.startswith("commentary:"):
            metadata["notes"] = line.split(":", 1)[1].strip()
        elif lower.startswith("roster:") or lower.startswith("team:") or lower.startswith("pokemon:"):
            rest = line.split(":", 1)[1].strip()
            if rest:
                roster_lines.append(rest)
        else:
            roster_lines.append(line)

    roster_blob = "\n".join(roster_lines).strip()
    pokemon_entries: List[str] = []
    showdown_export = ""

    # Check if roster_blob is a Showdown paste block
    if parse_showdown_paste and ("Ability:" in roster_blob or "EVs:" in roster_blob or "Nature" in roster_blob):
        parsed_mon_blocks = parse_showdown_paste(roster_blob)
        for p in parsed_mon_blocks:
            item_part = f" @ {p['item']}" if p.get("item") else ""
            pokemon_entries.append(f"{p['species']}{item_part}")
        showdown_export = roster_blob
    else:
        # Fallback: Comma, slash, or newline separated species
        tokens = re.split(r"[,/\n]+", roster_blob)
        for t in tokens:
            t_clean = t.strip()
            # Remove leading bullets or numbering: "1. Charizard @ Charizardite Y"
            t_clean = re.sub(r"^\d+[\.\)\-]\s*", "", t_clean).strip()
            if t_clean:
                pokemon_entries.append(t_clean)

    # Pad or slice to 6 slots
    slots = (pokemon_entries[:6] + [""] * 6)[:6]

    inferred_arch = metadata["archetype"] or infer_archetype(slots)

    return {
        "player": metadata["player"],
        "tournament": metadata["tournament"],
        "placement": metadata["placement"],
        "archetype": inferred_arch,
        "notes": metadata["notes"],
        "slots": slots,
        "showdown_export": showdown_export or "\n".join(slots),
    }


def add_scouted_team(
    player: str,
    tournament: str,
    placement: str,
    roster_or_paste: str,
    archetype: Optional[str] = None,
    notes: str = "",
    csv_path: Path = SCOUTED_CSV,
) -> Dict[str, object]:
    """
    Registers a scouted opponent team directly into data/Scouted_Teams.csv,
    assigning the next sequential Scouted_Team_ID (ST01, ST02...).
    """
    parsed = parse_plain_text_scouted_entry(f"""
Player: {player}
Tournament: {tournament}
Placement: {placement}
Archetype: {archetype or ''}
Notes: {notes}

{roster_or_paste}
    """)

    st_id = get_next_scouted_team_id(csv_path)
    date_val = get_excel_serial_timestamp()

    row_dict = {
        "Scouted_Team_ID": st_id,
        "Player_Name": sanitize_csv_cell(parsed["player"]),
        "Tournament": sanitize_csv_cell(parsed["tournament"]),
        "Date_Scouted": date_val,
        "Placement": sanitize_csv_cell(parsed["placement"]),
        "Pokemon_1": sanitize_csv_cell(parsed["slots"][0]),
        "Pokemon_2": sanitize_csv_cell(parsed["slots"][1]),
        "Pokemon_3": sanitize_csv_cell(parsed["slots"][2]),
        "Pokemon_4": sanitize_csv_cell(parsed["slots"][3]),
        "Pokemon_5": sanitize_csv_cell(parsed["slots"][4]),
        "Pokemon_6": sanitize_csv_cell(parsed["slots"][5]),
        "Showdown_Export": sanitize_csv_cell(parsed["showdown_export"]),
        "Archetype": sanitize_csv_cell(parsed["archetype"]),
        "Notes": sanitize_csv_cell(parsed["notes"]),
    }

    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(SCOUTED_TEAMS_COLS)
        writer.writerow([row_dict[col] for col in SCOUTED_TEAMS_COLS])

    return {
        "status": "SCOUTED_TEAM_REGISTERED",
        "scouted_team_id": st_id,
        "player": parsed["player"],
        "tournament": parsed["tournament"],
        "placement": parsed["placement"],
        "archetype": parsed["archetype"],
        "roster": [s for s in parsed["slots"] if s],
    }


# ==============================================================================
# 4. MunchStats Tournament Live & Offline Web Scraping
# ==============================================================================
# ==============================================================================
# Security Whitelist & SSRF / LFI Hardening Guardrails
# ==============================================================================

ALLOWED_SCRAPING_DOMAINS = {
    "munchstats.com",
    "www.munchstats.com",
    "pokemon.com",
    "www.pokemon.com",
    "pokepast.es",
    "bulbapedia.bulbagarden.net",
    "bulbapedia.com",
    "www.bulbapedia.com",
    "wikidex.net",
    "www.wikidex.net",
    "pikalytics.com",
    "www.pikalytics.com",
    "victoryroad.pro",
    "www.victoryroad.pro",
    "victoryroadvgc.com",
    "www.victoryroadvgc.com",
}

BLOCKED_IP_PREFIXES = (
    "127.",
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "169.254.",
    "0.0.0.0",
    "::1",
    "localhost",
)


def validate_scraping_target(target: str) -> Tuple[bool, Union[str, Path]]:
    """
    Validates that a URL or file path target complies with SSRF and LFI security guardrails.
    Returns (is_url: bool, validated_target: Union[str, Path]).
    Raises ValueError or PermissionError if unsafe.
    """
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

    file_path = Path(clean).resolve()
    try:
        file_path.relative_to(REPO_ROOT)
    except ValueError:
        raise PermissionError(
            f"Path Traversal Shield: Access outside repository root is blocked: {file_path}"
        )

    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    return False, file_path


def scrape_munchstats_url_or_json(
    source_url_or_file: str,
    tournament_name: Optional[str] = None,
    save_to_csv: bool = True,
    csv_path: Path = SCOUTED_CSV,
) -> List[Dict[str, object]]:
    """
    Parses a MunchStats tournament URL or a locally saved MunchStats HTML/JSON payload.
    Extracts standings (Top Cut / Top 16 / Top 8) and registers teams to Scouted_Teams.csv.
    """
    payload_text = ""
    is_live_url, validated_target = validate_scraping_target(source_url_or_file)

    if is_live_url:
        req = urllib.request.Request(
            str(validated_target),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CoachPorygon/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload_text = resp.read().decode("utf-8", errors="replace")
    else:
        payload_text = Path(validated_target).read_text(encoding="utf-8", errors="replace")

    results: List[Dict[str, object]] = []

    # Strategy A: Check if input is a JSON payload
    try:
        data = json.loads(payload_text)
        entries = data if isinstance(data, list) else data.get("standings", data.get("teams", []))
        if entries and isinstance(entries, list):
            t_title = tournament_name or data.get("tournament_name", "MunchStats Sanctioned Tournament")
            for entry in entries:
                p_name = entry.get("player") or entry.get("name") or "Unknown"
                place = entry.get("placement") or entry.get("rank") or "Top Cut"
                roster = entry.get("roster") or entry.get("pokemon") or []
                arch = entry.get("archetype") or infer_archetype(roster)
                export_text = entry.get("paste") or "\n".join(roster)
                if save_to_csv:
                    res = add_scouted_team(
                        player=p_name,
                        tournament=t_title,
                        placement=place,
                        roster_or_paste=export_text,
                        archetype=arch,
                        csv_path=csv_path,
                    )
                    results.append(res)
                else:
                    results.append({
                        "player": p_name,
                        "placement": place,
                        "archetype": arch,
                        "roster": roster
                    })
            return results
    except json.JSONDecodeError:
        pass

    # Strategy B: HTML Table / Text Scraping
    t_title = tournament_name or "MunchStats Tournament"
    title_match = re.search(r"<title>(.*?)</title>", payload_text, re.IGNORECASE)
    if title_match and not tournament_name:
        clean_title = title_match.group(1).replace("MunchStats", "").replace("-", "").strip()
        if clean_title:
            t_title = clean_title

    # Extract player sections or table rows containing Pokémon
    # MunchStats table pattern: Player Name, Placement, 6-Mon icons/names
    _player_pattern = re.compile(
        r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?</tr>',
        re.DOTALL | re.IGNORECASE
    )

    # Simple fallback: extract lines matching "Player - Placement: Mon1, Mon2, Mon3, Mon4, Mon5, Mon6"
    text_standings = re.findall(
        r"([A-Za-z0-9_\-\s]{2,30})\s*[-–—]\s*(\d+(?:st|nd|rd|th)?|Top\s*\d+)\s*[:]\s*([A-Za-z0-9\s,@\-\/\(\)]+)",
        payload_text
    )

    for p_name, place, mons in text_standings:
        p_name = p_name.strip()
        place = place.strip()
        mons_list = [m.strip() for m in re.split(r"[,/]+", mons) if m.strip()]
        if len(mons_list) >= 4:
            arch = infer_archetype(mons_list)
            if save_to_csv:
                res = add_scouted_team(
                    player=p_name,
                    tournament=t_title,
                    placement=place,
                    roster_or_paste="\n".join(mons_list),
                    archetype=arch,
                    csv_path=csv_path,
                )
                results.append(res)
            else:
                results.append({
                    "player": p_name,
                    "placement": place,
                    "archetype": arch,
                    "roster": mons_list
                })

    return results


# ==============================================================================
# 5. Core Clustering & Meta-Analysis
# ==============================================================================

def cluster_tournament_rosters(entries: List[Dict[str, str]]) -> List[Dict[str, object]]:
    """Groups competitor entries by canonical 6-Pokemon combination."""
    clusters: Dict[Tuple[str, ...], List[Dict[str, str]]] = defaultdict(list)
    canonical_display: Dict[Tuple[str, ...], List[str]] = {}

    for entry in entries:
        roster = [m.strip() for m in entry.get("roster", []) if m.strip()]
        key = tuple(sorted(m.lower() for m in roster))
        if key not in canonical_display:
            canonical_display[key] = roster
        clusters[key].append(entry)

    shared = []
    for key, trainers in clusters.items():
        shared.append({
            "roster": canonical_display[key],
            "count": len(trainers),
            "trainers": trainers
        })
    shared.sort(key=lambda x: x["count"], reverse=True)
    return shared


def summarize_scouted_meta(csv_path: Path = SCOUTED_CSV) -> Dict[str, object]:
    """Generates metagame metrics and most common cores from Scouted_Teams.csv."""
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return {"total_teams": 0, "message": "Scouted_Teams.csv is currently empty."}

    species_counter: Counter = Counter()
    archetype_counter: Counter = Counter()
    mega_counter: Counter = Counter()
    total_teams = 0

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_teams += 1
            arch = row.get("Archetype", "Unknown")
            if arch:
                archetype_counter[arch] += 1
            for i in range(1, 7):
                raw = row.get(f"Pokemon_{i}", "").strip()
                if not raw:
                    continue
                sp = raw.split("@")[0].strip()
                species_counter[sp] += 1
                if "mega" in sp.lower():
                    mega_counter[sp] += 1

    return {
        "total_teams_scouted": total_teams,
        "top_archetypes": archetype_counter.most_common(5),
        "top_species_usage": [
            {"species": sp, "count": c, "usage_pct": round((c / total_teams) * 100.0, 1)}
            for sp, c in species_counter.most_common(12)
        ] if total_teams > 0 else [],
        "top_megas": mega_counter.most_common(5),
    }


def load_tournament_meta(json_path: Path = TOURNAMENT_META_JSON) -> List[Dict[str, object]]:
    """Loads all tournament metagame packages from data/Tournament_Meta.json."""
    if not json_path.exists():
        return []
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def dump_tournament_meta_entry(entry: Dict[str, object], json_path: Path = TOURNAMENT_META_JSON) -> None:
    """Appends or updates a tournament metagame entry in data/Tournament_Meta.json."""
    current = load_tournament_meta(json_path)
    tid = entry.get("tournament_id")
    replaced = False
    for idx, t in enumerate(current):
        if t.get("tournament_id") == tid:
            current[idx] = entry
            replaced = True
            break
    if not replaced:
        current.append(entry)
    json_path.write_text(json.dumps(current, indent=2), encoding="utf-8")


# ==============================================================================
# 6. CLI Entrypoint
# ==============================================================================

def main():
    """CLI entry point for MunchStats metagame scraping and clustering."""
    parser = argparse.ArgumentParser(description="Coach Porygon VGC MunchStats & Scouted Teams Ingestion Engine")
    parser.add_argument("--lookup", nargs="+", help="List of Pokemon species to resolve to a Team ID (e.g. T01, ST01)")
    parser.add_argument("--add-text", type=str, help="Plain text or file containing natural language scouted team")
    parser.add_argument("--player", type=str, help="Player/Competitor name for manual team addition")
    parser.add_argument("--tournament", type=str, default="Sanctioned Tournament", help="Tournament name")
    parser.add_argument("--placement", type=str, default="Top Cut", help="Placement / Finish (e.g. 1st Place, Top 8)")
    parser.add_argument("--paste", type=str, help="Showdown team paste or roster list")
    parser.add_argument("--archetype", type=str, help="Optional archetype override")
    parser.add_argument("--notes", type=str, default="", help="Scouting notes")
    parser.add_argument("--scrape-url", type=str, help="Live MunchStats tournament URL to ingest")
    parser.add_argument("--scrape-file", type=str, help="Saved MunchStats HTML or JSON file to ingest")
    parser.add_argument("--cluster-json", type=str, help="Cluster JSON list of 6-mon cores")
    parser.add_argument("--meta-summary", action="store_true", help="Print metagame summary of Scouted_Teams.csv")
    parser.add_argument("--list-tournaments", action="store_true", help="Mode 6: List all ingested tournament meta records")
    parser.add_argument("--filter-tournament", type=str, help="Mode 6: Filter and dump meta analysis for a specific tournament")
    parser.add_argument("--export-meta-json", type=str, help="Mode 6: Export all tournament meta to specified file")
    args = parser.parse_args()

    # Mode 6: List tournaments
    if args.list_tournaments:
        tournaments = load_tournament_meta()
        print(f"--- INGESTED TOURNAMENTS ({len(tournaments)} total) ---")
        for t in tournaments:
            print(f"* [{t.get('tournament_id')}] {t.get('tournament_name')} ({t.get('date')}) - {t.get('total_players', 0)} players, Top Cut: {t.get('top_cut_size', 0)}")
            champ = t.get("champion", {})
            if champ:
                print(f"   Champion: {champ.get('player')} ({champ.get('archetype')})")
        return

    # Mode 6: Filter tournament
    if args.filter_tournament:
        tournaments = load_tournament_meta()
        q = args.filter_tournament.lower()
        matched = [t for t in tournaments if q in t.get("tournament_name", "").lower() or q in t.get("tournament_id", "").lower()]
        if not matched:
            print(f"No tournament matching '{args.filter_tournament}' found in data/Tournament_Meta.json.")
            return
        t = matched[0]
        print(f"=== METAGAME REPORT: {t.get('tournament_name')} ({t.get('date')}) ===")
        print(f"Division: {t.get('division')} | Total Competitors: {t.get('total_players')}")
        print("\nTOP SPECIES USAGE:")
        for sp in t.get("usage_stats", [])[:10]:
            print(f"  {sp.get('species', ''):<20} | {sp.get('usage_pct')}% ({sp.get('count')} trainers) - {sp.get('role', '')}")
        print("\nTOP ARCHETYPES:")
        for arch in t.get("top_archetypes", []):
            print(f"  {arch.get('archetype', ''):<32} | {arch.get('share_pct')}%")
        print("\nDOMINANT MEGAS:")
        for mega in t.get("dominant_megas", []):
            print(f"  {mega.get('mega', ''):<20} | {mega.get('share_pct')}%")
        return

    # Mode 6: Export Meta JSON
    if args.export_meta_json:
        out_p = Path(args.export_meta_json).resolve()
        tournaments = load_tournament_meta()
        out_p.write_text(json.dumps(tournaments, indent=2), encoding="utf-8")
        print(f"SUCCESS: Exported {len(tournaments)} tournament meta packages to {out_p}")
        return

    # 1. Mode 4 Roster Lookup
    if args.lookup:
        status, matches = resolve_team_id_by_roster(args.lookup)
        if status == "SINGLE_MATCH":
            m = matches[0]
            print(f"[AUTO-RESOLVED TEAM ID]: {m['Team_ID']} ({m.get('Archetype', 'Unknown')}) -> {m['Roster']}")
        elif status == "AMBIGUOUS_MATCH":
            ids = ", ".join(f"{m['Team_ID']} ({m.get('Archetype', '')})" for m in matches)
            print(f"[AMBIGUOUS TEAM ID]: Multiple candidate rosters match {args.lookup}: {ids}. Select one to proceed.")
        else:
            print(
                "[INPUT REQUIRED]: No matching roster found in Teams.csv or Scouted_Teams.csv. "
                "Specify active Team ID or add this roster to proceed."
            )

    # 2. Add via natural plain text
    elif args.add_text:
        text_content = args.add_text
        candidate_path = Path(args.add_text)
        if candidate_path.exists() and candidate_path.is_file():
            text_content = candidate_path.read_text(encoding="utf-8")
        parsed = parse_plain_text_scouted_entry(text_content)
        res = add_scouted_team(
            player=parsed["player"],
            tournament=parsed["tournament"],
            placement=parsed["placement"],
            roster_or_paste=parsed["showdown_export"],
            archetype=parsed["archetype"],
            notes=parsed["notes"],
        )
        print(f"SUCCESS: Registered scouted team [{res['scouted_team_id']}] for {res['player']} ({res['tournament']}) - {res['archetype']}")
        print(f"Roster: {' / '.join(res['roster'])}")

    # 3. Add via explicit CLI flags
    elif args.player and (args.paste or args.add_text):
        paste_text = args.paste or args.add_text
        res = add_scouted_team(
            player=args.player,
            tournament=args.tournament,
            placement=args.placement,
            roster_or_paste=paste_text,
            archetype=args.archetype,
            notes=args.notes,
        )
        print(f"SUCCESS: Registered scouted team [{res['scouted_team_id']}] for {res['player']} - {res['archetype']}")
        print(f"Roster: {' / '.join(res['roster'])}")

    # 4. Scrape URL or Saved File
    elif args.scrape_url or args.scrape_file:
        source = args.scrape_url or args.scrape_file
        print(f"Scraping tournament data from: {source}...")
        try:
            teams = scrape_munchstats_url_or_json(source, tournament_name=args.tournament)
            print(f"SUCCESS: Ingested {len(teams)} teams into data/Scouted_Teams.csv.")
            for t in teams[:5]:
                print(f"  * [{t.get('scouted_team_id', 'STxx')}] {t.get('player')} ({t.get('placement')}): {t.get('archetype')}")
        except Exception as e:
            print(f"ERROR: Could not ingest tournament: {e}", file=sys.stderr)

    # 5. Core Clustering
    elif args.cluster_json:
        cluster_path = Path(args.cluster_json).resolve()
        data = json.loads(cluster_path.read_text(encoding="utf-8"))
        clustered = cluster_tournament_rosters(data)
        print(json.dumps(clustered, indent=2))

    # 6. Meta Summary
    elif args.meta_summary:
        summary = summarize_scouted_meta()
        print(json.dumps(summary, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
