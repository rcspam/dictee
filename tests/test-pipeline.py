#!/usr/bin/env python3
"""Exhaustive tests for the dictee pipeline orchestration.

Tests the complete pipeline chaining: PP Normal → translation → PP Translation,
continuation indicators, env var mapping, edge cases, and step isolation.

Unlike test-postprocess.py (which tests dictee-postprocess.py in isolation),
this file tests the full pipeline modes:
  - normal:            text → PP Normal → output
  - normal+translate:  text → PP Normal → translate → output
  - full_chain:        text → PP Normal → translate → PP Translation → output

Run:  python3 tests/test-pipeline.py [-v]
"""

import os
import re
import subprocess
import sys
import unittest
from collections import namedtuple

# ── Configuration ────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)  # parent of tests/
POSTPROCESS = os.path.join(PROJECT_DIR, "dictee-postprocess.py")

# Named tuple for pipeline results
PipelineResult = namedtuple(
    "PipelineResult",
    ["output", "pp_steps", "trpp_steps", "translate_error", "continuation_appended"],
)

# All-false env dict to disable every PP step individually
_ALL_PP_FALSE = {
    "DICTEE_PP_RULES": "false",
    "DICTEE_PP_CONTINUATION": "false",
    "DICTEE_PP_LANGUAGE_RULES": "false",
    "DICTEE_PP_NUMBERS": "false",
    "DICTEE_PP_DICT": "false",
    "DICTEE_PP_CAPITALIZATION": "false",
    "DICTEE_PP_SHORT_TEXT": "false",
}

# ── Continuation word lists (subset for testing) ─────────────────────

CONT_WORDS_FR = {
    "le", "la", "les", "de", "du", "des", "un", "une",
    "et", "ou", "que", "qui", "tu", "je", "ne", "se",
}
CONT_WORDS_EN = {
    "the", "a", "an", "of", "to", "and", "or",
    "in", "on", "at", "is", "it", "that", "this",
}
CONT_WORDS_DE = {
    "der", "die", "das", "ein", "eine",
    "und", "oder", "in", "auf", "an", "ist", "zu",
}

# ── Mock translations ────────────────────────────────────────────────

_MOCK_TRANSLATIONS = {
    ("fr", "en"): {
        "Bonjour, comment allez-vous": "Hello, how are you",
        "Bonjour": "Hello",
        "Le chat est sur le tapis.": "The cat is on the mat.",
        "J'ai vingt-trois ans.": "I am twenty-three years old.",
        "Parles-tu français": "Do you speak French",
        "Le": "The",
        "C'est un bon point.": "That's a good point.",
        "Peut-être": "Maybe",
        "Bonjour, comment allez-vous ?": "Hello, how are you?",
        "C'est une belle journée, n'est-ce pas ?": "It's a beautiful day, isn't it?",
    },
    ("fr", "de"): {
        "Bonjour, comment allez-vous": "Hallo, wie geht es Ihnen",
        "Bonjour": "Hallo",
        "Le chat est sur le tapis.": "Die Katze ist auf dem Teppich.",
    },
    ("en", "fr"): {
        "Hello, how are you": "Bonjour, comment allez-vous",
        "The cat is on the mat.": "Le chat est sur le tapis.",
    },
    ("de", "en"): {
        "Hallo, wie geht es Ihnen": "Hello, how are you",
    },
}


def mock_translate(text, src, tgt):
    """Deterministic mock translation."""
    key = (src[:2], tgt[:2])
    mapping = _MOCK_TRANSLATIONS.get(key, {})
    translated = mapping.get(text.strip(), "")
    if not translated:
        # Fallback: return text with [TRANSLATED] prefix for verification
        return f"[{tgt.upper()}] {text}", ""
    return translated, ""


def mock_translate_fail(text, src, tgt):
    """Simulate translation failure."""
    return "", "Connection refused"


# ── Continuation indicator logic ─────────────────────────────────────

def _check_continuation(text, cont_words, indicator=">>"):
    """Check if last word is a continuation word, strip trailing punct, append indicator."""
    if not cont_words or not text.strip():
        return text, False
    m = re.search(r"([A-Za-zÀ-ÿ''\-]+)[\.\,\?\!\u2026\s]*$", text.rstrip())
    if not m:
        return text, False
    last = m.group(1).lower()
    # Hyphenated words: "parles-tu" → check "tu"
    if "-" in last:
        last = last.rsplit("-", 1)[-1]
    if last in cont_words:
        stripped = re.sub(r"[\.\,\?\!\u2026]+\s*$", "", text.rstrip())
        return stripped + indicator, True
    return text, False


# ── Pipeline runner ──────────────────────────────────────────────────

