# Milestone 4: Vectorized Attack Cascade Engine

## 1. Overview & Architectural Principles
Milestone 4 (`vgc_tensor_core/attack_cascade.py`) implements **Phase 4 (The 4-Step Vectorized Attack Cascade)** of an official Pokémon VGC 4v4 Doubles turn (Regulation M-C). It operates seamlessly on CPU and CUDA (`NVIDIA GeForce RTX 3060 Laptop GPU`) with zero runtime dependencies on legacy code (`engine/`).

```
                    PRE-ATTACK STATE (BARRIERS 1-3)
                                  │
                                  ▼
           [Step 0] ──► [Step 1] ──► [Step 2] ──► [Step 3]
              │            │            │            │
              ├────────────┴────────────┴────────────┤
              ▼                                      ▼
    [TARGETING & DEFENSE]                  [DAMAGE FORMULA & K-ROLLS]
    • Follow Me Redirection                • 16 Discrete Cartridge Rolls [0.85..1.00]
    • KO Redirection XOR                   • STAB (1.5x / 2.0x Adaptability)
    • Protect / Wide Guard / Quick Guard   • Type Chart Bilinear Contraction
    • Flinch / Faint Action Gates          • Focus Sash / Sturdy 1 HP Clamping
              │                                      │
              └──────────────────┬───────────────────┘
                                 ▼
                     [RECOIL, DRAIN & PIVOTS]
                     • Life Orb (-10% Max HP) & Move Recoil (-33%)
                     • Move Drain Healing (+75% Damage Dealt)
                     • Voluntary Self-Pivots (U-turn Bench Swap)
                     • Monte Carlo Aggregation & Variance Alerts
```

---

## 2. Core Mathematical Operators & Formulae

### 2.1. K-Sample Monte Carlo ($K=16$) Cartridge Damage Formula
Each Monte Carlo timeline $k \in \{0, \dots, K-1\}$ maps to a discrete 16-point cartridge roll:
$$R_k = \frac{85 + (k \bmod 16)}{100.0} \in \{0.85, 0.86, \dots, 1.00\}$$

The Level-50 damage formula evaluates with sequential integer floor truncations:
$$\text{Base} = \left\lfloor \frac{22 \cdot \text{Power} \cdot \frac{A}{D}}{50} \right\rfloor + 2$$
$$\text{Damage}_k = \left\lfloor \text{Base} \cdot \text{Spread} \cdot \text{Weather} \cdot \text{Terrain} \cdot R_k \cdot \text{STAB} \cdot \text{TypeEff} \cdot \text{Burn} \cdot \text{Item} \right\rfloor$$

Where:
- $A$: Attack (Physical) or Sp. Atk (Special), scaled by stat stage multiplier $M(\text{stage}) \in \left[\frac{2}{8}, \frac{8}{2}\right]$, `Huge Power` ($2.0\times$), `Guts` ($1.5\times$), `Choice Band/Specs` ($1.5\times$).
- $D$: Defense (Physical) or Sp. Def (Special), scaled by stat stage multiplier and `Assault Vest` ($1.5\times$).
- $\text{Spread}$: $0.75\times$ if multi-target attack hitting $>1$ alive target.
- $\text{Weather}$: Bilinear scaling from `tables.m_weather_mod [5, 18]` ($1.5\times$ or $0.5\times$).
- $\text{Terrain}$: Bilinear scaling from `tables.m_terrain_mod [5, 18]` ($1.3\times$ on grounded).
- $\text{STAB}$: $1.5\times$ ($2.0\times$ if `Adaptability`).
- $\text{TypeEff}$: Bilinear contraction $(m_{\text{type}} \mathbf{M}_{\text{type}} d_{\text{type1}}) \cdot (m_{\text{type}} \mathbf{M}_{\text{type}} d_{\text{type2}})$.
- $\text{Burn}$: $0.5\times$ on physical attacks unless attacker has `Guts`.
- $\text{Item}$: `Life Orb` deals $1.3\times$ damage.

---

### 2.2. Focus Sash & Sturdy 1 HP Clamping
If defender begins the hit at full health ($HP_{\text{cur}} \ge HP_{\max}$) and incoming damage is lethal ($\text{Damage}_k \ge HP_{\text{cur}}$):
$$\text{Damage}_k \leftarrow HP_{\text{cur}} - 1.0$$
$$\text{ITEM\_ACTIVE} \leftarrow 0.0 \quad (\text{Focus Sash consumed})$$

---

### 2.3. KO Target Redirection XOR
In doubles, when a single-target attack is declared against slot $T_1$, but $T_1$ faints earlier in the turn ($HP_{\text{cur}}(T_1) \le 0$):
$$\text{Target} = \begin{cases} T_2 & \text{if } HP_{\text{cur}}(T_2) > 0 \\ \varnothing & \text{if } HP_{\text{cur}}(T_2) \le 0 \quad (\text{attack fails}) \end{cases}$$

---

### 2.4. Recoil & Drain Dynamics
- **Life Orb:** Attacker loses $\lfloor 0.10 \cdot HP_{\max} \rfloor$ upon dealing damage.
- **Move Recoil (Flare Blitz, Brave Bird):** Attacker loses $\max(1, \lfloor \text{Damage}_k \cdot \text{recoil\_pct} \rfloor)$.
- **Move Drain (Draining Kiss, Giga Drain):** Attacker heals $\max(1, \lfloor \text{Damage}_k \cdot |\text{recoil\_pct}| \rfloor)$ clamped to $HP_{\max}$.

---

### 2.5. Empirical KO Probability & Variance Alert
Over $K=16$ Monte Carlo samples:
$$P(\text{faint}) = \frac{1}{K} \sum_{k=0}^{K-1} \mathbb{I}(HP_{\text{cur}, k} \le 0.0)$$
$$\text{roll\_variance\_alert} = \begin{cases} 1.0 & \text{if } 0.0 < P(\text{faint}) < 1.0 \\ 0.0 & \text{otherwise} \end{cases}$$

---

## 3. Test Suite Verification & Performance Benchmarks

### 3.1. Unit Test Matrix (`vgc_tensor_core/tests/test_milestone4_attack_cascade.py`)
- **[TEST 0] Follow Me Single-Target Redirection:** PASS (Redirected attack away from P2A to P2B).
- **[TEST 1] Focus Sash & Sturdy 1 HP Clamping:** PASS (Lethal damage clamped to 1 HP, Sash consumed).
- **[TEST 2] KO Target Redirection XOR:** PASS (Attacks automatically redirected to surviving partner).
- **[TEST 3] Life Orb Recoil and Move Drain Healing:** PASS (10% Life Orb recoil applied, 75% Drain heal applied).
- **[TEST 4] Monte Carlo Roll Variance Alert:** PASS (Triggered on damage threshold straddling rolls with $P(\text{faint}) = 81.2\%$).
- **[TEST 5] Mid-Turn Voluntary Pivot (U-turn):** PASS (Swapped active attacker with bench slot in-place).

### 3.2. Performance Benchmarks ($10,000 \text{ cells} \times 16 \text{ K-samples} = 160,000 \text{ simulations}$)
- **NumPy CPU Latency:** `6,228.38 ms` (equivalent to `~420 ms` for a $26 \times 26 = 676$ joint action matrix).
- **PyTorch CUDA Latency (RTX 3060):** `11,455.23 ms`.
