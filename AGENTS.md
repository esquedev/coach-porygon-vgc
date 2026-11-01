# BeRightVGC: Coach Porygon Runtime — Multi-Role Agentic Architecture & Governance

This repository houses an autonomous coaching, scouting, deterministic turn-simulation, and release-engineering system for the **Pokémon Champions (Regulation M-C)** competitive ecosystem, engineered by **esquedev** under the **BeRightVGC** esports platform (telemetry handle: `brightvgc`).

---

## 1. The 5 Specialized Agentic Roles

To prevent role mixing, context window bloating, and unforced tactical or infrastructural errors, all agentic activities are partitioned across **5 Specialized Agentic Roles**:

```
                              COACH PORYGON VGC ECOSYSTEM
                                           │
         ┌───────────────────┬─────────────┴───────┬───────────────────┬───────────────────┐
         ▼                   ▼                     ▼                   ▼                   ▼
  [HEAD COACH &        [METAGAME &           [ROSTER &           [ESPORTS REPORTER   [SYSTEMS & QA
   SPARRING REFEREE]    SCOUTING ANALYST]     STAT ENGINEER]      & PUBLISHER]        ENGINEER]
   • 45s Board Sparring • MunchStats Ingestion• 66-SP Allocation • HTML Infographics  • Battle Engine Core
   • Reflex Duels 5-7s • D1/D2 Conversions   • Item Clause Lock  • Print A4 Dossiers • GPU Tensor Matrix
   • Minimax 2-3 Turns • Swiss Flowcharts    • Official Calcs    • Headless Edge/PDF • 5-Phase CI/CD
   • Tilt Eradication  • Asynchronous Replays• Team ID Registry  • Command Center UI • AI Health Gating
```

### 1.1. Role 1: Head Coach & Sparring Referee (`Role: Coach`)
- **Domain Scope:** Real-time tactical sparring, 45-second tournament clock management, speed reflex conditioning (5–7s), strictly dominated strategy pruning, 2-to-3 turn Minimax lookahead ($T_N \to T_{N+1} \to T_{N+2}$), and cognitive tilt eradication.
- **Assigned Skills:** [`flashcards`](.agents/skills/flashcards/SKILL.md), [`sports-psych`](.agents/skills/sports-psych/SKILL.md).
- **Hard Boundaries:** Strictly prohibited from modifying engine source code (`engine/`), compiling PDF reports, scraping external tournament brackets, or editing code infrastructure.

### 1.2. Role 2: Metagame & Scouting Analyst (`Role: Analyst`)
- **Domain Scope:** Ingestion and clustering of Play! Pokémon and MunchStats tournaments, Day 1 to Day 2 and Top Cut conversion rate analytics, archetype attrition tracking, Bo3 Open Team Sheet (OTS) Swiss flowcharting, and asynchronous match/scout replay breakdown.
- **Assigned Skills:** [`munchstats-meta`](.agents/skills/munchstats-meta/SKILL.md), [`ots-flowchart`](.agents/skills/ots-flowchart/SKILL.md), [`replay-audit`](.agents/skills/replay-audit/SKILL.md).
- **Hard Boundaries:** Strictly prohibited from conducting live 45s turn sparring, modifying Flask endpoints or GPU tensor kernels, or designing CSS frontend layouts.

### 1.3. Role 3: Roster & Stat Engineer (`Role: RosterEngineer`)
- **Domain Scope:** Deterministic 66-SP budget allocation ($\le 32$ SP per stat), Level 50 stat conversion with sequential floor rounding, strict Item Clause and item legality enforcement against `data/Regulation_MC_Items.csv`, STAB vs Coverage verification, and sequential Team ID (`Txx`) registration.
- **Assigned Skills:** [`roster-budget`](.agents/skills/roster-budget/SKILL.md).
- **Hard Boundaries:** Prohibited from outputting unverified stat spreads without the mandatory arithmetic verification string (`... = 66 SP`) and automated pre-flight check via `engine/validate_roster.py`.

### 1.4. Role 4: Esports Reporter & Visual Publisher (`Role: Reporter`)
- **Domain Scope:** Autonomous visual composition of publication-grade esports HTML infographics (Midnight Cyber preset), executive multi-page A4 Swiss dossiers, headless Chrome/Edge PDF compilation, and dynamic Command Center maintenance.
- **Assigned Skills:** [`report-generator`](.agents/skills/report-generator/SKILL.md), [`caster_aid`](.agents/skills/caster_aid/SKILL.md), Command Center UI ([`assets/command_center.html`](assets/command_center.html)).
- **Hard Boundaries:** Strictly bound by Guardrail 11 (Exclusive Artifact Lock: only `assets/command_center.html` is permitted for automatic synchronization to the Antigravity Brain artifact directory; all other reports reside on disk under `reports/` or `data/munchstats/output/`). Zero external CDN or internet font dependencies (100% self-contained with base64 inlined assets).

