# Milestone 1: State Tensor Schema & Bilinear One-Hot Lookup Matrices

**Module File:** [`vgc_tensor_core/schema_and_tables.py`](../schema_and_tables.py)  
**Test Suite:** [`vgc_tensor_core/tests/test_milestone1_schema_and_tables.py`](../tests/test_milestone1_schema_and_tables.py)  
**Saved Test Output:** [`vgc_tensor_core/tests/outputs/milestone1_test_output.txt`](../tests/outputs/milestone1_test_output.txt)

---

## 1. Architectural Purpose & Isolation Guarantee

Milestone 1 establishes the mathematical foundation of the standalone `vgc_tensor_core` state machine.
1. **Zero Repository Dependencies:** `schema_and_tables.py` imports **zero** modules from `engine/`. It depends strictly on `numpy` and (optionally, when installed) `torch`.
2. **Block-Structured Tensor Geometry:** Rather than flattening heterogeneous battle variables into a single unstructured vector (where a matrix multiplication $\mathbf{s} \cdot \mathbf{M}$ would linearly sum unrelated features like HP and Weather), the board state is partitioned into **3 orthogonal, byte-aligned sub-tensors**:
   - **Global Field Tensor $\mathbf{F}$** of shape `[..., 24]`
   - **8-Slot Unified Roster Tensor $\mathbf{P}$** of shape `[..., 8, 80]`
   - **8-Slot Pre-Compiled Move Tensor $\mathbf{M}_{\text{moves}}$** of shape `[..., 8, 4, 48]`

---

## 2. Key Engineering Decisions & Mathematical Proofs

### Decision 1: Why 8 Unified Roster Slots (`[8, 80]`) Instead of 4 Active Slots?
In VGC 4v4 Doubles, each player brings 4 Pokémon (2 Active + 2 Bench):
- `0, 1`: Player 1 Active (`P1A`, `P1B`)
- `2, 3`: Player 1 Bench (`P1_Bench1`, `P1_Bench2`)
- `4, 5`: Player 2 Active (`P2A`, `P2B`)
- `6, 7`: Player 2 Bench (`P2_Bench1`, `P2_Bench2`)

**Mathematical Payoff:**  
When an active Pokémon switches with a bench Pokémon (voluntary switch, `U-turn`, `Parting Shot`, `Eject Button`, or `Red Card`), we do **not** need conditional memory copying. A switch between slot $a$ and slot $b$ is a pure **$8 \times 8$ Permutation Matrix $\mathbf{P}_{\text{perm}}^{(a,b)}$** (an $8 \times 8$ identity matrix $\mathbf{I}_8$ with rows $a$ and $b$ swapped) multiplying both the Roster Tensor $\mathbf{P}$ and the Move Tensor $\mathbf{M}_{\text{moves}}$:

$$\mathbf{P}_{\text{new}} = \mathbf{P}_{\text{perm}}^{(a,b)} \cdot \mathbf{P}_{\text{old}} \qquad \text{and} \qquad \mathbf{M}_{\text{moves, new}} = \mathbf{P}_{\text{perm}}^{(a,b)} \cdot \mathbf{M}_{\text{moves, old}}$$

Both the incoming Pokémon's stats/HP/status AND its 4 pre-compiled moves are swapped into the active slot in two Einstein contractions (`einsum("...ij,...jk->...ik")`).

---

### Decision 2: Why 84 Floats per Pokémon (`[8, 84]`) Instead of 64?
During index layout design, we summed the exact requirements for explicit One-Hot representations:
- `HP Channels` (`0..2`): **3 floats** (`HP_CUR`, `HP_MAX`, `ALIVE_FLAG`)
- `Level-50 Stats` (`3..7`): **5 floats** (`ATK`, `DEF`, `SPA`, `SPD`, `SPE`)
- `Stat Stage Boosts` (`8..14`): **7 floats** (`ATK..EVA` in $[-6, +6]$)
- `Non-Volatile Status One-Hot` (`15..21`): **7 floats** (`Healthy, Burn, Paralyze, Sleep, Freeze, Poison, Toxic`)
- `Primary Type One-Hot` (`22..39`): **18 floats**
- `Secondary Type One-Hot` (`40..57`): **18 floats**