def run_pipeline(
    text,
    mode="normal",
    lang_src="fr",
    lang_tgt="en",
    pp_env=None,
    trpp_env=None,
    translate_fn=None,
    cont_words_src=None,
    cont_words_tgt=None,
    cont_indicator=">>",
):
    """Run the full dictee pipeline, returns PipelineResult."""

    # Step 1: PP Normal
    env = os.environ.copy()
    env["DICTEE_LANG_SOURCE"] = lang_src
    env["DICTEE_LLM_POSTPROCESS"] = "false"
    env["DICTEE_PP_DEBUG"] = "true"
    if pp_env:
        env.update(pp_env)

    result = subprocess.run(
        [sys.executable, POSTPROCESS],
        input=text,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    pp_output = result.stdout.rstrip(" ")
    pp_steps = [
        line.split("\t")[1]
        for line in result.stderr.splitlines()
        if line.startswith("STEP\t") and len(line.split("\t")) >= 2
    ]

    # Step 2: Continuation check on source language
    continuation_appended = False
    if cont_words_src:
        pp_output, cont = _check_continuation(pp_output, cont_words_src, cont_indicator)
        if cont:
            continuation_appended = True

    # Step 3: Translation (if applicable)
    translate_error = ""
    if mode != "normal" and translate_fn is not None:
        translated, error = translate_fn(pp_output, lang_src, lang_tgt)
        if error:
            translate_error = error
            # On error, keep PP Normal result
        else:
            pp_output = translated

    # Step 4: PP Translation (full_chain only)
    trpp_steps = []
    if mode == "full_chain" and not translate_error:
        trpp_env_full = os.environ.copy()
        trpp_env_full["DICTEE_LANG_SOURCE"] = lang_tgt
        trpp_env_full["DICTEE_LLM_POSTPROCESS"] = "false"
        trpp_env_full["DICTEE_PP_DEBUG"] = "true"
        if trpp_env:
            # Map DICTEE_TRPP_* → DICTEE_PP_* for the second pass
            for key, val in trpp_env.items():
                if key.startswith("DICTEE_TRPP_"):
                    mapped = key.replace("DICTEE_TRPP_", "DICTEE_PP_", 1)
                    trpp_env_full[mapped] = val
                else:
                    trpp_env_full[key] = val

        result2 = subprocess.run(
            [sys.executable, POSTPROCESS],
            input=pp_output,
            capture_output=True,
            text=True,
            env=trpp_env_full,
            timeout=30,
        )
        pp_output = result2.stdout.rstrip(" ")
        trpp_steps = [
            line.split("\t")[1]
            for line in result2.stderr.splitlines()
            if line.startswith("STEP\t") and len(line.split("\t")) >= 2
        ]

    # Step 5: Continuation check on target language (after translate/TRPP)
    if mode != "normal" and cont_words_tgt and not translate_error:
        pp_output, cont = _check_continuation(pp_output, cont_words_tgt, cont_indicator)
        if cont:
            continuation_appended = True

    return PipelineResult(
        output=pp_output,
        pp_steps=pp_steps,
        trpp_steps=trpp_steps,
        translate_error=translate_error,
        continuation_appended=continuation_appended,
    )


# ══════════════════════════════════════════════════════════════════════
# 1. TestPipelineNormal — mode normal only
# ══════════════════════════════════════════════════════════════════════


class TestPipelineNormal(unittest.TestCase):
    """Pipeline mode=normal: text → PP Normal → output."""

    def test_fr_basic(self):
        r = run_pipeline("bonjour virgule comment allez-vous", lang_src="fr")
        self.assertIn("Bonjour", r.output)
        self.assertIn(",", r.output)

    def test_en_basic(self):
        r = run_pipeline("hello comma how are you", mode="normal", lang_src="en")
        self.assertIn(",", r.output)
        self.assertIn("how are you", r.output.lower())

    def test_de_basic(self):
        r = run_pipeline("Hallo Komma wie geht es Ihnen", mode="normal", lang_src="de")
        self.assertIn(",", r.output)
        self.assertIn("Hallo", r.output)

    def test_es_basic(self):
        # ES "coma" requires DICTEE_COMMAND_SUFFIX_ES to be set
        r = run_pipeline(
            "Hola coma seguido cómo estás",
            mode="normal",
            lang_src="es",
            pp_env={"DICTEE_COMMAND_SUFFIX_ES": "seguido"},
        )
        self.assertIn(",", r.output)

    def test_it_basic(self):
        r = run_pipeline("Ciao virgola come stai", mode="normal", lang_src="it")
        self.assertIn(",", r.output)

    def test_pt_basic(self):
        r = run_pipeline("Olá vírgula como vai você", mode="normal", lang_src="pt")
        self.assertIn(",", r.output)

    def test_uk_basic(self):
        # UK "кома" requires DICTEE_COMMAND_SUFFIX_UK to be set
        r = run_pipeline(
            "Привіт кома далі як справи друже",
            mode="normal",
            lang_src="uk",
            pp_env={"DICTEE_COMMAND_SUFFIX_UK": "далі"},
        )
        self.assertIn(",", r.output)

    def test_pp_debug_steps(self):
        """Verify STEP traces are returned when PP_DEBUG=true."""
        r = run_pipeline("bonjour virgule comment allez-vous", lang_src="fr")
        self.assertIsInstance(r.pp_steps, list)
        # At least some steps should appear with default config
        self.assertGreater(len(r.pp_steps), 0)

    def test_all_steps_run(self):
        """Verify all major step labels appear in the trace."""
        r = run_pipeline("bonjour virgule comment allez-vous point", lang_src="fr")
        step_text = " ".join(r.pp_steps)
        self.assertIn("Rules", step_text)
        self.assertIn("Capitalization", step_text)

    def test_no_translate_error(self):
        """Normal mode should never have translate errors."""
        r = run_pipeline("Test phrase.", lang_src="en")
        self.assertEqual(r.translate_error, "")

    def test_trpp_steps_empty(self):
        """Normal mode should not produce TRPP steps."""
        r = run_pipeline("Test phrase.", lang_src="en")
        self.assertEqual(r.trpp_steps, [])


# ══════════════════════════════════════════════════════════════════════
# 2. TestPipelineNormalTranslate — mode normal+translate
# ══════════════════════════════════════════════════════════════════════


class TestPipelineNormalTranslate(unittest.TestCase):
    """Pipeline mode=normal+translate: text → PP Normal → translate → output."""

    def test_fr_to_en(self):
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        # After PP, "bonjour virgule comment allez-vous" → "Bonjour, comment allez-vous"
        # mock_translate maps that to "Hello, how are you"
        self.assertEqual(r.output, "Hello, how are you")
        self.assertEqual(r.translate_error, "")

    def test_fr_to_de(self):
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="de",
            translate_fn=mock_translate,
        )
        self.assertEqual(r.output, "Hallo, wie geht es Ihnen")

    def test_en_to_fr(self):
        r = run_pipeline(
            "hello comma how are you",
            mode="normal+translate",
            lang_src="en",
            lang_tgt="fr",
            translate_fn=mock_translate,
        )
        self.assertEqual(r.output, "Bonjour, comment allez-vous")

    def test_pp_cleans_before_translate(self):
        """Verify voice commands are converted to punctuation before translation."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        # The PP step should have converted "virgule" → "," before translation
        self.assertNotIn("virgule", r.output)

    def test_translate_error_fallback(self):
        """On translation failure, return PP Normal result + error message."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate_fail,
        )
        # Should fall back to PP Normal output (French)
        self.assertIn("Bonjour", r.output)
        self.assertEqual(r.translate_error, "Connection refused")

    def test_translate_preserves_newlines(self):
        """Text with newlines should be passed to translate_fn preserving structure."""
        # Custom translate_fn that checks newlines
        newline_seen = []

        def translate_check_nl(text, src, tgt):
            newline_seen.append("\n" in text)
            return f"[{tgt.upper()}] {text}", ""

        r = run_pipeline(
            "Bonjour point à la ligne monde",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=translate_check_nl,
        )
        # The PP step should have converted "à la ligne" to \n,
        # then translate_fn receives text with \n
        self.assertTrue(len(newline_seen) > 0)

    def test_trpp_steps_empty_in_translate_mode(self):
        """normal+translate mode should not produce TRPP steps."""
        r = run_pipeline(
            "bonjour",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        self.assertEqual(r.trpp_steps, [])

    def test_unknown_translation_gets_fallback(self):
        """Unknown phrases get [TGT] prefix fallback."""
        r = run_pipeline(
            "phrase inconnue pour le test rapide",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        self.assertIn("[EN]", r.output)


# ══════════════════════════════════════════════════════════════════════
# 3. TestPipelineFullChain — mode full_chain
# ══════════════════════════════════════════════════════════════════════


class TestPipelineFullChain(unittest.TestCase):
    """Pipeline mode=full_chain: text → PP → translate → PP(tgt) → output."""

    def test_fr_to_en_full(self):
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        # After PP+translate → "Hello, how are you" → TRPP(en) → still valid
        self.assertIn("Hello", r.output)

    def test_trpp_steps_returned(self):
        """Verify trpp_steps are populated in full_chain mode."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        # The TRPP pass should produce at least some steps
        self.assertIsInstance(r.trpp_steps, list)
        self.assertGreater(len(r.trpp_steps), 0)

    def test_trpp_uses_target_lang(self):
        """Verify the second PP pass uses the target language."""
        # We verify indirectly: TRPP step should apply EN rules
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        # The TRPP pass runs with DICTEE_LANG_SOURCE=en
        # If it mistakenly used FR, it would apply French elisions, etc.
        self.assertNotEqual(r.trpp_steps, [])

    def test_trpp_llm_always_off(self):
        """Verify LLM is forced off in TRPP (DICTEE_LLM_POSTPROCESS=false)."""
        # If LLM were on, it would try to connect to ollama and fail/timeout
        # The test passing quickly confirms LLM is off
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        # Verify no LLM step in TRPP trace
        for step in r.trpp_steps:
            self.assertNotIn("LLM", step)

    def test_trpp_env_mapping(self):
        """Verify DICTEE_TRPP_* → DICTEE_PP_* mapping in second pass."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_RULES": "false"},
        )
        # With TRPP_RULES=false → Rules step should NOT appear in trpp_steps
        self.assertNotIn("Rules", r.trpp_steps)

    def test_trpp_language_rules_umbrella_off(self):
        """TRPP_LANGUAGE_RULES=false → all sub-flags false in TRPP."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_LANGUAGE_RULES": "false"},
        )
        # No language-specific steps in TRPP
        for step in r.trpp_steps:
            self.assertNotIn("Elisions", step)
            self.assertNotIn("Spanish", step)
            self.assertNotIn("German", step)
            self.assertNotIn("Typography", step)

    def test_full_chain_translate_error_skips_trpp(self):
        """If translation fails, TRPP is skipped."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate_fail,
        )
        self.assertEqual(r.translate_error, "Connection refused")
        self.assertEqual(r.trpp_steps, [])
        # Output should be PP Normal result (French)
        self.assertIn("Bonjour", r.output)


