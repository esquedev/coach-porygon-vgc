# -*- coding: utf-8 -*-
"""
Competitive analytics for MunchStats tournament data stored in SQLite.

This module is intentionally separate from ingestion:
- crawling/fetching happens in munchstats_crawler.py
- storage/upserts happen in munchstats_db.py
- read-only analytics here
"""

import json
import sqlite3
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from engine.analytics.munchstats_queries import (
        fetch_standings,
        fetch_team_slots,
        fetch_usage_by_phase,
    )
except ImportError:
    try:
        from munchstats_queries import (
            fetch_standings,
            fetch_team_slots,
            fetch_usage_by_phase,
        )
    except ImportError:
        raise

def infer_team_archetype(species_list: Sequence[str]) -> str:
    """
    Classify a team into a broad competitive archetype.
    This logic is intentionally lightweight and deterministic.
    """
    lower_set = {s.lower() for s in species_list if s}

    is_rain = any(k in lower_set for k in [
        "pelipper", "politoed", "basculegion", "archaludon", "raichu-mega-x"
    ])
    is_sun = any(k in lower_set for k in [
        "torkoal", "charizard-mega-y", "venusaur", "walking wake"
    ])
    is_sand = any(k in lower_set for k in [
        "tyranitar", "tyranitar-mega", "excadrill", "hippowdon"
    ])
    is_trick_room = any(k in lower_set for k in [
        "farigiraf", "rhyperior", "armarouge", "indeedee-f", "dusclops", "torkoal"
    ])
    is_psyspam = any(k in lower_set for k in ["indeedee", "indeedee-f"]) and any(
        k in lower_set for k in ["armarouge", "alakazam", "gardevoir"]
    )

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

def compute_usage_ranking(conn: sqlite3.Connection, tournament_id: str, phase: str = "all", limit: int = 20) -> List[Dict[str, Any]]:
    rows = fetch_usage_by_phase(conn, tournament_id, phase)
    return rows[:limit]

def compute_conversion_matrix(conn: sqlite3.Connection, tournament_id: str) -> List[Dict[str, Any]]:
    """
    Evaluate broad species conversion from Day 1 into Day 2 / Top Cut.
    Treats each species as a pick and looks at its lifecycle across phases.
    """
    standings = fetch_standings(conn, tournament_id)
    total_players = len(standings)
    if total_players == 0:
        return []

    # Build species counts from standings
    d1_counts: Counter[str] = Counter()
    d2_counts: Counter[str] = Counter()
    top16_counts: Counter[str] = Counter()
    top8_counts: Counter[str] = Counter()

    for entry in standings:
        player_name = entry.get("name") or ""
        team = fetch_team_slots(conn, tournament_id, player_name)
        species_seen: set[str] = set()

        for slot in team:
            species = (slot.get("pokemon") or "").strip()
            if not species or species in species_seen:
                continue
            species_seen.add(species)
            d1_counts[species] += 1

            day_reached = entry.get("day_reached") or ""
            if day_reached in ("day2", "top16", "top8"):
                d2_counts[species] += 1
            if day_reached in ("top16", "top8"):
                top16_counts[species] += 1
            if day_reached == "top8":
                top8_counts[species] += 1

    total_d2 = sum(1 for p in standings if (p.get("day_reached") or "") in ("day2", "top16", "top8"))
    total_t16 = sum(1 for p in standings if (p.get("day_reached") or "") in ("top16", "top8"))
    total_t8 = sum(1 for p in standings if (p.get("day_reached") or "") == "top8")

    rows = []
    for species in sorted(d1_counts.keys()):
        d1 = d1_counts[species]
        d2 = d2_counts[species]
        t16 = top16_counts[species]
        t8 = top8_counts[species]

        d1_pct = round((d1 / total_players) * 100.0, 2) if total_players else 0.0
        d2_pct = round((d2 / total_d2) * 100.0, 2) if total_d2 else 0.0
        t16_pct = round((t16 / total_t16) * 100.0, 2) if total_t16 else 0.0
        t8_pct = round((t8 / total_t8) * 100.0, 2) if total_t8 else 0.0

        d1_to_d2 = round((d2 / d1) * 100.0, 2) if d1 else 0.0
        d2_to_t16 = round((t16 / d2) * 100.0, 2) if d2 else 0.0
        d2_to_t8 = round((t8 / d2) * 100.0, 2) if d2 else 0.0

        if t8 > 0 or d2_to_t8 >= 10.0:
            tier = "CHAMPIONSHIP_CONVERTER"
            tag = "CHAMPIONSHIP ENGINE"
            color = "#10b981"
        elif d1_to_d2 >= 15.0 and d2_to_t8 <= 4.0:
            tier = "DAY2_GATEKEEPER"
            tag = "DAY 2 GATEKEEPER"
            color = "#f97316"
        elif d1 <= 3 and d2_to_t8 >= 8.0:
            tier = "SLEEPER_PUNISHER"
            tag = "SLEEPER PUNISHER"
            color = "#f59e0b"
        elif d1_pct >= 20.0 and d2_to_t8 >= 5.0:
            tier = "META_PILLAR"
            tag = "FORMAT PILLAR"
            color = "#06b6d4"
        elif (d1_to_d2 <= 8.0 and d2_to_t16 <= 5.0) or (d1_pct >= 15.0 and t8 == 0):
            tier = "SWISS_TRAP"
            tag = "SWISS TRAP"
            color = "#ef4444"
        else:
            tier = "BALANCED_CHOICE"
            tag = "BALANCED"
            color = "#94a3b8"

        rows.append({
            "species": species,
            "d1_count": d1,
            "d1_pct": d1_pct,
            "d2_count": d2,
            "d2_pct": d2_pct,
            "top16_count": t16,
            "top16_pct": t16_pct,
            "top8_count": t8,
            "top8_pct": t8_pct,
            "d1_to_d2_conv_pct": d1_to_d2,
            "d2_to_top16_conv_pct": d2_to_t16,
            "d2_to_top8_conv_pct": d2_to_t8,
            "tier": tier,
            "tag": tag,
            "color": color,
        })

    rows.sort(key=lambda r: (r["d2_to_top8_conv_pct"], r["top8_count"], r["d2_count"]), reverse=True)
    return rows

