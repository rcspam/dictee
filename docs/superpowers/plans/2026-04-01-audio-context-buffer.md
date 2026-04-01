# Audio Context Buffer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accumulate audio from previous dictations as context for the ASR daemon, improving recognition of short/technical words at the start of sentences.

**Architecture:** Shell-only feature in the `dictee` script. Before each transcription, concatenate a buffer of previous audio + an "Alpha Bravo" marker + the new recording, send to the daemon, then split the response on the marker regex. UI toggles in plasmoid config+popup, tray menu, and dictee-setup. Config via `dictee.conf`.

**Tech Stack:** Bash (dictee, dictee-switch-backend), ffmpeg (concat/trim), QML (plasmoid), PyQt6 (dictee-setup, dictee-tray), gettext (i18n)

**Spec:** `docs/superpowers/specs/2026-04-01-audio-context-buffer-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `dictee` | Modify | Core buffer logic: concat, transcribe, split, save, expire |
| `dictee-switch-backend` | Modify | Add `context true/false` command |
| `dictee-tray.py` | Modify | Add checkable "Audio context" menu item |
| `dictee-setup.py` | Modify | Add checkbox + spinbox in options section |
| `plasmoid/package/contents/ui/configGeneral.qml` | Modify | Add config checkbox |
| `plasmoid/package/contents/ui/FullRepresentation.qml` | Modify | Add toggle button in popup |
| `build-deb.sh` | Modify | Copy alpha-bravo.wav into package |
| `build-rpm.sh` | Modify | Copy alpha-bravo.wav into package |
| `PKGBUILD` | Modify | Install alpha-bravo.wav |
| `po/dictee.pot` + 6 `.po` files | Modify | New i18n strings |

---

### Task 1: Core buffer logic in `dictee`

**Files:**
- Modify: `dictee:93-99` (add buffer file variables)
- Modify: `dictee:751-774` (wrap transcription with buffer logic)

- [ ] **Step 1: Add buffer variables after existing file variables**

After line 99 (`LAST_WORD_FILE`), add:

```bash
# Audio context buffer
BUFFER_FILE="/dev/shm/.dictee_buffer${_UID_SUFFIX}.wav"
BUFFER_TS_FILE="/dev/shm/.dictee_buffer_ts${_UID_SUFFIX}"
COMBINED_FILE="/dev/shm/.dictee_combined${_UID_SUFFIX}.wav"
ALPHA_BRAVO=""
for _ab in "$(dirname "$(readlink -f "$0")")/assets/alpha-bravo.wav" /usr/share/dictee/assets/alpha-bravo.wav; do
    if [ -f "$_ab" ]; then ALPHA_BRAVO="$_ab"; break; fi
done
```

- [ ] **Step 2: Add buffer helper functions**

After the `save_last_word` function (around line 420), add these functions:

```bash
# Check if audio context buffer is enabled and marker exists
audio_context_enabled() {
    [ "${DICTEE_AUDIO_CONTEXT:-false}" = "true" ] && [ -n "$ALPHA_BRAVO" ]
}

# Check if buffer exists and is not expired
buffer_valid() {
    if [ ! -f "$BUFFER_FILE" ] || [ ! -f "$BUFFER_TS_FILE" ]; then
        return 1
    fi
    local ts now timeout
    ts=$(cat "$BUFFER_TS_FILE" 2>/dev/null) || return 1
    now=$(date +%s)
    timeout="${DICTEE_AUDIO_CONTEXT_TIMEOUT:-30}"
    if [ $((now - ts)) -gt "$timeout" ]; then
        _dbg "audio-context: buffer expired (age=$((now - ts))s > ${timeout}s)"
        rm -f "$BUFFER_FILE" "$BUFFER_TS_FILE"
        return 1
    fi
    return 0
}

