#!/usr/bin/env python3
"""Option α: Nemotron STREAMING (per-chunk text + time window) aligned to
Sortformer speakers by time-overlap — since Nemotron has no word timestamps,
we attribute each 560 ms chunk to the dominant speaker on its window, then
group consecutive same-speaker chunks. Compare with β (Voie A) and the others.
Usage: poc-alpha-stream-pos.py <audio-16k-mono.wav> [lang=fr-FR]"""
import os, re, sys, subprocess

AUDIO = os.path.abspath(sys.argv[1])
LANG = sys.argv[2] if len(sys.argv) > 2 else "fr-FR"
HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "target/release/nemo-stream-pos")
MODEL = os.path.join(HERE, "nemotron_multi")
SORT = "/usr/share/dictee/sortformer"

# 1. Sortformer segments (CPU) — same diarization as the other tests
env = dict(os.environ, DICTEE_FORCE_CPU="1")
r = subprocess.run(["diarize-only", AUDIO, SORT], capture_output=True, text=True, env=env)
segs = []
for ln in r.stdout.splitlines():
    p = ln.split()
    if len(p) >= 3:
        try:
            segs.append((float(p[0]), float(p[1]), int(p[2])))
        except ValueError:
            pass


def spk_at(a, b):
    best, bestov = None, 0.0
    for (s0, s1, spk) in segs:
        ov = min(b, s1) - max(a, s0)
        if ov > bestov:
            bestov, best = ov, spk
    return best


# 2. Nemotron streaming, positional (CPU; set NEMO_CUDA=1 in env for GPU)
res = subprocess.run([BIN, LANG, AUDIO], capture_output=True, text=True,
                     env=dict(os.environ, NEMO_MODEL_DIR=MODEL))
chunks = []
for ln in res.stdout.splitlines():
    if "\t" in ln:
        pos, txt = ln.split("\t", 1)
        a, b = pos.split()
        chunks.append((float(a), float(b), txt))

print(f"Sortformer: {len(segs)} segments; Nemotron stream chunks: {len(chunks)}")

# 3. assign each chunk to dominant speaker, group consecutive same-speaker
groups = []  # [spk, start, end, [texts]]
for (a, b, txt) in chunks:
    spk = spk_at(a, b)
    if groups and groups[-1][0] == spk:
        groups[-1][2] = b
        groups[-1][3].append(txt)
    else:
        groups.append([spk, a, b, [txt]])

print(f"\n=== OPTION α — Nemotron STREAMING aligned by position ({LANG}) ===")
for (spk, start, end, texts) in groups:
    # Recolle: concat chunks WITHOUT adding spaces (SentencePiece spaces are
    # already in each chunk), then collapse any double spaces.
    txt = re.sub(r"\s+", " ", "".join(texts)).strip()
    print(f"[{start:7.2f} - {end:7.2f}] SPK{spk}: {txt}")
