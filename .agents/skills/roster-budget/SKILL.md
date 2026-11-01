---
name: roster-budget
description: >-
  Use this skill when the user requests roster construction, stat spread optimization, or 66-SP
  budgeting (Mode 2: Teambuilding & Roster Engineering).
---

# Mode 2: Teambuilding & Roster Engineering (66-SP Deterministic Budgeting)

Deliver deterministic 66-SP roster engineering with zero conversational padding.

---

## 0. Governance, Role Alignment & Validation Matrix
- **Owner Role:** Roster & Stat Engineer (`Role: RosterEngineer`)
- **Domain Layer:** Domain Core (66-SP Allocation & Format Legality)
- **Permissions:** Read `data/Regulation_MC_Items.csv`, `data/MC_Available_Pokemon.csv`; execute `engine/sp_calculator.py`, `engine/validate_roster.py`, and `engine/register_team.py`; write (register) to `data/Teams.csv` and `data/trainer_profile.json`. Codebase infrastructure is locked.
- **Minimum Viable Context (MVC):** `Regulation_MC_Items.csv`, Level 50 SP formula, typing/STAB matrix, Item Clause. Exclude: Replay battle histories, MunchStats Swiss standings, frontend UI code.
- **Deterministic Validation Criteria:**
  - Mandatory arithmetic verification string output: `[HP] HP + [Atk] Atk + ... = 66 SP`.
  - All 6 slots verified via `engine/validate_roster.py` returning `[PASS - 100% LEGAL]`.
  - Exact sequential Team ID assignment (`Txx`).

---

## Execution Workflow

1. **Legacy Purge Guardrail**:
   - Zero tolerance for Gen 1–9 legacy mechanics. Never mention `Effort Values`, `EVs`, `Individual Values`, `IVs`, or `Hyper Training` in coaching prose.
2. **Item Legality & Item Clause Verification**:
   - Every proposed or equipped hold item must be verified against `data/Regulation_MC_Items.csv` (via `data/Regulation_MC_Items.csv` or `engine/validate_roster.py`).
   - If an item does not exist in `Regulation_MC_Items.csv`, it is not legal in Regulation M-C. Never propose unverified hold items.
   - Enforce Item Clause across all 6 slots (no duplicate items across the team).
3. **Species Typing & STAB Grounding**:
   - Retrieve exact official types directly from `data/MC_Available_Pokemon.csv` or `engine/validate_roster.py`.
   - Never assume or invent secondary typings (e.g., `Mega Raichu X` is mono-`Electric`).
   - A damaging move receives Same Type Attack Bonus (STAB, 1.5x) *only* if its type matches the Pokémon's verified typing.
   - Damaging moves of non-matching types must be explicitly labeled as "Non-STAB Coverage (1.0x)".
4. **Deterministic Pre-Flight Roster Validation**:
   - Before presenting any full 6-mon roster or Showdown export, run [`engine/validate_roster.py`](../../../engine/validate_roster.py):
     ```powershell
     python engine/validate_roster.py --paste "<Showdown Paste>"
     ```
   - All 6 slots must return `[PASS - 100% LEGAL]` for items, Item Clause, typings, and SP totals.
5. **Deterministic 66-SP Validation & Mandatory Verification String**:
   - Maximum `32 SP` per single stat; total across all 6 stats must equal exactly `66 SP`. Assign `0` to uninvested stats.
   - Apply `+10%` / `-10%` Stat Alignments *after* the 66-SP base budget is confirmed, strictly rounding down (`floor`).
   - Always output the explicit arithmetic verification string before presenting the final stat spread:
     `[HP SP] HP + [Atk SP] Atk + [Def SP] Def + [SpA SP] SpA + [SpD SP] SpD + [Spe SP] Spe = 66 SP`
6. **Survival & Damage Benchmarks**:
   - Verify key survival cutoffs and KO thresholds using [`engine/turn_simulator.py`](../../../engine/turn_simulator.py) or `data/Damage_Calculations.csv`. Flag any newly computed unindexed calcs as `[Official VGC Calc]`.

## 7. First-Proof Worked Example
```
Input: Build a bulky offensive Mega Feraligatr spread for Regulation M-C.
Verification String: 22 HP + 28 Atk + 0 Def + 0 SpA + 0 SpD + 16 Spe = 66 SP

Mega Feraligatr @ Feraligatrite
Ability: Dragonize
Level: 50
Alignment: +Atk, -SpA (Adamant)
SP Allocation: 22 HP / 28 Atk / 0 Def / 0 SpA / 0 SpD / 16 Spe
Stats: 182 HP / 209 Atk / 140 Def / 89 SpA / 103 SpD / 118 Spe
- Liquidation (STAB 1.5x)
- Outrage (STAB 1.5x via Dragonize)
- Ice Spinner (Non-STAB Coverage 1.0x)
- Protect

Benchmark [Official VGC Calc]: 28+ Atk Dragonize Outrage vs. 32 HP / 12 Def Garchomp: 100% OHKO (216-258 dmg).
```
