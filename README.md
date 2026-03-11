<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg">
    <img src="assets/banner-light.svg" alt="dictée" width="480">
  </picture>
</p>

<p align="center">
  <b>Push-to-talk voice dictation for Linux</b> — speak, and the text is typed at the cursor position. With optional translation.
</p>

<p align="center">
  <a href="https://github.com/rcspam/dictee/releases"><img src="https://img.shields.io/github/v/release/rcspam/dictee?label=release&color=blue" alt="Latest Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-green" alt="License GPL-3.0"></a>
  <img src="https://img.shields.io/badge/backend-Rust-orange?logo=rust" alt="Rust">
  <img src="https://img.shields.io/badge/frontend-PyQt6%20%2F%20Bash-yellow" alt="PyQt6 / Bash">
  <img src="https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux" alt="Linux">
</p>

<p align="center">
  <a href="README.fr.md">Lire en Fran&ccedil;ais</a>
</p>

---

<p align="center">
  <b>KDE Plasma widget</b><br>
  <a href="https://youtu.be/c6MyyW4LarE">
    <img src="assets/demo-plasmoid.gif?v=2" alt="Dictée Plasmoid demo — click to watch on YouTube" width="960">
  </a>
</p>

<p align="center">
  <b>Fullscreen animation (animation-speech)</b><br>
  <a href="https://youtu.be/-fWZZEO7mCA">
    <img src="assets/demo.gif" alt="dictee demo — click to watch on YouTube" width="960">
  </a>
</p>

Transcription is performed **100% locally** using the [NVIDIA Parakeet-TDT 0.6B](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx) model running via ONNX Runtime. No audio data is sent to any external server — your voice stays on your machine.

