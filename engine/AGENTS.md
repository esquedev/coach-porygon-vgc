# Engine Architecture Rules [SESSION: DEV]

1. **Domain Core Isolation:** `engine/turn_simulator.py`, `engine/sp_calculator.py`, and `engine/validate_roster.py` are pure domain logic. They must maintain ZERO dependencies on Flask, web frameworks, HTML rendering, or external network packages.
2. **Format Grounding:** All mathematical calculations must strictly enforce Regulation M-C limits: exactly 66 total Stat Points (SP) per Pokémon and a maximum of 32 SP per single stat. 
3. **Type Safety & Documentation:** All public interfaces, math pipelines, and domain services must declare strict PEP 484 type hints and PEP 257 docstrings.
4. **Scratch Isolation Protocol:** Never drop temporary debugging scripts, patch files, or intermediate state dumps into `engine/` or the workspace root. Route all exploratory executions strictly to `<appDataDir>/brain/<conversation-id>/scratch/` or use `python -c "..."`.
