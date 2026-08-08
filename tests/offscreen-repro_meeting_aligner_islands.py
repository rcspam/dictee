"""Reproducer: the live meeting aligner still uses the per-token rule that was
replaced in dictee-transcribe.py back in July (a323876 then d5cafd4).

AlignerWorker._try_align picks, for each token independently, the speaker with
maximum overlap. A diarizer blip -- a fraction of a second wrongly assigned to
another speaker in the middle of somebody's sentence -- is therefore copied
verbatim onto the words, splitting a clause into three lines with a one-word
island in the middle. The file path fixed this by scoring the words as a
SEQUENCE: switching speaker costs switch_penalty seconds unless the previous
word ended a clause or a real silence separates them, so a short island cannot
pay for the round trip.

Fixture below is the minimal discriminating case:
  - speaker 0 talks 0..10 s, uninterrupted, one word every 0.5 s, no punctuation
  - the diarizer inserts a 0.4 s blip for speaker 1 at 4.0..4.4 s
The word at 4.0..4.5 s sits inside the blip (distance 0 to speaker 1, 0.15 s to
speaker 0), so the per-token rule flips it; the sequence rule keeps it, since
flipping there and back costs 3.0 s against a 0.15 s gain.

Run: python3 tests/offscreen-repro_meeting_aligner_islands.py
"""
import importlib.util
import os
import sys
from importlib.machinery import SourceFileLoader

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# dictee-meeting-live has no .py suffix: spec_from_file_location cannot guess
# a loader, so name it explicitly.
_PATH = "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-meeting-live"
spec = importlib.util.spec_from_loader(
    "dictee_meeting_live", SourceFileLoader("dictee_meeting_live", _PATH))
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_meeting_live"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication

app = QApplication([])

# ── Fixture: one continuous 10 s turn, one 0.4 s diarizer blip ────────
WORDS = ["le", "modele", "de", "segmentation", "ne", "voit", "pas", "le",
         "changement", "de", "voix", "sur", "cette", "zone", "precise",
         "mais", "il", "insere", "un", "ilot"]
tokens = [{"text": w, "start_s": 0.5 * i, "end_s": 0.5 * (i + 1)}
          for i, w in enumerate(WORDS)]
segments = [
    {"start_s": 0.0, "end_s": 4.0, "speaker_id": 0},
    {"start_s": 4.0, "end_s": 4.4, "speaker_id": 1},   # the blip
    {"start_s": 4.4, "end_s": 10.0, "speaker_id": 0},
]

captured = []
worker = mod.AlignerWorker()
worker.aligned.connect(lambda cid, lines: captured.append((cid, lines)))
worker.chunk_offset[0] = 0.0
worker.on_transcribed(0, tokens)
worker.on_diarized(0, segments)

assert captured, "aligner emitted nothing"
_cid, lines = captured[0]
speakers = [ln["speaker"] for ln in lines]
print(f"lines={len(lines)} speakers={speakers}")
for ln in lines:
    print(f"  [{ln['start_s']:5.2f} - {ln['end_s']:5.2f}] S{ln['speaker']}: {ln['text']}")

assert len(lines) == 1, (
    f"a 0.4 s diarizer blip split a continuous turn into {len(lines)} lines "
    f"(speakers {speakers}); the sequence-aware fusion must absorb it")
assert lines[0]["speaker"] == 0, f"whole turn should stay on speaker 0, got {speakers}"
assert lines[0]["text"] == " ".join(WORDS), "no word may be lost or reordered"

# ── Guard: a REAL turn change must still switch ───────────────────────
# Same shape, but speaker 1 genuinely holds 4.0..7.0 s (6 words): the gain now
# far exceeds the 3.0 s round trip, so the fusion must produce three lines.
segments_real = [
    {"start_s": 0.0, "end_s": 4.0, "speaker_id": 0},
    {"start_s": 4.0, "end_s": 7.0, "speaker_id": 1},
    {"start_s": 7.0, "end_s": 10.0, "speaker_id": 0},
]
captured.clear()
worker.chunk_offset[1] = 0.0
worker.on_transcribed(1, tokens)
worker.on_diarized(1, segments_real)
_cid, lines2 = captured[0]
speakers2 = [ln["speaker"] for ln in lines2]
print(f"real-turn case: lines={len(lines2)} speakers={speakers2}")
assert speakers2 == [0, 1, 0], (
    f"a genuine 3 s interruption must still switch speakers, got {speakers2}")

print("OK")
