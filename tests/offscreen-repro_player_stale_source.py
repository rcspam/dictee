"""Reproducer M5 (audit 2026-07-25): selecting a file via History or the
recent-files dropdown only sets the text field — the audio player keeps
its previous source, and _on_play_pause only loads when the source is
empty. The user picks meeting B and Play plays meeting A.

QInputDialog.getItem / list_past_meetings are patched to drive the real
_on_open_history without a blocking dialog; the player/selection logic
under test runs unmodified."""
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication

app = QApplication([])
win = mod.TranscribeWindow()

A = "/tmp/meeting-A.wav"
B = "/tmp/meeting-B.wav"
# Real (tiny) WAVs so the media backend loads them without warnings.
import wave
for p in (A, B):
    w = wave.open(p, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(b"\x00\x00" * 1600)
    w.close()

# User browses file A (same three steps as _on_browse).
win._file_input.setText(A)
win._player.stop()
win._load_audio(A)
assert win._player.source().toLocalFile() == A, "precondition: A loaded"

# ── History selection of B (drives the real _on_open_history) ─────────
mod.list_past_meetings = lambda: [("meeting B", B)]
mod.QInputDialog.getItem = staticmethod(lambda *a, **k: ("meeting B", True))
win._on_open_history()
assert win._file_input.text() == B, "precondition: field shows B"
assert win._player.source().toLocalFile() == B, (
    "BUG M5: after picking B in History, the player still holds A — "
    "Play would play the wrong recording")

# ── Recent-files dropdown selection back to A ─────────────────────────
win._file_combo.addItem(A)
idx = win._file_combo.findText(A)
win._file_combo.setCurrentIndex(idx)      # what Qt does on user selection
win._file_combo.activated.emit(idx)       # the user-selection signal
assert win._file_input.text() == A, "precondition: field shows A again"
assert win._player.source().toLocalFile() == A, (
    "BUG M5: after picking A in the recent-files list, the player still "
    "holds B")

print("PLAYER STALE SOURCE OK")
