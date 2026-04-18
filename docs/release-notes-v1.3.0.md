# dictee 1.3.0

361 commits since v1.2.0 · 234 files changed · +58 302 / −11 868 lines.

## 🎯 Highlights

- **LLM-powered post-processing** — optional contextual corrector via the Ollama HTTP API, with configurable position in the pipeline (before or after regex rules).
- **Rebuilt post-processing pipeline** — three selectable modes (PP only / PP + translation / full chain), a mirror pipeline with independent rules for the translation branch, and a dedicated test panel with live configuration.
- **Native Rust Canary + Whisper large-v3-turbo** — the Canary AED backend now runs natively in Rust with `decodercontext` for smooth multi-language switching, and Whisper `large-v3-turbo` (809 M params) joins the model list.
- **Two-phase diarisation with a real state machine** — Sortformer pre-pass, dynamic VRAM thresholds, post-diarisation speaker renaming UI, and automatic Parakeet switch/restore.
- **Audio context buffer** — word-level timestamps now carry context across utterances, making continuation (`>>`) far more reliable; `sox` replaces `ffmpeg` for 20–40× faster audio trimming.
- **Redesigned first-run wizard** — new ASR / translation cards, hardware detection, in-memory temporary config until the final checks page, install validation for Vosk / Whisper / Canary, and a clean cancel flow.
- **New setup UI with sidebar + clickable SVG pipeline** — persistent sidebar navigation, a live SVG pipeline for post-processing with per-step tooltips and toggles, an About page with update check, and a Plasma-style `ToggleSwitch` widget throughout.

---

## 🧠 New AI capabilities

### ASR backends & models
- **Canary AED** ported from the Python `onnx-asr` daemon to a native Rust backend, with `decodercontext` for smooth multi-language switching.
- **Whisper `large-v3-turbo`** (809 M params, multilingual, fast) added, with HF cache detection for the `mobiuslabsgmbh` repo.
- WER benchmark automated against LibriSpeech for every Whisper model (tiny → large-v3).
- Shared Python module `dictee_models.py` as the single source of truth for ASR model management.
- `dictee-setup --models [--json]` lists installed models from the CLI (replaces the removed `dictee-models` helper).
- ✓ green / ✗ red availability indicators for Whisper and Vosk combo boxes, plus a coloured status label under each combo.
- Unavailable backends are greyed out everywhere (tray, plasmoid, backend switcher).
- Audio context is auto-skipped for Whisper `large-v3`, `turbo` and `distil` variants where word-level DTW is unreliable.

### LLM post-processing (Ollama)
- Optional contextual corrector through the **Ollama HTTP API**, selectable as a radio button.
- Configurable position in the pipeline (before or after regex rules).
- `num_gpu` now set through the API instead of an environment variable.
- Ollama entries greyed out everywhere when the model is not downloaded.
- Detailed offline notifications with status shown in both plasmoid and setup.

### Audio context buffer
- New buffer that carries word-level timestamps across utterances, making continuation (`>>`) far more reliable.
- Toggles surfaced in dictee-setup, plasmoid popup and tray menu; enabled by default.
- `dictee-switch-backend context` command added for scripting.
- **`sox` replaces `ffmpeg`** for concat/trim operations (20–40× faster).
- Word-level timestamps implemented for Canary and Whisper; Canary AED falls back gracefully when timestamps are unavailable.
- 0.5 s safety margin on the timestamp threshold.
- Auto-disabled for backends where DTW is degraded (non-Parakeet).
- Transcription text is never written to debug logs.

### Diarisation (Sortformer)
- **Two-phase flow**: Sortformer pass first, then the daemon socket.
- Diarisation button with a full state machine (`idle → preparing → ready → recording`), replacing the previous checkbox.
- Automatic **Parakeet backend switch** with restoration after diarisation.
- **Post-diarisation speaker renaming UI** in `dictee-transcribe`.
- `--sensitivity` flag on `transcribe-diarize` for the speaker-detection threshold.
- `diarizing` visual state greys transcription buttons during the pass.
- Plasmoid animation: blinking during switch, solid green when ready.
- **Dynamic VRAM thresholds**: 5 GB required for diarisation, 3.5 GB otherwise; daemon and Ollama are only unloaded when free VRAM < 2 GB.
- Diarisation deliberately skips the PP / translation / LLM chain (by design).
- Diarisation greyed out when the active backend is not Parakeet.
- `F9` protected during the diarize-ready phase; WAV copied before live diarisation to avoid a race on deletion.

