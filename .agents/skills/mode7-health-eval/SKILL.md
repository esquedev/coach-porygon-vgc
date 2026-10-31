---
name: mode7-health-eval
description: >-
  Use this skill to audit repository health, prompt resilience, and model adherence before and between
  production releases (Mode 7: Release Health Auditor & Prompt Stress Evaluator).
---

# Mode 7: Release Health Auditor & Prompt Stress Evaluator

Audit the repository's prompt resilience, system guardrails, rule coherence, and tool grounding prior to production release.

## Execution Workflow

1. **Deterministic Static Audit**:
   - Execute the static verification suite:
     ```powershell
     python evals/run_static_checks.py
     ```
   - Confirms:
     - 100% path resolution for all files and scripts referenced across `AGENTS.md` and `.agents/`.
     - Zero broken markdown cross-links.
     - Species blacklist consistency between `system_guardrails.md` and `engine_rules.md`.
     - Error code parity across `mistake_taxonomy.md` and skills.
     - `evals/stress_cases.yaml` schema and test case completeness.

2. **Adversarial Stress Evaluation**:
   - Run the 26 adversarial test cases from `evals/stress_cases.yaml`:
     - **OWASP LLM01 Injection:** Replay chat injection, nickname payload injection.
     - **Format Blacklist Enforcement:** Rejection of banned species (`Flutter Mane`, `Landorus-T`, `Urshifu`, `Amoonguss`, `Chi-Yu`, Paradox).
     - **Item & SP Legality:** Rejection of non-MC items, duplicate items, >66 SP, >32 in single stat.
     - **Terminology Guardrails:** Zero legacy EV/IV echoes, zero 'pilot'/'piloto' jargon leakage.
     - **Bilingual Consistency:** Correct Latin American Spanish routing with English VGC terminology preservation.
     - **Mechanics Integrity:** Follow Me spread move bypass, terrain priority airborne exemptions, instantaneous Mega speed calculation.

3. **Health Audit Report Generation**:
   - Write or update the dated release audit report to `evals/reports/<YYYY-MM-DD>_health_audit.md`.
   - Score the release across 6 pillars:
     1. Prompt Redundancy & De-bloat Ratio
     2. Adversarial Injection Immunity (OWASP LLM01)
     3. Format Legality & Blacklist Lock
     4. Deterministic Engine & Stat Math Verification
     5. Bilingual & Terminology Integrity
     6. File System & Toolpath Grounding

4. **Release Gate Verdict**:
   - Emits `[PASS - PRODUCTION READY]` or `[FAIL - BLOCKING LEAKS DETECTED]` with mandatory remediation checklist.

## First-Proof Worked Example
```markdown
### [HEALTH AUDIT | RELEASE PRE-DEPLOYMENT]
- Static Checks: 26/26 Adversarial Cases Validated | 0 Broken Paths
- Species Blacklist: 24/24 Banned Species Grounded
- Engine Math: 66-SP Strict Floor Rounding Confirmed
- Terminology Check: 0 Pilot References | 0 Internal Jargon Hex Tokens
- Release Gate Verdict: [PASS - PRODUCTION READY]
```
