#!/usr/bin/env python3
"""Tests for the dictee-transcribe ASR + translation backend routing.

1. Diarization (refonte of 2026-10-04): Nemotron 3 cuts the recording into
   pieces (diarize-only --pieces), then phase 2 sends one request per piece
   to whatever daemon transcribes, Canary included; MOSS runs alone when
   chosen. Before, a Canary daemon was bypassed by the standalone
   transcribe-diarize (Parakeet + Sortformer), because the two-phase path
   sent it the whole file in its fixed language (commit acfefc0).

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
_diarize_only_engine_args = _load_func("_diarize_only_engine_args")
_phase2_mode = _load_func("_phase2_mode")
_turns_in_pieces = _load_func("_turns_in_pieces")
_diarized_asr_spec = _load_func("_diarized_asr_spec")
_vram_needed_mb = _load_func("_vram_needed_mb")
_translate_available = _load_func("_translate_available")


# ---------------------------------------------------------------------
# ASR command routing
# ---------------------------------------------------------------------


class SelectTranscribeCmdTests(unittest.TestCase):
    """Routing matrix for _on_transcribe.

    Diarization runs Nemotron 3 in two phases (diarize-only, then the
    daemon piece by piece), or MOSS in one pass when it is chosen and
    installed. The F9 ASR backend no longer changes the command.
    """

    def route(self, diarize=True, has_transcribe=True, has_diarize_only=True,
              has_moss=False, diar_engine="nemotron3", has_nemotron3=True):
        return _select_transcribe_cmd(
            diarize=diarize, has_transcribe=has_transcribe,
            has_diarize_only=has_diarize_only, has_moss=has_moss,
            diar_engine=diar_engine, has_nemotron3=has_nemotron3)

    def test_plain_uses_transcribe_binary(self):
        self.assertEqual(self.route(diarize=False), ("transcribe", False, None))

    def test_plain_missing_transcribe_returns_error(self):
        self.assertEqual(self.route(diarize=False, has_transcribe=False),
                         (None, False, "transcribe"))

    def test_plain_ignores_the_diarization_engine(self):
        self.assertEqual(self.route(diarize=False, has_moss=True, diar_engine="moss"),
                         ("transcribe", False, None))

    def test_diarize_runs_nemotron3_in_two_phases(self):
        self.assertEqual(self.route(), ("diarize-only", True, None))

    def test_moss_when_chosen_and_installed(self):
        self.assertEqual(self.route(has_moss=True, diar_engine="moss"),
                         ("dictee-moss-diarize", False, None))

    def test_moss_chosen_but_missing_runs_nemotron3(self):
        self.assertEqual(self.route(diar_engine="moss"), ("diarize-only", True, None))

    def test_moss_installed_but_not_chosen_never_wins(self):
        self.assertEqual(self.route(has_moss=True), ("diarize-only", True, None))

    def test_retired_engine_names_run_nemotron3(self):
        # QSettings or meeting-live can still hand over these names
        for engine in ("auto", "multi", "sortformer"):
            self.assertEqual(self.route(diar_engine=engine),
                             ("diarize-only", True, None), engine)

    def test_no_usable_engine_names_diarize_only(self):
        self.assertEqual(self.route(has_nemotron3=False), (None, False, "diarize-only"))
        self.assertEqual(self.route(has_diarize_only=False), (None, False, "diarize-only"))


class DiarizeOnlyArgsTests(unittest.TestCase):
    def test_pieces_of_nemotron3_from_its_model_dir(self):
        # pieces up to diarize-only's 30 s whatever the engine (Parakeet's 5 s
        # cap went with Parakeet, out of diarized runs since 2026-10-04)
        self.assertEqual(_diarize_only_engine_args("/models/n3"),
                         ["/models/n3", "--engine", "nemotron3", "--pieces"])


class DiarizedAsrSpecTests(unittest.TestCase):
    """Parakeet translates some recordings into English (2026-10-04): a
    diarized run never transcribes with it, Whisper-Rust does instead."""

    def test_parakeet_choices_become_whisper_rust(self):
        for spec in ("parakeet-int8", "parakeet-fp32"):
            for f9 in ("parakeet", "canary", ""):
                self.assertEqual(_diarized_asr_spec(spec, f9), "whisper-rust", (spec, f9))

    def test_the_f9_daemon_when_it_is_parakeet_becomes_whisper_rust(self):
        for f9 in ("parakeet", "", None):
            self.assertEqual(_diarized_asr_spec("", f9), "whisper-rust", f9)

    def test_the_f9_daemon_on_another_engine_stays(self):
        for f9 in ("canary", "whisper-rust", "nemotron", "kyutai"):
            self.assertEqual(_diarized_asr_spec("", f9), "", f9)

    def test_other_choices_stay(self):
        for spec in ("canary", "whisper-rust", "whisper-rust-large-v3", "kyutai", "nemotron"):
            self.assertEqual(_diarized_asr_spec(spec, "parakeet"), spec)


class PhaseTwoTests(unittest.TestCase):
    """How phase 2 transcribes the Nemotron 3 pieces."""

    def test_most_backends_go_piece_by_piece(self):
        # vosk reads the whole request as a path: a '\tdiarize' request fails.
        # whisper-rust, SUMM-RE on 2026-10-04: WER 46.8 -> 30.7 % (004c) and
        # 44.0 -> 39.2 % (006b), right speaker 78.7 -> 87.7 % and 74.7 -> 82.2 %
        for backend in ("parakeet", "", None, "canary", "kyutai", "vosk", "whisper-rust"):
            self.assertEqual(_phase2_mode(backend), "pieces", backend)

    def test_nemotron_transcribes_the_whole_file_into_timed_words(self):
        # alone on a short piece this streaming model returns nothing
        self.assertEqual(_phase2_mode("nemotron"), "words")

    def test_faster_whisper_keeps_its_timestamped_full_file_path(self):
        # tiny invents words on short pieces: 006b WER 59.2 -> 75.2 %
        self.assertEqual(_phase2_mode("whisper"), "timestamps")


class TurnsInPiecesTests(unittest.TestCase):
    """Timed words on the Nemotron 3 pieces: one turn per piece holding
    words, timed with the piece."""

    PIECES = [{"start": 0.0, "end": 4.0, "speaker": 0},
              {"start": 4.0, "end": 6.5, "speaker": 1},
              {"start": 8.0, "end": 9.0, "speaker": 0}]

    def word(self, start, end, text="mot"):
        return {"start": start, "end": end, "text": text}

    def turns(self, words, delay=0.0):
        return [(t["start"], t["end"], t["speaker"], " ".join(t["parts"]))
                for t in _turns_in_pieces(words, self.PIECES, delay)]

    def test_each_word_in_the_piece_around_its_middle(self):
        # a word across a change of voice goes where most of it is
        words = [self.word(0.5, 0.9, "un"), self.word(3.5, 4.3, "deux"),
                 self.word(3.9, 4.5, "trois"), self.word(6.0, 6.2, "quatre"),
                 self.word(8.2, 8.5, "cinq")]
        self.assertEqual(self.turns(words), [(0.0, 4.0, 0, "un deux"),
                                             (4.0, 6.5, 1, "trois quatre"),
                                             (8.0, 9.0, 0, "cinq")])

    def test_between_pieces_the_nearest_one(self):
        words = [self.word(6.8, 7.0, "un"), self.word(7.6, 7.8, "deux"),
                 self.word(9.5, 9.8, "trois")]
        self.assertEqual(self.turns(words), [(4.0, 6.5, 1, "un"),
                                             (8.0, 9.0, 0, "deux trois")])

    def test_late_words_are_moved_back_into_their_piece(self):
        # dated 0.3 s late, the last word of a turn falls in the next one
        words = [self.word(3.7, 3.8, "fin"), self.word(4.1, 4.2, "tour")]
        self.assertEqual(self.turns(words), [(0.0, 4.0, 0, "fin"), (4.0, 6.5, 1, "tour")])
        self.assertEqual(self.turns(words, delay=0.3), [(0.0, 4.0, 0, "fin tour")])

    def test_no_piece_no_turn(self):
        self.assertEqual(_turns_in_pieces([self.word(1.0, 1.2)], [], 0.3), [])


class VramNeededTests(unittest.TestCase):
    """Free VRAM below which _on_transcribe stops the F9 daemon."""

    def test_plain_run_loads_parakeet(self):
        self.assertEqual(_vram_needed_mb(diarize=False, own_asr_model=False), 3584)

    def test_nemotron3_beside_the_resident_daemon(self):
        # 664 MiB peak on 21 and 50 min, measured 2026-10-04
        self.assertEqual(_vram_needed_mb(diarize=True, own_asr_model=False), 1024)

    def test_moss_or_an_isolated_engine_loads_its_own_model(self):
        self.assertEqual(_vram_needed_mb(diarize=True, own_asr_model=True), 5120)


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