Those 6 blocks alone consume **$3 + 5 + 7 + 7 + 18 + 18 = 58\text{ floats}$**. Squeezing into 64 floats would leave only 6 floats for all 10 Volatile states (`Protect`, `Wide Guard`, `Quick Guard`, `Protect Counter`, `Flinch`, `Active Turns`, `Taunt`, `Encore`, `Substitute`, `Helping Hand`) plus the 16 Equipment/Ability/Mega channels.

By expanding `MON_DIM` from `64` to **`84` floats** ($84 \times 4\text{ bytes} = 336\text{ bytes}$), every single volatile flag, item gate, ability ID, and all 5 in-place Mega Evolution stats (`MEGA_ATK..MEGA_SPE` at `78..82`, `MEGA_ABILITY_ID` at `83`) receive their own dedicated, un-aliased index (`0..83`).

---

### Decision 3: Bilinear One-Hot Contraction ($\mathbf{v}_{\text{state}}^T \cdot \mathbf{M} \cdot \mathbf{v}_{\text{action}}$)
To avoid `if/else` branching when checking how a field state (e.g., `Sunny Day`) modifies an action (e.g., a `Water` move), we represent:
- Active Weather as a $1 \times 5$ One-Hot vector $\mathbf{w} \in \{0,1\}^5$ (`[Clear, Sun, Rain, Sand, Snow]`)
- Active Move Type as a $1 \times 18$ One-Hot vector $\mathbf{m} \in \{0,1\}^{18}$
- The Weather-to-Type Interaction Table as a constant $5 \times 18$ matrix $\mathbf{M}_{\text{weather\_mod}}$ where $\mathbf{M}_{1, \text{Fire}} = 1.5$, $\mathbf{M}_{1, \text{Water}} = 0.5$, $\mathbf{M}_{2, \text{Water}} = 1.5$, $\mathbf{M}_{2, \text{Fire}} = 0.5$, and all other entries are $1.0$.

The weather multiplier is computed via the bilinear contraction (`compute_weather_move_multiplier`):

$$\text{Mult}_{\text{weather}} = \mathbf{w} \cdot \mathbf{M}_{\text{weather\_mod}} \cdot \mathbf{m}^T = \sum_{w=0}^{4} \sum_{t=0}^{17} w_w \, M_{w,t} \, m_t$$

- When $\mathbf{w} = \text{Sun}$ (`[0, 1, 0, 0, 0]`) and $\mathbf{m} = \text{Water}$: $\mathbf{w} \cdot \mathbf{M}_{\text{weather\_mod}}$ selects row 1, and dotting with $\mathbf{m}_{\text{Water}}$ extracts column 2 = **`0.5`**.

---

### Decision 4: The Branchless Single-Type vs. Dual-Type Effectiveness Identity
In Pokémon, dual-type effectiveness is multiplicative ($\text{Eff}_{\text{total}} = \text{Eff}_1 \times \text{Eff}_2$).  
For a Dual-Type Pokémon (like Garchomp: `Dragon` + `Ground`), `def_type1` has a `1.0` at `Dragon` and `def_type2` has a `1.0` at `Ground`.  
However, for a **Single-Type Pokémon**, `def_type2` is an all-zero vector $\mathbf{0}_{18}$. If we naively computed $(\mathbf{m} \cdot \mathbf{M}_{\text{chart}} \cdot \mathbf{d}_2)$, a single-type Pokémon would yield `0.0` (falsely making every single-type Pokémon immune to all damage!).

To solve this with **zero branching**, `compute_type_effectiveness` uses the linear-algebra identity:

$$\text{Eff}_1 = \mathbf{m} \cdot \mathbf{M}_{\text{chart}} \cdot \mathbf{d}_1^T$$

$$\text{Eff}_2 = \left(\mathbf{m} \cdot \mathbf{M}_{\text{chart}} \cdot \mathbf{d}_2^T\right) + \left(1.0 - \sum_{k=0}^{17} d_{2,k}\right)$$

$$\text{Eff}_{\text{total}} = \text{Eff}_1 \odot \text{Eff}_2$$

