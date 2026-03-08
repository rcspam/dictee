# Promotion dictee

## Awesome-lists — Textes pour les PRs

### 1. awesome-rust (rust-unofficial/awesome-rust) — 56K stars

**Section :** `Applications > Audio and Music` ou `Applications > Text processing`

**Ligne à ajouter :**
```markdown
* [rcspam/dictee](https://github.com/rcspam/dictee) — Push-to-talk voice dictation for Linux. 100% local, multilingual (25+ languages), speaker diarization. Rust backend on NVIDIA Parakeet via ONNX Runtime. [![build badge](https://img.shields.io/github/v/release/rcspam/dictee)](https://github.com/rcspam/dictee/releases)
```

**Titre PR :** `Add dictee — local voice dictation for Linux`
**Description PR :**
```
Adds [dictee](https://github.com/rcspam/dictee), a push-to-talk voice dictation tool for Linux.

- 100% local speech-to-text using NVIDIA Parakeet-TDT 0.6B via ONNX Runtime
- Multilingual: 25+ languages with native punctuation
- Speaker diarization (up to 4 speakers)
- GTK3/Bash frontend, Rust backend
- Daemon mode for near-instant transcription
- GPL-3.0 license
```

---

### 2. Awesome-Linux-Software (luong-komorebi/Awesome-Linux-Software) — 25K stars

**Section :** `Applications > Utilities` ou `Applications > Accessibility`

**Ligne à ajouter :**
```markdown
- [dictee](https://github.com/rcspam/dictee) - Push-to-talk voice dictation for Linux. 100% local, multilingual (25+ languages), with speaker diarization. GTK3/Bash frontend, Rust/ONNX backend.
```

**Titre PR :** `Add dictee — local voice dictation for Linux`

---

### 3. awesome-alternatives-in-rust (TaKO8Ki/awesome-alternatives-in-rust) — 4K stars

**Section :** Alternatives to voice dictation tools (Dragon NaturallySpeaking, Google Dictation, etc.)

**Ligne à ajouter :**
```markdown
| [dictee](https://github.com/rcspam/dictee) | Dragon NaturallySpeaking, Google Dictation | Push-to-talk voice dictation for Linux — 100% local, multilingual (25+ languages), speaker diarization |
```

**Titre PR :** `Add dictee as alternative to Dragon NaturallySpeaking / Google Dictation`

---

### 4. awesome-kde (francoism90/awesome-kde) — 700 stars

**Section :** `Utilities` ou `Accessibility`

**Ligne à ajouter :**
```markdown
- [dictee](https://github.com/rcspam/dictee) - Push-to-talk voice dictation with GTK3 config UI, tray icon, and KDE Plasma shortcut integration. 100% local, 25+ languages.
```

**Titre PR :** `Add dictee — local voice dictation with KDE Plasma integration`

---

### 5. awesome-stt (sb-static/awesome-stt)

**Ligne à ajouter :**
```markdown
- [dictee](https://github.com/rcspam/dictee) — Push-to-talk voice dictation for Linux. Rust backend using NVIDIA Parakeet-TDT via ONNX Runtime. 100% local, multilingual (25+ languages), speaker diarization.
```

---

## Posts Reddit

### r/linux — Show-off post

**Titre :** `dictee — I built a 100% local voice dictation tool for Linux (push-to-talk, 25+ languages, Rust/ONNX)`

**Corps :**
```
I've been working on **dictee**, a push-to-talk voice dictation tool for Linux that runs entirely on your machine — no cloud, no API keys, no data leaving your computer.

**How it works:** press a keyboard shortcut to start recording, press again to stop. The speech is transcribed and typed directly at the cursor position in whatever app you're using.

**Key features:**
- 🗣️ **25+ languages** with native punctuation & capitalization (French, German, Spanish, etc.)
- 🔒 **100% local** — uses NVIDIA Parakeet-TDT 0.6B model via ONNX Runtime
- 🎤 **Speaker diarization** — identify up to 4 speakers in meetings
- ⚡ **Daemon mode** — model loaded once, subsequent transcriptions are near-instant
- 🖥️ **GTK3 config UI** + tray icon + KDE/GNOME shortcut integration
- 📦 **.deb packages** (CPU and CUDA variants)
- 🌐 **Optional translation** — via translate-shell or ollama (100% local with translategemma)

**Tech stack:** Rust backend (ONNX Runtime inference), Bash/Python/GTK3 frontend, systemd service.

Built on top of [parakeet-rs](https://github.com/altunenes/parakeet-rs) by @altunenes.

GitHub: https://github.com/rcspam/dictee
Releases: https://github.com/rcspam/dictee/releases

Would love feedback! What voice dictation tools do you currently use on Linux?
```

