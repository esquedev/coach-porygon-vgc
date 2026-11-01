---
name: munchstats-meta
description: >-
  Ingests, clusters, analyzes, and queries tournament metagame data from MunchStats
  (www.munchstats.com/tournaments/) into structured datasets for filtering, telemetry, and coaching strategy.
---

# MunchStats Metagame Intelligence & Tournament Analytics

Autonomous metagame intelligence powered by competitive tournament data from **MunchStats** (`www.munchstats.com/tournaments/`) and official Play! Pokémon tournament brackets.

## 1. Purpose & Overview
Provides empirical metagame grounding for Coach Porygon:
1. **Tournament Usage Tracking:** Species usage rates, Mega Evolution distribution, common items, abilities, movesets, and Champion archetypes per tournament.
2. **Multiphase Conversion Dynamics:** Rigorous statistical ratio calculations measuring how effectively species, cores, and archetypes transition across all tournament stages:
   $$\text{D1} \to \text{D2 Conversion (\%)} = \left(\frac{\text{Day 2 Count}}{\text{Day 1 Count}}\right) \times 100\%$$
   $$\text{D2} \to \text{Top Cut Conversion (\%)} = \left(\frac{\text{Top Cut Count}}{\text{Day 2 Count}}\right) \times 100\%$$
3. **Pick Evaluation Taxonomy:** Categorizes competitive species into actionable tactical tiers:
   - `CHAMPIONSHIP_CONVERTER`: Disproportionately high Day 2 $\to$ Top Cut conversion ($\ge 10.0\%$) or Champion presence.
   - `DAY2_GATEKEEPER`: Strong Day 1 $\to$ Day 2 conversion ($\ge 15.0\%$), but severely drops off in Top Cut ($\le 4.0\%$).
   - `SLEEPER_PUNISHER`: Low Day 1 field share ($\le 12.0\%$), but explosive Day 2 $\to$ Top Cut efficiency ($\ge 8.0\%$).
   - `SWISS_TRAP`: High Day 1 popularity that collapses in Day 2 or achieves 0 Top Cut finishes.
   - `META_PILLAR`: High field share ($\ge 20.0\%$) with consistent multi-phase survival.
4. **Hive-Mind Consensus & Repeated Teams Mining:** Tracks identical 6-mon team registrations brought by testing squads, evaluating pilot attrition, collective conversion rates, and best pilot finishes.
5. **Archetype Attrition Waterfall:** Measures macro-archetype shifts from the open field into the Top 8 podium.
6. **Structured Data Governance:** Ingestion and management of persistent datasets:
   - `data/MunchStats_Overview.csv` (Template: `data/MunchStats_Overview.example.csv`)
   - `data/MunchStats_Usage.csv` (Template: `data/MunchStats_Usage.example.csv`)
   - `data/MunchStats_Top_Teams.csv` (Template: `data/MunchStats_Top_Teams.example.csv`)
   - `data/MunchStats_Pokemon_Sets.csv` (Template: `data/MunchStats_Pokemon_Sets.example.csv`)
   - `data/Scouted_Teams.csv` (Curated Top Cut Open Team Sheets)
   - `data/munchstats/raw/{tournament_slug}/` (Raw crawled JSON/CSV dumps)
   - `data/munchstats/output/{tournament_slug}/` (Statistical audits, HTML reports, and compiled PDFs)
7. **Visual Publication Engine:** Run [`engine/munchstats_analyzer.py`](../../../engine/munchstats_analyzer.py) to compile tournament analysis data, and invoke the [`report-generator`](../report-generator/SKILL.md) skill with [`engine/pdf_exporter.py`](../../../engine/pdf_exporter.py) to compile print-ready, publication-grade HTML and headless Chrome/Edge PDF metagame reports.

---

## 2. Supported VGC 2027 Tournaments
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

## 3. Execution Pipeline & 3-Tier Fallback Hierarchy