**Proof of Exactness:**
1. **Case A (Dual-Type Defender):** Since $\mathbf{d}_2$ is a valid One-Hot vector, $\sum_{k} d_{2,k} = 1.0$. Thus $(1.0 - 1.0) = 0.0$, and $\text{Eff}_2 = \mathbf{m} \cdot \mathbf{M}_{\text{chart}} \cdot \mathbf{d}_2^T$.
   - *Example:* `Ice` vs `Garchomp` (`Dragon` + `Ground`): $\text{Eff}_1 = 2.0$, $\text{Eff}_2 = 2.0 + 0.0 = 2.0 \implies \text{Eff}_{\text{total}} = 2.0 \times 2.0 = \mathbf{4.0\times}$.
   - *Example:* `Ground` vs `Charizard` (`Fire` + `Flying`): $\text{Eff}_1 = 2.0$, $\text{Eff}_2 = 0.0 + 0.0 = 0.0 \implies \text{Eff}_{\text{total}} = 2.0 \times 0.0 = \mathbf{0.0\times}$ (Immunity preserved!).
2. **Case B (Single-Type Defender):** Since $\mathbf{d}_2 = \mathbf{0}$, both $\mathbf{m} \cdot \mathbf{M}_{\text{chart}} \cdot \mathbf{d}_2^T = 0.0$ and $\sum_{k} d_{2,k} = 0.0$. Thus $\text{Eff}_2 = 0.0 + (1.0 - 0.0) = 1.0$, and $\text{Eff}_{\text{total}} = \text{Eff}_1 \times 1.0 = \mathbf{\text{Eff}_1}$!

---

### Decision 5: Column-Overwrite State Transition Matrices ($\mathbf{T}_{\text{set\_weather}}$)
When a move (`Sunny Day`) or ability (`Drought`) overwrites the active Weather One-Hot vector $\mathbf{w}_{\text{old}}$, how do we overwrite any previous One-Hot vector into target index $k$ using only matrix multiplication?

Because $\mathbf{w}_{\text{old}}$ is a One-Hot vector, the sum of its entries is strictly invariant: $\sum_{i=0}^{4} w_{\text{old}, i} = 1.0$.  
Therefore, for target weather $k \in \{0..4\}$, we define the $5 \times 5$ matrix $\mathbf{T}^{(k)}_{\text{set\_weather}}$ with **`1.0`s down column $k$** and `0.0`s everywhere else:

$$\left(\mathbf{w}_{\text{old}} \cdot \mathbf{T}^{(k)}_{\text{set\_weather}}\right)_j = \sum_{i=0}^{4} w_{\text{old}, i} \, T^{(k)}_{i,j} = \begin{cases} \sum_{i=0}^{4} w_{\text{old}, i} = 1.0 & \text{if } j = k \\ 0.0 & \text{if } j \neq k \end{cases}$$

---

## 3. Exact Feature Index Map Reference

### A. Global Field Tensor $\mathbf{F}$ (`FIELD_DIM = 24`)
| Index Range | Constant Name | Description |
| :--- | :--- | :--- |
| `0..4` | `WEATHER_START..WEATHER_END` | Weather One-Hot `[Clear, Sun, Rain, Sand, Snow]` |
| `5` | `WEATHER_TURNS` | Remaining Weather turns (`0..8`) |
| `6..10` | `TERRAIN_START..TERRAIN_END` | Terrain One-Hot `[None, Electric, Grassy, Psychic, Misty]` |
| `11` | `TERRAIN_TURNS` | Remaining Terrain turns (`0..8`) |
| `12` | `TRICK_ROOM_TURNS` | Remaining Trick Room turns (`0..5`) |
| `13` | `GRAVITY_TURNS` | Remaining Gravity turns (`0..5`) |
| `14..18` | `P1_TAILWIND..P1_MEGA_USED` | P1 Tailwind, Reflect, Light Screen, Aurora Veil turns, Mega Used flag |
| `19..23` | `P2_TAILWIND..P2_MEGA_USED` | P2 Tailwind, Reflect, Light Screen, Aurora Veil turns, Mega Used flag |

