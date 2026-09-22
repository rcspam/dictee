"""Reproducer: the 1 Hz run ticker must stop when a one-pass QProcess
run finishes. Exercises _on_finished's empty-output path (same
structural hole as the success path: no _stop_run_ticker)."""
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtCore import QByteArray
from PyQt6.QtWidgets import QApplication, QTextEdit

app = QApplication([])
win = mod.TranscribeWindow()

ed = QTextEdit()
win._init_tab_state(ed, None)
win._tabs.addTab(ed, "run")
win._text_edit = ed
win._run_tab = ed
win._transcription_in_progress = True
win._stdout_buf = QByteArray()  # empty output -> "No transcription result."
win._user_cancelled = False
win._daemon_was_active = False

win._start_run_ticker()
assert win._run_ticker is not None, "precondition: ticker armed"

win._on_finished(0, 0)

assert win._run_ticker is None, (
    "BUG: run ticker still alive after a finished one-pass run "
    "(phantom clock / alternating status lines)")
print("TICKER OK")
