---
name: mode1-replay-audit
description: >-
  Use this skill when the user provides a match replay, battle log, or third-party tournament match
  for Mode 1 Asynchronous Replay Breakdown & Telemetry Logging.
---

# Mode 1: Asynchronous Replay Breakdown & Direct CSV Telemetry Logging

Deliver dense, mathematically grounded coaching analysis directly without conversational preambles or pleasantries.

## Execution Workflow

1. **Automated Team ID Resolution**:
   - If the user did not specify a Team ID (`T01`–`T23` or `STxx`), run:
     `python scouts/munchstats_scraper.py --lookup <Species1> <Species2> ...`
   - Bind a single match automatically, prompt if ambiguous, or issue the `[INPUT REQUIRED]` hard halt if zero matches exist.
2. **Pre-Turn Validation & Minimax Branch Simulation**:
   - Identify the **Turning Point** where a `+6 VP` Checkmate state or massive tempo swing occurred.
   - Use [`engine/turn_simulator.py`](../../engine/turn_simulator.py) to simulate the exact turn divergence comparing the **User's Line** against the **Master-Tier Minimax Line**.
3. **Structured Output Sections**:
   - **Match Telemetry:** `[Format: Bo1_Ladder / Bo3_Swiss] | [User Team ID] vs [Opponent] | Result: [Win/Loss] | Archetype Matrix: [User vs Opponent]`
   - **Win Condition Audit (Grade A–F):** Assess Team Preview selection and Turn 1 lead execution against opposing speed control.
   - **The Turning Point (VP Heuristic):** Pinpoint the exact turn of divergence, explicitly outputting the VP delta (`Standard KO = +2 VP`, `Mega KO = +3 VP`, `Hard read / immunity switch = +2 VP`, `Critical Protect = +1 VP`) and contrasting User's Line vs. Minimax Line.
   - **Tactical Execution & Misplay Diagnosis:** Assign standardized error codes (`POS-01`–`POS-03`, `TGT-01`–`TGT-03`, `MEC-01`–`MEC-02`, `SPD-01`–`SPD-02`), classify the root cognitive trap (`Tunnel_Vision`, `Greed`, `Autopilot`, `Tilt`, `Format_Divergence`), and dictate the deterministic imperative fix.
   - **Team Evolution & Commentary:** Formulate concise, actionable roster improvements (SP spread optimizations, item swaps, tech moves).
4. **Direct CSV Telemetry Ingestion**:
   - Instead of printing external webhook URLs, log all telemetry directly into the workspace CSVs via [`engine/telemetry.py`](../../engine/telemetry.py):
     - **Personal Matches (`Txx`):** Run `python engine/telemetry.py --mode personal --payload <json>` to automatically append the match to `data/Raw_Matches.csv` and log the cognitive trap row to `data/Playstyle_Diagnostics.csv`.
     - **Scouted Matches (`STxx` / Third-Party):** Run `python engine/telemetry.py --mode scouted --payload <json>` to append directly to `data/Scouted_Raw_Matches.csv`.
     - **Damage Calculations:** Run `python engine/telemetry.py --mode calc --payload <json>` to append newly computed damage rows directly to `data/Damage_Calculations.csv`.
   - Confirm the logged `Match_ID` and updated CSV files at the bottom of the breakdown.
