# Milestone 2: Showdown-to-Tensor Compiler & 26x26 Matrix Action Pruner

**Module File:** [`vgc_tensor_core/compiler.py`](../compiler.py)  
**Reference Specification:** [`vgc_tensor_core/legacy_doc/logic_engine.py`](../legacy_doc/logic_engine.py)  
**Test Suite:** [`vgc_tensor_core/tests/test_milestone2_compiler_and_pruner.py`](../tests/test_milestone2_compiler_and_pruner.py)  
**Saved Test Output:** [`vgc_tensor_core/tests/outputs/milestone2_test_output.txt`](../tests/outputs/milestone2_test_output.txt)

---

## 1. Architectural Purpose & Isolation Guarantee

Milestone 2 builds the **CPU Frontend (Showdown-to-Tensor Compiler & $26 \times 26$ Matrix Action Pruner)**:
1. **Zero Coupling to `engine/` or Legacy Python Loops:** `vgc_tensor_core/legacy_doc/logic_engine.py` is preserved strictly as a reference specification in `legacy_doc/`. None of its string-checking methods are imported or called at runtime; instead, all of its Hard Physical Invariants and Soft Tactical Risk-Reward Priors are compiled directly into **vectorized matrix operations** inside `compiler.py`.
2. **Full $26 \times 26 = 676$ Per-Player Action Coordinate System:** Captures every possible VGC Doubles decision—including opponent targeting, partner self-targeting (`Helping Hand`, `Pollen Puff`, `Weakness Policy` self-procs), holding vs. triggering Mega Evolution for weather wars, and switching to Bench 1 or Bench 2.
3. **Sparse-to-Dense Active Grid Compression (`[N_valid, 2]`):** Automatically masks out the $\approx 85\%\text{–}90\%$ of impossible/redundant coordinates in the $676 \times 676$ joint space so the GPU state machine only simulates physically legal action pairs.

---

## 2. Key Engineering Decisions & Mathematical Formulations

### Decision 1: The 26-Choice Per-Slot Geometry (`26 x 26 = 676` Per Player)
For each active slot (`Slot A` and `Slot B`), the 26 discrete choices $c \in \{0..25\}$ are partitioned into **3 Target Buckets $\times$ 2 Mega Modes + 2 Bench Switches**:

$$c = (12 \times \text{mega\_mode}) + (4 \times \text{target\_bucket}) + \text{move\_idx} \quad \text{for } c \in \{0..23\}$$

| Choice Index Range | Mega Mode | Target Bucket | Move Index | Description |
| :--- | :---: | :---: | :---: | :--- |
| `0..3` | `0` (Base) | `0` (`Opp_A` / Default) | `0..3` | Base Move `0..3` $\to$ Opponent Slot A (or Spread / Self / Field) |
| `4..7` | `0` (Base) | `1` (`Opp_B`) | `0..3` | Base Move `0..3` $\to$ Opponent Slot B |
| `8..11` | `0` (Base) | `2` (`Partner`) | `0..3` | Base Move `0..3` $\to$ Partner Slot (Ally support / Self-hit policy) |
| `12..15` | `1` (Mega) | `0` (`Opp_A` / Default) | `0..3` | **Mega Evolve** + Move `0..3` $\to$ Opponent Slot A |
| `16..19` | `1` (Mega) | `1` (`Opp_B`) | `0..3` | **Mega Evolve** + Move `0..3` $\to$ Opponent Slot B |
| `20..23` | `1` (Mega) | `2` (`Partner`) | `0..3` | **Mega Evolve** + Move `0..3` $\to$ Partner Slot |
| `24` | — | `Bench_1` | — | Switch Active Slot $\leftrightarrow$ Bench Slot 1 |
| `25` | — | `Bench_2` | — | Switch Active Slot $\leftrightarrow$ Bench Slot 2 |

---

### Decision 2: Outer-Product Joint Validity Matrix & Cross-Slot Collision Locks
Given the 1D validity vectors $\mathbf{v}_A \in \{0,1\}^{26}$ for Active Slot A and $\mathbf{v}_B \in \{0,1\}^{26}$ for Active Slot B, the joint $26 \times 26$ validity matrix $\mathbf{M}_{\text{valid}}$ is constructed via outer product followed by two cross-slot collision masks:

$$\mathbf{M}_{\text{valid}} = \left(\mathbf{v}_A \otimes \mathbf{v}_B^T\right) \odot \mathbf{M}_{\text{no\_double\_mega}} \odot \mathbf{M}_{\text{no\_switch\_crash}}$$

