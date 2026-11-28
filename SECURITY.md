# Security Policy — Coach Porygon VGC

**Coach Porygon VGC** is a strictly local, non-commercial, open-source Pokémon VGC analytical suite. Protecting users who run our launchers and local web Studio is a top priority.

---

## 1. Verifying Official Releases (No `.exe` — Plain-Text Launchers Only)

We deliberately **do not ship compiled binaries**. Every official release contains only auditable source plus the plain-text launchers **[`start_replay_coach.bat`](start_replay_coach.bat)** (Windows) and **[`start_replay_coach.sh`](start_replay_coach.sh)** (Linux/macOS), so there is nothing opaque for SmartScreen / antivirus to flag and nothing to trust blindly.

Every GitHub Release (`CoachPorygonVGC-windows.zip`, `CoachPorygonVGC-linux-macos.tar.gz`) is:
- Built exclusively by [`.github/workflows/release.yml`](.github/workflows/release.yml) **only after** `origin/main` ancestry + the full test & anti-hallucination suite pass, with CI asserting the bundles contain **zero `.exe`**, a CRLF `.bat`, and an executable LF `.sh`.
- Published alongside a cryptographic **`SHA256SUMS.txt`** manifest.
- Signed with **GitHub SLSA Build Provenance Attestations** (`actions/attest-build-provenance`).

### Verify SHA-256 Checksum
```powershell
# Windows PowerShell
Get-FileHash .\CoachPorygonVGC-windows.zip -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```
```bash
# Linux / macOS
sha256sum -c --ignore-missing SHA256SUMS.txt   # (macOS: shasum -a 256 -c SHA256SUMS.txt)
```

### Verify GitHub Build Provenance (Optional, via GitHub CLI)
```bash
gh attestation verify CoachPorygonVGC-windows.zip --repo esquedev/coach-porygon-vgc
```

---

## 2. Built-In Defense-in-Depth Architecture

- **Loopback-Only Binding & DNS-Rebinding Defense:** `apps/replay_coach/server.py` binds exclusively to `127.0.0.1:8765` by default and validates the HTTP `Host` header against a strict loopback allowlist (`127.0.0.1`, `localhost`, `[::1]`).
- **Localhost CSRF Protection:** State-changing `POST` endpoints reject cross-site `Sec-Fetch-Site: cross-site`, untrusted `Origin`, and untrusted `Referer` headers (`403 Forbidden`).
- **Path Traversal & XSS Controls:** Static asset serving uses strict `Path.is_relative_to()` containment (rejecting null bytes, backslashes, and symlink escapes). Embedded Showdown replay logs apply case-insensitive `</script` and HTML comment escaping, and all responses emit `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: no-referrer`, and `Permissions-Policy`.
- **Memory DoS Cap:** JSON POST request bodies are hard-capped at `10 MiB` (`413 Payload Too Large`).
- **Launcher Binary-Planting & System-Python Isolation:** `start_replay_coach.bat` sets `NoDefaultCurrentDirectoryInExePath=1`, resolves `nvidia-smi` only from system paths / `PATH` (never the current folder), and both launchers enforce `PIP_REQUIRE_VIRTUALENV=1`, validate `--host`/`--port` (`.sh`), and never touch system-wide Python packages.
- **Zero-SQLi Persistence:** All user-facing DuckDB queries in `apps/replay_coach/ots_db.py` use strictly bound `?` parameters.

---

## 3. Reporting a Vulnerability

If you discover a security bug (in the launchers, HTTP server, replay parser, DuckDB persistence, or GitHub Actions workflows), please **do not open a public exploit issue**. Instead, email **`esquedevil94@gmail.com`** with:
- A concise description and reproduction steps.
- Affected file(s) and commit hash or release tag.

We will acknowledge reports promptly and release a patched version with full credit (unless you prefer anonymity).
