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
  <img src="https://img.shields.io/badge/frontend-GTK3%20%2F%20Bash-yellow" alt="GTK3 / Bash">
  <img src="https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux" alt="Linux">
</p>

<p align="center">
  <a href="README.fr.md">Lire en Fran&ccedil;ais</a>
</p>

---

<p align="center">
  <img src="assets/demo.gif" alt="dictee demo" width="600">
</p>

Transcription is performed **100% locally** using the [NVIDIA Parakeet-TDT 0.6B](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx) model running via ONNX Runtime. No audio data is sent to any external server — your voice stays on your machine.

A first press of the keyboard shortcut starts recording (with a visual animation via [animation-speech](https://github.com/rcspam/animation-speech), to install separately), a second press stops it, transcribes the speech and **types the text directly into the active application** (multilingual keyboard support via [ydotool-rebind](https://github.com/rcspam/ydotool-rebind), to install separately).

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
sudo dpkg -i dictee-cuda_0.99_amd64.deb

# CPU version (any computer)
sudo dpkg -i dictee-cpu_0.99_amd64.deb

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
sudo apt install pipewire ydotool wl-clipboard libnotify-bin python3-gi gir1.2-ayatanaappindicator3-0.1

# For translation (optional)
sudo apt install translate-shell    # --translate (Google Translate)
# or
curl -fsSL https://ollama.com/install.sh | sh && ollama pull translategemma  # --translate --ollama (100% local)
```

#### animation-speech (recommended)

[animation-speech](https://github.com/rcspam/animation-speech) displays a visual animation during recording and allows cancellation with the Escape key. Without this dependency, `dictee` works normally but without visual feedback.

```bash
# Install from the .deb
sudo dpkg -i animation-speech_1.2.0_all.deb
```

> Download: [animation-speech releases](https://github.com/rcspam/animation-speech/releases) (.deb and .tar.gz)

#### ydotool-rebind (non-QWERTY keyboards)

`ydotool` simulates keystrokes to type transcribed text into the active application. By default, it uses a **QWERTY** layout — which produces incorrect characters on other keyboard layouts (e.g. `q` instead of `a` on AZERTY).

[ydotool-rebind](https://github.com/rcspam/ydotool-rebind) is a wrapper that fixes this by translating text to QWERTY before passing it to `ydotool`. Supported layouts: **French (fr)**, **German (de)**, **Belgian (be)**, **Italian (it)**, **Spanish (es)**. The layout is auto-detected from your system configuration.

```bash
# Install from the .deb
sudo dpkg -i ydotool-rebind_2.0.0_all.deb

# Override layout if needed
echo "LAYOUT=de" | sudo tee /etc/ydotool-rebind/config
```

> Download: [ydotool-rebind releases](https://github.com/rcspam/ydotool-rebind/releases) (.deb and .tar.gz)
>
> **Note:** Without ydotool-rebind, dictation will produce garbled text on non-QWERTY keyboards. Other layouts can be [easily added](https://github.com/rcspam/ydotool-rebind#adding-a-new-layout).

### Notification area icon

`dictee-tray` displays an icon in the panel's notification area showing the daemon status (active/stopped). The context menu allows starting/stopping the daemon, launching a dictation, or opening the configuration.

```bash
# Launch manually
dictee-tray

# Enable at session startup
systemctl --user enable dictee-tray
```

The icon automatically adapts to light/dark themes.

### Configuration

`dictee --setup` opens a graphical interface (GTK3) for configuring:

- **Keyboard shortcut**: capture and automatic registration (KDE Plasma / GNOME)
- **Translation**: enable/disable, backend choice (translate-shell or ollama), source and target languages

Preferences are saved in `~/.config/dictee.conf` and automatically loaded on each launch. CLI arguments (`--translate`, `--ollama`) always take priority over the configuration.

> For unsupported environments (Sway, i3, Hyprland...), the tool shows the command to configure manually in your window manager.

---

## Backend: transcription engine

The transcription engine is built on [parakeet-rs](https://github.com/altunenes/parakeet-rs) by [@altunenes](https://github.com/altunenes) for NVIDIA Parakeet model inference via ONNX Runtime.

### Features

- **Multilingual transcription**: 25+ languages (including French) via ParakeetTDT 0.6B
- **Diarization**: speaker identification (up to 4 speakers) via Sortformer
- **Real-time streaming**: chunk-by-chunk transcription via Nemotron (English only)
- **Any audio format**: WAV, MP3, OGG, FLAC, OPUS... automatic conversion via ffmpeg
- **Daemon mode**: model loaded once, near-instant transcriptions
- **Microphone recording**: PipeWire / PulseAudio / ALSA, auto-unmute
- **GPU or CPU**: CUDA, TensorRT, CoreML, DirectML, OpenVINO

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

## License

This project is distributed under the **GPL-3.0-or-later** license (see [LICENSE](LICENSE)).

The original [parakeet-rs](https://github.com/altunenes/parakeet-rs) code by Enes Altun is under the MIT license (see [LICENSE-MIT](LICENSE-MIT)).

The Parakeet ONNX models (downloaded separately from HuggingFace) are provided by NVIDIA. This project does not distribute the models.
