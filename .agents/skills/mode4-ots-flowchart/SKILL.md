---
name: mode4-ots-flowchart
description: >-
  Use this skill when the user submits an opponent's 6-Pokemon Open Team Sheet (OTS) prior to a Bo3
  Swiss or bracket match (Mode 4: Open Team Sheet Swiss Flowcharting).
---

# Mode 4: Open Team Sheet (OTS) Swiss Flowcharting

Deliver a standalone, pre-match Bo3 game plan formatted for rapid memorization before mobile devices are stored away. Eliminate conversational padding.

## Execution Workflow

1. **Roster & Archetype Resolution**:
   - Cross-reference the user's active prototype (`data/Teams.csv`) and the opponent's 6-Pokémon sheet against `data/Scouted_Teams.csv` using `python scouts/munchstats_scraper.py --lookup ...`.
   - Compute exact Level 50 speed stats via [`engine/sp_calculator.py`](../../engine/sp_calculator.py).
2. **Mandatory 5-Part Dossier**:
   1. **Speed Tier Hierarchy:** Complete sorted ranking of all 12 Pokémon across both rosters by effective speed (including instantaneous post-Mega speed tiers and Tailwind/Weather modifiers).
   2. **Opposing Forced Leads:** Identify their two highest-probability opening pairs and primary win conditions.
   3. **Game 1 Lead Blueprint:** Prescribe the user's starting pair, Turn 1 game plan (incorporating the 4-Step Pre-Turn Validation Checklist), and backline anchors.
   4. **Game 2/3 Adaptation Tree:** Map explicit reactive adjustments (e.g., *"If Opponent leads Lead A+B in Game 2 -> Pivot to Mode C"*).
   5. **Trap Tech Audit:** Flag non-standard items, damage reduction berries (`Chople`, `Shuca`, `Occa`), unexpected `Wide Guard`, or speed-creep investments.
