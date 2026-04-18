# Changelog

All notable changes to **dictee** will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - Unreleased

361 commits, 234 files changed, +58 302 / −11 868 lines since `v1.2.0`.

### A. ASR backends & models

**Added**
- **Canary AED** now runs as a native Rust backend with `decodercontext` for smooth multi-language switching, replacing the Python `onnx-asr` daemon.
- **Whisper `large-v3-turbo`** model support (809 M params, multilingual, fast) with HF cache detection for the `mobiuslabsgmbh` repo.
- **WER benchmark** of all Whisper models (tiny → large-v3) against LibriSpeech.
- Shared Python module **`dictee_models.py`** as single source of truth for ASR model management.
- **`dictee-setup --models [--json]`** to list installed ASR models from the CLI.
- Model availability indicators in Whisper/Vosk combo boxes: ✓ green / ✗ red with coloured status label under each combo.
- Greyed-out state for unavailable backends in tray, plasmoid and backend switcher (Parakeet, Ollama, LibreTranslate).

**Changed**
- Daemon checkbox now verifies all backends, not just Parakeet.

**Removed**
- CLI `dictee-models` (superseded by `dictee-setup --models`).
- Legacy `transcribe-daemon-canary` binary and its CI lint entry.

**Fixed**
- Audio context auto-skipped for Whisper `large-v3`, `turbo` and `distil` variants (degraded word-level DTW).

### B. LLM post-processing (Ollama)

**Added**
- LLM post-processing integration through the Ollama HTTP API; optional contextual corrector selectable as a radio button.
- Configurable LLM position in the pipeline (before or after regex rules).
- Detailed Ollama offline notifications with status shown in both plasmoid and setup.

**Changed**
- `num_gpu` is now set through the Ollama API instead of an environment variable.
- Ollama entries are greyed out everywhere (tray, plasmoid, backend switcher) when the model is not downloaded.

**Fixed**
- `NameError: _os` on the `OLLAMA_NUM_GPU=0` runtime path.

### C. Translation (LibreTranslate, multi-language)

**Added**
- Multi-language translation with a dynamic target-language combo box and D-Bus notifications.
- Source ↔ target language swap button (⇅) on the translation page.
- Persistent Docker volume for LibreTranslate models.
- "Purge models" button with real volume size display.
- Language combo refresh after LibreTranslate start/stop/restart.
- Green status label for the translation backend with auto-refresh via `QFileSystemWatcher`.

**Changed**
- Canary source ↔ target swap correctly handled, along with ASR rules `l'eux`/`l'e`.
- "Apply" no longer shows a duplicate "restart LibreTranslate" prompt.
- Translation error messages are now detailed; an error sound plays and status is reflected in plasmoid/setup.

**Fixed**
- CJK translation handling.
- LibreTranslate volume sync and plasmoid target language.
- LibreTranslate-stopped state handled correctly in the plasmoid.
- Greyed-out state for uninstalled translation backends.

### D. Post-processing pipeline & modes

**Added**
- **Three pipeline modes** (normal PP / +translation / full chain) through a single combo box that replaces the two previous master switches.
- `DICTEE_PIPELINE_MODE` persisted in `dictee.conf` and read by the shell pipeline.
- **Mirror pipeline** (blue/orange) with a second PP run on the translation branch.
- Unified masters with independent blue/orange states.
- Per-step and per-sub-page greying when a master is off.
- Simplified orange SVG and a clickable translate icon opening the Translation menu.
- Translation PP is now enabled by default.

**Changed**
- `chk_trpp_short_text` syncs with `_trpp_state` (clicking the orange SVG updates it).
- Visual consistency between masters and the orange threshold combo.
- Sidebar sub-items stay navigable while being greyed when disabled.

**Fixed**
- Canary green notice restored on the translation page.
- TRPP persistence in `dictee.conf` with full i18n across 6 languages.

### E. Post-processing test panel

**Added**
- Complete redesign of the PP test panel (live config, highlight, indicator, anti-copy-paste artefacts).
- `QComboBox` with 3 pipeline modes + icons inside the test panel.
- Masters and translation toggle restored in tests.
- Keyword continuation support inside the test panel.
- Continuation works in translation mode with proper indentation.
- Re-run across languages after saving dictionary/rules.

