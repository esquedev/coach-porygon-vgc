---
name: team-modes-and-preview-playbook
description: Analyzes any 6-Pokémon Regulation M-C roster to compute all 15 4-mon mini-cores (modes) and 15 lead combinations against DuckDB regional tournament usage. Generates a 4-Step 90-Second Team Preview Execution Protocol, an If-Then-Else Decision-Tree Rulebook with zero-hallucination move grounding, deterministic local sprites via assets/slug_map.json, and live telemetry sync from data/telemetry/battles_telemetry.csv.
---

# Team Modes & Team Preview Playbook Skill

Use this skill whenever the user asks to analyze team modes (4-mon options), evaluate lead pairings, explore matchup weaknesses/strengths against tournament archetypes, or generate/update their 90-second Team Preview Execution Protocol and Rulebook.

---

## 1. Capabilities & Architecture

When invoked, this skill executes the Regulation M-C combinatorics and protocol engine:
1. **Deterministic Sprite & Item Slug Indexing (`assets/slug_map.json`)**:
   - Built via `scripts/build_sprite_slug_map.py`.
   - Maps all legal Champions Pokédex species, regional formes, gender variants, and Mega Stones to exact local PNG paths (Note: `assets/**/*.png` is shielded in `.geminiignore` to avoid context clutter; always resolve sprites via `assets/slug_map.json`).
2. **4-Step 90-Second Team Preview Execution Protocol**:
   - **Step 1 (00s–15s)**: Scan Opponent Speed & Field Mechanism (Tailwind, Rain, Sun, Trick Room/Psyspam, Intimidate Balance, Sand, Snow).
   - **Step 2 (15s–40s)**: Lock Bring-4 Mode (bench the 2 liabilities).
   - **Step 3 (40s–65s)**: Lock Lead Pair & Reserve Backline.
   - **Step 4 (65s–90s)**: Pre-commit Turn 1 Verified Move Commands (with Branch B switch/protect contingency).
3. **If-Then-Else Decision-Tree Rulebook (Zero-Hallucination Move Grounding)**:
   - Evaluates the 8 canonical Regulation M-C archetypes from DuckDB (`tournament_team_slots`) via `engine.modes` (`TeamModeAnalyzer` & `TournamentArchetypeMatcher`).
   - Strictly decouples **Screens** (`Reflect`, `Light Screen`, `Aurora Veil`) from **Pivoting** (`Volt Switch`, `Parting Shot`, `U-turn`).
   - Verifies that every Turn 1 command belongs to the active Pokémon's exact 4-move set.
4. **Live Practice Telemetry Context**:
   - Reads `data/telemetry/battles_telemetry.csv` to overlay empirical match counts, win rates per lead/mode, and coach post-mortem comments directly into the generated report.

---

## 2. Execution Workflow

### Step 1: Rebuild Slug Map (If New Assets Were Added — e.g., Regulation M-D Sprites)
```bash
.venv/bin/python scripts/build_sprite_slug_map.py
```

### Step 2: Run the Domain Combinatorics & Archetype Engine (`engine.modes`)
Compute all 15 4-mon modes, 15 lead pairs, and 8 tournament archetype matchup plans directly via Python (`engine.modes`):

```python
from pathlib import Path
from engine.db_registry import get_registry
from engine.modes import TeamModeAnalyzer, TournamentArchetypeMatcher

reg = get_registry()
paste = Path("data/teams/<team>.txt").read_text(encoding="utf-8")
members, modes, leads = TeamModeAnalyzer(reg).analyze_team(paste)
plans = TournamentArchetypeMatcher(reg).generate_all_plans(modes, leads)
```

### Step 3: Present Tactical Coaching Summary (or Render Interactive HTML/Markdown on Demand)
Using the verified `plans`, `modes`, `leads`, `assets/slug_map.json`, and optional `data/telemetry/` CSV records, present the structured GFM tables directly in chat or generate a tailored interactive HTML report under `reports/` when requested.