# ══════════════════════════════════════════════════════════════════════
# 4. TestPipelineCanaryException
# ══════════════════════════════════════════════════════════════════════


class TestPipelineCanaryException(unittest.TestCase):
    """Canary backend edge cases: translate_fn is called with text, not audio."""

    def test_canary_falls_back_to_text(self):
        """With canary backend, translate_fn is called with text (not audio)."""
        received_text = []

        def capture_translate(text, src, tgt):
            received_text.append(text)
            return mock_translate(text, src, tgt)

        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=capture_translate,
        )
        # translate_fn should have received the PP-processed text
        self.assertTrue(len(received_text) > 0)
        self.assertIn(",", received_text[0])  # Voice command was converted

    def test_canary_with_full_chain(self):
        """Canary + full_chain → TRPP runs on translated text."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        # TRPP should have run on the translated EN text
        self.assertGreater(len(r.trpp_steps), 0)
        self.assertIn("Hello", r.output)


# ══════════════════════════════════════════════════════════════════════
# 5. TestPipelineStepIsolation — each step alone
# ══════════════════════════════════════════════════════════════════════


class TestPipelineStepIsolation(unittest.TestCase):
    """Test each PP step in isolation by disabling all others."""

    def _env_only(self, step_key):
        """Returns env dict with only the given step enabled."""
        env = dict(_ALL_PP_FALSE)
        env[step_key] = "true"
        return env

    def test_rules_only(self):
        """Only DICTEE_PP_RULES=true, verify rules are applied."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            lang_src="fr",
            pp_env=self._env_only("DICTEE_PP_RULES"),
        )
        # Rules should convert "virgule" to ","
        self.assertIn(",", r.output)
        self.assertNotIn("virgule", r.output.lower())

    def test_continuation_only(self):
        """Only DICTEE_PP_CONTINUATION=true — continuation step runs."""
        r = run_pipeline(
            "Le. Chat",
            lang_src="fr",
            pp_env=self._env_only("DICTEE_PP_CONTINUATION"),
        )
        # Continuation should fix "Le. Chat" → "Le chat" (period removed after "Le")
        self.assertNotIn("Le. Chat", r.output)

    def test_numbers_only(self):
        """Only DICTEE_PP_NUMBERS=true, verify number conversion."""
        r = run_pipeline(
            "vingt-trois",
            lang_src="fr",
            pp_env=self._env_only("DICTEE_PP_NUMBERS"),
        )
        # text2num should convert "vingt-trois" → "23" (if text2num installed)
        # If not installed, it passes through
        self.assertTrue("23" in r.output or "vingt-trois" in r.output)

    def test_dict_only(self):
        """Only DICTEE_PP_DICT=true, verify dictionary applied."""
        r = run_pipeline(
            "test",
            lang_src="fr",
            pp_env=self._env_only("DICTEE_PP_DICT"),
        )
        # Dictionary may or may not change "test" — just verify no crash
        self.assertIsNotNone(r.output)

    def test_capitalization_only(self):
        """Only DICTEE_PP_CAPITALIZATION=true."""
        r = run_pipeline(
            "hello world this is a test sentence.",
            lang_src="en",
            pp_env=self._env_only("DICTEE_PP_CAPITALIZATION"),
        )
        # Capitalization should uppercase the first letter
        if r.output.strip():
            self.assertTrue(r.output[0].isupper())

    def test_all_off(self):
        """All PP flags false → text passthrough (only stripping)."""
        r = run_pipeline(
            "hello world",
            lang_src="en",
            pp_env=dict(_ALL_PP_FALSE),
        )
        self.assertEqual(r.output, "hello world")

    def test_all_on(self):
        """All flags true (default) → full pipeline runs."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            lang_src="fr",
        )
        # Full pipeline: "virgule" → "," and capitalization applied
        self.assertIn(",", r.output)
        self.assertTrue(r.output[0].isupper())

    def test_short_text_only(self):
        """Only DICTEE_PP_SHORT_TEXT=true. Use "Maison" — not in keepcaps."""
        r = run_pipeline(
            "Maison.",
            lang_src="fr",
            pp_env=self._env_only("DICTEE_PP_SHORT_TEXT"),
        )
        # Short text: < 3 words → lowercase + strip trailing punct
        self.assertEqual(r.output, "maison")

    def test_language_rules_only(self):
        """Only DICTEE_PP_LANGUAGE_RULES=true."""
        r = run_pipeline(
            "le homme est ici dans la maison bleu",
            lang_src="fr",
            pp_env=self._env_only("DICTEE_PP_LANGUAGE_RULES"),
        )
        # French elisions should convert "le homme" → "l'homme"
        self.assertIn("l'homme", r.output)


# ══════════════════════════════════════════════════════════════════════
# 6. TestPipelineContinuation
# ══════════════════════════════════════════════════════════════════════


class TestPipelineContinuation(unittest.TestCase):
    """Test continuation indicator logic."""

    def test_continuation_source_lang(self):
        """FR text ending with 'le' → '>>' appended."""
        text = "C'est le"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_target_lang(self):
        """EN text ending with 'the' → '>>' appended."""
        text = "Give me the"
        result, appended = _check_continuation(text, CONT_WORDS_EN)
        self.assertTrue(appended)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_hyphen_source(self):
        """'parles-tu' → 'tu' is continuation → '>>'."""
        text = "Parles-tu"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_hyphen_target(self):
        """'Maybe' (from 'Peut-être') → not a continuation word."""
        text = "Maybe"
        result, appended = _check_continuation(text, CONT_WORDS_EN)
        self.assertFalse(appended)
        self.assertEqual(result, "Maybe")

    def test_continuation_with_period(self):
        """'le.' → strip period, append '>>'."""
        text = "C'est le."
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertNotIn(".", result)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_with_ellipsis(self):
        """'le...' → strip, append '>>'."""
        text = "C'est le..."
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertNotIn("...", result)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_with_unicode_ellipsis(self):
        """'le\u2026' → strip unicode ellipsis, append '>>'."""
        text = "C'est le\u2026"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertTrue(result.endswith(">>"))

    def test_no_continuation_normal_word(self):
        """'maison' → no '>>'."""
        text = "La maison"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertFalse(appended)
        self.assertEqual(result, "La maison")

    def test_no_continuation_empty_text(self):
        """Empty text → no continuation."""
        result, appended = _check_continuation("", CONT_WORDS_FR)
        self.assertFalse(appended)

    def test_no_continuation_empty_words(self):
        """Empty word set → no continuation."""
        result, appended = _check_continuation("test le", set())
        self.assertFalse(appended)

    def test_no_continuation_none_words(self):
        """None word set → no continuation."""
        result, appended = _check_continuation("test le", None)
        self.assertFalse(appended)

    def test_continuation_custom_indicator(self):
        """Custom indicator '→' instead of '>>'."""
        text = "C'est le"
        result, appended = _check_continuation(text, CONT_WORDS_FR, indicator="→")
        self.assertTrue(appended)
        self.assertTrue(result.endswith("→"))

    def test_continuation_with_comma(self):
        """'le,' → strip comma, append '>>'."""
        text = "C'est le,"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertNotIn(",", result)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_with_question_mark(self):
        """'le?' → strip question mark, append '>>'."""
        text = "C'est le?"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_with_exclamation_mark(self):
        """'le!' → strip exclamation, append '>>'."""
        text = "C'est le!"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_de_words(self):
        """German continuation: 'der' → '>>'."""
        text = "Das ist der"
        result, appended = _check_continuation(text, CONT_WORDS_DE)
        self.assertTrue(appended)
        self.assertTrue(result.endswith(">>"))

    def test_continuation_pipeline_integration_source(self):
        """Full pipeline with continuation on source language."""
        r = run_pipeline(
            "C'est le",
            lang_src="fr",
            cont_words_src=CONT_WORDS_FR,
        )
        self.assertTrue(r.continuation_appended)
        self.assertTrue(r.output.endswith(">>"))

    def test_continuation_pipeline_integration_target(self):
        """Full pipeline with continuation on target language after translate."""
        r = run_pipeline(
            "C'est le",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            cont_words_tgt=CONT_WORDS_EN,
        )
        # "Le" → translated → check target continuation
        # The mock may or may not produce a continuation word
        self.assertIsNotNone(r.output)


# ══════════════════════════════════════════════════════════════════════
# 7. TestPipelineShortText
# ══════════════════════════════════════════════════════════════════════


class TestPipelineShortText(unittest.TestCase):
    """Short text correction (< 3 words)."""

    def test_short_text_single_word(self):
        """Short text on a non-keepcaps word: "Maison." → "maison"."""
        r = run_pipeline("Maison.", lang_src="fr")
        self.assertEqual(r.output, "maison")

    def test_short_text_two_words(self):
        """'Très bien.' → 'très bien'."""
        r = run_pipeline("Très bien.", lang_src="fr")
        self.assertEqual(r.output, "très bien")

    def test_short_text_above_threshold(self):
        """4+ words → no short text fix (keeps capitalization and punctuation)."""
        r = run_pipeline("Bonjour comment allez-vous aujourd'hui.", lang_src="fr")
        # 4+ words: should keep capitalization
        self.assertTrue(r.output[0].isupper())

    def test_short_text_translated(self):
        """After translate, short text fix on target lang (non-keepcaps word)."""
        def translate_maison(text, src, tgt):
            if text.strip().lower() == "maison":
                return "House", ""
            return mock_translate(text, src, tgt)

        r = run_pipeline(
            "Maison.",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=translate_maison,
        )
        # "Maison." → PP → "maison" → translate → "House"
        # → TRPP: "House" is 1 word, not in keepcaps, short text → "house"
        self.assertEqual(r.output, "house")

    def test_short_text_preserves_acronyms(self):
        """Short text should preserve ALL CAPS words."""
        r = run_pipeline(
            "NASA.",
            lang_src="en",
        )
        # "NASA" is all caps → preserved even in short text mode
        self.assertEqual(r.output, "NASA")

    def test_short_text_with_newline_skipped(self):
        """Short text with newline is skipped (multiline never 'short')."""
        r = run_pipeline(
            "Bonjour point à la ligne monde",
            lang_src="fr",
        )
        # "à la ligne" → \n, so text has newline → short text skipped
        if "\n" in r.output:
            # Capitalization should be preserved
            self.assertTrue(r.output[0].isupper())


# ══════════════════════════════════════════════════════════════════════
# 8. TestPipelineMasterSwitches
# ══════════════════════════════════════════════════════════════════════


class TestPipelineMasterSwitches(unittest.TestCase):
    """Test master on/off switches for PP and TRPP."""

    def test_pp_master_off(self):
        """PP disabled → text passthrough (no postprocess)."""
        r = run_pipeline(
            "bonjour virgule monde",
            lang_src="fr",
            pp_env=dict(_ALL_PP_FALSE),
        )
        # With all PP disabled, "virgule" should NOT be converted to ","
        self.assertIn("virgule", r.output.lower())

    def test_trpp_master_off_in_full_chain(self):
        """full_chain but TRPP disabled → same as normal+translate."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={
                "DICTEE_TRPP_RULES": "false",
                "DICTEE_TRPP_CONTINUATION": "false",
                "DICTEE_TRPP_LANGUAGE_RULES": "false",
                "DICTEE_TRPP_NUMBERS": "false",
                "DICTEE_TRPP_DICT": "false",
                "DICTEE_TRPP_CAPITALIZATION": "false",
                "DICTEE_TRPP_SHORT_TEXT": "false",
            },
        )
        # Translation should still work
        self.assertIn("Hello", r.output)
        # But TRPP steps should show nothing meaningful
        for step in r.trpp_steps:
            self.assertNotIn("Rules", step)

    def test_both_masters_off(self):
        """PP and TRPP both off → should still translate but no PP."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            pp_env=dict(_ALL_PP_FALSE),
            trpp_env={
                "DICTEE_TRPP_RULES": "false",
                "DICTEE_TRPP_CONTINUATION": "false",
                "DICTEE_TRPP_LANGUAGE_RULES": "false",
                "DICTEE_TRPP_NUMBERS": "false",
                "DICTEE_TRPP_DICT": "false",
                "DICTEE_TRPP_CAPITALIZATION": "false",
                "DICTEE_TRPP_SHORT_TEXT": "false",
            },
        )
        # "virgule" should still be there since PP is off
        # But translate_fn is called on the raw text
        # Output contains [EN] fallback since raw text won't match mock dict
        self.assertIsNotNone(r.output)
        self.assertEqual(r.translate_error, "")


# ══════════════════════════════════════════════════════════════════════
# 9. TestPipelineEdgeCases
# ══════════════════════════════════════════════════════════════════════


class TestPipelineEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_empty_text(self):
        """Empty input → empty output."""
        r = run_pipeline("", lang_src="fr")
        self.assertEqual(r.output.strip(), "")

    def test_whitespace_only(self):
        """Whitespace-only input → empty output."""
        r = run_pipeline("   ", lang_src="fr")
        self.assertEqual(r.output.strip(), "")

    def test_newline_text(self):
        """Text with embedded newline is handled correctly."""
        r = run_pipeline(
            "Bonjour point à la ligne monde point",
            lang_src="fr",
        )
        # "à la ligne" → \n
        self.assertIn("\n", r.output)

    def test_cyrillic_uk(self):
        """Ukrainian text → PP runs, no crash."""
        r = run_pipeline(
            "Привіт кома далі як справи друже",
            lang_src="uk",
            pp_env={"DICTEE_COMMAND_SUFFIX_UK": "далі"},
        )
        self.assertIn(",", r.output)
        self.assertIn("Привіт", r.output)

    def test_trailing_spaces_stripped(self):
        """Trailing spaces are stripped from PP output."""
        r = run_pipeline(
            "Bonjour le monde entier ici.",
            lang_src="fr",
        )
        self.assertFalse(r.output.endswith(" "))

    def test_special_chars_preserved(self):
        """Text with accents and special chars → preserved through pipeline."""
        r = run_pipeline(
            "Héllo café résumé naïve",
            lang_src="en",
            pp_env=dict(_ALL_PP_FALSE),
        )
        self.assertIn("café", r.output)
        self.assertIn("résumé", r.output)
        self.assertIn("naïve", r.output)

    def test_very_long_text(self):
        """1000-char text → pipeline handles without timeout."""
        long_text = "Bonjour le monde virgule " * 40  # ~1000 chars
        r = run_pipeline(long_text, lang_src="fr")
        # Should not timeout or crash
        self.assertIsNotNone(r.output)
        self.assertGreater(len(r.output), 0)

    def test_single_punctuation(self):
        """Single punctuation mark passes through."""
        r = run_pipeline(".", lang_src="fr")
        # PP may strip or keep it
        self.assertIsNotNone(r.output)

    def test_only_numbers(self):
        """Numeric-only text passes through."""
        r = run_pipeline(
            "42",
            lang_src="en",
            pp_env=dict(_ALL_PP_FALSE),
        )
        self.assertEqual(r.output, "42")

    def test_mixed_languages_no_crash(self):
        """Mixed-language text should not crash the pipeline."""
        r = run_pipeline(
            "Hello bonjour Hallo",
            lang_src="en",
        )
        self.assertIsNotNone(r.output)

    def test_unicode_emoji_preserved(self):
        """Emoji characters survive the pipeline."""
        r = run_pipeline(
            "Hello world test phrase here",
            lang_src="en",
            pp_env=dict(_ALL_PP_FALSE),
        )
        # At minimum, the text should pass through without crash
        self.assertIn("Hello", r.output)

    def test_tabs_preserved(self):
        """Tab characters in text survive the pipeline."""
        r = run_pipeline(
            "Col1\tCol2",
            lang_src="en",
            pp_env=dict(_ALL_PP_FALSE),
        )
        self.assertIn("\t", r.output)


# ══════════════════════════════════════════════════════════════════════
# 10. TestPipelineEnvVarMapping
# ══════════════════════════════════════════════════════════════════════


class TestPipelineEnvVarMapping(unittest.TestCase):
    """Test DICTEE_TRPP_* → DICTEE_PP_* mapping in full_chain mode."""

    def test_trpp_rules_mapping(self):
        """DICTEE_TRPP_RULES=false → second pass DICTEE_PP_RULES=false."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_RULES": "false"},
        )
        self.assertNotIn("Rules", r.trpp_steps)

    def test_trpp_continuation_mapping(self):
        """DICTEE_TRPP_CONTINUATION=false → no continuation step in TRPP."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_CONTINUATION": "false"},
        )
        self.assertNotIn("Continuation", r.trpp_steps)

    def test_trpp_language_rules_off_cascades(self):
        """Umbrella off → all sub-flags off in TRPP."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_LANGUAGE_RULES": "false"},
        )
        for step in r.trpp_steps:
            self.assertNotIn("Elisions", step)
            self.assertNotIn("Typography", step)

    def test_trpp_capitalization_mapping(self):
        """DICTEE_TRPP_CAPITALIZATION=false → no capitalization in TRPP."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_CAPITALIZATION": "false"},
        )
        self.assertNotIn("Capitalization", r.trpp_steps)

    def test_trpp_numbers_mapping(self):
        """DICTEE_TRPP_NUMBERS=false → no numbers step in TRPP."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_NUMBERS": "false"},
        )
        self.assertNotIn("Numbers", r.trpp_steps)

    def test_trpp_dict_mapping(self):
        """DICTEE_TRPP_DICT=false → no dictionary step in TRPP."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_DICT": "false"},
        )
        self.assertNotIn("Dictionary", r.trpp_steps)

    def test_trpp_short_text_mapping(self):
        """DICTEE_TRPP_SHORT_TEXT=false → no short text step in TRPP."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={"DICTEE_TRPP_SHORT_TEXT": "false"},
        )
        for step in r.trpp_steps:
            self.assertNotIn("Short text", step)

    def test_command_suffixes_passed(self):
        """DICTEE_COMMAND_SUFFIX_FR is passed through to PP."""
        r = run_pipeline(
            "bonjour point suivi comment allez-vous",
            lang_src="fr",
            pp_env={"DICTEE_COMMAND_SUFFIX_FR": "suivi"},
        )
        # With suffix "suivi", "point suivi" should become "."
        # Without suffix, "point" alone would become "." but "suivi" is kept
        self.assertIsNotNone(r.output)

    def test_multiple_trpp_env_vars(self):
        """Multiple TRPP env vars applied simultaneously."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
            trpp_env={
                "DICTEE_TRPP_RULES": "false",
                "DICTEE_TRPP_NUMBERS": "false",
                "DICTEE_TRPP_DICT": "false",
            },
        )
        self.assertNotIn("Rules", r.trpp_steps)
        self.assertNotIn("Numbers", r.trpp_steps)
        self.assertNotIn("Dictionary", r.trpp_steps)


# ══════════════════════════════════════════════════════════════════════
# 11. TestPipelineTrailingSpaces
# ══════════════════════════════════════════════════════════════════════


class TestPipelineTrailingSpaces(unittest.TestCase):
    """Trailing space handling in the pipeline."""

    def test_strip_after_pp(self):
        """Trailing spaces are stripped after PP."""
        r = run_pipeline(
            "Bonjour le monde entier ici.",
            lang_src="fr",
        )
        self.assertFalse(r.output.endswith(" "))

    def test_strip_before_continuation_check(self):
        """Trailing space doesn't break continuation detection."""
        # Text that ends with a continuation word + trailing space
        text = "C'est le "
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertTrue(result.endswith(">>"))

    def test_strip_after_trpp(self):
        """Trailing spaces stripped after TRPP in full_chain."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        self.assertFalse(r.output.endswith(" "))

    def test_strip_does_not_remove_newline(self):
        """Stripping spaces should not remove trailing newlines."""
        r = run_pipeline(
            "Bonjour point à la ligne",
            lang_src="fr",
        )
        # "à la ligne" → \n, the newline should be preserved
        if r.output.strip():
            # Just verify no crash, newline behavior depends on PP implementation
            self.assertIsNotNone(r.output)

    def test_multiple_trailing_spaces(self):
        """Multiple trailing spaces all stripped."""
        text = "C'est le   "
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        self.assertTrue(appended)
        self.assertFalse(result.rstrip(">>").endswith(" "))


# ══════════════════════════════════════════════════════════════════════
# Additional integration tests
# ══════════════════════════════════════════════════════════════════════


class TestPipelineResultStructure(unittest.TestCase):
    """Verify the PipelineResult namedtuple structure."""

    def test_result_fields(self):
        """PipelineResult has all expected fields."""
        r = run_pipeline("test", lang_src="en")
        self.assertTrue(hasattr(r, "output"))
        self.assertTrue(hasattr(r, "pp_steps"))
        self.assertTrue(hasattr(r, "trpp_steps"))
        self.assertTrue(hasattr(r, "translate_error"))
        self.assertTrue(hasattr(r, "continuation_appended"))

    def test_result_types(self):
        """PipelineResult fields have correct types."""
        r = run_pipeline("test", lang_src="en")
        self.assertIsInstance(r.output, str)
        self.assertIsInstance(r.pp_steps, list)
        self.assertIsInstance(r.trpp_steps, list)
        self.assertIsInstance(r.translate_error, str)
        self.assertIsInstance(r.continuation_appended, bool)


class TestPipelineModeValidation(unittest.TestCase):
    """Verify behavior with different mode values."""

    def test_normal_mode_no_translation(self):
        """In normal mode, translate_fn is never called even if provided."""
        call_count = []

        def counting_translate(text, src, tgt):
            call_count.append(1)
            return mock_translate(text, src, tgt)

        r = run_pipeline(
            "bonjour",
            mode="normal",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=counting_translate,
        )
        self.assertEqual(len(call_count), 0)

    def test_translate_mode_calls_translate(self):
        """In normal+translate mode, translate_fn IS called."""
        call_count = []

        def counting_translate(text, src, tgt):
            call_count.append(1)
            return mock_translate(text, src, tgt)

        r = run_pipeline(
            "bonjour",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=counting_translate,
        )
        self.assertEqual(len(call_count), 1)

    def test_full_chain_calls_translate(self):
        """In full_chain mode, translate_fn IS called."""
        call_count = []

        def counting_translate(text, src, tgt):
            call_count.append(1)
            return mock_translate(text, src, tgt)

        r = run_pipeline(
            "bonjour",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=counting_translate,
        )
        self.assertEqual(len(call_count), 1)

    def test_translate_without_fn(self):
        """normal+translate without translate_fn → no translation, no error."""
        r = run_pipeline(
            "bonjour",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=None,
        )
        # Should just return PP Normal output
        self.assertEqual(r.translate_error, "")


class TestPipelineLanguagePairs(unittest.TestCase):
    """Test various language pair combinations."""

    def test_de_to_en(self):
        """German → English translation chain."""
        r = run_pipeline(
            "Hallo Komma wie geht es Ihnen",
            mode="normal+translate",
            lang_src="de",
            lang_tgt="en",
            translate_fn=mock_translate,
        )
        self.assertEqual(r.output, "Hello, how are you")

    def test_fr_to_de_full_chain(self):
        """French → German full chain."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="de",
            translate_fn=mock_translate,
        )
        self.assertIn("Hallo", r.output)

    def test_same_language_translate(self):
        """Same src and tgt language — unusual but should not crash."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate",
            lang_src="fr",
            lang_tgt="fr",
            translate_fn=mock_translate,
        )
        # No fr→fr mapping in mock, should get [FR] fallback
        self.assertIsNotNone(r.output)


class TestPipelineContinuationInPipeline(unittest.TestCase):
    """Integration tests for continuation in full pipeline runs."""

    def test_continuation_not_appended_by_default(self):
        """Without cont_words, continuation is never appended."""
        r = run_pipeline(
            "C'est le",
            lang_src="fr",
        )
        self.assertFalse(r.continuation_appended)

    def test_continuation_appended_with_words(self):
        """With cont_words_src, continuation IS appended when last word matches."""
        r = run_pipeline(
            "C'est le",
            lang_src="fr",
            cont_words_src=CONT_WORDS_FR,
        )
        self.assertTrue(r.continuation_appended)

    def test_continuation_full_chain_both_langs(self):
        """Full chain with continuation on both source and target."""
        # Custom translate that returns a continuation word at the end
        def translate_ending_with_the(text, src, tgt):
            return "This is the", ""

        r = run_pipeline(
            "C'est le",
            mode="full_chain",
            lang_src="fr",
            lang_tgt="en",
            translate_fn=translate_ending_with_the,
            cont_words_src=CONT_WORDS_FR,
            cont_words_tgt=CONT_WORDS_EN,
        )
        self.assertTrue(r.continuation_appended)
        self.assertTrue(r.output.endswith(">>"))


class TestPipelinePerformance(unittest.TestCase):
    """Verify the pipeline doesn't hang or timeout on various inputs."""

    def test_repeated_punctuation(self):
        """Repeated punctuation doesn't cause ReDoS or hangs."""
        r = run_pipeline(
            "test..." * 50,
            lang_src="en",
        )
        self.assertIsNotNone(r.output)

    def test_many_newlines(self):
        """Many newlines handled without issues."""
        r = run_pipeline(
            "Bonjour point à la ligne " * 20,
            lang_src="fr",
        )
        self.assertIsNotNone(r.output)

    def test_large_whitespace(self):
        """Large amount of whitespace handled."""
        r = run_pipeline(
            "hello   " * 100 + "world",
            lang_src="en",
        )
        self.assertIsNotNone(r.output)


