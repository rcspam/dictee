#!/usr/bin/env python3
"""dictee-models — List all installed ASR models across all backends.

Usage:
    dictee-models [--json]

Can also be imported as a module:
    from dictee_models import find_all_models, whisper_model_cached
"""
import os
import sys
import json as json_mod

# Model locations
DICTEE_DATA = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "dictee",
)
HF_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
SYS_DIR = "/usr/share/dictee"


def _dir_size_mb(path):
    """Total size of a directory in MB."""
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total / (1024 * 1024)


def _hf_cache_size_mb(cache_dir):
    """Size of a HuggingFace cache entry (blobs hold the actual data)."""
    blobs = os.path.join(cache_dir, "blobs")
    if os.path.isdir(blobs):
        return _dir_size_mb(blobs)
    return _dir_size_mb(cache_dir)


def find_parakeet_models():
    """Find Parakeet TDT ONNX models."""
    models = []
    for base, location in [(SYS_DIR, "system"), (DICTEE_DATA, "user")]:
        tdt_dir = os.path.join(base, "tdt")
        if os.path.isfile(os.path.join(tdt_dir, "encoder-model.onnx")):
            size = _dir_size_mb(tdt_dir)
            models.append({
                "backend": "parakeet",
                "name": "parakeet-tdt-0.6b-v3",
                "path": tdt_dir,
                "location": location,
                "size_mb": round(size),
            })
    return models


def find_canary_models():
    """Find Canary ONNX models."""
    models = []
    for base, location in [(SYS_DIR, "system"), (DICTEE_DATA, "user")]:
        canary_dir = os.path.join(base, "canary")
        if os.path.isfile(os.path.join(canary_dir, "encoder-model.onnx")):
            size = _dir_size_mb(canary_dir)
            models.append({
                "backend": "canary",
                "name": "canary-1b-v2",
                "path": canary_dir,
                "location": location,
                "size_mb": round(size),
            })
    return models


def find_sortformer_models():
    """Find Sortformer diarization ONNX models."""
    models = []
    for base, location in [(SYS_DIR, "system"), (DICTEE_DATA, "user")]:
        sf_dir = os.path.join(base, "sortformer")
        onnx_files = [f for f in os.listdir(sf_dir) if f.endswith(".onnx")] if os.path.isdir(sf_dir) else []
        if onnx_files:
            size = _dir_size_mb(sf_dir)
            name = onnx_files[0].replace(".onnx", "")
            models.append({
                "backend": "sortformer",
                "name": name,
                "path": sf_dir,
                "location": location,
                "size_mb": round(size),
            })
    return models


def find_vosk_models():
    """Find Vosk models."""
    models = []
    vosk_dir = os.path.join(DICTEE_DATA, "vosk-models")
    if not os.path.isdir(vosk_dir):
        return models
    for entry in sorted(os.listdir(vosk_dir)):
        full = os.path.join(vosk_dir, entry)
        if os.path.isdir(full) and entry.startswith("vosk-model"):
            size = _dir_size_mb(full)
            models.append({
                "backend": "vosk",
                "name": entry,
                "path": full,
                "location": "user",
                "size_mb": round(size),
            })
    return models


def find_whisper_models():
    """Find Whisper models in HuggingFace cache."""
    models = []
    if not os.path.isdir(HF_CACHE):
        return models
    for entry in sorted(os.listdir(HF_CACHE)):
        if not entry.startswith("models--"):
            continue
        # Match whisper-related models
        lower = entry.lower()
        if "whisper" not in lower:
            continue
        cache_path = os.path.join(HF_CACHE, entry)
        snap = os.path.join(cache_path, "snapshots")
        if not os.path.isdir(snap) or not os.listdir(snap):
            continue
        # Parse org/name from models--org--name
        parts = entry.split("--", 2)
        if len(parts) == 3:
            name = f"{parts[1]}/{parts[2]}"
        else:
            name = entry.replace("models--", "")
        size = _hf_cache_size_mb(cache_path)
        models.append({
            "backend": "whisper",
            "name": name,
            "path": cache_path,
            "location": "cache",
            "size_mb": round(size),
        })
    return models


