"""Reproducer M6 (audit 2026-07-25): a TOTAL translation failure (backend
down) must not fabricate a translation tab full of untranslated source
text, nor overwrite the error with a success summary.

Pre-fix: TranslateThread emitted the SOURCE text as the finished result;
_on_translate_done unconditionally created the "src → Lang (Backend)" tab,
filled it with the source, switched to it, and _show_status replaced the
error with "audio X — translated in Y".

mod._translate_text is patched to return "" (what a dead backend yields);
everything else — the real thread, the real signals, the real slots — runs
unmodified."""
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication, QTextEdit

app = QApplication([])
win = mod.TranscribeWindow()

# A finished English run tab.
ed = QTextEdit()
win._init_tab_state(ed, None)
ed._raw_text = "The quick brown fox jumps over the lazy dog."
win._tabs.addTab(ed, "#1 Transcribe")
win._tabs.setCurrentWidget(ed)
win._text_edit = ed

# Target French, dead backend.
idx = win._cmb_lang_tgt.findData("fr")
assert idx >= 0, "precondition: French available in the target combo"
win._cmb_lang_tgt.setCurrentIndex(idx)
mod._translate_text = lambda *a, **k: ""

tabs_before = win._tabs.count()
win._on_translate()
th = win._translate_thread
assert th is not None, "precondition: translation thread started"
th.wait(10000)
for _ in range(20):  # deliver the queued cross-thread signals
    app.processEvents()

assert win._tabs.count() == tabs_before, (
    "BUG M6: a translation tab was created although the translation "
    "totally failed — it would contain the untranslated source text")
status = win._lbl_status.text()
assert "failed" in status.lower() or "échou" in status.lower(), (
    f"BUG M6: the error message was overwritten — status shows: {status!r}")

print("TRANSLATE FAIL TAB OK")
