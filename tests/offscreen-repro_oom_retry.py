"""Reproducer (m7): the GPU-OOM retry must redo the SAME run, in the
same tab.

The retry re-entered _on_transcribe from scratch, which (1) created a
second tab, leaving the first one behind with the OOM message, and (2)
re-read the Fichier field — a path edited during the two-second delay
made the retry transcribe a different file.

The VRAM probe is stubbed: the real one can stop the user's systemd ASR
services, which a test must never do.
"""
import importlib.util
import os
import subprocess
import sys
import time
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_real_run = subprocess.run

SRC = "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py"
spec = importlib.util.spec_from_file_location("dictee_transcribe", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtCore import QByteArray
from PyQt6.QtWidgets import QApplication

RUN_WAV = "/tmp/dictee-test-oom-run.wav"
OTHER_WAV = "/tmp/dictee-test-oom-other.wav"
for path in (RUN_WAV, OTHER_WAV):
    w = wave.open(path, "wb")
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
mod._postprocess = lambda text: text

# Capture what the OOM branch schedules instead of waiting 2 s for it —
# and without assuming which callable it is.
scheduled = []


class CapturingTimer(mod.QTimer):
    @staticmethod
    def singleShot(msec, callback):
        scheduled.append(callback)


mod.QTimer = CapturingTimer

# Never spawn a real engine: the retry must reach the routing block and
# stop there, after having decided which tab and which file it uses.
started = []


def fake_select(**kw):
    return (None, False, "transcribe")


mod._select_transcribe_cmd = fake_select

app = QApplication([])
win = mod.TranscribeWindow()
win.show()
win._file_input.setText(RUN_WAV)
win._chk_diarize.setChecked(False)
win._chk_auto_translate.setChecked(False)

# Start a run the normal way, but stop before the engine starts: reuse
# the tab _on_transcribe created and drive _on_finished by hand.
win._on_transcribe()
run_tab = win._run_tab
assert run_tab is not None
tabs_after_start = win._tabs.count()
assert getattr(run_tab, "_audio_path", None) == RUN_WAV, run_tab._audio_path

# Put the window back in the state a real in-flight run is in: the stub
# routing stopped the spinner when it bailed out, a real run keeps it.
win._start_tab_spinner(run_tab, "#1 Transcribe")

# Record the base title the retry starts its spinner with (the stubbed
# routing stops it again right after, so the dict cannot be read later).
spinner_bases = []
_real_start_spinner = win._start_tab_spinner


def recording_start_spinner(widget, base_title):
    spinner_bases.append(base_title)
    _real_start_spinner(widget, base_title)


win._start_tab_spinner = recording_start_spinner

# The engine dies with a CUDA allocation failure.
win._transcription_in_progress = True
win._process = None
win._user_cancelled = False
win._daemon_was_active = False
win._retry_done = False
win._start_time = time.monotonic()
win._stdout_buf = QByteArray(b"CUBLAS_STATUS_ALLOC_FAILED while allocating")
win._on_finished(1, 0)

# Meanwhile the user (or a file-manager drop) changes the Fichier field.
win._file_input.setText(OTHER_WAV)

# The retry fires (the real code schedules it 2 s later).
assert scheduled, "the OOM branch must schedule a retry"
scheduled[-1]()

assert win._tabs.count() == tabs_after_start, (
    f"BUG: the retry created another tab ({win._tabs.count()} vs "
    f"{tabs_after_start}) and orphaned the first one")
assert win._run_tab is run_tab, (
    "BUG: the retry landed on a different tab than the run it retries")
assert getattr(win._run_tab, "_audio_path", None) == RUN_WAV, (
    "BUG: the retry re-read the Fichier field and switched files: "
    f"{win._run_tab._audio_path!r}")
assert spinner_bases == ["#1 Transcribe"], (
    "BUG: the retry stacked a spinner frame onto the tab title: "
    f"{spinner_bases!r}")

# A normal Transcribe click after that still creates a fresh tab.
win._file_input.setText(OTHER_WAV)
win._on_transcribe()
assert win._tabs.count() == tabs_after_start + 1, "a normal run still opens its own tab"
assert win._run_tab is not run_tab
assert getattr(win._run_tab, "_audio_path", None) == OTHER_WAV

for path in (RUN_WAV, OTHER_WAV):
    os.unlink(path)
print("OOM RETRY OK")
