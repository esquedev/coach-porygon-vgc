# Security Policy — Coach Porygon VGC

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Hardening Architecture

Coach Porygon VGC implements strict defensive guardrails against LLM and web application vulnerabilities:
1. **OWASP LLM01 Untrusted Input Isolation:** All Showdown replay strings, nicknames, and chat messages are treated as inert strings. They are never interpolated into execution contexts.
2. **Path Traversal & Restricted Systems (SEC-03):** The local Command Center server (`engine/ui_server.py`) denies access (403 Forbidden) to `.git`, `.github`, `.agents`, and sensitive local profiles (`trainer_profile.json`).
3. **Strict Origin & Localhost CORS (SEC-01 / SEC-02):** API endpoints restrict Cross-Origin Resource Sharing strictly to loopback origins (`localhost`, `127.0.0.1`) and local `null` file origins.
4. **Denial-of-Service Defense (SEC-06):** Ingestion endpoints cap inbound POST request bodies at 5 MB (`413 Payload Too Large`).
5. **CSV Formula Injection Shield (CWE-1236):** All persistent spreadsheet writes in `engine/repositories.py` sanitize dangerous formula prefixes (`=`, `@`, `+`, `-`, `\t`, `\r`).
6. **SVG Active Script Eradication (SEC-05):** Digital vector assets in `assets/` are statically verified to contain zero `<script>` tags, inline event handlers (`onload`, `onerror`), or `javascript:` URIs.

## Reporting a Vulnerability

If you discover a security vulnerability or bypass of our deterministic guardrails:
1. **Do not create a public GitHub issue.**
2. Send a responsible disclosure report directly to the repository maintainer via the contact email listed on the lead developer's [GitHub profile (@esquedev)](https://github.com/esquedev).
3. Include detailed steps to reproduce the vulnerability, sample inputs, and potential impact.
4. You will receive an acknowledgment within 48 hours, followed by a remediation timeline.
