# Coach Porygon VGC — Autonomous Regulation M-C Coaching & Simulation Runtime

**Coach Porygon VGC** is an agentic esports coaching, scouting, and deterministic turn-simulation runtime built for the **Pokémon Champions (Regulation M-C)** competitive ecosystem. Instead of relying on LLM mental math, it combines always-on agent rules, modular operational skills, a Showdown-accurate `0x1000` fixed-point turn simulator, and automated telemetry logging.

---

## 1. Repository Architecture & How Agent Behavior is Configured

When you open this repository in **Antigravity**, the agent automatically configures its behavior from three layers:

```text
coach-porygon-vgc/
├── AGENTS.md                        # Root architectural map (always loaded)
├── .agents/
│   ├── rules/                       # Always-on system constraints & guardrails
│   │   ├── engine_rules.md          # Reg M-C mechanics, 66-SP math, VP track, Team ID lookup
│   │   └── mistake_taxonomy.md      # POS/TGT/MEC/SPD error codes, cognitive traps, guardrails
│   └── skills/                      # On-demand operational mode runbooks (Modes 1–5)
│       ├── mode1-replay-audit/      # Mode 1: Replay breakdown, VP Turning Point, TSV & Webhook
│       ├── mode2-roster-budget/     # Mode 2: 66-SP roster engineering & verification strings
│       ├── mode3-crucible-spar/     # Mode 3: 45-second board sparring & reflex flashcards
│       ├── mode4-ots-flowchart/     # Mode 4: Bo3 Open Team Sheet (OTS) Swiss flowcharting
│       └── mode5-sports-psych/      # Mode 5: Tilt debriefs & cognitive leak eradication
├── engine/                          # Deterministic execution scripts
│   ├── turn_simulator.py            # Showdown 0x1000 fixed-point doubles turn micro-simulator
│   ├── sp_calculator.py             # 66-SP budget validator & Level 50 floor stat calculator
│   └── telemetry.py                 # TSV damage calc logger & Google Apps Script webhook builder
├── scouts/                          # Tournament scouting & Pokedex verification pipeline
│   ├── munchstats_scraper.py        # Automated Team ID resolver (Txx / STxx) & core clusterer
│   └── pokedex_resolver.py          # Cache-first species/move verifier & 1-Attempt query builder
└── data/                            # Local CSV database & Markdown compendium
    ├── Teams.csv                    # Registered personal rosters (T01–T23)
    ├── Scouted_Teams.csv            # Private tournament OTS rosters (gitignored; see .example.csv)
    ├── Raw_Matches.csv              # Full historical match telemetry log
    ├── Playstyle_Diagnostics.csv    # Private mistake & VP delta tracker (gitignored; see .example.csv)
    ├── Damage_Calculations.csv      # Indexed Showdown damage calculations (CALC_001+)
    ├── MC_Available_Pokemon.csv     # All 335 legal Reg M-C species & Mega forms + base stats
    ├── Regulation_MC_Items.csv      # Legal Hold Items, Berries, and Mega Stones
    └── compendium/                  # Markdown mechanics compendium & M-C Calcs & Sets.md
```

### How to Modify My Behavior
* **Change Core Mechanics or Rules:** Edit [`.agents/rules/engine_rules.md`](.agents/rules/engine_rules.md). Because it has `trigger: always_on`, any edit you make takes effect on the very next prompt.
* **Add/Edit Mistake Codes or Guardrails:** Edit [`.agents/rules/mistake_taxonomy.md`](.agents/rules/mistake_taxonomy.md).
* **Tune Specific Mode Output Formats:** Edit the `SKILL.md` file inside the corresponding `.agents/skills/modeX-.../` folder.

---

## 2. How to Trigger Each Mode in Chat (Quick-Start Prompts)

You do not need to paste rules or system prompts anymore—just talk to the agent directly. Here is how to trigger each mode:

### Mode 0: General Coaching & Theorycrafting
Ask any metagame or mechanical question conversationally.
> **Example Prompt:**
> *"How does Mega Charizard Y's Activation Phase speed recalibration interact with Prankster Tailwind and Fake Out on Turn 1?"*

### Mode 1: Replay Audit & Direct CSV Telemetry Logging (`mode1-replay-audit`)
Paste a Showdown replay log, turn-by-turn summary, or match result. The agent will auto-resolve your Team ID from `data/Teams.csv`, simulate the Turning Point via `engine/turn_simulator.py`, assign error codes (`POS-xx`, `TGT-xx`, `MEC-xx`, `SPD-xx`), and write all telemetry directly into `data/Raw_Matches.csv`, `data/Playstyle_Diagnostics.csv`, and `data/Damage_Calculations.csv`.
> **Example Prompt:**
> *"Audit this Bo1 ladder match (Start Rating: 1051 -> 1033): [paste replay log or turn summary]"*

