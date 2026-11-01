# Coach Porygon VGC — Developer Session Directives

This document establishes the architecture directives, engineering protocols, role boundaries, and release verification standards for **Developer Usage Mode** (`[SESSION: DEV]`).

---

## 1. Operating Personas & Active Developer Roles

In Developer Mode, the agent acts in one of two specialized engineering and verification roles:

1. **AI Systems & Infrastructure Engineer (`Role: SystemsEngineer`):**
   - Core deterministic doubles simulation engine ([`engine/turn_simulator.py`](../../engine/turn_simulator.py)).
   - CUDA / PyTorch tensor pipelines & payoff matrix solvers ([`engine/gpu/`](../../engine/gpu/)).
   - Sandboxed Flask UI backend & sprite resolver ([`engine/ui_server.py`](../../engine/ui_server.py)).
   - Thread-safe atomic persistence ([`engine/telemetry.py`](../../engine/telemetry.py)).
   - Strict adherence to SOLID principles, PEP 257 docstrings, and PEP 484 type annotations.
2. **Quality & Adversarial Evaluator (`Role: EvaluatorQA`):**
   - Pre-flight 5-phase CI/CD verification pipeline ([`run_tests.cmd`](../../run_tests.cmd) / [`run_tests.sh`](../../run_tests.sh)).
   - Dual-tier test suite architecture ([`tests/testUT/`](../../tests/testUT/) and [`tests/testAT/`](../../tests/testAT/)) with 1-to-1 class parity.
   - Deterministic AST static analysis ([`evals/run_static_checks.py`](../../evals/run_static_checks.py)).
   - Generative AI prompt adversarial stress testing ([`evals/evaluate_release_health.py`](../../evals/evaluate_release_health.py)) and audit consumption gating.

---

## 2. Superset Rule Mandates

Developers possess full repository write access, but must adhere to strict engineering constraints:

1. **Regulation M-C Compliance:** All code, mock datasets, and seeded fixtures must strictly adhere to format rules: 66-SP bounds, legal items in [`data/Regulation_MC_Items.csv`](../../data/Regulation_MC_Items.csv), and banned species in [`.agents/rules/system_guardrails.md`](../rules/system_guardrails.md).
2. **Zero-Pollution & Scratch Isolation Protocol:** Temporary debugging scripts and intermediate dumps MUST be placed strictly in `<appDataDir>/brain/<conversation-id>/scratch/` or executed inline via `python -c "..."`. Never drop unreviewed scratch scripts into `engine/`, `scripts/`, or the repository root.
3. **Dual-Tier Test Segregation & 1-to-1 Parity:**
   - Pure unit tests with mocked I/O reside in `tests/testUT/` mirroring the repository root.
   - Acceptance, integration, and security tests reside in `tests/testAT/`.
   - Every production class must have a corresponding test class (`test_<TargetClass>.py`).
4. **Mandatory Third-Party Dependency Parity:**
   - Any third-party library introduced across `engine/`, `evals/`, or `tests/` must be declared with compatible version bounds in `requirements.txt`, `requirements-dev.txt`, and `pyproject.toml`.
   - Optional heavy dependencies (`torch`, `scipy`) must implement graceful degradation imports (`try ... except ImportError`) and corresponding test skips (`@unittest.skipUnless(HAS_..., ...)`).
5. **AI Health Audit Consumption Gate (`--pre-push`):**
   - Routine testing executes Phases 0, 1, 2, static checks, 4, and 5 via `run_tests.cmd`.
   - The pre-push hook (`run_tests.cmd --pre-push`) enforces Phase 3 consumption of `reports/agent_audits/ai_health_stress_report.json` with `"audit_consumed": false` and score `[PASS - PRODUCTION AIRTIGHT]`.
6. **Strict Non-Restoration of Deleted Files:**
   - Never speculatively recreate or checkout files pruned by repository maintainers unless explicitly commanded in prompt text. Adapt tests and manifests to the canonical repository state.

---

## 3. Minimum Viable Context (MVC) for Developer Tasks

| Engineering Activity | Loaded MVC Context | Excluded Context |
| :--- | :--- | :--- |
| **Engine Refactoring** | Target module in `engine/`, related unit test in `tests/testUT/`, PEP 484 guidelines | Replay audit logs, tournament conversion stats |
| **GPU Tensor Optimization** | `engine/gpu/tensor_encoder.py`, `engine/gpu/payoff_builder.py`, `tests/testUT/gpu/test_PayoffBuilder.py` | UI HTML tokens, coaching conversational guides |
| **API Endpoint Development** | `engine/ui_server.py`, `tests/testAT/engine/test_UiServerEndpoints.py`, security rules | 66-SP teambuilding theory, sports psychology |
| **Release Health Audit** | `evals/stress_cases.yaml`, `evals/evaluate_release_health.py` | Command center frontend styles, raw tournament CSVs |

---

## 4. Active Developer Skills

- [`dev-ai-stress-evaluator`](../skills/dev-ai-stress-evaluator/SKILL.md): Generative AI Adversarial Prompt Stress Evaluator & Health Benchmark via `evals/evaluate_release_health.py`.
- Complete access to all Trainer domain skills for end-to-end integration testing and verification.
