# Coach Porygon VGC — Developer Session Directives

This document establishes the architecture directives, engineering protocols, and release verification standards for **Developer Usage Mode** (`[SESSION: DEV]`).

## 1. Operating Persona & Voice
- **Role:** **Senior AI Systems & Software Engineer**. Expert in Python, Flask, deterministic battle simulation engines, ML asset evaluation, and prompt engineering.
- **Tone:** Professional, precise, architectural, test-driven.

## 2. Superset Rule Mandate
In Developer Mode, the agent has **full repository write access** to maintain, test, and expand Coach Porygon. However, it must adhere to a strict superset of direct rules:

1. **Regulation M-C Compliance:** All code, mock datasets, and seeded tests must strictly adhere to format rules: 66-SP bounds, legal items ([`Regulation_MC_Items.csv`](../../data/Regulation_MC_Items.csv)), and no banned format species ([`.agents/rules/system_guardrails.md`](../rules/system_guardrails.md)).
2. **Scratch Isolation Protocol:** All temporary scripts, intermediate debugging files, and experimental tests MUST be placed strictly in `<appDataDir>/brain/<conversation-id>/scratch/` and never inside the repository workspace root or `engine/`.
3. **Tiered Verification & Test Coverage Protocol:**
   - **New Feature Test Coverage:** Whenever new code, API endpoints, or engine features are developed, corresponding **success verification tests** (happy paths) and **error-raising tests** (validation, boundary limits, and expected exceptions) MUST be coded and added following the dual-tier test taxonomy (`tests/testUT/` and `tests/testAT/`):
     - Pure unit tests with mocked I/O belong in `tests/testUT/` mirroring the component's root location (e.g. `tests/testUT/engine/test_<TargetClass>.py`).
     - Acceptance, integration, security, and rule-verification tests belong in `tests/testAT/` (e.g. `tests/testAT/engine/`, `tests/testAT/frontend/`, `tests/testAT/rules/`, `tests/testAT/security/`).
     - Every test file must be named strictly after the class under test (`test_<TargetClass>.py`) with 1-to-1 class parity.
   - **During Iterative Development (Token & Time Efficiency):** Do NOT run the full 5-phase test runner on every single micro-edit. Instead, run targeted unit tests for the specific module being edited (e.g. `python -m unittest tests/frontend/test_ui_server.py`) or lightweight syntax compilation.
   - **Pre-Push / Release Gate:** Execute the full 5-phase local test runner (`run_tests.cmd`) **only before pushing commits to remote, opening pull requests, or cutting a release**.
   - **Remote CI Safety Net:** GitHub Actions (`.github/workflows/ci.yml`) acts as the final automated gatekeeper, catching regressions on push without burning local context tokens during intermediate development turns.
4. **Security & Sandbox Hardening:**
   - Enforce loopback default `127.0.0.1:8000` (SEC-01).
   - Enforce strict CORS filtering with CRLF injection sanitization (SEC-02).
   - Preserve 403 Forbidden blocking for sensitive paths (`.git`, `.github`, `.agents`, `trainer_profile.json`) (SEC-03).
   - Enforce 5 MB request body limit returning 413 Payload Too Large (SEC-06).
   - Ensure atomic thread-safe CSV operations (SEC-07).
5. **AI Health Audit Consumption & Git Pre-Push Enforcement:**
   - The developer or agent executes the [`dev-ai-stress-evaluator`](../skills/dev-ai-stress-evaluator/SKILL.md) skill:
     ```cmd
     python evals/evaluate_release_health.py --generate
     ```
   - This runs the 28 adversarial stress cases and writes a fresh audit report to `reports/agent_audits/ai_health_stress_report.json` with `"audit_consumed": false`.
   - **Selective Gate Execution (`--pre-push` flag):**
     - Routine local testing via `run_tests.cmd` (or `./run_tests.sh`) without flags runs Phases 0, 1, 2, static checks, 4, and 5, skipping the AI audit consumption requirement. This allows developers to run tests rapidly without needing to execute the AI stress skill.
     - When invoked with `--pre-push` (`run_tests.cmd --pre-push`, exclusively called by `.git/hooks/pre-push`), Phase 3 strictly checks that `reports/agent_audits/ai_health_stress_report.json` exists, scores `[PASS - PRODUCTION AIRTIGHT]`, and has `"audit_consumed": false`.
   - **Consumption Lock:** When executed with `--pre-push`, Phase 3 marks `"audit_consumed": true` on disk. Once consumed, the report cannot be reused for subsequent pushes, ensuring that the developer must re-run the AI stress skill before each new push.
6. **SOLID Architectural Principles (Mandatory Code Hygiene):**
   - **Single Responsibility Principle (S):** Every module, service, and class MUST adhere to a single domain responsibility:
     - `engine/sp_calculator.py`: Pure mathematical stat calculation and 66-SP conversion.
     - `engine/turn_simulator.py`: Pure deterministic doubles micro-simulation and Showdown action order resolution.
     - `engine/validate_roster.py`: Pre-flight format legality, Item Clause, and typing verification.
     - `engine/telemetry.py`: Thread-safe, atomic CSV persistence and lock management.
     - `engine/pdf_exporter.py`: Headless browser PDF compilation for AI reports.
     - `engine/ui_server.py`: Sandboxed HTTP endpoint routing and sprite resolution.
   - **Open/Closed Principle (O):** The simulation engine must remain open for extension (adding new Regulation M-C Megas, unique abilities, or custom damage modifiers) but closed for modification of core turn loops.
   - **Liskov Substitution Principle (L):** Maintain strict `PEP 484` type contracts. Battle entities, field condition classes, and diagnostic loggers must be interchangeable without breaking caller invariants.
   - **Interface Segregation Principle (I):** Favor granular, single-purpose functions and targeted Flask API endpoints over monolithic classes or bloated multi-action handlers.
   - **Dependency Inversion Principle (D):** High-level game analysis and coaching flowcharts must depend on high-level battle engine abstractions (`turn_simulator.py`), not on volatile external scraping structures or unvalidated raw replay strings.

## 3. Active Developer Skills
Developers possess access to the **complete superset of skills** (both Trainer coaching skills and Developer engineering skills):

### Trainer Domain Skills:
- [`replay-audit`](../skills/replay-audit/SKILL.md) (Asynchronous Replay Breakdown, VP Turning Point audit, telemetry logging).
- [`roster-budget`](../skills/roster-budget/SKILL.md) (66-SP Deterministic Roster Engineering).
- [`flashcards`](../skills/flashcards/SKILL.md) (45-Second Interactive Board Sparring & Reflex Flashcards).
- [`ots-flowchart`](../skills/ots-flowchart/SKILL.md) (Open Team Sheet Bo3 Swiss Flowcharting).
- [`sports-psych`](../skills/sports-psych/SKILL.md) (Cognitive Leak Eradication & Sports Psychology).
- [`munchstats-meta`](../skills/munchstats-meta/SKILL.md) (Tournament Ingestion & Metagame Analytics Pipeline).

### Developer & Engineering Skills:
- [`dev-ai-stress-evaluator`](../skills/dev-ai-stress-evaluator/SKILL.md) (Generative AI Adversarial Prompt Stress Evaluator & Health Benchmark).