# Trim buffer to max duration (DICTEE_AUDIO_CONTEXT_TIMEOUT seconds)
trim_buffer() {
    local timeout="${DICTEE_AUDIO_CONTEXT_TIMEOUT:-30}"
    local duration
    duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$BUFFER_FILE" 2>/dev/null) || return 0
    # Compare as integers (bash doesn't do float comparison)
    local dur_int=${duration%.*}
    if [ "${dur_int:-0}" -gt "$timeout" ]; then
        _dbg "audio-context: trimming buffer from ${duration}s to ${timeout}s"
        ffmpeg -y -loglevel error -sseof "-${timeout}" -i "$BUFFER_FILE" -ar 16000 -ac 1 "${BUFFER_FILE}.tmp" && \
            mv "${BUFFER_FILE}.tmp" "$BUFFER_FILE"
    fi
}

# Concatenate buffer + marker + new recording into combined file
build_combined() {
    local recording="$1"
    trim_buffer
    _dbg "audio-context: concat buffer + alpha-bravo + recording"
    ffmpeg -y -loglevel error \
        -i "$BUFFER_FILE" -i "$ALPHA_BRAVO" -i "$recording" \
        -filter_complex "[0][1][2]concat=n=3:v=0:a=1" \
        -ar 16000 -ac 1 "$COMBINED_FILE"
}

# Split transcription on "Alpha Bravo" marker, return text after marker
split_on_marker() {
    local text="$1"
    # Remove marker and everything before it
    local after
    after=$(echo "$text" | sed -E 's/.*[.,[:space:]]*[Aa]lpha[[:space:]]+[Bb]ravo[.,[:space:]]*//')
    if [ -n "$after" ] && [ "$after" != "$text" ]; then
        _dbg "audio-context: marker found, extracted ${#after} chars"
        echo "$after"
        return 0
    else
        _dbg "audio-context: WARNING — marker not found in transcription"
        return 1
    fi
}

# Save recording as new buffer (only if transcription was non-empty)
save_buffer() {
    local recording="$1"
    cp "$recording" "$BUFFER_FILE"
    date +%s > "$BUFFER_TS_FILE"
    _dbg "audio-context: buffer saved ($(stat -c%s "$BUFFER_FILE") bytes)"
}
```

- [ ] **Step 3: Replace direct transcription call with buffer-aware logic**

Replace lines 751-758 (the transcription block) with:

```bash
    # Determine which file to send to daemon
    local transcribe_file="$RECORDING_FILE"
    local used_context=false
    if audio_context_enabled && buffer_valid; then
        if build_combined "$RECORDING_FILE"; then
            transcribe_file="$COMBINED_FILE"
            used_context=true
            _dbg "audio-context: using combined file for transcription"
        else
            _dbg "audio-context: concat failed, using recording directly"
        fi
    fi

    _dbg "transcribe: sending $transcribe_file to daemon"
    if ! raw=$(eval transcribe-client "$transcribe_file"); then
        _dbg "transcribe: FAILED — daemon not responding"
        notify_dictee 0 dialog-error "Transcription failed — daemon not responding"
        write_state "idle"
        rm -f "$COMBINED_FILE"
        cleanup_session
        exit 1
    fi
    rm -f "$COMBINED_FILE"
    _dbg "transcribe: raw result=${#raw} chars"
    if [ -z "$raw" ]; then
        _dbg "transcribe: FAILED — empty result"
        notify_dictee 0 dialog-error "Transcription failed — empty result"
        write_state "idle"
        cleanup_session
        exit 1
    fi

    # If we used context, split on Alpha Bravo marker
    if [ "$used_context" = true ]; then
        local split_result
        if split_result=$(split_on_marker "$raw"); then
            raw="$split_result"
        else
            # Marker not found: warn user, use full text
            notify_dictee 0 dialog-error "Audio context: marker not found"
        fi
    fi
```

- [ ] **Step 4: Save buffer after successful transcription**

After the existing post-processing block (after line 781 `apply_continuation transcribed`), add:

```bash
    # Save recording as buffer for next push (only if non-empty transcription)
    if audio_context_enabled && [ -n "$transcribed" ]; then
        save_buffer "$RECORDING_FILE"
    fi
