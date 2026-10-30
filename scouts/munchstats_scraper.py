import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
TEAMS_CSV = REPO_ROOT / "data" / "Teams.csv"
SCOUTED_CSV = REPO_ROOT / "data" / "Scouted_Teams.csv"


def normalize_species_set(roster: List[str]) -> Set[str]:
    cleaned = set()
    for mon in roster:
        if not mon or not mon.strip():
            continue
        # Strip item ("@ ...") and gender ("(M)" / "(F)")
        base = mon.split("@")[0].replace("(M)", "").replace("(F)", "").strip().lower()
        if base:
            cleaned.add(base)
    return cleaned


def extract_row_roster(row: Dict[str, str]) -> List[str]:
    if "Pokemon_1" in row:
        return [row.get(f"Pokemon_{i}", "") for i in range(1, 7) if row.get(f"Pokemon_{i}", "")]
    if "Roster" in row:
        return row["Roster"].split("/")
    return []


def resolve_team_id_by_roster(active_mons: List[str]) -> Tuple[str, List[Dict[str, str]]]:
    """
    Implements the Automated Team ID Resolution & Lookup Protocol:
    Searches Teams.csv (T01-T23) and Scouted_Teams.csv (ST01-ST06) for an exact
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
                    team_id = row.get("Team_ID") or row.get("Column 1") or row.get("Scouted_Team_ID") or "Unknown"
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


def cluster_tournament_rosters(entries: List[Dict[str, str]]) -> List[Dict[str, object]]:
    """
    Groups tournament competitor entries by canonical 6-Pokemon combination.
    Each entry expects: {"player": str, "placement": str, "roster": List[str]}
    """
    clusters: Dict[Tuple[str, ...], List[Dict[str, str]]] = defaultdict(list)
    canonical_display: Dict[Tuple[str, ...], List[str]] = {}

    for entry in entries:
        roster = [m.strip() for m in entry.get("roster", []) if m.strip()]
        key = tuple(sorted(m.lower() for m in roster))
        if key not in canonical_display:
            canonical_display[key] = roster
        clusters[key].append(entry)

    shared = []
    for key, pilots in clusters.items():
        shared.append({
            "roster": canonical_display[key],
            "count": len(pilots),
            "pilots": pilots
        })
    shared.sort(key=lambda x: x["count"], reverse=True)
    return shared


def main():
    parser = argparse.ArgumentParser(description="Coach Porygon VGC Roster Lookup & Munchstats Clusterer")
    parser.add_argument("--lookup", nargs="+", help="List of Pokemon species to resolve to a Team ID (e.g. T01, ST01)")
    parser.add_argument("--cluster-json", type=str, help="Path to tournament JSON list to cluster shared 6-mon cores")
    args = parser.parse_args()

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
                "[INPUT REQUIRED]: No matching roster found in Proto#1–Proto#5, Teams.csv, or Scouted_Teams.csv. "
                "Specify your active Team ID (e.g., T01, ST01) or register this roster to proceed."
            )
    elif args.cluster_json:
        cluster_path = Path(args.cluster_json).resolve()
        if cluster_path.stat().st_size > 1_048_576:
            raise ValueError("Cluster JSON file exceeds 1 MB limit.")
        data = json.loads(cluster_path.read_text(encoding="utf-8"))
        clustered = cluster_tournament_rosters(data)
        print(json.dumps(clustered, indent=2))


if __name__ == "__main__":
    main()
