# Engine Architecture Rules [SESSION: DEV]

1. **Domain Core Isolation:** This directory contains pure domain logic.
2. **Type Safety & Documentation:** All public interfaces and math pipelines must use PEP 484 type annotations and PEP 257 docstrings.
3. **Format Grounding:** All mathematical models must adhere to Regulation M-C rules, enforcing the 66-SP limit (max 32 SP per stat) and Level 50 scaling formulas.
4. **Scratch Protocol:** Never place temporary scripts here. Route all intermediate dumps to `<appDataDir>/brain/<conversation-id>/scratch/`.