```

- [ ] **Step 5: Test manually**

```bash
# Enable context in config
echo 'DICTEE_AUDIO_CONTEXT=true' >> ~/.config/dictee.conf
echo 'DICTEE_AUDIO_CONTEXT_TIMEOUT=30' >> ~/.config/dictee.conf

# Test 1: First F9 — no buffer, should transcribe normally
DICTEE_DEBUG=true dictee
# Expected: "audio-context: buffer expired" or no buffer message, normal transcription

# Test 2: Second F9 within 30s — buffer should be used
DICTEE_DEBUG=true dictee
# Expected: "audio-context: using combined file", "marker found"

# Test 3: Wait 35s, F9 — buffer should be expired
sleep 35
DICTEE_DEBUG=true dictee
# Expected: "audio-context: buffer expired"
```

- [ ] **Step 6: Commit**

```bash
git add dictee
git commit -m "feat: audio context buffer — core logic in dictee script"
```

---

### Task 2: `dictee-switch-backend context` command

**Files:**
- Modify: `dictee-switch-backend:14-25` (add to usage)
- Modify: `dictee-switch-backend:52` area (add case branch)

- [ ] **Step 1: Add `context` to usage text**

In `dictee-switch-backend`, add to the usage function (after the diarize line):

```bash
    echo "  context [true|false]      Toggle audio context buffer"
```

- [ ] **Step 2: Add `context` case branch**

Before the `*) usage ;;` line at the end of the case block, add:

```bash
context)
    val="${2:-true}"
    case "$val" in
        true|false) ;;
        toggle)
            set +eu; source "$CONF"; set -eu
            if [ "${DICTEE_AUDIO_CONTEXT:-false}" = "true" ]; then val="false"; else val="true"; fi
            ;;
        *) echo "Error: context expects true, false, or toggle" >&2; usage ;;
    esac
    set_conf "DICTEE_AUDIO_CONTEXT" "$val"
    _dbg "context: $val"
    if [ "$val" = "true" ]; then
        notify_dictee 0 audio-chat-symbolic "Audio context: ON"
    else
        notify_dictee 0 audio-chat-symbolic "Audio context: OFF"
        # Clean up buffer files
        rm -f "/dev/shm/.dictee_buffer-$(id -u).wav" "/dev/shm/.dictee_buffer_ts-$(id -u)"
    fi
    (sleep 3; gdbus call --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications --method org.freedesktop.Notifications.CloseNotification "$NOTIFY_SERVER_ID" >/dev/null 2>&1) &
    echo "Audio context: $val"
    ;;
```

- [ ] **Step 3: Test**

```bash
dictee-switch-backend context true
# Expected: notification "Audio context: ON", DICTEE_AUDIO_CONTEXT=true in dictee.conf

dictee-switch-backend context false
# Expected: notification "Audio context: OFF", buffer files cleaned up

dictee-switch-backend context toggle
# Expected: toggles value
```

- [ ] **Step 4: Commit**

```bash
git add dictee-switch-backend
git commit -m "feat: dictee-switch-backend context command"
```

---

### Task 3: Tray toggle

**Files:**
- Modify: `dictee-tray.py` (add checkable menu item after diarize section)

- [ ] **Step 1: Add "Audio context" menu action**

After the diarize lock toggle block (around line 843), add:

```python
# Audio context buffer toggle
self.action_context_qt = self.menu.addAction(_("Audio context"))
self.action_context_qt.setCheckable(True)
self.action_context_qt.setChecked(
    read_conf_value("DICTEE_AUDIO_CONTEXT", "false").lower() == "true")
self.action_context_qt.setToolTip(
    _("Accumulate audio from previous dictations to improve recognition."))
self.action_context_qt.toggled.connect(self._on_context_toggled_qt)
```

- [ ] **Step 2: Add handler method**

In the handler methods section (near `_on_diarize_toggled_qt`), add:

```python
def _on_context_toggled_qt(self, checked):
    val = "true" if checked else "false"
    subprocess.Popen(["dictee-switch-backend", "context", val])
