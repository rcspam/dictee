"""Reproducer (m2 + m3): the Translate button must follow the active tab
AND the run state.

m2 — _update_translate_btn has no run-in-progress guard, and
_on_tab_changed calls it on every switch. Switching to an older finished
tab during a run re-enabled Translate, letting a translation start on
top of a running transcription.

m3 — LLM result tabs have no _rename_family (they never go through
_init_tab_state), so the button fell back to self._text_edit, the last
created run: Translate looked enabled on an LLM tab and would translate
a completely different tab's text.
"""
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py"
spec = importlib.util.spec_from_file_location("dictee_transcribe", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication, QTextEdit

app = QApplication([])
win = mod.TranscribeWindow()

# Translation must look available: a target language and a working
# backend, no auto-translate.
mod._translate_available = lambda backend: True
idx = win._cmb_lang_tgt.findData("fr")
if idx < 0:
    win._cmb_lang_tgt.addItem("Français", "fr")
    idx = win._cmb_lang_tgt.count() - 1
win._cmb_lang_tgt.setCurrentIndex(idx)
win._chk_auto_translate.setChecked(False)

# A finished run tab with text.
done = QTextEdit()
win._init_tab_state(done, "/tmp/a.wav")
done._raw_text = "some transcribed text"
win._tabs.addTab(done, "#1 Transcribe")
win._text_edit = done

win._tabs.setCurrentWidget(done)
win._update_translate_btn()
assert win._btn_translate.isEnabled(), "precondition: Translate is available when idle"

# --- m2: a run is going, the user switches to the finished tab --------
running = QTextEdit()
win._init_tab_state(running, "/tmp/b.wav")
win._tabs.addTab(running, "#2 Transcribe")
win._text_edit = running
win._run_tab = running
win._transcription_in_progress = True
win._tabs.setCurrentWidget(running)       # the run tab is shown at start

win._tabs.setCurrentWidget(done)          # user switches back: _on_tab_changed
assert not win._btn_translate.isEnabled(), (
    "BUG: switching tabs during a run re-enabled Translate")

win._transcription_in_progress = False
win._tabs.setCurrentWidget(running)
win._tabs.setCurrentWidget(done)
assert win._btn_translate.isEnabled(), "Translate must come back once the run is over"

# --- m3: an LLM result tab is not translatable ------------------------
# The last created run must hold text, otherwise the fallback the bug
# relies on (self._text_edit) is empty and hides it.
win._text_edit = done
llm = win._start_llm_result_tab("Synthese", source_widget=done)
llm.setPlainText("resume")
win._tabs.setCurrentWidget(llm)
assert not win._btn_translate.isEnabled(), (
    "BUG: Translate enabled on an LLM tab (it would translate another tab)")

# ...and clicking it anyway (stale enabled state) must do nothing rather
# than translate the last run behind the user's back.
captured = []


class FakeSig:
    def connect(self, *a):
        pass

    def disconnect(self, *a):
        pass


class FakeThread:
    def __init__(self, raw_text, *a, **kw):
        captured.append(raw_text)
        self.finished_signal = FakeSig()
        self.error_signal = FakeSig()

    def isRunning(self):
        return False

    def start(self):
        pass

    def deleteLater(self):
        pass


mod.TranslateThread = FakeThread
win._on_translate(False)
assert captured == [], (
    f"BUG: translating from an LLM tab translated another tab: {captured!r}")

# Back on a real tab, Translate works again.
win._tabs.setCurrentWidget(done)
assert win._btn_translate.isEnabled()

print("TRANSLATE BTN GATING OK")
