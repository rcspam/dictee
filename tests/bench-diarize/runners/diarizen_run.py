#!/usr/bin/env python3
"""Runner: DiariZen (BUT). BENCHMARK-ONLY — weights are CC BY-NC 4.0 (non-commercial),
NOT shippable in dictee (GPL). Used here purely as a quality ceiling / reference.
auto mode only: the high-level DiariZenPipeline does not expose num_speakers.

Usage (in the diarizen conda env):
  python diarizen_run.py --audio AUDIO_DIR --out OUT_DIR \
      [--model BUT-FIT/diarizen-wavlm-large-s80-md-v2]
"""
import argparse
import glob
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="BUT-FIT/diarizen-wavlm-large-s80-md-v2")
    a = ap.parse_args()

    # torch >= 2.6 flipped torch.load's default to weights_only=True, which
    # rejects DiariZen's pickled checkpoints. Trusted source (BUT/Brno,
    # benchmark-only) — restore the old behaviour for this process.
    import torch
    _torch_load = torch.load

    def _load_full(*args, **kwargs):
        # Force, don't setdefault: lightning_fabric's cloud_io._load passes
        # weights_only=True explicitly.
        kwargs["weights_only"] = False
        return _torch_load(*args, **kwargs)

    torch.load = _load_full

    from diarizen.pipelines.inference import DiariZenPipeline

    os.makedirs(a.out, exist_ok=True)
    pipe = DiariZenPipeline.from_pretrained(a.model)
    # The model's TOML ships batch_size=32 (WavLM-large): OOMs on 8 GB VRAM.
    # Shrink the inference batches post-construction (quality-neutral).
    for attr in ("_segmentation", "_embedding"):
        obj = getattr(pipe, attr, None)
        if obj is not None and hasattr(obj, "batch_size"):
            obj.batch_size = 8
    for wav in sorted(glob.glob(os.path.join(a.audio, "*.wav"))):
        fid = os.path.splitext(os.path.basename(wav))[0]
        ann = pipe(wav, sess_name=fid)
        with open(os.path.join(a.out, fid + ".rttm"), "w") as f:
            for seg, _, spk in ann.itertracks(yield_label=True):
                f.write(f"SPEAKER {fid} 1 {seg.start:.3f} {seg.end - seg.start:.3f} <NA> <NA> {spk} <NA> <NA>\n")
        print("ok", fid, flush=True)


if __name__ == "__main__":
    main()