```

- [ ] **Step 3: Test**

```bash
# Launch tray, verify "Audio context" menu item appears
dictee-tray &
# Click toggle, verify dictee.conf changes
grep DICTEE_AUDIO_CONTEXT ~/.config/dictee.conf
```

- [ ] **Step 4: Commit**

```bash
git add dictee-tray.py
git commit -m "feat: audio context toggle in tray menu"
```

---

### Task 4: dictee-setup checkbox + spinbox

**Files:**
- Modify: `dictee-setup.py` (add in the options section near clipboard checkbox)

- [ ] **Step 1: Find the options section and add audio context widgets**

Near the clipboard checkbox (`self.chk_clipboard`), add:

```python
# Audio context buffer
self.chk_audio_context = QCheckBox(_("Audio context buffer"))
self.chk_audio_context.setChecked(conf.get("DICTEE_AUDIO_CONTEXT", "false") == "true")
self.chk_audio_context.setToolTip(
    _("Accumulate audio from previous dictations to improve recognition\n"
      "of short or technical words at the start of sentences."))
lay_opt.addWidget(self.chk_audio_context)

lay_ctx = QHBoxLayout()
lay_ctx.setSpacing(8)
lbl_ctx = QLabel(_("Context duration (seconds):"))
lbl_ctx.setToolTip(
    _("Maximum duration of accumulated audio context.\n"
      "Also the inactivity timeout: the buffer expires\n"
      "after this many seconds without a non-empty dictation."))
self.spin_audio_context_timeout = QSpinBox()
self.spin_audio_context_timeout.setRange(5, 120)
self.spin_audio_context_timeout.setValue(
    int(conf.get("DICTEE_AUDIO_CONTEXT_TIMEOUT", "30")))
self.spin_audio_context_timeout.setSuffix(" s")
lay_ctx.addWidget(lbl_ctx)
lay_ctx.addWidget(self.spin_audio_context_timeout)
lay_ctx.addStretch()
lay_opt.addLayout(lay_ctx)
```

Note: `QSpinBox` must be in the imports. Verify and add if missing.

- [ ] **Step 2: Save values in the _on_apply method**

In the `_on_apply` method, where other config values are saved, add:

```python
set_conf("DICTEE_AUDIO_CONTEXT", "true" if self.chk_audio_context.isChecked() else "false")
set_conf("DICTEE_AUDIO_CONTEXT_TIMEOUT", str(self.spin_audio_context_timeout.value()))
```

- [ ] **Step 3: Test**

```bash
dictee-setup
# Verify checkbox and spinbox appear in options
# Toggle, change value, click Apply
# Check dictee.conf has correct values
```

- [ ] **Step 4: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: audio context config in dictee-setup"
```

---

### Task 5: Plasmoid config checkbox

**Files:**
- Modify: `plasmoid/package/contents/ui/configGeneral.qml`

- [ ] **Step 1: Add property alias**

In the property section at the top (around line 10-12), add:

```qml
property alias cfg_audioContext: audioContextCheck.checked
property int cfg_audioContextTimeout: 30
```

- [ ] **Step 2: Add checkbox in config UI**

Near the existing `showTranscriptionCheck` / `previewModeCheck` area, add:

```qml
QQC2.CheckBox {
    id: audioContextCheck
    Kirigami.FormData.label: i18n("Audio context buffer:")
}

RowLayout {
    Kirigami.FormData.label: i18n("Context duration:")
    spacing: Kirigami.Units.smallSpacing
    visible: audioContextCheck.checked

    QQC2.SpinBox {
        id: audioContextTimeoutSpin
        from: 5; to: 120; stepSize: 5
        value: configPage.cfg_audioContextTimeout
        onValueModified: configPage.cfg_audioContextTimeout = value
    }
    QQC2.Label {
        text: i18n("seconds")
    }
    Kirigami.ContextualHelpButton {
        toolTipText: i18n("Maximum duration of accumulated audio context. Also the inactivity timeout: the buffer expires after this many seconds without a non-empty dictation.")
    }
}
```

