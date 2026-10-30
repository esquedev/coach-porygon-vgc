# Contributing to Coach Porygon VGC

This document defines the branch naming taxonomy, commit conventions, and workflow standards for evolving the **Coach Porygon VGC** runtime, coaching rules, and Regulation M-C data pipelines.

---

## 1. Branch Naming Taxonomy (`<domain>/<short-slug>`)

Never commit directly to `master`. Always create a scoped branch using one of the five domain prefixes below:

| Prefix | Scope & Purpose | Target Directories | Example Branch Name |
| :--- | :--- | :--- | :--- |
| **`feat/`** | New architectural layers, new operational skills, or end-to-end pipelines | `.agents/`, `engine/`, `scouts/` | `feat/v1-agent-architecture` |
| **`engine/`** | Deterministic math, Showdown `0x1000` modifier parity, 66-SP stat rules, or turn simulation logic | `engine/` | `engine/showdown-parity-fixes` |
| **`coach/`** | Adjustments to Regulation M-C rules, Mistake Taxonomy (`POS`/`TGT`/`MEC`/`SPD`), or Mode 1–5 `SKILL.md` prompts | `.agents/rules/`, `.agents/skills/`, `AGENTS.md` | `coach/mode1-telemetry-tuning` |
| **`data/`** | Adding/updating personal rosters (`Teams.csv`), tournament scrapes (`Scouted_Teams.csv`), or Markdown compendium dossiers | `data/`, `data/compendium/` | `data/laic-prep-rosters` |
| **`fix/`** | Bug fixes in webhook URL encoding, CSV/TSV formatting, or scraper lookups | `engine/`, `scouts/` | `fix/webhook-pipe-encoding` |

---

## 2. Standard Git Workflow (Stashing, Branching & Committing)

### Moving Uncommitted Work Off `master`
If you have modified and untracked files in your working tree on `master`, always include **`-u` (`--include-untracked`)** when stashing so new directories (`.agents/`, `data/`, `engine/`, `scouts/`) are captured:

```powershell
# 1. Stash modified AND untracked files
git stash push -u -m "wip: describe current changes"

# 2. Create and switch to a properly scoped branch
git switch -c feat/v1-agent-architecture

# 3. Restore your stashed changes onto the new branch
git stash pop
```

### Commit Message Format
Follow Conventional Commits aligned with the branch prefixes:
* `feat: initialize v1 agent architecture, turn simulator, and Reg M-C data`
* `engine: add Aurora Veil and Helping Hand modifiers to turn_simulator.py`
* `coach: refine TGT-01 Protect tunneling heuristics in mode1-replay-audit`
* `data: ingest Puebla Regional top 36 OTS cores into Scouted_Teams.csv`
* `fix: encode newline characters as %7C in telemetry.py`

---

## 3. Pre-PR Validation Checklist

Before merging any branch into `master`, verify the following domain guardrails:

1. **Engine Changes (`engine/`):**
   * Run `python engine/turn_simulator.py` to confirm the Turn 6 Doubles test harness executes cleanly.
   * Run `python engine/sp_calculator.py --species "Charizard-Mega-Y" --nature Modest --hp 18 --atk 0 --def 1 --spa 32 --spd 1 --spe 14` to verify 66-SP validation and floor rounding.
2. **Coaching & Skill Changes (`coach/`):**
   * Ensure zero Gen 1–9 legacy training terms (`EVs`, `Effort Values`, `IVs`, `Individual Values`, `Hyper Training`) appear in coaching prose.
   * Verify that `.agents/rules/*.md` files stay under the `24 KB` per-file rule cap.
3. **Data & Compendium Changes (`data/`):**
   * Ensure all `.csv` and `.md` files are saved in **UTF-8** encoding with trailing empty template rows stripped.
   * Do not commit raw `.docx` or `.xlsx` binary exports into `data/compendium/`; convert them to `.md` and `.csv` first.
