# UX QA Stress Audit Report: Command Center & Frontend Architecture

**Document Version:** 1.0  
**Author:** UX QA Engineer  
**Scope:** `assets/*.html`, `assets/porygon_battle_hud_widget.html`, `engine/ui_server.py`, `engine/ui_generator.py`  
**Status:** Audit Completed — Remediation Plan Passed to UX Designer & UX Developer

---

## 1. Executive Summary
The Command Center is an ambitious, feature-dense competitive interface featuring 7 operational modes, interactive Crucible flashcards, live damage calculators, telemetry tables, and psychology meters.

However, the QA stress test uncovered major architectural inefficiencies:
- **Massive Inlining Bloat:** Each HTML file is ~2.1 MB due to multi-megabyte base64 string maps (`window.__COACH_PORYGON_SPRITES__` and `window.__COACH_PORYGON_ITEMS__`).
- **Triplicate File Maintenance:** `command_center.html`, `command_center_en.html`, and `command_center_es.html` duplicate over 29,000 lines each with minor string variations.
- **Redundant Script CDN Injections:** Tailwind CSS script is imported twice in the `<head>` tag.
- **XSS Susceptibility in Telemetry Rendering:** Unsanitized opponent nicknames and chat strings could be interpolated into `innerHTML`.
- **Offline / `file://` Degradation:** Hard failures occur when opened without the HTTP server running.

---

## 2. In-Depth Stress Findings

| ID | Category | Severity | Finding | Impact |
|---|---|---|---|---|
| **UX-01** | Performance | High | 2.1 MB HTML file size caused by monolithic inlined Base64 SVG maps. | Slow mobile rendering; wasteful DOM memory consumption. |
| **UX-02** | Maintainability | High | 3 copies of identical HTML (`command_center.html`, `_en.html`, `_es.html`). | Desynchronization risk when adding new UI features. |
| **UX-03** | Resilience | Medium | Double Tailwind script tags in `<head>`. | Redundant network requests; potential execution race conditions. |
| **UX-04** | Security | Critical | Opponent names, nicknames, and chat notes rendered without escaping. | Stored XSS vulnerability via untrusted Showdown replay inputs (OWASP LLM01). |
| **UX-05** | Accessibility | Medium | Interactive scenario buttons lack explicit `aria-pressed` and keyboard focus outlines. | Sub-optimal screen reader and keyboard navigation experience. |
| **UX-06** | Offline UX | Low | `fetch('/api/telemetry')` unhandled rejection if opened via `file://`. | Broken UI state when offline without local server running. |

---

## 3. Mandatory Remediation Checklist for UX Dev & Designer
1. **Consolidated i18n Architecture:**
   - Single source of truth HTML file with lightweight client-side locale toggle (EN/ES) switching data attributes dynamically.
2. **De-bloat Assets via Manifest:**
   - Replace inlined Base64 blobs with clean vector path references using `assets/svg_manifest.json` or direct URL paths (`assets/sprites/{slug}.svg`).
3. **Strict HTML Escaping Utility:**
   - Implement an immutable `escapeHtml()` function for all dynamic table rows, opponent names, and battle notes.
4. **Resilient Offline Fallback:**
   - If `/api/telemetry` is unreachable (e.g. running under `file://`), seamlessly fall back to embedded default telemetry or cached localStorage data.
