# Documentation Parakeet-RS

Documentation des différents programmes de transcription vocale.

## Vue d'ensemble

Parakeet-RS est une bibliothèque Rust pour la reconnaissance vocale automatique (ASR) et la diarisation de locuteurs, utilisant les modèles NVIDIA Parakeet via ONNX Runtime.

---

## Compatibilité linguistique

| Programme | Français | Anglais | Autres langues |
|-----------|:--------:|:-------:|:--------------:|
| `transcribe` | **OUI** | OUI | OUI (multilingue) |
| `transcribe-daemon` | **OUI** | OUI | OUI (multilingue) |
| `transcribe-client` | **OUI** | OUI | OUI (multilingue) |
| `transcribe-diarize` | **OUI** | OUI | OUI (multilingue) |
| `transcribe-stream-diarize` | **NON** | OUI | NON |

### Résumé

- **Pour le français** : Utilisez `transcribe`, `transcribe-daemon`/`transcribe-client`, ou `transcribe-diarize`
  - Ces programmes utilisent le modèle **ParakeetTDT** qui est multilingue

- **Streaming temps réel** (`transcribe-stream-diarize`) : **Anglais uniquement**
  - Ce programme utilise le modèle **Nemotron 0.6B** qui ne supporte que l'anglais

---

## Programmes disponibles

### 1. `transcribe` - Transcription simple

> **Langues : Multilingue (Français, Anglais, etc.)**

**Usage :**
```bash
transcribe <fichier_audio> [repertoire_modele]
```

**Description :**
Programme en ligne de commande pour transcrire un fichier audio. Utilise le modèle ParakeetTDT (multilingue, supporte le français). Accepte tout format audio supporté par ffmpeg (WAV, MP3, OGG, FLAC, OPUS, etc.) avec conversion automatique.

**Paramètres :**
- `fichier_audio` : Fichier audio (tout format supporté par ffmpeg)
- `repertoire_modele` : (Optionnel) Chemin vers le modèle TDT, par défaut `/usr/share/parakeet-transcribe/tdt`

**Sortie :**
Texte transcrit avec horodatages par phrase.

**Exemple :**
```bash
transcribe enregistrement.wav
transcribe interview.mp3
transcribe memo.ogg
```

---

### 2. `transcribe-daemon` - Serveur de transcription

> **Langues : Multilingue (Français, Anglais, etc.)**

**Usage :**
```bash
transcribe-daemon
```

**Description :**
Processus serveur qui charge le modèle une seule fois en mémoire et écoute les requêtes de transcription via un socket Unix. Évite le rechargement coûteux du modèle pour chaque transcription.

**Socket :**
- Chemin : `/tmp/transcribe.sock`
- Protocole : Texte (chemin audio → texte transcrit)

**Paramètres :**
- `[model_dir]` : (Optionnel) Chemin vers le modèle TDT, défaut `/usr/share/parakeet-transcribe/tdt`

**Fonctionnement :**
1. Charge le modèle ParakeetTDT au démarrage
2. Écoute sur le socket Unix
3. Reçoit des chemins de fichiers audio
4. Renvoie le texte transcrit

---

### 3. `transcribe-client` - Client de transcription

> **Langues : Multilingue (Français, Anglais, etc.)**

**Usage :**
```bash
# Mode fichier (WAV, MP3, OGG, FLAC, OPUS... conversion auto via ffmpeg)
transcribe-client <fichier_audio>

# Mode stdin (pipe, tout format supporté par ffmpeg)
cat audio.mp3 | transcribe-client
curl -s https://example.com/audio.ogg | transcribe-client

# Mode microphone (enregistrement live)
transcribe-client
```

**Description :**
Client qui communique avec le daemon pour transcrire de l'audio. Supporte trois modes :

**Mode 1 - Fichier :**
Envoie un fichier audio au daemon. Si le fichier n'est pas au format WAV, il est automatiquement converti en WAV 16kHz mono via `ffmpeg`.

**Mode 2 - Stdin (pipe) :**
Lit l'audio depuis l'entrée standard. `ffmpeg` auto-détecte le format via les headers et convertit en WAV. Utile pour les pipelines shell.

**Mode 3 - Microphone :**
Enregistre depuis le microphone puis envoie au daemon.

**Backends audio supportés (par ordre de priorité) :**
1. PipeWire (`pw-record`)
2. PulseAudio (`parecord`)
3. ALSA (`arecord`)

