# Security Policy — Coach Porygon VGC

**Coach Porygon VGC** is a strictly local, non-commercial, open-source Pokémon VGC analytical suite. Protecting users who run our Windows `.exe` launcher and local web Studio is a top priority.

---

## 1. Verifying Official Windows Releases (`CoachPorygonStudio.exe`)

Every official GitHub Release of `CoachPorygonStudio.exe` and `CoachPorygonVGC-windows-x64.zip` is:
- Compiled exclusively on GitHub's hosted `windows-latest` runners via [`.github/workflows/build-windows-launcher.yml`](.github/workflows/build-windows-launcher.yml) **only after** `origin/main` ancestry + the full test & anti-hallucination suite pass.
- Published alongside a cryptographic **`SHA256SUMS.txt`** manifest.
- Signed with **GitHub SLSA Build Provenance Attestations** (`actions/attest-build-provenance`).

### Verify SHA-256 Checksum (Windows PowerShell)
```powershell
Get-FileHash .\CoachPorygonStudio.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```
Confirm the hex hash matches `SHA256SUMS.txt` byte-for-byte.

### Verify GitHub Build Provenance (Optional, via GitHub CLI)
```bash
gh attestation verify CoachPorygonStudio.exe --repo esquedev/coach-porygon-vgc
```

### Why Does Windows SmartScreen Sometimes Warn About `.exe` Files?
Because **Coach Porygon VGC is a 100% fan-made, non-commercial project**, we do not purchase paid EV Code Signing certificates. Unsigned PyInstaller `.exe` wrappers are commonly flagged by Windows SmartScreen as "Unknown publisher."
- You can verify the `.exe` using the SHA-256 / GitHub attestation checks above, **or**
- Skip the `.exe` entirely and run the plain-text, human-auditable launcher **[`start_replay_coach.bat`](start_replay_coach.bat)** (Windows) or **[`start_replay_coach.sh`](start_replay_coach.sh)** (Linux/macOS) directly!

---

## 2. Built-In Defense-in-Depth Architecture

- **Loopback-Only Binding & DNS-Rebinding Defense:** `apps/replay_coach/server.py` binds exclusively to `127.0.0.1:8765` by default and validates the HTTP `Host` header against a strict loopback allowlist (`127.0.0.1`, `localhost`, `[::1]`).
- **Localhost CSRF Protection:** State-changing `POST` endpoints reject cross-site `Sec-Fetch-Site: cross-site`, untrusted `Origin`, and untrusted `Referer` headers (`403 Forbidden`).
- **Path Traversal & XSS Controls:** Static asset serving uses strict `Path.is_relative_to()` containment (rejecting null bytes, backslashes, and symlink escapes). Embedded Showdown replay logs apply case-insensitive `</script` and HTML comment escaping, and all responses emit `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: no-referrer`, and `Permissions-Policy`.
- **Memory DoS Cap:** JSON POST request bodies are hard-capped at `10 MiB` (`413 Payload Too Large`).
- **Windows Binary-Planting & System-Python Isolation:** `apps/replay_coach/launcher_entry.py` sets `NoDefaultCurrentDirectoryInExePath=1` on Windows, refuses to execute loose `python.exe`/`nvidia-smi.exe` files placed inside the repository folder, enforces `PIP_REQUIRE_VIRTUALENV=1`, and never touches system-wide Python packages.
- **Zero-SQLi Persistence:** All user-facing DuckDB queries in `apps/replay_coach/ots_db.py` use strictly bound `?` parameters.

---

## 3. Reporting a Vulnerability

If you discover a security bug (in the launcher, HTTP server, replay parser, DuckDB persistence, or GitHub Actions workflows), please **do not open a public exploit issue**. Instead, email **`esquedevil94@gmail.com`** with:
- A concise description and reproduction steps.
- Affected file(s) and commit hash or release tag.

We will acknowledge reports promptly and release a patched version with full credit (unless you prefer anonymity).
