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
   - **New Feature Test Coverage:** Whenever new code, API endpoints, or engine features are developed, corresponding **success verification tests** (happy paths) and **error-raising tests** (validation, boundary limits, and expected exceptions) MUST be coded and added to the appropriate directory inside `tests/` (e.g., `tests/backend/`, `tests/frontend/`, `tests/security/`, or `tests/negative/`).
   - **During Iterative Development (Token & Time Efficiency):** Do NOT run the full 5-phase test runner on every single micro-edit. Instead, run targeted unit tests for the specific module being edited (e.g. `python -m unittest tests/frontend/test_ui_server.py`) or lightweight syntax compilation.
   - **Pre-Push / Release Gate:** Execute the full 5-phase local test runner (`run_tests.cmd`) **only before pushing commits to remote, opening pull requests, or cutting a release**.
   - **Remote CI Safety Net:** GitHub Actions (`.github/workflows/ci.yml`) acts as the final automated gatekeeper, catching regressions on push without burning local context tokens during intermediate development turns.
4. **Security & Sandbox Hardening:**
   - Enforce loopback default `127.0.0.1:8000` (SEC-01).
   - Enforce strict CORS filtering with CRLF injection sanitization (SEC-02).
   - Preserve 403 Forbidden blocking for sensitive paths (`.git`, `.github`, `.agents`, `trainer_profile.json`) (SEC-03).
   - Enforce 5 MB request body limit returning 413 Payload Too Large (SEC-06).
   - Ensure atomic thread-safe CSV operations (SEC-07).
5. **AI Health Audit Consumption & One-Time Pre-Push Enforcement:**
   - The developer or agent executes the [`dev-ai-stress-evaluator`](../skills/dev-ai-stress-evaluator/SKILL.md) skill:
     ```cmd
     .\python.cmd evals/stress_ai_evaluator.py
     ```
   - This runs the 28 adversarial stress cases and writes a fresh audit report to `reports/agent_audits/ai_health_stress_report.json` with `"audit_consumed": false`.
   - The release health evaluator (`evals/evaluate_release_health.py`, executed in Phase 3 of `run_tests.cmd`) checks this report. It verifies that the verdict is `[PASS - PRODUCTION AIRTIGHT]` and that `"audit_consumed"` is `false`.
   - **Consumption Lock:** At the end of execution, `evals/evaluate_release_health.py` **modifies the original `ai_health_stress_report.json` file on disk, marking `"audit_consumed": true`**. Once consumed, the report cannot be validated again, preventing reuse of stale evaluations and forcing developers to re-execute the skill before any subsequent release or push.
   - **Git Pre-Push Hook:** Developers can wire `.git/hooks/pre-push` to reject `git push` if `reports/agent_audits/ai_health_stress_report.json` is missing, unconsumed, or failing.

## 3. Active Developer Skills
Developers possess access to the **complete superset of skills** (both Trainer coaching skills and Developer engineering skills):

### Trainer Domain Skills:
- [`replay-audit`](../skills/replay-audit/SKILL.md) (Asynchronous Replay Breakdown, VP Turning Point audit, telemetry logging).
- [`roster-budget`](../skills/roster-budget/SKILL.md) (66-SP Deterministic Roster Engineering).
- [`crucible-spar`](../skills/crucible-spar/SKILL.md) (45-Second Interactive Board Sparring & Reflex Flashcards).
- [`ots-flowchart`](../skills/ots-flowchart/SKILL.md) (Open Team Sheet Bo3 Swiss Flowcharting).
- [`sports-psych`](../skills/sports-psych/SKILL.md) (Cognitive Leak Eradication & Sports Psychology).

### Developer & Engineering Skills:
- [`munchstats-meta`](../skills/munchstats-meta/SKILL.md) (Tournament Ingestion & Metagame Analytics Pipeline).
- [`release-health-eval`](../skills/release-health-eval/SKILL.md) (Deterministic Static Health Auditor).
- [`dev-ai-stress-evaluator`](../skills/dev-ai-stress-evaluator/SKILL.md) (Generative AI Adversarial Prompt Stress Evaluator & Health Benchmark).
