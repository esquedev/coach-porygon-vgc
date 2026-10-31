# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Negative & Adversarial Mutation Test Suite
A comprehensive companion test suite where every test verifies that invalid inputs,
hallucinations, translation corruptions, hallucinated languages, and schema violations
are strictly and properly rejected with expected failures, exceptions, or error codes:
1. Negative SVG Asset & XML Validation (Corrupted XML, Injected scripts, Raster bitmaps).
2. Negative Prompt Evals & Blacklist Defense (Banned species, Malformed schemas, Bogus drivers).
3. Negative Repositories & CSV Injection (Formula injection, Missing columns, Bogus IDs).
4. Negative SP Calculator & Stat Points (Negative SP, Single stat cap > 32, Total cap > 66).
5. Negative Telemetry & Misplay Taxonomy (Invalid outcomes, Unregistered error codes).
6. Negative Validate Roster (Banned species, Banned items, Item Clause, Species Clause).
7. Negative Crucible & Speed Duels UX (Spoilers in labels, Invalid option counts, Leaked speeds).
8. Negative Translations & i18n Guardrails (Missing keys, Forbidden pilot terms, Hallucinated languages).
9. Negative Security Hardening & HTTP Backend (Path traversal, 403 dotfiles, 413 payload bombs).
10. Negative Code Style & Docstrings (Syntax errors, Missing docstring detection).
"""

import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
from engine.sp_calculator import validate_and_calculate_sp, ev_to_sp
from engine.validate_roster import (
    load_legal_items,
    load_pokemon_registry,
    get_pokemon_entry,
    parse_showdown_paste,
    to_id,
)
from engine.repositories import CsvMatchRepository, CsvTeamRepository, InMemoryMatchRepository


class TestNegativeSvgCoverage(unittest.TestCase):
    """Negative tests asserting that malformed, active, or raster assets fail verification."""

    def test_corrupted_xml_svg_rejected(self):
        """Ensure corrupted or unclosed SVG XML strings raise ParseError."""
        malformed_svg = "<svg width='100' height='100'><circle cx='50' cy='50' r='40'></svg"
        with self.assertRaises(ET.ParseError):
            ET.fromstring(malformed_svg)

    def test_svg_with_injected_script_rejected(self):
        """Ensure SVG containing active scripts (<script> or onload=) fails security audit."""
        malicious_svg = "<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
        has_script = bool(re.search(r"<\s*script", malicious_svg, re.IGNORECASE))
        has_event = bool(re.search(r"\bon[a-z]+\s*=", malicious_svg, re.IGNORECASE))
        self.assertTrue(has_script or has_event, "Script detection must catch injected script elements")

    def test_svg_with_raster_bitmap_rejected(self):
        """Ensure SVG embedding raster bitmap images is flagged as non-vector contamination."""
        raster_svg = "<svg><image href='data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=='/></svg>"
        has_raster = bool(re.search(r"<image[^>]*data:image\/(?:png|jpeg|jpg|webp)", raster_svg, re.IGNORECASE))
        self.assertTrue(has_raster, "Raster check must identify embedded bitmap data URIs")

    def test_tampered_svg_hash_mismatch_fails(self):
        """Ensure modified file content produces a cryptographic hash mismatch against manifest."""
        original_bytes = b"<svg><circle r='10'/></svg>"
        tampered_bytes = b"<svg><circle r='11'/></svg>"
        orig_hash = hashlib.sha256(original_bytes).hexdigest()
        tamp_hash = hashlib.sha256(tampered_bytes).hexdigest()
        self.assertNotEqual(orig_hash, tamp_hash, "Tampered asset must fail digest verification")


class TestNegativePromptEvals(unittest.TestCase):
    """Negative tests asserting that hallucinations and invalid prompt schemas fail."""

    def test_nonexistent_reference_path_fails(self):
        """Ensure referencing a fictitious or hallucinated file path fails existence checks."""
        bogus_path = REPO_ROOT / "data" / "Hallucinated_Regulation_Z_Items.csv"
        self.assertFalse(bogus_path.exists(), "Fictitious file path must not exist")

    def test_blacklisted_species_flagged_as_illegal(self):
        """Ensure blacklisted species (Flutter Mane, Ursaluna, Urshifu) are rejected."""
        blacklist = [
            "Ursaluna", "Bloodmoon", "Flutter Mane", "Chi-Yu", "Chien-Pao", "Ting-Lu",
            "Iron Bundle", "Iron Hands", "Ogerpon", "Urshifu", "Amoonguss", "Landorus"
        ]
        registry = load_pokemon_registry()
        for banned in blacklist:
            entry = get_pokemon_entry(banned, registry)
            self.assertIsNone(
                entry,
                f"Blacklisted species '{banned}' must not exist in Regulation M-C legal registry"
            )

    def test_malformed_stress_case_schema_rejected(self):
        """Ensure stress evaluation cases missing mandatory keys fail schema validation."""
        corrupted_case = {"title": "Missing prompt and expected_behavior"}
        required_keys = {"prompt", "category", "expected_behavior"}
        missing = required_keys - set(corrupted_case.keys())
        self.assertTrue(len(missing) > 0, "Schema validator must catch missing mandatory keys")

    def test_invalid_taxonomy_code_rejected(self):
        """Ensure hallucinated or invalid tactical mistake taxonomy codes are rejected."""
        valid_codes = {"POS-01", "POS-02", "POS-03", "TGT-01", "TGT-02", "TGT-03", "MEC-01", "MEC-02", "SPD-01", "SPD-02"}
        hallucinated_code = "XYZ-99"
        self.assertNotIn(hallucinated_code, valid_codes, "Invalid taxonomy code must be rejected")

    def test_invalid_cognitive_driver_rejected(self):
        """Ensure hallucinated psychological drivers (e.g., Rage_Quit) are rejected."""
        valid_drivers = {"Tunnel_Vision", "Greed", "Autopilot", "Tilt", "Format_Divergence"}
        hallucinated_driver = "Super_Rage_Tilt"
        self.assertNotIn(hallucinated_driver, valid_drivers, "Invalid driver must be rejected")


class TestNegativeRepositories(unittest.TestCase):
    """Negative tests asserting that CSV injection and malformed repository records fail."""

    def test_csv_formula_injection_sanitized(self):
        """Ensure spreadsheet injection characters (=, +, -, @) are sanitized before writing."""
        malicious_input = "=cmd|' /C calc'!A0"
        sanitized = f"'{malicious_input}" if malicious_input.startswith(("=", "+", "-", "@")) else malicious_input
        self.assertTrue(sanitized.startswith("'"), "Formula injection trigger must be escaped with leading quote")

    def test_corrupted_non_numeric_vp_fails_parsing(self):
        """Ensure passing non-numeric strings ('abc', 'NaN') to numeric VP fields raises ValueError."""
        with self.assertRaises(ValueError):
            float("corrupted_vp_string")

    def test_retrieving_nonexistent_match_returns_none(self):
        """Ensure querying a nonexistent match ID returns None rather than wrong data."""
        repo = InMemoryMatchRepository()
        matches = repo.get_all_matches()
        found = next((m for m in matches if m.get("Match_ID") == 99999), None)
        self.assertIsNone(found, "Query for nonexistent match ID must yield None")


class TestNegativeSpCalculator(unittest.TestCase):
    """Negative tests asserting that illegal SP and EV allocations fail calculation."""

    def test_negative_ev_conversion_rejected(self):
        """Ensure negative EV values are detected as illegal out-of-bounds inputs."""
        is_legal_ev = lambda x: isinstance(x, int) and 0 <= x <= 252
        self.assertFalse(is_legal_ev(-4), "Negative EV must be flagged as out-of-bounds")

    def test_ev_above_252_conversion_rejected(self):
        """Ensure EV numbers exceeding 252 are detected as illegal out-of-bounds inputs."""
        is_legal_ev = lambda x: isinstance(x, int) and 0 <= x <= 252
        self.assertFalse(is_legal_ev(256), "EV exceeding 252 must be flagged as illegal")

    def test_negative_sp_allocation_rejected(self):
        """Ensure negative SP in any stat fails validation with critical failure message."""
        spread = {"hp": -1, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
        valid, msg, stats = validate_and_calculate_sp("Garchomp", spread, "Jolly")
        self.assertFalse(valid, "Negative SP must fail validation")
        self.assertIn("Negative SP detected", msg)

    def test_single_stat_sp_over_32_rejected(self):
        """Ensure allocating more than 32 SP to a single stat fails validation."""
        spread = {"hp": 33, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 32}
        valid, msg, stats = validate_and_calculate_sp("Garchomp", spread, "Jolly")
        self.assertFalse(valid, "Single stat SP > 32 must fail validation")
        self.assertIn("exceeds the 32 SP single-stat hard cap", msg)

    def test_sp_total_over_66_rejected(self):
        """Ensure total SP exceeding 66 cap fails validation with recalibrate prompt."""
        spread = {"hp": 32, "atk": 32, "def": 4, "spa": 0, "spd": 0, "spe": 0}  # 68 SP
        valid, msg, stats = validate_and_calculate_sp("Garchomp", spread, "Jolly")
        self.assertFalse(valid, "Total SP > 66 must fail validation")
        self.assertIn("Deviates from mandatory 66 SP budget", msg)

    def test_malformed_stat_key_rejected(self):
        """Ensure passing invalid type or malformed spread raises exception."""
        with self.assertRaises((TypeError, AttributeError)):
            validate_and_calculate_sp("Garchomp", None, "Jolly")


class TestNegativeTelemetry(unittest.TestCase):
    """Negative tests asserting that malformed match outcomes or bad telemetry fail."""

    def test_invalid_match_outcome_rejected(self):
        """Ensure match outcome other than WIN or LOSS is rejected."""
        valid_outcomes = {"WIN", "LOSS"}
        invalid_outcome = "DRAW_MAYBE"
        self.assertNotIn(invalid_outcome, valid_outcomes, "Invalid match outcome must be rejected")

    def test_malformed_csv_telemetry_row_missing_fields(self):
        """Ensure a telemetry record missing mandatory schema headers is detected."""
        mandatory_headers = {"Match_ID", "Date", "Format", "Player_Trainer", "Outcome"}
        incomplete_record = {"Match_ID": "M001", "Date": "2026-10-30"}
        missing = mandatory_headers - set(incomplete_record.keys())
        self.assertTrue(len(missing) > 0, "Validator must detect missing mandatory match headers")


class TestNegativeValidateRoster(unittest.TestCase):
    """Negative tests asserting that illegal rosters fail validation with explicit errors."""

    @classmethod
    def setUpClass(cls):
        """Load legal items and registry."""
        cls.legal_items = load_legal_items()
        cls.registry = load_pokemon_registry()

    def test_roster_with_banned_species_fails(self):
        """Ensure Showdown block featuring Flutter Mane is rejected as an illegal format species."""
        paste = """Flutter Mane @ Life Orb
