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

# --- 2. speakers.json fills the maps in both finishers ------------------------

_meeting = tempfile.mkdtemp(prefix="dictee-meeting-")
_audio = os.path.join(_meeting, "audio.wav")
open(_audio, "wb").close()
with open(os.path.join(_meeting, "speakers.json"), "w", encoding="utf-8") as f:
    json.dump({"name_map": {"0": "Alice", "1": "Bob"},
               "anchors": {"0": [{"start": 0.5, "end": 4.0}],
                           "1": [{"start": 6.0, "end": 9.0}]}}, f)

SEGS = [{"speaker": "Speaker 0", "start": 0.0, "end": 5.0, "text": "a"},
        {"speaker": "Speaker 1", "start": 5.0, "end": 10.0, "text": "b"}]

w = mod.TranscribeWindow(file_path=_audio)
check("speakers.json loaded at construction",
      (w._pending_speakers_data or {}).get("name_map"), {"0": "Alice", "1": "Bob"})

w._was_diarized = True
w._segments = list(SEGS)
w._speaker_name_map = {}
w._text_edit._speaker_name_map = {}
w._apply_pending_speakers()
check("names applied to the window map", w._speaker_name_map, {"Speaker 0": "Alice", "Speaker 1": "Bob"})
check("names applied to the target tab map", w._text_edit._speaker_name_map, {"Speaker 0": "Alice", "Speaker 1": "Bob"})
check("consumed once", w._pending_speakers_data, None)

w._speaker_name_map = {}
w._apply_pending_speakers()
check("second call is a no-op", w._speaker_name_map, {})

w2 = mod.TranscribeWindow(file_path=_audio)
w2._was_diarized = False
w2._segments = []
w2._apply_pending_speakers()
check("plain (non diarized) run: nothing applied, data kept for a later diarized run",
      (w2._pending_speakers_data or {}).get("name_map"), {"0": "Alice", "1": "Bob"})

# Both finishers reset the maps then build the panel: the apply call must sit
# between the two. Read the source rather than run a fake transcription.
src = open(SCRIPT, encoding="utf-8").read()
for fn in ("_finish_transcription", "_on_finished"):
    body = src.split(f"    def {fn}(")[1].split("\n    def ")[0]
    reset = body.find("self._text_edit._speaker_name_map = {}")
    apply_ = body.find("self._apply_pending_speakers()")
    refresh = body.find("self._refresh_rename_panel_for_target()", reset)
    check(f"{fn}: apply sits after the reset and before the panel refresh",
          reset != -1 and reset < apply_ < refresh, True)

# --- 3. History picks a meeting and loads it like a drop would ------------------

_hist = tempfile.mkdtemp(prefix="dictee-history-")
os.makedirs(os.path.join(_hist, "2026-09-20_15-44"))
_hist_audio = os.path.join(_hist, "2026-09-20_15-44", "audio.wav")
open(_hist_audio, "wb").close()
with open(os.path.join(_hist, "2026-09-20_15-44", "meeting.meta.json"), "w") as f:
    json.dump({"title": "Weekly"}, f)
with open(os.path.join(_hist, "2026-09-20_15-44", "speakers.json"), "w") as f:
    json.dump({"name_map": {"0": "Carol"}, "anchors": {"0": [{"start": 0.0, "end": 1.0}]}}, f)
os.environ["DICTEE_MEETING_DIR"] = _hist

h = mod.TranscribeWindow()
check("History button exists", hasattr(h, "_btn_history"), True)
check("no file at start: no pending speakers", h._pending_speakers_data, None)

loaded = []
h._load_audio = lambda p: loaded.append(p)


class _Pick:
    @staticmethod
    def getItem(parent, title, label, items, current=0, editable=True):
        return items[0], True


mod.QInputDialog = _Pick
h._on_open_history()
check("History sets the file field", h._file_input.text(), _hist_audio)
check("History loads the player", loaded, [_hist_audio])
check("History picks up the meeting's speakers.json",
      (h._pending_speakers_data or {}).get("name_map"), {"0": "Carol"})


class _Cancel:
    @staticmethod
    def getItem(parent, title, label, items, current=0, editable=True):
        return "", False


mod.QInputDialog = _Cancel
h._file_input.setText("")
loaded.clear()
h._on_open_history()
check("cancelled dialog changes nothing", (h._file_input.text(), loaded), ("", []))

shown = []


class _Msg:
    """Stands in for the module-level QMessageBox name (never patch the Qt
    class itself): records the information box instead of showing it."""
    @staticmethod
    def information(parent, title, text, *a, **k):
        shown.append(text)


_real_msgbox = mod.QMessageBox
mod.QMessageBox = _Msg
os.environ["DICTEE_MEETING_DIR"] = tempfile.mkdtemp(prefix="dictee-history-empty-")
h._on_open_history()
mod.QMessageBox = _real_msgbox
check("no meeting: one information box", len(shown), 1)

if failures:
    print(f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("\nOK")
