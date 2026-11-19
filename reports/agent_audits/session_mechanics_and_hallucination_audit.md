# Coach Porygon VGC — Consolidated Session Mechanics & Hallucination Audit

**Last Consolidated:** 2026-11-19  
**Games Audited:** 11 Showdown Bo3 Games (Sets 1–4, `8–3` Match Record, Rating `1164 → 1247`)  
**Purpose:** Single-source-of-truth quality assurance registry for `[SESSION: TRAINER]` and `[SESSION: DEV]`. Consolidates all 11 match audits into:
1. **Deduplicated Master Issue Registry** (12 unique engineering issues across `src/engine/telemetry/extractor.py`, `src/engine/parser/showdown_parser.py`, `src/engine/cli.py`, and `src/engine/vgc_tensor_core/attack_cascade.py` — zero repeated entries).
2. **Consolidated Mechanics & Anti-Hallucination Ledger** (verified Regulation M-C mechanics, spread benchmarks, and coaching self-corrections).
3. **Condensed Match Audit Index & Physical Notebook Rules** (`Audits #1–#11`).

---

## 1. Deduplicated Master Issue Registry (For `[SESSION: DEV]`)

### Category A — Active-Slot, Nickname & Switch State Machine (`extractor.py` / `showdown_parser.py`)

