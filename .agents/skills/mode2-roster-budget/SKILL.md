---
name: mode2-roster-budget
description: >-
  Use this skill when the user requests roster construction, stat spread optimization, or 66-SP
  budgeting (Mode 2: Teambuilding & Roster Engineering).
---

# Mode 2: Teambuilding & Roster Engineering (66-SP Deterministic Budgeting)

Deliver deterministic 66-SP roster engineering with zero conversational padding.

## Execution Workflow

1. **Legacy Purge Guardrail**:
   - Zero tolerance for Gen 1–9 legacy mechanics. Never mention `Effort Values`, `EVs`, `Individual Values`, `IVs`, or `Hyper Training` in coaching prose.
2. **Deterministic 66-SP Validation**:
   - Before proposing any final stat spread, run [`engine/sp_calculator.py`](../../engine/sp_calculator.py):
     ```powershell
     python engine/sp_calculator.py --species "<Species>" --nature "<Nature>" --hp <HP> --atk <Atk> --def <Def> --spa <SpA> --spd <SpD> --spe <Spe>
     ```
   - Maximum `32 SP` per single stat; total across all 6 stats must equal exactly `66 SP`. Assign `0` to uninvested stats.
   - Apply `+10%` / `-10%` Stat Alignments *after* the 66-SP base budget is confirmed, strictly rounding down (`floor`).
3. **Mandatory Verification String**:
   - Always output the explicit arithmetic verification string before presenting the final stat spread:
     `[HP SP] + [Atk SP] + [Def SP] + [SpA SP] + [SpD SP] + [Spe SP] = 66 SP`
4. **Survival & Damage Benchmarks**:
   - Verify key survival cutoffs and KO thresholds using [`engine/turn_simulator.py`](../../engine/turn_simulator.py) or `data/Damage_Calculations.csv`. Flag any newly computed unindexed calcs as `[Gemini Generated Calc]`.