**Changed**
- Silence indicator 🔇, clear button, translated continuation in the test panel.

**Fixed**
- Test panel recomputes after dict/rules save, translation without PP, and re-runs across languages.

### F. Post-processing rules & keepcaps

**Added**
- Full **keepcaps UI editor** on the PP page with enriched word list, UI toggles and FR translations.
- Extended keepcaps matching: short-word exceptions, first-word matching, preserved voice commands.
- Programming-symbol rules (currencies, parentheses, operators).
- French "tiret du six" (→ `-`) and "tiret du huit" (→ `_`).
- Plural and bracket variants (open/close parenthesis, etc.).
- Decimal comma in FR/DE/ES/IT/PT: `"1, 5"` → `"1,5"`.
- "X point Y point Z" → `X.Y.Z` version-style conversion.
- Auto short-text correction (< 3 words): lowercase + trailing period removal.
- Short-text correction preserves voice commands (punctuation, line breaks).

**Fixed**
- Leading punctuation stripped from ASR output.
- Regex rules editor now saved by "Apply".
- Keepcaps rollout audits (blockers, major issues, robustness).

### G. Continuation (`>>`)

**Added**
- Configurable continuation indicator through `DICTEE_CONTINUATION_INDICATOR`, with dynamic backspace for the `_` marker.
- Indicator combo box inside the Continuation tab.
- Full edition of system words in advanced mode.
- Keyword continuation "minuscule" replaces "contre-point".
- Separate keyword section in the tab.
- Visual `&` section in the continuation tab.
- CI job `test-apply-continuation`.

**Fixed**
- `>>` stripped properly along with the FR NNBSP/NBSP typo at push start.
- Word preserved when Whisper output ends with `…`.
- Continuation scroll recomputes on group fold/unfold (system words and language sections).
- FlowLayout no longer miscomputes chip height inside collapsed groups.
- Walk parent chain to detect hidden ancestors.
- Canonical Qt fix (real `sizeHint` + `Maximum` vertical size policy) for continuation scroll.
- Continuation indicator saved correctly: `_sanitize_conf_value` no longer strips `<`, `>`, `&`.
- `_build_continuation_tab` uses `self.conf` instead of a missing `conf` parameter.
- Indicator length encoded in the `H<N>` marker.
- Empty `last_word` guarded in `apply_continuation` (double-space bug).
- Marker still saved when input is punctuation-only.
- `&` parasite on punctuation-only input eliminated.
- Dropped ambiguous transitive verbs from FR continuation list, reinstated "ce", removed "ça" (false positives).

### H. Voice commands & suffix

**Added**
- Voice-commands suffix field in dictee-setup, persisted in `dictee.conf`.
- Language combo for continuation keyword and command suffix.
- Suffix pre-filled by default for every language.
- Multilingual suffix tooltip with variants aligned under the field.
- `?` helper buttons with detailed tooltips for keyword and suffix.
- Multilingual tooltips + continuation separator + auto context.

**Fixed**
- Suffix tolerates the Parakeet-induced parasite "s" (e.g. `suivi`/`suivis`).
- FR suffix defaults to `final[es]` instead of `suivi`.

### I. Audio context buffer (v1.3)

**Added**
- Core buffer logic implemented in the `dictee` shell pipeline.
- `dictee-switch-backend context` command and toggles in plasmoid, tray, setup.
- Audio context enabled by default in setup.
- Audio-context config surfaced in dictee-setup, plasmoid and tray menu.
- i18n strings in 6 languages.
- Word-level timestamps for Canary and Whisper.

**Changed**
- Alpha/Bravo audio marker **replaced** by word-level timestamps (deprecated and removed).
- `sox` now used instead of `ffmpeg` for audio concat/trim (20-40× faster).
- Daemon timestamps mode is word-level instead of sentence-level.
- 0.5 s safety margin on the timestamp threshold.

**Fixed**
- Audio context disabled for non-Parakeet backends (Canary/Vosk/Whisper where DTW is unreliable).
- Buffer poisoning robustness (`ffmpeg` error paths, local scope, `trap ERR`).
- Alpha/Bravo regex covers collapsed tokens (`ALPHA`/`Alfa`/no-space) — 27/27 tests pass.
- Transcription text never leaked into debug logs.