---

## 🌍 Translation overhaul

- **Multi-language translation** with a dynamic target-language combo box and D-Bus notifications.
- Source ↔ target language swap button (⇅) on the translation page.
- **Persistent Docker volume** for LibreTranslate models, with a "Purge models" button showing the real volume size.
- Language combo refreshes automatically after LibreTranslate start/stop/restart.
- Green status label for the active translation backend, with auto-refresh via `QFileSystemWatcher`.
- Canary source ↔ target swap correctly handled, with matching ASR rules (`l'eux`, `l'e`).
- Translation error messages are now detailed; an error sound plays and status is reflected in both plasmoid and setup.
- CJK translation fixed; LibreTranslate volume sync and plasmoid target language consistent.
- LibreTranslate-stopped state handled cleanly across the UI.
- Uninstalled translation backends are greyed out everywhere.
- "Apply" no longer shows a duplicate "restart LibreTranslate" prompt.
- Full i18n for every new translation string across 6 languages.

---

## 🎚️ Post-processing rebuilt

### Pipeline & modes
- **Three selectable pipeline modes**: PP only / PP + translation / full chain — a single combo box replaces the two previous master switches.
- `DICTEE_PIPELINE_MODE` persisted in `dictee.conf` and honoured by the shell pipeline.
- **Mirror pipeline (blue / orange)** — a second PP run is applied to the translation branch with independent rules.
- Unified masters with independent blue/orange states, per-step and per-sub-page greying when a master is off.
- Translation PP enabled by default.
- Simplified orange SVG, with a clickable translate icon that opens the Translation menu.
- Canary green notice restored on the translation page.
- Full 6-language i18n for TRPP persistence and UI strings.

### Test panel
- Complete redesign: live configuration, highlight, indicator, anti-copy-paste artefacts.
- `QComboBox` with 3 pipeline modes and icons inside the test panel, synced bidirectionally with the PP combo.
- Keyword continuation support inside the test panel.
- Continuation works in translation mode with proper indentation.
- Re-run across languages after saving dictionary/rules.
- Silence indicator 🔇, clear button, translated continuation output.

### Rules & keepcaps
- Full **keepcaps UI editor** on the PP page: enriched word list, UI toggles, FR translations, extended matching (short words, first-word, preserved voice commands).
- Programming-symbol rules added (currencies, parentheses, operators).
- French **"tiret du six"** (→ `-`) and **"tiret du huit"** (→ `_`).
- Plural and bracket variants (open/close parenthesis, etc.).
- **Decimal comma** in FR/DE/ES/IT/PT: `"1, 5"` → `"1,5"`.
- "X point Y point Z" → `X.Y.Z` version-style conversion.
- **Auto short-text correction** (< 3 words): lowercase + trailing period removal, while preserving voice commands (punctuation, line breaks).
- Leading punctuation stripped from ASR output.
- Regex rules editor now saved by "Apply".
- Keepcaps rollout audits (blockers, major issues, robustness).

### Continuation (`>>`)
- **Configurable continuation indicator** via `DICTEE_CONTINUATION_INDICATOR`, with a dedicated combo box in the Continuation tab and dynamic backspace for the `_` marker.
- Full edition of system words in advanced mode.
- Keyword continuation **"minuscule"** replaces "contre-point".
- Separate keyword section in the tab, with a visual `&` section.
- Stripping of `>>` together with the FR NNBSP/NBSP typo at push start.
- Word preserved when Whisper output ends with `…`.
- FR continuation list cleaned up: ambiguous transitive verbs removed, `"ce"` kept, `"ça"` dropped (false positives).
- Scroll recomputes on fold/unfold (FlowLayout no longer miscomputes chip height in collapsed groups; walks parent chain for hidden ancestors; canonical Qt fix with real `sizeHint` + `Maximum` vertical size policy).
- Indicator length encoded in the `H<N>` marker; `_sanitize_conf_value` no longer strips `<`, `>`, `&`.
- Empty `last_word` guarded in `apply_continuation`; marker saved even on punctuation-only input; stray `&` on punctuation eliminated.
- New CI job `test-apply-continuation`.

