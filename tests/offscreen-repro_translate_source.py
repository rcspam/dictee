"""Reproducer: Translate must use the ACTIVE tab's run, not the last
created tab. A and B are two finished runs; A is active, B is the last
(self._text_edit). TranslateThread is stubbed to capture its input."""
import importlib.util
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication, QTextEdit

app = QApplication([])
win = mod.TranscribeWindow()


class FakeSig:
    def connect(self, *a):
        pass

    def disconnect(self, *a):
        pass


class FakeThread:
    captured = None

    def __init__(self, raw_text, segments, was_diarized,
                 lang_src, lang_tgt, backend):
        FakeThread.captured = raw_text
        self.finished_signal = FakeSig()
        self.error_signal = FakeSig()

    def isRunning(self):
        return False

    def start(self):
        pass

    def deleteLater(self):
        pass


mod.TranslateThread = FakeThread
win._cmb_lang_tgt = types.SimpleNamespace(currentData=lambda: "fr")

TEXT_A = "Hello, this is the first English recording about the weather."
TEXT_B = "Goodbye, this is the second English recording about music."


def make_run_tab(title, text):
    ed = QTextEdit()
    win._init_tab_state(ed, f"/tmp/{title}.wav")
    ed._raw_text = text
    win._tabs.addTab(ed, title)
    win._text_edit = ed
    return ed


tab_a = make_run_tab("run-a", TEXT_A)
tab_b = make_run_tab("run-b", TEXT_B)
assert win._text_edit is tab_b, "precondition: B is the last created tab"

# User is viewing A and clicks Translate (clicked sends a bool)
win._tabs.setCurrentWidget(tab_a)
win._on_translate(False)
assert FakeThread.captured == TEXT_A, (
    f"BUG: translated the last tab, not the active one: {FakeThread.captured!r}")

# Auto-translate must pin its source regardless of the visible tab
win._translate_thread = None
win._tabs.setCurrentWidget(tab_a)
win._on_translate(source=tab_b)
assert FakeThread.captured == TEXT_B, "explicit source= must win"

print("TRANSLATE SOURCE OK")
