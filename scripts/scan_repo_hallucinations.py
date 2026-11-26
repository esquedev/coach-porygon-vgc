#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Repository-Wide Anti-Hallucination & Integrity Guardrail Scanner
====================================================================================

Executed automatically by:
  - `.githooks/pre-commit` & `.githooks/pre-push`
  - `.github/workflows/ci.yml` (`develop` and `main` branches)
  - `tests/test_acceptance_anti_hallucination.py`

Enforces 5 deterministic codebase invariants:
1. **Regulation M-C Species Blacklist Lock:** Zero ungrounded Gen-9 Paradox / Restricted /
   banned species mentions in engine code, Studio app code, active team pastes, or agent skills.
2. **Strict `trainer_1` / `trainer_2` Identifier Mandate:** Zero `p1` / `p2` variable or
   parameter names anywhere in `src/engine/`, `apps/`, or `tests/` Python ASTs.
3. **Zero Gen-9 SV-Only Items or Terastallization in Team Pastes (`data/teams/`):** Rejects
   illegal SV items (`Clear Amulet`, `Covert Cloak`, `Booster Energy`, `Assault Vest`,
   `Choice Band`, `Choice Specs`) and `Tera Type:` headers in active Regulation M-C pastes.
4. **Domain Core Isolation (`src/engine/`):** Zero web framework or HTTP server imports
   (`flask`, `fastapi`, `http.server`, `aiohttp`, `tornado`) inside `src/engine/`.
5. **Studio Frontend JS Syntax Check:** Validates `apps/replay_coach/static/app.js` using
   in-process V8 (`py_mini_racer`) when installed.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys
from typing import Dict, List, Sequence, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent

REGULATION_MC_SPECIES_BLACKLIST: Tuple[str, ...] = (
    "Ursaluna",
    "Bloodmoon",
    "Flutter Mane",
    "Chi-Yu",
    "Chien-Pao",
    "Ting-Lu",
    "Wo-Chien",
    "Iron Bundle",
    "Iron Hands",
    "Iron Leaves",
    "Iron Boulder",
    "Iron Crown",
    "Iron Jugulis",
    "Iron Moth",
    "Iron Thorns",
    "Iron Treads",
    "Iron Valiant",
    "Roaring Moon",
    "Scream Tail",
    "Brute Bonnet",
    "Sandy Shocks",
    "Slither Wing",
    "Great Tusk",
    "Walking Wake",
    "Raging Bolt",
    "Gouging Fire",
    "Ogerpon",
    "Urshifu",
    "Amoonguss",
    "Gastrodon",
    "Landorus",
    "Tornadus",
    "Thundurus",
    "Enamorus",
    "Heatran",
    "Cresselia",
    "Calyrex",
    "Miraidon",
    "Koraidon",
    "Terapagos",
    "Zacian",
    "Zamazenta",
    "Kyogre",
    "Groudon",
    "Tatsugiri",
    "Dondozo",
    "Dudunsparce",
    "Oinkologne",
)

ILLEGAL_SV_ITEMS: Tuple[str, ...] = (
    "Clear Amulet",
    "Covert Cloak",
    "Booster Energy",
    "Assault Vest",
    "Choice Band",
    "Choice Specs",
    "Power Herb",
    "Safety Goggles",
    "Loaded Dice",
    "Mirror Herb",
    "Eviolite",
    "Weakness Policy",
    "Throat Spray",
    "Flame Orb",
    "Toxic Orb",
    "Black Sludge",
    "Punching Glove",
    "Ability Shield",
    "Heavy-Duty Boots",
)

BANNED_REG_MC_MOVES: Tuple[str, ...] = (
    "Surging Strikes",
    "Wicked Blow",
    "Ivy Cudgel",
    "Astral Barrage",
    "Glacial Lance",
    "Bleakwind Storm",
    "Wildbolt Storm",
    "Sandsear Storm",
    "Springtide Storm",
    "Tera Blast",
    "Tera Starstorm",
    "Thunderclap",
    "Tachyon Cutter",
    "Blood Moon",
    "Manual Hail",
)

