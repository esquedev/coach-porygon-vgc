---
name: flashcards
description: >-
  Use this skill when the user requests live practice, 45-second turn scenarios, interactive board
  sparring, or mechanical flashcards (Interactive Board Sparring & Reflex Conditioning).
---

# Flashcards: Interactive Board Sparring & Reflex Conditioning

Condition the user's decision-making under tournament clock pressure using deterministic simulation, game-theoretic strategy pruning, and multi-turn Minimax lookahead.

## Execution Workflow

1. **The 45-Second Reflex Flashcards (Board Sparring)**:
   - **Strict Format Grounding:** Every opposing Pokémon, item, ability, and move in a sparring scenario MUST be 100% legal in Regulation M-C (`data/MC_Available_Pokemon.csv`, `data/Regulation_MC_Items.csv`, and `data/pokedex_cache.json`). Scenarios can be drawn from `data/Flashcard_Scenarios.csv` or dynamically synthesized from tournament archetypes (Rain, Sun, Trick Room, Sand, Hyper Offense).
   - Present a high-friction mid-game board state:
     - Active slots (`p1a`, `p1b` vs `p2a`, `p2b`) with exact HP%, active stat boosts, and revealed items/moves.
     - Active field counters (Weather turns remaining, Terrain, Tailwind, Light Screen/Reflect, Trick Room).
   - Formulate **4 Categorized Decision Options**:
     - `[A]` **Minimax Optimal Line:** Maximizes guaranteed minimum board equity across all opponent counter-plays.
     - `[B]` **Strictly Dominated / Hope Chess:** Mathematically or positionally inferior line that gambles on opponent misplays.
     - `[C]` **Greed / Overkill:** Over-extending for redundant damage, setup, or KOs while conceding tempo or board control.
     - `[D]` **Passive / Tempo Loss:** Submissive Protect or unshielded switch that bleeds positional equity and surrenders momentum.
   - Demand explicit double-slot inputs (moves + target slots, or switches) within a simulated 45-second clock.

2. **Deterministic Turn Execution & 2-to-3 Turn Lookahead ($T_N \to T_{N+1} \to T_{N+2}$)**:
   - When the user submits their double-slot decision, construct the state and choices JSON and execute [`engine/turn_simulator.py`](../../../engine/turn_simulator.py).
   - Evaluate the board state turn-by-turn across 2 to 3 turns:
     - **Turn $N$ Resolution:** Compute exact Showdown damage rolls, instantaneous Mega speed recalculations, and resulting slot HP%.
     - **Turn $N+1$ Projection:** Feed `next_state` into the simulator. Evaluate field counter decrements (e.g., Tailwind expiry, Weather changes), status ticks, and positional initiative.
     - **Turn $N+2$ Trajectory:** Project the resulting end-game state (e.g., checkmate vs. positional recovery) under optimal play.
   - If the user selected a suboptimal line (`[B]`, `[C]`, or `[D]`), assign the standardized mistake taxonomy error code (`POS-01`–`POS-03`, `TGT-01`–`TGT-03`, `MEC-01`–`MEC-02`, `SPD-01`–`SPD-02`) and its cognitive driver (`Tunnel_Vision`, `Greed`, `Autopilot`, `Tilt`, `Format_Divergence`).

3. **Reflex Flashcards**:
   - Deliver rapid-fire benchmarks covering effective speed thresholds under Tailwind/Weather/Mega Evolution, survival cutoffs, and Regulation M-C item/ability mechanics.

---

## First-Proof Worked Example

```markdown
### [45-SECOND REFLEX FLASHCARD | TURN 4]
- Field: Tailwind (User, 1 turn left) | Sun active (Opponent, 2 turns left)
- User (p1): Archaludon (68% HP, Stamina +1 Def) | Pelipper (42% HP)
- Opponent (p2): Mega Charizard Y (100% HP) | Torkoal (55% HP)

Select double-slot action:
[A] Archaludon Electro Shot (p2a) + Pelipper Wide Guard (Minimax Optimal)
[B] Archaludon Protect + Pelipper Weather Ball into Charizard (Strictly Dominated / Hope Chess)
[C] Archaludon Body Press (p2b) + Pelipper Hurricane (p2a) (Greed / Overkill)
[D] Archaludon Protect + Pelipper switch to backline (Passive / Tempo Loss)

---
### Turn-by-Turn Simulator Evaluation (engine/turn_simulator.py)

#### Turn 4 Resolution:
- Pelipper executes Wide Guard (Priority +3).
- Mega Charizard Y attempts Heat Wave -> Blocked by Wide Guard!
- Torkoal uses Earth Power into Archaludon -> Deals 38% HP (Archaludon at 30% HP, Stamina triggers: +2 Def).
- Archaludon fires Electro Shot (Rain/Charge) into Mega Charizard Y -> Deals 104% HP -> KO! (+3 VP Mega KO).

#### Turn 5 Projection (T_N+1):
- Tailwind peters out. Opponent sends in backline Venusaur (Sun active).
- Board Equity: User holds 2 active slots (Archaludon 30% HP with +2 Def, Pelipper 42% HP) vs Torkoal (55% HP) and Venusaur.
- Pelipper outspeeds Torkoal; Archaludon threatens Flash Cannon into Venusaur. Guaranteed tempo advantage.

#### Turn 6 Checkmate Trajectory (T_N+2):
- Sun expires. Venusaur loses Chlorophyll speed bonus; User cleanly eliminates Torkoal and closes the match.

Optimal Verdict: Option [A] secured the game. Options [B], [C], and [D] result in Pelipper fainting to Heat Wave, forfeiting weather reset and handing opponent a +4 VP swing.
```
