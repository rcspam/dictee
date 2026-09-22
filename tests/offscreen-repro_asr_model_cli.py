"""Reproducer (m1): --asr-model with a sized spec was silently ignored.

The CLI documents whisper-tiny/-small/-medium and whisper-rust-<size>,
but the engine combo only carries the unsized entries, so findData()
returned -1, nothing was selected, and the run read the combo: the
default F9 daemon transcribed instead of the requested model.
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

from PyQt6.QtWidgets import QApplication

app = QApplication([])

# A sized spec the combo does not carry.
win = mod.TranscribeWindow(asr_model="whisper-medium")
assert win._asr_model_combo.currentData() == "whisper-medium", (
    "BUG: sized --asr-model spec ignored, combo left on "
    f"{win._asr_model_combo.currentData()!r}")
recipe = mod.asr_spec_to_daemon(win._asr_model_combo.currentData())
assert recipe["backend"] == "whisper", recipe
assert recipe["env"]["DICTEE_WHISPER_MODEL"] == "medium", recipe

# Same for a sized whisper-rust spec.
win2 = mod.TranscribeWindow(asr_model="whisper-rust-small")
assert win2._asr_model_combo.currentData() == "whisper-rust-small", (
    f"BUG: sized whisper-rust spec ignored: {win2._asr_model_combo.currentData()!r}")

# An unsized spec still selects the existing combo entry (no duplicate).
win3 = mod.TranscribeWindow(asr_model="nemotron")
assert win3._asr_model_combo.currentData() == "nemotron"
assert [win3._asr_model_combo.itemData(i)
        for i in range(win3._asr_model_combo.count())].count("nemotron") == 1

# Garbage must not crash the window and must leave the default in place.
win4 = mod.TranscribeWindow(asr_model="not-a-model")
assert win4._asr_model_combo.currentData() == "", (
    f"unknown spec must fall back to the F9 default: "
    f"{win4._asr_model_combo.currentData()!r}")

print("ASR MODEL CLI OK")
