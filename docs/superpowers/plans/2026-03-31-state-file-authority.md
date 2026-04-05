# State File Authority — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/dev/shm/.dictee_state` the single source of truth — backend writes, frontends read. Eliminate all race conditions in the diarize flow.

**Architecture:** The script `dictee` and `dictee-switch-backend` are the sole writers of the state file. Plasmoid and tray become pure readers that send commands via `executable.run()` / `subprocess.Popen()`. ESC is handled only by `dictee-ptt`. Two new states (`preparing`, `diarize-ready`) make the diarize flow visible to all frontends.

**Tech Stack:** Bash (dictee, dictee-switch-backend), QML/JS (plasmoid), Python/PyQt6 (tray, ptt)

**Spec:** `docs/superpowers/specs/2026-03-31-state-file-authority-design.md`

---

### Task 1: Backend — `dictee-switch-backend` écrit les nouveaux états

**Files:**
- Modify: `dictee-switch-backend:147-195` (diarize case)

- [ ] **Step 1: Ajouter `write_state` au bloc `diarize true`**

Dans le bloc `if [ "$val" = "true" ]` (ligne 162), ajouter les appels `write_state` et supprimer `set_conf "DICTEE_DIARIZE" "true"` :

```bash
    if [ "$val" = "true" ]; then
        # Save current backend and stop daemon to free VRAM
        write_state "preparing"
        set_conf "DICTEE_PRE_DIARIZE_BACKEND" "$current_asr"
        # Stop all daemons and wait for VRAM release
        _dbg "diarize: stopping all daemons for VRAM"
        systemctl --user disable --now dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null
        # Wait until GPU processes are gone (5s timeout)
        for i in $(seq 1 10); do
            if ! nvidia-smi --query-compute-apps=name --format=csv,noheader 2>/dev/null | grep -qE "transcribe|python"; then
                break
            fi
            sleep 0.5
        done
        write_state "diarize-ready"
        notify-send -t 3000 -i audio-speakers-symbolic -a Dictee "Diarisation activée" 2>/dev/null || true
```

- [ ] **Step 2: Ajouter `write_state` au bloc `diarize false`**

Dans le bloc `else` (ligne 178), supprimer `set_conf "DICTEE_DIARIZE" "false"` et ajouter `write_state "idle"` :

```bash
    else
        # Restore the previous backend daemon
        pre_backend="${DICTEE_PRE_DIARIZE_BACKEND:-$current_asr}"
        if [ -n "$pre_backend" ]; then
            set_conf "DICTEE_ASR_BACKEND" "$pre_backend"
            svc=$(asr_service "$pre_backend")
            _dbg "diarize: restoring $pre_backend → $svc"
            systemctl --user enable --now "$svc" 2>/dev/null
            set_conf "DICTEE_PRE_DIARIZE_BACKEND" ""
            notify-send -t 3000 -i audio-speakers-symbolic -a Dictee "Diarisation désactivée — retour à $pre_backend" 2>/dev/null || true
        else
            notify-send -t 3000 -i audio-speakers-symbolic -a Dictee "Diarisation désactivée" 2>/dev/null || true
        fi
        write_state "idle"
    fi
```

- [ ] **Step 3: Supprimer le bloc toggle**

Supprimer les lignes 149-157 (le `if [ "$val" = "toggle" ]` bloc) — le toggle n'est plus utilisé. Le caller passe toujours `true` ou `false`.

- [ ] **Step 4: Tester manuellement**

```bash
dictee-reset dictee; sleep 1
echo "=== diarize true ==="
dictee-switch-backend diarize true
cat /dev/shm/.dictee_state  # attendu: diarize-ready
echo "=== diarize false ==="
dictee-switch-backend diarize false
cat /dev/shm/.dictee_state  # attendu: idle
systemctl --user is-active dictee  # attendu: active
```

- [ ] **Step 5: Commit**

```bash
git add dictee-switch-backend
git commit -m "refactor: dictee-switch-backend écrit preparing/diarize-ready dans le state file"
```

---

### Task 2: Backend — `dictee` suppression ESC listener + simplification DIARIZE

**Files:**
- Modify: `dictee:56-66` (DIARIZE parsing)
- Modify: `dictee:431-440` (NO_ESC_LISTENER arg)
- Modify: `dictee:463-526` (ESC listener functions)
- Modify: `dictee:575,715,765,922` (calls to start/stop_escape_listener)