1. **Simultaneous Double-Mega Lock ($\mathbf{M}_{\text{no\_double\_mega}}$):**
   Even if both Active Slot A and Active Slot B hold Mega Stones (e.g., `Floette-Eternal` + `Charizard` on the field together), a player can only Mega Evolve **one** Pokémon per game/turn. Thus the entire $12 \times 12$ sub-block where *both* slots click Mega (`12..23` $\times$ `12..23`) is zeroed out:
   $$\mathbf{M}_{\text{valid}}[12:24, \, 12:24] = 0.0$$
2. **Simultaneous Bench Switch Crash ($\mathbf{M}_{\text{no\_switch\_crash}}$):**
   Both active slots cannot switch into the exact same reserve Pokémon simultaneously:
   $$\mathbf{M}_{\text{valid}}[24, \, 24] = 0.0 \qquad \text{and} \qquad \mathbf{M}_{\text{valid}}[25, \, 25] = 0.0$$
   *(Switching Slot A $\to$ Bench 1 and Slot B $\to$ Bench 2 at coordinates `(24, 25)` and `(25, 24)` remains `1.0`!)*

---

### Decision 3: Matrix Encoding of Hard Physical Invariants (`legacy_doc/logic_engine.py`)
Every hard physical failure from `legacy_doc/logic_engine.py` is encoded as a binary gate in $\mathbf{v}_A, \mathbf{v}_B \in \{0,1\}^{26}$ using pre-compiled move features (`MoveIdx.FIRST_TURN_ONLY`, `MoveIdx.IS_SOUND_MOVE`, `MoveIdx.WEATHER_SURE_HIT`, `MoveIdx.GRASSY_PRIO_BOOST`):

1. **Target Bucket Canonicalization Gate:**
   - Spread moves (`ALL_ADJACENT_FOES`, `ALL_ADJACENT`), Self moves (`SELF`), Side moves (`ALLY_SIDE`), and Field moves (`GLOBAL_FIELD`) are non-directional, so they are valid **only** in Target Bucket `0` (`0..3` and `12..15`); Buckets `1` and `2` are masked to `0.0` so non-directional moves never duplicate rows in the matrix.
   - `ALLY` moves (`Helping Hand`) are valid **only** in Target Bucket `2` (`8..11` and `20..23`).
2. **Turn-1 Only Moves (`Fake Out`, `First Impression`):**
   $$\text{Valid} = 0.0 \quad \text{if } \text{Move}[{\text{FIRST\_TURN\_ONLY}}] == 1.0 \;\land\; \text{Mon}[{\text{ACTIVE\_TURNS}}] > 0.0$$
3. **Priority Blocking & Psychic Terrain Exemption:**
   Effective priority is resolved as:
   $$p_{\text{eff}} = p_{\text{base}} + \mathbb{I}(\text{Prankster} \land \text{Status}) + \mathbb{I}(\text{GrassyGlide} \land \text{GrassyTerrain} \land \text{UserGrounded})$$
   If $p_{\text{eff}} > 0$ and the move targets an opposing slot (`tgt_bucket` $\in \{0, 1\}$):
   - Blocked (`0.0`) if either active opponent has `Armor Tail` or `Queenly Majesty`.
   - Blocked (`0.0`) if `Psychic Terrain` is active AND $\text{TargetGrounded} == 1.0$ (while Airborne targets with $\text{TargetGrounded} == 0.0$ remain `1.0`!).
4. **Prankster vs. Dark-Type Immunity:**
   $$\text{Valid} = 0.0 \quad \text{if } \text{Prankster} \;\land\; \text{Status} \;\land\; (\text{TargetType1}_{\text{Dark}} + \text{TargetType2}_{\text{Dark}} > 0)$$
5. **Ability & Terrain Nullifiers (`Soundproof`, `Good as Gold`, `Flash Fire`, Electric/Misty Sleep Block):**
   - Sound move into `Soundproof` $\to$ `0.0`
   - Status move into `Good as Gold` $\to$ `0.0`
   - Fire move into `Flash Fire` $\to$ `0.0`
   - Sleep move (`Spore`, `Hypnosis`) into Grounded target under `Electric` or `Misty` Terrain $\to$ `0.0`

---

