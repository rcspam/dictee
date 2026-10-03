#!/usr/bin/env python3
"""Numerical reference for src/nemotron3.rs (Nemotron 3 Diarization, ONNX export).

A numpy re-implementation of the host-side logic of transformers'
Nemotron3DiarizationForAudioFrameClassification (offline mode),
Nemotron3DiarizationSpeakerCache and NemotronAsrStreamingFeatureExtractor
(transformers commit 0a896aa41b, Apache-2.0). The ONNX graph only does the
feature stacking, the encoder and the head.

Run with uv, nothing to install:

  uv run --with numpy --with onnxruntime --with librosa --with soundfile \
      python tests/nemotron3-ref/reference.py dump --model DIR/model.onnx \
      --out REF_DIR [--excerpt-seconds 65] audio.wav

  uv run --with numpy python tests/nemotron3-ref/reference.py compress-fixture \
      tests/nemotron3-fixtures/compress.json

`dump` writes, for the excerpt and for the whole file: <name>.mel.f32
(frames x 128), <name>.probs.f32 (frames x 8, sigmoid of the logits),
<name>.json (frame counts) and <name>.rttm. The .f32 files are raw
little-endian float32, row-major.
"""
import argparse
import json
import math
import os

import numpy as np

SR = 16000
N_FFT = 512
WIN = 400
HOP = 160
N_MELS = 128
PREEMPH = 0.97
GUARD = 2.0 ** -24
SUB = 8
NSPK = 8
HIDDEN = 512

# streaming_config of config.json
SPKCACHE_LEN = 264
SIL_FRAMES = 1
PRED_THR = 0.25
LATEST_BOOST = 0.05
MIN_POS_RATE = 0.5
STRONG_RATE = 0.75
WEAK_RATE = 1.5

# offline mode of config.json, in encoder frames (80 ms)
CHUNK_LEN, RIGHT_CONTEXT, FIFO_LEN, UPDATE_PERIOD = 340, 40, 40, 300


