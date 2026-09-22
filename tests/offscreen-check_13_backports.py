"""Check the audit backports on release/1.3 (m4, m6, m7, m9, m11, m12,
m13, m14, m15).

1.3 has no per-tab state helper (_init_tab_state) and no _run_tab, so
tabs are built by hand here and the run tab is self._text_edit, exactly
as the 1.3 code assumes.

The VRAM probe is stubbed: the real one can stop the user's systemd ASR
services, which a test must never do.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_real_run = subprocess.run

SRC = "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py"
spec = importlib.util.spec_from_file_location("dictee_transcribe", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtCore import QByteArray, QProcess
from PyQt6.QtWidgets import QApplication, QDialog, QTextEdit

mod._postprocess = lambda text: text

WAV = "/tmp/dictee-13-check.wav"
OTHER = "/tmp/dictee-13-check-other.wav"
for p in (WAV, OTHER):
    w = wave.open(p, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(b"\x00\x00" * 16000)
    w.close()


class _Res:
    def __init__(self, out="", code=0):
        self.stdout = out
        self.stderr = ""
        self.returncode = code


def fake_run(cmd, *a, **kw):
    exe = cmd[0] if isinstance(cmd, (list, tuple)) else str(cmd)
    if exe == "ffprobe":
        return _real_run(cmd, *a, **kw)
    if exe == "nvidia-smi":
        return _Res("99999\n")
    raise AssertionError(f"test tried to run {exe}")


mod.subprocess.run = fake_run

app = QApplication([])
win = mod.TranscribeWindow()
win.show()

FAILED = []


def check(cond, msg):
    if not cond:
        FAILED.append(msg)


def new_run_tab(name, audio=None):
    ed = QTextEdit()
    ed._audio_path = audio
    ed._raw_text = ""
    ed._diarize_segments = []
    ed._was_diarized = False
    win._tabs.addTab(ed, name)
    win._text_edit = ed
    win._transcription_in_progress = True
    win._start_tab_spinner(ed, name)
    win._start_time = time.monotonic()
    return ed


# The LLM analysis that must keep its spinner through every terminator.
llm = QTextEdit()
llm._is_llm_result = True
win._tabs.addTab(llm, "#1 LLM: Synthese")
win._start_tab_spinner(llm, "#1 LLM: Synthese")

# --- m9: run terminators must not sweep other spinners ----------------
tab = new_run_tab("#1 Transcribe")
win._stdout_buf = QByteArray(b"boom")
win._user_cancelled = False
win._daemon_was_active = False
win._process = None
win._on_finished(3, 0)
check(llm in win._spinning_tabs, "m9 non-zero exit killed the LLM spinner")
check(tab not in win._spinning_tabs, "m9 the run's own spinner must stop")

tab = new_run_tab("#2 Transcribe")
win._stdout_buf = QByteArray(b"")
win._on_finished(0, 0)
check(llm in win._spinning_tabs, "m9 empty output killed the LLM spinner")

tab = new_run_tab("#3 Transcribe")
win._on_chunked_error("chunked failed")
check(llm in win._spinning_tabs, "m9 chunked error killed the LLM spinner")

tab = new_run_tab("#4 Diarize")
win._on_diarize_error("phase 2 failed")
check(llm in win._spinning_tabs, "m9 diarize error killed the LLM spinner")

tab = new_run_tab("#5 Diarize")
win._process = QProcess(win)
win._process.start("sleep", ["30"])
win._process.waitForStarted(3000)
win._on_process_timeout()
check(llm in win._spinning_tabs, "m9 watchdog killed the LLM spinner")
check(tab not in win._spinning_tabs, "m9 watchdog must stop the run's spinner")

tab = new_run_tab("#6 Transcribe")
win._process = None
win._finish_transcription("")
check(llm in win._spinning_tabs, "m9 empty finisher killed the LLM spinner")

tab = new_run_tab("#7 Transcribe")
win._audio_duration = 1.0
win._segments = []
win._was_diarized = False
win._transcribe_elapsed = 1.0
win._translate_elapsed = 0.0
win._show_status()
check(llm in win._spinning_tabs, "m9 _show_status killed the LLM spinner")
check(tab not in win._spinning_tabs, "m9 _show_status must stop the run's spinner")

# --- m4: missing engine binary ----------------------------------------
win._file_input.setText(WAV)
win._chk_diarize.setChecked(False)
mod._select_transcribe_cmd = lambda **kw: (None, False, "transcribe")
win._on_transcribe()
run_tab = win._text_edit
check(run_tab not in win._spinning_tabs, "m4 spinner spins forever on a missing binary")
check(win._transcription_in_progress is False, "m4 run flag stuck")

# --- m6: phase 2 cannot find the audio --------------------------------
tab = new_run_tab("#8 Diarize")
win._progress.setVisible(True)
win._diarize_audio_path = "/tmp/deleted-mid-run.wav"
win._restart_daemon_and_transcribe("[0.00s - 1.00s] Speaker 0: hi")
check(tab not in win._spinning_tabs, "m6 spinner spins forever when phase 2 audio is gone")
check(not win._progress.isVisible(), "m6 progress bar stays up")

# --- m11: a background run keeps its own format -----------------------
def set_format(fmt):
    win._cmb_format.setCurrentIndex(win._cmb_format.findData(fmt))


other = QTextEdit()
other._audio_path = None
other._raw_text = "older"
other._diarize_segments = []
other._was_diarized = False
other._format = "json"
win._tabs.addTab(other, "older tab")

# The run tab must be created by the real path: that is where 1.3 now
# captures the format (there is no _init_tab_state to do it).
set_format("text")
win._file_input.setText(WAV)
mod._select_transcribe_cmd = lambda **kw: (None, False, "transcribe")
win._on_transcribe()
bg = win._text_edit
win._transcription_in_progress = True
win._start_tab_spinner(bg, "#9 Transcribe")
win._start_time = time.monotonic()
win._tabs.setCurrentWidget(other)
set_format("json")
win._process = None
win._stdout_buf = QByteArray(b"hello world")
win._on_finished(0, 0)
check(bg.toPlainText() == "hello world",
      f"m11 background run rendered in the active tab's format: {bg.toPlainText()!r}")
check(getattr(bg, "_format", None) == "text",
      f"m11 background run remembered the wrong format: {getattr(bg, '_format', None)!r}")

# --- m12: renaming must not wipe hand edits ---------------------------
SEGS = [{"start": 0.0, "end": 1.0, "speaker": "Speaker 0", "text": "hi"}]
src_tab = QTextEdit()
src_tab._audio_path = WAV
src_tab._was_diarized = True
src_tab._diarize_segments = [dict(s) for s in SEGS]
src_tab._raw_text = "[0.00s - 1.00s] Speaker 0: hi"
win._tabs.addTab(src_tab, "#10 Diarize")

edited_tab = QTextEdit()
edited_tab._audio_path = WAV
edited_tab._was_diarized = True
edited_tab._diarize_segments = [dict(s) for s in SEGS]
edited_tab._raw_text = "[0.00s - 1.00s] Speaker 0: salut"
win._tabs.addTab(edited_tab, "#10 Diarize -> fr")
win._tabs.setCurrentWidget(edited_tab)
win._apply_format_to(edited_tab, edited_tab._diarize_segments, edited_tab._raw_text)
EDITED = "Speaker 0: salut, corrige a la main"
edited_tab.setPlainText(EDITED)

untouched = QTextEdit()
untouched._audio_path = WAV
untouched._was_diarized = True
untouched._diarize_segments = [dict(s) for s in SEGS]
untouched._raw_text = "[0.00s - 1.00s] Speaker 0: hallo"
win._tabs.addTab(untouched, "#10 Diarize -> de")
win._tabs.setCurrentWidget(untouched)
win._apply_format_to(untouched, untouched._diarize_segments, untouched._raw_text)

win._tabs.setCurrentWidget(src_tab)
win._was_diarized = True
win._segments = [dict(s) for s in SEGS]
from PyQt6.QtWidgets import QLineEdit

le = QLineEdit()
le.setText("Alice")
win._rename_line_edits = {"Speaker 0": le}
win._apply_speaker_rename()
check(edited_tab.toPlainText() == EDITED,
      f"m12 hand edits of a background tab were wiped: {edited_tab.toPlainText()!r}")
check(edited_tab._speaker_name_map == {"Speaker 0": "Alice"},
      "m12 the edited tab must still learn the new names")
check("Alice" in untouched.toPlainText(),
      f"m12 untouched sibling must be re-rendered: {untouched.toPlainText()!r}")

# --- m13 / m14 / m15: exports -----------------------------------------
out_dir = tempfile.mkdtemp(prefix="dictee-13-export-")
seen = {}


class FakeExportDialog:
    formats = ["text"]

    def __init__(self, tabs_info, current_format, base_name, parent=None,
                 current_tab_index=0):
        self._tabs_info = list(tabs_info)
        self._base = base_name
        seen["base"] = base_name

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


def read_export(ext, title, base):
    """Content of the exported file, or None when it was written under
    another name (which is itself a failure worth recording)."""
    import re as _re
    safe = _re.sub(r'[^\w.-]', '_', title)
    try:
        with open(os.path.join(out_dir, f"{base}-{safe}{ext}"), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


# m13: the name comes from the tab's audio, not the Fichier field.
win._file_input.setText(OTHER)
old = QTextEdit()
old._audio_path = "/home/user/audio/reunion.wav"
old._raw_text = "texte de la reunion"
old._diarize_segments = []
old._was_diarized = False
old.setPlainText("texte de la reunion")
win._tabs.addTab(old, "#11 Transcribe")
win._tabs.setCurrentWidget(old)
FakeExportDialog.formats = ["text"]
win._on_export_current_tab()
check(seen["base"] == "reunion",
      f"m13 export name came from the Fichier field: {seen['base']!r}")

# m14: two tabs with the same title, export the active one.
TITLE = "#12 Diarize -> Espagnol (Google)"
t1 = QTextEdit()
t1._audio_path = WAV
t1._was_diarized = True
t1._diarize_segments = [{"start": 0.0, "end": 1.0, "speaker": "Speaker 0", "text": "premier"}]
t1._raw_text = "premier"
win._tabs.addTab(t1, TITLE)
t2 = QTextEdit()
t2._audio_path = WAV
t2._was_diarized = True
t2._diarize_segments = [{"start": 0.0, "end": 1.0, "speaker": "Speaker 0", "text": "second"}]
t2._raw_text = "second"
win._tabs.addTab(t2, TITLE)
win._tabs.setCurrentWidget(t2)
win._apply_format_to(t2, t2._diarize_segments, t2._raw_text)
win._on_export_current_tab()
got = read_export(".txt", TITLE, "dictee-13-check")
check(got is not None and "second" in got and "premier" not in got,
      f"m14 exported the first namesake tab (or under another name): {got!r}")

# m15: a segment-less tab away from index 0, displayed as JSON.
plain = QTextEdit()
plain._audio_path = WAV
plain._raw_text = "texte simple sans locuteurs"
plain._diarize_segments = []
plain._was_diarized = False
win._tabs.addTab(plain, "#13 Transcribe")
win._tabs.setCurrentWidget(plain)
set_format("json")
win._apply_format_to(plain, [], plain._raw_text)
FakeExportDialog.formats = ["json"]
win._on_export_current_tab()
raw_json = read_export(".json", "#13 Transcribe", "dictee-13-check")
payload = json.loads(raw_json) if raw_json else None
check(payload == [{"text": "texte simple sans locuteurs"}],
      f"m15 JSON export nested the rendered view (or wrong name): {payload!r}")

# --- m7: the OOM retry redoes the same run ----------------------------
scheduled = []


class CapturingTimer(mod.QTimer):
    @staticmethod
    def singleShot(msec, callback):
        scheduled.append(callback)


mod.QTimer = CapturingTimer

win._file_input.setText(WAV)
set_format("text")
win._chk_diarize.setChecked(False)
mod._select_transcribe_cmd = lambda **kw: (None, False, "transcribe")
win._on_transcribe()
oom_tab = win._text_edit
tabs_before = win._tabs.count()
win._start_tab_spinner(oom_tab, "#14 Transcribe")
win._transcription_in_progress = True
win._process = None
win._retry_done = False
win._stdout_buf = QByteArray(b"CUBLAS_STATUS_ALLOC_FAILED while allocating")
win._on_finished(1, 0)
win._file_input.setText(OTHER)
check(bool(scheduled), "m7 no retry scheduled")
if scheduled:
    scheduled[-1]()
    check(win._tabs.count() == tabs_before,
          f"m7 the retry opened another tab ({win._tabs.count()} vs {tabs_before})")
    check(win._text_edit is oom_tab, "m7 the retry landed on a different tab")
    check(getattr(win._text_edit, "_audio_path", None) == WAV,
          f"m7 the retry switched files: {getattr(win._text_edit, '_audio_path', None)!r}")

shutil.rmtree(out_dir, ignore_errors=True)
for p in (WAV, OTHER):
    os.unlink(p)

if FAILED:
    print("ECHECS 1.3:")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print("1.3 BACKPORTS OK")
