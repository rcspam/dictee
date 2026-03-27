<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg">
    <img src="assets/banner-light.svg" alt="dictée" width="640">
  </picture>
</p>

<p align="center">
  <b><i>Speaking is just easier.</i></b>
</p>

<p align="center">
  <b>Speak freely, type instantly</b> — 100% local voice dictation for Linux with 25+ languages, translation, speaker diarization, and real-time visual feedback. Text appears right where your cursor is.
</p>

<p align="center">
  <a href="https://github.com/rcspam/dictee/releases"><img src="https://img.shields.io/github/v/release/rcspam/dictee?label=release&color=blue" alt="Latest Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-green" alt="License GPL-3.0"></a>
  <img src="https://img.shields.io/badge/backend-Rust-orange?logo=rust" alt="Rust">
  <img src="https://img.shields.io/badge/frontend-PyQt6%20%2F%20Bash-yellow" alt="PyQt6 / Bash">
  <img src="https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux" alt="Linux">
</p>

<p align="center">
  <a href="#installation">Installation</a> &bull;
  <a href="#configuration">Configuration</a> &bull;
  <a href="#visual-interfaces">Visual interfaces</a> &bull;
  <a href="#usage">Usage</a> &bull;
  <a href="#going-further">Going further</a> &bull;
  <a href="#roadmap">Roadmap</a>
</p>

---

**dictee** is a complete voice dictation system for Linux. Transcription is performed **100% locally** — no audio data ever leaves your machine. Press a shortcut, speak, and the text is typed directly into the active application.

