"""Reproducer M4 (audit 2026-07-25): on an install with NO diarization
engine, the toggle is correctly disabled at build time (with its
"No diarization model installed" tooltip), but _update_transcribe_btn
re-enables it with a bare setEnabled(not_running) — and it is wired to
_file_input.textChanged, so merely picking a file re-arms a toggle whose
run can only fail with "Command 'diarize-only' not found".

The availability helpers are module-level; patching them before window
construction simulates the engine-less install — the window logic under
test runs unmodified."""
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

# ── Install WITHOUT any diarization engine ────────────────────────────
_orig = (mod._diar_multi_available, mod._sortformer_available, mod._moss_available)
mod._diar_multi_available = lambda: False
mod._sortformer_available = lambda: False
mod._moss_available = lambda: False

win = mod.TranscribeWindow()
assert not win._chk_diarize.isEnabled(), (
    "precondition: toggle disabled at build time when no engine is installed")

win._file_input.setText("/tmp/whatever.wav")  # fires _update_transcribe_btn
assert not win._chk_diarize.isEnabled(), (
    "BUG M4: picking a file re-enabled the diarize toggle on an install "
    "with no diarization engine")

# ── Sanity: with engines available, the toggle still re-arms when idle ─
(mod._diar_multi_available, mod._sortformer_available, mod._moss_available) = _orig
win2 = mod.TranscribeWindow()
if win2._chk_diarize.isEnabled():  # dev machine has engines installed
    win2._file_input.setText("/tmp/whatever.wav")
    assert win2._chk_diarize.isEnabled(), (
        "REGRESSION: toggle must stay enabled when engines exist and no run "
        "is in flight")

print("DIAR TOGGLE NO ENGINE OK")
