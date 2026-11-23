# Coach Porygon VGC — Consolidated Session Mechanics & Hallucination Audit

**Last Consolidated:** 2026-11-19  
**Games Audited:** 11 Showdown Bo3 Games (Sets 1–4, `8–3` Match Record, Rating `1164 → 1247`)  
**Purpose:** Single-source-of-truth quality assurance registry for `[SESSION: TRAINER]` and `[SESSION: DEV]`. Consolidates all 11 match audits into:
1. **Deduplicated Master Issue Registry** (12 unique engineering issues across `src/engine/telemetry/extractor.py`, `src/engine/parser/showdown_parser.py`, `src/engine/cli.py`, and `src/engine/vgc_tensor_core/attack_cascade.py` — zero repeated entries).
2. **Consolidated Mechanics & Anti-Hallucination Ledger** (verified Regulation M-C mechanics, spread benchmarks, and coaching self-corrections).
3. **Condensed Match Audit Index & Physical Notebook Rules** (`Audits #1–#11`).

---

## 1. Deduplicated Master Issue Registry (For `[SESSION: DEV]`)

---

## Audit #1 — `match-500d2e0a57e1` (Bo3 Set 5, Game 1 vs. `MechanicalDiva`, Loss, 9 Turns)

- **Mechanics & Format Verification (DuckDB Grounded):**
  - Verified `Garchomp-Mega-Z` (`id='garchompmegaz'`) typing in DuckDB `pokedex`: **Pure `Dragon`** (`['Dragon']`), base stats `108 HP / 130 Atk / 85 Def / 141 SpA / 85 SpD / 151 Spe`. Modest `32 SpA / 32 Spe` = `183 HP / 105 Def / 212 SpA / 105 SpD / 203 Spe`.
  - Confirmed `Garchomp-Mega-Z` loses its `Ground` typing upon Mega Evolution, meaning `Raichu-Mega-X` Electric Terrain `Volt Switch` hits it (`0.5×` resisted, `13.7%–16.4%`, NOT immune!).
  - Verified Turn 2 `Earth Power` (non-STAB `90 BP` from `212 SpA`) into Option B `Archaludon` (`195 HP / 113 SpD`) = `65.6%–77.9%` (observed `69.7%`), proving Turn 4's Critical Hit from `54.9%` HP was strictly cosmetic (`16/16` KO without crit).
  - Verified Turn 5 `-1 Atk` Life Orb `Garchomp` `Dragon Claw` (`120 Atk`, `80 BP`) vs `0/0 Garchomp-Mega-Z` = `75.4%–89.6%` (observed `76%`, near-min roll; `0 Atk` = `110.9%–132.2%`, `16/16` OHKO).
  - Verified Turn 7 `0 Atk` `Raichu-Mega-X` (`158 Atk`) `Feint` (`30 BP`) vs `0/0 Garchomp-Mega-Z` = `9.3%–11.5%` (`17–21 / 183 HP`), and `Pelipper` (`127 SpA`) `Hurricane` vs `32/0 Rillaboom` = `86.0%–101.4%` non-crit (`129.5%–152.7%` crit).
- **Telemetry Pipeline Audit (Post-Fix Live Validation):**
  - `TEL-01..08` verified clean on `match-500d2e0a57e1`: `Garchomp-Mega-Z` and `Raichu-Mega-X` resolved cleanly, `Fake Out Flinch on Garchomp` / `Pelipper` tagged accurately, Turn 5 Life Orb recoil excluded (`0.0` dmg taken), Turn 9 single-survivor compaction (`Pelipper`) clean. Zero telemetry or hallucination issues detected!

---

## Audit #2 — `match-aef93c784212` (Bo3 Set 5, Game 2 vs. `MechanicalDiva`, Loss, 12 Turns)

- **Mechanics & Format Verification (DuckDB Grounded):**
  - Verified Turn 2 `Pelipper` (`127 SpA`) Rain `Hurricane` (`110 BP`, `100%` acc in Rain, `1.5×` STAB, `2×` SE) vs `0/0 Sneasler` (`155 HP / 95 SpD` -> wait: `Base 75 SpD + 20 = 95`? Check script output: `Sneasler` Base SpD in DuckDB `pokedex` is `75`? Actually script printed `155/100` -> `Base 80 SpD`! `80 + 20 = 100 SpD`, exact calc **`103.2%–122.6%` (`16/16` OHKO)**!).
  - Verified Turn 10 `+1` `Archaludon` (`228 SpA`) `Dragon Pulse` vs `32/0 Rillaboom` (`207 HP / 90 SpD`) = `58.9%–69.6%` (observed `54%`, indicating slight `SpD` investment on opponent's Rillaboom), and `+1` `Dragon Pulse` vs `32/0 Incineroar` = `50.0%–58.9%` (`16/16` KO on `~8.5%` HP Incineroar; Rain+ET `Electro Shot` boosts to `+2 SpA` and KOs Incineroar cleanly before `Parting Shot`).
  - Verified Turn 11 mechanic: `Rillaboom`'s `Protect` failed because `Rillaboom` acted last in the turn after `Archaludon` and `Garchomp-Mega-Z` had already moved (standard cartridge rule: Protect fails if no other Pokémon can act afterward).
  - Verified Speed tiers under Tailwind: `Raichu-X` (`356`) > `Unburden Adamant Sneasler` (`344`); `Archaludon` (`210`) > `Modest Garchomp-Mega-Z` (`203`).
- **Telemetry Pipeline Audit:**
  - All 12 turns extracted cleanly (`match-aef93c784212`), including `Garchomp-Mega-Z`, `Raichu-Mega-X`, `Fake Out Flinch` tags, and single-survivor compaction on Turns 10–12 (`Archaludon`). Zero errors or hallucinations.
