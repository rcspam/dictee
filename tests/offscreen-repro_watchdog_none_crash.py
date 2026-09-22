"""Reproducer: the duration watchdog must survive its own kill (M3,
audit 2026-07-25). _on_process_timeout kills the QProcess then calls
waitForFinished(3000); QProcess emits finished synchronously while
reaping (same-thread direct connection to _on_finished, wired exactly
as _on_transcribe does), whose preamble deleteLater()s and nulls
self._process. Control returns to _on_process_timeout, which then does
self._process.deleteLater() on None -> AttributeError inside a QTimer
slot -> PyQt6 aborts the whole app in production.

Uses a real QProcess running `sleep 30` with the app's own signal
wiring — nothing is stubbed on the path under test."""
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

from PyQt6.QtCore import QByteArray, QProcess
from PyQt6.QtWidgets import QApplication, QTextEdit

mod._postprocess = lambda text: text

app = QApplication([])
win = mod.TranscribeWindow()

ed = QTextEdit()
win._init_tab_state(ed, None)
win._tabs.addTab(ed, "run")
win._tabs.setCurrentWidget(ed)
win._text_edit = ed
win._run_tab = ed
win._transcription_in_progress = True
win._stdout_buf = QByteArray(b"")
win._user_cancelled = False
win._daemon_was_active = False
win._start_time = time.monotonic()

proc = QProcess(win)
proc.finished.connect(win._on_finished)  # same wiring as _on_transcribe
win._process = proc
proc.start("sleep", ["30"])
assert proc.waitForStarted(3000), "precondition: sleep process started"

try:
    win._on_process_timeout()
except AttributeError as e:
    raise AssertionError(
        f"BUG M3: watchdog crashed on its own cleanup ({e}) — in production "
        "PyQt6 aborts the app and every open tab is lost") from e

assert win._process is None, "watchdog must leave _process cleared"
assert not win._transcription_in_progress, (
    "watchdog must lower _transcription_in_progress")
win._update_transcribe_btn()  # has_file False here; just must not raise

print("WATCHDOG TIMEOUT OK")
