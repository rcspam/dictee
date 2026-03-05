# CLAUDE.md - parakeet-rs_rapha

## Projet

Fork personnalisé de parakeet-rs : toolkit Rust pour la reconnaissance vocale (ASR) et diarisation de locuteurs via les modèles NVIDIA Parakeet en ONNX. Version 0.3.2, maintenu par rcspam.

## Langue

Documentation et communication en **français**.

## Structure

```
src/
├── lib.rs                          # API publique
├── audio.rs                        # WAV, STFT, mel-spectrogrammes
├── parakeet_tdt.rs                 # Modèle TDT (multilingue, 25 langues)
├── nemotron.rs                     # Modèle Nemotron streaming (EN uniquement)
├── sortformer.rs                   # Diarisation (4 locuteurs max)
├── decoder.rs / decoder_tdt.rs     # Décodeurs token→texte
├── model.rs / model_tdt.rs / model_nemotron.rs / model_eou.rs  # Sessions ONNX
├── timestamps.rs                   # Alignement tokens→mots→phrases
├── config.rs / error.rs / vocab.rs / execution.rs / transcriber.rs
├── bin/
│   ├── transcribe.rs               # CLI batch (TDT, multilingue)
│   ├── transcribe_daemon.rs        # Serveur socket Unix (/tmp/transcribe.sock)
│   ├── transcribe_client.rs        # Client daemon + enregistrement micro
│   ├── transcribe_diarize.rs       # TDT + Sortformer
│   └── transcribe_stream_diarize.rs # Nemotron + Sortformer (EN uniquement)
```

## Modèle principal

**Parakeet-TDT 0.6B v3** (ONNX, depuis istupakov/parakeet-tdt-0.6b-v3-onnx sur HuggingFace).
- Architecture : FastConformer encoder + TDT decoder (Token-and-Duration Transducer)
- Fichiers : `encoder-model.onnx`, `decoder_joint-model.onnx`, `vocab.txt`
- Emplacement local : `models/tdt/` (symlink) ou `/usr/share/parakeet-transcribe/tdt/`
- Ponctuation et capitalisation natives (pas de post-traitement)

## Build

```bash
# CPU (défaut)
cargo build --release

# CUDA + diarisation
cargo build --release --features "cuda,sortformer"

# Paquets Debian (CPU + CUDA)
./build-deb.sh
```

### Features Cargo

- Défaut : `cpu`, `ort-defaults`
- GPU : `cuda`, `tensorrt`, `coreml`, `directml`, `openvino`, `webgpu`, `nnapi`
- Diarisation : `sortformer` (nécessaire pour les binaires `*-diarize`)

## Tests

```bash
cargo test
cargo test --features sortformer
```

## Dépendances clés

- `ort` 2.0.0-rc.11 (ONNX Runtime)
- `hound` (WAV I/O)
- `ndarray` (tableaux N-D)
- `rustfft` (FFT pour spectrogrammes)
- `tokenizers` (SentencePiece)

## Pipeline audio

```
WAV 16kHz mono → preemphasis (0.97) → STFT (n_fft=512, hop=160, win=400, Hann)
→ Mel filterbank (128 bins, Slaney, log guard 5.96e-8) → tenseur ONNX
```

## Conventions

- Les binaires utilisent `/usr/share/parakeet-transcribe/` comme chemin modèle par défaut
- Socket daemon : `/tmp/transcribe.sock`
- Audio micro : PipeWire → PulseAudio → ALSA (fallback)
- Durée enregistrement : env `TRANSCRIBE_DURATION` (optionnel ; sans → arrêt par Entrée)
- Auto-unmute micro : détection via `wpctl`/`pactl`, remute après transcription
- Branche principale : `master`
