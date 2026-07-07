#!/usr/bin/env python3
"""Convert an argmaxinc HuggingFace diarization dataset (parquet with
audio / timestamps_start / timestamps_end / speakers columns) into:
  <wavdir>/<file-id>.wav   (16 kHz mono via ffmpeg, no torch/torchcodec needed)
  <refdir>/<file-id>.rttm  (one SPEAKER line per turn)

Audio is read with decode=False (raw bytes) then piped through ffmpeg, so we avoid
the datasets 'torchcodec' decoding dependency entirely.

Usage:
  uv run --with datasets python hf2rttm.py \
      --dataset argmaxinc/aishell-4 --split test --wavdir AUDIO --refdir REF
file-ids are zero-padded indices, stable across runs (dataset order is fixed).
"""
import argparse
import os
import subprocess
import tempfile


def to16k_from_bytes(raw, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        tf.write(raw)
        tmp = tf.name
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", tmp,
             "-ac", "1", "-ar", "16000", "-f", "wav", dst],
            check=True,
        )
    finally:
        os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--wavdir", required=True)
    ap.add_argument("--refdir", required=True)
    ap.add_argument("--prefix", default="")
    args = ap.parse_args()

    from datasets import Audio, load_dataset

    os.makedirs(args.wavdir, exist_ok=True)
    os.makedirs(args.refdir, exist_ok=True)
    ds = load_dataset(args.dataset, split=args.split)
    ds = ds.cast_column("audio", Audio(decode=False))  # raw bytes, no torchcodec

    n = 0
    for i, ex in enumerate(ds):
        fid = f"{args.prefix}{i:05d}"
        wav = os.path.join(args.wavdir, fid + ".wav")
        a = ex["audio"]
        raw = a.get("bytes")
        if raw is None and a.get("path") and os.path.exists(a["path"]):
            with open(a["path"], "rb") as fh:
                raw = fh.read()
        if raw is None:
            print(f"skip {fid}: no audio bytes")
            continue
        to16k_from_bytes(raw, wav)
        with open(os.path.join(args.refdir, fid + ".rttm"), "w") as f:
            for s, e, spk in zip(ex["timestamps_start"], ex["timestamps_end"], ex["speakers"]):
                dur = float(e) - float(s)
                if dur > 0:
                    f.write(f"SPEAKER {fid} 1 {float(s):.3f} {dur:.3f} <NA> <NA> {spk} <NA> <NA>\n")
        n += 1
        if n % 5 == 0:
            print(f"  {n} files...", flush=True)
    print(f"wrote {n} files from {args.dataset}:{args.split}")


if __name__ == "__main__":
    main()