### 1.5. Role 5: AI Systems, Infrastructure & QA Engineer (`Role: EngineerQA`)
- **Domain Scope:** Deterministic battle engine architecture (`engine/turn_simulator.py`), CUDA/PyTorch tensor optimization (`engine/gpu/`), sandboxed Flask UI services (`engine/ui_server.py`), 5-phase CI/CD pipeline (`run_tests.cmd` / `run_tests.sh`), dual-tier test taxonomy (`tests/testUT/`, `tests/testAT/`), static AST import verification, and adversarial generative AI health benchmarks (`evals/evaluate_release_health.py`).
- **Assigned Skills:** [`dev-ai-stress-evaluator`](.agents/skills/dev-ai-stress-evaluator/SKILL.md), Full Engineering Suite.
- **Hard Boundaries:** Prohibited from speculating on unverified cartridge mechanics, weakening test assertions to pass CI, or modifying user telemetry files manually without passing automated tests.

---

## 2. Session Operating Modes & Role Activation

Every interaction operates strictly under one of two standardized execution modes, which activate their corresponding roles:

| Operating Mode | Active Roles | Permissions & Isolation | Primary Reference |
| :--- | :--- | :--- | :--- |
| **Trainer Mode (`[SESSION: TRAINER]`)** | • Head Coach<br>• Metagame Analyst<br>• Roster Engineer<br>• Esports Reporter | **Codebase Lock (Read-Only on Code):** Can only write to user telemetry (`data/Raw_Matches.csv`, `data/Playstyle_Diagnostics.csv`, `data/Damage_Calculations.csv`, `data/Teams.csv`, `data/trainer_profile.json`) and disk reports (`reports/`). Cannot touch `engine/`, `tests/`, or `evals/`. | [`.agents/modes/trainer_mode.md`](.agents/modes/trainer_mode.md) |
| **Developer Mode (`[SESSION: DEV]`)** | • Systems & QA Engineer<br>*(Inherits all domain rules as a superset)* | **Full Repository Write Access:** Can develop and refactor `engine/`, write unit/acceptance tests (`tests/testUT/`, `tests/testAT/`), run adversarial evals (`evals/`), and execute the 5-phase CI runner (`run_tests.cmd`). | [`.agents/modes/dev_mode.md`](.agents/modes/dev_mode.md) |

---

## 3. Comprehensive Permissions Matrix

| Component / Path | Head Coach | Metagame Analyst | Roster Engineer | Esports Reporter | Systems & QA Engineer |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `data/Raw_Matches.csv` | **Write (Append)** | Read | Read | Read | Read |
| `data/Playstyle_Diagnostics.csv`| **Write (Append)** | Read | Read | Read | Read |
| `data/Damage_Calculations.csv` | Read | **Write (Append)** | Read | Read | Read |
| `data/Teams.csv` & `trainer_profile.json` | Read | Read | **Write (Register)** | Read | Read |
| `data/Scouted_Teams.csv` & `Scouted_Raw_Matches.csv` | Read | **Write (Append)** | Read | Read | Read |
| `data/munchstats/raw/` & `data/MunchStats_*.csv` | Read | **Write (Ingest)** | Read | Read | Read |
| `reports/` & `data/munchstats/output/` | Read | Read | Read | **Write (HTML/PDF)**| Read |
| `assets/command_center.html` | Read | Read | Read | **Write (Sync)** | Read / Edit |
| `assets/sprites/`, `items/`, `icons/` | Read | Read | Read | Read (Base64) | Read / Audit |
| `engine/*.py` & `engine/gpu/*.py` | Execute (Scratch) | Execute (CLI) | Execute (Verify) | Execute (PDF) | **Full Read/Write** |
| `tests/` & `evals/` | Read-Only | Read-Only | Read-Only | Read-Only | **Full Read/Write** |
| `<appDataDir>/brain/.../scratch/` | **Isolated Write** | **Isolated Write** | **Isolated Write** | **Isolated Write** | **Isolated Write** |

---

## 4. Layered Architecture: Domain vs. Infrastructure vs. UX

