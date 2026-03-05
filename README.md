# parakeet-transcribe

Reconnaissance vocale (ASR) et diarisation de locuteurs sous Linux, basé sur les modèles NVIDIA Parakeet via ONNX Runtime.

Fork de [parakeet-rs](https://github.com/altunenes/parakeet-rs) par [@altunenes](https://github.com/altunenes), enrichi avec des outils CLI prêts à l'emploi : daemon, client micro, diarisation, paquets Debian.

## Fonctionnalités

- **Transcription multilingue** : 25+ langues (dont le français) via ParakeetTDT 0.6B
- **Diarisation** : identification de qui parle (jusqu'à 4 locuteurs) via Sortformer
- **Streaming temps réel** : transcription chunk par chunk via Nemotron (anglais uniquement)
- **Tout format audio** : WAV, MP3, OGG, FLAC, OPUS... conversion automatique via ffmpeg
- **Mode daemon** : modèle chargé une seule fois, transcriptions quasi-instantanées
- **Enregistrement micro** : PipeWire / PulseAudio / ALSA, auto-unmute
- **GPU ou CPU** : CUDA, TensorRT, CoreML, DirectML, OpenVINO

## Programmes

| Programme | Description | Langues |
|-----------|-------------|---------|
| `transcribe` | Transcription d'un fichier audio | Multilingue |
| `transcribe-daemon` | Serveur socket Unix (modèle préchargé) | Multilingue |
| `transcribe-client` | Client : fichier, stdin ou micro | Multilingue |
| `transcribe-diarize` | Transcription + identification des locuteurs | Multilingue |
| `transcribe-stream-diarize` | Streaming temps réel + diarisation | Anglais uniquement |
| `dictee` | Saisie vocale push-to-talk avec traduction optionnelle | Multilingue, FR→EN |

Tous les binaires supportent `--help` / `-h`.

> **Conseil :** pour des transcriptions plus réactives, utilisez le mode daemon (`transcribe-daemon` + `transcribe-client`). Le modèle est chargé une seule fois en mémoire, les transcriptions suivantes sont quasi-instantanées.

## Installation rapide (Debian/Ubuntu)

Télécharger le `.deb` depuis les [Releases](../../releases), puis :

```bash
# Version GPU (NVIDIA CUDA)
sudo dpkg -i parakeet-transcribe-cuda_0.3.2_amd64.deb

# Version CPU (tout ordinateur)
sudo dpkg -i parakeet-transcribe-cpu_0.3.2_amd64.deb

# Installer les dépendances manquantes
sudo apt-get install -f
```

### Modèles ONNX

Les modèles doivent être placés dans `/usr/share/parakeet-transcribe/` :

```
/usr/share/parakeet-transcribe/
├── tdt/                  # ParakeetTDT (multilingue)
│   ├── encoder-model.onnx
│   ├── decoder_joint-model.onnx
│   └── vocab.txt
├── sortformer/           # Diarisation
│   └── diar_streaming_sortformer_4spk-v2.1.onnx
└── nemotron/             # Streaming (anglais)
    ├── encoder-model.onnx
    ├── decoder-model.onnx
    └── vocab.txt
```

Le modèle TDT est disponible sur HuggingFace : [istupakov/parakeet-tdt-0.6b-v3-onnx](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx).

## Utilisation

```bash
# Transcrire un fichier (tout format)
transcribe audio.mp3

# Mode daemon (plus rapide pour plusieurs fichiers)
transcribe-daemon &
transcribe-client fichier1.wav
transcribe-client fichier2.ogg
cat audio.opus | transcribe-client

# Dictée vocale depuis le micro
transcribe-client
# → Enregistre jusqu'à Entrée. Le micro est démuté automatiquement si nécessaire.

# Transcription avec identification des locuteurs
transcribe-diarize reunion.wav
# [0.00 - 2.50] Speaker 1: Bonjour à tous.
# [2.80 - 5.10] Speaker 2: Merci d'être venus.
```

## Dictée vocale (push-to-talk)

Le script `dictee` permet la saisie vocale par raccourci clavier : un premier appui démarre l'enregistrement, un second l'arrête et **tape le texte transcrit à la position du curseur**.

La langue de transcription est la langue par défaut du système (détectée automatiquement par le modèle Parakeet). L'option `--translate` traduit le texte de FR vers EN avant de le taper.

```bash
# Dictée simple
dictee

# Avec traduction FR→EN
dictee --translate
dictee --translate --ollama    # via ollama/translategemma

# Annuler l'enregistrement en cours
dictee --cancel
```

### Backends de traduction

| Backend | Option | Description |
|---------|--------|-------------|
| [translate-shell](https://github.com/soimort/translate-shell) | `--translate` | Rapide, utilise Google Translate (défaut) |
| [ollama](https://ollama.com/) + translategemma | `--translate --ollama` | 100% local, plus lent mais sans dépendance cloud |

Le backend ollama utilise le modèle [translategemma](https://ollama.com/library/translategemma) avec le prompt suivant :

```
ollama run translategemma:latest "You are a professional French (fr) to English (en) translator.
Your goal is to accurately convey the meaning and nuances of the original French text
while adhering to English grammar, vocabulary, and cultural sensitivities.
Produce only the English translation, without any additional explanations or commentary.
Please translate the following French text into English:

<texte transcrit>"
```

### Dépendances

- `transcribe-daemon` en cours d'exécution
- `pw-record` (PipeWire)
- `ydotool` (saisie clavier virtuelle). Pour un clavier **AZERTY français**, installer [ydotool-rebind](https://github.com/david-vct/ydotool-rebind) qui corrige le mapping QWERTY et gère les accents.
- `wl-clipboard` (copie presse-papier)
- `translate-shell` ou `ollama` (si `--translate`)

### Optionnel

- [animation-speech](https://github.com/rcspam/animation-speech) : animation visuelle pendant l'enregistrement (contrôlée via `animation-speech-ctl`), annulation par touche Echap

## Compilation depuis les sources

### Prérequis

- Rust (edition 2021)
- ffmpeg (pour la conversion des formats audio)

### Build

```bash
# CPU uniquement
cargo build --release

# CUDA + diarisation
cargo build --release --features "cuda,sortformer"

# Paquets Debian (CPU + CUDA)
./build-deb.sh
```

### Features Cargo

| Feature | Description |
|---------|-------------|
| `cpu` | Exécution CPU (défaut) |
| `cuda` | GPU NVIDIA via CUDA |
| `tensorrt` | Optimisation TensorRT |
| `coreml` | Apple CoreML |
| `directml` | Microsoft DirectML |
| `openvino` | Intel OpenVINO |
| `sortformer` | Diarisation (nécessaire pour `*-diarize`) |

### Tests

```bash
cargo test
cargo test --features sortformer
```

## Architecture

```
Audio (tout format)
    ↓ ffmpeg (si non-WAV)
WAV 16kHz mono
    ↓ preemphasis (0.97)
STFT (n_fft=512, hop=160, win=400, Hann)
    ↓
Mel-spectrogram (128 bins, Slaney)
    ↓
Modèle ONNX (ParakeetTDT / Nemotron)
    ↓
Décodeur (tokens → texte)
    ↓
Agrégation timestamps (tokens → mots → phrases)
    ↓ [optionnel]
Sortformer (diarisation)
    ↓
Texte final avec horodatages / locuteurs
```

## Crédits

Ce projet est un fork de [parakeet-rs](https://github.com/altunenes/parakeet-rs) par [Enes Altun](https://github.com/altunenes), qui fournit la bibliothèque Rust pour l'inférence des modèles NVIDIA Parakeet via ONNX Runtime.

Ce fork ajoute :
- 5 binaires CLI prêts à l'emploi (daemon, client, diarisation, streaming)
- Conversion automatique de tout format audio via ffmpeg
- Résolution de chemins (`~/`, `./`, `../`)
- Auto-unmute du microphone (PipeWire/PulseAudio)
- Paquets Debian (.deb) pour installation système
- Service systemd

## Licence

Ce fork est distribué sous licence **GPL-3.0-or-later** (voir [LICENSE](LICENSE)).

Le code original de [parakeet-rs](https://github.com/altunenes/parakeet-rs) par Enes Altun est sous licence MIT (voir [LICENSE-MIT](LICENSE-MIT)).

Les modèles ONNX Parakeet (téléchargés séparément depuis HuggingFace) sont fournis par NVIDIA. Ce projet ne distribue pas les modèles.
