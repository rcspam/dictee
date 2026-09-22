"""Reproducer: cancelling (or closing the tab of) a phase-2/isolated-plain
run must release the run state. Two audit findings (M1/M2, 2026-07-25):

  M1  _on_cancel_run's phase-2 branch calls dw.cancel() — which suppresses
      the worker's own completion signals — but never sets
      self._diarize_worker = None. _update_transcribe_btn requires it to be
      None, so Transcribe + the diarize toggle + auto-translate + the
      sensitivity slider stay greyed forever ("Cancelled" shown).

  M2  _abort_main_workers (tab close / window close mid-run) cancels the
      workers but resets neither _transcription_in_progress nor the worker
      refs, and never stops the 1 Hz run ticker.

The stand-in worker is a real started QThread (isRunning() is genuinely
True) whose run() spins until cancel() — the window-side logic under test
is executed unmodified."""
import importlib.util
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication, QTextEdit

app = QApplication([])


class BlockedWorker(QThread):
    """Real running thread with the worker's cancel() contract."""

    def __init__(self):
        super().__init__()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        while not self._cancelled:
            time.sleep(0.02)


def arm_phase2(win):
    ed = QTextEdit()
    win._init_tab_state(ed, None)
    win._tabs.addTab(ed, "run")
    win._tabs.setCurrentWidget(ed)
    win._text_edit = ed
    win._run_tab = ed
    win._file_input.setText("/tmp/x.wav")
    win._daemon_was_active = False
    win._user_cancelled = False
    win._start_time = time.monotonic()
    w = BlockedWorker()
    w.start()
    deadline = time.monotonic() + 2
    while not w.isRunning() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert w.isRunning(), "precondition: stand-in worker running"
    win._diarize_worker = w
    win._transcription_in_progress = True
    win._start_run_ticker()
    win._update_transcribe_btn()
    assert not win._btn_transcribe.isEnabled(), "precondition: run in flight"
    return w


# ── M1: Cancel during phase 2 ──────────────────────────────────────────
win = mod.TranscribeWindow()
w = arm_phase2(win)
win._on_cancel_run()
w.wait(2000)
assert getattr(win, "_diarize_worker", None) is None, (
    "BUG M1: _on_cancel_run left _diarize_worker set — Transcribe locked out")
win._update_transcribe_btn()
assert win._btn_transcribe.isEnabled(), (
    "BUG M1: Transcribe still disabled after cancelling phase 2")
assert win._chk_diarize.isEnabled(), (
    "BUG M1: diarize toggle still disabled after cancelling phase 2")

# ── M2: closing the run tab mid-phase-2 (same path as closeEvent) ─────
win2 = mod.TranscribeWindow()
w2 = arm_phase2(win2)
win2._abort_main_workers()
w2.wait(2000)
assert getattr(win2, "_diarize_worker", None) is None, (
    "BUG M2: _abort_main_workers left _diarize_worker set — window bricked")
assert not win2._transcription_in_progress, (
    "BUG M2: _transcription_in_progress still True after abort")
assert getattr(win2, "_run_ticker", None) is None, (
    "BUG M2: 1 Hz run ticker still alive after abort (leaked QTimer)")
win2._update_transcribe_btn()
assert win2._btn_transcribe.isEnabled(), (
    "BUG M2: Transcribe still disabled after closing the run tab")

print("PHASE2 CANCEL LOCKOUT OK")
