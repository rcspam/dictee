<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg">
    <img src="assets/banner-light.svg" alt="dictée" width="480">
  </picture>
</p>

<p align="center">
  <b>Saisie vocale push-to-talk pour Linux</b> — parlez, et le texte s'écrit à la position du curseur. Avec traduction optionnelle.
</p>

<p align="center">
  <a href="https://github.com/rcspam/dictee/releases"><img src="https://img.shields.io/github/v/release/rcspam/dictee?label=release&color=blue" alt="Dernière release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-GPL--3.0-green" alt="Licence GPL-3.0"></a>
  <img src="https://img.shields.io/badge/backend-Rust-orange?logo=rust" alt="Rust">
  <img src="https://img.shields.io/badge/frontend-PyQt6%20%2F%20Bash-yellow" alt="PyQt6 / Bash">
  <img src="https://img.shields.io/badge/plateforme-Linux-lightgrey?logo=linux" alt="Linux">
</p>

<p align="center">
  <a href="README.md">Read in English</a>
</p>

---

<p align="center">
  <b>Widget KDE Plasma</b><br>
  <a href="https://youtu.be/c6MyyW4LarE">
    <img src="assets/demo-plasmoid-v2.gif" alt="Démo Plasmoid Dictée — cliquez pour voir sur YouTube" width="960">
  </a>
</p>

<p align="center">
  <b>Animation plein écran (animation-speech)</b><br>
  <a href="https://youtu.be/-fWZZEO7mCA">
    <img src="assets/demo.gif" alt="démo dictee — cliquez pour voir sur YouTube" width="960">
  </a>
</p>

La transcription est réalisée **100% en local** grâce au modèle [NVIDIA Parakeet-TDT 0.6B](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx) exécuté via ONNX Runtime. Aucune donnée audio n'est envoyée vers un serveur externe — votre voix reste sur votre machine.

Un premier appui sur le raccourci clavier démarre l'enregistrement (avec animation visuelle via [animation-speech](https://github.com/rcspam/animation-speech) ou le **widget KDE Plasma** inclus), un second l'arrête, transcrit la voix et **tape le texte directement dans l'application active** via [dotool](https://sr.ht/~geb/dotool/).

## Utilisation

```bash
# Premier lancement : configurer le raccourci clavier, la traduction, les langues
dictee --setup

# Dictée simple — transcrit et tape
dictee

# Avec traduction (défaut: langue système → anglais)
dictee --translate
dictee --translate --ollama    # traduction 100% locale via ollama/translategemma

# Changer les langues de traduction
DICTEE_LANG_TARGET=es dictee --translate    # → espagnol

# Annuler l'enregistrement en cours (via raccourci ou touche Echap)
dictee --cancel
```

### Post-traitement (dictée française)

Le texte transcrit est post-traité pour interpréter les commandes vocales françaises :
- « point à la ligne » → saut de ligne
- « trois petits points » → `...`

## Installation

Télécharger le `.deb` depuis les [Releases](../../releases), puis :

```bash
# Version GPU (NVIDIA CUDA)
sudo dpkg -i dictee-cuda_1.0.0_amd64.deb

# Version CPU (tout ordinateur)
sudo dpkg -i dictee-cpu_1.0.0_amd64.deb

# Installer les dépendances manquantes
sudo apt-get install -f
```

Après installation, lancez `dictee --setup` pour configurer le raccourci clavier et les options de traduction.

<p align="center">
  <img src="assets/dictee-setup.png" alt="dictee --setup" width="400">
</p>

### Dépendances

```bash
# Dépendances principales
sudo apt install pipewire dotool libnotify-bin python3-gi gir1.2-ayatanaappindicator3-0.1

# Optionnel (copie dans le presse-papier en bonus)
sudo apt install wl-clipboard

# Pour la traduction (optionnel) — 3 backends disponibles :
sudo apt install translate-shell    # translate-shell (Google ou Bing)
# ou
docker pull libretranslate/libretranslate  # LibreTranslate (100% local, Docker)
# ou
curl -fsSL https://ollama.com/install.sh | sh && ollama pull translategemma  # ollama (100% local)
```

#### Retour visuel pendant l'enregistrement

Deux options sont disponibles pour le retour visuel pendant l'enregistrement :

**Option 1 : Widget KDE Plasma (recommandé pour les utilisateurs KDE)**