### J. Diarisation (Sortformer)

**Added**
- **Two-phase diarisation**: Sortformer pass first, then daemon socket.
- Diarisation button with a full state machine (`idle → preparing → ready → recording`), replacing the previous checkbox.
- Automatic Parakeet backend switch with restoration after diarisation.
- Speaker renaming UI after diarisation.
- `--sensitivity` flag on `transcribe-diarize` (speaker-detection threshold).
- `diarizing` state that greys transcription buttons during the pass.
- Plasmoid animation (blinking during switch, solid green when ready).
- VRAM threshold adapted dynamically (5 GB with diarisation, 3.5 GB otherwise).

**Changed**
- Diarisation deliberately **skips** the PP / translation / LLM chain (by design).
- Tooltip wording now directs users to "Transcribe file" for long recordings.

**Fixed**
- Diarisation cancellation is now non-blocking and `F9` is protected.
- Diarisation greyed out when the active backend is not Parakeet (in plasmoid and tray).
- WAV file is copied before live diarisation (race condition on deletion).
- Buttons stay visible during the VRAM switch.
- Diarisation unchecked after every live transcription.
- `Transcribe` button reactivated after the two-phase flow.

### K. First-run setup wizard

**Added**
- Complete wizard redesign with ASR/translation cards and hardware detection.
- Explanatory dialog displayed before the wizard when no config exists.
- Vosk/Whisper/Canary install validation before "Next".
- Wizard writes to a temporary config file until the checks page, cleaned up on cancel.
- `_on_apply` only runs on "Finish", never earlier.
- Defaults set to hold + same-key + Alt for translation.
- `DICTEE_SETUP_DONE=true` marker for wizard completion.
- Quit button, in-memory config, tray included in visual feedback.
- Trash buttons for venvs/models Vosk/Whisper with 100 % i18n.

**Changed**
- `dictee-transcribe` now warns when dictee is not yet configured.
- `strip_period` defaults to `false` in wizard mode.

### L. dictee-setup sidebar navigation

**Added**
- Sidebar mode with a persistent SVG pipeline.
- About page with built-in update check.
- SVG navigation semantics: first click navigates, second click toggles, with i18n tooltips.
- Master language switch surfaced on the clickable SVG pipeline.
- SVG tooltips via `QEvent.ToolTip` with HTML multi-line content.

**Fixed**
- `QHelpEvent.pos()` returns `QPoint`; converted to `QPointF` for `QRectF.contains`.

### M. dictee-transcribe (file transcription UI)

**Added**
- Full UI redesign.
- Multi-format export with detailed error handling.
- i18n and packaging brought in line with the rest of the suite.
- `--debug` flag and PySide6 compatibility.
- `--translation` deep link scrolling to the translation `QGroupBox`.
- `dictee-setup --translation` entry point plus "Configure translation" button.
- Support for both wizard and classic modes.

**Fixed**
- Backend restoration moved to `closeEvent` instead of the dictee wrapper.
- Three successive robustness passes shipped.

### N. UX, widgets & layout

**Added**
- Plasma-style **`ToggleSwitch`** widget replacing `QCheckBox` across the setup UI.
- Braille spinner (32 frames / 30 fps) inside the "Apply" button with an event loop pump.
- Parallel `systemctl` calls inside `_on_apply`.
- Pulse animations on dictation/translation buttons during recording.
- Volume slider on the plasmoid popup.

**Changed**
- Apply no longer forces a daemon restart for PP toggles.
- Apply now saves continuation, dictionary, rules and main config in one shot.
- Tabs and checkboxes reordered to match the SVG pipeline.
- Checkboxes duplicated by the SVG are hidden; LLM tab moved to the end.
- Short text + LLM condensed on a single line.
- Regex-rules warning shown as a dismissable popup instead of a permanent label.
- Setup never reopens on the "Regex rules" tab by default.
- Dictionary undo/redo: icon-only buttons (30 px).
- External `QScrollArea` removed from the PP page (fixes sidebar-resize lag).
- Non-expanding accordions; `SizePolicy.Maximum` enforced for `ToggleSwitch` and accordions.
- Microphone slider capped at 60 %, without tick marks.
- Seven small PP-tab adjustments (alignment, spacing, labels).