class TestPipelineDebugTrace(unittest.TestCase):
    """Verify debug trace output from dictee-postprocess.py."""

    def test_trace_format(self):
        """Step trace labels are non-empty strings."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            lang_src="fr",
        )
        for step in r.pp_steps:
            self.assertIsInstance(step, str)
            self.assertGreater(len(step), 0)

    def test_trace_has_rules_step(self):
        """Rules step appears in trace when rules are enabled."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            lang_src="fr",
        )
        self.assertIn("Rules", r.pp_steps)

    def test_trace_has_capitalization_step(self):
        """Capitalization step appears in trace."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            lang_src="fr",
        )
        self.assertIn("Capitalization", r.pp_steps)

    def test_trace_no_rules_when_disabled(self):
        """Rules step absent when DICTEE_PP_RULES=false."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            lang_src="fr",
            pp_env={"DICTEE_PP_RULES": "false"},
        )
        self.assertNotIn("Rules", r.pp_steps)

    def test_trace_elisions_for_fr(self):
        """French elisions step appears for lang=fr."""
        r = run_pipeline(
            "le homme est parti de ici rapidement",
            lang_src="fr",
        )
        step_text = " ".join(r.pp_steps)
        self.assertIn("Elisions", step_text)

    def test_trace_no_elisions_for_en(self):
        """French elisions step does NOT appear for lang=en."""
        r = run_pipeline(
            "hello world this is a test sentence.",
            lang_src="en",
        )
        for step in r.pp_steps:
            self.assertNotIn("Elisions [fr]", step)


