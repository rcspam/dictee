#!/usr/bin/env python3
"""Tests for the dictee-transcribe ASR + translation backend routing.

Two regressions motivated this file:

1. The Canary PTT swap (DICTEE_ASR_BACKEND=canary) silently broke
   dictee-transcribe diarize phase-2 routing. The two-phase pipeline
   (diarize-only → transcribe-daemon socket) was designed for a
   Parakeet daemon (commit 566202e). When the daemon is Canary, it
   is locked at DICTEE_LANG_SOURCE — feeding it audio in another
   language mistranscribes silently. Fix: route diarize through the
   standalone transcribe-diarize binary when the daemon is Canary
   (commit acfefc0).

2. Translation backend availability checks drift quickly because
   each backend has its own dependency (trans CLI, ollama CLI,
   docker for libretranslate). Lock the contract here.

These tests load the relevant pure functions out of dictee-transcribe.py
without importing the script as a module — the script depends on PyQt6
which is not installed in CI.

Run: python3 tests/test-transcribe-routing.py [-v]
"""

import os
import sys
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------
# Load pure functions from dictee-transcribe.py without triggering Qt.
# ---------------------------------------------------------------------

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "dictee-transcribe.py",
)


def _load_func(name, source_path=SCRIPT):
    """Extract a top-level def by name and exec it into a fresh ns.

    Skips PyQt6 imports because we never touch the rest of the file.
    """
    with open(source_path, encoding="utf-8") as f:
        lines = f.readlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"def {name}("):
            start = i
            break
    if start is None:
        raise RuntimeError(f"Function {name}() not found in {source_path}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        # Stop at the next top-level def or class (no leading whitespace).
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end = j
            break
    src = "".join(lines[start:end])
    ns = {}
    exec(src, ns)
    return ns[name]


_select_transcribe_cmd = _load_func("_select_transcribe_cmd")
_translate_available = _load_func("_translate_available")


# ---------------------------------------------------------------------
# ASR command routing
# ---------------------------------------------------------------------


class SelectTranscribeCmdTests(unittest.TestCase):
    """Routing matrix for _on_transcribe.

    Inputs: (diarize, asr_backend, has_transcribe, has_diarize_only,
             has_transcribe_diarize)
    Output: (cmd, two_phase, missing_binary)
    """

    # Default fixture: every binary present, no backend env set.
    BASE = dict(
        has_transcribe=True,
        has_diarize_only=True,
        has_transcribe_diarize=True,
    )

    # ── diarize=False (plain transcribe) ──────────────────────────────

    def test_plain_uses_transcribe_binary(self):
        # Plain mode never touches the daemon — always Parakeet binary.
        cmd, two_phase, err = _select_transcribe_cmd(
            diarize=False, asr_backend="canary", **self.BASE)
        self.assertEqual(cmd, "transcribe")
        self.assertFalse(two_phase)
        self.assertIsNone(err)

    def test_plain_unaffected_by_backend(self):
        # The `transcribe` binary is hardcoded Parakeet-TDT — backend
        # env var has no influence on plain transcription.
        for backend in ("", "parakeet", "canary", "whisper", "vosk"):
            with self.subTest(backend=backend):
                cmd, _, _ = _select_transcribe_cmd(
                    diarize=False, asr_backend=backend, **self.BASE)
                self.assertEqual(cmd, "transcribe")

    def test_plain_missing_transcribe_returns_error(self):
        cmd, two_phase, err = _select_transcribe_cmd(
            diarize=False, asr_backend="",
            has_transcribe=False, has_diarize_only=True,
            has_transcribe_diarize=True)
        self.assertIsNone(cmd)
        self.assertFalse(two_phase)
        self.assertEqual(err, "transcribe")

    # ── diarize=True with Canary daemon (the regressed path) ──────────

    def test_canary_daemon_diarize_uses_standalone(self):
        # The bug fixed in acfefc0: Canary daemon is locked at
        # DICTEE_LANG_SOURCE. Phase-2 transcription via the daemon
        # socket would mistranscribe audio in any other language.
        # transcribe-diarize loads Parakeet-TDT itself (multilingual).
        cmd, two_phase, err = _select_transcribe_cmd(
            diarize=True, asr_backend="canary", **self.BASE)
        self.assertEqual(cmd, "transcribe-diarize")
        self.assertFalse(two_phase, "Canary path must NOT be two-phase")
        self.assertIsNone(err)

    def test_canary_case_insensitive(self):
        # DICTEE_ASR_BACKEND is matched .lower() — defensive against
        # users editing dictee.conf by hand.
        for variant in ("canary", "Canary", "CANARY", " canary "):
            with self.subTest(variant=repr(variant)):
                # Strip whitespace handling is the caller's job; we
                # only test case-insensitive match for the unstripped
                # canonical forms.
                cmd, _, _ = _select_transcribe_cmd(
                    diarize=True, asr_backend=variant.strip(), **self.BASE)
                self.assertEqual(cmd, "transcribe-diarize")

    def test_canary_falls_through_when_standalone_missing(self):
        # If transcribe-diarize binary isn't installed, fall back to
        # the daemon path — at least the user gets *something*. The
        # existing fallback chain is preserved.
        cmd, two_phase, err = _select_transcribe_cmd(
            diarize=True, asr_backend="canary",
            has_transcribe=True, has_diarize_only=True,
            has_transcribe_diarize=False)
        self.assertEqual(cmd, "diarize-only")
        self.assertTrue(two_phase)
        self.assertIsNone(err)

    # ── diarize=True with Parakeet daemon (default) ──────────────────

    def test_parakeet_daemon_diarize_uses_two_phase(self):
        # Original 566202e design: leverage the loaded Parakeet daemon
        # for phase-2 transcription. Saves model load time (~5-10 s).
        cmd, two_phase, err = _select_transcribe_cmd(
            diarize=True, asr_backend="parakeet", **self.BASE)
        self.assertEqual(cmd, "diarize-only")
        self.assertTrue(two_phase)
        self.assertIsNone(err)

    def test_empty_backend_treated_as_parakeet(self):
        # No DICTEE_ASR_BACKEND in conf → transcribe-daemon defaults
        # to Parakeet. Routing must not flag this as Canary.
        cmd, two_phase, _ = _select_transcribe_cmd(
            diarize=True, asr_backend="", **self.BASE)
        self.assertEqual(cmd, "diarize-only")
        self.assertTrue(two_phase)

    def test_parakeet_falls_back_when_diarize_only_missing(self):
        # Pre-566202e single-binary path. Still supported (e.g. older
        # /usr/bin/dictee-* that didn't ship diarize-only).
        cmd, two_phase, err = _select_transcribe_cmd(
            diarize=True, asr_backend="parakeet",
            has_transcribe=True, has_diarize_only=False,
            has_transcribe_diarize=True)
        self.assertEqual(cmd, "transcribe-diarize")
        self.assertFalse(two_phase)
        self.assertIsNone(err)

    def test_diarize_no_binaries_returns_error(self):
        # User installed transcribe but neither diarize binary —
        # surface "diarize-only not found" so they know what to install.
        cmd, two_phase, err = _select_transcribe_cmd(
            diarize=True, asr_backend="parakeet",
            has_transcribe=True, has_diarize_only=False,
            has_transcribe_diarize=False)
        self.assertIsNone(cmd)
        self.assertFalse(two_phase)
        self.assertEqual(err, "diarize-only")

    # ── Future-proofing for new daemon backends ───────────────────────

    def test_unknown_backend_uses_two_phase(self):
        # An unknown backend (e.g. future "whisper" daemon) currently
        # routes to the daemon path. This test DOCUMENTS that
        # behaviour — if a new daemon also needs to bypass the socket
        # like Canary does, _select_transcribe_cmd must be updated and
        # this test rewritten accordingly.
        cmd, two_phase, _ = _select_transcribe_cmd(
            diarize=True, asr_backend="whisper-future", **self.BASE)
        self.assertEqual(cmd, "diarize-only",
            "If you added a new daemon that should bypass phase-2 "
            "(like Canary), update _select_transcribe_cmd and rewrite "
            "this test — silent regressions for non-Parakeet daemons "
            "have happened before (see commit acfefc0).")
        self.assertTrue(two_phase)


# ---------------------------------------------------------------------
# Translation backend availability
# ---------------------------------------------------------------------


class TranslateAvailableTests(unittest.TestCase):
    """Each translation backend has its own dependency check.

    Patches the `shutil` module already imported inside
    _translate_available's source (re-imported via exec namespace).
    """

    def _which(self, present):
        """Return a fake shutil.which that succeeds only for `present`."""
        return lambda binary: f"/usr/bin/{binary}" if binary in present else None

    def test_google_requires_trans(self):
        with patch("shutil.which", new=self._which({"trans"})):
            self.assertTrue(_translate_available("google"))

    def test_google_unavailable_without_trans(self):
        with patch("shutil.which", new=self._which(set())):
            self.assertFalse(_translate_available("google"))

    def test_bing_uses_same_trans_binary(self):
        # Bing and Google share the `trans` CLI, just different -e flag.
        with patch("shutil.which", new=self._which({"trans"})):
            self.assertTrue(_translate_available("bing"))

    def test_ollama_requires_ollama_cli(self):
        with patch("shutil.which", new=self._which({"ollama"})):
            self.assertTrue(_translate_available("ollama"))

    def test_ollama_does_not_accept_trans(self):
        # Sanity: presence of `trans` does not make ollama available.
        with patch("shutil.which", new=self._which({"trans"})):
            self.assertFalse(_translate_available("ollama"))

    def test_libretranslate_requires_docker(self):
        # The local LibreTranslate instance runs in a Docker container
        # — `docker` CLI absence means the backend can't start.
        with patch("shutil.which", new=self._which({"docker"})):
            self.assertTrue(_translate_available("libretranslate"))

    def test_libretranslate_does_not_accept_trans(self):
        with patch("shutil.which", new=self._which({"trans"})):
            self.assertFalse(_translate_available("libretranslate"))

    def test_unknown_backend_returns_false(self):
        # An unknown backend string should never be reported available.
        with patch("shutil.which", new=self._which({"trans", "ollama", "docker"})):
            self.assertFalse(_translate_available("xyz"))


if __name__ == "__main__":
    unittest.main()