- **4 ASR backends**: [Parakeet-TDT](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx) (25 languages, native punctuation), [Canary-1B](https://huggingface.co/nvidia/canary-1b) (built-in translation, GPU), [Vosk](https://alphacephei.com/vosk/) (lightweight, ~50 MB), [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (99 languages)
- **Daemon mode**: model loaded once, near-instant transcriptions (~0.8s on CPU)
- **Translation**: 4 backends — Google, Bing, LibreTranslate (local), ollama (local)
- **Speaker diarization**: who said what, up to 4 speakers via Sortformer (CLI only, not yet in voice dictation)
- **3 visual interfaces**: KDE Plasma widget, notification area icon, fullscreen animation

<p align="center">
  <img src="plasmoid.png" alt="Plasmoid popup (recording)" width="520"><br>
  <img src="assets/wizard-en.png" alt="dictee --setup" width="720">
</p>

---

## Installation

Download the `.deb` from the [Releases](../../releases), then:

```bash
# GPU version (requires the NVIDIA CUDA repository — see "GPU dependencies" below)
sudo dpkg -i dictee-cuda_1.2.0_amd64.deb

# CPU version (any computer, no extra repository needed)
sudo dpkg -i dictee-cpu_1.2.0_amd64.deb

# Install missing dependencies
sudo apt-get install -f
```

> **Note:** The GPU version requires cuDNN from the [NVIDIA CUDA repository](#gpu-version-nvidia-cuda-dependencies), which is not included in standard Ubuntu/Fedora repos. Without it, the GPU version will still work but in CPU mode only.

**Fedora / openSUSE:**

```bash
# GPU version (NVIDIA CUDA — see "GPU dependencies" below)
sudo dnf install ./dictee-cuda-1.2.0-1.x86_64.rpm

# CPU version (any computer)
sudo dnf install ./dictee-cpu-1.2.0-1.x86_64.rpm
```

**Arch Linux (AUR):**

A `PKGBUILD` is available in the repository root. It builds from source and includes all components (x86_64 and aarch64).

**aarch64 (ARM64):**

Pre-built packages are x86_64 only. On aarch64 (Raspberry Pi 5, Ampere, etc.), build from source — see below. CUDA is limited to NVIDIA Jetson on this architecture; most users will use CPU mode.

**Other distributions (.tar.gz):**

```bash
tar xzf dictee-1.2.0_amd64.tar.gz
cd dictee-1.2.0
sudo ./install.sh
```

**From source:**

```bash
tar xzf dictee-1.2.0-source.tar.gz
cd dictee-1.2.0-source
cargo build --release --features sortformer
sudo ./install.sh
```

> For detailed build instructions and Cargo features, see [docs/building.md](docs/building.md).

### GPU version: NVIDIA CUDA dependencies

The GPU version (`dictee-cuda`) requires cuDNN, which is **not available** in standard Ubuntu/Fedora repositories. You need the NVIDIA CUDA repository:

**Ubuntu / Debian:**

```bash
wget -qO - https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/3bf863cc.pub | \
  sudo gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] \
  https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/ /" | \
  sudo tee /etc/apt/sources.list.d/cuda-ubuntu2404-x86_64.list
sudo apt update
sudo apt install libcudnn9-cuda-12
```

> Replace `ubuntu2404` with your version (`ubuntu2204`, `ubuntu2504`, etc.). See [NVIDIA CUDA repos](https://developer.download.nvidia.com/compute/cuda/repos/).

**Fedora:**

```bash
sudo dnf config-manager addrepo --from-repofile=https://developer.download.nvidia.com/compute/cuda/repos/fedora41/x86_64/cuda-fedora41.repo
sudo dnf install libcudnn9-cuda-12
```

> Without cuDNN, the GPU version falls back to CPU automatically. `dictee-setup` will detect this and guide you through the setup.

### Dependencies

| Debian / Ubuntu | Fedora / openSUSE | Arch Linux |
|-----------------|-------------------|------------|
| `pipewire` | `pipewire` | `pipewire` |
| `dotool` | — (bundled) | `dotool` |
| `ffmpeg` | `ffmpeg-free` | `ffmpeg` |
| `libnotify-bin` | `libnotify` | `libnotify` |
| `python3-pyqt6` | `python3-pyqt6` | `python-pyqt6` |
| `python3-pyqt6.qtmultimedia` | `python3-qt6-multimedia` | `python-pyqt6-multimedia` |
| `python3-gi` | `python3-gobject` | `python-gobject` |
| `wl-clipboard` / `xclip` | `wl-clipboard` / `xclip` | `wl-clipboard` / `xclip` |

---

## Configuration

After installation, run `dictee --setup` to configure everything from a graphical interface:

<p align="center">
  <img src="assets/dictee-setup.png" alt="dictee --setup" width="720">
  <img src="assets/postprocess.png" alt="Post-processing dictionary" width="720">
</p>

### ASR backend

Four mutually exclusive transcription backends, switchable from `dictee --setup`:

| Backend | Languages | Model size | Warm daemon | Type |
|---------|-----------|------------|-------------|------|
| **Parakeet-TDT** (default) | 25 | ~2.5 GB | ~0.8s | ONNX Runtime (Rust) |
| **Canary-1B** | 4 (EN,ES,FR,DE) | ~5 GB | ~0.7s (GPU) | ONNX Runtime (Python, GPU recommended) |
| **Vosk** | 9+ | ~50 MB | ~1.5s | Python (lightweight) |
| **faster-whisper** | 99 | ~500 MB–3 GB | ~0.3s | CTranslate2 (Python) |

Each backend runs as a systemd user service — same Unix socket protocol, fully transparent to the user.

### Keyboard shortcuts

`dictee --setup` captures and registers shortcuts automatically (KDE Plasma / GNOME). Two separate shortcuts: one for dictation, one for dictation + translation.

> For tiling WMs (Sway, i3, Hyprland…), the tool shows the command to add manually to your config.

### Translation

| Backend | Privacy | Speed | Quality | Setup |
|---------|---------|-------|---------|-------|
| **translate-shell** (Google) | Online | 0.2–0.7s | Good | `apt install translate-shell` |
| **translate-shell** (Bing) | Online | 1.7–2.2s | Good | `apt install translate-shell` |
| **LibreTranslate** | 100% local | 0.1–0.3s | Good | Docker (~2 GB image) |
| **ollama** | 100% local | 2.3–3.4s | Best | ollama + translategemma model |

### Quick backend switching

Switch ASR or translation backend instantly from the command line, the tray icon menu, or the Plasma widget:

```bash
# Switch ASR backend
dictee-switch-backend asr canary

# Switch translation backend
dictee-switch-backend translate ollama

# Show current backends
dictee-switch-backend status
# → ASR: parakeet (dictee.service, active)
# → Translate: google (trans)
```

The tray icon and Plasma widget include sub-menus for switching backends without opening the configuration.

---

## Visual interfaces

### KDE Plasma widget

A native KDE Plasma 6 widget with real-time audio visualization during recording, daemon status, and quick controls (dictate, translate, cancel).

<p align="center">
  <img src="plasmoid.png" alt="Plasmoid popup (recording)" width="500">
</p>

<p align="center">
  <img src="plasmoid_config.png" alt="Plasmoid configuration" width="600">
</p>

Five animation styles with Hanning envelope, per-style sensitivity, and optional color gradients:

| Bars | Wave | Pulse | Dots | Waveform |
|:----:|:----:|:-----:|:----:|:--------:|
| ![Bars](plasmoid/assets/anim-bars.svg?v=2) | ![Wave](plasmoid/assets/anim-wave.svg) | ![Pulse](plasmoid/assets/anim-pulse.svg) | ![Dots](plasmoid/assets/anim-dots.svg) | ![Waveform](plasmoid/assets/anim-waveform.svg) |

All styles support color gradients, adjustable Hanning envelope (shape and center frequency), per-style sensitivity curve, and fine-tuning options (bar count, spacing, radius, speed…).

```bash
# Install (included in .deb, or manually)
kpackagetool6 -t Plasma/Applet -i /usr/share/dictee/dictee.plasmoid
```

Right-click on the panel → "Add Widgets…" → search for "Dictée".

> For full widget settings documentation, see [docs/plasmoid.md](docs/plasmoid.md).

### Notification area icon (dictee-tray)

`dictee-tray` is the alternative to the KDE Plasma widget for non-KDE desktops (GNOME, Xfce, Sway, Hyprland…). It displays a notification area icon reflecting the real-time state: idle, recording (green), transcribing (blue), daemon stopped (red).

<p align="center">
  <img src="tray.png" alt="dictee-tray context menu" width="400">
</p>

- Left click → start dictation
- Middle click → cancel
- Context menu → all actions (dictation, translation, daemon, configuration)

```bash
# Launch manually
dictee-tray

# Enable at session startup
systemctl --user enable --now dictee-tray
```

The icon automatically adapts to light/dark themes.

Both the Plasma widget and the tray icon include:
- **Backend selectors** — switch ASR and translation backends without opening `dictee-setup`
- **First-run detection** — prompts to run the setup wizard if not yet configured
- **Install detection** (Plasma widget) — shows a clear message if dictee is not installed

### animation-speech

[animation-speech](https://github.com/rcspam/animation-speech) is a standalone project that provides a fullscreen visual animation during recording, with cancellation via Escape key. It works on any Wayland compositor supporting `wlr-layer-shell` (KDE Plasma, Sway, Hyprland…).

<p align="center">
  <a href="https://youtu.be/-fWZZEO7mCA">
    <img src="assets/demo.gif" alt="animation-speech demo — click to watch on YouTube" width="640">
  </a>
</p>

```bash
sudo dpkg -i animation-speech_1.2.0_all.deb
```

> Download: [animation-speech releases](https://github.com/rcspam/animation-speech/releases)

> **Note:** animation-speech is not compatible with GNOME (no `wlr-layer-shell` support). GNOME users can use `dictee-tray` for visual feedback. Contributions for a GNOME Shell extension are welcome — see the [plasmoid source](plasmoid/) for reference architecture.

Without any visual interface, `dictee` works normally but without visual feedback during recording.

---

## Usage

```bash
# Simple dictation — transcribe and type
dictee

# With translation (default: system language → English)
dictee --translate
dictee --translate --ollama    # 100% local translation via ollama

# Change translation languages
DICTEE_LANG_TARGET=es dictee --translate    # → Spanish

# Cancel an ongoing recording (via shortcut or Escape key)
dictee --cancel

# Test post-processing rules
dictee-test-rules                    # interactive mode
dictee-test-rules --loop             # continuous test loop
dictee-test-rules --wav file.wav     # test from audio file

# Switch backend from command line
dictee-switch-backend status         # show current backends
dictee-switch-backend asr canary     # switch to Canary
dictee-switch-backend translate bing # switch translation to Bing
```

---

## Going further

### Post-processing

dictee includes a configurable text transformation pipeline that runs after transcription:

- **Custom rules** — regex-based text replacements (e.g., voice commands like "new line", "comma")
- **Dictionary** — replace common ASR mistakes with correct words
- **Continuation** — detect incomplete sentences across multiple dictations
- **Elisions** — French grammar rules (e.g., "le arbre" → "l'arbre")
- **Number conversion** — spoken numbers to digits (e.g., "vingt-trois" → "23")
- **Auto-capitalization** — capitalize after sentence-ending punctuation
- **LLM correction** — optional grammar/spelling fix via Ollama before rules

Configure from `dictee --setup` → Post-processing tab, or test rules with `dictee-test-rules`.

<p align="center">
  <img src="assets/postprocess.gif" alt="Post-processing: dictionary, regex rules, continuation" width="800">
</p>

| Documentation | Description |
|---------------|-------------|
| [docs/cli-programs.md](docs/cli-programs.md) | CLI binaries, direct usage, ONNX models |
| [docs/building.md](docs/building.md) | Building from source, Cargo features, audio pipeline |
| [docs/plasmoid.md](docs/plasmoid.md) | Widget settings, animation styles, configuration details |
| [Post-processing](docs/postprocessing.md) | Text transformation pipeline: rules, dictionary, elisions, text2num, capitalization, LLM correction |

---

## Roadmap

**v1.2.0 (current):** 4 ASR backends (+ Canary), post-processing pipeline, quick backend switching, first-run wizard, `dictee-test-rules`

- (v1.3) **Hotword boosting** — bias ASR decoding toward custom names and terms without retraining (beam search + Aho-Corasick in Rust)
- Diarization from tray/plasmoid — select audio file, get speaker-labeled transcription
- CLI for speech-to-text (pipe audio, get text)
- `dictee-ctl` coordinator — single entry point, eliminates race conditions
- VAD (Voice Activity Detection) — hands-free dictation without push-to-talk
- Real-time streaming transcription with live text display
- Built-in visual overlay (replace external `animation-speech`)
- AppImage / Flatpak packaging
- COSMIC / GNOME applet (contributions welcome!)

## Credits

The transcription engine is built on [parakeet-rs](https://github.com/altunenes/parakeet-rs) by [Enes Altun](https://github.com/altunenes), which provides the Rust library for NVIDIA Parakeet model inference via ONNX Runtime. The Canary-1B backend uses [onnx-asr](https://github.com/istupakov/onnx-asr) by [Ivan Stupakov](https://github.com/istupakov) for ONNX-based ASR inference.

## License

This project is distributed under the **GPL-3.0-or-later** license (see [LICENSE](LICENSE)).

The original [parakeet-rs](https://github.com/altunenes/parakeet-rs) code by Enes Altun is under the MIT license (see [LICENSE-MIT](LICENSE-MIT)).

[dotool](https://sr.ht/~geb/dotool/) by geb is bundled for keyboard input simulation and is under the GPL-3.0 license.

The Parakeet ONNX models (downloaded separately from HuggingFace) are provided by NVIDIA. This project does not distribute the models.