**Variables d'environnement :**
- `TRANSCRIBE_DURATION` : Durée d'enregistrement en secondes (optionnel). Sans cette variable, l'enregistrement continue jusqu'à ce que l'utilisateur appuie sur Entrée.

**Auto-unmute :**
Si le microphone est muté au moment de l'enregistrement, `transcribe-client` le détecte (via `wpctl` ou `pactl`), affiche un avertissement, démute automatiquement, puis remute après la transcription.

**Dépendance :**
- `ffmpeg` (nécessaire pour la conversion des formats non-WAV)

**Exemples :**
```bash
# Transcrire un MP3 directement
transcribe-client enregistrement.mp3

# Transcrire depuis un pipe
ffmpeg -i video.mp4 -f wav - | transcribe-client

# Enregistrer 10 secondes et transcrire
TRANSCRIBE_DURATION=10 transcribe-client
```

---

### 4. `transcribe-diarize` - Transcription avec identification des locuteurs

> **Langues : Multilingue (Français, Anglais, etc.)**

**Usage :**
```bash
transcribe-diarize <fichier_audio> [rep_tdt] [rep_sortformer]
```

**Prérequis :**
Compilé avec la feature `sortformer` activée.

**Description :**
Combine la transcription avec la diarisation pour identifier qui parle. Accepte tout format audio supporté par ffmpeg. Utilise :
- **ParakeetTDT** : Transcription du texte
- **Sortformer** : Identification des locuteurs

**Paramètres :**
- `fichier_audio` : Fichier audio (tout format supporté par ffmpeg)
- `rep_tdt` : (Optionnel) Chemin modèle TDT, défaut `/usr/share/parakeet-transcribe/tdt`
- `rep_sortformer` : (Optionnel) Chemin modèle Sortformer, défaut `/usr/share/parakeet-transcribe/sortformer`

**Sortie :**
Chaque phrase préfixée par l'identifiant du locuteur.

**Exemple :**
```bash
transcribe-diarize reunion.wav
transcribe-diarize interview.mp3
# Sortie:
# [0.00 - 2.50] Locuteur 1: Bonjour à tous.
# [2.80 - 5.10] Locuteur 2: Merci d'être venus.
```

---

### 5. `transcribe-stream-diarize` - Transcription en streaming avec diarisation

> **Langues : ANGLAIS UNIQUEMENT**

**Usage :**
```bash
# Depuis un fichier (tout format audio)
transcribe-stream-diarize <fichier_audio>

# Depuis le microphone (Ctrl+C pour arrêter)
transcribe-stream-diarize
```

**Prérequis :**
- Feature `sortformer` activée

**Limitation importante :**
Le modèle Nemotron 0.6B utilisé pour le streaming ne supporte que l'**anglais**.
Pour le français, utilisez `transcribe-diarize` à la place (non temps-réel mais multilingue).

**Description :**
Transcription en temps réel avec diarisation. Accepte tout format audio supporté par ffmpeg. Utilise :
- **Nemotron 0.6B** : Transcription streaming par chunks de 560ms
- **Sortformer** : Diarisation des locuteurs

**Fonctionnement :**
1. Traite l'audio par morceaux de 560ms (8960 échantillons à 16kHz)
2. Affiche le texte transcrit en temps réel
3. À la fin, affiche le résultat final avec les locuteurs identifiés

**Variables d'environnement :**
- `NEMOTRON_DIR` : Chemin modèle Nemotron (défaut : `/usr/share/parakeet-transcribe/nemotron`)
- `SORTFORMER_DIR` : Chemin modèle Sortformer (défaut : `/usr/share/parakeet-transcribe/sortformer`)

**Auto-unmute :**
Si le microphone est muté, `transcribe-stream-diarize` le détecte (via `wpctl` ou `pactl`), démute automatiquement, puis remute après l'enregistrement.

---

## Architecture technique

### Modèles utilisés

| Modèle | Usage | Langues | Particularité |
|--------|-------|---------|---------------|
| **ParakeetTDT** | Transcription générale | **Multilingue** (FR, EN, DE, ES...) | 600M paramètres, précis |
| **Nemotron 0.6B** | Streaming temps réel | **Anglais uniquement** | Chunks 560ms, faible latence |
| **Sortformer** | Diarisation | Indépendant de la langue | Jusqu'à 4 locuteurs |

### Quel programme choisir pour le français ?

