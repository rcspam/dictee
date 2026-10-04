"""dictee-transcribe --file AUDIO --transcript TRANSCRIPT: the live preview of
dictee-meeting-live becomes the meeting's result without a new analysis.

Checks that:
  - _read_diarized_transcript keeps the '[a s - b s] Speaker N: text' lines
    and leaves out the rest (the meeting title);
  - the window opens a diarized result tab with those lines, playing AUDIO,
    and starts no process (nothing is transcribed again);
  - the speaker names given during the meeting (speakers.json) are applied;
  - an empty transcript says so and opens no result.

QSettings and dictee.conf are read from a throwaway XDG_CONFIG_HOME.
Run: python3 tests/offscreen-check_meeting_transcript.py
"""
import importlib.util
import json
import os
import sys
import tempfile
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="dictee-transcript-check-")
# a configured install, or the window opens the first-run dialog and waits
with open(os.path.join(os.environ["XDG_CONFIG_HOME"], "dictee.conf"), "w") as f:
    f.write("DICTEE_SETUP_DONE=true\n")

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", os.path.join(HERE, "..", "dictee-transcribe.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

meeting = tempfile.mkdtemp(prefix="dictee-meeting-")
audio = os.path.join(meeting, "audio.wav")
with wave.open(audio, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(b"\0\0" * 16000 * 12)
transcript = os.path.join(meeting, "transcript-live.md")
with open(transcript, "w", encoding="utf-8") as f:
    f.write("# Réunion du lundi\n\n"
            "[0.500s - 3.200s] Speaker 0: Bonjour à tous.\n"
            "[3.400s - 6.000s] Speaker 1: Bonjour, on commence ?\n"
            "[6.100s - 9.800s] Speaker 0: Oui, le premier point.\n")
with open(os.path.join(meeting, "speakers.json"), "w", encoding="utf-8") as f:
    json.dump({"name_map": {"1": "Alice"},
               "anchors": {"1": [{"start": 3.4, "end": 6.0}]}}, f)

lines = mod._read_diarized_transcript(transcript).splitlines()
assert lines == ["[0.500s - 3.200s] Speaker 0: Bonjour à tous.",
                 "[3.400s - 6.000s] Speaker 1: Bonjour, on commence ?",
                 "[6.100s - 9.800s] Speaker 0: Oui, le premier point."], lines
assert mod._read_diarized_transcript(os.path.join(meeting, "missing.md")) == ""

started = []
real_start = mod.QProcess.start
mod.QProcess.start = lambda self, *a, **k: started.append(a) or real_start(self, *a, **k)


def settle(ms=600):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


win = mod.TranscribeWindow(file_path=audio, transcript=transcript)
win.show()
settle()
tab = win._tabs.currentWidget()
assert getattr(tab, "_was_diarized", False), "the transcript must land as a diarized result"
speakers = [seg["speaker"] for seg in tab._diarize_segments]
assert len(speakers) == 3 and len(set(speakers)) == 2, tab._diarize_segments
assert "premier point" in tab.toPlainText(), tab.toPlainText()
assert tab._audio_path == audio, tab._audio_path
assert not win._transcription_in_progress
assert started == [], f"nothing may be transcribed again: {started}"
assert "Alice" in tab._speaker_name_map.values(), tab._speaker_name_map
win.close()

empty = os.path.join(meeting, "empty.md")
with open(empty, "w", encoding="utf-8") as f:
    f.write("# Réunion vide\n")
win = mod.TranscribeWindow(file_path=audio, transcript=empty)
win.show()
settle()
assert not any(getattr(win._tabs.widget(i), "_was_diarized", False)
               for i in range(win._tabs.count())), "an empty transcript opens no result"
assert started == []
win.close()
print("OK")
