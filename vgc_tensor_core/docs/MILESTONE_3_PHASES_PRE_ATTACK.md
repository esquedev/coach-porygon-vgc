# Milestone 3: Phases 1–3 Pre-Attack Vectorized Engine (`phases_pre_attack.py`)

## 1. Architectural Purpose & Scope

In an official Pokémon VGC 4v4 Doubles turn (Regulation M-C), **before a single damaging or status move is executed**, the cartridge resolves three mandatory synchronization barriers across all 4 active slots (`0: P1A`, `1: P1B`, `4: P2A`, `5: P2B`):

1. **Optional Turn-0 Lead Entry Ability Pass (`resolve_lead_entry_abilities=True`):**
   - Sorts all 4 initial active leads by `TrickRoomSign * EffectiveSpeed` and fires their entry abilities (`Drizzle`, `Drought`, `Sand Stream`, `Snow Warning`, `Electric/Grassy/Psychic/Misty Surge`, `Hospitality`, and `Intimidate` $\to$ immediate reactive `Defiant` / `Competitive`) before Turn 1 choices execute.
2. **Phase 1 — Barrier 1: Voluntary Switches (`Priority +6`) & Speed-Ordered Switch-In Abilities:**
   - Resets outgoing stat boosts (`8..14`), volatile states (`58..66`), `UNBURDEN_ACTIVE` (`72`), and `CHOICE_LOCKED_MOVE` (`73`) on switching active slots via Hadamard multiplication with `tables.switch_persist_mask`.
   - Swaps the active slot and target bench slot (`0..1 <-> 2..3` for P1, `4..5 <-> 6..7` for P2) across both the Roster Tensor $\mathbf{P}$ (`[..., 8, 84]`) and Move Tensor $\mathbf{M}_{\text{moves}}$ (`[..., 8, 4, 52]`).
   - Sorts all newly switched-in slots by `TrickRoomSign * EffectiveSpeed` and fires their Switch-In Entry Abilities.
3. **Phase 2 — Barrier 2: Mega Evolution (`Priority +5.5`), Instantaneous Regulation M-C 5-Stat Recalibration & Mega Entry Abilities:**
   - Transforms active slots choosing Mega Evolution (`choice_idx in 12..23`) in-place by interpolating all 5 Level-50 stats (`STAT_ATK..STAT_SPE` $\leftarrow$ `MEGA_ATK..MEGA_SPE` at indices `78..82`) and `ABILITY_ID` $\leftarrow$ `MEGA_ABILITY_ID` (`83`).
   - Sorts newly Mega-Evolved slots by their new post-Mega `TrickRoomSign * EffectiveSpeed` and fires Mega Entry Abilities (`Mega Charizard Y` `Drought`, `Mega Manectric` `Intimidate`, etc.).
4. **Phase 3 — Barrier 3: Effective Speed, Priority Bracket & Seeded `±0.01` Jitter Turn-Order Sort:**
   - Computes Cartridge Level-50 Effective Speed $S_{\text{eff}}$ and Effective Priority $p_{\text{eff}}$ for all 4 active slots.
   - Detects exact intra-bracket speed ties (`speed_tie_alert` mask `[B1, B2]`), applies a reproducible seeded `±0.01` tie-break jitter, generates human-readable `speed_tie_notes`, and outputs `execution_order [B1, B2, 4]` via `argsort`.

---

## 2. Key Engineering Decisions & Mathematical Proofs

### Decision 1: Why Separate Entry Abilities into Two Synchronization Barriers (Barrier 1 $\to$ Barrier 2)?
In competitive VGC (Regulation M-C), Switches occur at Priority bracket `+6`, whereas Mega Evolution occurs at Priority bracket `+5.5` (after all voluntary switches have completed, before `+5` Helping Hand).

**Proof of Cross-Phase Weather Overwrite (`Test 03`):**
- Suppose Player 1 switches out `Grimmsnarl` into `Pelipper` (`Drizzle`, `Speed = 85`) while Player 2 Mega Evolves `Charizard` into `Mega Charizard Y` (`Drought`, `Speed = 169`) on the same turn.
- If Switch-In abilities and Mega Evolution abilities were pooled into a single speed-sorted pass, `Mega Charizard Y` (`169`) would act first (`Sun`) and slower `Pelipper` (`85`) would act second (`Rain`), falsely leaving `Rain` on the board!
- By enforcing **Barrier 1 (Switches + Switch-In Abilities)** strictly before **Barrier 2 (Mega Evolution + Mega Entry Abilities)**:
  1. At **Barrier 1**, `Pelipper` switches in and triggers `Drizzle`:
     $$\mathbf{w}^{(1)} = \mathbf{w}^{(0)} \cdot \mathbf{T}_{\text{set\_weather}}^{(\text{Rain})} = [0, 0, 1, 0, 0]$$
  2. At **Barrier 2**, `Charizard` Mega Evolves into `Mega Charizard Y` and triggers `Drought`:
     $$\mathbf{w}^{(2)} = \mathbf{w}^{(1)} \cdot \mathbf{T}_{\text{set\_weather}}^{(\text{Sun})} = [0, 1, 0, 0, 0]$$
  - **`Sun` (`[0, 1, 0, 0, 0]`) always wins**, regardless of relative speeds!

