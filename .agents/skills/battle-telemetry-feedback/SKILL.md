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
2. Running the Bo1/Bo3 OTS 66-SP & Tensor Core CLI (`scripts/coach_bo3.py`) or Replay Coach Studio (`apps/replay_coach/`) to solve exact opponent 66-SP bounds and evaluate Nash equilibrium lines, regret, and downside risk ($CVaR_{0.10}$).
3. Injecting structured coaching comments with standardized tags into the CSV's `comment` column:
   - `[LEAD_EVAL]`: Turn 1 bring assessment against opponent's preview.
   - `[MEGA_DECISION]`: Timing and species selection for Mega Evolution (Priority +5.5).
   - `[SPEED_INITIATIVE]`: Weather speed doubling, Tailwind, Unburden, or Trick Room control.
   - `[ITEM_TRIGGER]`: White Herb, Focus Sash, Sitrus Berry, or Leftovers activation.
   - `[WEATHER_TERRAIN]`: Sun vs. Rain control, Electric Terrain deployment.
   - `[VARIANCE_AUDIT]`: Distinguishing cartridge RNG (crits, flinches, low damage rolls) from misplays.
   - `[NASH_REGRET]`: Regret calculation on lines deviating from the risk-resilient Nash equilibrium.
4. Delivering an executive post-mortem to the player with concrete tournament takeaways.

---

## Step-by-Step Execution Workflow

### Step 1: Dump Raw Telemetry to CSV
When a raw Showdown chat log is provided (either as text or a saved file), immediately dump the turn records:

```bash
python3 scripts/dump_battle_telemetry.py \
    --log path/to/match.log \
    --paste data/teams/<team>.txt \
    --output data/telemetry/battles_telemetry.csv
```

*Note: This generates or appends records to `data/telemetry/battles_telemetry.csv`, automatically recording the `match_id`, active Pokémon slots, moves executed, damage percentages, faints, field conditions, tactical triggers, and variance events. Timestamps are strictly grounded in the local machine system time (`datetime.now()`) to align with player session clocks rather than remote server UTC.*

---

### Step 2: Run Bo1/Bo3 OTS 66-SP & Tensor Core Audit
Run the headless v2 coaching CLI against 1 to 3 Showdown replays (auto-extracts opponent OTS from `|showteam|`, or pass `--opp-ots` for Bo1 replays without `|showteam|`):

```bash
PYTHONPATH=src:. python3 scripts/coach_bo3.py \
    --team data/teams/<team>.txt \
    --replays path/to/g1.html [path/to/g2.html path/to/g3.html] \
    --rng-samples 128 \
    --lang en \
    --style vgc \
    --export-csv <team>
```

*(Pass `--two-ply` to enable Selective 2-Ply Lookahead on the Strict-IEDS core, or `--no-sim` to only solve and print the opponent's clamped 66-SP bounds.)*

---

### Step 3: Populate Tactical Comments into Telemetry CSV
Using Python and `engine.telemetry.batch_update_comments`, populate the `comment` column for critical turns in `data/telemetry/battles_telemetry.csv` using standardized tags:

```python
from engine.telemetry import batch_update_comments

comments = {
    1: "[LEAD_EVAL] Fake Out stopped Tailwind setup. Solid tempo control against Whimsicott + Charizard-Mega-Y.",
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

### Step 4: Deliver the Coach Post-Mortem in Chat
Present a clean, high-impact summary to the user:
1. **Match Result & Key Turning Point:** The single turn where game equity was won or lost.
2. **Variance vs. Decision Audit:** Did the game come down to bad luck or a tactical leak?
3. **Turn-by-Turn Formatting Mandate:** Always format turn-by-turn match audits and telemetry breakdowns using **native GitHub Flavored Markdown (GFM) tables** (`| Turn | Board State | Actions Executed | Tactical & Process Audit |`) with responsive cell-wrapping, or vertical Turn Cards. **Strictly never use fixed-width ASCII / Unicode box-drawing tables (`┌─┬─┐`) inside code blocks**, which wrap onto subsequent lines and break horizontal alignment on narrow or responsive client windows.
4. **Actionable Takeaway for Tournament Play:** What one specific habit or rule to remember for the next match.

