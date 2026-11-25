"""The gettext catalog follows the code, and every language is complete.

  - every _("literal") / N_("literal") of the Python UIs is in po/dictee.pot,
    including the ones written inside f-strings (xgettext 0.21 skips those);
  - the pot holds no msgid the code no longer uses;
  - each po/<lang>.po translates every msgid, nothing untranslated or fuzzy;
  - the diarized transcript's format tokens (Speaker N, UNKNOWN), read back
    by DIARIZE_RE, are never routed through gettext.

Regenerate with: python3 po/update-catalog.py
Run: python3 tests/test-i18n-catalog.py
"""
import importlib.util
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
spec = importlib.util.spec_from_file_location(
    "update_catalog", os.path.join(ROOT, "po", "update-catalog.py"))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class CatalogFollowsTheCode(unittest.TestCase):
    def setUp(self):
        self.code = set(catalog.code_msgids())
        self.pot = catalog.pot_msgids(os.path.join(ROOT, "po", "dictee.pot"))

    def test_every_marked_string_is_in_the_pot(self):
        missing = sorted(self.code - self.pot)
        self.assertEqual(missing, [], "run po/update-catalog.py")

    def test_the_pot_holds_no_dead_string(self):
        dead = sorted(self.pot - self.code)
        self.assertEqual(dead, [], "run po/update-catalog.py")

    def test_strings_inside_f_strings_are_found(self):
        self.assertIn("click to start daemon", self.code)   # dictee-tray.py
        self.assertIn("Asset for your install", self.code)  # dictee-setup.py

    def test_transcribe_window_is_in_the_catalog(self):
        self.assertIn("Rename speakers", self.pot)
        self.assertIn("Name (e.g. Alice)", self.pot)

    def test_transcript_format_tokens_stay_untranslated(self):
        for token in ("Speaker", "UNKNOWN"):
            self.assertNotIn(token, self.code)


class EveryLanguageIsComplete(unittest.TestCase):
    def test_no_untranslated_or_fuzzy_entry(self):
        env = dict(os.environ, LC_ALL="C", LANG="C", LANGUAGE="")
        for lang in catalog.LANGS:
            po = os.path.join(ROOT, "po", f"{lang}.po")
            out = subprocess.run(
                ["msgfmt", "--check", "--statistics", "-o", os.devnull, po],
                capture_output=True, text=True, env=env)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertNotIn("untranslated", out.stderr, f"{lang}: {out.stderr}")
            self.assertNotIn("fuzzy", out.stderr, f"{lang}: {out.stderr}")


if __name__ == "__main__":
    unittest.main(argv=sys.argv, verbosity=2)