---

### Decision 2: The Simultaneous Switch-In Weather/Terrain Overwrite Theorem (`Test 01`)
When two Pokémon with weather-setting abilities switch in at the **same** barrier (e.g., P1 switches to `Pelipper` `Drizzle` at `Speed = 85` and P2 switches to `Torkoal` `Drought` at `Speed = 40`), both entry abilities are queued in speed order:

$$\text{EntryScore}_s = 100000.0 \cdot I_{\text{trig}}(s) + \text{TrickRoomSign} \cdot S_{\text{eff}}(s) + \delta_{\text{slot}}(s)$$

where $\text{TrickRoomSign} = 1.0 - 2.0 \cdot I_{\text{TR\_TURNS} > 0} \in \{+1.0, -1.0\}$.
- **Case A: Normal Room ($\text{TR} = 0 \implies \text{TrickRoomSign} = +1.0$):**
  1. Step 0 (Fastest): `Pelipper` ($+85$) fires `Drizzle` $\to \mathbf{w} = [0, 0, 1, 0, 0]$ (`Rain`).
  2. Step 1 (Slower): `Torkoal` ($+40$) fires `Drought` $\to \mathbf{w} = [0, 0, 1, 0, 0] \cdot \mathbf{T}^{(\text{Sun})} = [0, 1, 0, 0, 0]$ (`Sun` wins!).
- **Case B: Trick Room ($\text{TR} > 0 \implies \text{TrickRoomSign} = -1.0$):**
  1. Step 0 (Slowest has highest score $-40 > -85$): `Torkoal` ($-40$) fires `Drought` first (`Sun`).
  2. Step 1 (Faster acts second): `Pelipper` ($-85$) fires `Drizzle` second $\to \mathbf{w} = [0, 1, 0, 0, 0] \cdot \mathbf{T}^{(\text{Rain})} = [0, 0, 1, 0, 0]$ (`Rain` wins!).

---

### Decision 3: Vectorized `Intimidate` $\to$ Immediate Reactive `Defiant` / `Competitive` (`Test 02`)
When an active slot $s$ triggers `Intimidate`, for each opposing active slot $o \in \text{Opponents}(s)$, the exact branchless landing gate is:

$$I_{\text{intim}}(o) = I_{\text{actor}}(s) \cdot I_{\text{Abil}_s == \text{INTIMIDATE}} \cdot \text{Alive}_o \cdot (1 - I_{\text{Sub}_o > 0}) \cdot (1 - \text{ItemAct}_o \cdot I_{\text{Item}_o == \text{CLEAR\_AMULET}}) \cdot (1 - I_{\text{Abil}_o \in \{\text{INNER\_FOCUS}, \text{SCRAPPY}, \text{GOOD\_AS\_GOLD}\}})$$

If $b_{\text{atk}}^{(0)} = \mathbf{P}_{o, \text{BOOST\_ATK}}$ is the initial Attack stage:
1. **Actual Stage Drop Gate:**
   $$I_{\text{dropped}}(o) = I_{\text{intim}}(o) \cdot I_{b_{\text{atk}}^{(0)} > -6.0}$$
2. **Post-Intimidate + Immediate Reactive `Defiant` ($+2\text{ Atk}$):**
   $$\mathbf{P}_{o, \text{BOOST\_ATK}} \leftarrow \text{ clamp}\Big(\text{clamp}(b_{\text{atk}}^{(0)} - I_{\text{intim}}(o), -6, +6) + 2.0 \cdot I_{\text{dropped}}(o) \cdot I_{\text{Abil}_o == \text{DEFIANT}}, -6, +6\Big)$$
   - For `Kingambit` (`Defiant`) starting at $0.0\text{ Atk}$: $0.0 - 1.0 + 2.0 = \mathbf{+1.0\text{ Atk}}$!
   - For `Garchomp` holding `Clear Amulet`: $I_{\text{intim}}(o) = 0.0 \implies \mathbf{0.0\text{ Atk}}$!
3. **Immediate Reactive `Competitive` ($+2\text{ SpA}$):**
   $$\mathbf{P}_{o, \text{BOOST\_SPA}} \leftarrow \text{clamp}\Big(b_{\text{spa}}^{(0)} + 2.0 \cdot I_{\text{dropped}}(o) \cdot I_{\text{Abil}_o == \text{COMPETITIVE}}, -6, +6\Big)$$