---

### r/rust — "What are you working on?" thread ou post dédié

**Titre :** `dictee — Local voice dictation for Linux, Rust backend with ONNX Runtime`

**Corps :**
```
I've been building **dictee**, a voice dictation tool for Linux with a Rust backend.

The Rust part handles the heavy lifting: loading NVIDIA Parakeet-TDT 0.6B models via `ort` (ONNX Runtime bindings), computing mel-spectrograms from audio (`rustfft` + `ndarray`), running the TDT decoder, and serving transcriptions through a Unix socket daemon.

**Rust crate highlights:**
- Custom mel-spectrogram pipeline (preemphasis → STFT → Slaney filterbank)
- Token-and-Duration Transducer (TDT) decoder
- Sortformer-based speaker diarization
- Unix socket server for daemon mode (model loaded once in memory)
- ~4,500 lines of Rust, built on [parakeet-rs](https://github.com/altunenes/parakeet-rs)

**End result:** press a shortcut, speak, text appears at your cursor. 25+ languages, 100% local.

Key dependencies: `ort` =2.0.0-rc.11, `ndarray`, `rustfft`, `hound`, `tokenizers`.

GitHub: https://github.com/rcspam/dictee

Happy to answer questions about ONNX Runtime in Rust or the audio processing pipeline!
```

---

### r/commandline — Tool announcement

**Titre :** `dictee — Push-to-talk voice dictation from the terminal (100% local, 25+ languages)`

**Corps :**
```
**dictee** is a push-to-talk voice dictation tool for Linux that transcribes speech and types it at the cursor position.

Quick start:
```bash
# Install
sudo dpkg -i dictee-cpu_0.99_amd64.deb

# Configure shortcut
dictee --setup

# Or use directly from the terminal
transcribe audio.mp3           # transcribe any audio file
transcribe-client              # record from mic, transcribe on Enter
transcribe-diarize meeting.wav # transcription + speaker identification
```

- 100% local (NVIDIA Parakeet-TDT via ONNX Runtime)
- 25+ languages with native punctuation
- Daemon mode: model loaded once, near-instant transcriptions
- Supports any audio format (automatic ffmpeg conversion)

GitHub: https://github.com/rcspam/dictee
```

---

### r/opensource — Project announcement

**Titre :** `dictee — Open source voice dictation for Linux, 100% local (GPL-3.0)`

**Corps :**
```
I'm sharing **dictee**, an open source voice dictation tool for Linux that runs entirely on your machine.

**Why another dictation tool?**
Most voice dictation solutions either require a cloud service (privacy concerns) or don't integrate well with Linux desktops. dictee aims to be the "just works" local alternative:

- Press a shortcut → speak → text appears at cursor
- 25+ languages with automatic punctuation
- Speaker diarization (who said what)
- KDE Plasma & GNOME integration
- .deb packages for easy installation

**Tech:** Rust backend (NVIDIA Parakeet-TDT 0.6B via ONNX Runtime), GTK3/Bash/Python frontend.
**License:** GPL-3.0

GitHub: https://github.com/rcspam/dictee

Built on [parakeet-rs](https://github.com/altunenes/parakeet-rs). Feedback welcome!
```

---

### r/kde

**Titre :** `dictee — Voice dictation for KDE Plasma (100% local, shortcut integration)`

**Corps :**
```
**dictee** is a push-to-talk voice dictation tool that integrates with KDE Plasma's shortcut system.

`dictee --setup` opens a GTK3 config window that lets you capture a keyboard shortcut and automatically registers it in Plasma. The tray icon (`dictee-tray`) shows daemon status and adapts to your Plasma theme.

- 25+ languages, 100% local (no cloud)
- Speaker diarization
- .deb packages available

GitHub: https://github.com/rcspam/dictee
```