### Voice commands & suffix
- Voice-commands **suffix** field in dictee-setup, persisted in `dictee.conf`.
- Language combo for both continuation keyword and command suffix.
- Suffix pre-filled by default for every language (FR defaults to `final[es]`).
- Multilingual suffix tooltip with variants aligned under the field; `?` helper buttons with detailed tooltips.
- Suffix tolerates the Parakeet-induced parasite "s" (e.g. `suivi` / `suivis`).

---

## 🎨 Redesigned setup & plasmoid

### First-run wizard
- Complete redesign with **ASR / translation cards** and hardware detection.
- Explanatory dialog shown before the wizard when no config exists.
- **Install validation** for Vosk / Whisper / Canary before "Next".
- Wizard writes to a **temporary config** until the checks page, cleaned up on cancel.
- `_on_apply` only runs on "Finish", never earlier.
- Defaults: hold + same key + Alt for translation.
- `DICTEE_SETUP_DONE=true` marker for wizard completion.
- Quit button, in-memory config, tray included in visual feedback.
- **Trash buttons** for Vosk/Whisper venvs and models, with 100 % i18n.
- `strip_period` defaults to `false` in wizard mode.
- `dictee-transcribe` now warns when dictee is not yet configured.
- **Light theme support** throughout the wizard, with theme-aware colours.

### dictee-setup sidebar navigation
- **Sidebar mode** with a persistent SVG pipeline on every page.
- **About page** with built-in update check.
- SVG navigation semantics: first click navigates, second click toggles, with i18n tooltips.
- Master language switch surfaced directly on the clickable SVG pipeline.
- HTML multi-line SVG tooltips via `QEvent.ToolTip`.

### dictee-transcribe (file transcription UI)
- Full UI redesign with multi-format export and detailed error handling.
- `--debug` flag and PySide6 compatibility.
- `--translation` deep link that scrolls to the translation `QGroupBox`.
- `dictee-setup --translation` entry point and "Configure translation" button.
- Works in both wizard and classic modes.
- Backend restoration moved to `closeEvent` instead of the dictee wrapper.
- i18n and packaging brought in line with the rest of the suite.

### Widgets & layout
- New **Plasma-style `ToggleSwitch`** widget replacing `QCheckBox` across the setup UI.
- **Braille spinner** (32 frames / 30 fps) inside the "Apply" button, with an event loop pump.
- Parallel `systemctl` calls during `_on_apply`.
- Pulse animations on dictation/translation buttons during recording.
- Apply no longer forces a daemon restart for PP toggles.
- Apply now saves continuation, dictionary, rules and main config in one shot.
- Tabs and checkboxes reordered to match the SVG pipeline; checkboxes duplicated by the SVG are hidden; the LLM tab moved to the end.
- Short text + LLM condensed on a single line.
- Regex-rules warning now shown as a dismissable popup instead of a permanent label; setup never reopens on the "Regex rules" tab by default.
- Dictionary undo/redo: icon-only buttons (30 px).
- External `QScrollArea` removed from the PP page (fixes sidebar-resize lag).
- Non-expanding accordions; `SizePolicy.Maximum` enforced for `ToggleSwitch` and accordions.
- Microphone slider capped at 60 %, without tick marks.
- Continuation/dictionary scroll recomputes on fold/unfold.
- Seven small PP-tab adjustments (alignment, spacing, labels).
- **Theme-aware styling** across dictee-setup.