- [ ] **Step 1: Simplifier le parsing DIARIZE**

Remplacer les lignes 56-66 par :

```bash
# --diarize flag: explicit from plasmoid, F9 never passes it
DIARIZE="false"
for _arg in "$@"; do
    if [ "$_arg" = "--diarize" ]; then DIARIZE="true"; fi
done
```

Supprimer les lignes `_DIARIZE_PREPARED` (61-64) — le state file remplace cette détection.

- [ ] **Step 2: Supprimer ESC listener**

Supprimer entièrement :
- Les fonctions `start_escape_listener` et `stop_escape_listener` (lignes ~463-526)
- La variable `ESC_LISTENER_PIDFILE` et `NO_ESC_LISTENER` (lignes ~431-440)
- Tous les appels à `stop_escape_listener` (lignes ~575, ~715, ~765)
- L'appel à `start_escape_listener` (ligne ~922)

- [ ] **Step 3: Supprimer le flag --no-esc-listener du parsing d'args**

Dans le parsing d'arguments (vers ligne 431), supprimer `--no-esc-listener)` case.

- [ ] **Step 4: Tester que dictee fonctionne sans ESC listener**

```bash
dictee-reset dictee; sleep 1
dictee &
sleep 1.5
cat /dev/shm/.dictee_state  # attendu: recording
dictee --cancel
sleep 0.5
cat /dev/shm/.dictee_state  # attendu: idle ou cancelled
```

- [ ] **Step 5: Commit**

```bash
git add dictee
git commit -m "refactor: supprimer ESC listener interne, simplifier --diarize flag"
```

---

### Task 3: Backend — `dictee --cancel` refactorisé en switch sur état

**Files:**
- Modify: `dictee:700-744` (cancel block)

- [ ] **Step 1: Réécrire le bloc cancel**

Remplacer le bloc cancel (de `if [ "$CANCEL" = true ]` à `exit 0`) par :

```bash
if [ "$CANCEL" = true ]; then
    trap - ERR
    # Read current state under flock
    _cancel_state=""
    (
        flock -n 200 || exit 0
        current=$(cat "$STATE_FILE" 2>/dev/null)
        if [ "$current" = "cancelled" ] || [ "$current" = "idle" ] || [ "$current" = "offline" ]; then
            exit 0
        fi
        echo "cancelled" > "$STATE_FILE"
        echo "$current"
    ) 200>"$STATE_LOCK" | read -r _cancel_state || true

    if [ -z "$_cancel_state" ]; then
        _dbg "cancel: nothing to cancel"
        exit 0
    fi

    _dbg "cancel: state was $_cancel_state"

    case "$_cancel_state" in
        preparing|diarize-ready)
            # Diarize preparation — kill switch-backend and restore daemon
            if pkill -f "dictee-switch-backend diarize true" 2>/dev/null; then true; fi
            dictee-switch-backend diarize false 2>/dev/null || true
            notify_dictee 3000 audio-chat-none-symbolic "Diarisation annulée"
            ;;
        recording)
            # Active recording — stop it
            stop_animation quit
            restore_audio
            stop_recording
            notify_dictee 3000 audio-chat-none-symbolic "Enregistrement annulé"
            cleanup_session
            # If diarize was prepared, restore daemon
            _pre_b=$(grep '^DICTEE_PRE_DIARIZE_BACKEND=' "$DICTEE_CONF" 2>/dev/null | cut -d= -f2)
            if [ -n "$_pre_b" ]; then
                _dbg "cancel: recording had diarize prepared — restoring daemon"
                dictee-switch-backend diarize false 2>/dev/null || true
            else
                write_state "idle"
            fi
            ;;
        diarizing)
            # Diarization in progress — kill processes and restore daemon
            if pkill -f "dictee-transcribe.*--diarize" 2>/dev/null; then true; fi
            if pkill -f "transcribe-diarize" 2>/dev/null; then true; fi
            if pkill -f "diarize-only" 2>/dev/null; then true; fi
            sleep 0.2
            dictee-switch-backend diarize false 2>/dev/null || true
            notify_dictee 3000 audio-chat-none-symbolic "Diarisation annulée"
            ;;
        transcribing|switching)
            write_state "idle"
            ;;
    esac
    _dbg "cancel: done"
    exit 0
fi
```

