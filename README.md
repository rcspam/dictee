# dictee

**Saisie vocale push-to-talk pour Linux** — parlez, et le texte s'écrit à la position du curseur. Avec traduction optionnelle.

La transcription est réalisée **100% en local** grâce au modèle [NVIDIA Parakeet-TDT 0.6B](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx) exécuté via ONNX Runtime. Aucune donnée audio n'est envoyée vers un serveur externe — votre voix reste sur votre machine.

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

### Post-traitement (dictée française)

Le texte transcrit est post-traité pour interpréter les commandes vocales françaises :
- « point à la ligne » → saut de ligne
- « trois petits points » → `...`

## Installation

Télécharger le `.deb` depuis les [Releases](../../releases), puis :

```bash
# Version GPU (NVIDIA CUDA)
sudo dpkg -i dictee-cuda_0.3.2_amd64.deb

# Version CPU (tout ordinateur)
sudo dpkg -i dictee-cpu_0.3.2_amd64.deb

# Installer les dépendances manquantes
sudo apt-get install -f
```

### Dépendances

```bash
# Dépendances principales
sudo apt install pipewire ydotool wl-clipboard libnotify-bin python3-gi gir1.2-ayatanaappindicator3-0.1

# Pour la traduction (optionnel)
sudo apt install translate-shell    # --translate (Google Translate)
# ou
curl -fsSL https://ollama.com/install.sh | sh && ollama pull translategemma  # --translate --ollama (100% local)
```

#### animation-speech (recommandé)

[animation-speech](https://github.com/rcspam/animation-speech) affiche une animation visuelle pendant l'enregistrement et permet d'annuler avec la touche Echap. Sans cette dépendance, `dictee` fonctionne normalement mais sans retour visuel.

```bash
# Installer depuis le .deb (voir les releases du repo)
sudo dpkg -i animation-speech_*.deb
```

#### ydotool-rebind (clavier AZERTY)

`ydotool` simule les frappes clavier pour taper le texte transcrit dans l'application active. Par défaut, il utilise un layout **QWERTY** — ce qui produit des caractères incorrects sur un clavier AZERTY (par ex. `q` au lieu de `a`).

[ydotool-rebind](https://github.com/david-vct/ydotool-rebind) est un wrapper qui corrige ce problème en remappant les touches pour supporter les claviers AZERTY et les caractères accentués français (é, è, ê, à, ç, etc.).

```bash
# Installer ydotool-rebind (remplace la commande ydotool)
git clone https://github.com/david-vct/ydotool-rebind.git
cd ydotool-rebind
sudo make install
```

> **Note :** Sans ydotool-rebind, la dictée produira du texte avec des caractères mélangés sur un clavier français. Cette dépendance est indispensable pour les claviers AZERTY.

### Icône de zone de notification

`dictee-tray` affiche une icône dans la boîte à miniatures du panel qui indique l'état du daemon (actif/arrêté). Le menu contextuel permet de démarrer/arrêter le daemon, lancer une dictée ou ouvrir la configuration.

```bash
# Lancer manuellement
dictee-tray

# Activer au démarrage de la session
systemctl --user enable dictee-tray
```

L'icône s'adapte automatiquement au thème clair/sombre.

### Configuration

`dictee --setup` ouvre une interface graphique (GTK3) qui permet de configurer :

- **Raccourci clavier** : capture et enregistrement automatique (KDE Plasma / GNOME)
- **Traduction** : activer/désactiver, choix du backend (translate-shell ou ollama), langues source et cible

Les préférences sont sauvegardées dans `~/.config/dictee.conf` et chargées automatiquement à chaque lancement. Les arguments CLI (`--translate`, `--ollama`) ont toujours priorité sur la configuration.

> Pour les environnements non supportés (Sway, i3, Hyprland...), l'outil indique la commande à configurer manuellement dans le gestionnaire de fenêtres.

---

## Backend : moteur de transcription

Le moteur de transcription s'appuie sur [parakeet-rs](https://github.com/altunenes/parakeet-rs) par [@altunenes](https://github.com/altunenes) pour l'inférence des modèles NVIDIA Parakeet via ONNX Runtime.

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

Les modèles doivent être placés dans `/usr/share/dictee/` :

```
/usr/share/dictee/
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

Le moteur de transcription s'appuie sur [parakeet-rs](https://github.com/altunenes/parakeet-rs) par [Enes Altun](https://github.com/altunenes), qui fournit la bibliothèque Rust pour l'inférence des modèles NVIDIA Parakeet via ONNX Runtime.

Ce projet ajoute :
- 5 binaires CLI prêts à l'emploi (daemon, client, diarisation, streaming)
- Script de dictée vocale push-to-talk avec traduction
- Conversion automatique de tout format audio via ffmpeg
- Résolution de chemins (`~/`, `./`, `../`)
- Auto-unmute du microphone (PipeWire/PulseAudio)
- Paquets Debian (.deb) pour installation système
- Service systemd
- Interface de configuration GTK3 (`dictee --setup`)
- Icône de zone de notification (`dictee-tray`)

## Licence

Ce projet est distribué sous licence **GPL-3.0-or-later** (voir [LICENSE](LICENSE)).

Le code original de [parakeet-rs](https://github.com/altunenes/parakeet-rs) par Enes Altun est sous licence MIT (voir [LICENSE-MIT](LICENSE-MIT)).

Les modèles ONNX Parakeet (téléchargés séparément depuis HuggingFace) sont fournis par NVIDIA. Ce projet ne distribue pas les modèles.