### Plasmoid
- **Audio-source selector** (microphone / monitor 🔊 / application 📺) inline on the daemon row, backed by PipeWire (`pw-dump` + `node.name`) with a refresh button.
- **Vertical level meter** next to the selector, re-started automatically when the source changes.
- `dictee-audio-sources` helper script to list PipeWire sources.
- `dictee-plasmoid-level-daemon` auto-resolves the monitor for application sources.
- Microphone **volume slider** in the popup.
- **Light theme** supported, with a reset-to-defaults button on the icon.
- Popup width stabilised (min 28, preferred 36, max 40 gridUnit).
- Backend selectors hidden until the wizard has completed.
- Tooltips added on every button, fully translated in FR (and 5 other languages).
- Fixed clicks blocked by flickering tooltips.
- Points-clignotants and pulse animation during recording; waveform visibility and defaults tuned (bars 15, wave 60, dots 10, waveform 17).
- Preview checkbox restored (without the confusing "mic test" label).
- Layout: Preview on the left, actions stacked on the right.
- Audio-context checkbox placed between the ASR combo and the translation combo, and the tool-button version sits to the right of "Configure Dictée".
- Arrow → removed between the translation combo and the language combo.
- `dicteeConfigured` now initialised to `false` (was `true`).
- Refactored to a **pure state reader** — no local state, relies entirely on the state file.

### Audio sources & microphone calibration
- **Audio-source selection**: microphone, monitor, application output.
- **RMS silence threshold** with a calibration lab and a pipelines accordion.

---

## ⚙️ Reliability & architecture

### State-file authority (major refactor)
- The state file becomes the **single source of truth** across the stack.
- Tray, plasmoid and PTT are now **pure state readers** with no local state.
- `dictee start/stop/cancel` now switch on the state file.
- `dictee --diarize` flag simplified.
- `dictee-switch-backend` writes `preparing` / `diarize-ready` into the state file.
- **Fixed notification ID** eliminates race conditions on replace/close; persistent notifications are properly closed in every exit path and in `cleanup_on_error`.

### Keyboard shortcuts & PTT
- `Ctrl+J` shortcut, visual `&` for continuation, hard `F9` blocking during diarize-ready.
- PTT snapshot no longer shadows `gettext _`.
- Keyboard guard against sticky modifiers and escape sequences.
- `F9` blocked during `diarize-ready` without `--diarize`, with stale `DICTEE_DIARIZE` cleaned up.
- `F9` no longer blocked after reboot when the state file is absent from `/dev/shm` at first boot.
- UID suffix on `PIDFILE` and `OWN_PIDFILE` (multi-user safety).
- `TRANSLATE_FLAG` UID, `PIDFILE.lock` cleanup, `ComboBox` binding.

### Refactor & cleanup
- New `dictee-common.sh` with shared helpers used by every dictee script.
- Seven utility functions extracted from the main `dictee` entry-point script.
- Duplicated patterns factored out of `switch-backend` and `reset`.
- All French comments translated to English inside shell scripts (consistency).
- `DICTEE_ANIMATION` split into `DICTEE_ANIM_SPEECH` and `DICTEE_ANIM_PLASMOID`.
- Local directory now prioritised over `/usr/lib/dictee` in `sys.path`.
- QThread signals renamed `finished` → `done` to avoid the `QThread.finished` clash.
- HF Whisper cache paths centralised across cancel / delete / detect flows.
- Plasmoid reset button reads defaults from `main.xml`.
- `save_config()` preserves comments and sanitises shell-injection attempts.
- Alpha/Bravo audio marker removed (replaced by word-level timestamps).
- Legacy `transcribe-daemon-canary` binary removed.

### Robustness (multiple audit passes)
- Paranoid audit #1 (4 bugs) and audit #2 (9 bugs) on daemon robustness.
- Daemon issues fixed at high (3), medium (3) and low priority (state-switching, idle after `daemon_start`).
- Daemon now uses `restart` + `reset-failed` instead of `start`.
- Polling on daemon start replaces the single 2 s check.
- Daemon start now reads `dictee.conf` instead of `is-enabled`.
- Boot-time enable verifies return codes and the Canary preset.
- **Smart VRAM handling**: daemon and Ollama are only stopped when free VRAM < 2 GB; VRAM is freed before transcription (daemon stop + Ollama unload); dynamic threshold of 5 GB for diarisation, 3.5 GB otherwise.
- Double-cancel race no longer re-enters the diarisation branch.
- Offline daemon notifications handled cleanly; complete offline stop-daemon flow with configurable notifications and F9 protection.
- Cancel race conditions covered by stress tests.
- Full diarisation tray/F9 flow; silence notifications; removal of dead code.
- Silence notification closed properly; PySide6 imports cleaned up; duplicated tooltip fixed.
- Exhaustive pre-merge audit for devel-1.3 → master.