Le widget Plasma 6 inclus affiche des barres audio en temps réel directement dans le panneau, avec contrôles du daemon et animations configurables. Voir [Widget KDE Plasma](#widget-kde-plasma) ci-dessous.

**Option 2 : animation-speech (tous les bureaux)**

[animation-speech](https://github.com/rcspam/animation-speech) affiche une animation visuelle plein écran pendant l'enregistrement et permet d'annuler avec la touche Echap. Fonctionne sur les compositeurs Wayland supportant `wlr-layer-shell` (KDE Plasma, Sway, Hyprland…). Non compatible avec GNOME.

> **Utilisateurs GNOME** : il n'existe pas encore d'extension GNOME Shell pour dictee. Les contributions sont les bienvenues — voir le [code source du plasmoid](plasmoid/) comme architecture de référence (machine à états, bandes audio FFT, communication avec le daemon).

```bash
# Installer depuis le .deb
sudo dpkg -i animation-speech_1.2.0_all.deb
```

> Télécharger : [releases animation-speech](https://github.com/rcspam/animation-speech/releases) (.deb et .tar.gz)

Sans aucune de ces options, `dictee` fonctionne normalement mais sans retour visuel.

### Icône de zone de notification

`dictee-tray` est le substitut au widget KDE Plasma pour les bureaux non-KDE (GNOME, Xfce, Sway, Hyprland…). Il affiche une icône dans la zone de notification qui reflète l'état en temps réel : idle, enregistrement (vert), transcription (bleu), daemon arrêté (rouge). Le clic gauche lance une dictée, le clic molette annule, et le menu contextuel donne accès à toutes les actions (dictée, traduction, daemon, configuration).

```bash
# Lancer manuellement
dictee-tray

# Activer au démarrage de la session
systemctl --user enable --now dictee-tray
```

L'icône s'adapte automatiquement au thème clair/sombre. Sur KDE Plasma, préférer le [widget plasmoid](#widget-kde-plasma) qui offre des animations audio en temps réel.

### Widget KDE Plasma

Un widget natif KDE Plasma 6 est inclus. Il affiche une visualisation audio en temps réel pendant l'enregistrement, l'état du daemon, et des contrôles rapides (dictée, traduction, annulation).

| Popup du widget (enregistrement) | Configuration |
|:--------------------------------:|:-------------:|
| ![Popup plasmoid](plasmoid.png) | ![Configuration plasmoid](plasmoid_config.png) |

```bash
# Installer (inclus dans le .deb, ou manuellement)
kpackagetool6 -t Plasma/Applet -i /usr/share/dictee/dictee.plasmoid

# Mettre à jour
kpackagetool6 -t Plasma/Applet -u /usr/share/dictee/dictee.plasmoid
```

Clic droit sur le panneau → « Ajouter des composants graphiques… » → chercher « Dictée ».

#### Styles d'animation

Cinq styles d'animation sont disponibles, tous avec enveloppe Hanning (atténuation aux bords), sensibilité par style, et couleurs arc-en-ciel optionnelles :

| Barres | Onde | Pulsation | Points | Forme d'onde |
|:------:|:----:|:---------:|:------:|:------------:|
| ![Barres](plasmoid/assets/anim-bars.svg?v=2) | ![Onde](plasmoid/assets/anim-wave.svg) | ![Pulsation](plasmoid/assets/anim-pulse.svg) | ![Points](plasmoid/assets/anim-dots.svg) | ![Forme d'onde](plasmoid/assets/anim-waveform.svg) |

Mode arc-en-ciel : ![Rainbow](plasmoid/assets/anim-rainbow.svg?v=2)

#### Réglages

- **Volume micro** — réglage du niveau d'entrée directement depuis la config du widget
- **Seuil de silence** — met à zéro l'audio sous un seuil pour un silence net
- **Auto-calibration** — capture le bruit ambiant au démarrage pour une normalisation optimale
- **Sensibilité** — courbe de puissance par style d'animation (`pow(raw, 1/sens)`) pour un contrôle précis
- **Forme d'enveloppe** — puissance Hanning ajustable (plate → pointue)
- **Centre d'enveloppe** — déplace le pic sur la plage de fréquences (80–4000 Hz) pour une meilleure répartition spectrale
- **Contrôles par style** — nombre de barres, espacement, rayon, vitesse, etc.

> Nécessite `python3-numpy` et `pulseaudio-utils` (parec) pour la visualisation audio en temps réel.

### Configuration

`dictee --setup` ouvre une interface graphique (PyQt6) qui permet de configurer :

- **Modèles ASR** : téléchargement et gestion des modèles de transcription (TDT, Sortformer, Nemotron)
- **Raccourcis clavier** : capture et enregistrement automatique (KDE Plasma / GNOME) — raccourcis séparés pour la dictée et la dictée + traduction
- **Traduction** : langues source/cible, choix du backend :

| Backend | Confidentialité | Vitesse | Qualité | Prérequis |
|---------|-----------------|---------|---------|-----------|
| **translate-shell** (Google) | En ligne | 0,2–0,7s | Bonne | `apt install translate-shell` |
| **translate-shell** (Bing) | En ligne | 1,7–2,2s | Bonne | `apt install translate-shell` |
| **LibreTranslate** | 100% local | 0,1–0,3s | Bonne | Docker (~2 Go d'image) |
| **ollama** | 100% local | 2,3–3,4s | Meilleure | ollama + modèle translategemma/aya |
- **Options** : copie presse-papier, retour visuel (overlay animation-speech ou widget Plasma)
- **Services** : démarrage automatique du daemon et du tray

Les préférences sont sauvegardées dans `~/.config/dictee.conf` et chargées automatiquement à chaque lancement. Les arguments CLI (`--translate`, `--ollama`) ont toujours priorité sur la configuration.

> Pour les environnements non supportés (Sway, i3, Hyprland...), l'outil indique la commande à configurer manuellement dans le gestionnaire de fenêtres.

---

## Backend : moteur de transcription

Trois backends de transcription sont supportés. Le moteur par défaut s'appuie sur [parakeet-rs](https://github.com/altunenes/parakeet-rs) par [@altunenes](https://github.com/altunenes) pour l'inférence des modèles NVIDIA Parakeet via ONNX Runtime. Des backends alternatifs (Vosk, faster-whisper) sont disponibles pour les cas d'usage légers ou multilingues.

### Fonctionnalités

- **Transcription multilingue** : 25+ langues via ParakeetTDT 0.6B, saisie dans toutes les langues via dotool (support XKB natif)
- **Diarisation** : identification de qui parle (jusqu'à 4 locuteurs) via Sortformer
- **Streaming temps réel** : transcription chunk par chunk via Nemotron (anglais uniquement)
- **Tout format audio** : WAV, MP3, OGG, FLAC, OPUS... conversion automatique via ffmpeg
- **Mode daemon** : modèle chargé une seule fois, transcriptions quasi-instantanées
- **Enregistrement micro** : PipeWire / PulseAudio / ALSA, auto-unmute
- **GPU ou CPU** : CUDA, TensorRT, CoreML, DirectML, OpenVINO
- **Backends ASR alternatifs** : Vosk et faster-whisper — installables depuis `dictee --setup`

### Backends ASR

Trois backends de transcription mutuellement exclusifs sont disponibles, commutables depuis `dictee --setup` :

| Backend | Langues | Taille modèle | Démarrage à froid | Daemon chaud | Type |
|---------|---------|----------------|-------------------|--------------|------|
| **Parakeet-TDT** (défaut) | 25 | ~2,5 Go | ~3s | ~0,8s | ONNX Runtime (Rust) |
| **Vosk** | 9+ | ~50 Mo | ~2s | ~1,5s | Python (léger) |
| **faster-whisper** | 99 | ~500 Mo–3 Go | ~2s | ~0,3s | CTranslate2 (Python) |

> Mesuré sur 10s de parole française, CPU (AMD Ryzen). Démarrage à froid = lancement service + chargement modèle + première transcription. Chaud = daemon déjà chargé.

**Parakeet-TDT** offre la meilleure précision avec ponctuation et capitalisation natives. **faster-whisper** est le plus rapide une fois chargé et supporte 99 langues. **Vosk** est le plus léger en disque et RAM (~50 Mo de modèle).

- Chaque backend tourne en service systemd utilisateur (`dictee.service`, `dictee-vosk.service`, `dictee-whisper.service`) — mutuellement exclusifs via `Conflicts=`
- Même protocole socket Unix → `transcribe-client` et `dictee` fonctionnent sans modification
- Vosk et faster-whisper sont installés dans des venvs Python isolés (`~/.local/share/dictee/`)
- Le téléchargement de modèles et le changement de backend se font depuis `dictee --setup`

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
- Interface de configuration PyQt6 (`dictee --setup`)
- Icône de zone de notification (`dictee-tray`)
- Widget KDE Plasma 6 avec visualisation audio temps réel

## Licence

Ce projet est distribué sous licence **GPL-3.0-or-later** (voir [LICENSE](LICENSE)).

Le code original de [parakeet-rs](https://github.com/altunenes/parakeet-rs) par Enes Altun est sous licence MIT (voir [LICENSE-MIT](LICENSE-MIT)).

[dotool](https://sr.ht/~geb/dotool/) par geb est intégré pour la simulation de saisie clavier et est sous licence GPL-3.0.

Les modèles ONNX Parakeet (téléchargés séparément depuis HuggingFace) sont fournis par NVIDIA. Ce projet ne distribue pas les modèles.
