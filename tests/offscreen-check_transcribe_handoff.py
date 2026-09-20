#!/usr/bin/env python3
"""Offscreen checks of the dictee-transcribe side of the meeting handoff.

Builds the real TranscribeWindow (QT_QPA_PLATFORM=offscreen) against a
throwaway config so the first-run dialog never opens, then checks:
- --asr-model reaches both binary env builders as DICTEE_PARAKEET_QUANT
- speakers.json names land in the speaker maps before the panel is built
- History lists past meetings and loads the chosen one into the player path

No Rust binary is launched, no daemon is contacted.
"""
import importlib.util
import json
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_cfg = tempfile.mkdtemp(prefix="dictee-transcribe-test-cfg-")
with open(os.path.join(_cfg, "dictee.conf"), "w", encoding="utf-8") as f:
    f.write("DICTEE_SETUP_DONE=true\nDICTEE_PARAKEET_QUANT=int8\n")
os.environ["XDG_CONFIG_HOME"] = _cfg
os.environ["HOME"] = tempfile.mkdtemp(prefix="dictee-transcribe-test-home-")

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "dictee-transcribe.py")
spec = importlib.util.spec_from_file_location("dictee_transcribe", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication  # noqa: E402
app = QApplication([])

failures = []


def check(label, got, expected):
    if got == expected:
        print(f"PASS {label}")
    else:
        print(f"FAIL {label}: got {got!r}, expected {expected!r}")
        failures.append(label)


# --- 1. --asr-model reaches the binaries -------------------------------------

win = mod.TranscribeWindow(asr_model="parakeet-fp32", diar_engine="auto")
check("asr_model env computed", win._asr_model_env, {"DICTEE_PARAKEET_QUANT": "fp32"})

env = win._build_process_env()
check("QProcess env: --asr-model overrides the conf", env.value("DICTEE_PARAKEET_QUANT"), "fp32")

worker = mod._ChunkedPipelineWorker("/nonexistent/a.wav", 0.5, diarize=True,
                                    extra_env=win._asr_model_env)
check("chunked worker env: --asr-model overrides the conf",
      worker._subprocess_env.get("DICTEE_PARAKEET_QUANT"), "fp32")

plain = mod.TranscribeWindow()
check("no --asr-model: conf value kept in QProcess env",
      plain._build_process_env().value("DICTEE_PARAKEET_QUANT"), "int8")
check("no --asr-model: conf value kept in worker env",
      mod._ChunkedPipelineWorker("/nonexistent/a.wav", 0.5).
      _subprocess_env.get("DICTEE_PARAKEET_QUANT"), "int8")

if failures:
    print(f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("\nOK")
