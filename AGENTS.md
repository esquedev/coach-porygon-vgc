# Coach Porygon VGC — Agentic Architecture

This workspace houses an autonomous coaching, scouting, and deterministic turn-simulation system for the **Pokémon Champions (Regulation M-C)** competitive ecosystem.

## 1. Dual-Session Operating Modes

Every agentic session operates strictly under one of two standardized execution modes:

* **Trainer Usage Mode (`[SESSION: TRAINER]`)** — Governed by [`.agents/modes/trainer_mode.md`](.agents/modes/trainer_mode.md):
  * **Role:** Head Coach Porygon (competitive VGC coaching, Swiss flowcharting, 66-SP teambuilding, battle sparring, sports psychology, metagame intelligence).
  * **File Touch Whitelist:** Strictly restricted to user telemetry (`data/Raw_Matches.csv`, `data/Playstyle_Diagnostics.csv`, `data/Damage_Calculations.csv`, `data/Teams.csv`, `data/trainer_profile.json`, and `reports/`).
  * **Codebase Lock:** Strict read-only isolation on all source code (`engine/`, `tests/`, `evals/`, `assets/*.html`).
* **Developer Usage Mode (`[SESSION: DEV]`)** — Governed by [`.agents/modes/dev_mode.md`](.agents/modes/dev_mode.md):
  * **Role:** Senior AI Systems & Software Engineer.
  * **Superset Directives:** Inherits all Trainer domain mechanics plus engineering rules: SOLID principles, scratch isolation, 5-phase CI/CD verification (`run_tests.cmd`), and Generative AI prompt stress evaluation.

---

## 2. Architecture Overview

1. **Workspace Rules (`.agents/rules/`)**:
   - [`engine_rules.md`](.agents/rules/engine_rules.md): Regulation M-C mechanics, 66-SP stat rules, instantaneous Mega Evolution speed scaling, Victory Point (VP) heuristic track, Trainer Profile POV binding (`trainer_profile.json`), strict item legality lock (`Regulation_MC_Items.csv`), typing/STAB grounding, zero-guessing team verification, and the 4-Step Pre-Turn Validation & Multi-Turn Minimax Protocol.
   - [`champions_mechanics_compendium.md`](.agents/rules/champions_mechanics_compendium.md): Unified competitive rulebook detailing Level 50 SP conversion formulas, simultaneous Mega Evolution priorities, redirection immunity, and psychic terrain matrix.
   - [`mistake_taxonomy.md`](.agents/rules/mistake_taxonomy.md): Standardized playstyle diagnostic error codes (`POS-01`–`POS-03`, `TGT-01`–`TGT-03`, `MEC-01`–`MEC-02`, `SPD-01`–`SPD-02`) and cognitive trap drivers.
   - [`system_guardrails.md`](.agents/rules/system_guardrails.md): Technical system guardrails, zero-hallucination rules, OWASP LLM01 untrusted input isolation, format species blacklist, canonical Trainer terminology, centralized agent audits in `reports/agent_audits/`, and exclusive artifact lock (`assets/command_center.html` only).
   - [`software_dev_guidelines.md`](.agents/rules/software_dev_guidelines.md): Software development and repository hygiene standards, scratch isolation protocol, automated pre-flight CI/CD verification, dual-tier test taxonomy (`testUT`/`testAT`) with 1:1 class-to-test parity, cross-platform runner parity, PEP 257/484 quality mandates, and format grounding.

2. **Specialized Agent Skills (`.agents/skills/`)**:
   - **General Coaching & Theorycrafting**: Default conversational Head Coach mode.
   - [`replay-audit`](.agents/skills/replay-audit/SKILL.md): Asynchronous Replay Breakdown, multi-turn Minimax turning point simulation via `engine/turn_simulator.py`, and direct CSV telemetry logging via `engine/telemetry.py`.
   - [`roster-budget`](.agents/skills/roster-budget/SKILL.md): 66-SP Deterministic Roster Engineering validated by `engine/sp_calculator.py` and `engine/validate_roster.py`.
   - [`flashcards`](.agents/skills/flashcards/SKILL.md): 45-Second Interactive Board Sparring & Reflex Flashcards with 4 categorized options and turn-by-turn simulation via `engine/turn_simulator.py`.
   - [`ots-flowchart`](.agents/skills/ots-flowchart/SKILL.md): Open Team Sheet (OTS) Bo3 Swiss Flowcharting backed by `data/Scouted_Teams.csv`.
   - [`sports-psych`](.agents/skills/sports-psych/SKILL.md): Cognitive Leak Eradication & Sports Psychology debriefs.
   - [`munchstats-meta`](.agents/skills/munchstats-meta/SKILL.md): MunchStats Tournament Ingestion, Metagame Usage Analytics, Day 1/2 Conversion Rates & Tournament Analytics.
   - [`report-generator`](.agents/skills/report-generator/SKILL.md): Esports Infographics, Multi-Page Swiss Dossiers & Print-Ready PDF Report Generation.
   - [`dev-ai-stress-evaluator`](.agents/skills/dev-ai-stress-evaluator/SKILL.md): Generative AI Adversarial Prompt Stress Evaluator & Health Benchmark via `evals/evaluate_release_health.py`.

3. **Deterministic Engine (`engine/`)**:
   - [`turn_simulator.py`](engine/turn_simulator.py): Dependency-free Showdown-accurate doubles turn micro-simulator (official damage modifiers, 66-SP stat computation, action order sorting, and spectator replay output).
   - [`sp_calculator.py`](engine/sp_calculator.py): Verifies exact `66 SP` allocation (`<= 32 SP` per stat), computes Level 50 stats with sequential floor rounding, and emits the mandatory verification string.
   - [`validate_roster.py`](engine/validate_roster.py): Pre-flight format validator enforcing item legality (`Regulation_MC_Items.csv`), Item Clause, verified typings (`MC_Available_Pokemon.csv`), and strict STAB vs. Coverage classification.
   - [`pdf_exporter.py`](engine/pdf_exporter.py): Headless Chrome/Edge PDF compilation engine for AI-authored esports reports and dossiers.
   - [`register_team.py`](engine/register_team.py): Ingests raw Showdown team export pastes, validates format legality and 66-SP allocations per member, auto-assigns next sequential Team ID (`Txx`), writes to `data/Teams.csv`, and updates `data/trainer_profile.json`.
   - [`telemetry.py`](engine/telemetry.py): Logs personal matches directly to `data/Raw_Matches.csv` and `data/Playstyle_Diagnostics.csv`; logs scouted matches to `data/Scouted_Raw_Matches.csv`; and appends damage calcs directly to `data/Damage_Calculations.csv`.
   - [`ui_server.py`](engine/ui_server.py): Sandboxed Flask web server and dynamic sprite resolver delivering the bilingual Command Center.

4. **Data & Telemetry Repository (`data/` & `reports/`)**:
   - **Trainer Profile (`data/trainer_profile.json`)**: Configures user trainer handles (`known_alts`, e.g. `aws_secret`, `brightvgc`) and `last_team_id` for instantaneous replay attribution without ambiguous scraping.
   - **Centralized Agent Audits (`reports/agent_audits/`)**: Persistent storage for all automated release health audits, stress benchmarks, and evaluator telemetry (`evals/evaluate_release_health.py`).