#### `TEL-01`: Auto-POV Trainer Inference Fails When POV Player Is Listed 2nd
- **Location:** [showdown_parser.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/parser/showdown_parser.py#L421-L436)
- **Observed In:** Audit #6 (`match-6ceee1c2cb33`)
- **Root Cause:** When `pov_trainer` is omitted, `parse_showdown_chat_log` unconditionally assigns `trainer_1 = detected_trainers[0]`. Whenever a Showdown log header prints `Battle started between <opponent> and <user>!`, `trainer_1` and `trainer_2` are inverted, merging `Go! <Pokemon>!` lines into the opponent's team and leaving `trainer_2` active slots blank.
- **Required Fix:** When `pov_trainer` is omitted, infer `trainer_1` deterministically from `Go! <Pokemon>!` perspective lines (which Showdown only emits for the local POV player) and/or by matching `user_team_paste` species against `<Trainer>'s team:` preview lines.

#### `TEL-02`: Nickname, Mega-Forme Alias & Pivot/Double-Faint Slot Resolution Failure
- **Location:** [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L158-L175), [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L250-L304), [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L334-L344)
- **Observed In:** Audits #3 (`match-0b3b0d85b0e2`), #5 (`match-6b7ef1306355`), #7 (`match-1c839dd0c258`), #8 (`match-62f3552c6a05`), #9 (`match-6afcaec2ec66`), #10 (`match-382fe59c8ddc`), #11 (`match-8e3433f8b31c`)
- **Root Cause:** Four coupled defects in `extractor.py`'s active-slot tracker (`t1_active`, `t2_active`):
  1. **Nickname Loss:** `Go! Hazard (Charizard)!` strips the nickname and stores `"Charizard"`, so subsequent `"Hazard, come back!"` or `"Hazard fainted!"` fails `"Hazard" in t1_active` and falls back to `t1_active.pop(0)`, overwriting the partner's slot.
  2. **Base vs. Mega Forme Mismatch:** Sending out or Mega Evolving into `"Raichu-Mega-X"` / `"Charizard-Mega-Y"` stores the Mega string, whereas Showdown's faint/withdrawal line prints base species (`"The opposing Raichu fainted!"`), failing exact string lookup and popping Slot 0.
  3. **Pivot Move Switch-Outs Ignored:** Pivot lines (`"<Mon> went back to <Trainer>!"` from `Volt Switch`, `Parting Shot`, `U-turn`, `Flip Turn`, `Teleport`, `Shed Tail`, or `Red Card` / `Eject Button` / `Emergency Exit`) never set `last_withdrawn_t1` / `last_withdrawn_t2`, causing the incoming replacement to overwrite Slot 0 (even producing duplicate active slots like `Raichu, Raichu`).
  4. **Single-Scalar Withdrawal Buffer Breaks on Double Faints:** Storing a single `last_withdrawn_t1: Optional[str]` instead of a FIFO queue (`List[str]`) loses the first fainted slot when both active Pokémon faint on the same turn (`Venusaur fainted! Garchomp fainted!`).
- **Required Fix:** Track active slots as a 2-element list with a bidirectional nickname/base-species/Mega-species resolver and a FIFO queue of pending open slot indices (`pending_open_slots_t1`, `pending_open_slots_t2`) populated by `withdrew`, `come back!`, `went back to`, `fainted!`, `dragged out`, and `Eject Button` / `Red Card` events.

#### `TEL-03`: Fainted Pokémon Persists in Active Slot When Bench Is Empty
- **Location:** [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L334-L344)
- **Observed In:** Audits #1 (`match-39bebb6d24b0`), #4 (`match-ff756ea31166`), #11 (`match-8e3433f8b31c`)
- **Root Cause:** When a Pokémon faints in an endgame with no bench replacement left (`2v1` or `1v2`), `m_faint` only records `last_withdrawn_t* = fainted_mon` without clearing the slot. Because no `sent out` / `Go!` line follows, the fainted Pokémon remains listed as active for all remaining turns.
- **Required Fix:** Immediately clear the fainted Pokémon's slot (`""`) upon `fainted!` and push its slot index to `pending_open_slots_t*` so a replacement fills that exact index if sent out, or it remains empty (`""`) if no replacement exists.

---

### Category B — Weather, Terrain & Field Conditions Tracking (`extractor.py`)

#### `TEL-04`: `field_conditions` Applied Retroactively From End-of-Match State & Missing Hazards / Case Variants
- **Location:** [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L215-L249), [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L390-L406)
- **Observed In:** Audits #1 (`match-39bebb6d24b0`), #2 (`match-d047950d1a9f`), #10 (`match-382fe59c8ddc`)
- **Root Cause:**
  1. `t1_tailwind`, `t2_tailwind`, `trick_room`, `t1_screens`, and `t2_screens` are mutated during the line-parsing loop, but `conds` is constructed *after* the entire battle loop finishes (`lines 395–406`), stamping the final turn's state onto **every** turn (`Turn 1..N`).
  2. Case-sensitive `"The tailwind petered out"` misses Showdown's `"Your team's Tailwind petered out!"` and `"The opposing team's Tailwind petered out!"`, so `t1_tailwind` never resets to `False`.
  3. `Aurora Veil` and entry hazards (`Toxic Spikes` / `"poison spikes were scattered"`, `Stealth Rock`, `Spikes`, `Sticky Web`) are not tracked in `field_conditions`.
- **Required Fix:** Snapshot `field_conditions` per turn during the turn loop, match case-insensitive Tailwind expiration (`"tailwind petered out" in line.lower()`), and track `Aurora Veil` and entry hazards per side.

#### `TEL-05`: Missing Showdown Phrasings for `Electric Surge` Terrain & `Drought` Sun Expiration
- **Location:** [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L191-L213)
- **Observed In:** Audits #1 (`match-39bebb6d24b0`), #5 (`match-6b7ef1306355`)
- **Root Cause:**
  1. Showdown logs `"An electric current ran across the battlefield!"` when `Electric Surge` activates, whereas `extractor.py:202` only checks `"surged across the battlefield"`.
  2. Showdown logs `"The harsh sunlight faded."` when `Drought` expires, whereas `extractor.py:192` checks `"The sunlight faded"` (which fails because `"harsh"` sits between `"The"` and `"sunlight"`).
- **Required Fix:** Match `"electric current ran across"` / `"surged across"` for `Electric` terrain, and match `"sunlight faded"` (without `"The "` prefix) for Sun expiration.

#### `TEL-06`: End-of-Turn Faint-Replacement Weather/Terrain Overwrites Combat-Phase Weather/Terrain
- **Location:** [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L179-L213)
- **Observed In:** Audit #10 (`match-382fe59c8ddc` Turns 6–7)
- **Root Cause:** When a Pokémon faints during combat and its end-of-turn replacement triggers a weather/terrain ability (`Sand Stream`, `Drizzle`, `Drought`, `* Surge`) after all moves have executed, `entry["weather"] = cur_weather` overwrites the weather/terrain that was active during the turn's combat phase.
- **Required Fix:** Once `entry["faints"]` is non-empty (post-combat faint replacement phase) and moves have already executed on that turn, update `cur_weather` / `cur_terrain` for Turn `N+1` without overwriting Turn `N`'s combat-phase `entry["weather"]` / `entry["terrain"]` (or record `Sun -> Sand (EoT)`).

---

### Category C — Damage Attribution & Variance Classification (`extractor.py`)

#### `TEL-07`: Self-Inflicted / Friendly-Fire Damage Misattributed as Opponent Damage & Passive Chip Context
- **Location:** [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L319-L331)
- **Observed In:** Audits #1 (`match-39bebb6d24b0` Turns 6, 8), #5 (`match-6b7ef1306355` Turns 2–4)
- **Root Cause:** `m_dmg` credits all `(<Mon> lost X% of its health!)` lines to the opponent based solely on whether `"The opposing "` appears in the victim's name, ignoring whether the current move was self-inflicted (`Substitute`, `Clangorous Soul`, `Shed Tail`, `Curse`) or friendly-fire (`Raichu Feint -> partner Archaludon`).
- **Required Fix:** Track the active move context (`last_active_attacker`, `last_move_name`, `last_attacker_is_t2`); exclude self-cost moves (`Substitute`, `Clangorous Soul`, `Shed Tail`) and same-team friendly-fire from opponent `damage_dealt_to_trainer_*`.

#### `TEL-08`: Variance Classifier False Negatives (Spread Crits) & Deterministic False Positives (`Fake Out`, Semi-Invulnerable Dodges)
- **Location:** [extractor.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/telemetry/extractor.py#L346-L385)
- **Observed In:** Audits #2 (`match-d047950d1a9f` T7), #3 (`match-0b3b0d85b0e2` T1), #10 (`match-382fe59c8ddc` T6), #11 (`match-8e3433f8b31c` T1)
- **Root Cause:**
  1. *False Negative:* Spread crits print `"A critical hit on the opposing <Mon>!"` or `"A critical hit on <Mon>!"`, which fails `"A critical hit!" in line` (`"!"` is at the end of the target name).
  2. *False Positive (`Fake Out`):* `Fake Out` causes a `100%` deterministic flinch, yet `"flinched" in line` logs it as RNG variance `"Flinch on <Mon>"`.
  3. *False Positive (Semi-Invulnerable Dodge):* Two-turn semi-invulnerable moves (`Phantom Force`, `Shadow Force`, `Fly`, `Bounce`, `Dig`, `Dive`, `Sky Drop`) cause attacks to print `"avoided the attack!"`, which is deterministic rather than accuracy RNG `"Attack Missed"`.
  4. *Ambiguous Mirror Mega Tag:* `"Mega Evolution (<Species>)"` omits `trainer_1` / `trainer_2` ownership when both teams carry the same Mega species.
- **Required Fix:** Match `"A critical hit"` prefix; suppress `"Flinch on ..."` when the current move is `"Fake Out"`; track semi-invulnerable vanish states (`"vanished instantly!"`, `"flew up high!"`, `"dug a hole!"`, etc.) and suppress `"Attack Missed"` against vanished targets; prefix Mega Evolution tags or disambiguate mirror species.

---

### Category D — CLI, Tensor Engine & Environment (`cli.py`, `attack_cascade.py`, `.venv`)

#### `CLI-01`: `engine.cli` Evaluates Terminal Post-Match State on Completed Battle Logs
- **Location:** [cli.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/cli.py#L39-L166)
- **Observed In:** Audit #1 (`match-39bebb6d24b0`)
- **Root Cause:** Passing a finished battle log to `engine.cli` parses through the final faint/win line, leaving the losing side with `0` active Pokémon (`None, None`) and evaluating a meaningless post-match state.
- **Required Fix:** Add `--turn <N>` to `engine.cli` (and `parse_showdown_chat_log`) to slice/evaluate the board state at the start of Turn `N`, and automatically rewind to the final playable turn (`turns_played`) when `battle.winner` is present and `--turn` is omitted.

#### `ENG-01`: PyTorch CUDA VRAM Exhaustion on Multi-Turn / High-Hypothesis Runs (6 GB GPU)
- **Location:** [attack_cascade.py](file:///home/cyberpsycho/Desktop/Repos/coach-porygon-vgc/src/engine/vgc_tensor_core/attack_cascade.py#L311-L333)
- **Observed In:** Audit #1 (`match-39bebb6d24b0`)
- **Root Cause:** Allocating `[B1, B2, K, 8, 84]` tensor clones on CUDA across multiple turns or hypotheses in one process can exceed 5.67 GiB VRAM without cache cleanup or fallback.
- **Required Fix:** Wrap CUDA execution in `CoachTurnAdvisor` / `_execute_attack_cascade_torch` with `torch.cuda.empty_cache()` cleanup and graceful fallback (or batch chunking) on `torch.cuda.OutOfMemoryError`.

#### `SOL-01`: Single-Turn Evaluation Myopia on Intentional Win-Condition Preservation Sacrifices
- **Location:** `src/engine/solver/` & Coach Post-Mortem Protocol
- **Observed In:** Audit #2 (`match-d047950d1a9f` Turns 3 & 6)
- **Root Cause:** Single-turn state scoring penalizes sacrificing an unboosted active Pokémon (`Archaludon`) without recognizing that preserving the switched-out weather setter (`Drizzle Pelipper`) is mandatory to beat the opponent's back-line weather core (`Hippowdon + Sand Rush Houndstone`).

#### `ENV-01`: `.venv/bin/python3` Symlink Points to System Python 3.14 Instead of Python 3.12
- **Location:** `.venv/bin/python3`
- **Observed In:** Audit #1
- **Root Cause:** `.venv/bin/python` symlinks to `python3.12` (matching compiled `cpython-312` wheels in `.venv`), whereas `.venv/bin/python3` symlinks to `/usr/bin/python3` (`3.14`), causing `ModuleNotFoundError: No module named 'numpy._core._multiarray_umath'` when invoked via `python3`.

---

## 2. Consolidated Mechanics & Anti-Hallucination Ledger

All mechanics below were mathematically verified across Audits #1–#11 via `VGCDataRegistry` (DuckDB), `.agents/rules/champions_mechanics_compendium.md`, and Gen 9 fixed-point (`4096`-scale `pokeRound`) 16-roll enumeration:

1. **Level 50 Champions Stat Formulas (`66 SP` total, `≤ 32 SP` per stat, 31 IVs):**
   - $\text{HP} = \text{Base} + \text{SP} + 75$, $\quad \text{Stat} = \lfloor (\text{Base} + \text{SP} + 20) \times \text{NatureMult} \rfloor$.
2. **Verified `char_y_v4` Bulk & Offensive Benchmarks:**
   - **`Mega Charizard Y` (`Modest`, `22 HP / 19 Def / 3 SpA / 1 SpD / 21 Spe` → `175 / 111 / 117 / 200 / 136 / 141`):**
     - Survives `Adamant 32 Atk Sneasler` `4×` `Rock Tomb` (`93.7%` observed, `6.3%` remaining).
     - Survives `Jolly 32 Atk Excadrill` `4×` spread `Rock Slide` `16/16` times (`77.7%–91.4%`, `82.3%` observed).
     - Survives `Choice Scarf Adamant 32 Atk Garchomp` `4×` spread `Rock Slide` `16/16` times (`82.3%–98.3%`, `144–172 / 175 HP`).
   - **`Archaludon` (`Bold`, `32 HP / 2 Def / 32 SpD` → `197 / 112 / 167 / 145 / 117 / 105`, updated from `Modest 32/2/7/25`):**
     - Survives `Adamant 32 Atk Sneasler` `Close Combat` `16/16` times (`83.2%–98.5%` vs. `8/16` OHKO on `152 Def` Modest/Calm).
     - Survives `Modest 0–26 SpA Mega Charizard Y` Sun `Weather Ball` `16/16` times (`72.1%–98.0%`) and `32 SpA` `15/16` times (`85.8%–101.0%`).
3. **Verified Field, Priority & Move Interactions:**
   - **Priority `+5.5` Mega Evolution:** Recalculates speed and triggers weather/terrain (`Drought`, `Electric Surge`, `Sand Stream`, `Snow Warning`) immediately in speed order of the Mega-Evolving Pokémon. Only one Mega Evolution is allowed per team per battle.
   - **`Feint` (`+2` Priority):** Lifts `Spiky Shield` / `Protect` (preventing contact chip for partner moves) **and** shatters `Wide Guard` for the **entire opposing side** of the field.
   - **`Stomping Tantrum` (`75 BP`):** Does **NOT** double to `150 BP` when the user's previous single-target or spread move was blocked by `Protect` / `Detect`.
   - **`Roost`:** Removes the user's `Flying` type for the remainder of the turn (turning `Flying/Fighting` `Mega Staraptor` into pure `Fighting`, which resists `Rock Slide` `0.5×` while remaining `2.0×` weak to `Hurricane`).
   - **Mid-Turn Weather Pivots & `Electro Shot`:** Pivoting a faster `Volt Switch` into `Pelipper` (`Drizzle`) sets Rain mid-turn, allowing slower `Archaludon` to fire a 0-turn `Electro Shot` on that same turn. Conversely, an opponent switching in a slower weather setter (`Hippowdon` / `Tyranitar`) at turn start forces `Electro Shot` into a 2-turn charge and dynamically changes `Weather Ball`'s type.
   - **Critical Hits & `Darkest Lariat` vs. `Stamina`:** Critical hits (`1.5×`) ignore positive `Stamina` Defense boosts (a `2.25×` effective swing against `+1 Def` `Archaludon`). `Darkest Lariat` also ignores target Defense stage changes.
   - **`Rough Skin` vs. `Focus Sash + Unburden`:** Pivoting `Garchomp` into `Focus Sash Sneasler`'s contact move deals `12.5%` `Rough Skin` chip, disabling `Focus Sash` without consuming it and keeping `Unburden` offline.
4. **Coaching Self-Corrections Logged:**
   - **Audit #2 (Set 1 G2):** Corrected single-turn evaluation of Turn 6 `Pelipper -> Archaludon` sacrifice; recognized `Pelipper` preservation was mandatory and traced the actual leak to Turn 3 (ignoring `Roost` on OTS).
   - **Audit #9 → #10 (Set 4 G1/G2):** Caught and corrected an OTS misread on `bvacp80`'s `Excadrill` (`Jolly Nature`, `154` Spe outside Sand / `308` in Sand) prior to Game 3.

---

## 3. Condensed Match Audit Index & Physical Notebook Rules (`Audits #1–#11`)

| Audit | Match ID | Opponent (Set / Game) | Result | Core Mechanics Verified & Notebook Rule Delivered |
| :--- | :--- | :--- | :--- | :--- |
| **#1** | `match-39bebb6d24b0` | `unbis3` (Set 1, G1) | **W** (8T) | `Feint` lifts `Spiky Shield`; `Toxic Debris` on any physical hit; mid-turn `Sand Stream` traps `Electro Shot`.<br>📓 *Enemy weather setter in the back? Click Dragon Pulse, NEVER Electro Shot.* |
| **#2** | `match-d047950d1a9f` | `unbis3` (Set 1, G2) | **W** (10T) | `Prankster Charm` + `Contrary Mega Staraptor` (`+2 Atk`); `Roost` strips `Flying` type (`Rock Slide` `0.5×`).<br>📓 *Check OTS for Roost/Recovery before clicking chip spread moves—overkill with single-target STAB.* |
| **#3** | `match-0b3b0d85b0e2` | `CastorN24` (Set 2, G1) | **W** (7T) | `178` Spe `Fake Out` tie; 1-Mega lockout; `Feint` (`+2`) shatters `Wide Guard` team-wide.<br>📓 *Feint (+2) breaks Wide Guard for your ENTIRE side of the field.* |
| **#4** | `match-ff756ea31166` | `CastorN24` (Set 2, G2) | **L** (9T) | `+5.5` Mega weather speed order; `Lightning Rod` blocks `Volt Switch`; final-turn TR recharging target error.<br>📓 *On the final turn of Trick Room, ignore recharging Hyper Beam slots and eliminate the faster threat.* |
| **#5** | `match-6b7ef1306355` | `CastorN24` (Set 2, G3) | **W** (8T) | Base `Raichu` `Lightning Rod` + `12.5%/turn` `Solar Power` recoil on un-Mega'd opposing `Charizard`.<br>📓 *In Dual-Mega mirrors, choosing Charizard-Y turns base Raichu into a permanent Lightning Rod shield.* |
| **#6** | `match-6ceee1c2cb33` | `chaos damage` (Set 3, G1) | **W** (5T) | `Rough Skin` breaks `Focus Sash` without triggering `Unburden`; `Electric Surge` demotes `Expanding Force`.<br>📓 *Pivoting Rough Skin Garchomp into Sash Sneasler breaks Sash without triggering Unburden.* |
| **#7** | `match-1c839dd0c258` | `chaos damage` (Set 3, G2) | **L** (4T) | `22 HP / 19 Def` `Charizard-Y` lives `Sneasler` `Rock Tomb` (`93.7%`); same-turn `Parting Shot` + faint re-entry.<br>📓 *Never bring pure Sun into Incineroar + Heat Wave Mega Dragonite; bring Rain + Archaludon.* |
| **#8** | `match-62f3552c6a05` | `chaos damage` (Set 3, G3) | **W** (7T) | `Leftovers` threshold (`2.6%` survival); mid-turn `Volt Switch -> Pelipper` enables 0-turn `Electro Shot`; `Darkest Lariat` ignores `+2 Def`.<br>📓 *When Rain expires, faster Volt Switch -> Pelipper sets Drizzle mid-turn for an instant 0-turn Electro Shot.* |
| **#9** | `match-6afcaec2ec66` | `bvacp80` (Set 4, G1) | **W** (10T) | Non-Mega `Salamence` (`167` Spe) outsped by `Garchomp` (`169` Spe, `1/16` OHKO); `Protect` does not double `Stomping Tantrum`; `Grassy Terrain` recovery thresholds.<br>📓 *Hitting Protect does NOT double Stomping Tantrum—and Double Protect under Grassy Terrain farms +6.25% survival thresholds.* |
| **#10** | `match-382fe59c8ddc` | `bvacp80` (Set 4, G2) | **L** (8T) | Base `Charizard` Rain `Weather Ball` (`67%–79%` vs. Tyranitar); `4.17%` crit ignores `+1 Def Stamina` (`2.25×` swing); Turn 7 `Hazard Protect` endgame win line.<br>📓 *In Rain, Charizard's Weather Ball is a 150-BP Water nuke—and Protect Charizard-Y when a Rock Slide user can't drop this turn.* |
| **#11** | `match-8e3433f8b31c` | `bvacp80` (Set 4, G3) | **W** (10T) | `22 HP / 19 Def` `Charizard-Y` survives `Jolly Excadrill` `4×` spread `Rock Slide` `16/16` times (`77.7%–91.4%`, `82.3%` actual) for double-KO `Heat Wave`.<br>📓 *Trust 22 HP / 19 Def Charizard-Y to live Jolly Excadrill spread Rock Slide 16/16 times.* |
