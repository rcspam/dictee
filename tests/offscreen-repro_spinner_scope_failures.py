"""Reproducer (m9, remaining sites): the failure/cancel/timeout paths of
a run must stop that run's spinner only.

m9 was fixed on the success tail (_show_status), but every other run
terminator still called _stop_all_spinners(), which wipes the spinner of
a concurrent LLM analysis that is still generating.

Each case below runs one terminator with an LLM tab spinning and checks
the LLM keeps its animation while the run's own spinner stops.
"""
import importlib.util
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py"
spec = importlib.util.spec_from_file_location("dictee_transcribe", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtCore import QByteArray, QProcess
from PyQt6.QtWidgets import QApplication, QTextEdit

mod._postprocess = lambda text: text

app = QApplication([])
win = mod.TranscribeWindow()

# The LLM analysis that must survive every case below.
llm = QTextEdit()
llm._is_llm_result = True
win._tabs.addTab(llm, "#1 LLM: Synthese")
win._start_tab_spinner(llm, "#1 LLM: Synthese")


def new_run_tab(name):
    """A fresh run tab with its spinner, set up as the current run."""
    ed = QTextEdit()
    win._init_tab_state(ed, None)
    win._tabs.addTab(ed, name)
    win._text_edit = ed
    win._run_tab = ed
    win._transcription_in_progress = True
    win._start_tab_spinner(ed, name)
    win._start_time = time.monotonic()
    return ed


def check(case, run_tab):
    assert llm in win._spinning_tabs, (
        f"BUG [{case}]: stopped a concurrent LLM analysis's spinner")
    assert run_tab not in win._spinning_tabs, (
        f"[{case}]: the run's own spinner must stop")


# 1. User cancelled a phase-1 / one-pass QProcess run.
tab = new_run_tab("#1 Transcribe")
win._user_cancelled = True
win._daemon_was_active = False
win._stdout_buf = QByteArray(b"")
win._on_finished(0, 0)
check("cancelled run", tab)

# 2. Engine exited with an error code.
tab = new_run_tab("#2 Transcribe")
win._user_cancelled = False
win._stdout_buf = QByteArray(b"boom")
win._on_finished(3, 0)
check("non-zero exit", tab)

# 3. Engine succeeded but produced nothing.
tab = new_run_tab("#3 Transcribe")
win._stdout_buf = QByteArray(b"")
win._on_finished(0, 0)
check("empty output", tab)

# 4. Chunked pipeline failed.
tab = new_run_tab("#4 Transcribe")
win._on_chunked_error("chunked failed")
check("chunked error", tab)

# 5. Phase-2 diarization failed.
tab = new_run_tab("#5 Diarize")
win._on_diarize_error("phase 2 failed")
check("diarize error", tab)

# 6. Watchdog fired on a live process (the terminator only runs when the
#    process is actually still going).
tab = new_run_tab("#6 Diarize")
win._process = QProcess(win)
win._process.start("sleep", ["30"])
assert win._process.waitForStarted(3000), "could not start the stand-in process"
win._on_process_timeout()
check("watchdog timeout", tab)

# 7. Cancel clicked during phase 2.
tab = new_run_tab("#7 Diarize")


class FakeWorker:
    def isRunning(self):
        return True

    def cancel(self):
        pass


win._chunked_worker = None
win._process = None
win._diarize_worker = FakeWorker()
win._btn_cancel.setVisible(True)
win._on_cancel_run()
check("phase-2 cancel", tab)

# 8. Two-phase finisher with no text at all.
tab = new_run_tab("#8 Diarize")
win._finish_transcription("", tab, True)
check("finisher, no result", tab)

# No terminator may reach for the global spinner sweep any more.
source = open(SRC, encoding="utf-8").read()
assert "_stop_all_spinners" not in source, (
    "BUG: a run terminator still stops every spinner in the window")

print("SPINNER SCOPE OK")