### B. 8-Slot Roster Tensor $\mathbf{P}$ (`ROSTER_SLOTS = 8`, `MON_DIM = 84`)
| Index Range | Constant Name | Description |
| :--- | :--- | :--- |
| `0..2` | `HP_CUR, HP_MAX, ALIVE_FLAG` | Current HP, Max HP, and Alive boolean gate (`1.0` if `HP_CUR > 0`) |
| `3..7` | `STAT_ATK..STAT_SPE` | Active Level-50 calculated stats (`Atk, Def, SpA, SpD, Spe`) |
| `8..14` | `BOOST_ATK..BOOST_EVA` | Stat Stage Boosts in `[-6.0, +6.0]` (Reset to `0.0` on switch) |
| `15..21` | `STATUS_START..STATUS_END` | Non-Volatile Status One-Hot `[Healthy, Burn, Paralyze, Sleep, Freeze, Poison, Toxic]` |
| `22..39` | `TYPE1_START..TYPE1_END` | Primary Type One-Hot (`18` canonical types) |
| `40..57` | `TYPE2_START..TYPE2_END` | Secondary Type One-Hot (`18` types; all `0.0` if single-typed) |
| `58..67` | `VOLATILE_START..VOLATILE_END` | `Protect`, `Wide/Quick Guard`, `Protect Counter`, `Flinch`, `Active Turns`, `Taunt`, `Encore`, `Substitute`, `Helping Hand` |
| `68..83` | `GROUNDED_FLAG..MEGA_ABILITY_ID` | `Grounded`, `Item Active/ID`, `Ability ID`, `Unburden`, `Choice Lock`, `Last Move`, `Toxic Counter`, `Can/Is Mega`, `Mega Atk..Spe (78..82)`, `Mega Ability (83)` |

### C. 8-Slot Pre-Compiled Move Tensor $\mathbf{M}_{\text{moves}}$ (`[8, 4, 52]`)
| Index Range | Constant Name | Description |
| :--- | :--- | :--- |
| `0..4` | `BASE_POWER..CRIT_STAGE` | `Base Power`, `Accuracy`, `Priority`, `TargetType`, `Crit Stage` |
| `5..22` | `TYPE_START..TYPE_END` | Move Type One-Hot (`18` canonical types) |
| `23..25` | `CAT_START..CAT_END` | Move Category One-Hot `[Physical, Special, Status]` |
| `26..34` | `STAT_DELTA_START..SELF` | 7 Stat Stage Deltas (`Atk..Eva`), `Stat Delta Chance`, `Self/Target Flag` |
| `35..42` | `SEC_STATUS_START..CHANCE` | Secondary Status One-Hot (`7` statuses) + `Secondary Status Chance` |
| `43..51` | `RECOIL_PCT..IS_BULLET` | `Recoil/Drain Pct`, `Flinch Chance`, `Protect Type`, `Switch Mode`, `Field Op ID`, `Is Sound/Powder/Spread/Bullet` |

---

## 4. How to Run the Milestone 1 Verification Suite & Saved Output

### Command to Execute:
```powershell
.\.venv\Scripts\python.exe vgc_tensor_core/tests/test_milestone1_schema_and_tables.py
```

