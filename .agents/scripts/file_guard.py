"""PreToolUse file & command guardrail for Coach Porygon VGC."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

PROTECTED_PREFIXES = (
    "src/engine/",
    "apps/",
    "tests/",
    "evals/",
    ".agents/rules/",
)
PROTECTED_FILES = {
    "pyproject.toml",
    "requirements.txt",
}
BANNED_COMMANDS = (
    "Remove-Item",
    "rm -rf",
    "del ",
    "git clean",
    "git checkout --",
)


def _to_repo_relative(raw_path: str) -> str:
    """Normalize an absolute or relative path into a POSIX repo-relative path."""
    cleaned = raw_path.replace("\\", "/").strip()
    if not cleaned:
        return ""
    try:
        resolved = Path(cleaned).resolve()
        return resolved.relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return cleaned.lstrip("./")


def main() -> None:
    payload = json.load(sys.stdin)
    tool = payload.get("toolCall", {})
    name = tool.get("name", "")
    args = tool.get("args", {})

    # 1. Block destructive shell commands globally
    if name == "run_command":
        cmd = str(args.get("CommandLine", ""))
        for banned in BANNED_COMMANDS:
            if banned in cmd:
                print(
                    json.dumps(
                        {
                            "decision": "deny",
                            "reason": f"Blocked destructive command: {banned}. Strict non-restoration guardrail active.",
                        }
                    )
                )
                sys.exit(0)

    # 2. Enforce codebase lock (require explicit human approval on core infrastructure paths)
    if name in ("edit_file", "write_file"):
        rel_path = _to_repo_relative(str(args.get("Path", "")))
        if rel_path in PROTECTED_FILES or any(rel_path.startswith(p) for p in PROTECTED_PREFIXES):
            print(
                json.dumps(
                    {
                        "decision": "force_ask",
                        "reason": f"Protected infrastructure path '{rel_path}' requires [SESSION: DEV] or explicit human approval.",
                    }
                )
            )
            sys.exit(0)

    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
