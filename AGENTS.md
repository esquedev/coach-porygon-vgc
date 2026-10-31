# Coach Porygon VGC — Agentic Architecture

This workspace houses an autonomous coaching, scouting, and deterministic turn-simulation system for the **Pokémon Champions (Regulation M-C)** competitive ecosystem.

## Architecture Overview

1. **Workspace Rules (`.agents/rules/`)**:
   - [`engine_rules.md`](.agents/rules/engine_rules.md): Regulation M-C mechanics, 66-SP stat rules, instantaneous Mega Evolution speed scaling, Victory Point (VP) heuristic track, Trainer Profile POV binding (`trainer_profile.json`), strict item legality lock (`Regulation_MC_Items.csv`), typing/STAB grounding, zero-guessing team verification, and the 4-Step Pre-Turn Validation Checklist.
   - [`mistake_taxonomy.md`](.agents/rules/mistake_taxonomy.md): Standardized playstyle diagnostic error codes (`POS-01`–`POS-03`, `TGT-01`–`TGT-03`, `MEC-01`–`MEC-02`, `SPD-01`–`SPD-02`) and cognitive trap drivers.
   - [`system_guardrails.md`](.agents/rules/system_guardrails.md): Technical system guardrails, zero-hallucination rules, OWASP LLM01 untrusted input isolation, format species blacklist, and canonical Trainer terminology.

2. **Operational Mode Skills (`.agents/skills/`)**:
   - **Mode 0 (General Coaching & Theorycrafting)**: Default conversational Head Coach mode.
   - [`mode1-replay-audit`](.agents/skills/mode1-replay-audit/SKILL.md): Asynchronous Replay Breakdown, VP Turning Point audit via `engine/turn_simulator.py`, and direct CSV telemetry logging via `engine/telemetry.py`.
   - [`mode2-roster-budget`](.agents/skills/mode2-roster-budget/SKILL.md): 66-SP Deterministic Roster Engineering validated by `engine/sp_calculator.py` and `engine/validate_roster.py`.
   - [`mode3-crucible-spar`](.agents/skills/mode3-crucible-spar/SKILL.md): 45-Second Interactive Board Sparring & Reflex Flashcards refereed by `engine/turn_simulator.py`.
   - [`mode4-ots-flowchart`](.agents/skills/mode4-ots-flowchart/SKILL.md): Open Team Sheet (OTS) Bo3 Swiss Flowcharting backed by `data/Scouted_Teams.csv`.
   - [`mode5-sports-psych`](.agents/skills/mode5-sports-psych/SKILL.md): Cognitive Leak Eradication & Sports Psychology debriefs.
   - [`mode6-munchstats-meta`](.agents/skills/mode6-munchstats-meta/SKILL.md): MunchStats Tournament Ingestion, Metagame Usage Analytics & Session Dumper.
   - [`mode7-health-eval`](.agents/skills/mode7-health-eval/SKILL.md): Release Health Auditor & Prompt Stress Evaluator running deterministic static checks via `evals/run_static_checks.py` and 26 adversarial evals (`evals/stress_cases.yaml`).

3. **Deterministic Engine (`engine/`)**:
   - [`turn_simulator.py`](engine/turn_simulator.py): Dependency-free Showdown-accurate doubles turn micro-simulator (official damage modifiers, 66-SP stat computation, action order sorting, and spectator replay output).
   - [`sp_calculator.py`](engine/sp_calculator.py): Verifies exact `66 SP` allocation (`<= 32 SP` per stat), computes Level 50 stats with sequential floor rounding, and emits the mandatory verification string.
   - [`validate_roster.py`](engine/validate_roster.py): Pre-flight format validator enforcing item legality (`Regulation_MC_Items.csv`), Item Clause, verified typings (`MC_Available_Pokemon.csv`), and strict STAB vs. Coverage classification.
   - [`register_team.py`](engine/register_team.py): Ingests raw Showdown team export pastes, validates format legality and 66-SP allocations per member, auto-assigns next sequential Team ID (`Txx`), writes to `data/Teams.csv`, and updates `data/trainer_profile.json`.
   - [`telemetry.py`](engine/telemetry.py): Logs personal matches directly to `data/Raw_Matches.csv` and `data/Playstyle_Diagnostics.csv`; logs scouted matches to `data/Scouted_Raw_Matches.csv`; and appends damage calcs directly to `data/Damage_Calculations.csv`.

4. **Scouting & Knowledge Pipeline (`scouts/` & `data/`)**:
   - [`munchstats_scraper.py`](scouts/munchstats_scraper.py): Parses tournament OTS team lists, clusters shared 6-Pokémon cores, and updates `data/Scouted_Teams.csv`.
   - [`pokedex_resolver.py`](scouts/pokedex_resolver.py): Cache-first species/move/item verifier (`data/Regulation_MC_Items.csv`, `data/MC_Available_Pokemon.csv`, `data/pokedex_cache.json`) enforcing the 1-Attempt Precision Query Protocol and `[DATA_UNVERIFIED]` failsafe.
   - **Trainer Profile (`data/trainer_profile.json`)**: Configures user trainer handles (`known_alts`, e.g. `aws_secret`, `brightvgc`) and `last_team_id` for instantaneous replay attribution without ambiguous scraping.