**Fixed**
- Continuation/dictionary scroll recomputes on fold/unfold.

### O. Audio sources & microphone calibration

**Added**
- Audio-source selection (microphone, monitor, application output).
- RMS silence threshold with a calibration lab and pipelines accordion.

### P. Keyboard shortcuts & dictee-ptt

**Added**
- `Ctrl+J` shortcut, visual `&` for continuation, hard `F9` blocking during diarize-ready.

**Fixed**
- PTT snapshot no longer shadows `gettext _`.
- Keyboard guard against sticky modifiers and escape sequences.
- `F9` blocked during `diarize-ready` without `--diarize` flag; stale `DICTEE_DIARIZE` cleaned up.
- `F9` no longer blocked after reboot (state file absent from `/dev/shm` at first boot).
- UID suffix on `PIDFILE` and `OWN_PIDFILE` (multi-user safety).
- `TRANSLATE_FLAG` UID, `PIDFILE.lock` cleanup, `ComboBox` binding.

### Q. State-file authority (major refactor)

**Added**
- State file established as the single source of truth across the stack.
- Debug logging unified across all components.

**Changed**
- Tray, plasmoid and PTT are now pure state readers with no local state.
- `dictee start/stop/cancel` now switch on the state file.
- `dictee --diarize` flag simplified.
- `dictee-switch-backend` writes `preparing` / `diarize-ready` into the state file.
- Fixed notification ID to eliminate race conditions on replace/close.
- Persistent notifications properly closed in every exit path and `cleanup_on_error`.

### R. Refactor & cleanup

**Added**
- New `dictee-common.sh` with shared functions across all scripts.
- `save_config()` preserves comments and sanitises shell injection.

**Changed**
- Seven utility functions extracted from the `dictee` entry-point script.
- Duplicated patterns factored out of `switch-backend` and `reset`.
- All French comments translated to English inside shell scripts (consistency).
- `DICTEE_ANIMATION` split into `DICTEE_ANIM_SPEECH` and `DICTEE_ANIM_PLASMOID`.
- Local directory now prioritised over `/usr/lib/dictee` in `sys.path`.
- QThread signals renamed `finished` → `done` to avoid the `QThread.finished` clash.
- HF Whisper cache paths centralised for cancel / delete / detect flows.
- Plasmoid reset button reads defaults from `main.xml`.

**Removed**
- Alpha/Bravo audio marker (replaced by word-level timestamps).
- `transcribe-daemon-canary` binary.

### S. Robustness fixes (multiple audit passes)

**Fixed**
- Paranoid audit #1 (4 bugs) and audit #2 (9 bugs) on daemon robustness.
- Daemon: high-priority (3), medium (3), low (state-switching, idle after `daemon_start`) issues.
- Daemon restart used instead of start, with `reset-failed`.
- Polling on daemon start replaces the single 2 s check.
- Daemon start now reads `dictee.conf` instead of `is-enabled`.
- Boot-time enable: verify return codes and Canary preset.
- Smart VRAM handling: daemon and Ollama are only stopped when free VRAM < 2 GB.
- VRAM is freed before transcription (daemon stop + Ollama unload).
- VRAM threshold dynamic: 5 GB for diarisation, 3.5 GB otherwise.
- Double-cancel race no longer re-enters the diarisation branch.
- Offline daemon notification handled cleanly.
- `lt_widget` visible only when the translation backend is LibreTranslate.
- Complete offline stop-daemon flow with configurable notifications and F9 protection.
- Cancel race conditions covered by stress tests.
- Full diarisation tray/F9 flow, silence notifications, removal of dead code.
- Silence notification closed properly; PySide6 imports; duplicated tooltip fix.
- Exhaustive pre-merge audit (devel-1.3 → master).

### T. Packaging & build