### Debug & observability
- `DICTEE_DEBUG=true` toggles debug logging everywhere: shell scripts, Rust binaries, plasmoid, tray.
- 37 trace points in dictee-setup, exposed through `--help` and `--debug`.
- Debug checkbox added in dictee-setup (Options section).
- Debug logging added to the `diarize-only` and `transcribe-diarize` Rust binaries.
- Diarisation segment logs restored (timestamps + speaker IDs).
- **Transcription content is never written to debug logs** (privacy).

### Security
- `save_config()` sanitises shell-injection attempts.
- Multi-user UID audit on keepcaps configuration (blocker fixed).
- `_sanitize_conf_value` strips `<`, `>`, `&` to prevent marker corruption.

---

## 📦 Packaging & distribution

### One-liner online installer (new)
- **`install-online.sh`** — one-shot installer hosted on GitHub, invoked as `curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install-online.sh | bash`.
- Auto-detects the distro family (Ubuntu / Debian / Fedora / openSUSE / Arch) and falls back to the tarball installer elsewhere.
- Auto-detects an NVIDIA GPU and prompts CPU vs GPU (reads from `/dev/tty` so it works when piped).
- Adds the NVIDIA CUDA APT repository automatically on Ubuntu/Debian (cuda-keyring), adds the openSUSE CUDA repo via `zypper addrepo`, and on Arch it picks up `yay` / `paru` to install the AUR-only `dotool` dependency.
- Runtime fallback when a NVIDIA repo version doesn't exist yet for a brand-new distro release (HEAD request + older-repo fallback).
- Flags: `--cpu`, `--gpu`, `--version X.Y.Z`, `--non-interactive`, `--help`.
- Companion **`uninstall-online.sh`** auto-detects the install method (`dpkg`, `rpm`, `pacman`, or tarball) and calls the right remover. `--purge` also wipes `~/.config/dictee`, ONNX models and the LibreTranslate Docker volume.

### CUDA build
- Full CUDA build support: `load-dynamic` flag, `libonnxruntime.so`, CUDA 12 deps and intelligent postinst.
- CUDA runtime libraries (`libcufft.so.11`, `libcudart.so.12`) bundled inside the CUDA `.deb` / `.rpm`.
- `/etc/ld.so.conf.d/dictee.conf` shipped so `/usr/lib/dictee/` is picked up by the dynamic linker; `ldconfig` run from the `postinst`.

### Debian (`.deb`)
- `build-deb.sh` now generates both `dictee-cpu` and `dictee-cuda` packages plus a `dictee-plasmoid` package and a `.tar.gz`.
- Stray `*.so.*` files properly excluded from the CPU `.deb` (they were leaking 278 MB of CUDA libs).
- Postinst refreshes the icon cache, fixes the dotool udev rule (`0620 → 0660`), reloads systemd user services for every logged-in user and auto-enables the correct ASR daemon based on the per-user `dictee.conf`.

### Fedora / openSUSE (`.rpm`)
- `build-rpm.sh` mirrors the `.deb` layout: separate CPU/CUDA packages, ld.so.conf entry, same bundled CUDA libs.
- RPM plasmoid now installs to the correct `/usr/share/plasma/plasmoids/` path.
- `dnf install` used instead of `rpm -U` for the `animation-speech` dependency.

### Arch (`PKGBUILD`)
- Official `PKGBUILD` at the repo root (x86_64 + aarch64) with CUDA/cuDNN as `optdepends`.
- `build()` compiles Rust binaries and all locales from `.po` sources.

### CI
- CI lint updated for v1.3: removed the obsolete `transcribe-daemon-canary` binary.
- `text-to-num` (PyPI `text2num`) installed in CI for number-conversion tests.
- Internal research markdown files untracked from git (kept locally via `.gitignore`).