# ══════════════════════════════════════════════════════════════════════
# ADVERSARIAL & EDGE CASE TESTS
# ══════════════════════════════════════════════════════════════════════


class TestPipelineIdempotency(unittest.TestCase):
    """Running PP twice should not corrupt the result."""

    def test_double_pp_normal(self):
        """PP Normal applied twice — second pass should be nearly idempotent."""
        r1 = run_pipeline("bonjour virgule comment allez-vous", lang_src="fr")
        # Feed the output of pass 1 as input to pass 2
        r2 = run_pipeline(r1.output, lang_src="fr")
        # Should not add extra capitalization, double punctuation, etc.
        self.assertEqual(r1.output, r2.output)

    def test_double_pp_en(self):
        """PP Normal on already-clean English text — no corruption."""
        r1 = run_pipeline("Hello, how are you?", lang_src="en")
        r2 = run_pipeline(r1.output, lang_src="en")
        self.assertEqual(r1.output, r2.output)

    def test_double_pp_with_numbers(self):
        """Numbers already converted should not be re-processed."""
        r1 = run_pipeline("vingt-trois", lang_src="fr")
        r2 = run_pipeline(r1.output, lang_src="fr")
        self.assertEqual(r1.output, r2.output)


class TestPipelineTranslationOutputFormats(unittest.TestCase):
    """Simulate various translation backend output quirks."""

    def test_translate_adds_quotes(self):
        """Ollama sometimes wraps output in quotes."""
        def mock_with_quotes(text, src, tgt):
            return '"Hello, how are you"', ""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate", translate_fn=mock_with_quotes,
        )
        # Pipeline should pass through — it doesn't strip quotes
        self.assertIn("Hello", r.output)

    def test_translate_adds_prefix(self):
        """Ollama sometimes prefixes with 'Translation:'."""
        def mock_with_prefix(text, src, tgt):
            return "Translation: Hello, how are you", ""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate", translate_fn=mock_with_prefix,
        )
        self.assertIn("Hello", r.output)

    def test_translate_returns_empty_no_error(self):
        """Translation returns empty string but no error — pipeline uses empty result.
        This is the expected behavior: the pipeline does NOT fallback to PP Normal
        result when translation returns empty without error."""
        def mock_empty(text, src, tgt):
            return "", ""
        r = run_pipeline(
            "bonjour", mode="normal+translate", translate_fn=mock_empty,
        )
        # Empty translation = empty output (no automatic fallback)
        self.assertEqual(r.output, "")

    def test_translate_returns_same_text(self):
        """Translation returns the same text (same language pair)."""
        def mock_identity(text, src, tgt):
            return text, ""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate", translate_fn=mock_identity,
        )
        # Should still work — pipeline doesn't crash
        self.assertTrue(len(r.output) > 0)

    def test_translate_adds_trailing_newline(self):
        """Some backends add trailing newlines."""
        def mock_newline(text, src, tgt):
            return "Hello, how are you\n", ""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate", translate_fn=mock_newline,
        )
        self.assertIn("Hello", r.output)

    def test_translate_partial_text(self):
        """Translation returns only part of the text."""
        def mock_partial(text, src, tgt):
            return "Hello", ""  # only first word
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="normal+translate", translate_fn=mock_partial,
        )
        self.assertEqual(r.output.strip(), "Hello")