- [ ] **Step 2: Tester tous les scénarios cancel**

```bash
# Cancel depuis idle → no-op
dictee-reset dictee; sleep 1
dictee --cancel; cat /dev/shm/.dictee_state  # idle

# Cancel depuis preparing
dictee-switch-backend diarize true &
sleep 0.5; dictee --cancel; sleep 1
cat /dev/shm/.dictee_state  # idle
systemctl --user is-active dictee  # active

# Cancel depuis recording
dictee-reset dictee; sleep 1
dictee & sleep 1.5
dictee --cancel; sleep 0.5
cat /dev/shm/.dictee_state  # idle

# Cancel depuis diarize recording
dictee-reset dictee; sleep 1
dictee-switch-backend diarize true; sleep 0.5
dictee --diarize & sleep 1.5
dictee --cancel; sleep 1
cat /dev/shm/.dictee_state  # idle
systemctl --user is-active dictee  # active
```

- [ ] **Step 3: Commit**

```bash
git add dictee
git commit -m "refactor: dictee --cancel basé sur state file (switch sur état)"
```

---

### Task 4: Backend — `dictee` start/stop refactorisé

**Files:**
- Modify: `dictee:888-922` (start recording)
- Modify: `dictee:758-820` (stop recording + diarize)

- [ ] **Step 1: Refactoriser le guard de start recording**

Remplacer la vérification d'état actuelle (lignes ~888-897) par un switch strict :

```bash
# Check state allows recording
_current_state=$(cat "$STATE_FILE" 2>/dev/null)
case "$_current_state" in
    idle|diarize-ready)
        ;;  # OK to record
    *)
        _dbg "start-recording: BLOCKED (state=$_current_state)"
        exit 0
        ;;
esac
```

Supprimer la vérification spéciale `DIARIZE != "true"` pour le daemon check (lignes ~901-913) — en mode diarize, l'état sera `diarize-ready` (daemon arrêté, c'est normal). Remplacer par :

```bash
# Check daemon is running (skip in diarize mode — daemon is intentionally stopped)
if [ "$_current_state" != "diarize-ready" ]; then
    if ! systemctl --user is-active "${_ASR_SERVICE}" >/dev/null 2>&1; then
        _dbg "start-recording: BLOCKED — daemon $_ASR_SERVICE not active"
        notify_dictee 3000 audio-chat-none-symbolic "Daemon arrêté — démarrez-le d'abord"
        exit 0
    fi
fi
```

- [ ] **Step 2: Simplifier le bloc stop + diarize**

Dans le bloc diarize (lignes ~782-820), supprimer :
- Le `sed -i 's/^DICTEE_DIARIZE=.*/DICTEE_DIARIZE=false/'` (ligne ~804) — plus de config DIARIZE
- La boucle d'attente VRAM inline (lignes ~773-793) — `dictee-transcribe` gère la VRAM

Garder :
- `write_state "diarizing"`
- La copie du WAV
- Le `systemd-run dictee-transcribe`

```bash
    if [ "$DIARIZE" = "true" ]; then
        _dbg "diarize: launching dictee-transcribe"
        write_state "diarizing"
        diarize_file="/tmp/dictee-diarize-$(date +%s).wav"
        cp "$RECORDING_FILE" "$diarize_file"
        cleanup_session
        _dbg "diarize: launching dictee-transcribe --file $diarize_file --diarize"
        systemd-run --user --no-block --collect \
            --unit="dictee-transcribe-$$" \
            dictee-transcribe --file "$diarize_file" --diarize
        exit 0
    fi
```

- [ ] **Step 3: Relancer les tests de robustesse**

```bash
bash /tmp/dictee-robustness-tests.sh
bash /tmp/dictee-fast-tests.sh
```

Tous les 25 tests doivent passer.

- [ ] **Step 4: Commit**

```bash
git add dictee
git commit -m "refactor: dictee start/stop basé sur state file, diarize simplifié"
```

---

### Task 5: Frontend — Plasmoid `main.qml` refactorisé

**Files:**
- Modify: `plasmoid/package/contents/ui/main.qml`

- [ ] **Step 1: Supprimer les propriétés obsolètes**