- [ ] **Step 3: Propagate config to dictee.conf on save**

The plasmoid config uses Plasma's built-in config system. To propagate to `dictee.conf`, match the existing pattern used by other config values in this plasmoid. If it uses `PlasmaCore.DataSource` with shell commands:

```qml
onCfg_audioContextChanged: {
    var val = cfg_audioContext ? "true" : "false"
    confWriter.connectSource("dictee-switch-backend context " + val)
}
```

- [ ] **Step 4: Commit**

```bash
git add plasmoid/package/contents/ui/configGeneral.qml
git commit -m "feat: audio context checkbox in plasmoid config"
```

---

### Task 6: Plasmoid popup toggle button

**Files:**
- Modify: `plasmoid/package/contents/ui/FullRepresentation.qml`

- [ ] **Step 1: Add toggle button**

After the diarize button block (around line 403), add a context toggle button:

```qml
PlasmaComponents.Button {
    id: btnAudioContext
    Layout.fillWidth: true
    Layout.preferredWidth: 0
    checkable: true
    checked: Plasmoid.configuration.audioContext

    contentItem: RowLayout {
        spacing: 4
        Kirigami.Icon {
            source: "media-record-symbolic"
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Kirigami.Units.iconSizes.small
        }
        PlasmaComponents.Label {
            text: i18n("Audio context")
            color: btnAudioContext.checked ? "#98c379" : Kirigami.Theme.textColor
        }
    }

    onToggled: {
        var val = checked ? "true" : "false"
        executable.exec("dictee-switch-backend context " + val)
    }

    QQC2.ToolTip.text: i18n("Accumulate audio from previous dictations to improve recognition.")
}
```

Note: Verify the exact name of the shell command executor component in this file and match the existing pattern.

- [ ] **Step 2: Commit**

```bash
git add plasmoid/package/contents/ui/FullRepresentation.qml
git commit -m "feat: audio context toggle in plasmoid popup"
```

---

### Task 7: Build scripts — install alpha-bravo.wav

**Files:**
- Modify: `build-deb.sh:41-48`
- Modify: `build-rpm.sh:127-132`
- Modify: `PKGBUILD:106-108` area

- [ ] **Step 1: build-deb.sh**

In the assets copy section (after the SVG copies around line 44), add:

```bash
# Audio context marker
if [ -f "./assets/alpha-bravo.wav" ]; then
    cp ./assets/alpha-bravo.wav "$PKG_DIR/usr/share/dictee/assets/"
fi
```

Also add the same in the tarball section (around line 308):

```bash
if [ -f "./assets/alpha-bravo.wav" ]; then
    cp ./assets/alpha-bravo.wav "$TARBALL_DIR/usr/share/dictee/assets/"
fi
```

- [ ] **Step 2: build-rpm.sh**

In the assets copy section (after line 132), add:

```bash
if [ -f "./assets/alpha-bravo.wav" ]; then
    cp ./assets/alpha-bravo.wav "$buildroot/usr/share/dictee/assets/"
fi
```

- [ ] **Step 3: PKGBUILD**

In the `package()` function, after the icons install section, add:

```bash
# Audio context marker
install -Dm644 assets/alpha-bravo.wav "$pkgdir/usr/share/dictee/assets/alpha-bravo.wav"
```

- [ ] **Step 4: Commit**

```bash
git add build-deb.sh build-rpm.sh PKGBUILD
git commit -m "feat: install alpha-bravo.wav in packages"
```

---

### Task 8: i18n — nouvelles chaines

**Files:**
- Modify: `po/dictee.pot` + `po/{fr,de,es,it,uk,pt}.po`

- [ ] **Step 1: Extract new strings**

Run `xgettext` to update the POT file:

```bash
xgettext --language=Python --keyword=_ --output=po/dictee.pot \
    --package-name=dictee --package-version=1.3.0 \
    dictee-setup.py dictee-tray.py
```

Or manually add these entries to `po/dictee.pot`:

```
msgid "Audio context"
msgstr ""

msgid "Audio context buffer"
msgstr ""

msgid "Accumulate audio from previous dictations to improve recognition."
msgstr ""

msgid "Accumulate audio from previous dictations to improve recognition\nof short or technical words at the start of sentences."
msgstr ""

msgid "Context duration (seconds):"
msgstr ""

msgid "Maximum duration of accumulated audio context.\nAlso the inactivity timeout: the buffer expires\nafter this many seconds without a non-empty dictation."
msgstr ""

msgid "Audio context: marker not found"
msgstr ""
```

- [ ] **Step 2: Update .po files**

```bash
for lang in fr de es it uk pt; do
    msgmerge --update po/${lang}.po po/dictee.pot
done
```

- [ ] **Step 3: Translate FR (prioritaire)**

Edit `po/fr.po` and fill in the French translations:

```
msgid "Audio context"
msgstr "Contexte audio"

msgid "Audio context buffer"
msgstr "Buffer de contexte audio"

msgid "Accumulate audio from previous dictations to improve recognition."
msgstr "Accumule l'audio des dictées précédentes pour améliorer la reconnaissance."

msgid "Context duration (seconds):"
msgstr "Durée du contexte (secondes) :"

msgid "Audio context: marker not found"
msgstr "Contexte audio : marqueur non trouvé"
```

- [ ] **Step 4: Compile .mo files**

```bash
for lang in fr de es it uk pt; do
    msgfmt -o po/${lang}.mo po/${lang}.po
done
```

- [ ] **Step 5: Commit**

```bash
git add po/
git commit -m "i18n: audio context buffer strings (6 languages)"
```

---

### Task 9: Integration test end-to-end

- [ ] **Step 1: Test full flow with context OFF (default)**

```bash
# Ensure context is off
dictee-switch-backend context false
DICTEE_DEBUG=true dictee  # F9 start, F9 stop
# Expected: normal transcription, no buffer messages in debug log
```

- [ ] **Step 2: Test full flow with context ON**

```bash
dictee-switch-backend context true
# First dictation (no buffer yet)
DICTEE_DEBUG=true dictee
# Expected: transcription works, buffer saved

# Second dictation within 30s
DICTEE_DEBUG=true dictee
# Expected: "using combined file", "marker found", correct text extracted

# Verify buffer file exists
ls -la /dev/shm/.dictee_buffer*
```

- [ ] **Step 3: Test expiration**

```bash
# Set short timeout for testing
sed -i 's/DICTEE_AUDIO_CONTEXT_TIMEOUT=.*/DICTEE_AUDIO_CONTEXT_TIMEOUT=5/' ~/.config/dictee.conf

dictee-switch-backend context true
DICTEE_DEBUG=true dictee  # Create buffer
sleep 6
DICTEE_DEBUG=true dictee  # Should expire buffer
# Expected: "buffer expired" in debug log

# Restore normal timeout
sed -i 's/DICTEE_AUDIO_CONTEXT_TIMEOUT=.*/DICTEE_AUDIO_CONTEXT_TIMEOUT=30/' ~/.config/dictee.conf
```

- [ ] **Step 4: Test empty transcription preserves buffer**

```bash
# Short F9 press with no speech — should not overwrite buffer
# Expected: buffer file unchanged (same timestamp)
```

- [ ] **Step 5: Test UI toggles**

```bash
# Plasmoid: toggle audio context in popup, verify dictee.conf changes
# Tray: toggle audio context in menu, verify dictee.conf changes
# Setup: toggle checkbox + change spinbox, apply, verify dictee.conf
```

- [ ] **Step 6: Final commit (if any fixes needed)**

```bash
git add -u
git commit -m "fix: audio context buffer integration fixes"
```
