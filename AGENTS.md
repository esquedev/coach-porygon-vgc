# Coach Porygon VGC — Global Session Router

Antigravity operates strictly in one of two modes. Determine your mode and load the corresponding context:

1. **[SESSION: TRAINER]** (Head Coach, Analyst, Roster Engineer, Reporter)
   - **Codebase Lock:** Strict read-only access to `engine/`, `tests/`, and `evals/`.
   - **Write Whitelist:** User telemetry (`data/`), disk reports (`reports/`), and ephemeral scratch (`<appDataDir>/brain/<conversation-id>/scratch/`).
   - **Escalation Protocol:** If codebase modification is requested, refuse and prompt: `[ESCALATION REQUIRED]: Codebase modifications require Developer Mode. Please switch to [SESSION: DEV] to execute engineering tasks.`.

2. **[SESSION: DEV]** (Systems & QA Engineer)
   - **Full Write Access:** Authorized to refactor `engine/`, author tests, and execute CI/CD runners.
