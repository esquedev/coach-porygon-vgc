import json
import sys

def main():
    payload = json.load(sys.stdin)
    tool = payload.get("toolCall", {})
    name = tool.get("name", "")
    args = tool.get("args", {})

    # 1. Block destructive shell commands globally
    if name == "run_command":
        cmd = args.get("CommandLine", "")
        banned_commands = ["Remove-Item", "rm -rf", "del ", "git clean", "git checkout --"]
        for banned in banned_commands:
            if banned in cmd:
                print(json.dumps({
                    "decision": "deny", 
                    "reason": f"Blocked destructive command: {banned}. Strict non-restoration guardrail active."
                }))
                sys.exit(0)

    # 2. Enforce Trainer Mode codebase lock (force human approval on core files)
    if name in ("edit_file", "write_file"):
        path = args.get("Path", "").replace("\\", "/")
        protected_paths = [
            "engine/", 
            "tests/", 
            "evals/", 
            "pyproject.toml", 
            "requirements.txt", 
            ".agents/rules/"
        ]
        
        # Only command_center.html, scratch/, and specific data/ paths are freely writable in Trainer mode
        if any(path.startswith(p) for p in protected_paths):
            print(json.dumps({
                "decision": "force_ask", 
                "reason": f"Protected infrastructure path '{path}' requires [SESSION: DEV] or explicit human approval."
            }))
            sys.exit(0)

    print(json.dumps({"decision": "allow"}))

if __name__ == "__main__":
    main()