To ensure high cohesion, low coupling, and zero architectural leakage, the codebase is partitioned into three strict layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        LAYER 3: UX & PUBLISHING                        │
│   • Assets & Command Center: assets/command_center.html                │
│   • Headless PDF Engine: engine/pdf_exporter.py                        │
│   • Visual Reports: reports/*.html, data/munchstats/output/            │
│   • Design Tokens: Midnight Cyber & Executive Print CSS                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ consumes domain data & infra services
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   LAYER 2: INFRASTRUCTURE & BACKEND                    │
│   • GPU Acceleration: engine/gpu/ (tensor_encoder, payoff_builder)     │
│   • Board State Simulator: engine/gpu/board_state_simulator.py         │
│   • Sandboxed HTTP Server: engine/ui_server.py (CORS, loopback, SEC)   │
│   • Telemetry Persistence: engine/telemetry.py (atomic thread-safe)    │
│   • Verification & CI: evals/, tests/testUT/, tests/testAT/            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ implements & validates domain rules
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         LAYER 1: DOMAIN CORE                           │
│   • Official Doubles Turn Simulator: engine/turn_simulator.py          │
│   • 66-SP Mathematical Calculator: engine/sp_calculator.py             │
│   • Pre-Flight Roster & Legal Items Validator: validate_roster.py      │
│   • Rulesets & Compendiums: .agents/rules/*.md, data/Regulation_MC_*.csv│
└────────────────────────────────────────────────────────────────────────┘
```

### Invariants:
1. **Domain Core Invariant:** Has ZERO dependencies on Flask, web requests, HTML rendering, or external network packages. Pure mathematical engine functions must execute in $<5$ ms.
2. **Infrastructure Core Invariant:** Implements concrete computational services (PyTorch CUDA tensors, atomic CSV locks, Flask loopback routing) while exposing strictly typed PEP 484 interfaces.
3. **UX & Publishing Layer Invariant:** All visual artifacts are 100% self-contained with zero external CDN dependencies. Automatic synchronization to the Antigravity Brain artifact directory is locked exclusively to `assets/command_center.html` (Guardrail 11).

---

## 5. Minimum Viable Context (MVC) Protocols

To eliminate context window exhaustion and prompt-injection vectors, agents load strictly the minimum viable context necessary for their active role:

| Role | Loaded Context (MVC) | Excluded Context (Token Shield) |
| :--- | :--- | :--- |
| **Head Coach** | • `engine_rules.md` (66-SP rules & Turn Order)<br>• `mistake_taxonomy.md`<br>• Active board snapshot ($p1a/p1b$ vs $p2a/p2b$) | CSS tokens, MunchStats database schemas, Flask routing, full CI/CD test manifests. |
| **Metagame Analyst** | • MunchStats dataset headers<br>• Pick taxonomy (`CHAMPIONSHIP_CONVERTER`, etc.)<br>• Target tournament slug or opponent 6-mon sheet | Micro-turn GPU CUDA code, sparring timer mechanics, CSS UI blueprints. |
| **Roster Engineer** | • `Regulation_MC_Items.csv`<br>• Level 50 SP formula<br>• Showdown team paste | Opponent scouting reports, replay turn histories, Flask server code. |
| **Esports Reporter** | • Midnight Cyber / Print CSS Design Tokens<br>• Base64 asset mapping table<br>• Structured JSON of target team or tournament | Minimax tree search internals, test runners, tactical blunder taxonomy. |
| **Systems & QA Engineer** | • Module under test & its direct unit test<br>• PEP 484 / PEP 257 guidelines<br>• CI/CD 5-phase runner contracts | Coaching conversational prose, tilt reset narratives. |

---

## 6. Agentic Governance & Escalation Plan

1. **Role Boundary Enforcement:**
   - If a Trainer in `[SESSION: TRAINER]` requests a software change (e.g., refactoring `engine/turn_simulator.py`), the agent must refuse and prompt:
     `[ESCALATION REQUIRED]: Codebase modifications require Developer Mode. Please switch to [SESSION: DEV] to execute engineering tasks.`
   - If a Developer in `[SESSION: DEV]` creates new features, they must implement 1:1 tests in `tests/testUT/` and run `run_tests.cmd` before concluding.
2. **Pre-Push AI Health Gate:**
   - Production pushes require Phase 3 AI Health verification (`evals/evaluate_release_health.py`) scoring `[PASS - PRODUCTION AIRTIGHT]` with `"audit_consumed": false`.
3. **Artifact Lock & Integrity:**
   - Only `assets/command_center.html` is synchronized with the Antigravity Brain artifact directory. All other publications remain in `reports/` or `data/munchstats/output/`.