def compute_top_cores(conn: sqlite3.Connection, tournament_id: str, size: int = 2, limit: int = 12) -> List[Dict[str, Any]]:
    """
    Finds dominant 2-mon cores by counting species pairs in each team.
    """
    standings = fetch_standings(conn, tournament_id)
    if not standings:
        return []

    pair_counts: Counter[Tuple[str, str]] = Counter()
    pair_placements: Dict[Tuple[str, str], List[int]] = defaultdict(list)

    for entry in standings:
        player_name = entry.get("name") or ""
        team = fetch_team_slots(conn, tournament_id, player_name)
        species = sorted([slot.get("pokemon") or "" for slot in team if slot.get("pokemon")])
        if len(species) < 2:
            continue

        if size == 2:
            for a, b in __import__("itertools").combinations(species, 2):
                if a == b:
                    continue
                pair = tuple(sorted((a, b)))
                pair_counts[pair] += 1
                pair_placements[pair].append(int(entry.get("placement") or 9999))

    results = []
    total_teams = len(standings)
    for pair, count in pair_counts.most_common(limit):
        placements = pair_placements.get(pair, [])
        share_pct = round((count / total_teams) * 100.0, 2) if total_teams else 0.0
        results.append({
            "mon1": pair[0],
            "mon2": pair[1],
            "count": count,
            "share_pct": share_pct,
            "avg_rank": round(sum(placements) / len(placements), 1) if placements else 9999.0,
            "best_rank": min(placements) if placements else 9999,
        })

    return results

def compute_archetype_summary(conn: sqlite3.Connection, tournament_id: str) -> List[Dict[str, Any]]:
    standings = fetch_standings(conn, tournament_id)
    if not standings:
        return []

    archetype_counts: Counter[str] = Counter()
    archetype_best_rank: Dict[str, int] = {}
    archetype_best_player: Dict[str, str] = {}

    for entry in standings:
        player_name = entry.get("name") or ""
        team = fetch_team_slots(conn, tournament_id, player_name)
        species = [slot.get("pokemon") or "" for slot in team if slot.get("pokemon")]
        arch = infer_team_archetype(species)
        archetype_counts[arch] += 1

        rank = int(entry.get("placement") or 9999)
        if arch not in archetype_best_rank or rank < archetype_best_rank[arch]:
            archetype_best_rank[arch] = rank
            archetype_best_player[arch] = player_name

    results = []
    total_teams = len(standings)
    for arch, count in archetype_counts.most_common():
        results.append({
            "archetype": arch,
            "count": count,
            "share_pct": round((count / total_teams) * 100.0, 2) if total_teams else 0.0,
            "best_rank": archetype_best_rank.get(arch, 9999),
            "best_player": archetype_best_player.get(arch, "N/A"),
        })

    return results