---

### Decision 4: Cartridge Level-50 Effective Speed Formula (`compute_active_effective_speeds`)
For each active slot $s \in \{0, 1, 4, 5\}$, Effective Speed $S_{\text{eff}}(s)$ is computed with sequential floor rounding:

$$S_1 = \left\lfloor \text{STAT\_SPE}_s \times \frac{\max(2.0, 2.0 + b_{\text{spe}})}{\max(2.0, 2.0 - b_{\text{spe}})} \right\rfloor$$

$$S_2 = \left\lfloor S_1 \times (1.0 + I_{\text{weather\_spe}}(s)) \times (1.0 + \text{UNBURDEN\_ACTIVE}_s) \right\rfloor$$

$$S_3 = \left\lfloor S_2 \times \left(1.0 + 0.5 \cdot \text{ITEM\_ACTIVE}_s \cdot I_{\text{ITEM}_s == \text{CHOICE\_SCARF}}\right) \right\rfloor$$

$$S_4 = \left\lfloor S_3 \times \left(1.0 + I_{\text{SIDE\_TAILWIND} > 0}\right) \right\rfloor$$

$$S_{\text{eff}}(s) = \left\lfloor S_4 \times \left(1.0 - 0.5 \cdot \text{STATUS\_PARALYZE}_s\right) \right\rfloor$$

---

### Decision 5: Exact Speed Tie Detection (`speed_tie_alert`) & Seeded `±0.01` Jitter (`Test 05`)
To ensure that exact 50/50 speed ties are never silently hidden inside an arbitrary array-index order while keeping the tensor sort 100% deterministic and reproducible:
1. **Pairwise Intra-Bracket Speed Tie Detection:**
   Across all $\binom{4}{2} = 6$ pairs of active slots $(i, j)$:
   $$\text{Tie}_{i,j} = I_{\text{Alive}_i \land c_i < 24} \cdot I_{\text{Alive}_j \land c_j < 24} \cdot I_{p_{\text{eff}}(i) == p_{\text{eff}}(j)} \cdot I_{S_{\text{eff}}(i) == S_{\text{eff}}(j)}$$
   $$\text{Speed\_Tie\_Alert} = \min\left(1.0, \sum_{0 \le i < j \le 3} \text{Tie}_{i,j}\right)$$
2. **Bounded `±0.01` Seeded Jitter ($\epsilon_s \in [-0.01, +0.01]$):**
   Because $S_{\text{eff}}(s) \in \mathbb{Z}_{\ge 1}$ is always an exact integer, any two Pokémon with different effective speeds satisfy $|S_{\text{eff}}(i) - S_{\text{eff}}(j)| \ge 1.0$. Since $|\epsilon_i - \epsilon_j| \le 0.02 \ll 1.0$, adding $\epsilon_s$ **never** alters the turn order of non-tied Pokémon, and strictly breaks ties when $p_{\text{eff}}(i) == p_{\text{eff}}(j)$ and $S_{\text{eff}}(i) == S_{\text{eff}}(j)$:
   $$\text{SortScore}_s = 10000.0 \cdot p_{\text{eff}}(s) + \text{TrickRoomSign} \cdot S_{\text{eff}}(s) + \epsilon_s$$

---

## 3. How to Run the Milestone 3 Verification Suite & Saved Output

### Command to Execute:
```powershell
.\.venv\Scripts\python.exe vgc_tensor_core/tests/test_milestone3_phases_pre_attack.py
```

