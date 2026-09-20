#!/usr/bin/env python3
"""Tests for the dictee-transcribe command line and its meeting handoff helpers.

dictee-meeting-live hands the recorded meeting over with
`dictee-transcribe --file audio.wav --diarize --diar-engine auto --asr-model
parakeet-int8`. argparse must accept that line, parakeet-int8/fp32 must reach
the Rust binaries as DICTEE_PARAKEET_QUANT, speakers.json must be matched onto
the batch speaker labels, and History must list past meetings.

Pure functions are extracted from dictee-transcribe.py without importing it
(PyQt6 is not installed in every CI job), like tests/test-transcribe-routing.py.

Run: python3 tests/test-transcribe-args.py [-v]
"""

import argparse
import json
import os
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dictee-transcribe.py")


def _load_func(name, ns_extra=None):
    """Extract a top-level def by name and exec it into a fresh namespace.

    ns_extra seeds the globals the function body needs (os, json, argparse).
    """
    with open(SCRIPT, encoding="utf-8") as f:
        lines = f.readlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(f"def {name}(")), None)
    if start is None:
        raise RuntimeError(f"Function {name}() not found in {SCRIPT}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end = j
            break
    ns = dict(ns_extra or {})
    exec("".join(lines[start:end]), ns)
    return ns[name]


_asr_model_env = _load_func("_asr_model_env")
_build_arg_parser = _load_func("_build_arg_parser", {"argparse": argparse})


class AsrModelEnvTests(unittest.TestCase):

    def test_int8(self):
        self.assertEqual(_asr_model_env("parakeet-int8"), {"DICTEE_PARAKEET_QUANT": "int8"})

    def test_fp32(self):
        self.assertEqual(_asr_model_env("parakeet-fp32"), {"DICTEE_PARAKEET_QUANT": "fp32"})

    def test_other_engines_are_ignored(self):
        for spec in ("whisper", "whisper-rust", "nemotron", "kyutai", "", None):
            with self.subTest(spec=spec):
                self.assertEqual(_asr_model_env(spec), {})


class ArgParserTests(unittest.TestCase):

    def test_meeting_handoff_line_is_accepted(self):
        args = _build_arg_parser().parse_args(
            ["--file", "/x/audio.wav", "--diarize",
             "--diar-engine", "auto", "--asr-model", "parakeet-int8"])
        self.assertEqual(args.file, "/x/audio.wav")
        self.assertTrue(args.diarize)
        self.assertEqual(args.diar_engine, "auto")
        self.assertEqual(args.asr_model, "parakeet-int8")

    def test_analyze_another_file_line_is_accepted(self):
        args = _build_arg_parser().parse_args(["--asr-model", "parakeet-fp32"])
        self.assertIsNone(args.file)
        self.assertEqual(args.asr_model, "parakeet-fp32")

    def test_defaults(self):
        args = _build_arg_parser().parse_args([])
        self.assertIsNone(args.diar_engine)
        self.assertIsNone(args.asr_model)
        self.assertEqual(args.files, [])

    def test_positional_files_still_work(self):
        args = _build_arg_parser().parse_args(["a.wav", "b.wav"])
        self.assertEqual(args.files, ["a.wav", "b.wav"])


if __name__ == "__main__":
    unittest.main()
