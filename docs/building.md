# Compilation depuis les sources

[Retour au README principal](../README.md)

---

## Prérequis

- **Rust** (edition 2021)
- **ffmpeg** (pour la conversion des formats audio)
- **Go** + **scdoc** + **libxkbcommon-dev** (pour dotool)
- **podman** (ou docker) pour les paquets : les binaires Rust des paquets
  sont compilés dans un conteneur Debian 12 (glibc 2.36) afin de démarrer
  sur toute distribution supportée (issue #32)

## Build

```bash
# CPU uniquement
cargo build --release

# CUDA + diarisation
cargo build --release --features "cuda,sortformer"

# Paquets Debian (CPU + CUDA)
./build-deb.sh
```

`build-deb.sh`, `build-rpm.sh` et `build-tar.sh` n'appellent pas `cargo`
directement mais `packaging/cargo-glibc236.sh`, qui construit une fois
l'image `dictee-build-glibc236` puis compile dans `target/glibc236/`.
Compilés sur l'hôte (Ubuntu 24.04, glibc 2.39), les mêmes binaires
importent `GLIBC_2.39` et refusent de se lancer sur Debian 12. Le
`PKGBUILD` Arch n'est pas concerné : il compile sur la machine de
l'utilisateur.

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