FORBIDDEN_DOMAIN_IMPORTS: Tuple[str, ...] = (
    "flask",
    "fastapi",
    "starlette",
    "http.server",
    "aiohttp",
    "tornado",
    "django",
)

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "vendor",
    "showdown",
    "munchstats",
    "agent_audits",
    "bug_logs",
    "prep_tools",
}

CANONICAL_EXEMPT_FILES = {
    "scan_repo_hallucinations.py",
    "test_acceptance_anti_hallucination.py",
    "README.md",
    "AGENTS.md",
    "LICENSE",
}


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def check_banned_species_hallucinations(root: Path = REPO_ROOT) -> List[str]:
    """Scan active engine/app/team/skill files for ungrounded non-Regulation-M-C species."""
    violations: List[str] = []
    scan_roots = [root / "src" / "engine", root / "apps", root / "data" / "teams", root / ".agents" / "skills"]
    scan_exts = {".py", ".txt", ".md", ".html", ".js"}

    for base in scan_roots:
        if not base.exists():
            continue
        for fpath in sorted(base.rglob("*")):
            if not fpath.is_file() or fpath.suffix.lower() not in scan_exts:
                continue
            if _is_excluded(fpath.relative_to(root)) or fpath.name in CANONICAL_EXEMPT_FILES:
                continue
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            rel = fpath.relative_to(root).as_posix()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "REGULATION_MC_SPECIES_BLACKLIST" in line or "ILLEGAL_FORMAT_SPECIES" in line:
                    continue
                for banned in REGULATION_MC_SPECIES_BLACKLIST:
                    if re.search(rf"\b{re.escape(banned)}\b", line, re.IGNORECASE):
                        violations.append(f"[BANNED_SPECIES] {rel}:{lineno} -> '{banned}': {line.strip()[:100]}")
    return violations