### Full Saved Output (`vgc_tensor_core/tests/outputs/milestone3_test_output.txt`):
```text
========================================================================================================
MILESTONE 3 VERBOSE MATRIX TRACE — PHASES 1–3 (SWITCHES, MEGA EVOLUTION & SPEED/PRIORITY SORT)
Active Compute Backend : torch (device=cuda:0) | GPU: NVIDIA GeForce RTX 3060 Laptop GPU
========================================================================================================

[TEST 01] BARRIER 1: SIMULTANEOUS SWITCH-IN WEATHER WAR (NORMAL ROOM vs TRICK ROOM)
--------------------------------------------------------------------------------------------------------
  Scenario: P1A switches to Pelipper (Drizzle, Spe=85) | P2A switches to Torkoal (Drought, Spe=40)
  • Outgoing Grimmsnarl (Moved to Slot 2) Boost Reset : Boost_Atk=0.0 (was +2.0), Taunt=0.0 (was 2.0)
  • Normal Room (TR=0): Pelipper(85) sets Rain 1st -> Torkoal(40) sets Sun 2nd  | Final Weather One-Hot = [0.0, 1.0, 0.0, 0.0, 0.0] (Sun Wins!)
  • Trick Room  (TR=5): Torkoal(40) sets Sun 1st   -> Pelipper(85) sets Rain 2nd | Final Weather One-Hot = [0.0, 0.0, 1.0, 0.0, 0.0] (Rain Wins!)
  Result: PASS

[TEST 02] BARRIER 1: INTIMIDATE -> IMMEDIATE REACTIVE DEFIANT (+2 ATK) & CLEAR AMULET IMMUNITY
--------------------------------------------------------------------------------------------------------
  • P1 Incineroar Switch-In Intimidate -> P2A Floette (Unprotected)   : Boost_Atk = -1.0
  • P1 Incineroar Switch-In Intimidate -> P2B Kingambit (Defiant)     : Boost_Atk = +1.0 (-1 + 2 = +1.0!)
  • P2 Salamence Switch-In Intimidate  -> P1B Garchomp (Clear Amulet) : Boost_Atk = +0.0 (Blocked by Clear Amulet!)
  Result: PASS

[TEST 03] BARRIER 1 (SWITCH) -> BARRIER 2 (MEGA) WEATHER SEQUENCING PROOF
--------------------------------------------------------------------------------------------------------
  Scenario: P1A switches to Pelipper (Drizzle, Spe=85) at Barrier 1 (+6)
            P2A Mega Evolves Charizard -> Mega Charizard Y (Drought, Spe=169) at Barrier 2 (+5.5)
  • Mega Charizard Y Transformation : IsMega=1, SpA=211 (was 161), P2_Mega_Used=1
  • Final Weather One-Hot           : [0.0, 1.0, 0.0, 0.0, 0.0] -> Sun! (Barrier 2 Mega Drought overwrites Barrier 1 Switch Drizzle!)
  Result: PASS

[TEST 04] BARRIER 2: REGULATION M-C INSTANTANEOUS MEGA SPEED RECALIBRATION
--------------------------------------------------------------------------------------------------------
  • Col 0 (Base Floette, Choice 0)  Effective Speeds [P1A, P1B, P2A, P2B] : [80.0, 169.0, 144.0, 150.0]
    -> Execution Order (1=Garchomp 169 -> 3=Kingambit 150 -> 2=Floette 144 -> 0=Grimmsnarl 80) : [1, 3, 2, 0]
  • Col 1 (Mega Floette, Choice 12) Effective Speeds [P1A, P1B, P2A, P2B] : [80.0, 169.0, 168.0, 150.0]
    -> Execution Order (1=Garchomp 169 -> 2=MegaFloette 168 -> 3=Kingambit 150 -> 0=Grimmsnarl 80): [1, 2, 3, 0]
  • Mega Floette 5-Stat Vector [Atk, Def, SpA, SpD, Spe]                  : [85.0, 87.0, 195.0, 178.0, 168.0]
  Result: PASS

[TEST 05] BARRIER 3: PRIORITY BRACKETS, EXACT SPEED TIE DETECTION & ±0.01 JITTER LOG
--------------------------------------------------------------------------------------------------------
  • Effective Priorities [P1A(Prankster), P1B, P2A, P2B(Protect)] : [1.0, 0.0, 0.0, 4.0]
  • Effective Speeds     [P1A, P1B(169), P2A(169), P2B]           : [80.0, 169.0, 169.0, 150.0]
  • Seeded ±0.01 Jitters [P1A, P1B, P2A, P2B] (seed=2026)         : [-0.00559999980032444, -0.0017000000225380063, 0.009499999694526196, -0.008200000040233135]
  • Final Execution Order [0..3]                                  : [3, 0, 2, 1]
  • Speed_Tie_Alert Mask [0, 0]                                   : 1.0
  • Human-Readable Alert : [SPEED_TIE_ALERT cell=(0,0)] P1B(Slot1) vs P2A(Slot4) tied at Priority=+0, EffectiveSpeed=169 | Seeded Jitter (P1B(Slot1)=-0.0017, P2A(Slot4)=+0.0095) -> P2A(Slot4) wins tie-break (50/50 coinflip alert!)
  Result: PASS

[TEST 06] FULL 100x100 GRID (10,000 UNIVERSES) PHASES 1–3 LATENCY BENCHMARK (CPU vs CUDA)
--------------------------------------------------------------------------------------------------------
  • PyTorch (cpu   ) [100x100 = 10,000 cells] Phases 1–3 Mean Latency : 248.223 ms / pass
  • PyTorch (cuda:0) [100x100 = 10,000 cells] Phases 1–3 Mean Latency : 98.589 ms / pass
  Result: PASS

========================================================================================================
TOTAL TESTS RUN: 6 | FAILURES: 0 | ERRORS: 0
STATUS: PASS (100% EXACT MATHEMATICAL PARITY)
========================================================================================================
```