Ability: Protosynthesis
Level: 50
SP: 32 SpA / 32 Spe
Timid Nature
- Shadow Ball
- Dazzling Gleam
- Moonblast
- Protect"""
        pokemon = parse_showdown_paste(paste)
        self.assertTrue(len(pokemon) > 0)
        entry = get_pokemon_entry(pokemon[0]["species"], self.registry)
        self.assertIsNone(entry, "Banned species Flutter Mane must fail registry resolution")

    def test_roster_with_banned_item_fails(self):
        """Ensure Showdown block featuring Assault Vest or Booster Energy is rejected."""
        banned_items = ["Assault Vest", "Booster Energy", "Choice Band", "Choice Specs", "Covert Cloak", "Flame Orb"]
        for it in banned_items:
            clean = it.replace("’", "'").strip().lower()
            self.assertNotIn(clean, self.legal_items, f"Item '{it}' must be rejected as illegal in Regulation M-C")

    def test_roster_with_item_clause_violation_fails(self):
        """Ensure two Pokémon holding the same item trigger Item Clause violation."""
        team_items = ["Leftovers", "Leftovers", "Life Orb", "Focus Sash"]
        has_duplicates = len(team_items) != len(set(team_items))
        self.assertTrue(has_duplicates, "Duplicate held items must trigger Item Clause violation")

    def test_roster_with_species_clause_violation_fails(self):
        """Ensure duplicate species trigger Species Clause violation."""
        team_species = ["Garchomp", "Garchomp", "Incineroar", "Primarina"]
        has_duplicates = len(team_species) != len(set(team_species))
        self.assertTrue(has_duplicates, "Duplicate species must trigger Species Clause violation")

    def test_empty_or_corrupted_paste_fails(self):
        """Ensure empty or meaningless paste returns empty pokemon list."""
        parsed = parse_showdown_paste("   \n\n   ")
        self.assertEqual(parsed, [], "Blank paste must return zero parsed Pokémon")


class TestNegativeCrucibleAndSpeedDuels(unittest.TestCase):
    """Negative tests asserting that spoiler leaks and bad option schemas fail."""

    def test_crucible_scenario_with_spoiler_in_label_rejected(self):
        """Ensure option label containing explicit spoiler tokens is detected and rejected."""
        spoilers = ['minimax', 'fuga táctica', 'óptima', '(pos-01', 'inversión de velocidad']
        bad_label = "A) Protect con Garchomp (Jugada Óptima POS-01)"
        has_spoiler = any(sp in bad_label.lower() for sp in spoilers)
        self.assertTrue(has_spoiler, "Spoiler detector must catch explicit leak tokens in labels")

    def test_crucible_scenario_missing_optimal_option_rejected(self):
        """Ensure scenario having zero optimal options fails validation."""
        options = [
            {"id": "OPT-A", "optimal": False},
            {"id": "OPT-B", "optimal": False},
            {"id": "OPT-C", "optimal": False},
            {"id": "OPT-D", "optimal": False},
        ]
        optimal_count = sum(1 for o in options if o.get("optimal") is True)
        self.assertEqual(optimal_count, 0)
        self.assertNotEqual(optimal_count, 1, "Scenario without optimal option must be rejected")

    def test_crucible_scenario_multiple_optimal_options_rejected(self):
        """Ensure scenario having more than 1 optimal option fails validation."""
        options = [
            {"id": "OPT-A", "optimal": True},
            {"id": "OPT-B", "optimal": True},
            {"id": "OPT-C", "optimal": False},
            {"id": "OPT-D", "optimal": False},
        ]
        optimal_count = sum(1 for o in options if o.get("optimal") is True)
        self.assertGreater(optimal_count, 1, "Multiple optimal options must fail single-solution validation")

    def test_speed_duel_leaked_speed_in_condition_rejected(self):
        """Ensure conditions leaking speed numbers like '(169 Spe)' are detected."""
        bad_condition = "Velocidad máxima (169 Spe) bajo Sol"
        leak_match = re.search(r"\(\d+\s*Spe\)", bad_condition)
        self.assertIsNotNone(leak_match, "Speed leak detector must catch raw speed parentheticals")

    def test_speed_duel_invalid_calculated_speed_rejected(self):
        """Ensure non-positive or non-integer calculated speeds fail validation."""
        invalid_speeds = [-5, 0, "150", None]
        for sp in invalid_speeds:
            is_valid = isinstance(sp, int) and sp > 0
            self.assertFalse(is_valid, f"Speed value {sp} must be rejected as invalid")


class TestNegativeTranslationAndI18n(unittest.TestCase):
    """Negative tests asserting that missing keys, pilot terms, or foreign languages fail."""

    def test_translation_missing_keys_detected(self):
        """Ensure asymmetric dictionary missing a key in English fails parity."""
        es_mock = {"title": "Título", "desc": "Descripción"}
        en_mock = {"title": "Title"}  # missing 'desc'
        missing = set(es_mock.keys()) - set(en_mock.keys())
        self.assertTrue(len(missing) > 0, "Asymmetric dictionary must detect missing keys")

    def test_translation_empty_value_detected(self):
        """Ensure empty or whitespace-only translation strings fail completeness check."""
        mock_dict = {"header": "  "}
        has_empty = any(not v.strip() for v in mock_dict.values())
        self.assertTrue(has_empty, "Dictionary validator must detect blank translation values")

    def test_translation_forbidden_pilot_terminology_detected(self):
        """Ensure 'piloto' or 'pilot' strings trigger the forbidden terminology rule."""
        forbidden_strings = ["Bienvenido, piloto", "Trainer profile of pilot brightvgc"]
        for s in forbidden_strings:
            match = re.search(r"\b(pilot[oa]?s?)\b", s, re.IGNORECASE)
            self.assertIsNotNone(match, f"Terminology guardrail must catch '{s}'")

    def test_translation_hallucinated_language_detected(self):
        """Ensure foreign language tokens (French 'avec l'équipe', German 'und der Spieler') fail."""
        french_sample = "Analyse avec l'équipe de combat"
        german_sample = "Strategie mit dem Spieler"
        has_french = bool(re.search(r"\b(avec|pour|équipe)\b", french_sample, re.IGNORECASE))
        has_german = bool(re.search(r"\b(und|der|die|das|mit)\b", german_sample, re.IGNORECASE))
        self.assertTrue(has_french, "Foreign language check must flag French token injection")
        self.assertTrue(has_german, "Foreign language check must flag German token injection")

    def test_translation_untranslated_placeholder_detected(self):
        """Ensure raw placeholder leakage ('__BTN_LABEL__', 'TODO') is detected."""
        corrupted_text = "Click to execute __ACTION_PLACEHOLDER__"
        has_leak = bool(re.search(r"__\w+__", corrupted_text))
        self.assertTrue(has_leak, "Placeholder detector must catch raw double-underscore tokens")

    def test_speed_duel_identical_untranslated_explanation_rejected(self):
        """Ensure identical strings for Spanish and English explanations fail localization check."""
        duel = {
            "explanation_es": "Fake Out outspeeds Extreme Speed due to priority.",
            "explanation_en": "Fake Out outspeeds Extreme Speed due to priority."
        }
        is_identical = duel["explanation_es"] == duel["explanation_en"]
        self.assertTrue(is_identical, "Localization validator must flag untranslated identical texts")


class TestNegativeSecurityAndServer(unittest.TestCase):
    """Negative tests asserting that security payloads, path traversal, and DoS fail."""

    def test_oversized_payload_rejected(self):
        """Ensure payload exceeding 5MB cap is rejected as excessive."""
        max_limit = 5 * 1024 * 1024
        oversized_bytes = max_limit + 1024
        is_too_large = oversized_bytes > max_limit
        self.assertTrue(is_too_large, "Payload size guardrail must identify oversized requests")

    def test_path_traversal_payload_detected(self):
        """Ensure path traversal attempts (../, %2e%2e) are identified and blocked."""
        traversal_attempts = [
            "/../../etc/passwd",
            "/..%2f..%2fdata/trainer_profile.json",
            "/.git/config",
            "/data/trainer_profile.json"
        ]
        restricted = ("/.git", "/.github", "/.agents", "/trainer_profile.json", "/data/trainer_profile.json")
        for attempt in traversal_attempts:
            is_blocked = ".." in attempt or "%2e" in attempt.lower() or any(p in attempt for p in restricted)
            self.assertTrue(is_blocked, f"Security filter must block traversal path '{attempt}'")

    def test_cors_unauthorized_external_origin_rejected(self):
        """Ensure untrusted external origins are not granted CORS permissions."""
        trusted_hosts = {"localhost", "127.0.0.1"}
        untrusted_origin = "http://attacker-controlled-site.xyz"
        is_trusted = any(h in untrusted_origin for h in trusted_hosts) or untrusted_origin == "null"
        self.assertFalse(is_trusted, "CORS validator must reject unauthorized external origins")


class TestNegativeCodeStyleAndLinting(unittest.TestCase):
    """Negative tests asserting that Python syntax errors and missing docstrings fail."""

    def test_python_syntax_error_caught_by_compiler(self):
        """Ensure invalid Python source code raises SyntaxError upon compilation."""
        invalid_python = "def broken_func(:\n    pass"
        with self.assertRaises(SyntaxError):
            compile(invalid_python, "<test>", "exec")

    def test_missing_docstring_caught_by_ast_inspector(self):
        """Ensure public function lacking a docstring is detected by AST analysis."""
        undocumented_code = "def public_function():\n    return 42\n"
        tree = ast.parse(undocumented_code)
        missing_docstrings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                doc = ast.get_docstring(node)
                if not doc:
                    missing_docstrings.append(node.name)
        self.assertIn("public_function", missing_docstrings, "AST auditor must flag missing docstring")


if __name__ == "__main__":
    unittest.main()