def load_config():
    """Load dictee.conf to identify active backend and models."""
    conf_path = os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "dictee.conf",
    )
    conf = {}
    if os.path.isfile(conf_path):
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    conf[k] = v
    return conf


def whisper_model_cached(model_id):
    """Check if a Whisper model is fully downloaded in HuggingFace cache.

    A model is considered complete only if model.bin (CTranslate2 format)
    exists in the snapshot directory. Partial downloads are not counted.
    """
    if not os.path.isdir(HF_CACHE):
        return False
    candidates = [
        f"models--Systran--faster-whisper-{model_id}",
        f"models--{model_id.replace('/', '--')}",
        f"models--openai--whisper-{model_id}",
    ]
    for c in candidates:
        snap = os.path.join(HF_CACHE, c, "snapshots")
        if not os.path.isdir(snap):
            continue
        for rev in os.listdir(snap):
            model_bin = os.path.join(snap, rev, "model.bin")
            if os.path.isfile(model_bin) or os.path.islink(model_bin):
                return True
    return False


def canary_model_installed():
    """Check if Canary ONNX model files are present."""
    for d in [os.path.join(SYS_DIR, "canary"), os.path.join(DICTEE_DATA, "canary")]:
        if os.path.isfile(os.path.join(d, "encoder-model.onnx")):
            return True
    return False


def find_all_models():
    """Find all models across all backends."""
    all_models = []
    all_models.extend(find_parakeet_models())
    all_models.extend(find_canary_models())
    all_models.extend(find_sortformer_models())
    all_models.extend(find_vosk_models())
    all_models.extend(find_whisper_models())
    return all_models


def print_table(models):
    """Print models as a formatted table."""
    if not models:
        print("No models found.")
        return

    conf = load_config()
    active_backend = conf.get("DICTEE_ASR_BACKEND", "parakeet")
    active_whisper = conf.get("DICTEE_WHISPER_MODEL", "small")
    active_vosk = conf.get("DICTEE_VOSK_MODEL", "") or conf.get("DICTEE_LANG_SOURCE", "fr")

    total_size = sum(m["size_mb"] for m in models)

    print(f"Active backend: {active_backend}")
    if active_backend == "whisper":
        print(f"Active Whisper model: {active_whisper}")
    elif active_backend == "vosk":
        print(f"Active Vosk model: {active_vosk}")
    print()
    print(f"{'':>2} {'Backend':<12} {'Model':<45} {'Size':>7} {'Location':<8} Path")
    print("-" * 112)
    for m in models:
        size_str = f"{m['size_mb']} MB" if m["size_mb"] < 1024 else f"{m['size_mb']/1024:.1f} GB"
        # Mark active model
        active = ""
        if m["backend"] == active_backend and m["backend"] in ("parakeet", "canary", "sortformer"):
            active = "▶ "
        elif m["backend"] == "whisper" and active_backend == "whisper":
            # Match active whisper model
            name_lower = m["name"].lower()
            if active_whisper in name_lower or active_whisper.replace("/", "--") in name_lower.replace("/", "--"):
                active = "▶ "
        elif m["backend"] == "vosk" and active_backend == "vosk":
            if active_vosk in m["name"]:
                active = "▶ "
        print(f"{active:>2}{m['backend']:<12} {m['name']:<45} {size_str:>7} {m['location']:<8} {m['path']}")

    total_str = f"{total_size:.0f} MB" if total_size < 1024 else f"{total_size/1024:.1f} GB"
    print(f"\n{len(models)} models, {total_str} total")


def main():
    use_json = "--json" in sys.argv
    models = find_all_models()

    if use_json:
        print(json_mod.dumps(models, indent=2))
    else:
        print_table(models)


if __name__ == "__main__":
    main()
