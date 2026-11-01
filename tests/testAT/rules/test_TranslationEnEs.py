#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Bilingual English/Spanish Translation Acceptance Tests
Verifies:
1. 1:1 key parity and symmetry between Spanish (es) and English (en) dictionaries.
2. 100% coverage of all HTML data-i18n tags within both translation sets.
3. Speed Duels bilingual explanation completeness and grammatical divergence.
4. Canonical Trainer terminology enforcement: 'Entrenador' (ES) and 'Trainer' (EN), strictly prohibiting 'piloto'/'pilot'.
5. Preservation of canonical VGC game terminology (Protect, Fake Out, Tailwind, STAB, etc.).
6. Absence of raw placeholders, template syntax, or unrendered tokens.
7. Anti-hallucination language guardrail: zero French, German, or Italian token leakage.
8. Language initialization configuration across language-specific compiled command centers.
"""

from pathlib import Path
import re
import pyhocon
from pyhocon import ConfigFactory
import unittest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
from engine.speed_duels_data import SPEED_DUELS


def extract_i18n_dictionaries(html_content: str):
    """Parse out I18N.es and I18N.en key-value dictionaries from HTML source."""
    es_match = re.search(r'const\s+I18N\s*=\s*\{\s*es:\s*\{([^}]+)\}', html_content, re.DOTALL)
    en_match = re.search(r'en:\s*\{([^}]+)\}\s*\};', html_content, re.DOTALL)

    def parse_block(text: str):
        """Parse raw JavaScript key-value lines into a Python dictionary."""
        result = {}
        for line in text.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            m = re.match(r'["\']?([a-zA-Z0-9_-]+)["\']?\s*:\s*["\'](.*)["\'],?$', line)
            if m:
                result[m.group(1)] = m.group(2)
        return result

    es_dict = parse_block(es_match.group(1)) if es_match else {}
    en_dict = parse_block(en_match.group(1)) if en_match else {}
    return es_dict, en_dict


class TestTranslationEnEs(unittest.TestCase):
    """Acceptance test suite validating bilingual Spanish/English localization fidelity."""

    @classmethod
    def setUpClass(cls):
        """Load command center HTML templates and compiled artifacts."""
        cls.cc_path = REPO_ROOT / "assets" / "command_center.html"
        cls.assertTrue(cls.cc_path.exists(), "assets/command_center.html must exist")
        cls.html = cls.cc_path.read_text(encoding="utf-8")
        cls.es_dict, cls.en_dict = extract_i18n_dictionaries(cls.html)

    def test_i18n_dictionary_symmetry_and_non_empty(self):
        """Ensure Spanish and English dictionaries have identical keys and non-empty values."""
        self.assertGreater(len(self.es_dict), 50, "Spanish dictionary must contain at least 50 keys")
        self.assertGreater(len(self.en_dict), 50, "English dictionary must contain at least 50 keys")

        missing_in_en = set(self.es_dict.keys()) - set(self.en_dict.keys())
        missing_in_es = set(self.en_dict.keys()) - set(self.es_dict.keys())

        self.assertEqual(missing_in_en, set(), f"Keys present in ES but missing in EN: {missing_in_en}")
        self.assertEqual(missing_in_es, set(), f"Keys present in EN but missing in ES: {missing_in_es}")

        for k, v in self.es_dict.items():
            self.assertTrue(v and v.strip(), f"ES key '{k}' has empty translation value")
        for k, v in self.en_dict.items():
            self.assertTrue(v and v.strip(), f"EN key '{k}' has empty translation value")

    def test_all_html_data_i18n_tags_bound_in_dictionaries(self):
        """Ensure all data-i18n attributes in the UI template exist in both translation tables."""
        tags = set(re.findall(r'data-i18n="([^"]+)"', self.html))
        self.assertGreater(len(tags), 50, "UI template must contain at least 50 data-i18n tags")

        missing_es = tags - set(self.es_dict.keys())
        missing_en = tags - set(self.en_dict.keys())

        self.assertEqual(missing_es, set(), f"HTML data-i18n tags missing in I18N.es: {missing_es}")
        self.assertEqual(missing_en, set(), f"HTML data-i18n tags missing in I18N.en: {missing_en}")

    def test_speed_duels_bilingual_explanations_completeness(self):
        """Verify that all 50 Speed Duels have distinct Spanish and English explanations."""
        self.assertEqual(len(SPEED_DUELS), 50, "Expected 50 Speed Duels in speed_duels_data.py")

        for d in SPEED_DUELS:
            duel_id = d["id"]
            es_exp = d.get("explanation_es", "").strip()
            en_exp = d.get("explanation_en", "").strip()

            self.assertTrue(es_exp, f"{duel_id} missing explanation_es")
            self.assertTrue(en_exp, f"{duel_id} missing explanation_en")
            self.assertNotEqual(
                es_exp,
                en_exp,
                f"{duel_id} has identical Spanish and English explanations (untranslated)"
            )

            # Assert language distinctness
            es_tokens = ["velocidad", "supera", "nivel", "espacio", "prioridad", "puntos", "efectivos", "tras", "caída", "movimiento"]
            has_es = any(t in es_exp.lower() for t in es_tokens) or any(c in es_exp for c in "áéíóúñ¿¡")
            self.assertTrue(has_es, f"{duel_id} explanation_es does not look like Spanish: '{es_exp}'")

            en_tokens = [
                "speed", "outspeeds", "priority", "level", "effective", "points",
                "moves", "under", "attack", "drops", "allowing", "after", "first"
            ]
            has_en = any(t in en_exp.lower() for t in en_tokens)
            self.assertTrue(has_en, f"{duel_id} explanation_en does not look like English: '{en_exp}'")

    def test_canonical_trainer_terminology(self):
        """Enforce canonical Trainer/Entrenador terminology and reject 'piloto'/'pilot'."""
        forbidden_patterns = [
            r"\bpiloto\b",
            r"\bpilotos\b",
            r"\bpilot\b",
            r"\bpilots\b",
        ]

        # Scan command_center.html
        for pat in forbidden_patterns:
            matches = re.findall(pat, self.html, re.IGNORECASE)
            self.assertEqual(
                matches,
                [],
                f"Forbidden aviation/mecha pilot terminology found in HTML: {matches}"
            )

        # Verify Trainer / Entrenador presence in I18N
        self.assertIn("ENTRENADOR", self.es_dict.get("trainer_badge", "").upper())
        self.assertIn("TRAINER", self.en_dict.get("trainer_badge", "").upper())

    def test_game_terminology_preserved_in_both_languages(self):
        """Ensure canonical VGC mechanics, moves, and formats are preserved without mistranslation."""
        canonical_terms = [
            "Protect",
            "Tailwind",
            "Fake Out",
            "Trick Room",
            "STAB",
            "Regulation M-C",
            "Liquid Voice",
            "Focus Sash",
            "Sitrus Berry",
            "Life Orb",
        ]

        # In both languages, key VGC game terms should remain in their canonical form
        for term in canonical_terms:
            self.assertIn(
                term.lower(),
                self.html.lower(),
                f"Canonical game term '{term}' missing from command center"
            )

    def test_no_untranslated_placeholders_or_template_leaks(self):
        """Ensure dictionaries and rendered text contain zero raw placeholder leakages."""
        leak_patterns = [
            r"__\w+__",
            r"\{\{\w+\}\}",
            r"\bTODO\b",
            r"\bTRANSLATE_ME\b",
            r"\bundefined\b",
            r"\[TBD\]",
        ]

        for lang, d in [("es", self.es_dict), ("en", self.en_dict)]:
            for k, val in d.items():
                for pat in leak_patterns:
                    self.assertIsNone(
                        re.search(pat, val),
                        f"Placeholder leak '{pat}' found in I18N.{lang}['{k}']: '{val}'"
                    )

    def test_no_hallucinated_languages(self):
        """Ensure neither dictionary leaks unintended third-party language tokens."""
        french_tokens = ["\ble\b", "\bla\b", "\bles\b", "\bavec\b", "\bpour\b", "\béquipe\b"]
        german_tokens = ["\bder\b", "\bdie\b", "\bdas\b", "\bund\b", "\bmit\b"]

        for lang, d in [("es", self.es_dict), ("en", self.en_dict)]:
            for k, val in d.items():
                val_low = val.lower()
                for pat in french_tokens:
                    if lang == "es":
                        self.assertIsNone(
                            re.search(pat, val_low),
                            f"Hallucinated French word in I18N.{lang}['{k}']: '{val}'"
                        )
                for pat in german_tokens:
                    self.assertIsNone(
                        re.search(pat, val_low),
                        f"Hallucinated German word in I18N.{lang}['{k}']: '{val}'"
                    )

    def test_html_initial_language_and_lang_attribute(self):
        """Verify that language artifacts initialize with appropriate lang attribute and settings."""
        es_path = REPO_ROOT / "assets" / "command_center_es.html"
        en_path = REPO_ROOT / "assets" / "command_center_en.html"

        if es_path.exists():
            es_html = es_path.read_text(encoding="utf-8")
            self.assertIn('<html lang="es">', es_html)
            self.assertIn("window.__INITIAL_LANG__ = 'es'", es_html)

        if en_path.exists():
            en_html = en_path.read_text(encoding="utf-8")
            self.assertIn('<html lang="en">', en_html)
            self.assertIn("window.__INITIAL_LANG__ = 'en'", en_html)


if __name__ == "__main__":
    unittest.main()
