# Test Engineering & QA Rules [SESSION: DEV]

1. **Dual-Tier Test Segregation (Target Architecture):** Maintain strict separation between fast unit verification and end-to-end integration tests:
   - `tests/unit/`: Fast, in-memory unit tests with mocked I/O and zero network calls.
   - `tests/integration/`: End-to-end simulations, DuckDB registry verification, CLI/Replay Coach pipelines, and multi-turn replay verifiers.
   - *(Transition note: Existing suites under `tests/vgc_tensor_core/`, `tests/engine/`, and `tests/test_*.py` are scheduled to be consolidated into `tests/unit/` and `tests/integration/`.)*
2. **Identifier & Format Compliance:** All fixtures, assertions, and mocks must strictly use `trainer_1` / `trainer_2` (never `p1` / `p2`) and enforce Regulation M-C invariants (66 SP total, 32 SP cap per stat, 31 IVs, Mega Priority `+5.5`, zero Terastallization).
3. **Graceful Degradation:** Any test exercising optional heavy dependencies (e.g., `torch`, `scipy`, CUDA) must guard imports cleanly or fall back to CPU so collection never breaks on CPU-only laptops or minimal CI environments.
4. **100% Green Mandate:** Execute the full pytest suite via `PYTHONPATH=src:. .venv/bin/pytest tests/ -q` and confirm every test passes before concluding any engineering task.