### Full Saved Output (`vgc_tensor_core/tests/outputs/milestone1_test_output.txt`):
```text
================================================================================================
MILESTONE 1 VERBOSE MATRIX TRACE — VGC TENSOR CORE (SCHEMA & BILINEAR TABLES)
Active Compute Backend : torch (device=cuda:0) | GPU: NVIDIA GeForce RTX 3060 Laptop GPU
================================================================================================

[TEST 01] TENSOR DIMENSIONS & MEMORY LAYOUT VERIFICATION
------------------------------------------------------------------------------------------------
  Global Field Tensor F       : shape=(24,)          | float32 bytes=96 B
  8-Slot Roster Tensor P      : shape=(8, 84)        | float32 bytes=2688 B
  8-Slot Move Tensor M_moves  : shape=(8, 4, 52)     | float32 bytes=6656 B
  Full 100x100 Turn Grid Size : F=960 KB, P=26.9 MB, M_moves=66.6 MB (or 1.28 MB shared palette)
  MonIdx Slice Check          : HP[0:3], Stats[3:8], Boosts[8:15], Status[15:22], Type1[22:40], Type2[40:58], Volatiles[58:68], Equip/Mega[68:84]
  Switch Persist Mask [0..83] : [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
  Result: PASS (Zero overlapping channels)

[TEST 02] COLUMN-OVERWRITE WEATHER STATE TRANSITION MATRIX (w_new = w_old @ T_set_weather[k])
------------------------------------------------------------------------------------------------
  Weathers Index Map          : [(0, 'Clear'), (1, 'Sun'), (2, 'Rain'), (3, 'Sand'), (4, 'Snow')]
  Initial Vector w_old (Rain) : [0.0, 0.0, 1.0, 0.0, 0.0]  (Sum = 1.0)
  Operator Matrix T_set_weather[1 (Sun)] (shape 5x5):
               |  Clear    Sun   Rain   Sand   Snow
    ------------------------------------
    Clear      | [   0.00   1.00   0.00   0.00   0.00 ]
    Sun        | [   0.00   1.00   0.00   0.00   0.00 ]
    Rain       | [   0.00   1.00   0.00   0.00   0.00 ]
    Sand       | [   0.00   1.00   0.00   0.00   0.00 ]
    Snow       | [   0.00   1.00   0.00   0.00   0.00 ]
  Matrix Product w_old @ T[1] : [0.0, 1.0, 0.0, 0.0, 0.0]  -> Active Weather is now Sun (index 1)!
  Result: PASS (All 5x5 = 25 weather state transitions verified)

[TEST 03] WEATHER-TO-MOVE BILINEAR CONTRACTION (mult = w_onehot @ M_weather_mod @ m_type^T)
------------------------------------------------------------------------------------------------
  Operator Matrix M_weather_mod [5x18] (Showing first 6 types: Normal, Fire, Water, Grass, Electric, Ice):
               | Normal   Fire  Water  Grass Electric    Ice
    ---------------------------------------------
    Clear      | [   1.00   1.00   1.00   1.00   1.00   1.00 ]
    Sun        | [   1.00   1.50   0.50   1.00   1.00   1.00 ]
    Rain       | [   1.00   0.50   1.50   1.00   1.00   1.00 ]
    Sand       | [   1.00   1.00   1.00   1.00   1.00   1.00 ]
    Snow       | [   1.00   1.00   1.00   1.00   1.00   1.00 ]
  Step A1: w_sun  [0.0, 1.0, 0.0, 0.0, 0.0] @ M_weather_mod = [1.0, 1.5, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
  Step B1: (w_sun @ M_weather_mod) @ m_water [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] = 0.5000
  Step B2: (w_sun @ M_weather_mod) @ m_fire  [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] = 1.5000
  Step A2: w_rain [0.0, 0.0, 1.0, 0.0, 0.0] @ M_weather_mod = [1.0, 0.5, 1.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
  Step B3: (w_rain @ M_weather_mod) @ m_water = 1.5000 | @ m_fire = 0.5000
  Result: PASS

[TEST 04] TERRAIN BILINEAR CONTRACTION WITH GROUNDED GATE
------------------------------------------------------------------------------------------------
  Equation: mult = 1.0 + grounded_flag * ((t_onehot @ M_terrain_mod @ m_type^T) - 1.0)
  t_psychic [0.0, 0.0, 0.0, 1.0, 0.0] @ M_terrain_mod = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.2999999523162842, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
  Raw Contraction (t_psychic @ M @ m_psychic) = 1.3000
  With Grounded=1.0: 1.0 + 1.0 * (1.3000 - 1.0) = 1.3000
  With Grounded=0.0: 1.0 + 0.0 * (1.3000 - 1.0) = 1.0000
  Result: PASS

[TEST 05] DUAL-TYPE & SINGLE-TYPE MULTIPLICATIVE EFFECTIVENESS IDENTITY
------------------------------------------------------------------------------------------------
  Identity: eff1 = (m @ M_chart @ d1) | eff2 = (m @ M_chart @ d2) + (1.0 - sum(d2)) | total = eff1 * eff2
  • Ice vs Garchomp (Dragon + Ground)       : eff1=2.00 | raw_eff2=2.00 + (1 - sum_d2=1.0) -> eff2=2.00 | total = 2.00 * 2.00 = 4.00x
  • Ice vs Pure Dragon (Dragon + None)      : eff1=2.00 | raw_eff2=0.00 + (1 - sum_d2=0.0) -> eff2=1.00 | total = 2.00 * 1.00 = 2.00x
  • Poison Jab vs Grimmsnarl (Dark + Fairy) : eff1=1.00 | raw_eff2=2.00 + (1 - sum_d2=1.0) -> eff2=2.00 | total = 1.00 * 2.00 = 2.00x
  • Ground vs Charizard (Fire + Flying)     : eff1=2.00 | raw_eff2=0.00 + (1 - sum_d2=1.0) -> eff2=0.00 | total = 2.00 * 0.00 = 0.00x
  • Fire vs Kingdra (Water + Dragon)        : eff1=0.50 | raw_eff2=0.50 + (1 - sum_d2=1.0) -> eff2=0.50 | total = 0.50 * 0.50 = 0.25x
  • Fire vs Empoleon (Water + Steel)        : eff1=0.50 | raw_eff2=2.00 + (1 - sum_d2=1.0) -> eff2=2.00 | total = 0.50 * 2.00 = 1.00x
  Result: PASS

[TEST 06] STAB DOT PRODUCT CONTRACTION (is_stab = (atk_type1 + atk_type2) @ move_type)
------------------------------------------------------------------------------------------------
  Attacker Multi-Hot (Dragon + Ground) : [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
  • Ground Move Dot Product = 1.0 -> STAB = 1.0 + 0.5 * 1.0 = 1.50x (Adaptability: 2.00x)
  • Rock Move Dot Product   = 0.0 -> STAB = 1.0 + 0.5 * 0.0 = 1.00x
  Result: PASS

[TEST 07] 8x8 SWITCH PERMUTATION MATRIX (P_new = P_perm[0, 2] @ P_old)
------------------------------------------------------------------------------------------------
  Operator Matrix P_switch_perms[0, 2] (Swaps Active Slot 0 <-> Bench Slot 2):
               | P1A(0) P1B(1) P1_B1(2) P1_B2(3) P2A(4) P2B(5) P2_B1(6) P2_B2(7)
    -----------------------------------------------------------------
    P1A(0)     | [   0.00   0.00   1.00   0.00   0.00   0.00   0.00   0.00 ]
    P1B(1)     | [   0.00   1.00   0.00   0.00   0.00   0.00   0.00   0.00 ]
    P1_B1(2)   | [   1.00   0.00   0.00   0.00   0.00   0.00   0.00   0.00 ]
    P1_B2(3)   | [   0.00   0.00   0.00   1.00   0.00   0.00   0.00   0.00 ]
    P2A(4)     | [   0.00   0.00   0.00   0.00   1.00   0.00   0.00   0.00 ]
    P2B(5)     | [   0.00   0.00   0.00   0.00   0.00   1.00   0.00   0.00 ]
    P2_B1(6)   | [   0.00   0.00   0.00   0.00   0.00   0.00   1.00   0.00 ]
    P2_B2(7)   | [   0.00   0.00   0.00   0.00   0.00   0.00   0.00   1.00 ]
  Before Multiply -> Slot 0..7 HP_CUR  : [183.0, 0.0, 202.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  After Multiply  -> Slot 0..7 HP_CUR  : [202.0, 0.0, 183.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  Before Multiply -> Slot 0..7 Move0 BP: [75.0, 0.0, 120.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  After Multiply  -> Slot 0..7 Move0 BP: [120.0, 0.0, 75.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  Result: PASS

[TEST 08] FULL 100x100 GRID (10,000 CELLS) BATCH SPEED BENCHMARK (CPU vs CUDA)
------------------------------------------------------------------------------------------------
  • PyTorch (cpu   ) [100x100 = 10,000 cells] Mean Latency : 1.173 ms / pass
  • PyTorch (cuda:0) [100x100 = 10,000 cells] Mean Latency : 0.706 ms / pass
  Result: PASS

================================================================================================
TOTAL TESTS RUN: 8 | FAILURES: 0 | ERRORS: 0
STATUS: PASS (100% EXACT MATHEMATICAL PARITY)
================================================================================================
```