Supprimer ces propriétés (lignes ~255-257) :
```
property bool diarizeEnabled: false
property bool diarizeFlowActive: false
property int diarizeResetCount: 0
```

- [ ] **Step 2: Supprimer `cleanupDiarize()`**

Supprimer la fonction entière (lignes ~297-304).

- [ ] **Step 3: Supprimer `onExpandedChanged` cancel**

Supprimer le bloc (lignes ~452-460).

- [ ] **Step 4: Supprimer le binding `diarizeResetCount` dans fullRepresentation**

Dans le binding `fullRepresentation:` (~ligne 464), supprimer `diarizeResetCount: root.diarizeResetCount`.

- [ ] **Step 5: Réécrire `parseState()`**

Remplacer la fonction `parseState()` (~lignes 306-353) :

```javascript
    function parseState(output) {
        var newState = output.trim()
        if (newState === root.state || newState === "") return
        _dbg("state: " + root.state + " → " + newState)

        // Stop all safety timers on any transition
        transcribingTimer.stop()
        recordingTimer.stop()
        diarizingTimer.stop()
        switchingTimer.stop()

        if (newState === "cancelled") {
            root.activeButton = ""
            root.state = "idle"
            return
        }

        root.state = newState

        // Start safety timers for active states
        switch (newState) {
        case "recording":
            recordingTimer.restart()
            break
        case "transcribing":
            transcribingTimer.restart()
            break
        case "diarizing":
            diarizingTimer.restart()
            break
        case "switching":
            switchingTimer.restart()
            break
        case "preparing":
            preparingTimer.restart()
            break
        case "diarize-ready":
            diarizeReadyTimer.restart()
            break
        case "idle":
            root.activeButton = ""
            break
        }
    }
```

- [ ] **Step 6: Ajouter les timers manquants**

Après les timers existants, ajouter :

```qml
    // Timer de sécurité pour preparing (30s max)
    Timer {
        id: preparingTimer
        interval: 30000
        running: false; repeat: false
        onTriggered: {
            if (root.state === "preparing") {
                _dbg("TIMEOUT: preparing 30s — cancelling")
                executable.run("dictee --cancel")
            }
        }
    }

    // Timer de sécurité pour diarize-ready (120s max — user forgot?)
    Timer {
        id: diarizeReadyTimer
        interval: 120000
        running: false; repeat: false
        onTriggered: {
            if (root.state === "diarize-ready") {
                _dbg("TIMEOUT: diarize-ready 120s — cancelling")
                executable.run("dictee --cancel")
            }
        }
    }
```

- [ ] **Step 7: Réécrire `handleAction()`**

Remplacer la fonction `handleAction()` :

```javascript
    function handleAction(action) {
        _dbg("action: " + action + " (state=" + root.state + ")")

        switch (action) {
        case "dictate":
            executable.run(root.activeButton === "diarize" ? "dictee --diarize" : "dictee")
            break
        case "dictate-translate":
            executable.run("dictee --translate")
            break
        case "diarize-prepare":
            executable.run("dictee-switch-backend diarize true")
            break
        case "cancel":
            executable.run("dictee --cancel")
            break
        case "start-daemon":
            executable.run("bash -c '" +
                "conf=${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf; " +
                "svc=dictee; " +
                "if [ -f \"$conf\" ]; then " +
                "  b=$(grep ^DICTEE_ASR_BACKEND= \"$conf\" | cut -d= -f2); " +
                "  case $b in vosk) svc=dictee-vosk;; whisper) svc=dictee-whisper;; canary) svc=dictee-canary;; esac; " +
                "fi; " +
                "systemctl --user enable --now $svc'")
            break
        case "stop-daemon":
            executable.run("bash -c 'for s in dictee dictee-vosk dictee-whisper dictee-canary; do systemctl --user stop $s 2>/dev/null; systemctl --user reset-failed $s 2>/dev/null; done'")
            break
        case "reset": {
            var svcMap = { "parakeet": "dictee", "vosk": "dictee-vosk", "whisper": "dictee-whisper", "canary": "dictee-canary" }
            var svc = svcMap[root.currentAsrBackend] || "dictee"
            executable.run("dictee-reset " + svc)
            root.activeButton = ""
            break
        }
        case "transcribe-file":
            executable.run("env QT_QPA_PLATFORMTHEME=kde dictee-transcribe")
            break
        case "setup":
            executable.run("env QT_QPA_PLATFORMTHEME=kde dictee-setup")
            break
        case "postprocess":
            executable.run("env QT_QPA_PLATFORMTHEME=kde dictee-setup --postprocess")
            break
        }
    }
```

