---
name: munchstats-meta
description: Ingests, clusters, analyzes, and dumps tournament metagame data from MunchStats (www.munchstats.com/tournaments/) into structured datasets for filtering, telemetry, and UI visualization.
---

# Mode 6: MunchStats Meta Analysis & Tournament Dumper

## 1. Purpose & Overview
Mode 6 provides autonomous metagame intelligence by scraping, parsing, clustering, and dumping competitive tournament data from **MunchStats** (`www.munchstats.com/tournaments/`) and official Play! Pokémon tournament brackets.

It powers:
1. **Tournament Usage Tracking:** Species usage rates, Mega Evolution distribution, common items, abilities, movesets, and Champion archetypes per tournament.
2. **Day 1 vs. Day 2 Conversion Rates:** Rigorous statistical ratio calculations measuring how effectively species and cores transition from Swiss Day 1 into Day 2 and Top Cut.
3. **Core Clustering & Archetype Identification:** Identification of 2-mon and 6-mon core clusters across tournament Top Cuts.
4. **Structured Data Dumper & Governance:** Continuous export to the 5 official MunchStats datasets (`data/MunchStats_Overview.csv`, `data/MunchStats_Usage.csv`, `data/MunchStats_Standings.csv`, `data/MunchStats_Top_Teams.csv`, `data/MunchStats_Pokemon_Sets.csv`) and their corresponding schema templates (`data/MunchStats_Overview.example.csv`, etc.).

---

## 2. Ingestion & Analytics Pipeline

Run the automated pipeline to compile and refresh all 5 governance datasets across all 7 official VGC 2027 regional tournaments (`PB002`, `NC002`, `LO002`, `RE002`, `FR002`, `BR002`, `BA002`):

```powershell
python scouts/munchstats_pipeline.py
```

### Supported VGC 2027 Tournaments
| Code | ID | Tournament Name | Location | Format |
|---|---|---|---|---|
| `PB002` | `TM_PUEBLA_2027` | Puebla Regional Championships | Puebla, Mexico | Regulation M-C |
| `NC002` | `TM_NICE_2027` | Nice Regional Championships | Nice, France | Regulation M-C |
| `LO002` | `TM_LOUISVILLE_2027` | Louisville Regional Championships | Louisville, USA | Regulation M-C |
| `RE002` | `TM_RECIFE_2027` | Recife Regional Championships | Recife, Brazil | Regulation M-C |
| `FR002` | `TM_FRANKFURT_2027` | Frankfurt Regional Championships | Frankfurt, Germany | Regulation M-C |
| `BR002` | `TM_BRISBANE_2027` | Brisbane Regional Championships | Brisbane, Australia | Regulation M-C |
| `BA002` | `TM_BALTIMORE_2027` | Baltimore Regional Championships | Baltimore, USA | Regulation M-C |

---

## 3. Data Governance & Table Schemas

### Table 1: `data/MunchStats_Overview.csv` (Template: `data/MunchStats_Overview.example.csv`)
High-level tournament intelligence, attendance numbers, Day 2 cuts, Champion identity, and dominant Mega Evolution.
* **Fields:** `Tournament_ID`, `MunchStats_ID`, `Tournament_Name`, `Location`, `Date`, `Division`, `Total_Players`, `Day2_Players`, `Top_Cut_Size`, `Champion_Player`, `Champion_Archetype`, `Dominant_Mega`, `Dominant_Mega_Usage_Pct`, `Notes`

### Table 2: `data/MunchStats_Usage.csv` (Template: `data/MunchStats_Usage.example.csv`)
Species usage metrics across tournament phases with conversion rate mathematics.
* **Fields:** `Tournament_ID`, `Phase`, `Rank`, `Species`, `Raw_Count`, `Usage_Pct`, `Day1_Count`, `Day1_Usage_Pct`, `Day2_Count`, `Day2_Usage_Pct`, `Conversion_Rate_Pct`, `Top_Cut_Count`, `Top_Cut_Usage_Pct`, `Most_Common_Item`, `Most_Common_Ability`, `Most_Common_Moves`
* **Conversion Rate Formula:**
  $$\text{Conversion Rate (\%)} = \left(\frac{\text{Day 2 Count}}{\text{Day 1 Count}}\right) \times 100\%$$

### Table 3: `data/MunchStats_Standings.csv` (Template: `data/MunchStats_Standings.example.csv`)
Every competitor's final placement, Swiss record, Day reached, and full 6-mon Open Team Sheet roster.
* **Fields:** `Tournament_ID`, `Placement`, `Numeric_Rank`, `Player_Name`, `Record`, `Day_Reached`, `Archetype`, `Pokemon_1`..`Pokemon_6`

### Table 4: `data/MunchStats_Top_Teams.csv` (Template: `data/MunchStats_Top_Teams.example.csv`)
Repeated 6-mon core clusters, frequency count, archetype, cluster tournament share, and best placement.
* **Fields:** `Tournament_ID`, `Team_Cluster_ID`, `Archetype`, `Roster_Size`, `Frequency_Count`, `Cluster_Share_Pct`, `Highest_Placement`, `Best_Player`, `Pokemon_1`..`Pokemon_6`, `Core_Synergy_Notes`

### Table 5: `data/MunchStats_Pokemon_Sets.csv` (Template: `data/MunchStats_Pokemon_Sets.example.csv`)
Empirical item, ability, nature, and 4-move distributions per species.
* **Fields:** `Tournament_ID`, `Species`, `Set_Rank`, `Item`, `Ability`, `Nature`, `Move_1`, `Move_2`, `Move_3`, `Move_4`, `Count`, `Set_Share_Pct`

---

## 4. Guardrails & Compliance
1. **Regulation M-C Legal Grounding:** Validate all ingested species against `data/MC_Available_Pokemon.csv` and items against `data/Regulation_MC_Items.csv`.
2. **Species Blacklist Enforcement:** Reject non-format staples (`Ursaluna`, `Flutter Mane`, `Urshifu`, `Amoonguss`, `Gastrodon`, `Landorus-T`, etc.) with `[ILLEGAL_FORMAT_SPECIES]`.
3. **OWASP Formula Injection Defense:** Sanitize any cells beginning with `=`, `+`, `-`, or `@` with a leading apostrophe before serializing to CSV.
4. **Deterministic Output:** Zero hallucination of player names or win-loss records; flag unconfirmed stats with `[DATA_UNVERIFIED]`.
