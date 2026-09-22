"""Reproducer: the Cancel button must be hidden when a one-pass
QProcess run finishes (user report: after a MOSS diarize run both
Transcribe and Cancel stayed on screen). Exercises _on_finished's
success and empty-output paths — only the cancel/error paths hid the
button. isHidden() is used instead of isVisible(): the window is never
shown offscreen, so isVisible() would be False regardless."""
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

mod._postprocess = lambda text: text

app = QApplication([])
win = mod.TranscribeWindow()


def run(raw, diarize):
    ed = QTextEdit()
    win._init_tab_state(ed, None)
    win._tabs.addTab(ed, "run")
    win._tabs.setCurrentWidget(ed)
    win._text_edit = ed
    win._run_tab = ed
    win._transcription_in_progress = True
    win._stdout_buf = QByteArray(raw.encode())
    win._user_cancelled = False
    win._daemon_was_active = False
    win._chk_diarize.setChecked(diarize)
    win._chk_auto_translate.setChecked(False)
    import time
    win._start_time = time.monotonic()
    # As _on_transcribe does for every QProcess run shape
    win._btn_cancel.setVisible(True)
    win._btn_cancel.setEnabled(True)
    assert not win._btn_cancel.isHidden(), "precondition: Cancel armed"
    win._on_finished(0, 0)
    return ed


# Success path, diarized output (the MOSS one-pass shape)
raw = "[0.00s - 1.00s] Speaker 0: hi\n[1.00s - 2.00s] Speaker 1: yo"
run(raw, diarize=True)
assert win._btn_cancel.isHidden(), (
    "BUG: Cancel still shown after a successful one-pass diarized run")

# Empty-output path (same structural hole)
run("", diarize=False)
assert win._btn_cancel.isHidden(), (
    "BUG: Cancel still shown after a one-pass run with no output")

print("CANCEL BTN OK")