### Release assets (10 files)
For every release: 3 `.deb` (cpu / cuda / plasmoid) + 3 `.rpm` (cpu / cuda / plasmoid) + `.plasmoid` + plasmoid `.tar.gz` + binaries `.tar.gz` + source `.tar.gz`.

---

## 🌐 Full i18n pass (fr, de, es, it, pt, uk)

- Every new string shipped in v1.3 translated across **six languages**: French, German, Spanish, Italian, Portuguese and Ukrainian.
- `.pot` template regenerated via `xgettext`, `.po` files merged with `msgmerge` and compiled to `.mo` for every release.
- **Full i18n pass on Ollama API integration** strings (backend status, error messages, configuration hints).
- **Audio context buffer** fully localised across the 6 languages.
- **Plasmoid tooltips** translated for every button, with particular care on the French set.
- **Light theme title** and theme-aware labels localised everywhere.
- Missing / fuzzy French translations cleaned up, including the PP translate tooltip and the LibreTranslate prompt.
- Incorrect `#, python-format` flag removed from `po/uk.po` (broke `msgfmt --check` in CI).
- FR agreement typo fixed ("seules les règles").
- Plasmoid domain (`plasma_applet_com.github.rcspam.dictee`) kept in sync with the setup/tray domain (`dictee`) across locales.

---

## 🧪 Quality & docs

### Automated tests (~920 new tests)
- **682 post-processing tests** in `tests/test-postprocess.py` — 12 pipeline steps × 7 languages, including TRPP, diarisation, and ReDoS hardening; wired into CI with an isolated `XDG_CONFIG_HOME`.
- **148 full-pipeline tests** in `tests/test-pipeline.py` — 3 modes × languages × backends × edge cases.
- **90 robustness tests** for voice commands, short words and the continuation keyword.
- New CI job **`test-apply-continuation`** covering the continuation edge cases.
- `rules.conf.default` updated to match the validated user `rules.conf` (suffixes, `\b`, ASR variants).

### Manual test protocols
- **UI checklist** at `docs/test-checklist-ui-pipeline.md` (39 interactive checks).
- **Vocal test protocol** at `docs/test-protocol-vocal.md` (38 end-to-end checks, with the 27 French stress sentences).
- **Manual test protocol** at `docs/test-protocol.md` (18 combined scenarios).

### Documentation
- **Audio context buffer** spec and implementation plan (`docs/spec-audio-context.md`, `docs/plan-audio-context.md`).
- **State-file authority** spec and implementation plan.
- **`dictee-ctl` central coordinator** spec (target v1.4).
- **Guided LibreTranslate / Ollama setup** flow documented from the wizard.
- README: dependencies table removed (handled by packages), ASR / translation tables corrected, first-run wizard mentioned explicitly, every configuration entry point documented.
- README banner reduced to 80 % (512 px) with a new SVG viewBox (330 × 120).
- Screenshots refreshed with backends visible.
- `CHANGELOG.md` introduced at the repo root, following the Keep a Changelog format.

### Cleanup
- Internal research Markdown files untracked from git (kept locally, hidden from GitHub).
- Build artefacts from v1.2.0 moved to `.gitignore`.
- Temporary profiling / debug prints removed (`dictee-setup`, `translate-paste`).
- `save_config()` sanitises shell-injection attempts; `_sanitize_conf_value` strips `<`, `>`, `&` to protect the continuation marker.

---

## Installation

**One-liner (recommended):**

```bash
curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install-online.sh | bash
```

Auto-detects your distro (Ubuntu, Debian, Fedora, openSUSE, Arch) and GPU, adds the NVIDIA CUDA repo if needed, and installs the right package.

For manual installation, see the [README](../README.md#installation).

## Full diff

See [`CHANGELOG.md`](../CHANGELOG.md) for the exhaustive per-section breakdown (26 sections A→Z).

**Full diff:** [`v1.2.0...v1.3.0`](https://github.com/rcspam/dictee/compare/v1.2.0...v1.3.0)
