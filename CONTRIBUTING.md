# Contributing to Coach Porygon VGC 🦆⚡

Thank you for contributing to **Coach Porygon VGC** — a **100% fan-made, strictly non-commercial** open-source VGC analytics engine and Replay Coach Studio.

---

## 1. Local Development Setup

```bash
git clone https://github.com/esquedev/coach-porygon-vgc.git
cd coach-porygon-vgc

python3 -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Activate Versioned Git Hooks (Required)
Every contributor must enable the repository's versioned Git hooks under `.githooks/`:

```bash
./scripts/install_git_hooks.sh
```

What the hooks enforce automatically:
- **`.githooks/pre-commit`**: Runs `python scripts/scan_repo_hallucinations.py` across all **7 codebase integrity gates**:
  1. `banned_species` — Zero non-Regulation M-C species names in `src/engine/`, `apps/`, `data/teams/`, or `.agents/skills/`.
  2. `banned_moves_and_rules` — Zero banned SV moves, Phase-0 Mega claims, or stale Hail logic.
  3. `p1_p2_identifiers` — AST check guaranteeing `trainer_1` / `trainer_2` everywhere (zero `p1` / `p2` variables or parameters).
  4. `team_pastes_legality` — Zero Terastallization (`Tera Type:`) or SV-only items in `data/teams/*.txt`.
  5. `domain_isolation` — Zero web framework / HTTP server imports inside `src/engine/`.
  6. `studio_js_syntax` — In-process V8 syntax verification (`py_mini_racer`) of `apps/replay_coach/static/app.js`.
  7. `reg_mc_md_asset_isolation` — Guarantees `assets/sprites/Reg_M-C/` contains strictly legal DuckDB M-C sprites, `assets/sprites/Reg_M-D/` holds the confirmed M-D differential only, rumored M-D preview sprites remain isolated in `assets/sprites/Reg_M-D_rumored/`, and `assets/slug_map.json` has zero broken paths.
- **`.githooks/pre-push`**: On pushes targeting `develop` or `main`, runs the full test suite (`pytest tests/ -q`), including **`TestAT-1`..`TestAT-10`** (`tests/test_acceptance_anti_hallucination.py`).

---

## 2. Architecture & Domain Invariants

1. **Domain Core Isolation (`src/engine/`):**
   - Pure tensor mathematics, DuckDB queries, damage calculation bridges, and game-theoretic solvers (`IEDS`, `HiGHS` Zero-Sum Nash LP, `Logit QRE`, `Selective 2-Ply Lookahead`, `8-Pillar Victory Equity`).
   - Zero web framework dependencies. All HTTP/UI code lives strictly in `apps/replay_coach/`.
   - Sanctioned tournament ingestion lives in `src/engine/munchstats_pipeline/munchstats_crawler.py` (stdlib `urllib` → NDJSON archive under `src/engine/data/munchstats/raw/archive/`).
2. **Regulation M-C Invariants:**
   - Level 50 Champions Stat Formulas (`HP = Base + SP + 75`; `Stat = floor((Base + SP + 20) * NatureMult)`), mandatory **31 IVs**, **66 total SP**, **max 32 SP per stat**.
   - Mega Evolution at Priority `+5.5` with instant speed tier recalculation; Terastallization forbidden.
   - All Pokémon/move/item/ability lookups MUST route through in-memory DuckDB (`engine.db_registry.get_registry()`).
3. **Discrete RNG Integrity:**
   - Never smear expected values. Use the Dual-Draw Spinning-Wheel on `[0, 100)` with SplitMix64 scrambling for accuracy, crits, multi-hits, secondary effects, speed ties, and 16 discrete damage rolls (`{85..100}/100`).
4. **Strict UI Register Separation (`VGC` vs. `Scientific`):**
   - In `vgc` mode (`es_vgc`, `en_vgc`), keep copy 100% competitive trainer language — never leak academic notation (`IEDS`, `Nash`, `QRE`, `LQRE`, `CVaR`, `Minimax`, `U_risk`).
   - Reserve formal game-theoretic notation strictly for `scientific` mode (`es_scientific`, `en_scientific`).
5. **Identifiers & Typing:**
   - Always use `trainer_1` and `trainer_2` (never `p1` or `p2`).
   - Include PEP 484 type annotations and PEP 257 docstrings on public classes/functions.

---

## 3. Running Tests & Updating Assets

```bash
# 7-gate anti-hallucination & JS syntax check
python scripts/scan_repo_hallucinations.py

# Full unit, integration, Lead Lab, Prep Tools & TestAT-1..10 acceptance suite
PYTHONPATH=src:. .venv/bin/pytest tests/ -v

# Rebuild deterministic sprite/item slug map (Reg_M-C + confirmed Reg_M-D only)
PYTHONPATH=src:. .venv/bin/python scripts/build_sprite_slug_map.py

# Ingest a new MunchStats tournament into DuckDB archive
PYTHONPATH=src:. .venv/bin/python -m engine.munchstats_pipeline.munchstats_crawler \
  --tournament-id "https://www.munchstats.com/tournaments/<TOKEN>/all/"

# Regenerate the offline Regulation M-D Meta Scout Base64 HTML report
PYTHONPATH=src:. .venv/bin/python scripts/generate_reg_md_meta_report.py
```

---

## 4. Building & Releasing `CoachPorygonStudio.exe`

We ship a lightweight (`~8 MB`) PyInstaller bootstrap launcher (`apps/replay_coach/launcher_entry.py` + `scripts/build_windows_launcher.py`) that auto-creates an isolated `.venv` and installs the user's exact GPU/CPU PyTorch wheel.

- **Dry-run verification on Linux / macOS / Windows:**
  ```bash
  python scripts/build_windows_launcher.py --check
  ```
- **Local Windows build:**
  ```powershell
  pip install pyinstaller
  python scripts/build_windows_launcher.py
  # Outputs dist\CoachPorygonStudio.exe
  ```
- **Automated GitHub Actions Release Pipeline (`.github/workflows/build-windows-launcher.yml`):**
  1. Every push to `develop` or `main` runs **`.github/workflows/ci.yml`** (Flake8, 7-gate anti-hallucination scanner, Python `3.11`/`3.12` unit suite, `TestAT-1`..`TestAT-10` acceptance fuzzer, `twine check`, and `build_windows_launcher.py --check`).
  2. When CI passes cleanly on **`main`**, `build-windows-launcher.yml` automatically compiles and uploads `CoachPorygonStudio.exe` and `CoachPorygonVGC-windows-x64.zip` as workflow artifacts.
  3. Pushing a **`v*` release tag** enforces that the tagged commit is an ancestor of `origin/main` AND passes the full test + anti-hallucination suite before compiling and publishing the public GitHub Release.

---

## 5. Non-Commercial Fan Policy & Licensing

Original source code contributions are licensed under **GNU AGPLv3** ([`LICENSE`](LICENSE)). Please review [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) before adding any third-party library or asset.