- [ ] **Step 8: Supprimer le readConfCmd `DICTEE_DIARIZE`**

Dans `readConfCmd` (~ligne 259), supprimer `$DICTEE_DIARIZE|` de la commande et la lecture en onNewData (~lignes 118-120).

Dans `onNewData` (vers ligne 159), supprimer la branche `DIARIZE_READY` :
```javascript
// SUPPRIMER:
} else if (stdout.indexOf("DIARIZE_READY") !== -1) {
    root.diarizeEnabled = true
}
```

- [ ] **Step 9: Commit**

```bash
git add plasmoid/package/contents/ui/main.qml
git commit -m "refactor: plasmoid main.qml — pur lecteur d'état, plus d'état local"
```

---

### Task 6: Frontend — Plasmoid `FullRepresentation.qml` refactorisé

**Files:**
- Modify: `plasmoid/package/contents/ui/FullRepresentation.qml`

- [ ] **Step 1: Supprimer `diarizeResetCount` et son handler**

Supprimer les lignes ~13-21 :
```qml
// SUPPRIMER:
property int diarizeResetCount: 0
onDiarizeResetCountChanged: { ... }
```

- [ ] **Step 2: Simplifier enabled de btnDictate et btnTranslate**

Ligne ~246, remplacer :
```qml
enabled: (fullRep.state === "idle" || fullRep.state === "recording") && btnDiarize.dState === "idle"
```
par :
```qml
enabled: fullRep.state === "idle" || fullRep.state === "recording"
```

Même chose ligne ~283 pour btnTranslate.

- [ ] **Step 3: Réécrire le bloc btnDiarize**

Remplacer tout le `PlasmaComponents.Button { id: btnDiarize ... }` (~lignes 309-424) par :

```qml
        PlasmaComponents.Button {
            id: btnDiarize
            Layout.fillWidth: true
            Layout.preferredWidth: 0

            enabled: root.sortformerAvailable && (
                fullRep.state === "idle" ||
                fullRep.state === "preparing" ||
                fullRep.state === "diarize-ready" ||
                (fullRep.state === "recording" && root.activeButton === "diarize")
            )

            contentItem: RowLayout {
                spacing: 4
                Kirigami.Icon {
                    source: "group"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                }
                PlasmaComponents.Label {
                    text: {
                        switch (fullRep.state) {
                            case "preparing":    return i18n("Preparing… (click to cancel)")
                            case "diarize-ready": return i18n("Start diarization")
                            case "diarizing":    return i18n("Diarization in progress...")
                            default:
                                if (fullRep.state === "recording" && root.activeButton === "diarize")
                                    return i18n("Stop diarization")
                                return i18n("Diarization")
                        }
                    }
                    color: {
                        if (fullRep.state === "diarize-ready") return "#98c379"
                        if (fullRep.state === "recording" && root.activeButton === "diarize") return "#e06c75"
                        return Kirigami.Theme.textColor
                    }
                }
            }

            onClicked: {
                switch (fullRep.state) {
                    case "idle":
                        root.activeButton = "diarize"
                        fullRep.actionRequested("diarize-prepare")
                        break
                    case "preparing":
                        fullRep.actionRequested("cancel")
                        break
                    case "diarize-ready":
                        fullRep.actionRequested("dictate")
                        break
                    case "recording":
                        // Stop recording (toggle)
                        fullRep.actionRequested("dictate")
                        break
                }
            }

            // Pulse animation during preparing
            opacity: fullRep.state === "preparing" ? pulseAnim.currentOpacity : 1.0

            SequentialAnimation {
                id: pulseAnim
                property real currentOpacity: 1.0
                running: fullRep.state === "preparing"
                loops: Animation.Infinite
                NumberAnimation { target: pulseAnim; property: "currentOpacity"; to: 0.4; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { target: pulseAnim; property: "currentOpacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            }

            QQC2.ToolTip.text: {
                if (!root.sortformerAvailable)
                    return i18n("Sortformer model not installed. Configure in dictee-setup.")
                switch (fullRep.state) {
                    case "preparing": return i18n("Freeing GPU memory...")
                    case "diarize-ready": return i18n("Click to start recording with speaker identification")
                    case "recording": return root.activeButton === "diarize"
                        ? i18n("Click to stop and identify speakers")
                        : i18n("Record and identify speakers (max 4)")
                    default: return i18n("Record and identify speakers (max 4)")
                }
            }
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }
```

