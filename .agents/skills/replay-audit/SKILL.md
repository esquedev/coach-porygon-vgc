---
name: replay-audit
description: >-
  Use this skill when the user provides a match replay, battle log, or third-party tournament match
  for Mode 1 Asynchronous Replay Breakdown & Telemetry Logging.
---

# Replay Audit: Asynchronous Replay Breakdown & Telemetry Logging

Deliver dense, mathematically grounded coaching analysis directly without conversational preambles or pleasantries.

---

## 0. Governance, Role Alignment & Validation Matrix
- **Owner Role:** Metagame & Scouting Analyst (`Role: Analyst`) / Head Coach (`Role: Coach`)
- **Domain Layer:** Domain Core (Turn Simulation & Turning Point Logic) & Infrastructure (Telemetry Persistence)
- **Permissions:** Read `data/trainer_profile.json`, `data/Teams.csv`, `data/Scouted_Teams.csv`; execute `engine/turn_simulator.py` and `engine/telemetry.py`; write (append) to `data/Raw_Matches.csv`, `data/Playstyle_Diagnostics.csv`, `data/Scouted_Raw_Matches.csv`, and `data/Damage_Calculations.csv`. Codebase is locked.
- **Minimum Viable Context (MVC):** Replay log, `known_alts`, `last_team_id`, Turning Point detection criteria, mistake taxonomy. Exclude: UI CSS design tokens, crawler HTML parsers, unit test implementations.
- **Deterministic Validation Criteria:**
  - Mandatory POV binding against `trainer_profile.json` (halt on ambiguity).
  - Multi-turn Minimax simulation ($T_N \to T_{N+1} \to T_{N+2}$) quantifying net $\Delta VP$.
  - Atomic telemetry logging via `python engine/telemetry.py`.

---

## Execution Workflow

1. **Trainer Profile & Strict Team ID Verification**:
   - Determine trainer POV by matching player usernames in the replay against `known_alts` in `data/trainer_profile.json`.
   - If the user did not specify a Team ID (`T01`–`Txx` or `STxx`):
     - Check `last_team_id` in `data/trainer_profile.json`.
     - If available, prompt: `[INPUT REQUIRED]: No Team ID specified. Are you running last registered team [last_team_id] or a new team? (If new, provide Showdown Team Paste to register via 'python engine/register_team.py').`
     - Halt execution immediately until confirmed. Never speculate, guess, or silently bind an old team.

2. **Pre-Turn Validation & Multi-Turn Minimax Branch Simulation ($T_N \to T_{N+1} \to T_{N+2}$)**:
   - Identify the **Turning Point** where a massive tempo swing or decisive $\Delta VP$ divergence occurred.
   - Actively execute [`engine/turn_simulator.py`](../../../engine/turn_simulator.py) to simulate the divergence across 2 to 3 turns:
      - **Turn $N$ Divergence:** Compare the user's actual action against the Minimax optimal line, calculating exact Showdown damage rolls, dual-typing effectiveness (4.0x weaknesses, 0.25x double resistances, 0.0x immunities), active STAB bonuses (Primary, Secondary, or converted '-ate' STAB), status procs, and immediate VP gain/loss.
     - **Turn $N+1$ Board Fallout:** Feed the simulator's output state into the next turn. Evaluate the resulting positional fallout (field condition expirations, exposed slots, lost weather/terrain momentum).
     - **Turn $N+2$ End-Game Trajectory:** Project the checkmate or stabilization path, establishing why the optimal branch preserved the win condition while the user's line collapsed.

3. **Structured Output Sections**:
   - **Match Telemetry:** `[Format: Bo1_Ladder / Bo3_Swiss] | [User Team ID] vs [Opponent] | Result: [Win/Loss] | Archetype Matrix: [User vs Opponent]`
   - **Win Condition Audit (Grade A–F):** Assess Team Preview selection and Turn 1 lead execution against opposing speed control.
   - **The Turning Point (Turn-by-Turn Minimax Simulation):**
     - Explicitly detail Turn $N$, Turn $N+1$, and Turn $N+2$ progression for both the **User's Line** and the **Minimax Counter-Line**.
     - Quantify the net VP delta (`Standard KO = +2 VP`, `Mega KO = +3 VP`, `Hard read / immunity switch = +2 VP`, `Critical Protect = +1 VP`).
    - **Tactical Execution & Misplay Diagnosis:** Assign standardized error codes (`POS-01`–`POS-03`, `TGT-01`–`TGT-03`, `MEC-01`–`MEC-02`, `SPD-01`–`SPD-02`), classify the root cognitive trap (`Tunnel_Vision`, `Greed`, `Autopilot`, `Tilt`, `Format_Divergence`), evaluate dual-type resistance or immunity errors, and dictate the deterministic imperative fix.
   - **Team Evolution & Commentary:** Formulate concise, actionable roster improvements (SP spread optimizations, item swaps, tech moves).

4. **Direct CSV Telemetry Ingestion**:
   - Log all telemetry directly into the workspace CSVs via [`engine/telemetry.py`](../../../engine/telemetry.py):
     - **Personal Matches (`Txx`):** Run `python engine/telemetry.py --mode personal --payload <json>` to automatically append the match to `data/Raw_Matches.csv` and log the cognitive trap row to `data/Playstyle_Diagnostics.csv`.
     - **Scouted Matches (`STxx` / Third-Party):** Run `python engine/telemetry.py --mode scouted --payload <json>` to append directly to `data/Scouted_Raw_Matches.csv`.
     - **Damage Calculations:** Run `python engine/telemetry.py --mode calc --payload <json>` to append newly computed damage rows directly to `data/Damage_Calculations.csv`.
   - Confirm the logged `Match_ID` and updated CSV files at the bottom of the breakdown.

---

## First-Proof Worked Example

```markdown
### Match Telemetry
[Format: Bo1_Ladder] | T24 vs opponent_vgc | Result: Loss | Archetype Matrix: Rain Offense vs Sun Balance

### Win Condition Audit (Grade: C+)
Turn 1 lead ceded instant board equity: dry hard switch into active sun boosted Charizard.

### The Turning Point (Turn 3 | VP Delta: -4 VP)
#### Multi-Turn Divergence Simulation (engine/turn_simulator.py):
- **User's Actual Line (Turns 3–5):**
  - *Turn 3:* Swapped Pelipper directly into Charizard Solar Beam without Protect (POS-01). Pelipper fainted (-2 VP). Lost weather control.
  - *Turn 4:* Archaludon forced to face boosted Sun Heat Wave without Rain support, taking 78% damage.
  - *Turn 5:* Opponent secured double KO. Match collapsed into checkmate.
- **Master Minimax Line (Turns 3–5):**
  - *Turn 3:* Protect Archaludon + Weather Ball Pelipper targeting Charizard partner slot while absorbing Sun hit (+1 VP Protect).
  - *Turn 4:* Rain reset on safe pivot. Electro Shot eliminates Mega Charizard Y (+3 VP Mega KO).
  - *Turn 5:* Dominant 4v2 board state secured.

### Tactical Execution & Misplay Diagnosis
- Error Code: POS-01 (Dry Hard Switch)
- Cognitive Trap: Autopilot
- Deterministic Fix: Run Pre-Turn Checklist step 2 & 3 before swapping in fragile weather setters; use Protect pivoting to reset field states safely.

### CSV Ingestion Status
Logged Match M2027-048 to data/Raw_Matches.csv and diagnostic to data/Playstyle_Diagnostics.csv.
```