def check_forbidden_p1_p2_identifiers(root: Path = REPO_ROOT) -> List[str]:
    """AST-scan Python source & test files to enforce `trainer_1`/`trainer_2` (zero `p1`/`p2`)."""
    violations: List[str] = []
    scan_roots = [root / "src" / "engine", root / "apps", root / "tests"]

    for base in scan_roots:
        if not base.exists():
            continue
        for fpath in sorted(base.rglob("*.py")):
            if _is_excluded(fpath.relative_to(root)):
                continue
            rel = fpath.relative_to(root).as_posix()
            try:
                tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=rel)
            except SyntaxError as exc:
                violations.append(f"[SYNTAX_ERROR] {rel}:{exc.lineno} -> {exc.msg}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in ("p1", "p2"):
                    violations.append(f"[IDENTIFIER_P1_P2] {rel}:{node.lineno} -> variable '{node.id}' (use trainer_1/trainer_2)")
                elif isinstance(node, ast.arg) and node.arg in ("p1", "p2"):
                    violations.append(f"[IDENTIFIER_P1_P2] {rel}:{node.lineno} -> arg '{node.arg}' (use trainer_1/trainer_2)")
    return violations


def check_team_pastes_reg_mc_legality(root: Path = REPO_ROOT) -> List[str]:
    """Verify active Showdown pastes in `data/teams/` have zero Tera Types and zero SV-only items."""
    violations: List[str] = []
    teams_dir = root / "data" / "teams"
    if not teams_dir.exists():
        return violations

    for fpath in sorted(teams_dir.glob("*.txt")):
        rel = fpath.relative_to(root).as_posix()
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(r"^\s*Tera\s+Type\s*:", line, re.IGNORECASE):
                violations.append(f"[ILLEGAL_TERA] {rel}:{lineno} -> Terastallization forbidden in Reg M-C")
            for sv_item in ILLEGAL_SV_ITEMS:
                if re.search(rf"@\s*{re.escape(sv_item)}\b", line, re.IGNORECASE):
                    violations.append(f"[ILLEGAL_SV_ITEM] {rel}:{lineno} -> '{sv_item}' is not legal in Reg M-C")
    return violations


def check_domain_core_isolation(root: Path = REPO_ROOT) -> List[str]:
    """Verify `src/engine/` contains zero web-framework or HTTP server imports."""
    violations: List[str] = []
    engine_dir = root / "src" / "engine"
    if not engine_dir.exists():
        return violations

    for fpath in sorted(engine_dir.rglob("*.py")):
        if _is_excluded(fpath.relative_to(root)):
            continue
        rel = fpath.relative_to(root).as_posix()
        try:
            tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mod_name = ""
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_name = alias.name
                    if any(mod_name == bad or mod_name.startswith(f"{bad}.") for bad in FORBIDDEN_DOMAIN_IMPORTS):
                        violations.append(f"[DOMAIN_ISOLATION] {rel}:{node.lineno} -> forbidden import '{mod_name}'")
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod_name = node.module
                if any(mod_name == bad or mod_name.startswith(f"{bad}.") for bad in FORBIDDEN_DOMAIN_IMPORTS):
                    violations.append(f"[DOMAIN_ISOLATION] {rel}:{node.lineno} -> forbidden import from '{mod_name}'")
    return violations


def check_studio_js_syntax(root: Path = REPO_ROOT) -> List[str]:
    """Validate `apps/replay_coach/static/app.js` using V8 (`py_mini_racer`) when installed."""
    js_path = root / "apps" / "replay_coach" / "static" / "app.js"
    if not js_path.exists():
        return []
    try:
        from py_mini_racer import MiniRacer  # type: ignore
    except ImportError:
        return []

    js_src = js_path.read_text(encoding="utf-8")
    try:
        MiniRacer().eval(f"new Function({js_src!r}); 'JS_OK'")
    except Exception as exc:
        return [f"[JS_SYNTAX_ERROR] apps/replay_coach/static/app.js -> {exc}"]
    return []


def check_banned_moves_and_rule_hallucinations(root: Path = REPO_ROOT) -> List[str]:
    """Scan engine, Studio, rules, and skills for banned Gen-9 SV moves, Phase-0 Mega claims, and unannotated Hail logic."""
    violations: List[str] = []
    scan_roots = [
        root / "src" / "engine",
        root / "apps",
        root / ".agents" / "rules",
        root / ".agents" / "skills",
    ]
    scan_exts = {".py", ".md", ".html", ".js"}

    for base in scan_roots:
        if not base.exists():
            continue
        for fpath in sorted(base.rglob("*")):
            if not fpath.is_file() or fpath.suffix.lower() not in scan_exts:
                continue
            if _is_excluded(fpath.relative_to(root)) or fpath.name in CANONICAL_EXEMPT_FILES:
                continue
            rel = fpath.relative_to(root).as_posix()
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for bad_mv in BANNED_REG_MC_MOVES:
                    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(bad_mv)}(?![A-Za-z0-9_])", line, re.IGNORECASE):
                        violations.append(f"[BANNED_MOVE] {rel}:{lineno} -> '{bad_mv}': {line.strip()[:100]}")
                if rel.startswith(".agents/rules/") and re.search(r"Mega Evolution.*Phase 0", line, re.IGNORECASE):
                    violations.append(
                        f"[MEGA_TIMING_CONTRADICTION] {rel}:{lineno} -> Mega Evolution resolves at Priority +5.5, never Phase 0"
                    )
                if (
                    (rel.startswith("src/engine/vgc_tensor_core/") or rel.startswith("src/engine/modes/"))
                    and re.search(r"(?<![A-Za-z0-9_])hail(?![A-Za-z0-9_])", line, re.IGNORECASE)
                    and "Legacy Showdown" not in line
                ):
                    violations.append(f"[STALE_HAIL_LOGIC] {rel}:{lineno} -> use Snowscape/Snow, not Hail: {line.strip()[:100]}")
    return violations


CONFIRMED_REG_MD_FILES = {
    "dondozo.png",
    "heatran.png",
    "heatran-mega.png",
    "tatsugiri.png",
    "tatsugiri-droopy.png",
    "tatsugiri-stretchy.png",
    "tatsugiri-mega.png",
    "tatsugiri-droopy-mega.png",
    "tatsugiri-stretchy-mega.png",
}

