"""Reproducer (m14 + m15): exporting must use the tab the user is on.

m14 — _do_export re-resolved the tab by TITLE and took the first match.
Two translations of the same run into the same language with the same
backend carry the exact same title, so exporting the second one wrote
the first one's segments.

m15 — for a tab with no speaker segments, the JSON/SRT export only used
the tab's stored raw text when the tab was at index 0; any other tab
exported whatever was on screen, so a tab displayed as JSON came out as
JSON nested inside JSON.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication, QDialog, QTextEdit

app = QApplication([])
win = mod.TranscribeWindow()

out_dir = tempfile.mkdtemp(prefix="dictee-export-test-")


class FakeExportDialog:
    """Accepts immediately and exports the requested formats."""
    formats = ["text"]

    def __init__(self, tabs_info, current_format, base_name, parent=None,
                 current_tab_index=0):
        self._tabs_info = list(tabs_info)
        self._base = base_name

    def exec(self):
        return QDialog.DialogCode.Accepted

    def selected_tabs(self):
        return list(self._tabs_info)

    def export_formats(self):
        return list(FakeExportDialog.formats)

    def export_dir(self):
        return out_dir

    def base_name(self):
        return self._base


mod.ExportDialog = FakeExportDialog


def read_export(fmt_ext, tab_title, base="transcription"):
    import re as _re
    safe = _re.sub(r'[^\w.-]', '_', tab_title)
    path = os.path.join(out_dir, f"{base}-{safe}{fmt_ext}")
    with open(path, encoding="utf-8") as f:
        return f.read()


# --- m14: two translation tabs sharing one title -----------------------
SEGS_1 = [{"start": 0.0, "end": 1.0, "speaker": "Speaker 0", "text": "premier"}]
SEGS_2 = [{"start": 0.0, "end": 1.0, "speaker": "Speaker 0", "text": "second"}]
TITLE = "#1 Diarize 50% → Espagnol (Google)"

win._file_input.setText("/tmp/reunion.wav")

t1 = QTextEdit()
win._init_tab_state(t1, "/tmp/reunion.wav")
t1._was_diarized = True
t1._diarize_segments = [dict(s) for s in SEGS_1]
t1._raw_text = "premier"
win._tabs.addTab(t1, TITLE)

t2 = QTextEdit()
win._init_tab_state(t2, "/tmp/reunion.wav")
t2._was_diarized = True
t2._diarize_segments = [dict(s) for s in SEGS_2]
t2._raw_text = "second"
win._tabs.addTab(t2, TITLE)

win._tabs.setCurrentWidget(t2)
win._apply_format_to(t2, t2._diarize_segments, t2._raw_text)
FakeExportDialog.formats = ["text"]
win._on_export_current_tab()
got = read_export(".txt", TITLE, base="reunion")
assert "second" in got and "premier" not in got, (
    f"BUG: exported the first tab with the same title: {got!r}")

# --- m15: segment-less tab away from index 0, displayed as JSON --------
plain = QTextEdit()
win._init_tab_state(plain, "/tmp/reunion.wav")
plain._raw_text = "texte simple sans locuteurs"
win._tabs.addTab(plain, "#2 Transcribe")
win._tabs.setCurrentWidget(plain)
idx = win._cmb_format.findData("json")
win._cmb_format.setCurrentIndex(idx)
win._apply_format_to(plain, [], plain._raw_text)
assert plain.toPlainText().lstrip().startswith("["), plain.toPlainText()

FakeExportDialog.formats = ["json"]
win._on_export_current_tab()
payload = json.loads(read_export(".json", "#2 Transcribe", base="reunion"))
assert payload == [{"text": "texte simple sans locuteurs"}], (
    f"BUG: JSON export of a non-index-0 plain tab nested the rendered view: {payload!r}")

FakeExportDialog.formats = ["srt"]
win._on_export_current_tab()
srt = read_export(".srt", "#2 Transcribe", base="reunion")
assert "texte simple sans locuteurs" in srt and "{" not in srt, (
    f"BUG: SRT export of a non-index-0 plain tab used the rendered view: {srt!r}")

# A tab the user edited must export its edits, not the stored raw text —
# in its own format and across formats.
plain2 = QTextEdit()
win._init_tab_state(plain2, "/tmp/reunion.wav")
plain2._raw_text = "avant correction"
win._tabs.addTab(plain2, "#3 Transcribe")
win._tabs.setCurrentWidget(plain2)
win._cmb_format.setCurrentIndex(win._cmb_format.findData("text"))
win._apply_format_to(plain2, [], plain2._raw_text)
plain2.setPlainText("apres correction")

FakeExportDialog.formats = ["text"]
win._on_export_current_tab()
assert read_export(".txt", "#3 Transcribe", base="reunion") == "apres correction", (
    "edited tab must export its edits verbatim in its own format")

FakeExportDialog.formats = ["json"]
win._on_export_current_tab()
payload2 = json.loads(read_export(".json", "#3 Transcribe", base="reunion"))
assert payload2 == [{"text": "apres correction"}], (
    f"cross-format export of an edited tab must carry the edits: {payload2!r}")

shutil.rmtree(out_dir, ignore_errors=True)
print("EXPORT TARGET OK")
