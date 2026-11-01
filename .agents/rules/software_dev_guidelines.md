# Software Development Guidelines & Engineering Guardrails

This document establishes the mandatory software engineering standards, repository hygiene protocols, and verification workflows for all automated agents and human contributors working on the **Coach Porygon VGC** codebase.

---

## 1. Zero-Pollution & Scratch Isolation Protocol

* **Prohibition of Root and Scripts Pollution:** Never create temporary, scratch, or experimental scripts (`test_*.py`, `temp_*.py`, `patch_*.py`, `scratch_*.py`, etc.) in the workspace root or inside `scripts/`.
* **Designated Ephemeral Directory (`scratch/`):**
  * All intermediate debugging scripts, exploratory dumps, and one-off inspection utilities MUST be placed inside `scratch/` or executed inline using `python -c "..."`.
  * The `scratch/` directory is shielded by `.gitignore` (ignoring all contents except `scratch/.gitkeep`).
* **Role of `scripts/`:**
  * `scripts/` is strictly reserved for official, documented, version-controlled developer utilities and deployment tooling. Never drop unreviewed or temporary scripts into `scripts/`.

---

## 2. Deterministic Pre-Flight CI/CD Verification

* **Unified 5-Phase Pipeline:**
  * Before completing any software development task, feature implementation, or bugfix, run the standard CI runner:
    * Windows: `cmd.exe /c run_tests.cmd`
    * POSIX: `./run_tests.sh`
* **Automated Pre-Flight Sanitization:**
  * The CI runner (`run_tests.cmd` / `run_tests.sh`) **already executes Phase 0 workspace sanitization** via `engine/clean_workspace.py` at the very beginning of each run. It automatically wipes `scratch/`, bytecode caches (`__pycache__`, `*.pyc`), and build artifacts.
  * Running `engine/clean_workspace.py` as a separate, manual step before running `run_tests.cmd` is redundant and unnecessary. Standalone execution of `engine/clean_workspace.py` is reserved exclusively for quick manual cleanup when running tests is not required.
* **100% Green Mandate:**
  * All 5 phases must pass without failure:
    1. `[PHASE 0/5]` Workspace Sanitization (`engine/clean_workspace.py`)
    2. `[PHASE 1/5]` Schema & Template Initialization (`data/*.example.csv`)
    3. `[PHASE 2/5]` Linting and Syntax Compilation (`flake8` / `pycodestyle` with 0 violations)
    4. `[PHASE 3/5]` Static Guardrails & Stress Evaluation (`evals/evaluate_release_health.py`)
    5. `[PHASE 4/5]` Vector/Raster Asset Audit & Manifest Generation (`engine/verify_png_inventory.py`)
    6. `[PHASE 5/5]` Acceptance, Security, and Regression Test Suite (`tests/run_all_tests.py`)

---

## 3. Cross-Platform Parity & Launcher Integrity

* **Windows & POSIX Synchronization:**
  * Any modification to runner logic, arguments, or environment variables in `run_tests.cmd` must be faithfully mirrored in `run_tests.sh` and vice versa.
* **Dynamic Python Runtime Launching:**
  * Use the workspace virtual environment interpreter (`.venv\Scripts\python.exe` on Windows, `$PY` on POSIX) or active Python environment rather than assuming a system-wide python path.
  * Local runners (`run_tests.cmd` and `run_tests.sh`) dynamically discover `.venv` first before falling back to system interpreters.

---

## 4. Python Code Quality & Documentation Standards

* **PEP 257 Docstrings:**
  * Every new or modified Python module, class, and public function must have descriptive docstrings explaining its purpose, parameters, return types, and exceptions.
* **PEP 484 Type Annotations:**
  * Public interfaces, mathematical calculations, and pipeline functions must declare explicit type hints.
* **Flake8 Compliance:**
  * The codebase enforces clean formatting with zero flake8 warnings or errors across `engine/`, `evals/`, `scouts/`, and `tests/`.

---

## 5. Domain Grounding & Terminology Lock

* **Regulation M-C Compliance:**
  * All algorithms, stat computations, damage formulas, and roster validations must strictly respect Regulation M-C limits (66 SP per Pokémon, max 32 SP per stat, legal items in `data/Regulation_MC_Items.csv`, and banned species in `system_guardrails.md`).
* **Canonical Trainer Terminology:**
  * Always use **Trainer** (English) or **Entrenador** (Spanish). Mecha or aviation terms (`pilot`, `piloto`) are strictly forbidden.
* **Zero Engine Hex Jargon in User Faces:**
  * User-facing text, reports, and UI labels must refer to the calculator and turn engine naturally (e.g., *Official VGC Damage Calculator* / *Simulador Oficial VGC*), never exposing raw internal hex multipliers or engine variables.

---

## 6. Test Suite Architecture & Taxonomy (testUT & testAT)

* **Dual-Tier Test Segregation:**
  * **Unit Tests (`tests/testUT/`):** Fast, in-memory, deterministic tests that validate individual classes, methods, and mathematical functions in strict isolation with zero network calls and mocked disk I/O.
  * **Acceptance & Integration Tests (`tests/testAT/`):** End-to-end user workflows, multi-turn battle simulations, Swiss flowcharting, security hardening, live Flask endpoint probing, schema validation, and cross-platform packaging.
* **Root-Mirroring Subfolder Topology:**
  * Both `tests/testUT/` and `tests/testAT/` must maintain internal subfolder structures that mirror the root repository architecture:
    * `tests/testUT/engine/` and `tests/testAT/engine/` mirror `engine/`.
    * `tests/testUT/evals/` and `tests/testAT/evals/` mirror `evals/`.
    * `tests/testUT/assets/` and `tests/testAT/assets/` mirror `assets/`.
    * `tests/testAT/frontend/` mirrors the dashboard UI layer (`assets/command_center.html`, `ui_server.py`).
    * `tests/testAT/rules/` mirrors `.agents/rules/` (anti-hallucination, banned species, translation parity).
* **1-to-1 Class Parity & Strict Naming Conventions:**
  * Test files must be named strictly and unambiguously after the class or domain service they are testing: `test_<TargetClass>.py`.
  * Every test file must contain a single primary test class following `class Test<TargetClass>(unittest.TestCase)`.
  * Monolithic multi-class test catch-alls (e.g. bundling disparate domain components into a single file) are strictly prohibited.
  * Negative adversarial tests must be co-located or mapped directly to their target unit (e.g., `test_Negative<TargetClass>.py` or as dedicated negative test methods within `Test<TargetClass>`).

