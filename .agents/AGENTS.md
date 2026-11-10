# Engine Architecture & Development Rules [SESSION: DEV]

Canonical engineering standards for `src/engine/` and associated mathematical engines:

1. **Domain Core Isolation:**
   - Modules in `src/engine/` represent pure domain logic, statistical mathematics, and tensor contractions.
   - Maintain ZERO dependencies on web frameworks (Flask, FastAPI), external network requests, or UI rendering.

2. **Type Safety & Documentation:**
   - All public classes, interfaces, tensor dimensions, and math pipelines must use strict PEP 484 type annotations.
   - All modules, classes, and public methods must include comprehensive PEP 257 docstrings.

3. **Format Grounding & Invariants (Regulation M-C):**
   - **Level 50 Scaling:**
     $$\text{HP} = \left\lfloor \frac{(2 \cdot \text{Base} + 31 + \lfloor \text{SP} / 4 \rfloor) \cdot 50}{100} \right\rfloor + 60$$
     $$\text{Stat} = \left\lfloor \left( \left\lfloor \frac{(2 \cdot \text{Base} + 31 + \lfloor \text{SP} / 4 \rfloor) \cdot 50}{100} \right\rfloor + 5 \right) \cdot \text{NatureMult} \right\rfloor$$
   - **Stat Points (SP):** Exactly 66 total SP budget per Pokémon; maximum 32 SP per stat.
   - **IVs:** Mandatory 31 IVs.
   - **Mechanics:** Mega Evolution resolves at Priority `+5.5` with instantaneous speed tier recalculation. Terastallization is strictly forbidden.

4. **Identifier Convention:**
   - Use `trainer_1` (POV player) and `trainer_2` (opponent player) exclusively throughout the entire codebase.
   - Never introduce `p1` or `p2`.

5. **In-Memory DuckDB Integration:**
   - Query all Pokémon, moves, abilities, items, and regional tournament usage through `VGCDataRegistry` (`engine.db_registry.get_registry()`).
   - Do not create hardcoded move tables or load raw `.jsonl` files in domain code.

6. **Discrete-RNG Fidelity:**
   - Never replace discrete cartridge luck with deterministic averages (no expected-value smearing).
   - Use the Dual-Draw Spinning-Wheel on `[0, 100)` with Counter-Based SplitMix64 scrambling for all events:
     - Accuracy checks
     - Critical hit stages: Stage 0 ($1/24 \approx 4.17\%$), Stage 1 ($12.5\%$), Stage 2 ($50\%$), Stage 3 ($100\%$)
     - 16 Cartridge Damage Rolls: discrete uniform draw from $\{85, 86, \dots, 100\} / 100.0$
     - Multi-hit distributions: 35/35/15/15 or Loaded Dice 50/50
     - Secondary status, stat drops, flinch, and speed ties (50/50)

7. **Risk-Resilient Downside Modeling:**
   - Always evaluate downside risk via Conditional Value at Risk ($CVaR_{0.10}$):
     $$U_{\text{risk}} = (1 - \lambda) \cdot \mathbb{E}[U] + \lambda \cdot CVaR_{0.10}[U], \quad \lambda = 0.25$$

8. **Scratch Isolation Protocol:**
   - Never write temporary scratch scripts or debug dumps into `src/engine/` or the repository root.
   - Route all intermediate dumps to `<appDataDir>/brain/<conversation-id>/scratch/` or `data/`.
