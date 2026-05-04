<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg">
    <img src="assets/banner-light.svg" alt="dictée" width="512">
  </picture>
</p>

<p align="center">
  <b><i>Speaking is just easier.</i></b>
</p>

<p align="center">
  <b>Speak freely, type instantly on <em>Wayland</em></b> (X11 compatible) — 100% local voice dictation for Linux with 25+ languages, 5 translation backends, speaker diarization, and real-time visual feedback. Text appears right where your cursor is.
</p>

<p align="center">
  <a href="https://github.com/rcspam/dictee/releases"><img src="https://img.shields.io/github/v/release/rcspam/dictee?label=release&color=blue&include_prereleases" alt="Latest Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-green" alt="License GPL-3.0"></a>
  <img src="https://img.shields.io/badge/backend-Rust-orange?logo=rust" alt="Rust">
  <img src="https://img.shields.io/badge/frontend-PyQt6%20%2F%20Bash-yellow" alt="PyQt6 / Bash">
  <img src="https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux" alt="Linux">
  <a href="https://github.com/rcspam/dictee/wiki"><img src="https://img.shields.io/badge/docs-wiki-blue" alt="Wiki"></a>
</p>

> 🎉 **v1.3.1 stable — May 2026.** Major changes since v1.2:
>
> - **`dictee-transcribe`** — new dedicated window for offline transcription of audio/video files. Timeline player synced with text, multi-tab, per-tab translation and LLM analysis, export to PDF / SRT / JSON / Markdown.
> - **Speaker diarization** up to 4 speakers via NVIDIA Sortformer, plus a chunked pipeline that lifts the VRAM cap on long files (54-min keynote diarized in 122 s).
> - **LLM analysis** on diarized transcripts — synthesis, chapters, ASR cleanup; 14 providers configurable side by side (Ollama, OpenAI, Claude, Gemini, Mistral, DeepSeek, Groq, Cerebras, OpenRouter…).
> - **Canary-1B v2** ASR backend (NVIDIA AED) with **built-in translation** on 12 native pairs — no external service needed.
> - **Portable CUDA libs** via pip venv at postinst — no NVIDIA repo required.
>
> v1.3.1 patch fixes: CUDA → CPU runtime fallback, `uinput` auto-load on Fedora/RHEL, strict setup-wizard checks. → [Release](https://github.com/rcspam/dictee/releases/tag/v1.3.1) · [Changelog](https://github.com/rcspam/dictee/wiki/Changelog)
>
> 📚 The full [**dictee wiki**](https://github.com/rcspam/dictee/wiki) is online — 24 pages covering installation, configuration, all 4 ASR backends (with Parakeet-TDT and Canary-1B deep-dives), post-processing, diarization, troubleshooting, and developer guide. Available in 🇬🇧 English and 🇫🇷 French.

<p align="center">
  <img src="assets/demo-dictee-1.3.1.gif" alt="dictee — push-to-talk demo: press F8, speak, text appears at the cursor" width="900">
</p>

<p align="center">
  <img src="assets/screenshots-vm/transcribe-diarize_1.3.png" alt="dictee-transcribe — file transcription with speaker diarization, audio player, and per-tab translation" width="900">
</p>

<p align="center">
  <a href="#what-is-dictee">What is dictee?</a> &bull;
  <a href="#quick-start">Quick start</a> &bull;
  <a href="#features">Features</a> &bull;
  <a href="#installation">Installation</a> &bull;
  <a href="#configuration">Configuration</a> &bull;
  <a href="#usage">Usage</a> &bull;
  <a href="#post-processing">Post-processing</a> &bull;
  <a href="#known-limitations">Limitations</a> &bull;
  <a href="#roadmap">Roadmap</a> &bull;
  <a href="https://github.com/rcspam/dictee/wiki">Wiki</a>
</p>

---

## What is dictee?

**dictee** is a complete voice dictation system for Linux. Press a shortcut, speak, and the text is typed directly into the active application — any application, any window, any text field.

Transcription is performed **100% locally** by default: no audio ever leaves your machine unless you explicitly choose a cloud translation backend.

- 🔒 **100% local by default** — Parakeet, Canary, faster-whisper and Vosk all run offline on your hardware
- 🌍 **25+ languages** — with native punctuation and capitalization (Parakeet-TDT)
- 🔀 **4 ASR backends** — switch instantly depending on language, latency and hardware
- 🎨 **Visual feedback** — KDE Plasma widget, system tray, or fullscreen animation

---

## Quick start

Three steps to go from zero to dictation in under two minutes:

**1. Install**

```bash
curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install.sh | bash
```

**2. Configure**

The first-run wizard walks you through backend selection, model download and keyboard shortcut binding. Re-run anytime with `dictee --setup`.

<p align="center">
  <img src="assets/screenshots-vm/wizard_1.3.png" alt="First-run setup wizard" width="720">
</p>

**3. Speak**

Press your shortcut (default **F9**), speak, release. The transcription appears at your cursor.

<p align="center">
  <img src="assets/screenshots-vm/plasmoid-cheat.png" alt="Plasmoid widget recording" width="720">
</p>

For detailed install paths (manual `.deb`/`.rpm`, GPU prerequisites, AUR, from source), see [Installation](#installation) below or the wiki's [Installation](https://github.com/rcspam/dictee/wiki/Installation) and [GPU-Setup](https://github.com/rcspam/dictee/wiki/GPU-Setup) pages.

---

## Features

### 4 ASR backends

| Backend | Languages | Model size | Warm latency | Notes |
|---------|-----------|------------|--------------|-------|
| **Parakeet-TDT 0.6B v3** | 25 | ~2.5 GB | ~0.8s CPU · ~0.16s GPU | Default, native punctuation |
| **Canary-1B v2** | 25 | ~5 GB | ~0.7s GPU | Built-in translation (25 ↔ EN, 48 pairs) |
| **faster-whisper** | 99 | ~500 MB–3 GB | ~0.3s | Wide language coverage |
| **Vosk** | 20+ | ~50 MB | ~1.5s | Lightweight, strict offline |

Each backend runs as a systemd user service with the same Unix socket protocol — switching is transparent. → [ASR-Backends wiki](https://github.com/rcspam/dictee/wiki/ASR-Backends)

### 5 translation backends

| Backend | Privacy | Speed | Quality | Languages |
|---------|---------|-------|---------|-----------|
| **Canary-1B** | 🔒 Local | Built-in | Excellent | 4 |
| **LibreTranslate** | 🔒 Local | 0.1–0.3s | Good | 30+ |
| **Ollama** | 🔒 Local | 2–3s | Excellent | Any (LLM) |
| **Google Translate** | 🌐 Cloud | 0.2–0.7s | Excellent | 130+ |
| **Bing Translator** | 🌐 Cloud | 1.7–2.2s | Very good | 100+ |

→ [Translation wiki](https://github.com/rcspam/dictee/wiki/Translation) · [Ollama-Setup](https://github.com/rcspam/dictee/wiki/Ollama-Setup)

### Post-processing pipeline

A 12-step configurable pipeline transforms raw ASR output before it hits your cursor:

- **Regex rules + dictionary** — 7 languages, ASR variants, voice commands → [Rules-and-Dictionary](https://github.com/rcspam/dictee/wiki/Rules-and-Dictionary)
- **LLM correction** — optional fluency polish via local Ollama (first / last / hybrid position) → [LLM-Correction](https://github.com/rcspam/dictee/wiki/LLM-Correction)
- **Numbers & dates** — cardinal, ordinal, versions, decimals, French times → [Numbers-Dates-Continuation](https://github.com/rcspam/dictee/wiki/Numbers-Dates-Continuation)
- **Continuation buffer** — continue a sentence across dictations with last-word memory
- **Short-text keepcaps** — per-language exceptions for acronyms and names (new in v1.3)

→ [Post-Processing-Overview](https://github.com/rcspam/dictee/wiki/Post-Processing-Overview)

### Speaker diarization (Meetings)

Answer *"who spoke when?"* in multi-speaker recordings via NVIDIA's **Sortformer** model. Up to 4 speakers, ideal for meeting notes and interviews. Triggered via **Meeting mode** or `dictee --meeting`. → [Diarization wiki](https://github.com/rcspam/dictee/wiki/Diarization)

<p align="center">
  <img src="assets/screenshots-vm/diarization-1_1.3.png" alt="Speaker diarization output" width="900">
</p>

<p align="center">
  <img src="assets/screenshots-vm/diarisation-2_1.3.png" alt="Speaker diarization — speaker labels" width="900">
</p>

### Transcribe audio & video files

Push-to-talk is dictee's main flow, but the bundled **`dictee-transcribe`** window also handles offline transcription of any audio or video file you already have. Multi-tab interface, audio player synchronised with the timeline, per-tab translation and LLM analysis, export to **PDF / SRT / JSON / Markdown**.

- **Any input format** (mp3, mp4, wav, opus, flac, mkv…) — auto-converted via ffmpeg
- **Multi-tab** — keep the original transcription side-by-side with translations and LLM analyses (summary, chapters, ASR cleanup…)
- **Speaker diarization** built-in — toggle on, get up to 4 speakers labelled and renamable
- **LLM analysis** — 14 providers configurable side by side (Ollama, OpenAI, Claude, Gemini, Mistral, DeepSeek, Groq, Cerebras, OpenRouter…)
- **Per-tab translation** — Canary / LibreTranslate / Ollama / Google / Bing

→ [LLM-Diarization wiki](https://github.com/rcspam/dictee/wiki/LLM-Diarization)

### 3 visual interfaces

- **KDE Plasma 6 widget** — native QML plasmoid, 5 animation styles, live state → [Plasmoid-Widget](https://github.com/rcspam/dictee/wiki/Plasmoid-Widget)
- **System tray icon** — PyQt6, works on GNOME/XFCE/Sway (AppIndicator fallback) → [Tray-Icon](https://github.com/rcspam/dictee/wiki/Tray-Icon)
- **animation-speech** (external) — fullscreen overlay on `wlr-layer-shell` compositors

All three share state via a filesystem watcher — any change is reflected instantly across interfaces (multi-user safe with UID suffix).

<p align="center">
  <img src="assets/screenshots-vm/plasmoid-cheat.png" alt="KDE Plasma plasmoid" width="720">
</p>

<p align="center">
  <img src="assets/screenshots-vm/tray_1.3.png" alt="System tray menu" width="360">
</p>

#### animation-speech (fullscreen overlay)

[animation-speech](https://github.com/rcspam/animation-speech) is a standalone project that provides a fullscreen visual animation during recording, with cancellation via the Escape key. It works on any Wayland compositor supporting `wlr-layer-shell` (KDE Plasma, Sway, Hyprland…).

<p align="center">
  <a href="https://youtu.be/-fWZZEO7mCA">
    <img src="assets/demo.gif" alt="animation-speech demo — click to watch on YouTube" width="640">
  </a>
</p>

```bash
sudo dpkg -i animation-speech_1.2.0_all.deb
```

> Download: [animation-speech releases](https://github.com/rcspam/animation-speech/releases)

> **Note:** animation-speech is not compatible with GNOME (no `wlr-layer-shell` support). GNOME users can rely on `dictee-tray` for visual feedback. Contributions for a GNOME Shell extension are welcome — see the [plasmoid source](plasmoid/) for reference architecture.

---

## Installation

### One-liner (recommended)

Auto-detects distro and GPU, adds the NVIDIA CUDA repo if needed, installs the right package:

```bash
curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install.sh | bash
```

Supported: **Ubuntu, Debian, Fedora, openSUSE, Arch Linux**. Other distros fall back to the tarball path.

**Options** (after `--`):

```bash
# Force CPU (skip GPU detection)
curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install.sh | bash -s -- --cpu

# Force GPU (CUDA)
curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install.sh | bash -s -- --gpu

# Pin a specific version
curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install.sh | bash -s -- --version 1.3.1

# Non-interactive
curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install.sh | bash -s -- --non-interactive
```

### Manual install

Download from [Releases](../../releases).

**Ubuntu / Debian (CPU):**

```bash
sudo apt install ./dictee-cpu_1.3.1_amd64.deb
```

**Ubuntu / Debian (GPU):** requires the NVIDIA CUDA APT repo — see [GPU-Setup](https://github.com/rcspam/dictee/wiki/GPU-Setup) for the one-time setup, then:

```bash
sudo apt install ./dictee-cuda_1.3.1_amd64.deb
```

**Fedora / openSUSE (CPU):**

```bash
sudo dnf install ./dictee-cpu-1.3.1-1.x86_64.rpm
```

**Fedora / openSUSE (GPU):** add the CUDA repo first (see [GPU-Setup](https://github.com/rcspam/dictee/wiki/GPU-Setup)), then `dictee-cuda-1.3.1-1.x86_64.rpm`.

**Arch Linux (AUR):** `PKGBUILD` in the repo root (x86_64 + aarch64). Clone + `makepkg -si`.

**aarch64 / Jetson:** no pre-built package — build from source. CUDA limited to NVIDIA Jetson boards.

**Other distros (tarball):**

```bash
tar xzf dictee-1.3.1_amd64.tar.gz
cd dictee-1.3.1
sudo ./install.sh
```

**From source:** `cargo build --release --features sortformer` then `sudo ./install.sh`. See [Developer-Guide](https://github.com/rcspam/dictee/wiki/Developer-Guide) for full Cargo features and package build scripts.

---

## Configuration

First launch triggers a **setup wizard** (backend, model, shortcuts).

<p align="center">
  <img src="assets/screenshots-vm/wizard_1.3.png" alt="First-run setup wizard" width="800">
</p>

Reconfigure anytime from the application menu, tray icon, Plasma widget, or by running:

```bash
dictee --setup
```

<p align="center">
  <img src="assets/screenshots-vm/dictee-setup_1.3.png" alt="Full configuration panel" width="800">
</p>

### Backend switching (one-liner)

```bash
# Show current backends
dictee-switch-backend status

# Switch ASR (parakeet · canary · whisper · vosk)
dictee-switch-backend asr canary

# Switch translation (canary · libretranslate · ollama · google · bing)
dictee-switch-backend translate ollama
```

The tray and plasmoid include backend sub-menus — no terminal required.

For detailed configuration (all ASR backends, translation matrix, plasmoid settings, keyboard shortcuts on tiling WMs), see the wiki:

- [ASR-Backends](https://github.com/rcspam/dictee/wiki/ASR-Backends) · [Translation](https://github.com/rcspam/dictee/wiki/Translation)
- [Plasmoid-Widget](https://github.com/rcspam/dictee/wiki/Plasmoid-Widget) · [Tray-Icon](https://github.com/rcspam/dictee/wiki/Tray-Icon)
- [Keyboard-Shortcuts](https://github.com/rcspam/dictee/wiki/Keyboard-Shortcuts) (KDE/GNOME/Sway/i3/Hyprland)

---

## Usage

```bash
# Simple dictation — transcribe and type
dictee

# Dictate + translate (default: system language → English)
dictee --translate
dictee --translate --ollama            # 100% local via Ollama

# Change target language
DICTEE_LANG_TARGET=es dictee --translate   # → Spanish

# Meeting mode (diarization, up to 4 speakers)
dictee --meeting

# Cancel ongoing dictation
dictee --cancel

# Test post-processing rules live
dictee-test-rules                       # interactive
dictee-test-rules --loop                # continuous loop
dictee-test-rules --wav file.wav        # from audio file
```

→ Full command reference: [CLI-Reference wiki](https://github.com/rcspam/dictee/wiki/CLI-Reference)

---

## Post-processing

dictee runs a **configurable 12-step pipeline** after transcription and before paste:

1. ASR variants normalization
2. Dictionary substitution
3. Numbers & dates conversion
4. Continuation buffer merge
5. Regex rules (pre-LLM)
6. LLM correction *(optional, first position)*
7. Regex rules (post-LLM)
8. Short-text exceptions (keepcaps)
9. Extended match mode
10. Final capitalization
11. Translation *(optional)*
12. Paste / inject

Configure via `dictee --setup` → **Post-processing** tab, or test rules live with `dictee-test-rules`.

<p align="center">
  <img src="assets/screenshots-vm/post-process-regex.png" alt="Regex rules editor" width="900">
</p>

<p align="center">
  <img src="assets/screenshots-vm/post-process-regex-test.png" alt="Regex rules with integrated test panel" width="900">
</p>

→ Deep dives: [Post-Processing-Overview](https://github.com/rcspam/dictee/wiki/Post-Processing-Overview) · [Rules-and-Dictionary](https://github.com/rcspam/dictee/wiki/Rules-and-Dictionary) · [LLM-Correction](https://github.com/rcspam/dictee/wiki/LLM-Correction) · [Numbers-Dates-Continuation](https://github.com/rcspam/dictee/wiki/Numbers-Dates-Continuation)

---

## Known limitations

- **Diarization + Parakeet on 8 GB GPU** is capped around **10–15 min of audio**. Parakeet-TDT loads the full mel-spectrogram in one pass (~185 MB VRAM per minute), which overflows consumer GPUs past ~15 min. Workarounds: split the file, disable diarization, or use the CPU backend. Auto-chunking is planned for the v1.3 final release. → [Diarization wiki](https://github.com/rcspam/dictee/wiki/Diarization)
- **AMD / Intel GPUs** are not currently supported — dictee falls back to CPU.
- **No real-time streaming** — Parakeet-TDT and Canary require the full utterance; only Nemotron (EN-only, via Rust binary) streams natively.

For bug reports and workarounds, see [Troubleshooting](https://github.com/rcspam/dictee/wiki/Troubleshooting).

---

## Roadmap

**v1.3.1 (current)** — **CUDA → CPU runtime fallback**: the CUDA package now probes `/proc/driver/nvidia/gpus/` at startup and falls back to CPU automatically on hosts without a usable NVIDIA driver (virtio VMs, headless containers, machines with the driver uninstalled), instead of crashing in a restart loop. Setup wizard's "ASR service" check is now strict (active state + open socket), so the final page can no longer report "Everything is ready" while the daemon is dead. New `DICTEE_FORCE_CPU=1` env override.

**v1.3.0** — Short-text keepcaps exceptions (7 languages), extended match mode, LibreTranslate purge models, continuation + translate fixes, version-number dictation, multi-user safe (UID suffix on state files), plasmoid cross-process toggles (LLM / Short / Meeting), 682 postprocess tests + 148 pipeline tests, theme-aware banner.

**v1.4+ (planned)**
- **Chunked diarization** — process files > 15 min via `transcribe-diarize-batch` (prototype validated: 54 min in 122 s)
- **Hotword boosting** — bias ASR decoding toward custom names (shallow fusion on TDT logits, Parakeet only)
- **Whisper translate** — multi-target translation via `task="translate"` (EN-only, offline)
- **Moonshine** CPU backend
- **CLI speech-to-text** — pipe audio, get text
- **VAD** — hands-free dictation without push-to-talk
- **Streaming transcription** with live text display
- **Built-in overlay** — replace external `animation-speech`
- **AppImage / Flatpak** packaging
- **COSMIC / GNOME Shell** applets (contributions welcome!)

→ Full history: [Changelog wiki](https://github.com/rcspam/dictee/wiki/Changelog)

---

## Credits

The transcription engine builds on [parakeet-rs](https://github.com/altunenes/parakeet-rs) by [Enes Altun](https://github.com/altunenes) — Rust library for NVIDIA Parakeet inference via ONNX Runtime. The Rust Canary implementation was originally ported from [onnx-asr](https://github.com/istupakov/onnx-asr) by [Ivan Stupakov](https://github.com/istupakov) and is now fully self-contained. Parakeet and Canary ONNX models are provided by NVIDIA (downloaded separately from HuggingFace, not redistributed by this project).

Keyboard input simulation uses [dotool](https://sr.ht/~geb/dotool/) by geb (GPL-3.0).

## License

This project is distributed under the **GPL-3.0-or-later** license (see [LICENSE](LICENSE)).

The original [parakeet-rs](https://github.com/altunenes/parakeet-rs) code by Enes Altun is under the MIT license (see [LICENSE-MIT](LICENSE-MIT)). [dotool](https://sr.ht/~geb/dotool/) is bundled under GPL-3.0.
