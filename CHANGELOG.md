# Changelog — BeRightVGC / Coach Porygon VGC

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.0] - 2026-11-01

### Added
- **5-Family Report Taxonomy:** Expanded the `report-generator` skill to support 5 canonical publication archetypes: Tactical Replay Audits, Metagame & Swiss Intelligence, Telemetry & Playstyle Diagnostics, Coach QA & Decision Audits, and Swiss Opponent Scouting / Caster Aid.
- **4-Tier Insight Hierarchy:** Formalized insight generation depth from L1 Descriptive, L2 Diagnostic (Mistake Taxonomy), L3 Game-Theoretic (Nash $v^*$, $\Delta V^*$, 16 damage rolls), to L4 Prescriptive & Actionable ($T_N \to T_{N+1}$ line planning and tilt resets).
- **Multi-Persona Visual Presets:** Added design themes across `engine/ui_generator.py` and `engine/pdf_exporter.py` for Midnight Cyber (Competitor HUD), Deep Diagnostic (Coach/Analyst), Executive Print A4 (Broadcaster/Caster), and Executive Sponsor Brief.
- **Repository-Wide Anti-Hallucination Scanner:** Created `evals/scan_repo_hallucinations.py` pre-hook leveraging `validate_roster.py`'s canonical Regulation M-C blacklist to continuously enforce zero format leaks across codebase, fixtures, and documentation.
- **HTML Artifact Purger Pre-Hook:** Created `evals/purge_html_artifacts.py` to prevent transient HTML report accumulation and keep Git commits clean, while preserving core assets.
- **CLI Customization Flags:** Added `--theme` and `--report-type` flags to `main.py` for headless report rendering and PDF compilation.

### Changed
- **Unified Brand Architecture:** Condensed branding across the entire repository under **esquedev** (Engineering Studio), **BeRightVGC** (Competitive Esports Platform, telemetry: `brightvgc`), and **Coach Porygon VGC** (Deterministic Runtime Engine).
- **Overhauled Documentation:** Synchronized `README.md`, `CONTRIBUTING.md`, and `LEGAL.md` with accurate test metrics (247 passing tests, 916 SHA-256 PNG assets, 35 adversarial stress cases).
- **Refined Test Fixtures:** Purged legacy format species from test fixtures (`Heatran`, `Flutter Mane`, `Ursaluna`) and substituted legal Regulation M-C alternatives.

---

## [1.1.0] - 2026-10-31

### Added
- **5 Specialized Agentic Roles:** Implemented role partitioning in `AGENTS.md` and `.agents/modes/` (Head Coach, Metagame Analyst, Roster Engineer, Esports Reporter, Systems & QA Engineer) with Minimum Viable Context (MVC) token protection.
- **GPU-Accelerated Nash Payoff Matrices:** Integrated PyTorch CUDA and HiGHS linear programming solvers in `engine/tactics/` and `engine/gpu/` for simultaneous $5 \times 5$ action evaluations and counterfactual equity loss calculation ($\Delta V^*$).
- **5-Phase Local CI/CD Pipeline:** Created `run_tests.cmd` and `run_tests.sh` with Phase 0 (Workspace Sanitization), Phase 1 (Schema Init), Phase 2 (Linting), Phase 3 (AI Health Audit), Phase 4 (Asset Curation), and Phase 5 (Full Test Suite).
- **Esports Broadcaster Caster Aid:** Implemented `engine/caster_dossier.py` and `.agents/skills/caster_aid/` to synthesize live broadcast cheat sheets, matchup matrices, and speed ladders.
- **Generative AI Release Health Gate:** Created `evals/evaluate_release_health.py` (Mode 7) with 35 adversarial stress tests verifying zero prompt injection and zero format hallucination before push.

---

## [1.0.0] - 2026-10-25

### Added
- **Deterministic Level 50 Turn Simulator:** Implemented official VGC integer damage formulas, terrain/weather interactions, and dynamic speed recalculations in `engine/turn_simulator.py`.
- **Bijective 66-Stat-Point Calculator:** Implemented exact mathematical EV $\leftrightarrow$ SP bidirectional conversion at Level 50 with sequential floor rounding (`engine/sp_calculator.py`).
- **Cyberpunk Command Center HUD:** Built standalone single-page interactive dashboard (`assets/command_center.html`) featuring bilingual support (EN/ES), tilt barometers, and 45-second interactive sparring puzzles.
- **Format Legality Engine:** Added `engine/validate_roster.py` enforcing item clause and species validation against `data/Regulation_MC_Items.csv` and `data/MC_Available_Pokemon.csv`.
- **Match Telemetry Pipeline:** Added thread-safe CSV persistence in `engine/telemetry.py` for match records, damage calculations, and playstyle mistake audits.