FORBIDDEN_MC_SPRITE_STEMS = {
    "gothitelle",
    "heatran",
    "heatran-mega",
    "dondozo",
    "tatsugiri",
    "tatsugiri-droopy",
    "tatsugiri-stretchy",
    "tatsugiri-mega",
    "amoonguss",
    "latias",
    "latios",
    "cobalion",
    "terrakion",
    "virizion",
    "flamigo",
    "porygon-z",
}


def check_reg_mc_md_asset_isolation(root: Path = REPO_ROOT) -> List[str]:
    """Verify strict Reg M-C vs. Confirmed Reg M-D vs. Rumored asset boundaries & slug_map integrity."""
    violations: List[str] = []
    mc_dir = root / "assets" / "sprites" / "Reg_M-C"
    md_dir = root / "assets" / "sprites" / "Reg_M-D"
    slug_map_path = root / "assets" / "slug_map.json"

    if mc_dir.exists():
        for png in sorted(mc_dir.glob("*.png")):
            if png.stem.lower() in FORBIDDEN_MC_SPRITE_STEMS:
                violations.append(f"[ILLEGAL_MC_SPRITE] assets/sprites/Reg_M-C/{png.name} is not legal in Reg M-C")

    if md_dir.exists():
        actual_md = {p.name for p in md_dir.glob("*.png")}
        extra_md = sorted(actual_md - CONFIRMED_REG_MD_FILES)
        missing_md = sorted(CONFIRMED_REG_MD_FILES - actual_md)
        for f in extra_md:
            violations.append(f"[UNCONFIRMED_MD_SPRITE] assets/sprites/Reg_M-D/{f} belongs in Reg_M-D_rumored/")
        for f in missing_md:
            violations.append(f"[MISSING_MD_SPRITE] assets/sprites/Reg_M-D/{f} missing")

    if slug_map_path.exists():
        try:
            sm = json.loads(slug_map_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return [f"[SLUG_MAP_JSON_ERROR] {exc}"]
        for section in ("species", "items"):
            for k, rel in (sm.get(section) or {}).items():
                if "Reg_M-D_rumored" in str(rel):
                    violations.append(f"[RUMORED_LEAK_IN_SLUG_MAP] {section}[{k}] -> {rel}")
                elif not (root / str(rel)).is_file():
                    violations.append(f"[BROKEN_SLUG_MAP_PATH] {section}[{k}] -> {rel}")
    return violations


def run_all_guards(root: Path = REPO_ROOT) -> Dict[str, List[str]]:
    """Run every repository anti-hallucination and integrity guardrail and return grouped violations."""
    return {
        "banned_species": check_banned_species_hallucinations(root),
        "banned_moves_and_rules": check_banned_moves_and_rule_hallucinations(root),
        "p1_p2_identifiers": check_forbidden_p1_p2_identifiers(root),
        "team_pastes_legality": check_team_pastes_reg_mc_legality(root),
        "domain_isolation": check_domain_core_isolation(root),
        "studio_js_syntax": check_studio_js_syntax(root),
        "reg_mc_md_asset_isolation": check_reg_mc_md_asset_isolation(root),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on clean pass, 1 on any guardrail violation."""
    _ = argv
    results = run_all_guards(REPO_ROOT)
    total_violations = sum(len(v) for v in results.values())

    print("==========================================================================")
    print(" Coach Porygon VGC — Anti-Hallucination & Codebase Integrity Gate")
    print("==========================================================================")
    for check_name, errs in results.items():
        status = "PASS" if not errs else f"FAIL ({len(errs)})"
        print(f"  [{status:10s}] {check_name}")
        for err in errs[:15]:
            print(f"      - {err}")
        if len(errs) > 15:
            print(f"      ... and {len(errs) - 15} more")

    print("==========================================================================")
    if total_violations > 0:
        print(f" [FAIL] {total_violations} guardrail violation(s) detected. Fix before commit/push!")
        return 1

    print(" [PASS] All anti-hallucination & Regulation M-C guardrails passed cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