Whenever a tournament link or identifier is submitted (e.g. `https://www.munchstats.com/tournaments/BA002-JL3KVbvivVKNAc/all/`):

### 🥇 Tier 1 (Primary): Deterministic Python Crawler & Analyzer Pipeline
1. **Extraction & Raw Dump (`engine/munchstats_crawler.py`):**
   ```bash
   python engine/munchstats_crawler.py --url "<TOURNAMENT_URL>"
   ```
   - Fetches official REST API endpoints (`/tournaments/api/{id}/all/`, `/standings?day=all`, `/day1/`, `/day2/`, `/top8/`).
   - Extracts complete tournament overview, stages, and Day 1 $\to$ Day 2 movers.
   - Writes raw datasets to `data/munchstats/raw/{tournament_slug}/` (*overview.json*, *standings.json*, *standings.csv*, *usage.json*, *usage.csv*).
   - Automatically registers the top 16 highest-impact teams (Top Cut finalists & top archetypes) into `data/Scouted_Teams.csv` with sequential `STxx` IDs without saturating storage.

2. **Statistical Analysis & Visual Report Compilation (`engine/munchstats_analyzer.py`):**
   ```bash
   python engine/munchstats_analyzer.py --tournament-slug "<TOURNAMENT_SLUG>"
   ```
   - Computes multi-phase conversion dynamics across Day 1, Day 2, Top 16, and Top 8.
   - Evaluates picks under the competitive taxonomy (`CHAMPIONSHIP_CONVERTER`, `DAY2_GATEKEEPER`, `SLEEPER_PUNISHER`, `SWISS_TRAP`, `META_PILLAR`).
   - Mines hive-mind consensus teams (most repeated 6-mon rosters) with conversion rates and Showdown pastes.
   - Computes the macro-archetype attrition waterfall.
   - Generates executive Markdown report (*vgc_coaching_report.md*) and structured JSON (*vgc_analytics_summary.json*).
   - Compiles publication-grade, self-contained HTML report (*tournament_report.html*) with embedded base64 sprites.
   - Compiles print-ready PDF (*tournament_report.pdf*) using local headless Google Chrome or Microsoft Edge.

3. **Ad-Hoc In-Memory Relational Queries (`--sql` / `--query`):**
   Agents and coaches can interrogate tournament standings directly using standard SQL without disk overhead or database locks. `MunchStatsRelationalEngine` spins up an in-memory SQLite database (`:memory:`) and indexes all competitors, team slots, items, and moves in <15ms:
   ```bash
   python engine/munchstats_analyzer.py -s "<TOURNAMENT_SLUG>" --sql "<SQL_QUERY>"
   ```

   **In-Memory Relational Schema:**
   - `competitors`: `player_id`, `name`, `placement`, `day_reached` (`day1` | `day2` | `top16` | `top8`), `wins`, `losses`
   - `team_members`: `member_id`, `player_id`, `slot`, `species`, `item`, `ability`, `nature`, `tera_type`
   - `moves`: `move_id`, `member_id`, `move_name`

   **High-Leverage Relational Queries:**
   - *Top Cut Conversion Rates:*
     ```sql
     SELECT tm.species, COUNT(DISTINCT c.player_id) AS total_pilots,
            COUNT(DISTINCT CASE WHEN c.day_reached IN ('day2', 'top16', 'top8') THEN c.player_id END) AS d2_pilots,
            ROUND(COUNT(DISTINCT CASE WHEN c.day_reached IN ('day2', 'top16', 'top8') THEN c.player_id END) * 100.0 / COUNT(DISTINCT c.player_id), 1) AS conv_pct
     FROM team_members tm JOIN competitors c ON tm.player_id = c.player_id
     GROUP BY tm.species HAVING total_pilots >= 5
     ORDER BY conv_pct DESC LIMIT 10;
     ```
   - *Dominant 2-Mon Cores in Top 16:*
     ```sql
     SELECT m1.species AS mon_1, m2.species AS mon_2, COUNT(*) AS frequency
     FROM team_members m1
     JOIN team_members m2 ON m1.player_id = m2.player_id AND m1.species < m2.species
     JOIN competitors c ON m1.player_id = c.player_id
     WHERE c.placement <= 16
     GROUP BY mon_1, mon_2 ORDER BY frequency DESC LIMIT 10;
     ```
   - *Item & Move Distribution for Specific Species:*
     ```sql
     SELECT tm.item, tm.ability, m.move_name, COUNT(*) AS count
     FROM team_members tm
     JOIN moves m ON tm.member_id = m.member_id
     WHERE tm.species = 'Charizard-Mega-Y'
     GROUP BY tm.item, tm.ability, m.move_name ORDER BY count DESC LIMIT 15;
     ```

