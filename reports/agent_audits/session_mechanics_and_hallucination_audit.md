# Coach Porygon VGC — Consolidated Session Mechanics & Hallucination Audit

**Last Consolidated:** 2026-11-19  
**Games Audited:** 11 Showdown Bo3 Games (Sets 1–4, `8–3` Match Record, Rating `1164 → 1247`)  
**Purpose:** Single-source-of-truth quality assurance registry for `[SESSION: TRAINER]` and `[SESSION: DEV]`. Consolidates all 11 match audits into:
1. **Deduplicated Master Issue Registry** (12 unique engineering issues across `src/engine/telemetry/extractor.py`, `src/engine/parser/showdown_parser.py`, `src/engine/cli.py`, and `src/engine/vgc_tensor_core/attack_cascade.py` — zero repeated entries).
2. **Consolidated Mechanics & Anti-Hallucination Ledger** (verified Regulation M-C mechanics, spread benchmarks, and coaching self-corrections).
3. **Condensed Match Audit Index & Physical Notebook Rules** (`Audits #1–#11`).

---

## 1. Deduplicated Master Issue Registry (For `[SESSION: DEV]`)
