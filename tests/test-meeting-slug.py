#!/usr/bin/env python3
"""Pure helpers of dictee-meeting-live: folder slug, F9 model spec, whisper tokens.

Ported from master's tests/test-meeting-slug.py, rewritten for unittest so it
runs with python3 alone like the rest of this directory. Nothing here builds
a window, so the shared state file is never touched.

Run: python3 tests/test-meeting-slug.py
"""
import importlib.machinery
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
loader = importlib.machinery.SourceFileLoader(
    "meeting_live_pure", os.path.join(ROOT, "dictee-meeting-live"))
spec = importlib.util.spec_from_loader("meeting_live_pure", loader)
ml = importlib.util.module_from_spec(spec)
sys.modules["meeting_live_pure"] = ml
spec.loader.exec_module(ml)


class TestPureHelpers(unittest.TestCase):

    def test_slug(self):
        self.assertEqual(ml.slug_title("Réunion équipe !"), "r-union-quipe")
        self.assertEqual(ml.slug_title("  A  B  "), "a-b")
        self.assertEqual(ml.slug_title(""), "")

    def test_current_f9_spec(self):
        # Whisper specs are per engine: the size follows dictee-setup and is
        # not part of the spec (master's own test still expects the sized
        # form and fails on master; this pins what the code does today).
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "whisper",
                                             "DICTEE_WHISPER_MODEL": "medium"}), "whisper")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "whisper"}), "whisper")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "whisper-rust"}), "whisper-rust")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "nemotron"}), "nemotron")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "kyutai"}), "kyutai")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "parakeet",
                                             "DICTEE_PARAKEET_QUANT": "int8"}), "parakeet-int8")
        self.assertEqual(ml.current_f9_spec({}), "parakeet-fp32")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "canary"}), "parakeet-fp32")

    def test_normalize_asr_spec_folds_old_sized_specs(self):
        self.assertEqual(ml.normalize_asr_spec("whisper-medium"), "whisper")
        self.assertEqual(ml.normalize_asr_spec("whisper-rust-large-v3"), "whisper-rust")
        self.assertEqual(ml.normalize_asr_spec("parakeet-int8"), "parakeet-int8")
        self.assertEqual(ml.normalize_asr_spec(""), "")
        self.assertEqual(ml.normalize_asr_spec(None), "")

    def test_parse_whisper_tokens(self):
        text = "[0.00s - 0.50s] Bonjour\n[0.50s - 1.20s] le\n[1.20s - 2.00s] monde\n"
        self.assertEqual(ml._parse_whisper_tokens(text), [
            {"text": "Bonjour", "start_s": 0.0, "end_s": 0.5},
            {"text": "le", "start_s": 0.5, "end_s": 1.2},
            {"text": "monde", "start_s": 1.2, "end_s": 2.0},
        ])
        # sentence-level lines (no 's' suffix) and blanks/garbage are robust
        self.assertEqual(ml._parse_whisper_tokens("[1 - 2] hi"),
                         [{"text": "hi", "start_s": 1.0, "end_s": 2.0}])
        self.assertEqual(ml._parse_whisper_tokens(""), [])
        self.assertEqual(ml._parse_whisper_tokens("garbage no brackets"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