def mel_features(audio):
    """NemotronAsrStreamingFeatureExtractor, offline path (center=True)."""
    import librosa

    melfb = librosa.filters.mel(sr=SR, n_fft=N_FFT, n_mels=N_MELS, fmin=0.0,
                                fmax=SR / 2, norm="slaney").astype(np.float32)
    # torch.hann_window(400, periodic=False), zero-padded to n_fft and centered
    window = np.zeros(N_FFT, dtype=np.float32)
    off = (N_FFT - WIN) // 2
    window[off:off + WIN] = np.hanning(WIN).astype(np.float32)

    x = audio.astype(np.float32)
    n = len(x)
    x = np.concatenate([x[:1], x[1:] - PREEMPH * x[:-1]])
    xp = np.pad(x, (N_FFT // 2, N_FFT // 2))
    n_frames = 1 + (len(xp) - N_FFT) // HOP
    feats = np.empty((n_frames, N_MELS), dtype=np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(xp, N_FFT)[::HOP]
    for b in range(0, n_frames, 20000):
        blk = frames[b:b + 20000] * window
        pw = np.abs(np.fft.rfft(blk, axis=1)) ** 2
        feats[b:b + 20000] = np.log(pw.astype(np.float32) @ melfb.T + GUARD)
    valid = n // HOP
    feats[valid:] = 0.0
    return feats, valid


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class SpeakerCache:
    def __init__(self):
        budget = SPKCACHE_LEN // NSPK - SIL_FRAMES
        self.min_pos = math.floor(budget * MIN_POS_RATE)
        self.n_strong = math.floor(budget * STRONG_RATE)
        self.n_weak = math.floor(budget * WEAK_RATE)
        self.embeds = np.zeros((0, HIDDEN), np.float32)
        self.probs = np.zeros((0, NSPK), np.float32)
        self.fifo = np.zeros((0, HIDDEN), np.float32)
        self.is_compressed = False

    def get_embeds(self):
        return np.concatenate([self.embeds, self.fifo], axis=0)

    def frame_scores(self, probs):
        lp = np.log(np.maximum(probs, PRED_THR))
        lc = np.log(np.maximum(1.0 - probs, PRED_THR))
        scores = lp - lc + lc.sum(axis=-1, keepdims=True) - math.log(0.5)
        is_speech = probs > 0.5
        scores = np.where(is_speech, scores, -np.inf)
        is_pos = scores > 0
        enough = is_pos.sum(axis=0, keepdims=True) >= self.min_pos
        return np.where(~is_pos & is_speech & enough, -np.inf, scores).astype(np.float32)

    @staticmethod
    def boost(scores, k, boost):
        k = min(k, scores.shape[0])
        idx = np.argpartition(-scores, k - 1, axis=0)[:k]  # top-k per speaker
        out = scores.copy()
        for s in range(scores.shape[1]):
            out[idx[:, s], s] += boost
        return out

    def compress_indices(self, probs):
        """Frame indices kept by the compression, len(probs) standing for the silence slot."""
        n, ns = probs.shape
        scores = self.frame_scores(probs)
        scores[SPKCACHE_LEN:] += LATEST_BOOST
        scores = self.boost(scores, self.n_strong, -2.0 * math.log(0.5))
        scores = self.boost(scores, self.n_weak, -math.log(0.5))
        scores = np.concatenate([scores, np.full((SIL_FRAMES, ns), np.inf, np.float32)], axis=0)
        n_scored = n + SIL_FRAMES
        sentinel = n_scored * ns
        flat = scores.T.reshape(-1)  # speaker-major, like transpose(1, 2)
        top = np.argpartition(-flat, SPKCACHE_LEN - 1)[:SPKCACHE_LEN]
        top = np.where(flat[top] == -np.inf, sentinel, top)
        top = np.sort(top)
        return np.where(top == sentinel, n, np.minimum(top % n_scored, n))

    def compress(self, embeds, probs, sil):
        fidx = self.compress_indices(probs)
        embeds = np.concatenate([embeds, sil[None, :]], axis=0)
        probs = np.concatenate([probs, np.zeros((1, NSPK), np.float32)], axis=0)
        return embeds[fidx], probs[fidx]

    def update(self, step_embeds, step_logits, sil, n_chunk, step_mask):
        n_cache, n_fifo = self.embeds.shape[0], self.fifo.shape[0]
        p = sigmoid(step_logits)
        probs = p.reshape(-1, SUB, NSPK).mean(axis=1) * step_mask[:, None]
        start = n_cache + n_fifo
        fifo = np.concatenate([self.fifo, step_embeds[start:start + n_chunk]], axis=0)
        nf = fifo.shape[0]
        popped = 0 if nf <= FIFO_LEN else min(max(UPDATE_PERIOD, nf - FIFO_LEN), nf)
        if popped:
            fifo_probs = probs[n_cache:n_cache + nf]
            stored = self.probs[:n_cache] if self.is_compressed else probs[:n_cache]
            c_emb = np.concatenate([self.embeds, fifo[:popped]], axis=0)
            c_prb = np.concatenate([stored, fifo_probs[:popped]], axis=0)
            fifo = fifo[popped:]
            if c_emb.shape[0] > SPKCACHE_LEN:
                c_emb, c_prb = self.compress(c_emb, c_prb, sil)
                self.is_compressed = True
            self.embeds, self.probs = c_emb, c_prb
        self.fifo = fifo


def diarize(sess, feats, valid):
    t_mel = feats.shape[0]
    n_emb = -(-t_mel // SUB)
    emb_mask = (np.arange(n_emb) * SUB < valid).astype(np.int64)
    cache = SpeakerCache()
    sil = None
    out = []
    for start in range(0, n_emb, CHUNK_LEN):
        end = min(start + CHUNK_LEN, n_emb)
        stop = min(end + RIGHT_CONTEXT, n_emb)
        cached = cache.get_embeds()
        step_mask = np.concatenate([np.ones(cached.shape[0], np.int64), emb_mask[start:stop]])
        logits, chunk_embeds, silence = sess.run(["logits", "chunk_embeds", "silence_embeds"], {
            "input_features": feats[start * SUB:stop * SUB][None],
            "cached_embeds": cached[None].astype(np.float32),
            "attention_mask": step_mask[None],
        })
        if sil is None:
            sil = silence.reshape(-1).astype(np.float32)
        logits = logits[0]
        step_embeds = np.concatenate([cached, chunk_embeds[0]], axis=0)
        cache.update(step_embeds, logits, sil, end - start, step_mask.astype(np.float32))
        c = cached.shape[0]
        out.append(logits[c * SUB:(c + end - start) * SUB])
    return sigmoid(np.concatenate(out, axis=0)[:t_mel]).astype(np.float32)


def segments(probs, valid, thr=0.5):
    """transformers' extract_speaker_dict: speaker activity at 10 ms."""
    active = probs > thr
    active[valid:] = False
    a = active.astype(np.int8)
    z = np.zeros((1, a.shape[1]), np.int8)
    ch = np.diff(np.concatenate([z, a, z], axis=0), axis=0)
    segs = []
    for s in range(a.shape[1]):
        st = np.nonzero(ch[:, s] == 1)[0]
        en = np.nonzero(ch[:, s] == -1)[0]
        segs += [(b * HOP / SR, e * HOP / SR, s) for b, e in zip(st, en)]
    segs.sort(key=lambda g: (g[0], g[2]))
    return segs


def dump(args):
    import onnxruntime as ort
    import soundfile as sf

    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    audio, sr = sf.read(args.audio, dtype="float32", always_2d=True)
    assert sr == SR, sr
    audio = audio.mean(axis=1)
    os.makedirs(args.out, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.audio))[0]
    jobs = [(f"{base}.excerpt", audio[:int(args.excerpt_seconds * SR)]), (base, audio)]
    for name, x in jobs:
        feats, valid = mel_features(x)
        probs = diarize(sess, feats, valid)
        feats.tofile(os.path.join(args.out, name + ".mel.f32"))
        probs.tofile(os.path.join(args.out, name + ".probs.f32"))
        with open(os.path.join(args.out, name + ".json"), "w") as f:
            json.dump({"samples": len(x), "frames": feats.shape[0], "valid": valid}, f)
        with open(os.path.join(args.out, name + ".rttm"), "w") as f:
            for b, e, s in segments(probs, valid):
                f.write(f"SPEAKER {base} 1 {b:.3f} {e - b:.3f} <NA> <NA> spk{s} <NA> <NA>\n")
        print(f"{name}: {len(x) / SR:.1f} s, {feats.shape[0]} frames, "
              f"speakers {sorted({s for _, _, s in segments(probs, valid)})}")


def compress_fixture(args):
    """Random but speech-like probabilities, and the frames the compression keeps."""
    rng = np.random.default_rng(20261003)
    n = 330
    logits = rng.normal(-3.0, 1.5, size=(n, NSPK))
    # a few speakers talk in turns, two of them overlap now and then
    for s, (a, b) in enumerate([(0, 120), (100, 210), (200, 330), (40, 70), (250, 262)]):
        logits[a:b, s] = rng.normal(3.0, 1.5, size=b - a)
    probs = sigmoid(logits).astype(np.float32)
    keep = SpeakerCache().compress_indices(probs)
    with open(args.path, "w") as f:
        # float(v) is the exact value of the float32, so Rust reads back the same bits
        json.dump({"probs": [[float(v) for v in row] for row in probs],
                   "keep": [int(i) for i in keep]}, f)
    print(f"{args.path}: {n} frames, {int((keep == n).sum())} silence slots")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--model", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--excerpt-seconds", type=float, default=65.0)
    d.add_argument("audio")
    c = sub.add_parser("compress-fixture")
    c.add_argument("path")
    args = ap.parse_args()
    dump(args) if args.cmd == "dump" else compress_fixture(args)


if __name__ == "__main__":
    main()