---

### 🥈 Tier 2 (Fallback 1): HTML DOM Parsing & Elevated Sandbox Probing
If external API access is blocked or restricted by network boundaries:
1. Parse the initial HTML page source to extract `window.hubOverview` (`stages`, `movers`, and top 10 species per phase).
2. Request manual elevation / sandbox bypass for probing network endpoints if live API requests fail with permission errors.
3. Serialize recovered data directly into `data/munchstats/raw/` and trigger `engine/munchstats_analyzer.py`.

---

### 🥉 Tier 3 (Fallback 2): Conversational Agent Synthesis & Local Compendium
If external network is completely offline or the remote host is unreachable:
1. Fallback to local offline tournament archives: `data/Tournament_Meta.json`, `data/Munchstats_Aggregate_Meta.json`, and `data/Scouted_Teams.csv`.
2. Synthesize metagame intelligence directly in chat using natural language reasoning:
   - Identify counter-leads for active archetypes (Rain, Sun, Trick Room, Psyspam, Goodstuffs Balance).
   - Formulate Swiss Day 1 vs. Day 2 flowcharting recommendations grounded in verified Regulation M-C data.

---

## 4. Head Coach Tactical Interpretation Directives

When coaching a Trainer on tournament telemetry, enforce the following strategic rules:

1. **Avoid Day 1 Popularity Bias:** Never recommend a Pokémon solely based on high Day 1 usage. Cross-reference whether the pick is a **Day 2 Gatekeeper** (e.g. Gholdengo or Incineroar in Baltimore, which convert well in early Swiss but hit a ceiling before Top 8) versus a **Championship Converter** (e.g. Politoed, Milotic, or Staraptor-Mega, whose conversion to Top 8 is 2x–5x higher than average).
2. **Exploiting Hive-Mind Consensus Teams:** In Mode 4 (OTS Swiss Flowcharting), check if the opponent's roster matches one of the most repeated 6-mon teams mined in *vgc_analytics_summary.json*. If it matches, the Trainer gains full foreknowledge of the squad's testing group origin, EV tendencies, and standard turn-1 lead patterns.
3. **Archetype Divergence Warnings:** Always highlight when a popular variant within an archetype is failing while another thrives (e.g. in Baltimore 2027: *Rain Archaludon* achieved 25% of Top 8, whereas *Rain Electric Seed* suffered a 0.0% Top Cut conversion rate).

---

## 5. Guardrails & Compliance
1. **Regulation M-C Legal Grounding:** Validate all ingested species against `data/MC_Available_Pokemon.csv` and items against `data/Regulation_MC_Items.csv`.
2. **Species Blacklist Enforcement:** Reject non-format staples (`Ursaluna`, `Flutter Mane`, `Urshifu`, `Amoonguss`, `Gastrodon`, `Landorus-T`, etc.) with `[ILLEGAL_FORMAT_SPECIES]`.
3. **OWASP Formula Injection Defense:** Sanitize any cells beginning with `=`, `+`, `-`, or `@` with a leading apostrophe before serializing to CSV.
4. **Deterministic Output:** Zero hallucination of player names or win-loss records; flag unconfirmed stats with `[DATA_UNVERIFIED]`.
