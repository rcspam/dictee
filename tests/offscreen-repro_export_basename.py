"""Reproducer (m13): the export filename must come from the exported
tab's own audio file, not from whatever the Fichier field currently
holds. Loading another file then exporting an older tab used to propose
the new file's name.
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

from PyQt6.QtWidgets import QApplication, QDialog, QTextEdit

app = QApplication([])
win = mod.TranscribeWindow()

seen = {}


class FakeExportDialog:
    def __init__(self, tabs_info, current_format, base_name, parent=None,
                 current_tab_index=0):
        seen["base"] = base_name

    def exec(self):
        return QDialog.DialogCode.Rejected


class FakeLLMExportDialog:
    def __init__(self, default_name, text, parent=None):
        seen["llm_base"] = default_name

    def exec(self):
        return QDialog.DialogCode.Rejected


mod.ExportDialog = FakeExportDialog
mod.LLMExportDialog = FakeLLMExportDialog

# An old transcription of reunion.wav...
old = QTextEdit()
win._init_tab_state(old, "/home/user/audio/reunion.wav")
old._raw_text = "texte de la reunion"
old.setPlainText("texte de la reunion")
win._tabs.addTab(old, "#1 Transcribe")

# ...and an LLM analysis of it, created the way _on_llm_process does.
llm = win._start_llm_result_tab("Synthese", source_widget=old)
llm.setPlainText("resume")
assert getattr(llm, "_audio_path", "missing") is None, (
    "an LLM tab must stay unbound from the player")

# The user has since picked another file in the Fichier field.
win._file_input.setText("/home/user/audio/interview.m4a")

win._tabs.setCurrentWidget(old)
win._on_export_current_tab()
assert seen["base"] == "reunion", (
    f"BUG: export name came from the Fichier field: {seen['base']!r}")

win._tabs.setCurrentWidget(llm)
win._on_export_current_tab()
assert seen["llm_base"] == "reunion-Synthese", (
    f"BUG: LLM export name came from the Fichier field: {seen['llm_base']!r}")

# A tab with no audio of its own still falls back to the Fichier field.
orphan = QTextEdit()
win._init_tab_state(orphan, None)
orphan.setPlainText("sans fichier")
win._tabs.addTab(orphan, "#2 Transcribe")
win._tabs.setCurrentWidget(orphan)
win._on_export_current_tab()
assert seen["base"] == "interview", seen["base"]

print("EXPORT BASENAME OK")
