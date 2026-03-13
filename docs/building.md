# Compilation depuis les sources

[Retour au README principal](../README.md)

---

## Prérequis

- **Rust** (edition 2021)
- **ffmpeg** (pour la conversion des formats audio)
- **Go** + **scdoc** + **libxkbcommon-dev** (pour dotool)

## Build

```bash
# CPU uniquement
cargo build --release

# CUDA + diarisation
cargo build --release --features "cuda,sortformer"

# Paquets Debian (CPU + CUDA)
./build-deb.sh
```

## Features Cargo

| Feature | Description |
|---------|-------------|
| `cpu` | Exécution CPU (défaut) |
| `cuda` | GPU NVIDIA via CUDA |
| `tensorrt` | Optimisation TensorRT |
| `coreml` | Apple CoreML |
| `directml` | Microsoft DirectML |
| `openvino` | Intel OpenVINO |
| `sortformer` | Diarisation (nécessaire pour `*-diarize`) |

## Tests

```bash
cargo test
cargo test --features sortformer
```

## Pipeline audio (architecture interne)

```
Audio (tout format)
    │ ffmpeg (si non-WAV)
WAV 16kHz mono
    │ preemphasis (0.97)
STFT (n_fft=512, hop=160, win=400, Hann)
    │
Mel-spectrogram (128 bins, Slaney)
    │
Modèle ONNX (ParakeetTDT / Nemotron)
    │
Décodeur (tokens → texte)
    │
Agrégation timestamps (tokens → mots → phrases)
    │ [optionnel]
Sortformer (diarisation)
    │
Texte final avec horodatages / locuteurs
```
