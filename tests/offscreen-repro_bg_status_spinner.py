"""Reproducer (m10 + m9): a run landing in the background must not talk
over the tab the user is reading, nor stop someone else's spinner.

m10 — _show_status wrote the run summary straight into the status
labels, with none of the "is this tab visible?" guard _run_status has.
A background run therefore overwrote the status line of the tab in view.

m9 — _show_status stopped EVERY tab spinner, so a concurrent LLM
analysis lost its animation (and got its title reset) while the model
was still generating.
"""
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

from PyQt6.QtCore import QByteArray
from PyQt6.QtWidgets import QApplication, QTextEdit

mod._postprocess = lambda text: text

app = QApplication([])
win = mod.TranscribeWindow()

# Tab A: what the user is reading, with its own status line.
tab_a = QTextEdit()
win._init_tab_state(tab_a, None)
tab_a._raw_text = "older transcription"
tab_a._status_text = "audio 1.0s — transcribed in 2s"
win._tabs.addTab(tab_a, "#1 Transcribe")

# Tab C: an LLM analysis still running, with its spinner.
tab_c = QTextEdit()
tab_c._is_llm_result = True
win._tabs.addTab(tab_c, "#1 LLM: Synthese")
win._start_tab_spinner(tab_c, "#1 LLM: Synthese")

# Tab B: the run, started while B was active.
tab_b = QTextEdit()
win._init_tab_state(tab_b, None)
win._tabs.addTab(tab_b, "#2 Transcribe")
win._tabs.setCurrentWidget(tab_b)
win._text_edit = tab_b
win._run_tab = tab_b
win._start_tab_spinner(tab_b, "#2 Transcribe")

# The user goes back to A while the run is going.
win._tabs.setCurrentWidget(tab_a)
win._lbl_status.setText(tab_a._status_text)
win._lbl_status.setVisible(True)

# The run lands in the background.
win._transcription_in_progress = True
win._stdout_buf = QByteArray(b"hello world")
win._user_cancelled = False
win._daemon_was_active = False
win._chk_diarize.setChecked(False)
win._chk_auto_translate.setChecked(False)
win._start_time = time.monotonic()
win._on_finished(0, 0)

# m10: the visible tab's status line is untouched, the summary is stored
# on the run tab and shows up when the user switches to it.
assert win._lbl_status.text() == tab_a._status_text, (
    f"BUG: background run wrote over the visible tab's status: {win._lbl_status.text()!r}")
assert tab_b._status_text and "transcribed in" in tab_b._status_text, (
    f"the run summary must still be stored on its tab: {tab_b._status_text!r}")
win._tabs.setCurrentWidget(tab_b)
assert win._lbl_status.text() == tab_b._status_text, (
    f"switching to the run tab must show its summary: {win._lbl_status.text()!r}")

# m9: the LLM analysis keeps its spinner; the run's own spinner stopped.
assert tab_c in win._spinning_tabs, (
    "BUG: a finished run stopped the spinner of a still-running LLM analysis")
assert tab_b not in win._spinning_tabs, "the run's own spinner must stop"
assert win._tabs.tabText(win._tabs.indexOf(tab_b)) == "#2 Transcribe", (
    "the run tab title must be restored")

print("BG STATUS SPINNER OK")
