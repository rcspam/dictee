# dictee

**Saisie vocale push-to-talk pour Linux** — parlez, et le texte s'écrit à la position du curseur. Avec traduction optionnelle.

Un premier appui sur le raccourci clavier démarre l'enregistrement (avec animation visuelle), un second l'arrête, transcrit la voix et **tape le texte directement dans l'application active**.

## Utilisation

```bash
# Dictée simple — transcrit et tape
dictee

# Avec traduction (défaut: langue système → anglais)
dictee --translate
dictee --translate --ollama    # traduction 100% locale via ollama/translategemma

# Changer les langues de traduction
DICTEE_LANG_TARGET=es dictee --translate    # → espagnol

# Annuler l'enregistrement en cours (via raccourci ou touche Echap)
dictee --cancel

# Ouvrir l'interface de configuration (raccourci clavier, traduction, langues)
dictee --setup
```

### Langues

La langue de transcription est détectée automatiquement par le modèle Parakeet (25+ langues supportées). Pour la traduction, les langues sont configurables :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DICTEE_LANG_SOURCE` | langue système (`$LANG`) | Langue source |
| `DICTEE_LANG_TARGET` | `en` | Langue cible |

### Backends de traduction

| Backend | Option | Description |
|---------|--------|-------------|
| [translate-shell](https://github.com/soimort/translate-shell) | `--translate` | Rapide, utilise Google Translate (défaut) |
| [ollama](https://ollama.com/) + translategemma | `--translate --ollama` | 100% local, plus lent mais sans dépendance cloud |

Le backend ollama utilise le modèle [translategemma](https://ollama.com/library/translategemma) avec le prompt suivant :

```
ollama run translategemma:latest "You are a professional <source> to <target> translator.
Your goal is to accurately convey the meaning and nuances of the original text
while adhering to the target language grammar, vocabulary, and cultural sensitivities.
Produce only the <target> translation, without any additional explanations or commentary.
Please translate the following text:

<texte transcrit>"
```

Les langues `<source>` et `<target>` sont remplacées par les valeurs de `DICTEE_LANG_SOURCE` et `DICTEE_LANG_TARGET`.

> **Note :** Le premier appel avec `--ollama` peut être sensiblement plus long, le temps pour ollama de charger le modèle translategemma en mémoire. Les appels suivants seront plus rapides tant que le modèle reste chargé.

### Post-traitement (dictée française)

Le texte transcrit est post-traité pour interpréter les commandes vocales françaises :
- « point à la ligne » → saut de ligne
- « trois petits points » → `...`

## Installation

Télécharger le `.deb` depuis les [Releases](../../releases), puis :

```bash
# Version GPU (NVIDIA CUDA)
sudo dpkg -i parakeet-transcribe-cuda_0.3.2_amd64.deb

# Version CPU (tout ordinateur)
sudo dpkg -i parakeet-transcribe-cpu_0.3.2_amd64.deb

# Installer les dépendances manquantes
sudo apt-get install -f
```

### Dépendances

| Dépendance | Rôle | Obligatoire |
|------------|------|:-----------:|
| [parakeet-transcribe](#backend--parakeet-transcribe) | Moteur de transcription (daemon) | oui |
| [animation-speech](https://github.com/rcspam/animation-speech) | Animation visuelle pendant l'enregistrement + annulation par Echap | recommandé |
| `pw-record` (PipeWire) | Enregistrement audio micro | oui |
| `ydotool` | Saisie clavier virtuelle | oui |
| [ydotool-rebind](https://github.com/david-vct/ydotool-rebind) | Correction AZERTY + accents français pour ydotool | oui (clavier AZERTY) |
| `wl-clipboard` | Copie presse-papier (Wayland) | oui |
| `libnotify` | Notifications bureau | oui |
| [translate-shell](https://github.com/soimort/translate-shell) | Traduction via Google Translate | si `--translate` |
| [ollama](https://ollama.com/) + [translategemma](https://ollama.com/library/translategemma) | Traduction 100% locale | si `--translate --ollama` |
| `python3-gi` (PyGObject) | Interface de configuration (`dictee --setup`) et icône tray | recommandé |
| `gir1.2-ayatanaappindicator3-0.1` | Icône dans la zone de notification (KDE/GNOME) | recommandé |

### Icône de zone de notification

`parakeet-tray` affiche une icône dans la boîte à miniatures du panel qui indique l'état du daemon (actif/arrêté). Le menu contextuel permet de démarrer/arrêter le daemon, lancer une dictée ou ouvrir la configuration.

```bash
# Lancer manuellement
parakeet-tray