- [ ] **Step 4: Supprimer `_handleEsc()` et `Keys.onEscapePressed`**

Supprimer la fonction `_handleEsc()` (~lignes 427-437) et le handler `Keys.onEscapePressed` (~ligne 440).

- [ ] **Step 5: Mettre à jour le point de couleur d'état**

Dans le Rectangle de couleur du statut (~lignes 84-101), ajouter les cas manquants :

```qml
            color: {
                switch (fullRep.state) {
                case "offline":
                    return Kirigami.Theme.negativeTextColor
                case "recording":
                    return Kirigami.Theme.highlightColor
                case "transcribing":
                    return Kirigami.Theme.positiveTextColor
                case "switching":
                    return Kirigami.Theme.neutralTextColor
                case "preparing":
                case "diarize-ready":
                case "diarizing":
                    return "#9B59B6"
                default:
                    return Kirigami.Theme.positiveTextColor
                }
            }
```

- [ ] **Step 6: Mettre à jour le texte de statut**

Dans le label de statut (~lignes 104-123), ajouter :

```qml
                case "preparing":
                    return i18n("Preparing diarization…")
                case "diarize-ready":
                    return i18n("Ready for diarization")
```

- [ ] **Step 7: Supprimer `Component.onCompleted: forceActiveFocus()`**

Ligne ~614 — plus nécessaire car on ne capture plus ESC dans le popup.

- [ ] **Step 8: Copier vers le plasmoid installé et tester**

```bash
cp plasmoid/package/contents/ui/FullRepresentation.qml \
   ~/.local/share/plasma/plasmoids/com.github.rcspam.dictee/contents/ui/FullRepresentation.qml
cp plasmoid/package/contents/ui/main.qml \
   ~/.local/share/plasma/plasmoids/com.github.rcspam.dictee/contents/ui/main.qml
kquitapp6 plasmashell; sleep 2; plasmashell --replace &disown
```

Vérifier : ouvrir popup, tous les boutons visibles, état idle affiché.

- [ ] **Step 9: Commit**

```bash
git add plasmoid/package/contents/ui/FullRepresentation.qml
git commit -m "refactor: plasmoid FullRepresentation — bouton diarize lit state file, plus d'état local"
```

---

### Task 7: Frontend — Tray `dictee-tray.py` refactorisé

**Files:**
- Modify: `dictee-tray.py:221-228` (ICON_MAP)
- Modify: `dictee-tray.py:562-568` (GTK cancel)
- Modify: `dictee-tray.py:942-948` (Qt cancel)
- Modify: `dictee-tray.py` (state mappings, tooltips)

- [ ] **Step 1: Mettre à jour ICON_MAP**

Remplacer ICON_MAP (lignes 221-228) :

```python
ICON_MAP = {
    "idle": "parakeet-active-dark" if _DARK else "parakeet-active",
    "offline": "parakeet-offline",
    "recording": "parakeet-recording",
    "transcribing": "parakeet-transcribing",
    "diarize": "parakeet-diarize",
    "diarizing": "parakeet-diarize",
    "preparing": "parakeet-diarize",
    "diarize-ready": "parakeet-diarize",
}
```

- [ ] **Step 2: Simplifier le cancel GTK**

Dans `_cancel()` GTK (~lignes 562-568), remplacer par :

```python
    def _cancel(self, *_args):
        subprocess.Popen(["dictee", "--cancel"])
```

Supprimer le bloc `if self.item_diarize_gtk.get_active()` qui faisait `dictee-switch-backend diarize false`.

- [ ] **Step 3: Simplifier le cancel Qt**

Dans `_cancel()` Qt (~lignes 942-948), même simplification :

```python
    def _cancel(self):
        subprocess.Popen(["dictee", "--cancel"])
```

- [ ] **Step 4: Ajouter les nouveaux états aux mappings**