### Mode 2: 66-SP Roster Engineering (`mode2-roster-budget`)
Ask to build or optimize a Pokémon spread under the 66-SP cap (`<= 32 SP` per stat). The agent runs `engine/sp_calculator.py` to verify the math and outputs the Mandatory Verification String.
> **Example Prompt:**
> *"Mode 2: Build a Modest Mega Charizard Y 66-SP spread that hits at least 146 Speed and survives 32+ Atk Sneasler Rock Slide."*

### Mode 3: 45-Second Crucible Sparring (`mode3-crucible-spar`)
Ask for a live 45-second mid-game board state or rapid-fire reflex flashcards. When you reply with your double-slot move choices, the agent runs `engine/turn_simulator.py` to referee the turn and audits your line against the opponent's minimax counter-play.
> **Example Prompt:**
> *"Mode 3: Put me in the 45-Second Crucible using T23 against Rain Archaludon (`ST02`), Turn 3 mid-game."*

### Mode 4: Open Team Sheet (OTS) Swiss Flowcharting (`mode4-ots-flowchart`)
Submit an opponent's 6-Pokémon OTS (or reference a `Scouted_Teams.csv` ID) before a Bo3 set to get a 5-part dossier (12-Mon Speed Tier Hierarchy, Opposing Forced Leads, Game 1 Blueprint, Game 2/3 Adaptation Tree, Trap Tech Audit).
> **Example Prompt:**
> *"Mode 4: Generate my Bo3 OTS Swiss Flowchart piloting `T22` against `ST01` (Salamence-Mega / Sneasler / Indeedee-M / Milotic / Tyranitar-Mega / Excadrill)."*

### Mode 5: Sports Psychology & Leak Eradication (`mode5-sports-psych`)
Trigger a post-session review or audit your `data/Playstyle_Diagnostics.csv` and `data/Raw_Matches.csv` logs to diagnose recurring cognitive traps (`Tunnel_Vision`, `Greed`, `Autopilot`, `Tilt`, `Format_Divergence`).
> **Example Prompt:**
> *"Mode 5: Audit my last 10 matches in `Raw_Matches.csv` and `Playstyle_Diagnostics.csv` and tell me what cognitive leak is costing me the most rating."*

---

## 3. Running the Engine & Scouting Pipelines Directly (CLI)

All scripts in `engine/` and `scouts/` are zero-dependency Python 3 modules that either you or the agent can execute directly:

### A. 66-SP Deterministic Validator (`engine/sp_calculator.py`)
Validates `sum(SP) == 66`, enforces `0 <= SP <= 32` per stat, and computes floor-rounded Level 50 stats for any of the 335 species in `data/MC_Available_Pokemon.csv`:
```powershell
python engine/sp_calculator.py --species "Charizard-Mega-Y" --nature Modest --hp 18 --atk 0 --def 1 --spa 32 --spd 1 --spe 14
```

### B. Doubles Turn Micro-Simulator (`engine/turn_simulator.py`)
Runs a full doubles turn with Showdown's exact `0x1000` (`4096`) fixed-point modifiers (`3072/4096` spread penalty, `2732/4096` screens, `5461/4096` aura, weather, STAB, stage multipliers) and outputs the spectator replay log:
```powershell
# Run built-in Turn 6 Doubles test harness
python engine/turn_simulator.py

# Run custom board state & choices JSON files
python engine/turn_simulator.py --state path/to/state.json --choices path/to/choices.json --roll-mode fixed --fixed-roll 0.925
```

### C. Automated Team ID Lookup & Core Clusterer (`scouts/munchstats_scraper.py`)
Resolves a partial or full active Pokémon list against `data/Teams.csv` (`T01`–`T23`) and `data/Scouted_Teams.csv` (`ST01`–`ST06`):
```powershell
python scouts/munchstats_scraper.py --lookup Raichu Kommo-o Farigiraf Incineroar
```

### D. Direct CSV Telemetry Logger (`engine/telemetry.py`)
Writes personal matches (`Raw_Matches.csv` + `Playstyle_Diagnostics.csv`), scouted matches (`Scouted_Raw_Matches.csv`), and new damage calcs (`Damage_Calculations.csv`) directly to disk with auto-incremented IDs:
```powershell
python engine/telemetry.py --mode personal --payload path/to/match_telemetry.json
python engine/telemetry.py --mode scouted --payload path/to/scouted_match.json
python engine/telemetry.py --mode calc --payload path/to/damage_calc.json
```

### E. Cache-First Pokedex & Legality Resolver (`scouts/pokedex_resolver.py`)
Checks `data/MC_Available_Pokemon.csv` and `data/pokedex_cache.json` first, or outputs the exact 1-Attempt Bulbapedia/WikiDex precision query and `[DATA_UNVERIFIED]` failsafe tag:
```powershell
python scouts/pokedex_resolver.py --species "Mega Lucario Z"
python scouts/pokedex_resolver.py --species "Charizard" --move "Scorching Sands"
```
