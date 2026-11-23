# Engine Architecture & Development Rules [SESSION: DEV]

Canonical engineering standards for `src/engine/` and associated mathematical engines:

1. **Domain Core Isolation & Data Ingestion Boundary:**
   - Core simulation, mathematical, and inference modules (`src/engine/vgc_tensor_core/`, `src/engine/solver/`, `src/engine/state/`, `src/engine/modes/`, `src/engine/inference/`, `src/engine/parser/`, `src/engine/telemetry/`) represent pure domain logic, statistical mathematics, and tensor contractions with ZERO dependencies on web frameworks (Flask, FastAPI), live network requests, or UI rendering.
   - **Sanctioned Ingestion Pipeline:** `src/engine/munchstats_pipeline/` is the canonical stdlib-only (`urllib`) tournament ingestion module authorized to fetch MunchStats tournament archives into `src/engine/data/munchstats/raw/archive/` for DuckDB consumption.
   - All web servers, GUI assets, and standalone user applications (e.g., `apps/replay_coach/`) MUST live strictly under `apps/` and consume `src/engine/` through its public APIs.

2. **Type Safety & Documentation:**
   - All public classes, interfaces, tensor dimensions, and math pipelines must use strict PEP 484 type annotations.
   - All modules, classes, and public methods must include comprehensive PEP 257 docstrings.

3. **Format Grounding & Invariants (Regulation M-C):**
   - **Level 50 Champions Stat Formulas (Mandatory 31 IVs):**
     $$\text{HP} = \text{Base} + \text{SP} + 75$$
     $$\text{Stat} = \left\lfloor (\text{Base} + \text{SP} + 20) \cdot \text{NatureMult} \right\rfloor$$
     Equivalent cartridge EV conversion: $\text{EV} = 0$ if $\text{SP} = 0$, and $\text{EV} = 4 + 8 \cdot (\text{SP} - 1)$ for $1 \le \text{SP} \le 32$.
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
     - Multi-hit distributions: 35/35/15/15 standard cartridge wheel (or guaranteed 5 hits with Skill Link)
     - Secondary status, stat drops, flinch, and speed ties (50/50)

7. **Risk-Resilient Downside Modeling:**
   - Always evaluate downside risk via Conditional Value at Risk ($CVaR_{0.10}$):
     $$U_{\text{risk}} = (1 - \lambda) \cdot \mathbb{E}[U] + \lambda \cdot CVaR_{0.10}[U], \quad \lambda = 0.25$$

8. **Scratch Isolation Protocol:**
   - Never write temporary scratch scripts or debug dumps into `src/engine/` or the repository root.
   - Route all intermediate dumps to `<appDataDir>/brain/<conversation-id>/scratch/` or `data/`.