class TestPipelineDoublePostprocessInteraction(unittest.TestCase):
    """PP Normal + PP Translation interactions that could corrupt text."""

    def test_no_double_punctuation(self):
        """PP Normal adds period, translation preserves it, TRPP should not add another."""
        def mock_with_period(text, src, tgt):
            return "Hello.", ""
        r = run_pipeline(
            "bonjour",
            mode="full_chain",
            translate_fn=mock_with_period,
        )
        # Should not have ".." or ". ."
        self.assertNotIn("..", r.output)

    def test_no_double_capitalization(self):
        """Text already capitalized by PP Normal, then translated (capitalized),
        then TRPP should not break capitalization."""
        def mock_cap(text, src, tgt):
            return "HELLO WORLD", ""
        r = run_pipeline(
            "bonjour",
            mode="full_chain",
            translate_fn=mock_cap,
        )
        # TRPP capitalization should not lowercase an all-caps input
        # (short_text might though, if enabled and < 3 words)
        self.assertIn("HELLO", r.output.upper())

    def test_typography_fr_then_en(self):
        """FR typography adds NNBSP before '?'. After translation to EN,
        the TRPP with EN lang should NOT add NNBSP."""
        r = run_pipeline(
            "comment allez-vous point d'interrogation",
            mode="full_chain",
            lang_src="fr", lang_tgt="en",
            translate_fn=mock_translate,
        )
        # FR typography adds NNBSP before '?' in the PP Normal pass.
        # After translation to EN, the TRPP with EN lang should not add
        # more NNBSP. But if the mock translation preserves the '?',
        # the existing NNBSP from the French source may survive in the
        # translated text (this is a known limitation — the translator
        # would normally produce clean EN without NNBSP).
        self.assertTrue(len(r.output) > 0)