def compute_repeated_team_clusters(conn: sqlite3.Connection, tournament_id: str, min_players: int = 2, limit: int = 10) -> List[Dict[str, Any]]:
    standings = fetch_standings(conn, tournament_id)
    if not standings:
        return []

    teams_map: Dict[Tuple[str, ...], List[Dict[str, Any]]] = defaultdict(list)
    for entry in standings:
        player_name = entry.get("name") or ""
        team = fetch_team_slots(conn, tournament_id, player_name)
        mons = sorted([slot.get("pokemon") or "" for slot in team if slot.get("pokemon")])
        if len(mons) == 6:
            key = tuple(mons)
            teams_map[key].append(entry)

    results = []
    total_teams = len(standings)
    for mon_tuple, entries in sorted(teams_map.items(), key=lambda x: len(x[1]), reverse=True)[:limit]:
        if len(entries) < min_players:
            continue

        placements = [int(e.get("placement") or 9999) for e in entries]
        day2_count = sum(1 for e in entries if (e.get("day_reached") or "") in ("day2", "top16", "top8"))
        top16_count = sum(1 for e in entries if (e.get("day_reached") or "") in ("top16", "top8"))
        top8_count = sum(1 for e in entries if (e.get("day_reached") or "") == "top8")

        results.append({
            "roster": list(mon_tuple),
            "player_count": len(entries),
            "share_pct": round((len(entries) / total_teams) * 100.0, 2) if total_teams else 0.0,
            "day2_count": day2_count,
            "day2_conv_pct": round((day2_count / len(entries)) * 100.0, 2) if entries else 0.0,
            "top16_count": top16_count,
            "top8_count": top8_count,
            "best_rank": min(placements),
            "avg_rank": round(sum(placements) / len(placements), 1) if placements else 9999.0,
            "archetype": infer_team_archetype(list(mon_tuple)),
        })

    return results

def analyze_tournament(conn: sqlite3.Connection, tournament_id: str) -> Dict[str, Any]:
    standings = fetch_standings(conn, tournament_id)
    if not standings:
        return {
            "tournament_id": tournament_id,
            "status": "NO_DATA",
            "standings_count": 0,
        }

    champion = min(standings, key=lambda x: int(x.get("placement") or 9999))
    champion_name = champion.get("name") or "Competitor"
    champion_team = fetch_team_slots(conn, tournament_id, champion_name)
    champion_species = [slot.get("pokemon") or "" for slot in champion_team if slot.get("pokemon")]

    summary = {
        "tournament_id": tournament_id,
        "status": "OK",
        "standings_count": len(standings),
        "champion": {
            "name": champion_name,
            "placement": int(champion.get("placement") or 9999),
            "day_reached": champion.get("day_reached"),
            "archetype": infer_team_archetype(champion_species),
            "record": {
                "wins": int(champion.get("wins") or 0),
                "losses": int(champion.get("losses") or 0),
            },
            "species": champion_species,
        },
        "usage_ranking_all": compute_usage_ranking(conn, tournament_id, phase="all", limit=20),
        "usage_ranking_day1": compute_usage_ranking(conn, tournament_id, phase="day1", limit=20),
        "usage_ranking_day2": compute_usage_ranking(conn, tournament_id, phase="day2", limit=20),
        "usage_ranking_top8": compute_usage_ranking(conn, tournament_id, phase="top8", limit=20),
        "conversion_matrix": compute_conversion_matrix(conn, tournament_id),
        "top_cores": compute_top_cores(conn, tournament_id, size=2, limit=12),
        "archetype_summary": compute_archetype_summary(conn, tournament_id),
        "repeated_team_clusters": compute_repeated_team_clusters(conn, tournament_id, min_players=2, limit=10),
    }
    return summary
