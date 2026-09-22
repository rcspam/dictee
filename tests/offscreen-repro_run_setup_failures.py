"""Reproducer (m4 + m5 + m6): three loose ends on the run setup paths.

m4 — when the engine binary is missing, _on_transcribe returns without
stopping the tab spinner, so the title spins forever and Translate stays
greyed out. Two branches: no command at all, and an isolated engine with
no diarize-only fallback.

m5 — self._moss_run is set late in _on_transcribe (after the chunked and
isolated early returns) and never cleared, so the run after a MOSS run
gets no elapsed clock: _start_run_ticker bails out on the stale flag.

m6 — phase 2 giving up on a missing audio file leaves the spinner, the
progress bar and the Cancel button on screen.

The VRAM probe is stubbed out: the real one can stop the user's systemd
ASR services, which a test must never do.
"""
import importlib.util
import os
import subprocess
import sys
import wave

# Keep the real callable: patching mod.subprocess.run rebinds the shared
# module attribute, so calling subprocess.run later would recurse.
_real_run = subprocess.run

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py"
spec = importlib.util.spec_from_file_location("dictee_transcribe", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication, QTextEdit

WAV = "/tmp/dictee-test-run-setup.wav"
w = wave.open(WAV, "wb")
w.setnchannels(1)
w.setsampwidth(2)
w.setframerate(16000)
w.writeframes(b"\x00\x00" * 16000)  # 1 s
w.close()


class _Res:
    def __init__(self, out="", code=0):
        self.stdout = out
        self.stderr = ""
        self.returncode = code


def fake_run(cmd, *a, **kw):
    """Let ffprobe through (real duration), report plenty of free VRAM,
    and refuse anything that would touch the user's system."""
    exe = cmd[0] if isinstance(cmd, (list, tuple)) else str(cmd)
    if exe == "ffprobe":
        return _real_run(cmd, *a, **kw)
    if exe == "nvidia-smi":
        return _Res("99999\n")
    raise AssertionError(f"test tried to run {exe}")


mod.subprocess.run = fake_run

app = QApplication([])
win = mod.TranscribeWindow()
win.show()  # _on_transcribe bails out on an invisible window
win._file_input.setText(WAV)


def run_tab_of(win):
    return win._run_tab


# --- m4: engine binary missing ----------------------------------------
mod._select_transcribe_cmd = lambda **kw: (None, False, "transcribe-diarize")
win._chk_diarize.setChecked(False)
win._on_transcribe()
tab = run_tab_of(win)
assert tab is not None and win._tabs.indexOf(tab) >= 0, "a run tab was created"
assert tab not in win._spinning_tabs, (
    "BUG [missing binary]: the tab spinner spins forever")
assert win._transcription_in_progress is False

# --- m4 bis: isolated engine with no diarize-only fallback ------------
import shutil

_real_which = shutil.which
mod._select_transcribe_cmd = lambda **kw: ("transcribe-diarize", False, None)
mod._diar_multi_available = lambda: False
shutil.which = lambda name: None
win._chk_diarize.setChecked(True)
win._asr_model_combo.setCurrentIndex(win._asr_model_combo.findData("nemotron"))
try:
    win._on_transcribe()
finally:
    shutil.which = _real_which
tab = run_tab_of(win)
assert tab not in win._spinning_tabs, (
    "BUG [no diarize-only]: the tab spinner spins forever")
assert win._transcription_in_progress is False

win._chk_diarize.setChecked(False)
win._asr_model_combo.setCurrentIndex(win._asr_model_combo.findData(""))

# --- m5: a MOSS run must not mute the next run's clock ----------------
# Route to the missing-binary branch again: this case only needs the head
# of _on_transcribe, and must not spawn a real engine.
mod._select_transcribe_cmd = lambda **kw: (None, False, "transcribe")
win._moss_run = True
win._on_transcribe()
assert win._moss_run is False, (
    "BUG: the previous run's MOSS flag survives into the next run")
win._start_run_ticker()
assert getattr(win, "_run_ticker", None) is not None, (
    "BUG: the elapsed clock never starts after a MOSS run")
win._stop_run_ticker()

# --- m6: phase 2 cannot find the audio any more ------------------------
ed = QTextEdit()
win._init_tab_state(ed, None)
win._tabs.addTab(ed, "#9 Diarize")
win._run_tab = ed
win._text_edit = ed
win._transcription_in_progress = True
win._start_tab_spinner(ed, "#9 Diarize")
win._btn_cancel.setVisible(True)
win._progress.setVisible(True)
win._diarize_audio_path = "/tmp/this-file-was-deleted-mid-run.wav"
win._restart_daemon_and_transcribe("[0.00s - 1.00s] Speaker 0: hi")
assert ed not in win._spinning_tabs, (
    "BUG [phase 2, audio gone]: the tab spinner spins forever")
assert not win._btn_cancel.isVisible(), (
    "BUG [phase 2, audio gone]: Cancel stays on screen")
assert not win._progress.isVisible(), (
    "BUG [phase 2, audio gone]: the progress bar stays on screen")
assert win._transcription_in_progress is False

os.unlink(WAV)
print("RUN SETUP FAILURES OK")
