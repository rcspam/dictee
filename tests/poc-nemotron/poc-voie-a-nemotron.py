#!/usr/bin/env python3
"""Voie A with Nemotron 3.5 instead of Canary.
Sortformer segments the audio (CPU), the timeline is cleaned (drop micro,
merge same-speaker, resolve overlaps), then Nemotron transcribes each clean
segment. The Nemotron model is loaded ONCE (nemo-fr takes all segments).
Usage: poc-voie-a-nemotron.py <audio.wav> [lang=fr-FR]"""
import os, sys, subprocess, tempfile

AUDIO = os.path.abspath(sys.argv[1])
LANG = sys.argv[2] if len(sys.argv) > 2 else "fr-FR"
HERE = os.path.dirname(os.path.abspath(__file__))
NEMO_BIN = os.path.join(HERE, "target/release/nemo-fr")
MODEL_DIR = os.path.join(HERE, "nemotron_multi")
SORTFORMER_DIR = "/usr/share/dictee/sortformer"
MIN_DUR, MERGE_GAP = 1.0, 0.6

# 1. Sortformer (CPU) -> raw segments
env = dict(os.environ, DICTEE_FORCE_CPU="1")
r = subprocess.run(["diarize-only", AUDIO, SORTFORMER_DIR],
                   capture_output=True, text=True, env=env)
raw = []
for ln in r.stdout.splitlines():
    p = ln.split()
    if len(p) >= 3:
        try:
            raw.append((float(p[0]), float(p[1]), int(p[2])))
        except ValueError:
            pass


def clean(segs, min_dur, merge_gap):
    segs = [(a, b, s) for (a, b, s) in segs if b - a >= min_dur]
    segs.sort()
    out = []
    for (a, b, s) in segs:
        if out:
            pa, pb, ps = out[-1]
            if a < pb:
                if s == ps:
                    out[-1] = (pa, max(pb, b), ps)
                    continue
                a = pb
                if b - a < min_dur:
                    continue
            if s == ps and a - pb <= merge_gap:
                out[-1] = (pa, b, ps)
                continue
        out.append((a, b, s))
    return out


segs = clean(raw, MIN_DUR, MERGE_GAP)
print(f"Sortformer: {len(raw)} raw -> {len(segs)} clean segments")

# 2. extract each clean segment to a 16k mono wav
tmp = tempfile.mkdtemp()
wavs = []
for i, (a, b, spk) in enumerate(segs):
    w = f"{tmp}/seg_{i}.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", AUDIO,
                    "-ss", f"{a}", "-t", f"{b - a}", "-ar", "16000", "-ac", "1", w],
                   stdin=subprocess.DEVNULL)
    wavs.append(w)

# 3. one nemo-fr call: model loaded once, one line per segment
denv = dict(os.environ, NEMO_MODEL_DIR=MODEL_DIR)
res = subprocess.run([NEMO_BIN, LANG] + wavs, capture_output=True, text=True, env=denv)
texts = res.stdout.splitlines()
if res.returncode != 0:
    print("nemo-fr stderr:", res.stderr[-500:])

print(f"\n=== VOIE A — Nemotron 3.5 ({LANG}) per Sortformer segment ===")
for (a, b, spk), txt in zip(segs, texts):
    print(f"[{a:7.2f} - {b:7.2f}] SPK{spk}: {txt}")

subprocess.run(["rm", "-rf", tmp])