Dans les fonctions `_check_state()` (GTK ~ligne 583, Qt ~ligne 963), s'assurer que `"preparing"` et `"diarize-ready"` sont traités comme des états valides.

Dans les tooltips/labels Qt (~lignes 982-1008), ajouter :

```python
"preparing": _("Preparing diarization…"),
"diarize-ready": _("Ready for diarization"),
```

Dans les labels du menu dot (~ligne 1007), ajouter les couleurs :

```python
if self.state in ("preparing", "diarize-ready", "diarizing"):
    dot_color = "#9B59B6"
```

- [ ] **Step 5: Relancer le tray et tester**

```bash
pkill -f dictee-tray; sleep 0.5; dictee-tray &disown
```

- [ ] **Step 6: Commit**

```bash
git add dictee-tray.py
git commit -m "refactor: tray — pur lecteur d'état, cancel simplifié, nouveaux états"
```

---

### Task 8: Frontend — `dictee-ptt.py` vérifie l'état avant ESC

**Files:**
- Modify: `dictee-ptt.py:240-248` (ESC handler)

- [ ] **Step 1: Ajouter lecture du state file**

Ajouter une constante et une fonction helper en haut du fichier :

```python
STATE_FILE = "/dev/shm/.dictee_state"

def read_state():
    """Read current state from state file."""
    try:
        return open(STATE_FILE).read().strip()
    except (FileNotFoundError, PermissionError):
        return "offline"
```

- [ ] **Step 2: Modifier le handler ESC**

Dans le handler ESC (~lignes 240-248), remplacer la condition :

```python
if code == KEY_ESC and value == KEY_DOWN:
    state = read_state()
    if state in ("recording", "preparing", "diarize-ready", "diarizing"):
        log(f"ESC: state={state} — sending cancel")
        run_dictee_async("--cancel")
    return False
```

Supprimer la condition basée sur `self.recording or self.recording_translate` — on se base sur le state file.

- [ ] **Step 3: Tester ESC dans différents états**

```bash
# ESC pendant idle → pas de cancel
dictee-reset dictee; sleep 1
# (appuyer ESC manuellement, vérifier pas de log cancel)

# ESC pendant recording → cancel
dictee & sleep 1.5
# (appuyer ESC, vérifier state → cancelled/idle)

# ESC pendant preparing → cancel
dictee-switch-backend diarize true &
sleep 0.5
# (appuyer ESC, vérifier state → idle, daemon restauré)
```

- [ ] **Step 4: Commit**

```bash
git add dictee-ptt.py
git commit -m "refactor: dictee-ptt vérifie state file avant d'agir sur ESC"
```

---

### Task 9: Tests de robustesse complets

**Files:**
- Modify: `/tmp/dictee-full-tests.sh` (mettre à jour pour nouveaux états)

- [ ] **Step 1: Relancer les tests existants**

```bash
bash /tmp/dictee-robustness-tests.sh
bash /tmp/dictee-fast-tests.sh
```

Les 25 tests doivent passer.

- [ ] **Step 2: Relancer les tests complets**

```bash
bash /tmp/dictee-full-tests.sh
```

Les 30 tests doivent passer. Si certains échouent à cause des nouveaux états, les adapter.

- [ ] **Step 3: Tests manuels diarisation**

Tester via le plasmoid :
1. Clic Diarize → "Preparing…" → attend "Start diarization" → clic → enregistre → clic stop → fenêtre dictee-transcribe s'ouvre
2. Clic Diarize → "Preparing…" → clic cancel → F9 → dictée NORMALE
3. Clic Diarize → "Preparing…" → ESC physique (via dictee-ptt) → F9 → dictée NORMALE
4. Clic Diarize → "Start diarization" → ESC physique → F9 → dictée NORMALE
5. Clic Diarize → "Start diarization" → fermer popup → rouvrir → état toujours "Start diarization"

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "fix: diarize cancel during preparing phase — state file as single authority

Refactoring complet v1.3 :
- State file (/dev/shm/.dictee_state) = seule source de vérité
- Nouveaux états: preparing, diarize-ready
- Plasmoid/tray = purs lecteurs d'état
- Un seul chemin ESC (dictee-ptt)
- Plus de race conditions diarize/F9/ESC"
```