### Decision 4: Soft Tactical Prior Matrix ($\mathbf{M}_{\text{prior}} \in \mathbb{R}^{26 \times 26}$)
For all surviving legal actions ($\mathbf{M}_{\text{valid}}[i, j] == 1.0$), the compiler computes the soft risk-reward prior vectors $\mathbf{p}_A, \mathbf{p}_B \in \mathbb{R}^{26}$ and their outer-product matrix:

$$\mathbf{M}_{\text{prior}} = \left(\mathbf{p}_A \otimes \mathbf{p}_B^T\right) \odot \mathbf{M}_{\text{valid}}$$

- **Consecutive Protect Decay:** $\text{Prior} = 0.40$ when $\text{PROTECT\_COUNTER} == 1$, and $0.10$ when $\text{PROTECT\_COUNTER} \ge 2$.
- **Bilinear Type Effectiveness Priors:**
  - $\text{Eff} \ge 4.0\times \implies 1.35 \times \text{Acc}_{\text{eff}}$
  - $\text{Eff} \ge 2.0\times \implies 1.20 \times \text{Acc}_{\text{eff}}$
  - $\text{Eff} \le 0.25\times \implies 0.50$
  - $\text{Eff} == 0.0\times \implies 0.20$ (Ground vs Airborne switch read) or $0.15$ (Type immunity switch read)
  - Partner self-attack (`tgt_bucket == 2` on `SINGLE_FOE` move) $\implies 0.15$

---

## 3. How to Run the Milestone 2 Verification Suite & Saved Output

### Command to Execute:
```powershell
.\.venv\Scripts\python.exe vgc_tensor_core/tests/test_milestone2_compiler_and_pruner.py
```

