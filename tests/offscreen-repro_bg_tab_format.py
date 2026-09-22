"""Reproducer (m11): a run that lands while the user reads ANOTHER tab
must be rendered in ITS OWN format, not in the format combo's value
(which shows the active tab's format).

Scenario: the user starts a run with the combo on "text", switches to
another tab and picks "json" there; when the run lands, its tab must
still show plain text and remember "text".
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


def set_format(fmt):
    idx = win._cmb_format.findData(fmt)
    assert idx >= 0, fmt
    win._cmb_format.setCurrentIndex(idx)


# The user was reading tab A in JSON before starting the run.
tab_a = QTextEdit()
win._init_tab_state(tab_a, None)
tab_a._raw_text = "older transcription"
win._tabs.addTab(tab_a, "A")

# Run starts with the combo on "text": its tab is created and active.
set_format("text")
tab_b = QTextEdit()
win._init_tab_state(tab_b, None)
win._tabs.addTab(tab_b, "#1 Transcribe")
win._tabs.setCurrentWidget(tab_b)
win._text_edit = tab_b
win._run_tab = tab_b

# The user switches back to A and picks JSON while the run is going.
win._tabs.setCurrentWidget(tab_a)
set_format("json")

# A is legitimately re-rendered in JSON: that was the user's own click.
a_before = tab_a.toPlainText()
assert a_before.lstrip().startswith("["), a_before

# The run lands in the background.
win._transcription_in_progress = True
win._stdout_buf = QByteArray(b"hello world")
win._user_cancelled = False
win._daemon_was_active = False
win._chk_diarize.setChecked(False)
win._chk_auto_translate.setChecked(False)
win._start_time = time.monotonic()
win._on_finished(0, 0)

assert tab_b._raw_text == "hello world", repr(tab_b._raw_text)
assert tab_b.toPlainText() == "hello world", (
    "BUG: background run rendered in the active tab's format: "
    f"{tab_b.toPlainText()!r}")
assert getattr(tab_b, "_format", None) == "text", (
    "BUG: background run remembered the active tab's format: "
    f"{getattr(tab_b, '_format', None)!r}")

# The active tab must not have been touched by the background run.
assert tab_a.toPlainText() == a_before, repr(tab_a.toPlainText())

# A run landing on the VISIBLE tab still follows the combo (WYSIWYG).
win._tabs.setCurrentWidget(tab_b)
set_format("json")
win._apply_format()
assert tab_b.toPlainText().lstrip().startswith("["), tab_b.toPlainText()
assert tab_b._format == "json"

print("BG TAB FORMAT OK")