A first press of the keyboard shortcut starts recording (with a visual animation via [animation-speech](https://github.com/rcspam/animation-speech) or the included **KDE Plasma widget**), a second press stops it, transcribes the speech and **types the text directly into the active application** via [dotool](https://sr.ht/~geb/dotool/).

## Usage

```bash
# First launch: configure keyboard shortcut, translation, languages
dictee --setup

# Simple dictation — transcribe and type
dictee

# With translation (default: system language → English)
dictee --translate
dictee --translate --ollama    # 100% local translation via ollama/translategemma

# Change translation languages
DICTEE_LANG_TARGET=es dictee --translate    # → Spanish

# Cancel an ongoing recording (via shortcut or Escape key)
dictee --cancel
```

### Post-processing (French dictation)

Transcribed text is post-processed to interpret French voice commands:
- "point à la ligne" → line break
- "trois petits points" → `...`

## Installation

Download the `.deb` from the [Releases](../../releases), then:

```bash
# GPU version (NVIDIA CUDA)
sudo dpkg -i dictee-cuda_0.99.9_amd64.deb

# CPU version (any computer)
sudo dpkg -i dictee-cpu_0.99.9_amd64.deb

# Install missing dependencies
sudo apt-get install -f
```

After installation, run `dictee --setup` to configure the keyboard shortcut and translation options.

<p align="center">
  <img src="assets/dictee-setup.png" alt="dictee --setup" width="400">
</p>

### Dependencies

```bash
# Main dependencies
sudo apt install pipewire dotool libnotify-bin python3-gi gir1.2-ayatanaappindicator3-0.1

# Optional (clipboard copy as bonus)
sudo apt install wl-clipboard

# For translation (optional) — 3 backends available:
sudo apt install translate-shell    # translate-shell (Google or Bing)
# or
docker pull libretranslate/libretranslate  # LibreTranslate (100% local, Docker)
# or
curl -fsSL https://ollama.com/install.sh | sh && ollama pull translategemma  # ollama (100% local)
```

#### Visual feedback during recording

Two options are available for visual feedback during recording:

**Option 1: KDE Plasma widget (recommended for KDE users)**

The included Plasma 6 widget displays real-time audio bars directly in the panel, with daemon controls and configurable animations. See [KDE Plasma widget](#kde-plasma-widget) below.

**Option 2: animation-speech (all desktops)**

[animation-speech](https://github.com/rcspam/animation-speech) displays a fullscreen visual animation during recording and allows cancellation with the Escape key. Works on Wayland compositors supporting `wlr-layer-shell` (KDE Plasma, Sway, Hyprland…). Not compatible with GNOME.

> **GNOME users**: there is currently no GNOME Shell extension for dictee. Contributions are welcome — if you'd like to develop one, see the [plasmoid source](plasmoid/) for reference architecture (state machine, audio bands via FFT, daemon communication).

```bash
# Install from the .deb
sudo dpkg -i animation-speech_1.2.0_all.deb
```

> Download: [animation-speech releases](https://github.com/rcspam/animation-speech/releases) (.deb and .tar.gz)

Without either option, `dictee` works normally but without visual feedback.

### Notification area icon

`dictee-tray` displays an icon in the panel's notification area showing the daemon status (active/stopped). The context menu allows starting/stopping the daemon, launching a dictation, or opening the configuration.

```bash
# Launch manually
dictee-tray

# Enable at session startup
systemctl --user enable dictee-tray
```

The icon automatically adapts to light/dark themes.

### KDE Plasma widget

A native KDE Plasma 6 widget is included. It displays real-time audio visualization during recording, daemon status, and provides quick controls (dictate, translate, cancel).

| Widget popup (recording) | Configuration |
|:------------------------:|:-------------:|
| ![Plasmoid popup](plasmoid.png) | ![Plasmoid config](plasmoid_config.png) |

```bash
# Install (included in .deb, or manually)
kpackagetool6 -t Plasma/Applet -i /usr/share/dictee/dictee.plasmoid

# Update
kpackagetool6 -t Plasma/Applet -u /usr/share/dictee/dictee.plasmoid
```

Right-click on the panel → "Add Widgets…" → search for "Dictée".

#### Animation styles

Five animation styles are available, all with Hanning envelope (tapered edges), per-style sensitivity, and optional rainbow colors:

| Bars | Wave | Pulse | Dots | Waveform |
|:----:|:----:|:-----:|:----:|:--------:|
| ![Bars](plasmoid/assets/anim-bars.svg) | ![Wave](plasmoid/assets/anim-wave.svg) | ![Pulse](plasmoid/assets/anim-pulse.svg) | ![Dots](plasmoid/assets/anim-dots.svg) | ![Waveform](plasmoid/assets/anim-waveform.svg) |

Rainbow mode: ![Rainbow](plasmoid/assets/anim-rainbow.svg)

#### Settings

- **Noise gate** — zero out audio below a threshold for clean silence
- **Calibrate** — record silence to subtract background noise
- **Per-style controls** — bar count, spacing, radius, speed, etc.

> Requires `python3-numpy` and `pulseaudio-utils` (parec) for real-time audio visualization.

### Configuration

`dictee --setup` opens a graphical interface (PyQt6) for configuring:

- **ASR models**: download and manage transcription models (TDT, Sortformer, Nemotron)
- **Keyboard shortcuts**: capture and automatic registration (KDE Plasma / GNOME) — separate shortcuts for dictation and dictation + translation
- **Translation**: source/target languages, backend choice:
  - **translate-shell** — Google or Bing engine (online)
  - **LibreTranslate** — 100% local via Docker (~2 GB image), with pull/start/stop controls
  - **ollama** — 100% local LLM translation (translategemma, aya…)
- **Options**: clipboard copy, visual feedback (animation-speech overlay or Plasma widget)
- **Services**: daemon and tray autostart

Preferences are saved in `~/.config/dictee.conf` and automatically loaded on each launch. CLI arguments (`--translate`, `--ollama`) always take priority over the configuration.

> For unsupported environments (Sway, i3, Hyprland...), the tool shows the command to configure manually in your window manager.

---

## Backend: transcription engine

The transcription engine is built on [parakeet-rs](https://github.com/altunenes/parakeet-rs) by [@altunenes](https://github.com/altunenes) for NVIDIA Parakeet model inference via ONNX Runtime.

### Features

- **Multilingual transcription**: 25+ languages via ParakeetTDT 0.6B, text typed in any language via dotool (native XKB support)
- **Diarization**: speaker identification (up to 4 speakers) via Sortformer
- **Real-time streaming**: chunk-by-chunk transcription via Nemotron (English only)
- **Any audio format**: WAV, MP3, OGG, FLAC, OPUS... automatic conversion via ffmpeg
- **Daemon mode**: model loaded once, near-instant transcriptions
- **Microphone recording**: PipeWire / PulseAudio / ALSA, auto-unmute
- **GPU or CPU**: CUDA, TensorRT, CoreML, DirectML, OpenVINO
- **Alternative ASR backends**: Vosk (lightweight, streaming) and faster-whisper (99 languages, CTranslate2) — installable from `dictee --setup`

### Programs

| Program | Description | Languages |
|---------|-------------|-----------|
| `transcribe` | Transcribe an audio file | Multilingual |
| `transcribe-daemon` | Unix socket server (preloaded model) | Multilingual |
| `transcribe-client` | Client: file, stdin, or microphone | Multilingual |
| `transcribe-diarize` | Transcription + speaker identification | Multilingual |
| `transcribe-stream-diarize` | Real-time streaming + diarization | English only |

All binaries support `--help` / `-h`.

> **Tip:** `dictee` uses daemon mode (`transcribe-daemon` + `transcribe-client`). The model is loaded once into memory, subsequent transcriptions are near-instant.

### Direct usage

```bash
# Transcribe a file (any format)
transcribe audio.mp3

# Daemon mode (faster for multiple files)
transcribe-daemon &
transcribe-client file1.wav
transcribe-client file2.ogg
cat audio.opus | transcribe-client

# Voice dictation from microphone (without the dictee script)
transcribe-client
# → Records until Enter. Microphone is auto-unmuted if necessary.

# Transcription with speaker identification
transcribe-diarize meeting.wav
# [0.00 - 2.50] Speaker 1: Hello everyone.
# [2.80 - 5.10] Speaker 2: Thanks for coming.
```

### ONNX models

Models should be placed in `/usr/share/dictee/`:

```
/usr/share/dictee/
├── tdt/                  # ParakeetTDT (multilingual)
│   ├── encoder-model.onnx
│   ├── decoder_joint-model.onnx
│   └── vocab.txt
├── sortformer/           # Diarization
│   └── diar_streaming_sortformer_4spk-v2.1.onnx
└── nemotron/             # Streaming (English)
    ├── encoder-model.onnx
    ├── decoder-model.onnx
    └── vocab.txt
```

The TDT model is available on HuggingFace: [istupakov/parakeet-tdt-0.6b-v3-onnx](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx).

### Audio pipeline architecture

```
Audio (any format)
    ↓ ffmpeg (if not WAV)
WAV 16kHz mono
    ↓ preemphasis (0.97)
STFT (n_fft=512, hop=160, win=400, Hann)
    ↓
Mel-spectrogram (128 bins, Slaney)
    ↓
ONNX model (ParakeetTDT / Nemotron)
    ↓
Decoder (tokens → text)
    ↓
Timestamp aggregation (tokens → words → sentences)
    ↓ [optional]
Sortformer (diarization)
    ↓
Final text with timestamps / speakers
```

## Building from source

### Prerequisites

- Rust (edition 2021)
- ffmpeg (for audio format conversion)

### Build

```bash
# CPU only
cargo build --release

# CUDA + diarization
cargo build --release --features "cuda,sortformer"

# Debian packages (CPU + CUDA)
./build-deb.sh
```

### Cargo features

| Feature | Description |
|---------|-------------|
| `cpu` | CPU execution (default) |
| `cuda` | NVIDIA GPU via CUDA |
| `tensorrt` | TensorRT optimization |
| `coreml` | Apple CoreML |
| `directml` | Microsoft DirectML |
| `openvino` | Intel OpenVINO |
| `sortformer` | Diarization (required for `*-diarize`) |

### Tests

```bash
cargo test
cargo test --features sortformer
```

## Credits

The transcription engine is built on [parakeet-rs](https://github.com/altunenes/parakeet-rs) by [Enes Altun](https://github.com/altunenes), which provides the Rust library for NVIDIA Parakeet model inference via ONNX Runtime.

This project adds:
- 5 ready-to-use CLI binaries (daemon, client, diarization, streaming)
- Push-to-talk voice dictation script with translation
- Automatic conversion of any audio format via ffmpeg
- Path resolution (`~/`, `./`, `../`)
- Microphone auto-unmute (PipeWire/PulseAudio)
- Debian packages (.deb) for system installation
- Systemd service
- GTK3 configuration interface (`dictee --setup`)
- Notification area icon (`dictee-tray`)
- KDE Plasma 6 widget with real-time audio visualization

## License

This project is distributed under the **GPL-3.0-or-later** license (see [LICENSE](LICENSE)).

The original [parakeet-rs](https://github.com/altunenes/parakeet-rs) code by Enes Altun is under the MIT license (see [LICENSE-MIT](LICENSE-MIT)).

[dotool](https://sr.ht/~geb/dotool/) by geb is bundled for keyboard input simulation and is under the GPL-3.0 license.

The Parakeet ONNX models (downloaded separately from HuggingFace) are provided by NVIDIA. This project does not distribute the models.
