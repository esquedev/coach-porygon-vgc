---
name: mode3-crucible-spar
description: >-
  Use this skill when the user requests live practice, 45-second turn scenarios, interactive board
  sparring, or mechanical flashcards (Mode 3: Interactive Board Sparring & Reflex Conditioning).
---

# Mode 3: Interactive Board Sparring & Reflex Conditioning

Condition the user's decision-making under tournament clock pressure using deterministic simulation.

## Execution Workflow

1. **The 45-Second Crucible**:
   - Present a high-friction mid-game board state:
     - Active slots (`p1a`, `p1b` vs `p2a`, `p2b`) with exact HP%, active stat boosts, and revealed items/moves.
     - Active field counters (Weather turns remaining, Terrain, Tailwind, Light Screen/Reflect, Trick Room).
   - Demand explicit double-slot inputs (moves + target slots, or switches) within a simulated 45-second clock.
2. **Deterministic Turn Execution & Minimax Evaluation**:
   - When the user submits their double-slot decision, construct the state and choices JSON and run [`engine/turn_simulator.py`](../../engine/turn_simulator.py) to produce the exact Showdown spectator replay log.
   - Audit the user's input against the opponent's Level 1 and Minimax counter-plays.
   - Flag "Hope Chess" (relying on opponent mistakes) vs. deterministic trades, and assign standardized mistake codes (`POS-xx`, `TGT-xx`, `MEC-xx`, `SPD-xx`) if a leak occurred.
3. **Reflex Flashcards**:
   - When requested, deliver rapid-fire benchmarks covering effective speed thresholds under Tailwind/Weather/Mega Evolution, survival cutoffs, and Regulation M-C item/ability mechanics.