# Activer au démarrage de la session
systemctl --user enable parakeet-tray
```

L'icône s'adapte automatiquement au thème clair/sombre.

---

## Backend : parakeet-transcribe

Le moteur de transcription est basé sur les modèles NVIDIA Parakeet via ONNX Runtime. C'est un fork de [parakeet-rs](https://github.com/altunenes/parakeet-rs) par [@altunenes](https://github.com/altunenes).

### Fonctionnalités

- **Transcription multilingue** : 25+ langues (dont le français) via ParakeetTDT 0.6B
- **Diarisation** : identification de qui parle (jusqu'à 4 locuteurs) via Sortformer
- **Streaming temps réel** : transcription chunk par chunk via Nemotron (anglais uniquement)
- **Tout format audio** : WAV, MP3, OGG, FLAC, OPUS... conversion automatique via ffmpeg
- **Mode daemon** : modèle chargé une seule fois, transcriptions quasi-instantanées
- **Enregistrement micro** : PipeWire / PulseAudio / ALSA, auto-unmute
- **GPU ou CPU** : CUDA, TensorRT, CoreML, DirectML, OpenVINO

### Programmes

| Programme | Description | Langues |
|-----------|-------------|---------|
| `transcribe` | Transcription d'un fichier audio | Multilingue |
| `transcribe-daemon` | Serveur socket Unix (modèle préchargé) | Multilingue |
| `transcribe-client` | Client : fichier, stdin ou micro | Multilingue |
| `transcribe-diarize` | Transcription + identification des locuteurs | Multilingue |
| `transcribe-stream-diarize` | Streaming temps réel + diarisation | Anglais uniquement |

Tous les binaires supportent `--help` / `-h`.

> **Conseil :** `dictee` utilise le mode daemon (`transcribe-daemon` + `transcribe-client`). Le modèle est chargé une seule fois en mémoire, les transcriptions suivantes sont quasi-instantanées.

### Utilisation directe

```bash
# Transcrire un fichier (tout format)
transcribe audio.mp3

# Mode daemon (plus rapide pour plusieurs fichiers)
transcribe-daemon &
transcribe-client fichier1.wav
transcribe-client fichier2.ogg
cat audio.opus | transcribe-client

# Dictée vocale depuis le micro (sans le script dictee)
transcribe-client
# → Enregistre jusqu'à Entrée. Le micro est démuté automatiquement si nécessaire.

# Transcription avec identification des locuteurs
transcribe-diarize reunion.wav
# [0.00 - 2.50] Speaker 1: Bonjour à tous.
# [2.80 - 5.10] Speaker 2: Merci d'être venus.
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

### Architecture du pipeline audio

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

## Crédits

Le moteur de transcription est un fork de [parakeet-rs](https://github.com/altunenes/parakeet-rs) par [Enes Altun](https://github.com/altunenes), qui fournit la bibliothèque Rust pour l'inférence des modèles NVIDIA Parakeet via ONNX Runtime.

Ce fork ajoute :
- 5 binaires CLI prêts à l'emploi (daemon, client, diarisation, streaming)
- Script de dictée vocale push-to-talk avec traduction
- Conversion automatique de tout format audio via ffmpeg
- Résolution de chemins (`~/`, `./`, `../`)
- Auto-unmute du microphone (PipeWire/PulseAudio)
- Paquets Debian (.deb) pour installation système
- Service systemd
- Interface de configuration GTK3 (`dictee --setup`)
- Icône de zone de notification (`parakeet-tray`)

## Licence

Ce fork est distribué sous licence **GPL-3.0-or-later** (voir [LICENSE](LICENSE)).

Le code original de [parakeet-rs](https://github.com/altunenes/parakeet-rs) par Enes Altun est sous licence MIT (voir [LICENSE-MIT](LICENSE-MIT)).

Les modèles ONNX Parakeet (téléchargés séparément depuis HuggingFace) sont fournis par NVIDIA. Ce projet ne distribue pas les modèles.
