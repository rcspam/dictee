"""Reproducer (m12): renaming a speaker must not throw away manual edits
made in a sibling tab the user is not looking at.

A speaker rename re-renders every tab of the run's family. A translation
tab the user has hand-corrected is re-rendered from its segments, which
silently replaces the whole text. The visible tab is still re-rendered
(that is the point of clicking Apply), but background siblings keep
their text; their name map is updated so the next explicit render shows
the new names.
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

tab_a = QTextEdit()
win._init_tab_state(tab_a, "/tmp/file.wav")
tab_a._was_diarized = True
tab_a._diarize_segments = [dict(s) for s in SEGS]
tab_a._raw_text = "[0.00s - 1.00s] Speaker 0: hi"
win._tabs.addTab(tab_a, "#1 Diarize")

# Translation of A: same family, rendered once, then hand-corrected.
tab_t = QTextEdit()
win._init_tab_state(tab_t, "/tmp/file.wav")
tab_t._rename_family = tab_a
tab_t._was_diarized = True
tab_t._diarize_segments = [dict(s) for s in SEGS]
tab_t._raw_text = "[0.00s - 1.00s] Speaker 0: salut"
win._tabs.addTab(tab_t, "#1 Diarize → fr")
win._tabs.setCurrentWidget(tab_t)
win._apply_format_to(tab_t, tab_t._diarize_segments, tab_t._raw_text)
EDITED = "Speaker 0: salut — corrigé à la main"
tab_t.setPlainText(EDITED)

# An untouched sibling must still follow the rename.
tab_u = QTextEdit()
win._init_tab_state(tab_u, "/tmp/file.wav")
tab_u._rename_family = tab_a
tab_u._was_diarized = True
tab_u._diarize_segments = [dict(s) for s in SEGS]
tab_u._raw_text = "[0.00s - 1.00s] Speaker 0: hallo"
win._tabs.addTab(tab_u, "#1 Diarize → de")
win._tabs.setCurrentWidget(tab_u)
win._apply_format_to(tab_u, tab_u._diarize_segments, tab_u._raw_text)

# The user renames from the run tab.
win._tabs.setCurrentWidget(tab_a)
le = QLineEdit()
le.setText("Alice")
win._rename_line_edits = {"Speaker 0": le}
win._apply_speaker_rename()

assert tab_t.toPlainText() == EDITED, (
    f"BUG: manual edits of a background sibling were wiped: {tab_t.toPlainText()!r}")
assert tab_t._speaker_name_map == {"Speaker 0": "Alice"}, (
    "the edited tab must still learn the new names for its next render")
assert "Alice" in tab_u.toPlainText(), (
    f"untouched sibling must be re-rendered with the new name: {tab_u.toPlainText()!r}")
assert "Alice" in tab_a.toPlainText(), (
    f"the active tab must show the rename: {tab_a.toPlainText()!r}")

print("RENAME KEEPS EDITS OK")