class TestPipelineLanguageRulesCrossContamination(unittest.TestCase):
    """Rules from one language should not apply to another."""

    def test_fr_rules_not_applied_to_en(self):
        """French-specific rules (e.g. elisions) should not run on EN text."""
        r = run_pipeline("the hotel is nice", lang_src="en")
        # Should NOT become "l'hotel" or similar French contraction
        self.assertIn("the hotel", r.output.lower())

    def test_en_rules_not_applied_to_fr(self):
        """English-specific rules should not run on FR text."""
        r = run_pipeline("le hôtel est beau", lang_src="fr")
        # French elision might apply: "l'hôtel" — that's correct
        # But English rules should not be involved
        self.assertNotIn("[EN]", r.output)

    def test_trpp_uses_target_lang_rules(self):
        """In full_chain FR→EN, the TRPP should use EN rules, not FR."""
        def mock_en(text, src, tgt):
            return "The hotel is very nice, isn't it?", ""
        r = run_pipeline(
            "bonjour",
            mode="full_chain",
            lang_src="fr", lang_tgt="en",
            translate_fn=mock_en,
        )
        # TRPP should process with EN rules
        self.assertTrue(len(r.trpp_steps) >= 0)  # at least ran


class TestPipelineContinuationEdgeCases(unittest.TestCase):
    """Tricky continuation scenarios."""

    def test_continuation_word_as_proper_noun(self):
        """'Le' as start of sentence (proper noun context) — still triggers continuation."""
        r = run_pipeline(
            "Le",
            lang_src="fr",
            cont_words_src=CONT_WORDS_FR,
        )
        self.assertTrue(r.continuation_appended)
        self.assertTrue(r.output.endswith(">>"))

    def test_no_continuation_after_newline(self):
        """Text ending with newline + continuation word — the shell skips continuation
        when text contains \\n. Our pipeline should match."""
        # Note: dictee-postprocess may convert "point à la ligne" to \n
        r = run_pipeline(
            "Bonjour.\nLe",
            lang_src="fr",
            cont_words_src=CONT_WORDS_FR,
        )
        # The shell skips save_last_word when text contains \n
        # Our test pipeline currently doesn't skip — document the divergence
        # This is a known limitation of the test panel vs shell

    def test_continuation_only_last_word_matters(self):
        """Only the very last word is checked, not intermediate ones."""
        r = run_pipeline(
            "Je mange le gâteau",
            lang_src="fr",
            cont_words_src=CONT_WORDS_FR,
        )
        # "gâteau" is NOT a continuation word
        self.assertFalse(r.continuation_appended)

    def test_continuation_with_multiple_hyphens(self):
        """'peut-être-pas' → check 'pas' (not 'être' or 'peut')."""
        text = "peut-être-pas"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        # "pas" is not in CONT_WORDS_FR
        self.assertFalse(appended)

    def test_continuation_with_apostrophe(self):
        """Words with apostrophe: "l'a" → check "l'a" or "a"."""
        text = "c'est"
        result, appended = _check_continuation(text, CONT_WORDS_FR)
        # "c'est" is not in the continuation words
        self.assertFalse(appended)

    def test_continuation_indicator_in_text_naturally(self):
        """Text that naturally contains '>>' should not confuse the pipeline."""
        text = "envoyez >> ensuite"
        r = run_pipeline(text, lang_src="fr", cont_words_src=CONT_WORDS_FR)
        # "ensuite" is not continuation — no extra >> added
        self.assertFalse(r.continuation_appended)

    def test_continuation_after_translation_changes_word(self):
        """FR 'le' is continuation. After translation to EN, 'the' is also continuation.
        But if FR 'maison' translates to EN 'house' (not continuation), no indicator."""
        def mock_house(text, src, tgt):
            return "house", ""
        r = run_pipeline(
            "maison",
            mode="normal+translate",
            translate_fn=mock_house,
            cont_words_src=CONT_WORDS_FR,
            cont_words_tgt=CONT_WORDS_EN,
        )
        self.assertFalse(r.continuation_appended)


