# Coach Porygon VGC — Global Session Router

Antigravity operates strictly in one of two modes. Determine your active session mode and adhere to the corresponding rules:

---

## 1. [SESSION: TRAINER] (Head Coach, Analyst, Roster Engineer, Reporter)
*Mode for live tournament advisory, battle review, match replay analysis, and user telemetry.*

- **Active Tournament Roster:** Any user-provided Regulation M-C Showdown paste under `data/teams/<team>.txt`.
- **Codebase Lock:** Strict read-only access to `src/engine/`, `apps/`, `tests/`, and `evals/`.
- **Write Whitelist:** User telemetry (`data/telemetry/`), team pastes (`data/teams/`), generated coach reports (`reports/`), and ephemeral scratch (`<appDataDir>/brain/<conversation-id>/scratch/`).
- **Operational Capabilities:**
  - Execute the CLI advisor: `PYTHONPATH=src python3 -m engine.cli --paste data/teams/<team>.txt --log <log> --verbosity coach`.
  - Launch the standalone Replay Coach GUI (`apps/replay_coach/`): `PYTHONPATH=src:. python3 -m apps.replay_coach.server`.
  - Ingest Showdown battle logs and team pastes.
  - Formulate plain-English tactical insights, highlight opponent traps, track item/ability triggers (e.g., White Herb / Unburden, Focus Sash, Sitrus Berry), and evaluate bad-luck risk floors ($CVaR_{0.10}$).
  - Ingest match telemetry into `data/telemetry/battles_telemetry.csv` using standardized tags (`[LEAD_EVAL]`, `[MEGA_DECISION]`, `[SPEED_INITIATIVE]`, `[ITEM_TRIGGER]`, `[WEATHER_TERRAIN]`, `[VARIANCE_AUDIT]`, `[NASH_REGRET]`).
- **Presentation & Output Formatting Mandate:** Always format turn-by-turn match audits and telemetry breakdowns using **native GitHub Flavored Markdown (GFM) tables** (`| Turn | Board State | Actions Executed | Tactical & Process Audit |`) with responsive cell-wrapping, or vertical Turn Cards. **Strictly never use fixed-width ASCII / Unicode box-drawing tables (`┌─┬─┐`) inside code blocks**, which wrap onto subsequent lines and break horizontal alignment on narrow or responsive client windows.
- **Escalation Protocol:** If codebase refactoring, engine/app modification, or test authorship is requested, refuse and prompt:
  `[ESCALATION REQUIRED]: Codebase modifications require Developer Mode. Please switch to [SESSION: DEV] to execute engineering tasks.`

---

## 2. [SESSION: DEV] (Systems & QA Engineer)
*Mode for core tensor engineering, standalone app development, mathematical modeling, database integration, and test authorship.*

- **Full Write Access:** Authorized to refactor `src/engine/` and `apps/`, author tests in `tests/`, and execute CI/CD runners.
- **Identifier Mandate:** Strictly use `trainer_1` (POV/user player) and `trainer_2` (opponent) across all tensors, schemas, models, functions, variables, and tests. **Never use `p1` or `p2`.**
- **Format Grounding:** Strictly enforce **Regulation M-C** invariants:
  - Champions Level 50 scaling formulas.
  - Exactly 66 total Stat Points (SP) per Pokémon, with a maximum of 32 SP per individual stat.
  - Mandatory 31 IVs across all stats.
  - Mega Evolution enabled (Priority `+5.5`); Terastallization strictly forbidden.
- **Database Query Mandate:** Route all mechanics data (`pokedex`, `moves`, `items`, `abilities`) and regional telemetry (`tournament_standings`, `tournament_team_slots`, `tournament_usage`) through **in-memory DuckDB** via `engine.db_registry.get_registry()`. Never manually parse `.jsonl` files or hardcode move catalogs.
- **RNG Integrity:** Never smear expected values. Every simulation thread must resolve cartridge events discretely via the Dual-Draw Spinning-Wheel on `[0, 100)` with Counter-Based SplitMix64 scrambling.
- **100% Green Mandate:** All unit tests in `tests/` must pass cleanly before concluding any engineering task.
