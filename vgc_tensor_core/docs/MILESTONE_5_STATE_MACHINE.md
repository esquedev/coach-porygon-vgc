# Milestone 5: End-of-Turn & Unified VGC Tensor State Machine

## 1. Overview & Architectural Principles
Milestone 5 (`vgc_tensor_core/state_machine.py`) completes the full VGC Doubles turn cycle by implementing **Phase 5 (End-of-Turn Resolution)** and unifying the entire 5-phase engine into a single, high-level, branchless class: `VgcTensorStateMachine`.

```
           INITIAL STATE VECTOR [F, P, M] & JOINT ACTIONS [p1, p2]
                                      │
                                      ▼
           [PHASES 1–3: PRE-ATTACK SYNCHRONIZATION BARRIERS]
           • Barrier 1: Switches & Speed-Sorted Entry Abilities (+6)
           • Barrier 2: Mega Evolution & Instantaneous Speed (+5.5)
           • Barrier 3: Effective Speed, Priority & Seeded Jitter Sort
                                      │
                                      ▼
           [PHASE 4: 4-STEP VECTORIZED ATTACK CASCADE]
           • Steps 0..3: Action Gating & Guards
           • Follow Me & KO Target Redirection XOR
           • Level 50 Damage Formula across K=16 Monte Carlo Rolls
           • Focus Sash / Sturdy Clamping & Recoil/Drain Dynamics
                                      │
                                      ▼
           [PHASE 5: END-OF-TURN RESOLUTION & REPLACEMENTS]
           • Sandstorm Chip (-1/16) & Status Chip (Burn, Poison, Toxic)
           • Grounded Grassy Terrain (+1/16) & Leftovers (+1/16) Healing
           • Field & Side Counter Decrements (Weather, Terrain, Tailwind)
           • Protect Consecutive Counter Resets
           • Compiler Tactical Prior Auto-Replacements for Fainted Slots
           • Match Termination & Winner Evaluation
                                      │
                                      ▼
              END-OF-TURN STEP RESULT [Next_F, Next_P, Next_M]
```

---

## 2. Phase 5 Mathematical Specifications

### 2.1. Residual Chip Damage
* **Sandstorm Weather Chip:**
  $$\Delta HP_{\text{Sand}} = \left\lfloor \frac{HP_{\max}}{16} \right\rfloor \cdot \mathbb{I}(\text{Weather} == \text{Sand}) \cdot (1 - \mathbb{I}_{\text{Rock/Ground/Steel}}) \cdot (1 - \mathbb{I}_{\text{SafetyGoggles}})$$
* **Burn Chip:**
  $$\Delta HP_{\text{Burn}} = \left\lfloor \frac{HP_{\max}}{16} \right\rfloor \cdot \mathbb{I}(\text{STATUS\_BURN} == 1.0)$$
* **Poison Chip:**
  $$\Delta HP_{\text{Poison}} = \left\lfloor \frac{HP_{\max}}{8} \right\rfloor \cdot \mathbb{I}(\text{STATUS\_POISON} == 1.0)$$
* **Toxic Escalating Chip:**
  $$\Delta HP_{\text{Toxic}} = \left\lfloor \frac{HP_{\max} \cdot \text{TOXIC\_COUNTER}}{16} \right\rfloor \cdot \mathbb{I}(\text{STATUS\_TOXIC} == 1.0)$$
  * Followed by `TOXIC_COUNTER += 1.0`.

---

### 2.2. Residual Healing (Airborne Exemption)
* **Grassy Terrain Healing:**
  $$\Delta HP_{\text{Grassy}} = \left\lfloor \frac{HP_{\max}}{16} \right\rfloor \cdot \mathbb{I}(\text{Terrain} == \text{Grassy}) \cdot \mathbb{I}(\text{GROUNDED\_FLAG} == 1.0)$$
  * Flying-type and `Levitate` slots (`GROUNDED_FLAG == 0.0`) receive **zero** healing, adhering strictly to cartridge rules.
* **Leftovers Healing:**
  $$\Delta HP_{\text{Leftovers}} = \left\lfloor \frac{HP_{\max}}{16} \right\rfloor \cdot \mathbb{I}(\text{ITEM\_ID} == \text{LEFTOVERS}) \cdot \mathbb{I}(\text{ITEM\_ACTIVE} == 1.0)$$

---

### 2.3. Field Counter Decrements & Volatile Resets
* **Turn Decrement:**
  $$C_{t+1} = \max(0.0, C_t - 1.0)$$
  * If Weather turns reach 0, weather automatically resets to Clear (`W_CLEAR = 0`).
  * If Terrain turns reach 0, terrain automatically resets to None (`T_NONE = 0`).
  * If Tailwind / Screen turns reach 0, side flags reset to 0.
* **Protect Counter Reset:**
  If an active slot did **not** execute Protect/Wide/Quick Guard this turn:
  $$\text{PROTECT\_COUNTER} \leftarrow 0.0$$
  If it did execute Protect: $\text{PROTECT\_COUNTER}$ is preserved for next-turn decay calculations.

---

### 2.4. Compiler Tactical Prior Auto-Replacement Heuristic
If active slot $A$ faints ($HP_{\text{cur}} \le 0$):
1. If only one bench slot is alive, it is immediately promoted.
2. If both bench slots ($B_1, B_2$) are alive, the engine evaluates their relative board equity and promotes the slot with higher speed/equity:
   $$B^* = \begin{cases} B_1 & \text{if } \text{Speed}(B_1) \ge \text{Speed}(B_2) \\ B_2 & \text{otherwise} \end{cases}$$
3. An in-place tensor swap executes between slot $A$ and slot $B^*$.

---

## 3. Unified Engine API (`VgcTensorStateMachine`)

```python
from vgc_tensor_core.state_machine import VgcTensorStateMachine

sm = VgcTensorStateMachine(backend="torch")  # Auto-selects CUDA RTX 3060 if available

step_res = sm.step(
    F=field_tensor,
    P=roster_tensor,
    M_moves=moves_tensor,
    p1_choices=p1_choices,
    p2_choices=p2_choices,
    num_mc_samples=16,
)

print("Next Field Shape:", step_res.F.shape)
print("Mean HP Vector:", step_res.mean_hp)
print("Faint Probabilities:", step_res.faint_prob)
print("Match Finished:", step_res.is_terminal)
```

---

## 4. Test Suite Verification & Benchmarks

### 4.1. Unit Test Matrix (`vgc_tensor_core/tests/test_milestone5_state_machine.py`)
- **[TEST 1] End-of-Turn Chip Damage:** PASS (P1A took Burn -10 HP and Sandstorm -10 HP).
- **[TEST 2] Grassy Terrain & Leftovers Healing:** PASS (Grounded healed +20 HP; Airborne took 0 HP).
- **[TEST 3] Field Counter Decrements:** PASS (Weather reset to Clear; Terrain & Tailwind decremented).
- **[TEST 4] Protect Streak Reset:** PASS (Non-protecting slot counter reset to 0.0; protecting slot preserved).
- **[TEST 5] Compiler Auto-Replacement Heuristic:** PASS (Fainted slot auto-replaced by living bench slot).
- **[TEST 6] Full Turn 1 End-to-End Step:** PASS (Full turn executed cleanly with 16 Monte Carlo samples).

### 4.2. Performance Benchmarks ($1,024 \text{ cells} \times 16 \text{ K-samples} = 16,384 \text{ simulations}$)
- **NumPy CPU Latency:** `522.59 ms` per pass.
- **PyTorch CUDA Latency (RTX 3060):** `791.78 ms` per pass.
