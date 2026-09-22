"""Headless smoke test for the tab-owned-state refactor.

Constructs TranscribeWindow offscreen, checks the projections, the
per-tab init, a simulated tab switch and the AttributeError guard on
the getter-only properties.
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

from PyQt6.QtWidgets import QApplication, QTextEdit

app = QApplication([])
win = mod.TranscribeWindow()

# 1. Initial tab got the canonical state
ed0 = win._tabs.widget(0)
assert ed0._raw_text == "" and ed0._diarize_segments == [], "init_tab_state missing on initial tab"
assert ed0._was_diarized is False and ed0._speaker_name_map == {}
assert ed0._audio_duration == 0.0 and ed0._status_text == ""

# 2. Projections read the active tab
assert win._raw_text == "" and win._segments == []
assert win._was_diarized is False and win._speaker_name_map == {}

# 3. Getter-only: shared writes must raise
for attr in ("_raw_text", "_segments", "_was_diarized", "_speaker_name_map"):
    try:
        setattr(win, attr, "x")
    except AttributeError:
        pass
    else:
        raise AssertionError(f"setting win.{attr} did not raise")

# 4. Simulated finished tab + switch: projections follow the active tab
ed1 = QTextEdit()
win._init_tab_state(ed1, "/tmp/fake.wav")
ed1._raw_text = "hello"
ed1._was_diarized = True
ed1._diarize_segments = [{"start": 0.0, "end": 1.0, "speaker": "Speaker 0", "text": "hello"}]
ed1._speaker_name_map = {"Speaker 0": "Alice"}
win._tabs.addTab(ed1, "t1")
win._tabs.setCurrentWidget(ed1)
assert win._raw_text == "hello" and win._was_diarized is True
assert win._segments[0]["speaker"] == "Speaker 0"
assert win._speaker_name_map == {"Speaker 0": "Alice"}
win._tabs.setCurrentWidget(ed0)
assert win._raw_text == "" and win._was_diarized is False and win._segments == []

# 5. _run_status stores on the run tab (fallback path, no run yet)
win._run_status("testing")
assert win._text_edit._status_text == "testing"

print("SMOKE OK")
