---
name: mode6-munchstats-meta
description: Ingests, clusters, analyzes, and dumps tournament metagame data from MunchStats (www.munchstats.com/tournaments/) into structured datasets for filtering, telemetry, and UI visualization.
---

# Mode 6: MunchStats Meta Analysis & Tournament Dumper

## 1. Purpose & Overview
Mode 6 provides autonomous metagame intelligence by scraping, parsing, clustering, and dumping competitive tournament data from **MunchStats** (`www.munchstats.com/tournaments/`) and official Play! Pokémon tournament brackets.

It powers:
1. **Tournament Usage Tracking:** Species usage rates, Mega Evolution distribution, common items, and Tera/Champion archetypes per tournament.
2. **Session & Tournament Slicing:** Ability to filter match telemetry, scouted teams, and archetype trends by specific tournament (e.g. *2027 Nice Regional*, *2027 Charlotte Regional*, *2027 Utrecht Special Event*).
3. **Core Clustering & Archetype Identification:** Identification of 2-mon and 6-mon core clusters across tournament Top Cuts.
4. **Structured Data Dumper:** Continuous export to `data/Tournament_Meta.json` and `data/Scouted_Teams.csv` for consumption by the Command Center UI and Mode 4 Flowcharts.

---

## 2. Ingestion Protocols

### Protocol A: Natural Language & Plain Text Meta Dump
When network access is restricted or the user pastes tournament summary text, standings, or MunchStats exports:
```powershell
python scouts/munchstats_scraper.py --dump-meta-text "path/to/tournament_dump.txt" --tournament "2027 Nice Regional Championships"
```

### Protocol B: Direct Web Ingestion (Outside Sandbox)
```powershell
python scouts/munchstats_scraper.py --scrape-url "https://www.munchstats.com/tournaments/nice-2027" --tournament "2027 Nice Regional Championships"
```

### Protocol C: Metagame Export for UI Filtering
```powershell
python scouts/munchstats_scraper.py --export-meta-json data/Tournament_Meta.json
```

---

## 3. Data Schema: `data/Tournament_Meta.json`
Every ingested tournament produces a validated entry containing:
```json
{
  "tournament_id": "TM_NICE_2027",
  "tournament_name": "2027 Nice Regional Championships",
  "date": "2027-02-14",
  "division": "Masters",
  "total_players": 482,
  "top_cut_size": 16,
  "usage_stats": [
    { "species": "Raichu-Mega-X", "count": 184, "usage_pct": 38.2 },
    { "species": "Sneasler", "count": 165, "usage_pct": 34.2 },
    { "species": "Garchomp", "count": 150, "usage_pct": 31.1 }
  ],
  "top_archetypes": [
    { "archetype": "Rain Electric Seed Offense", "share_pct": 24.5 },
    { "archetype": "Dual Mega Disruption Balance", "share_pct": 19.8 }
  ],
  "dominant_megas": [
    { "mega": "Mega Raichu X", "share_pct": 31.0 },
    { "mega": "Mega Charizard Y", "share_pct": 26.5 }
  ]
}
```

---

## 4. Guardrails & Compliance
1. **Regulation M-C Legal Grounding:** Validate all ingested species against `data/MC_Available_Pokemon.csv` and items against `data/Regulation_MC_Items.csv`.
2. **Species Blacklist Enforcement:** Reject non-format staples (Ursaluna, Flutter Mane, Urshifu, Amoonguss, Gastrodon, Landorus-T) with `[ILLEGAL_FORMAT_SPECIES]`.
3. **Deterministic Output:** Zero hallucination of player names or win-loss records; flag unconfirmed stats with `[DATA_UNVERIFIED]`.
