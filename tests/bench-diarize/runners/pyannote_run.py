#!/usr/bin/env python3
"""Runner: pyannote.audio pipeline (community-1 or 3.1).
auto or oracle mode (oracle reads num_speakers from the reference RTTM).
Writes <out>/<file-id>.rttm with our stable file-ids.

Usage:
  HF_TOKEN=hf_xxx uv run --with pyannote.audio --with torch python pyannote_run.py \
     --model pyannote/speaker-diarization-community-1 \
     --audio AUDIO_DIR --ref REF_DIR --out OUT_DIR --mode oracle [--device cuda]

Gated models: accept conditions on the HF model page + provide HF_TOKEN.
"""
import argparse
import glob
import os
import sys


def count_ref_speakers(rttm):
    spk = set()
    if not os.path.exists(rttm):
        return 0
    for line in open(rttm):
        f = line.split()
        if f and f[0] == "SPEAKER":
            spk.add(f[7])
    return len(spk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="auto", choices=["auto", "oracle"])
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args()

    import torch
    from pyannote.audio import Pipeline

    # Token resolution order: explicit env, else the cached `huggingface-cli login`
    # token (huggingface_hub reads ~/.cache/huggingface/token automatically when
    # token is None). We never need the raw token in the conversation.
    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    kw = {}
    if tok:
        kw["token"] = tok
    try:
        pipe = Pipeline.from_pretrained(a.model, **kw)               # pyannote 4.x (token=)
    except TypeError:
        # pyannote 3.x uses use_auth_token=
        pipe = Pipeline.from_pretrained(a.model, use_auth_token=(tok or True))
    if pipe is None:
        sys.exit(f"from_pretrained returned None for {a.model} — accept the model "
                 f"conditions on its HF page and run `huggingface-cli login`.")
    pipe.to(torch.device(a.device))

    os.makedirs(a.out, exist_ok=True)
    for wav in sorted(glob.glob(os.path.join(a.audio, "*.wav"))):
        fid = os.path.splitext(os.path.basename(wav))[0]
        kw = {}
        if a.mode == "oracle":
            n = count_ref_speakers(os.path.join(a.ref, fid + ".rttm"))
            if n > 0:
                kw["num_speakers"] = n
        out = pipe(wav, **kw)
        ann = getattr(out, "speaker_diarization", out)  # community-1 wraps; 3.1 returns Annotation
        with open(os.path.join(a.out, fid + ".rttm"), "w") as f:
            for seg, _, spk in ann.itertracks(yield_label=True):
                f.write(f"SPEAKER {fid} 1 {seg.start:.3f} {seg.end - seg.start:.3f} <NA> <NA> {spk} <NA> <NA>\n")
        print("ok", fid, flush=True)


if __name__ == "__main__":
    main()