### Full Saved Output (`vgc_tensor_core/tests/outputs/milestone2_test_output.txt`):
```text
====================================================================================================
MILESTONE 2 VERBOSE MATRIX TRACE — SHOWDOWN COMPILER & 26x26 ACTION PRUNER
Active Compute Backend : torch (device=cuda:0) | GPU: NVIDIA GeForce RTX 3060 Laptop GPU
====================================================================================================

[TEST 01] COMPILED BATTLE STATE TENSORS (TURN 1: GRIMMSNARL+GARCHOMP vs FLOETTE-MEGA+SNEASLER)
----------------------------------------------------------------------------------------------------
  Field Tensor F [24]       : Weather One-Hot=[1.0, 0.0, 0.0, 0.0, 0.0] | Terrain One-Hot=[1.0, 0.0, 0.0, 0.0, 0.0]
  Slot 0 (P1A:Grimmsnarl     ): HP=202.0/202.0 | Alive=1 | Spe= 80.0 (MegaSpe= 80.0, CanMega=0) | Move BPs=[0.0, 0.0, 75.0, 0.0]
  Slot 1 (P1B:Garchomp       ): HP=183.0/183.0 | Alive=1 | Spe=169.0 (MegaSpe=169.0, CanMega=0) | Move BPs=[75.0, 100.0, 0.0, 0.0]
  Slot 2 (P1_B1:Incineroar   ): HP=202.0/202.0 | Alive=1 | Spe= 80.0 (MegaSpe= 80.0, CanMega=0) | Move BPs=[40.0, 120.0, 0.0, 0.0]
  Slot 3 (P1_B2:Sinistcha    ): HP=178.0/178.0 | Alive=1 | Spe= 90.0 (MegaSpe= 90.0, CanMega=0) | Move BPs=[0.0, 0.0, 0.0, 0.0]
  Slot 4 (P2A:Floette        ): HP=181.0/181.0 | Alive=1 | Spe=144.0 (MegaSpe=168.0, CanMega=1) | Move BPs=[80.0, 50.0, 0.0, 0.0]
  Slot 5 (P2B:Sneasler       ): HP=155.0/155.0 | Alive=1 | Spe=189.0 (MegaSpe=189.0, CanMega=0) | Move BPs=[80.0, 120.0, 40.0, 0.0]
  Slot 6 (P2_B1:Charizard    ): HP=153.0/153.0 | Alive=1 | Spe=167.0 (MegaSpe=167.0, CanMega=1) | Move BPs=[95.0, 110.0, 0.0, 0.0]
  Slot 7 (P2_B2:Kingambit(KO)): HP=  0.0/207.0 | Alive=0 | Spe= 70.0 (MegaSpe= 70.0, CanMega=0) | Move BPs=[80.0, 70.0, 120.0, 0.0]
  Result: PASS

[TEST 02] 26x26 ACTION MATRIX & CROSS-SLOT COLLISION PRUNING
----------------------------------------------------------------------------------------------------
  Choice Index Legend (0..25): [(0, 'M0->OppA'), (1, 'M1->OppA'), (2, 'M2->OppA'), (3, 'M3->OppA'), (4, 'M0->OppB'), (5, 'M1->OppB'), (6, 'M2->OppB'), (7, 'M3->OppB'), (8, 'M0->Ally'), (9, 'M1->Ally'), (10, 'M2->Ally'), (11, 'M3->Ally'), (12, 'MegaM0->A'), (13, 'MegaM1->A'), (14, 'MegaM2->A'), (15, 'MegaM3->A'), (16, 'MegaM0->B'), (17, 'MegaM1->B'), (18, 'MegaM2->B'), (19, 'MegaM3->B'), (20, 'MegaM0->P'), (21, 'MegaM1->P'), (22, 'MegaM2->P'), (23, 'MegaM3->P'), (24, 'Sw->Bnch1'), (25, 'Sw->Bnch2')]
  P1A (Grimmsnarl) Valid[26] : [1, 1, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1] (Sum=10/26)
  P1B (Garchomp)   Valid[26] : [1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1] (Sum=8/26)
  P1 Joint Valid Actions     : 78 / 676 (Pruned 598 invalid pairs!)
  P2A (Floette+Mega)Valid[26]: [1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0] (Sum=13/26 - includes Mega 12..23!)
  P2B (Sneasler)   Valid[26] : [1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0] (Sum=11/26 - Bench2 KO -> Sw25=0!)
  P2 Joint Valid Actions     : 142 / 676 (Pruned 534 invalid pairs!)
  Total Active Joint Grid    : 78 x 142 = 11076 legal universes (out of 676x676 = 456,976 raw cells!)
  Result: PASS

[TEST 03] SIMULTANEOUS DOUBLE-MEGA LOCK (M_valid[12:24, 12:24] = 0.0)
----------------------------------------------------------------------------------------------------
  Slot A (Floette) Mega Choices Sum   : 6
  Slot B (Charizard) Mega Choices Sum : 6
  Joint[12:24, 0:12] (A Mega, B Base) : 36 valid pairs
  Joint[0:12, 12:24] (A Base, B Mega) : 36 valid pairs
  Joint[12:24, 12:24] (BOTH Mega)     : 0 valid pairs (Strictly Blocked!)
  Result: PASS

[TEST 04] HARD PHYSICAL INVARIANTS (MATRIX PRUNER PARITY WITH LOGIC_ENGINE.PY)
----------------------------------------------------------------------------------------------------
  • Sneasler Fake Out on active_turns=1.0 (Choices 2, 6)    : 0.0, 0.0 (Blocked!)
  • Prankster Thunder Wave -> Grounded/Dark P2A (Choice 3)  : 0.0 (Blocked by Psychic Terrain & Dark!)
  • Prankster Thunder Wave -> Airborne P2B (Choice 7)       : 1.0 (Exempt & Valid!)
  • Spore under Electric Terrain / Good as Gold (Choices 0,4): 0.0, 0.0 (Blocked!)
  Result: PASS

[TEST 05] SOFT TACTICAL PRIOR MATRIX (HIGH-RISK / HIGH-REWARD CONTINUUM)
----------------------------------------------------------------------------------------------------
  • Garchomp Stomping Tantrum -> Airborne Charizard (Choice 0) : Valid=1 | Prior=0.20 (Hard Switch Read)
  • Garchomp Stomping Tantrum -> 2.0x SE Sneasler (Choice 4)   : Valid=1 | Prior=1.20 (Deterministic SE)
  • Garchomp Consecutive Protect (protect_counter=1, Choice 3) : Valid=1 | Prior=0.40 (~33% Decay Heuristic)
  • Garchomp Partner Self-Target (Choice 8)                    : Valid=1 | Prior=0.15 (Self-Side Policy)
  Result: PASS

[TEST 06] COMPILER + 26x26 MATRIX PRUNER LATENCY BENCHMARK
----------------------------------------------------------------------------------------------------
  • Full 8-Slot Compilation + P1/P2 [26x26] Mask & Prior Generation : 2.314 ms / turn
  Result: PASS

====================================================================================================
TOTAL TESTS RUN: 6 | FAILURES: 0 | ERRORS: 0
STATUS: PASS (100% EXACT MATHEMATICAL PARITY)
====================================================================================================
```