| Besoin | Programme recommandé |
|--------|---------------------|
| Transcription simple | `transcribe` |
| Transcriptions multiples (performance) | `transcribe-daemon` + `transcribe-client` |
| Dictée vocale (microphone) | `transcribe-client` (sans argument) |
| Réunion avec identification des locuteurs | `transcribe-diarize` |
| Streaming temps réel | Non disponible en français |

### Pipeline de traitement

```
Audio WAV (16kHz mono)
    ↓
Extraction Mel-spectrogram (128 bins)
    ↓
Modèle ONNX (ParakeetTDT/Nemotron)
    ↓
Décodeur (tokens → texte)
    ↓
Agrégation timestamps (tokens → mots → phrases)
    ↓
[Optionnel] Sortformer (diarisation)
    ↓
Texte final avec horodatages/locuteurs
```

### Format audio requis

- **Format natif** : WAV 16kHz mono (PCM 16-bit ou 32-bit float)
- **Autres formats** : MP3, OGG, FLAC, OPUS, etc. (conversion automatique via `ffmpeg` dans tous les binaires)

---

## Compilation

### Features disponibles

```bash
# CPU uniquement (défaut)
cargo build --release

# Avec CUDA (GPU NVIDIA)
cargo build --release --features cuda

# Avec diarisation
cargo build --release --features sortformer

# CUDA + diarisation
cargo build --release --features "cuda,sortformer"
```

### Backends d'exécution

| Feature | Description |
|---------|-------------|
| `cpu` | Exécution CPU (défaut) |
| `cuda` | GPU NVIDIA via CUDA |
| `tensorrt` | Optimisation TensorRT |
| `coreml` | Apple CoreML |
| `directml` | Microsoft DirectML |
| `openvino` | Intel OpenVINO |

---

## Installation des modèles

Les modèles doivent être placés dans `/usr/share/parakeet-transcribe/` :

```
/usr/share/parakeet-transcribe/
├── tdt/
│   ├── encoder-model.onnx
│   ├── decoder_joint-model.onnx
│   └── vocab.txt
├── sortformer/
│   └── diar_streaming_sortformer_4spk-v2.1.onnx
└── nemotron/
    ├── encoder-model.onnx
    ├── decoder-model.onnx
    └── vocab.txt
```

---

## Service systemd

Un fichier service est fourni pour lancer le daemon au démarrage :

```bash
# Installer le service
sudo cp transcribe-daemon.service /etc/systemd/system/

# Activer et démarrer
sudo systemctl enable transcribe-daemon
sudo systemctl start transcribe-daemon

# Vérifier le statut
sudo systemctl status transcribe-daemon
```

---

## Exemples d'utilisation

### Transcription basique
```bash
transcribe mon_audio.wav
transcribe interview.mp3
transcribe memo.ogg
```

### Transcription via daemon (plus rapide pour plusieurs fichiers)
```bash
# Terminal 1 : Lancer le daemon
transcribe-daemon

# Terminal 2 : Envoyer des fichiers (tout format audio)
transcribe-client fichier1.wav
transcribe-client fichier2.mp3
transcribe-client fichier3.ogg
```

### Transcription via stdin (pipe)
```bash
# Depuis un fichier
cat audio.opus | transcribe-client

# Depuis une URL
curl -s https://example.com/audio.mp3 | transcribe-client

# Extraire l'audio d'une vidéo
ffmpeg -i video.mp4 -f wav - | transcribe-client
```

### Dictée vocale
```bash
# Enregistrer jusqu'à Entrée
transcribe-client

# Enregistrer 15 secondes (timeout fixe)
TRANSCRIBE_DURATION=15 transcribe-client
```

### Transcription de réunion avec locuteurs
```bash
transcribe-diarize reunion.wav
transcribe-diarize reunion.mp3
```

---

## Aide en ligne

Tous les binaires supportent `--help` et `-h` :
```bash
transcribe --help
transcribe-daemon -h
transcribe-client --help
transcribe-diarize -h
transcribe-stream-diarize --help
```

---

## Dépannage

### Erreur "Model not found"
Vérifiez que les modèles sont installés dans `/usr/share/parakeet-transcribe/` ou spécifiez le chemin manuellement.

### Erreur "Socket not found"
Le daemon n'est pas lancé. Démarrez-le avec `transcribe-daemon`.

### Pas de son enregistré
Vérifiez que PipeWire, PulseAudio ou ALSA est configuré correctement.
Si le microphone est muté, `transcribe-client` et `transcribe-stream-diarize` le détectent et le démutent automatiquement.

### Performance lente sur CPU
Utilisez la version CUDA si vous avez un GPU NVIDIA compatible.
