"""Reproducer: speaker rename must stay within one run's family.

A and B are two independent diarized runs of the SAME audio file; T is
a translation of A. Renaming from A must update A and T, never B.
"""
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication, QLineEdit, QTextEdit

app = QApplication([])
win = mod.TranscribeWindow()

SEGS = [{"start": 0.0, "end": 1.0, "speaker": "Speaker 0", "text": "hi"}]


def make_run_tab(title):
    ed = QTextEdit()
    win._init_tab_state(ed, "/tmp/same-file.wav")
    ed._was_diarized = True
    ed._diarize_segments = [dict(s) for s in SEGS]
    ed._raw_text = "[0.00s - 1.00s] Speaker 0: hi"
    win._tabs.addTab(ed, title)
    return ed


tab_a = make_run_tab("#1 Diarize")
tab_b = make_run_tab("#2 Diarize")

# Translation of A, built the way _on_translate_done does it
tab_t = QTextEdit()
win._init_tab_state(tab_t, "/tmp/same-file.wav")
tab_t._rename_family = getattr(tab_a, "_rename_family", tab_a)
tab_t._was_diarized = True
tab_t._diarize_segments = [dict(s) for s in SEGS]
tab_t._raw_text = "[0.00s - 1.00s] Speaker 0: salut"
win._tabs.addTab(tab_t, "fr")

win._tabs.setCurrentWidget(tab_a)
le = QLineEdit()
le.setText("Alice")
win._rename_line_edits = {"Speaker 0": le}

win._apply_speaker_rename()

assert tab_a._speaker_name_map == {"Speaker 0": "Alice"}, tab_a._speaker_name_map
assert tab_t._speaker_name_map == {"Speaker 0": "Alice"}, (
    "translation tab must keep syncing with its source run")
assert tab_b._speaker_name_map == {}, (
    "BUG: independent run of the same file was renamed too: "
    f"{tab_b._speaker_name_map}")
print("RENAME FAMILY OK")
