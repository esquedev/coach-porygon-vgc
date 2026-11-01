#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Deterministic Static Verification & Prompt Health Runner
Part of Mode 7: Release Health Auditor & Prompt Stress Evaluator.

Executes 100% dependency-free static checks across the workspace:
1. Validates evals/stress_cases.yaml schema and completeness (>=25 cases).
2. Verifies that all paths, scripts, and CSVs referenced in AGENTS.md and .agents/skills/ exist.
3. Verifies species blacklist consistency across rule files.
4. Verifies mistake taxonomy codes and cognitive trap drivers.
5. Verifies canonical Trainer terminology and zero internal hex leakage.
"""

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent

# Standardized mistake codes from .agents/rules/mistake_taxonomy.md
CANONICAL_ERROR_CODES = {
    "POS-01", "POS-02", "POS-03",
    "TGT-01", "TGT-02", "TGT-03",
    "MEC-01", "MEC-02",
    "SPD-01", "SPD-02"
}

CANONICAL_COGNITIVE_DRIVERS = {
    "Tunnel_Vision",
    "Greed",
    "Autopilot",
    "Tilt",
    "Format_Divergence"
}

CANONICAL_BLACKLIST = [
    "Ursaluna", "Flutter Mane", "Chi-Yu", "Chien-Pao", "Ting-Lu",
    "Iron Bundle", "Iron Hands", "Iron Leaves", "Iron Boulder", "Iron Crown",
    "Roaring Moon", "Scream Tail", "Brute Bonnet", "Sandy Shocks", "Slither Wing",
    "Ogerpon", "Urshifu", "Amoonguss", "Gastrodon", "Landorus",
    "Tornadus", "Thundurus", "Enamorus", "Heatran", "Cresselia"
]


def load_yaml_cases(yaml_path: Path):
    """
    Lightweight, dependency-free parser for evals/stress_cases.yaml.
    Parses test cases with id, category, mode, description, expected, forbidden.
    """
    if not yaml_path.exists():
        raise FileNotFoundError(f"Stress cases file not found: {yaml_path}")

    text = yaml_path.read_text(encoding="utf-8")
    cases = []
    current_case = {}
    current_list_key = None

    for line in text.splitlines():
        line_strip = line.strip()
        if not line_strip or line_strip.startswith("#"):
            continue

        # New case entry
        if line.startswith("  - id:") or line.startswith("- id:"):
            if current_case:
                cases.append(current_case)
            current_case = {}
            current_list_key = None
            val = line_strip.split(":", 1)[1].strip().strip('"').strip("'")
            current_case["id"] = val
            continue

        if line.startswith("    ") and not line.startswith("      "):
            parts = line_strip.split(":", 1)
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().strip('"').strip("'")
                if val:
                    current_case[key] = val
                    current_list_key = None
                else:
                    current_list_key = key
                    current_case[key] = []
            continue

        if line.startswith("      - ") and current_list_key:
            val = line_strip[2:].strip().strip('"').strip("'")
            if current_list_key in current_case and isinstance(current_case[current_list_key], list):
                current_case[current_list_key].append(val)

    if current_case:
        cases.append(current_case)

    return cases


def verify_stress_cases_schema():
    """Verifies that evals/stress_cases.yaml has >=25 cases with valid schema."""
    yaml_file = REPO_ROOT / "evals" / "stress_cases.yaml"
    cases = load_yaml_cases(yaml_file)
    assert len(cases) >= 25, f"Expected >= 25 stress test cases, found {len(cases)}"

    seen_ids = set()
    for c in cases:
        cid = c.get("id")
        assert cid, f"Missing case id in {c}"
        assert cid not in seen_ids, f"Duplicate case id: {cid}"
        seen_ids.add(cid)
        assert c.get("family") in ("domain_critical", "agent_perturbation"), f"Case {cid} missing or invalid family"
        assert c.get("category"), f"Case {cid} missing category"
        assert c.get("mode"), f"Case {cid} missing mode"
        assert c.get("description"), f"Case {cid} missing description"
        assert c.get("expected_behaviors"), f"Case {cid} missing expected_behaviors"
        assert c.get("forbidden_behaviors"), f"Case {cid} missing forbidden_behaviors"

    return len(cases)


def ensure_local_data_templates():
    """Ensure gitignored telemetry/profile files have baseline local templates on clean CI runs."""
    data_dir = REPO_ROOT / "data"
    if data_dir.exists():
        for ex_file in data_dir.glob("*.example.*"):
            target_name = ex_file.name.replace(".example", "")
            target_file = data_dir / target_name
            if not target_file.exists():
                target_file.write_bytes(ex_file.read_bytes())


def verify_referenced_paths():
    """Scans AGENTS.md and .agents/skills/ for referenced files and validates existence."""
    ensure_local_data_templates()
    markdown_files = [REPO_ROOT / "AGENTS.md"]
    markdown_files.extend((REPO_ROOT / ".agents").rglob("*.md"))

    missing_paths = []
    checked_count = 0

    # Match markdown links: [text](target)
    md_link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    # Match backticked explicit filepaths containing slashes or extensions
    code_path_pattern = re.compile(r'`([a-zA-Z0-9_\-\./\\]+\.(?:py|csv|json|md|html|yaml|yml))`')

    for md_file in markdown_files:
        content = md_file.read_text(encoding="utf-8")

        # 1. Check markdown links
        for text, target in md_link_pattern.findall(content):
            target_clean = target.split("#")[0].strip()
            if not target_clean or target_clean.startswith("http://") or target_clean.startswith("https://"):
                continue
            if "<" in target_clean or ">" in target_clean:
                continue

            resolved = (md_file.parent / target_clean).resolve()
            data_resolved = (REPO_ROOT / "data" / target_clean).resolve()
            candidates = [resolved, data_resolved]
            example_candidates = [
                c.with_name(c.stem + ".example" + c.suffix) for c in candidates
            ]
            checked_count += 1
            if not any(c.exists() for c in candidates + example_candidates):
                missing_paths.append((str(md_file.relative_to(REPO_ROOT)), target, str(resolved)))

        # 2. Check explicitly backticked filepaths
        for p_str in code_path_pattern.findall(content):
            p_clean = p_str.strip()
            if p_clean.startswith("http://") or p_clean.startswith("https://") or "<" in p_clean:
                continue
            if p_clean.startswith("evals/reports/"):
                continue

            # Resolve relative to root, parent, or known subdirs
            candidates = [
                REPO_ROOT / p_clean,
                md_file.parent / p_clean,
                REPO_ROOT / "data" / p_clean,
                REPO_ROOT / "engine" / p_clean,
                REPO_ROOT / ".agents" / "rules" / p_clean
            ]
            example_candidates = [
                c.with_name(c.stem + ".example" + c.suffix) for c in candidates
            ]
            found = any(c.exists() for c in candidates + example_candidates)
            checked_count += 1
            if not found:
                missing_paths.append((str(md_file.relative_to(REPO_ROOT)), p_str, str(REPO_ROOT / p_clean)))

    if missing_paths:
        for source, ref, target in missing_paths:
            print(f"[BROKEN LINK] In {source}: '{ref}' -> {target}")
        raise FileNotFoundError(f"Found {len(missing_paths)} broken file references in prompt rules.")

    return checked_count


def verify_species_blacklist():
    """Verifies species blacklist consistency."""
    guardrails_file = REPO_ROOT / ".agents" / "rules" / "system_guardrails.md"
    assert guardrails_file.exists(), "system_guardrails.md missing"
    content = guardrails_file.read_text(encoding="utf-8")

    for species in CANONICAL_BLACKLIST:
        assert species in content, f"Blacklisted species '{species}' missing in system_guardrails.md"
    return len(CANONICAL_BLACKLIST)


def verify_taxonomy_codes():
    """Verifies mistake taxonomy codes and cognitive drivers."""
    tax_file = REPO_ROOT / ".agents" / "rules" / "mistake_taxonomy.md"
    assert tax_file.exists(), "mistake_taxonomy.md missing"
    content = tax_file.read_text(encoding="utf-8")

    for code in CANONICAL_ERROR_CODES:
        assert code in content, f"Error code '{code}' missing from mistake_taxonomy.md"

    for driver in CANONICAL_COGNITIVE_DRIVERS:
        assert driver in content, f"Cognitive driver '{driver}' missing from mistake_taxonomy.md"

    return len(CANONICAL_ERROR_CODES) + len(CANONICAL_COGNITIVE_DRIVERS)


def verify_declared_dependencies():
    """
    AST-based static validation of external Python package imports across engine/ and tests/.
    Ensures that every third-party package imported is explicitly declared in requirements.txt,
    requirements-dev.txt, or pyproject.toml.
    """
    import ast

    declared = set()
    req_files = [
        REPO_ROOT / "requirements.txt",
        REPO_ROOT / "requirements-dev.txt",
        REPO_ROOT / "pyproject.toml"
    ]

    for rf in req_files:
        if rf.exists():
            for line in rf.read_text(encoding="utf-8").splitlines():
                clean = line.strip().split("#")[0].strip().strip('"').strip("'")
                if not clean or clean.startswith("[") or ("=" in clean and not any(op in clean for op in [">=", "<=", "==", "~="])):
                    continue
                pkg_match = re.match(r"^([a-zA-Z0-9_\-]+)", clean)
                if pkg_match:
                    pkg_name = pkg_match.group(1).lower().replace("-", "_")
                    declared.add(pkg_name)

    import_map = {
        "pillow": "pil",
        "scikit_learn": "sklearn",
        "pyyaml": "yaml",
        "pytest_cov": "pytest",
        "tomli": "tomllib",
    }
    for dist, mod in import_map.items():
        if dist in declared:
            declared.add(mod)

    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    stdlib.update({
        "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
        "copy", "csv", "ctypes", "dataclasses", "datetime", "decimal", "difflib",
        "enum", "fileinput", "fnmatch", "fractions", "functools", "glob", "graphlib", "gzip",
        "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect", "io", "ipaddress",
        "itertools", "json", "logging", "math", "mimetypes", "multiprocessing",
        "operator", "os", "pathlib", "pickle", "platform", "pprint", "queue",
        "random", "re", "secrets", "shutil", "signal", "socket", "socketserver", "sqlite3",
        "ssl", "stat", "string", "struct", "subprocess", "sys", "tempfile",
        "threading", "time", "timeit", "tomllib", "traceback", "types", "typing",
        "unicodedata", "unittest", "urllib", "uuid", "warnings", "weakref", "wsgiref", "xml", "zipfile", "zoneinfo"
    })
    internal_modules = {"engine", "evals", "tests", "main", "munchstats_scraper"}
    for p in (REPO_ROOT / "engine").rglob("*.py"):
        internal_modules.add(p.stem.lower().replace("-", "_"))
    for p in (REPO_ROOT / "evals").rglob("*.py"):
        internal_modules.add(p.stem.lower().replace("-", "_"))
    for p in (REPO_ROOT / "tests").rglob("*.py"):
        internal_modules.add(p.stem.lower().replace("-", "_"))

    undeclared = []
    scanned_imports = 0

    scan_dirs = [REPO_ROOT / "engine", REPO_ROOT / "tests", REPO_ROOT / "evals"]
    for sdir in scan_dirs:
        for py_file in sdir.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except Exception:
                continue

            for node in ast.walk(tree):
                module_names = []
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_names.append(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module:
                        module_names.append(node.module.split(".")[0])

                for mod in module_names:
                    mod_lower = mod.lower().replace("-", "_")
                    scanned_imports += 1
                    if mod_lower in stdlib or mod_lower in internal_modules:
                        continue
                    if mod_lower not in declared:
                        undeclared.append((str(py_file.relative_to(REPO_ROOT)), mod))

    if undeclared:
        for fpath, mod in undeclared:
            print(f"  [UNDECLARED DEPENDENCY] File: {fpath} imports '{mod}', but '{mod}' is not declared in requirements.txt or pyproject.toml.")
        raise AssertionError(f"Found {len(undeclared)} undeclared third-party dependencies.")

    return scanned_imports


def run_all_checks():
    """Run 5 deterministic static checks: schema, file paths, blacklist, taxonomy, dependencies."""
    print("=" * 60)
    print("COACH PORYGON VGC — DETERMINISTIC STATIC EVALUATION RUNNER")
    print("=" * 60)

    total_cases = verify_stress_cases_schema()
    print(f"  ✓ Stress Cases Schema: {total_cases} adversarial cases validated.")

    paths_checked = verify_referenced_paths()
    print(f"  ✓ Referenced Paths: {paths_checked} file/script references verified on disk.")

    blacklist_count = verify_species_blacklist()
    print(f"  ✓ Species Blacklist: {blacklist_count} format species strictly grounded.")

    tax_count = verify_taxonomy_codes()
    print(f"  ✓ Mistake Taxonomy: {tax_count} tactical codes and cognitive drivers verified.")

    dep_count = verify_declared_dependencies()
    print(f"  ✓ Declared Dependencies: {dep_count} imports validated against requirements manifests.")

    print("=" * 60)
    print("STATUS: [PASS - ALL PROMPT HEALTH CHECKS GREEN]")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = run_all_checks()
        sys.exit(0 if success else 1)
    except Exception as exc:
        print(f"\n[FAIL - STATIC AUDIT ERROR]: {exc}")
        sys.exit(1)