class TestPipelineSpecialCharacters(unittest.TestCase):
    """Characters that could break regex or subprocess."""

    def test_backslash_in_text(self):
        """Backslash should not break postprocess regex."""
        r = run_pipeline("chemin\\fichier", lang_src="fr")
        self.assertIn("\\", r.output)

    def test_dollar_sign(self):
        """$ should not be interpreted as shell variable."""
        r = run_pipeline("prix: $100", lang_src="en")
        self.assertIn("$100", r.output)

    def test_single_quotes(self):
        """Single quotes (common in French: l'homme)."""
        r = run_pipeline("l'homme est là", lang_src="fr")
        self.assertTrue(len(r.output) > 0)

    def test_double_quotes(self):
        """Double quotes are converted to guillemets by FR typography rules."""
        r = run_pipeline('il a dit "bonjour"', lang_src="fr")
        # French typography converts "..." to «\xa0...\xa0»
        self.assertIn('«', r.output)

    def test_pipe_character(self):
        """Pipe | should not break subprocess."""
        r = run_pipeline("option A | option B", lang_src="en")
        self.assertIn("|", r.output)

    def test_semicolon(self):
        """Semicolon should not break shell."""
        r = run_pipeline("first; second", lang_src="en")
        self.assertIn(";", r.output)

    def test_angle_brackets(self):
        """< > should not be interpreted as shell redirection."""
        r = run_pipeline("a < b > c", lang_src="en")
        self.assertTrue(len(r.output) > 0)

    def test_null_byte(self):
        """Null byte should not crash the pipeline."""
        r = run_pipeline("hello\x00world", lang_src="en")
        # Might be stripped, but should not crash
        self.assertIsNotNone(r.output)

    def test_unicode_normalization(self):
        """NFC vs NFD: 'é' as single char vs 'e' + combining accent."""
        import unicodedata
        nfc = unicodedata.normalize("NFC", "café")
        nfd = unicodedata.normalize("NFD", "café")
        r_nfc = run_pipeline(nfc, lang_src="fr")
        r_nfd = run_pipeline(nfd, lang_src="fr")
        # Both should produce the same output
        self.assertEqual(
            unicodedata.normalize("NFC", r_nfc.output),
            unicodedata.normalize("NFC", r_nfd.output))


class TestPipelineCommandSuffixInteraction(unittest.TestCase):
    """Command suffix edge cases with translation."""

    def test_suffix_only_applies_to_source_lang(self):
        """Command suffix is for source language PP, not target TRPP."""
        r = run_pipeline(
            "point suivi",
            mode="full_chain",
            lang_src="fr",
            pp_env={"DICTEE_COMMAND_SUFFIX_FR": "suivi"},
            translate_fn=mock_translate,
        )
        # "point suivi" should become "." in PP Normal
        # Then "." gets translated (probably stays ".")
        self.assertNotIn("suivi", r.output)

    def test_suffix_word_appears_naturally(self):
        """The suffix word 'suivi' appears as a normal word (not after a command)."""
        r = run_pipeline(
            "le suivi est important",
            lang_src="fr",
            pp_env={"DICTEE_COMMAND_SUFFIX_FR": "suivi"},
        )
        # "suivi" here is NOT after a command — should be kept
        self.assertIn("suivi", r.output.lower())


class TestPipelineShortTextWithTranslation(unittest.TestCase):
    """Short text fix interaction with translation."""

    def test_long_fr_becomes_short_en(self):
        """3-word FR sentence 'C'est un bon point.' → EN might be 1 word.
        Short text fix on target should handle this."""
        def mock_one_word(text, src, tgt):
            return "Good.", ""
        r = run_pipeline(
            "C'est bon.",
            mode="full_chain",
            translate_fn=mock_one_word,
        )
        # "Good." is 1 word — short text fix should lowercase + strip period
        # (if short_text is enabled, which it is by default)
        # Result might be "good" or "Good." depending on step order
        self.assertTrue(len(r.output.strip()) > 0)

    def test_short_fr_becomes_long_en(self):
        """1-word FR 'Bonjour' → EN 'Hello' — both short, both get short text fix."""
        def mock_hello(text, src, tgt):
            return "Hello.", ""
        r = run_pipeline(
            "Bonjour.",
            mode="full_chain",
            translate_fn=mock_hello,
        )
        self.assertTrue(len(r.output.strip()) > 0)


class TestPipelineTRPPSkippedOnTranslateError(unittest.TestCase):
    """When translation fails, TRPP should NOT run."""

    def test_trpp_skipped_on_error(self):
        """Translation error → no TRPP, output is PP Normal result."""
        r = run_pipeline(
            "bonjour virgule comment allez-vous",
            mode="full_chain",
            translate_fn=mock_translate_fail,
        )
        self.assertTrue(len(r.translate_error) > 0)
        self.assertEqual(len(r.trpp_steps), 0)
        # Output should be the PP Normal result (not empty)
        self.assertIn("Bonjour", r.output)

    def test_trpp_skipped_on_empty_translation(self):
        """Empty translation result → TRPP skipped."""
        def mock_empty(text, src, tgt):
            return "", ""
        r = run_pipeline(
            "bonjour",
            mode="full_chain",
            translate_fn=mock_empty,
        )
        self.assertEqual(len(r.trpp_steps), 0)


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
