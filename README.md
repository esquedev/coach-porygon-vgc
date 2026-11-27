# Coach Porygon VGC 🦆⚡

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch CUDA & CPU](https://img.shields.io/badge/PyTorch-CUDA_%7C_CPU-ee4c2c.svg)](https://pytorch.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-38k_Slots_(9_Events)-FFF000.svg)](https://duckdb.org/)
[![Format: Reg M-C](https://img.shields.io/badge/Format-Regulation_M--C_(Champions)-7c3aed.svg)](https://www.pokemon.com/)
[![Tests](https://img.shields.io/badge/Pytest-100%25_Passing-brightgreen.svg)](tests/)

**An open-source GPU/CPU Tensor State Machine, 90×90 Team-Preview Lead Lab & Game-Theoretic Replay Coach for Competitive Pokémon VGC 4v4 Doubles (Regulation M-C / Pokémon Champions).**

Coach Porygon VGC boots into a unified **7-Card Cyber-Tactical Command Hub** featuring:
1. **⚡ Dynamic Speed Tiers (Offline Base64 HTML)** — Lv.50 31-IV speed tables against Top 50 DuckDB (`9` official events incl. LAIC 2027) with Tailwind, Icy Wind, Choice Scarf, Unburden, Weather, and Mega speed shifts.
2. **💥 Damage & KO Matrix (Offline Base64 HTML)** — Exact 16-roll `SmogonChampionsCalc` OHKO/2HKO matrices across 5 Weathers × 5 Terrains & Screens.
3. **🧠 Bo3 Replay Coach (Tactical HUD + Live LQRE $\beta$ + Hybrid GPU+CPU Scheduler)** — Synchronized official Showdown player + zero-scroll Tactical HUD (sprite-visualized *Played vs. #1* cards, 8-Pillar diverging tug-of-war equity bars, live adjustable Logit QRE $\beta \in [0.5, 20.0]$ slider with skill presets & formula card, strict VGC vs. Scientific language separation), Showdown opponent anonymization (`Showdown Opponent (Elo N)`), true wire Game # preservation, and a **Zero-GIL Hybrid GPU + Multi-Core CPU Turn Scheduler** with post-join ordered hardware-tagged logs.
4. **🎯 Factored 90×90 Turn-1 Lead & Bring Lab (+ Own × Opp Playbook Matrix & DuckDB Vault)** — Pit any two 6-Pokémon teams (Full 66-SP or EV-less OTS + 1–3 Bo3 scouting logs) and simulate Turn 1 across all 15×15 leads × 6×6 benches (`8,100` modes) via **Dual-End Hybrid GPU + Multi-Core CPU Work-Stealing**, persistent DuckDB Matchup Vault caching, interactive **Own-Lead × Opp-Lead Turn-1 Playbook Matrix**, live adjustable LQRE $\beta$, `15×15` heatmap, `6×6` Back-2 drilldown, and 1-click/batch unpruned Turn-1 Audit (`K=128`).
5. **📊 Bo3 Session & Tournament Analytics** — Local team-folder CSV telemetry (`data/telemetry/`) tracking Win Rate, accuracy curve, phase errors, and lead-pair effectiveness.
6. **🔮 Regulation M-D Meta Scout & Prep Dossier (Offline Base64 HTML)** — 8-Tab tournament prep dossier (`5.35 MB`, `244` embedded Base64 sprites) featuring ** Coach Porygon's Signature 66-SP Reg M-D Team ("Iron-Volt Crown")**, `Regieleki` & `Regidrago`, 26 exact 16-roll Champions damage benchmarks, Top-20 DuckDB M-C → M-D Shift Matrix, 39-mon Interactive Speed Tiers, 5 Counterplay Playbooks, Interactive 6-Mon Readiness Checker, 31-mon Tier List (**Confirmed M-D** vs. **Rumored Wave**), and 6 LAIC 2027 → M-D Blueprints.
7. **🗄️ Own vs. Rival Team Database (DuckDB)** — Dedicated searchable roster vault separating **🏠 Own Teams** vs. **🛡 Rival Teams** with automatic archetype classification (`Sun / Weather`, `Rain`, `Sand`, `Trick Room`, `Tailwind Offense`, `Balance`), Regulation filters (`Reg M-C` / `Reg M-D`), and opponent Elo badges.

> **🇪🇸 Resumen Rápido (Español):** Coach Porygon VGC es un entrenador interactivo y motor matemático en GPU/CPU para **Pokémon VGC Dobles (Regulation M-C / Champions)**. Carga tus replays Bo1/Bo3 de Pokémon Showdown y tus equipos 66-SP (o resuelve los SPs rivales exactos con `smogon/damage-calc` Champions) para auditar cada turno con simulación RNG discreta, protección de peor escenario ($CVaR_{10}$), equilibrio de Nash, **Herramientas Prep Base64 offline (Velocidades y Matriz de Daño sin IA)** y analítica de sesiones Bo3 — **100% bilingüe (ES / EN) y sin LLMs en el motor de cálculo**. En Windows haz doble clic en **`start_replay_coach.bat`** (o compila **`CoachPorygonStudio.exe`**); en Linux/macOS ejecuta **`./start_replay_coach.sh`** — ambos crean y activan `.venv` automáticamente sin tocar tu Python del sistema.

---

## 1. Install & Run the Replay Coach Web Server (Windows, Linux & macOS)

### Option A — 1-Click Isolated `.venv` Launchers (Recommended)
1. Install **[Python 3.10+](https://www.python.org/downloads/)** (on Windows, check **"Add python.exe to PATH"**).
2. Clone or download this repository:
   ```bash
   git clone https://github.com/esquedev/coach-porygon-vgc.git
   cd coach-porygon-vgc
   ```
3. Launch with **automatic isolated `.venv` creation & activation** (never touches system Python packages):
   - **Windows (Batch):** Double-click **[`start_replay_coach.bat`](start_replay_coach.bat)** (or run `.\start_replay_coach.bat`).
   - **Linux / macOS (Bash):** Run **`./start_replay_coach.sh`**.
   - **Windows Native Launcher (`.exe`):** Build or download the lightweight **`CoachPorygonStudio.exe`** (`~8 MB`, see Option B below) and double-click it inside the repo folder.

What every launcher does automatically:
- Creates and activates an isolated project **`.venv`** on first run (never pollutes system-wide Python).
- Checks a SHA-256 stamp of `requirements.txt` (`.venv/.requirements.sha256`) plus full core imports (`torch`, `numpy`, `scipy`, `duckdb`, `py_mini_racer`) so dependency updates sync automatically while subsequent launches boot in ~2s.
- Auto-detects NVIDIA GPUs (`nvidia-smi`) to install **CUDA 12.4 PyTorch**, or **CPU / Apple Silicon PyTorch** otherwise.
- Sets `PYTHONPATH` (`src;.` / `src:.`), starts Replay Coach Studio at **`http://127.0.0.1:8765/`**, and opens your browser automatically.

*(Pass server flags straight through any launcher, e.g. `./start_replay_coach.sh --device cpu --port 9000` or `.\start_replay_coach.bat --port 9000`.)*

### Option B — Windows No-Git 1-Click Release Bundle (`CoachPorygonStudio.exe`)
For Windows users who prefer not to use `git`, download **`CoachPorygonVGC-windows-x64.zip`** from the **[GitHub Releases](https://github.com/esquedev/coach-porygon-vgc/releases/latest)** page, extract it, and double-click **`CoachPorygonStudio.exe`** (`~8 MB`, compiled automatically on `windows-latest` via [`.github/workflows/build-windows-launcher.yml`](.github/workflows/build-windows-launcher.yml) **only after 100% of CI & acceptance tests pass on `main`**, or on verified `main`-ancestor `v*` release tags).

Instead of shipping a bloated 3 GB CPU-only PyTorch monolith, `CoachPorygonStudio.exe` wraps the pure-stdlib launcher ([`apps/replay_coach/launcher_entry.py`](apps/replay_coach/launcher_entry.py)) with a custom Great Ball icon ([`assets/coach_porygon.ico`](assets/coach_porygon.ico)) and bootstraps `.venv` with the user's exact GPU:
```powershell
# Dry-run validate on Linux / macOS / Windows:
python scripts/build_windows_launcher.py --check

# Or compile locally on Windows:
pip install pyinstaller
python scripts/build_windows_launcher.py
# Output: dist\CoachPorygonStudio.exe
```

### Option C — Manual Setup (PowerShell / Bash)
```powershell
git clone https://github.com/esquedev/coach-porygon-vgc.git
cd coach-porygon-vgc

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# With NVIDIA GPU (CUDA 12.4):
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt

# Or CPU-only:
# pip install -r requirements.txt

$env:PYTHONPATH = "src;."
python -m apps.replay_coach.server
# Open http://127.0.0.1:8765/ in your browser
```

<details>
<summary><strong>Linux / macOS Installation & Server Flags</strong></summary>

```bash
git clone https://github.com/esquedev/coach-porygon-vgc.git
cd coach-porygon-vgc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src:. python3 -m apps.replay_coach.server --device auto --port 8765
```
CLI flags for `apps.replay_coach.server`: `--host` (default `127.0.0.1`), `--port` (default `8765`), `--device {auto,cuda,cpu}`.

</details>

---

## 2. How the Linear Algebra Tensor Core Works

Traditional Pokémon simulators use slow Python object trees and nested `if/else` loops — impossible to evaluate across hundreds of simultaneous VGC action pairs (`26 × 26 = 676` joint lines per trainer) and hundreds of discrete RNG rolls per cell.

**Coach Porygon VGC** compiles the entire 4v4 Doubles board into **3 flat `float32` tensors** so every rule runs simultaneously across `[Strats_1 × Strats_2 × K]` parallel worlds:

![3-Tensor VGC Board State Representation v2.1](docs/images/tensor_anatomy.svg)

| Tensor | Shape | What It Stores |
| :--- | :--- | :--- |
| **`F` (Field)** | `[Strats_1, Strats_2, K, 26]` | Weather & Terrain one-hots/timers, Trick Room, Gravity, Tailwind, Reflect/Light Screen/Aurora Veil, Mega flags, Toxic Spikes. |
| **`P` (Roster)** | `[Strats_1, Strats_2, K, 8, 96]` | 8 fixed slots (`0–3` `trainer_1`, `4–7` `trainer_2`) × HP, L50 stats, boosts (`-6..+6`), status/Disguise, dual-types, items, abilities, Mega payload, and **2-Turn Persistent State (`88..95`)** (`STOMPING_PRIMED`, `LAST_MOVE_FAILED`, `CONSEC_USE`, `RECHARGE`, `CHARGING`, `ENCORE`). |
| **`M` (Moves)** | `[Strats_1, Strats_2, K, 8, 4, 60]` | 4 DuckDB-compiled move vectors per slot (BP, accuracy, priority, 18-type one-hot, multi-hit, recharge/contact/slicing/punch/pulse/bite/bullet flags). |

### Worked Example: One Branchless Operation (`Switch-In + Intimidate`)

Instead of branching with `if mon.switched:`, every game mechanic is a **matrix multiplication or binary gate `g ∈ {0, 1}` operating across rows simultaneously**. Below is how **Phase 1 (Switch-In + Intimidate + Defiant + White Herb / Unburden)** resolves in one GPU pass:

![Step-by-Step Branchless Switch-In plus Intimidate Operation](docs/images/switch_intimidate_op.svg)

### End-to-End Architecture Pipeline

![Coach Porygon VGC Zero-AI Architecture Pipeline](docs/images/architecture_pipeline.svg)

1. **Permutation Matrix Multiply (`Π · P_before = P_after`):** Selecting *Switch Slot A → Bench 1* swaps Row `0` (`Charizard`) and Row `2` (`Incineroar`) via permutation matrix `Π`, while the persistence mask `m` zeroes temporary stat boosts (`SpA +2 → 0`) on the outgoing Pokémon in the exact same multiply.
2. **Masked Vector Addition (`Intimidate + Defiant + White Herb`):** Opposing Active Rows `r4` (`Kingambit`) and `r5` (`Sneasler`) receive `-1 Atk` from `Incineroar`, then branchless counter-gates add `+2 Atk` for `Defiant` and restore `< 0 → 0` + `Unburden (2× Speed)` for `White Herb` — letting the GPU automatically spot and penalize bad Intimidate traps in Nash/IEDS!

**Why this extrapolates cleanly to the whole engine:**
- **Mega Evolution (Phase 2, Priority `+5.5`):** Exact same blend formula (`Stats' = (1 - m)·Stats + m·MegaStats`) with instantaneous Regulation M-C speed recalculation.
- **Type Effectiveness (Phase 4):** Bilinear matrix contraction across the `18 × 18` type chart (`m_typeᵀ · T · t_1 × m_typeᵀ · T · t_2`), plus exact weather stat buffs (Rock `1.5× SpD` in Sand, Ice `1.5× Def` in Snow).
- **Discrete RNG & Downside Risk (`CVaR_10`):** Zero expected-value smearing — every thread `k` spins a SplitMix64 Dual-Draw wheel for accuracy, crits, and the 16 cartridge damage rolls (`{85..100}/100`), then ranks plays by $U_{\text{risk}} = 0.75\,\mathbb{E}[U] + 0.25\,CVaR_{0.10}[U]$ through **IEDS → Zero-Sum Nash LP → Logit QRE** (plus optional **Selective 2-Ply Lookahead** on the Strict-IEDS core).

---

## 3. Capabilities & Visual Showcase

### A. Replay Coach Studio (`apps/replay_coach/`)
A 3-step guided local web app featuring:
- **Step 1 — Bo1 / Bo3 Bundle & Clamped 66-SP OTS Workbench:** Drag-and-drop **1 to 3 Showdown replays (`G1`/`G2`/`G3`)** together to auto-extract opponent `|showteam|` OTS and solve exact clamped 66-SP bounds (`[min_sp, max_sp]`) via the vendored offline **`smogon/damage-calc` Champions** engine (`mini-racer` / `quickjs`, zero Node.js required). Locked (`🔒`) and bounded stats cannot be overridden; adjust remaining unobserved SPs interactively with live Level 50 stat previews, searchable DuckDB team library with sprites, and optional **`2-Ply (Turn+2)`** lookahead toggle.
- **Step 2 — Live Tensor Core Execution Console:** Real-time SSE phase-by-phase log (`COMPILE → PRUNE → PHASE 1–5 → IEDS → PLY_2 → NASH_QRE → VERDICT`) with live Stop / Resume / Restart controls and seamless `G1`/`G2`/`G3` game switching.
- **Step 3 — Synchronized Showdown Review & Bo3 Session Analytics:** Official Showdown battle playback synced to turn verdicts (`!!`, `!`, `?!`, `?`, `??`), unified top player controls, **4-profile bilingual switcher (`ES`/`EN` × `VGC`/`Scientific`)**, team CSV telemetry export, **Bo3 Session Analytics Dashboard**, and 1-click diagnostic **Bug Log Generator**.
- **Topbar `Prep Tools` (`Herramientas Prep`) View — Zero-AI Offline Base64 Mobile Generator:** Pick any saved DuckDB roster or paste any Regulation M-C 66-SP team, choose `Top 20 / 35 / 50`, interactively preview **Speed Tiers** (exact 31-IV Champions Lv. 50 speeds + Base/Mega switchers + dynamic team speed-doubling toggles) and **Damage & KO Matrix** (pre-computed exact `smogon/damage-calc` Champions 16-roll tables across all **5 Weathers** `Clear/Sun/Rain/Sand/Snow`, all **5 Terrains** `None/Electric/Grassy/Psychic/Misty`, Spread vs. Single-Target, Helping Hand, Screens, Crit, Burn, Partner Double-Up, Focus Sash/Sitrus/Resist Berries/Terrain Seeds, and 7 legal `≤ 66 SP` bulk profiles), and 1-click download a portable single-file offline `.html` for your phone — **zero AI subscription required!**

| Step 1 — Match & Full OTS Setup | Step 3 — Synchronized Replay & Coach Advice |
| :---: | :---: |
| ![Replay Coach Studio Setup](docs/images/studio_setup.png) | ![Replay Coach Studio Review](docs/images/studio_review.png) |

---

### B. Zero-AI Automated Offline Mobile-Portable Prep Tools (Base64 HTMLs)
Generate zero-dependency, single-file Base64 HTML reports for **any** 6-Pokémon Regulation M-C team directly from the Studio **`Prep Tools`** view or via the headless CLI (`scripts/generate_prep_tools.py`) — powered 100% by in-memory DuckDB, local Base64 sprites, and vendored `smogon/damage-calc` Champions:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/generate_prep_tools.py \
  --team data/teams/char_y_v4.txt \
  --top-n 50 \
  --out-dir reports/prep_tools \
  --lang en
```

| Interactive Speed Tiers (Mobile Base64) | Interactive Damage & KO Matrix (5 Weathers × 5 Terrains) |
| :---: | :---: |
| ![Speed Tiers Mobile Preview](docs/images/speed_tiers_preview.png) | ![Damage Calcs Mobile Preview](docs/images/damage_calcs_preview.png) |

---

### C. Antigravity IDE Agentic Coaching Workflows
Built-in workspace rules ([`AGENTS.md`](AGENTS.md)) and skills turn Antigravity IDE into a Regulation M-C Head Coach (`[SESSION: TRAINER]`) grounded strictly in in-memory DuckDB (`pokedex`, `moves`, `items`, `abilities`, `tournament_team_slots`):
- **`team-modes-and-preview-playbook`:** Computes all 15 4-mon modes and 15 lead pairs for any 66-SP roster into a 90-second Team Preview Decision-Tree Playbook.
- **`battle-telemetry-feedback`:** Extracts Showdown battle logs into `data/telemetry/<team>/battles_telemetry.csv` with standardized coaching audit tags (`[LEAD_EVAL]`, `[MEGA_DECISION]`, `[VARIANCE_AUDIT]`, `[NASH_REGRET]`).

![Antigravity IDE Agentic Coaching Workflow](docs/images/antigravity_ide.png)

---

## 4. Headless Bo1/Bo3 CLI & Test Suite

### Headless Bo1/Bo3 OTS 66-SP & Tensor Core CLI (`scripts/coach_bo3.py`)
```bash
PYTHONPATH=src:. python3 scripts/coach_bo3.py \
  --team data/teams/char_y_v4.txt \
  --replays g1.html g2.html g3.html \
  --rng-samples 128 \
  --lang en \
  --style vgc \
  --export-csv char_y_v4
```
*(Supports `--opp-ots <file>` for Bo1 replays without `|showteam|`, `--two-ply` for Selective 2-Ply Lookahead, `--no-sim` for instant 66-SP solving only, `--device {auto,cuda,cpu}`, `--lang {es,en}`, and `--style {vgc,scientific}`.)*

### Verification, Git Pre-Hooks & Contributing (`develop` & `main`)
See **[`CONTRIBUTING.md`](CONTRIBUTING.md)** for full developer guidelines, 7-gate anti-hallucination checks, and `.exe` release rules.
```powershell
# Windows (PowerShell)
$env:PYTHONPATH = "src;."
.\.venv\Scripts\pytest.exe tests/ -q

# Linux / macOS — Full suite + TestAT-1..10 Acceptance & Anti-Hallucination Model Fuzzer
PYTHONPATH=src:. .venv/bin/pytest tests/ -q

# Activate local versioned Git pre-commit (7 gates + V8 JS check) & pre-push hooks
./scripts/install_git_hooks.sh
```
GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) automatically runs **Lint & 7-Gate Anti-Hallucination Scanner**, **Unit/Integration Tests (`3.11`/`3.12`)**, **Acceptance Test & Anti-Hallucination Model Fuzzer**, and **Package + Launcher Check** on every push and PR targeting `develop` or `main`. Only when `main` passes full CI does [`.github/workflows/build-windows-launcher.yml`](.github/workflows/build-windows-launcher.yml) compile and publish `CoachPorygonStudio.exe`.

---

## 5. Community Special Thanks, License & Third-Party Credits

### Special Thanks to the Community 💚
Special thanks to the **Pokémmunity MÉXICO** and **PokéMex** group chats for their constant support, real-match testing, and feedback that shaped Coach Porygon VGC's features and UX.

### Fan-Made Non-Commercial Project & Intellectual Property Disclaimer
**Coach Porygon VGC** is a **100% fan-made, strictly non-commercial** project created by fans for fans and **will never be monetized** (no ads, no paywalls, no subscriptions, no sponsorships).

> **Trademark & Copyright Notice:** Pokémon, Pokémon Champions, and all Pokémon names, forms, moves, abilities, items, and sprites are trademarks and copyrights of **© Nintendo, Creatures Inc., GAME FREAK inc., and The Pokémon Company**. This project is **not affiliated with, endorsed by, or sponsored by** Nintendo, Creatures Inc., GAME FREAK inc., or The Pokémon Company.

### Source Code License
Original Coach Porygon VGC source code is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)** — see [`LICENSE`](LICENSE). Third-party software, community datasets, and official Pokémon trademarks/sprites are explicitly excluded from the AGPLv3 grant and remain the property of their respective owners.

### Third-Party Vendor, Asset & Data Credits
Full license texts and attributions live in **[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)**:

| Component | Credit / Source | License |
| :--- | :--- | :--- |
| **Pokémon Sprites, Items, Mega Stones & Reg M-C / M-D Catalogs** | **[Pokéos](https://www.pokeos.com/)** | Official Pokémon assets © Nintendo / Creatures Inc. / GAME FREAK inc. / The Pokémon Company |
| **Champions Damage Calculator (`@smogon/calc` v0.12.0)** | **[Smogon `damage-calc`](https://github.com/smogon/damage-calc)** (Honko & contributors) | MIT |
| **Replay Player (`replay-embed.js`) & Champions Mod Data** | **[Pokémon Showdown](https://github.com/smogon/pokemon-showdown)** (Guangcong Luo / Zarel & contributors) | MIT |
| **Regional Tournament Standings & Meta Usage** | **[MunchStats](https://www.munchstats.com/)** | Community tournament dataset |
| **Core Compute & Storage Stack** | **PyTorch** (BSD-3), **NumPy** (BSD-3), **SciPy / HiGHS** (BSD-3 / MIT), **DuckDB** (MIT), **MiniRacer / V8** (ISC / BSD-3) | Respective OSI licenses |

*Rights-holder removal requests: contact `esquedevil94@gmail.com`.*
