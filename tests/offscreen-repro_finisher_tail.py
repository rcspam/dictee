"""Structural test of the factored finisher tail: drive _on_finished
through a successful one-pass run (plain and diarized) and check what
lands on the target tab. _postprocess is stubbed to identity."""
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
    win._on_finished(0, 0)
    return ed


# Plain run: control chars must now be stripped (the old QProcess path
# kept them — _clean_segment_text alignment)
ed = run("hello\x07 world  ", diarize=False)
assert ed._raw_text == "hello world", repr(ed._raw_text)
assert ed._was_diarized is False and ed._diarize_segments == []
assert ed._transcribe_elapsed >= 0.0 and ed._status_text, "summary stored on tab"
assert win._transcription_in_progress is False

# Diarized run: segments parsed and stored on the tab
raw = "[0.00s - 1.00s] Speaker 0: hi\n[1.00s - 2.00s] Speaker 1: yo"
ed2 = run(raw, diarize=True)
assert ed2._was_diarized is True
assert [s["speaker"] for s in ed2._diarize_segments] == ["Speaker 0", "Speaker 1"]
assert ed2._speaker_name_map == {}
assert "2" in ed2._status_text, ed2._status_text  # "2 speaker(s)" summary
assert getattr(win, '_run_ticker', None) is None

print("FINISHER TAIL OK")
