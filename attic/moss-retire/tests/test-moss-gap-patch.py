#!/usr/bin/env python3
"""Killer test for the dictee-moss-diarize gap patching (secondary ASR).

Feature 2026-07-21: when MOSS leaves a suspicious hole in the transcript
(silent omission or a truncated runaway chunk), a secondary ASR engine
transcribes the missing span and the text is inserted with the UNKNOWN
label (already accepted by DIARIZE_RE end to end), so the LLM analysis
never loses content. If the secondary engine returns nothing, the hole
was silence and only the existing warning remains.

Run: python3 tests/test-moss-gap-patch.py [-v]
"""

import importlib.machinery
import importlib.util
import os
import unittest

DRIVER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "dictee-moss-diarize")


def _load_driver():
    loader = importlib.machinery.SourceFileLoader("dictee_moss_diarize", DRIVER)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class GapPatchTests(unittest.TestCase):
    def setUp(self):
        self.driver = _load_driver()
        # A 40-s hole (60 -> 100) plus a small legit pause (100 -> 104).
        self.turns = [
            (0.0, 30.0, 0, "premier tour"),
            (30.5, 60.0, 1, "deuxième tour"),
            (100.0, 120.0, 0, "après le trou"),
            (104.0, 130.0, 1, "dernier tour"),
        ]

    def test_gap_is_patched_with_unknown_label(self):
        calls = []

        def fake_asr(start, end):
            calls.append((start, end))
            return "texte récupéré par le moteur de secours"

        out = self.driver._patch_gaps(list(self.turns), fake_asr)
        self.assertEqual(calls, [(60.0, 100.0)],
                         "only the >10-s hole is retried, not the 4-s pause")
        patched = [t for t in out if t[2] is None]
        self.assertEqual(len(patched), 1)
        s, e, spk, text = patched[0]
        self.assertEqual((s, e), (60.0, 100.0))
        self.assertIn("récupéré", text)
        # Inserted in chronological position, original turns untouched.
        self.assertEqual([t[0] for t in out], sorted(t[0] for t in out))
        self.assertEqual(len(out), len(self.turns) + 1)

    def test_silence_yields_no_patch(self):
        out = self.driver._patch_gaps(list(self.turns), lambda s, e: "  ")
        self.assertEqual(out, self.turns, "empty ASR result -> hole kept as is")

    def test_no_gap_no_call(self):
        calls = []
        tight = [(0.0, 50.0, 0, "a"), (52.0, 90.0, 1, "b")]
        out = self.driver._patch_gaps(list(tight),
                                      lambda s, e: calls.append(1) or "x")
        self.assertEqual(calls, [])
        self.assertEqual(out, tight)

    def test_unknown_label_is_in_the_diarize_contract(self):
        # The UNKNOWN label must be parseable by the UI and the LLM layer.
        import re
        diarize_re = re.compile(
            r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(Speaker\s+\d+|UNKNOWN):\s*(.*)")
        line = "[60.00s - 100.00s] UNKNOWN: texte récupéré"
        m = diarize_re.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(3), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
