# Test Engineering & QA Rules [SESSION: DEV]

1. **Dual-Tier Test Segregation:** Maintain strict separation of concerns.
   - `tests/testUT/`: Fast, in-memory unit tests with mocked I/O and zero network calls. 
   - `tests/testAT/`: End-to-end acceptance, integration, multi-turn simulations, and live endpoint probing.
2. **1-to-1 Class Parity:** Every production class must have a corresponding test file named exactly `test_<TargetClass>.py`. Monolithic, multi-class test catch-alls are prohibited.
3. **Graceful Degradation:** Any module utilizing optional heavy dependencies (e.g., `torch`, `scipy`) must implement graceful degradation imports (`try ... except ImportError`) and shield tests using `@unittest.skipUnless` to prevent collection failures in minimal CI environments.
4. **100% Green Mandate:** Developers must run the standard CI runner (`run_tests.cmd` or `run_tests.sh`) and pass all 5 phases before concluding any feature or bugfix task.
