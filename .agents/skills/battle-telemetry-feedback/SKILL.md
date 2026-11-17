---
name: battle-telemetry-feedback
description: >-
  Use this skill when the user provides a Pokémon Showdown battle log or replay from practice or tournament play.
  Executes turn-by-turn telemetry extraction to CSV, runs game-theoretic turn post-mortems, and populates tactical
  comments into the telemetry suite to track player improvement.
---

# Battle Telemetry & Tactical Feedback Runbook

This skill automates the full post-match coaching pipeline:
1. Extracting turn-by-turn cartridge telemetry into `data/telemetry/battles_telemetry.csv`.
2. Running the game-theoretic turn advisor (`engine.cli`) to evaluate Nash equilibrium lines, regret, and downside risk ($CVaR_{0.10}$).
3. Injecting structured coaching comments with standardized tags into the CSV's `comment` column:
   - `[LEAD_EVAL]`: Turn 1 bring assessment against opponent's preview.
   - `[MEGA_DECISION]`: Timing and species selection for Mega Evolution (Priority +5.5).
   - `[SPEED_INITIATIVE]`: Weather speed doubling, Tailwind, Unburden, or Trick Room control.
   - `[ITEM_TRIGGER]`: White Herb, Focus Sash, Sitrus Berry, or Leftovers activation.
   - `[WEATHER_TERRAIN]`: Sun vs. Rain control, Electric Terrain deployment.
   - `[VARIANCE_AUDIT]`: Distinguishing cartridge RNG (crits, flinches, low damage rolls) from misplays.
   - `[NASH_REGRET]`: Regret calculation on lines deviating from the risk-resilient Nash equilibrium.
4. Auto-syncing the interactive Team Preview Playbook (`reports/char_y_v3_playbook.html`) and markdown cheatsheet.
5. Delivering an executive post-mortem to the player with concrete tournament takeaways.

---

## Step-by-Step Execution Workflow

### Step 1: Dump Raw Telemetry to CSV
When a raw Showdown chat log is provided (either as text or a saved file), immediately dump the turn records:

```bash
python3 scripts/dump_battle_telemetry.py \
    --log path/to/match.log \
    --paste data/teams/char_y_v3.txt \
    --output data/telemetry/battles_telemetry.csv
```

*Note: This generates or appends records to `data/telemetry/battles_telemetry.csv`, automatically recording the `match_id`, active Pokémon slots, moves executed, damage percentages, faints, field conditions, tactical triggers, and variance events. Timestamps are strictly grounded in the local machine system time (`datetime.now()`) to align with player session clocks rather than remote server UTC.*

---

### Step 2: Run Game-Theoretic Turn Advisor
Run the turn advisor CLI against the battle log to detect missed opportunities and evaluate risk floors:

```bash
python3 -m engine.cli \
    --paste data/teams/char_y_v3.txt \
    --log path/to/match.log \
    --verbosity coach
```

---

### Step 3: Populate Tactical Comments into Telemetry CSV
Using Python and `engine.telemetry.batch_update_comments`, populate the `comment` column for critical turns in `data/telemetry/battles_telemetry.csv` using standardized tags:

```python
from engine.telemetry import batch_update_comments

comments = {
    1: "[LEAD_EVAL] Fake Out stopped Tailwind setup. Solid tempo control against Kyogre + Tornadus.",
    2: "[VARIANCE_AUDIT] Opponent landed a 4.1% critical hit through screen.",
    3: "[MEGA_DECISION] Mega Evolved Charizard Y into Rain to reset Sun and secure OHKO with Weather Ball.",
    4: "[ITEM_TRIGGER] White Herb restored Intimidate drop, immediately activating Sneasler's Unburden.",
}

batch_update_comments(
    csv_path="data/telemetry/battles_telemetry.csv",
    match_id="<match_id>",
    comments_by_turn=comments,
)
```

---

### Step 4: Auto-Sync the Team Preview Playbook
After populating the turn comments in `data/telemetry/battles_telemetry.csv`, immediately refresh the interactive Team Preview Playbook so the new match record, empirical lead win rates, and coaching notes appear in the live report:

```bash
PYTHONPATH=src:src/engine python3 scripts/generate_team_preview_playbook.py \
    --paste data/teams/char_y_v3.txt \
    --telemetry data/telemetry/battles_telemetry.csv \
    --out reports/char_y_v3_playbook.html \
    --cheatsheet reports/char_y_v3_cheatsheet.md
```

---

### Step 5: Deliver the Coach Post-Mortem in Chat
Present a clean, high-impact summary to the user:
1. **Match Result & Key Turning Point:** The single turn where game equity was won or lost.
2. **Variance vs. Decision Audit:** Did the game come down to bad luck or a tactical leak?
3. **Turn-by-Turn Formatting Mandate:** Always format turn-by-turn match audits and telemetry breakdowns using **native GitHub Flavored Markdown (GFM) tables** (`| Turn | Board State | Actions Executed | Tactical & Process Audit |`) with responsive cell-wrapping, or vertical Turn Cards. **Strictly never use fixed-width ASCII / Unicode box-drawing tables (`┌─┬─┐`) inside code blocks**, which wrap onto subsequent lines and break horizontal alignment on narrow or responsive client windows.
4. **Actionable Takeaway for LAIC:** What one specific habit or rule to remember for the next match.

