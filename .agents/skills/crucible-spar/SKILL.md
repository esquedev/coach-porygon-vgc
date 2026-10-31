---
name: crucible-spar
description: >-
  Use this skill when the user requests live practice, 45-second turn scenarios, interactive board
  sparring, or mechanical flashcards (Mode 3: Interactive Board Sparring & Reflex Conditioning).
---

# Mode 3: Interactive Board Sparring & Reflex Conditioning

Condition the user's decision-making under tournament clock pressure using deterministic simulation.

## Execution Workflow

1. **The 45-Second Reflex Flashcards (Board Sparring)**:
   - **Strict Format Grounding:** Every opposing Pokémon, item, ability, and move in a sparring scenario MUST be 100% legal in Regulation M-C (`data/MC_Available_Pokemon.csv`, `data/Regulation_MC_Items.csv`, and `data/pokedex_cache.json`). Opposing teams may be dynamically devised from common competitive archetypes (Rain, Sun, Trick Room, Sand, Hyper Offense) or inspired by tournament cores, provided all items and learnsets strictly comply with the format lock.
   - Present a high-friction mid-game board state:
     - Active slots (`p1a`, `p1b` vs `p2a`, `p2b`) with exact HP%, active stat boosts, and revealed items/moves.
     - Active field counters (Weather turns remaining, Terrain, Tailwind, Light Screen/Reflect, Trick Room).
   - Demand explicit double-slot inputs (moves + target slots, or switches) within a simulated 45-second clock.
2. **Deterministic Turn Execution & Minimax Evaluation**:
   - When the user submits their double-slot decision, construct the state and choices JSON and run [`engine/turn_simulator.py`](../../../engine/turn_simulator.py) to produce the exact Showdown spectator replay log.
   - Audit the user's input against the opponent's Level 1 and Minimax counter-plays.
   - Flag "Hope Chess" (relying on opponent mistakes) vs. deterministic trades, and assign standardized mistake codes (`POS-xx`, `TGT-xx`, `MEC-xx`, `SPD-xx`) if a leak occurred.
3. **Reflex Flashcards**:
   - When requested, deliver rapid-fire benchmarks covering effective speed thresholds under Tailwind/Weather/Mega Evolution, survival cutoffs, and Regulation M-C item/ability mechanics.

## 4. First-Proof Worked Example
```markdown
### [45-SECOND REFLEX FLASHCARD | TURN 4]
- Field: Tailwind (User, 1 turn left) | Sun active (Opponent, 2 turns left)
- User (p1): Archaludon (68% HP, Stamina +1 Def) | Pelipper (42% HP)
- Opponent (p2): Mega Charizard Y (100% HP) | Torkoal (55% HP)

Select double-slot action:
[A] Archaludon Protect + Pelipper Weather Ball into Charizard
[B] Archaludon Electro Shot (p2a) + Pelipper Wide Guard (Minimax optimal)
[C] Archaludon Body Press (p2b) + Pelipper Hurricane (p2a)
[D] Archaludon Protect + Pelipper switch to backline

Evaluated via: python engine/turn_simulator.py
Optimal Line: [B] Wide Guard nullifies opposing Heat Wave spread; Electro Shot secures +3 VP Mega KO.
```
