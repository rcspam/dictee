#!/usr/bin/env python3
"""Killer test for the dictee-moss-diarize chunked pipeline robustness.

Regression 2026-07-21: on a 17-min voice memo, chunk 9 hit the decode
generation cap (transcribe_cpp OutputTruncated, status 18) and the WHOLE
run crashed with a traceback in the UI — although the bindings explicitly
preserve the partial transcript on the exception (`partial_result`, always
set by the C API for this status). One runaway chunk must degrade to a
partial chunk, never kill the run.

Run: python3 tests/test-moss-driver-truncation.py [-v]
"""

import importlib.machinery
import importlib.util
import os
import sys
import types
import unittest

DRIVER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "dictee-moss-diarize")


def _load_driver():
    loader = importlib.machinery.SourceFileLoader("dictee_moss_diarize", DRIVER)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class _Result:
    def __init__(self, text):
        self.text = text


def _fake_transcribe_cpp(truncate_on_call, partial_text):
    """Build a fake transcribe_cpp package: session.run() returns one good
    turn per chunk, except the truncate_on_call-th call (0-based), which
    raises OutputTruncated carrying the partial transcript — exactly the
    contract documented in transcribe_cpp/errors.py."""
    errors = types.ModuleType("transcribe_cpp.errors")

    class TranscribeError(Exception):
        pass

    class OutOfMemory(TranscribeError):
        pass

    class OutputTruncated(TranscribeError):
        partial_result = None

    errors.TranscribeError = TranscribeError
    errors.OutOfMemory = OutOfMemory
    errors.OutputTruncated = OutputTruncated

    class _Session:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def run(self, seg):
            call = self.calls
            self.calls += 1
            if call == truncate_on_call:
                exc = OutputTruncated(
                    "transcribe_run: output truncated: decode hit the "
                    "context/generation cap before end-of-stream (status 18)")
                exc.partial_result = _Result(partial_text)
                raise exc
            return _Result("[1.0][S01] bonjour tout le monde [3.0]")

    class _Model:
        def __init__(self, path):
            self._session = _Session()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def session(self):
            return self._session

    pkg = types.ModuleType("transcribe_cpp")
    pkg.Model = _Model
    pkg.errors = errors
    return pkg


class MossChunkedTruncationTests(unittest.TestCase):
    def setUp(self):
        self.driver = _load_driver()
        # 100 s of silence, chunk 40 s / overlap 10 s -> starts 0/30/60/90
        self.pcm = [0.0] * (100 * self.driver.SAMPLE_RATE)

    def _run(self, fake):
        old = {k: sys.modules.get(k)
               for k in ("transcribe_cpp", "transcribe_cpp.errors")}
        sys.modules["transcribe_cpp"] = fake
        sys.modules["transcribe_cpp.errors"] = fake.errors
        try:
            return self.driver._transcribe_chunked(
                self.pcm, "/nonexistent/model.gguf", 40, 10)
        finally:
            for k, v in old.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_truncated_chunk_keeps_partial_and_run_continues(self):
        # Chunk 2 (offset 60 s) truncates after one complete turn plus an
        # unterminated tail; the run must keep going and keep that turn.
        fake = _fake_transcribe_cpp(
            truncate_on_call=2,
            partial_text="[2.0][S01] début récupéré [5.0]"
                         "[6.0][S02] queue coupée sans balise de fin")
        chunks = self._run(fake)
        self.assertEqual(len(chunks), 4, "one bad chunk must not end the run")
        st, turns = chunks[2]
        self.assertEqual(st, 60)
        self.assertEqual(len(turns), 1, "the complete partial turn is kept, "
                                        "the unterminated tail is dropped")
        self.assertAlmostEqual(turns[0][0], 62.0)  # offset applied
        self.assertIn("début récupéré", turns[0][3])

    def test_truncated_chunk_with_no_partial_yields_empty_chunk(self):
        # Defensive: partial_result may be None when the status surfaced
        # outside a result-bearing call (errors.py contract).
        fake = _fake_transcribe_cpp(truncate_on_call=1, partial_text="")

        class _NoPartialSession:
            calls = 0

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def run(self, seg):
                call = _NoPartialSession.calls
                _NoPartialSession.calls += 1
                if call == 1:
                    exc = fake.errors.OutputTruncated("truncated (status 18)")
                    exc.partial_result = None
                    raise exc
                return _Result("[1.0][S01] ok [2.0]")

        class _NoPartialModel:
            def __init__(self, path):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def session(self):
                return _NoPartialSession()

        fake.Model = _NoPartialModel
        chunks = self._run(fake)
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[1][1], [], "no partial -> empty chunk, no crash")


if __name__ == "__main__":
    unittest.main()