**Added**
- **Dual-mode `install.sh`** — same script used for both `curl | bash` online install and the local tarball install. Auto-detects the mode from the script's directory, with `--online` / `--tarball` flags to override. Handles Ubuntu/Debian/Fedora/openSUSE/Arch online, falls back to the tarball installer elsewhere. Auto-detects NVIDIA GPU and adds the CUDA repo (Ubuntu/Debian cuda-keyring, Fedora repo via dnf, openSUSE repo via zypper). Arch picks up `yay` / `paru` for the AUR-only `dotool` dependency.
- **Universal `uninstall.sh`** — auto-detects `dpkg` / `rpm` / `pacman` / tarball installs and removes each layer inline. `--purge` also wipes `~/.config/dictee`, ONNX models and the LibreTranslate Docker volume.
- Full CUDA build support: `load-dynamic` flag, `libonnxruntime.so`, CUDA 12 deps and intelligent postinst.
- CUDA runtime libraries (`libcufft.so.11`, `libcudart.so.12`) included in CUDA packages.
- CI: `text-to-num` installed and `text2num` package name fixed for the number-conversion tests.
- Build artefacts cleanup: research Markdown files untracked (kept locally via `.gitignore`).

**Changed**
- RPM plasmoid now installs to `/usr/share/plasma/plasmoids/`.
- `dnf install` used instead of `rpm -U` for `animation-speech`.
- `pkg/` regenerated by `build-deb.sh` (no longer the source of truth).

**Fixed**
- Stray `*.so.*` libraries excluded from the CPU `.deb`.
- Packaging v1.3: diarize icon, RPM `postun`, PKGBUILD assets, `install.sh`.
- CI lint updated for v1.3.

### U. Internationalisation (fr, de, es, it, pt, uk)

**Added**
- Full i18n pass for Ollama API strings (xgettext/msgmerge refresh).
- Audio-context buffer strings translated in 6 languages.
- Plasmoid tooltips fully translated, with completed FR coverage.

**Fixed**
- Missing/fuzzy FR translations, PP translate tooltip, LT prompt.
- Incorrect `python-format` flag removed from `po/uk.po`.
- FR agreement typo ("seules les règles").
- Light-theme title translated everywhere.
- `.pot` and `.po`/`.mo` files regenerated for every new string.

### V. Tests & validation

**Added**
- **682 post-processing tests** in `tests/test-postprocess.py` (12 steps, 7 languages, TRPP, diarisation, ReDoS hardening) + CI integration + `rules.conf.default`.
- **148 full-pipeline tests** in `tests/test-pipeline.py` covering 3 modes × languages × backends × edge cases.
- **90 robustness tests** for voice commands, short words and continuation keyword.
- Manual test protocol with 18 combined scenarios + 27 FR stress sentences.
- UI checklist at `docs/test-checklist-ui-pipeline.md` (39 checks).
- Vocal test protocol at `docs/test-protocol-vocal.md` (38 checks).

### W. Documentation

**Added**
- Audio context buffer spec and implementation plan (v1.3).
- State-file authority spec and implementation plan.
- `dictee-ctl` central coordinator spec (target v1.4).
- Guided LibreTranslate/Ollama setup from the wizard.

**Changed**
- Removed the dependencies table (dependencies are now managed by packages).
- Clarified "from the terminal" for `dictee --setup`.
- Documented every configuration entry point and the first-run wizard.
- Corrected ASR/translation tables.
- README banner reduced to 80 % (512 px) with new SVG viewBox 330×120.
- Refreshed plasmoid/tray screenshots with backends visible.

### X. Debug & observability

**Added**
- `DICTEE_DEBUG=true` toggles debug logging everywhere: shell scripts, Rust binaries, plasmoid, tray.
- 37 trace points in dictee-setup, with `--help` and `--debug` flags.
- Debug checkbox inside dictee-setup (Options section).
- Debug logging for `diarize-only` and `transcribe-diarize` Rust binaries.

**Changed**
- Diarisation segment logs restored (timestamps + speaker IDs).
- Transcription content is never written to debug logs.

### Y. Security

**Changed**
- `save_config()` sanitises shell-injection attempts.
- Multi-user UID audit on keepcaps configuration.
- `_sanitize_conf_value` strips `<`, `>`, `&` to prevent marker corruption.

### Z. Cleanup

**Removed**
- Temporary profiling code in dictee-setup.
- Temporary debug prints for `translate-paste`.
- Stale build artefacts from v1.2.0 (added to `.gitignore`).

[1.3.0]: https://github.com/rcspam/dictee/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/rcspam/dictee/releases/tag/v1.2.0
