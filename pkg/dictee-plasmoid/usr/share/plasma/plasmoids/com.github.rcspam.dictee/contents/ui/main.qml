import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // Le plasmoid hérite par défaut du color set du panel (souvent sombre).
    // Forcer View garantit que le popup (FullRepresentation) suit le thème des
    // applications — blanc en Breeze Light, sombre en Breeze Dark.
    Kirigami.Theme.colorSet: Kirigami.Theme.View
    Kirigami.Theme.inherit: false

    // State: "offline", "idle", "recording", "transcribing", "switching", "preparing", "diarize-ready", "diarizing"
    property string state: "offline"
    property bool dicteeInstalled: true
    property bool dicteeConfigured: false
    property string lastTranscription: ""
    // Niveau audio micro (0.0 - 1.0)
    property real audioLevel: 0.0
    // Bandes de frequences (pour le mode spectre des barres)
    property var audioBands: []
    // Etat effectif (preview force recording)
    readonly property string effectiveState: Plasmoid.configuration.previewMode ? "recording" : state

    // Sensibilité active selon le style d'animation (contrôle la courbe de puissance)
    readonly property real activeSensitivity: {
        var style = Plasmoid.configuration.animationStyle || "bars"
        switch (style) {
        case "bars":     return Plasmoid.configuration.barSensitivity      || 2.0
        case "wave":     return Plasmoid.configuration.waveSensitivity     || 2.0
        case "pulse":    return Plasmoid.configuration.pulseSensitivity    || 2.0
        case "dots":     return Plasmoid.configuration.dotSensitivity      || 2.0
        case "waveform": return Plasmoid.configuration.waveformSensitivity || 2.0
        default:         return Plasmoid.configuration.audioSensitivity    || 2.0
        }
    }

    // Couleur des barres selon l'etat
    property color barColor: {
        switch (effectiveState) {
        case "recording":
            return Kirigami.Theme.highlightColor
        case "transcribing":
            return Kirigami.Theme.positiveTextColor
        case "offline":
            return Kirigami.Theme.negativeTextColor
        case "idle":
            return Kirigami.Theme.textColor
        default:
            return Kirigami.Theme.textColor
        }
    }

    switchWidth: Kirigami.Units.gridUnit * 18
    switchHeight: Kirigami.Units.gridUnit * 12

    toolTipMainText: "Dictee"
    toolTipSubText: {
        switch (state) {
        case "offline":
            if (!root.dicteeInstalled) return i18n("Dictée not installed")
            if (!root.dicteeConfigured) return i18n("Dictée not configured — run dictee-setup")
            return i18n("Daemon stopped")
        case "idle":
            return i18n("Daemon active")
        case "recording":
            return i18n("Recording…")
        case "transcribing":
            return i18n("Transcribing…")
        case "switching":
            return i18n("Switching backend…")
        case "preparing":
            return i18n("Preparing…")
        case "diarize-ready":
            return i18n("Diarize ready")
        case "diarizing":
            return i18n("Diarizing…")
        default:
            return ""
        }
    }

    // DataSource pour les commandes ponctuelles (etat, actions)
    Plasma5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            var stdout = data["stdout"].trim()

            if (source === daemonCheckCmd) {
                // Check if dictee is installed and configured
                if (stdout === "not-installed") {
                    root.dicteeInstalled = false
                    root.dicteeConfigured = false
                    console.log("[dictee-plasmoid] daemonCheck: not-installed → offline")
                    root.state = "offline"
                } else if (stdout === "not-configured") {
                    root.dicteeInstalled = true
                    root.dicteeConfigured = false
                    console.log("[dictee-plasmoid] daemonCheck: not-configured → offline")
                    root.state = "offline"
                } else {
                    root.dicteeInstalled = true
                    root.dicteeConfigured = true
                    // Polling lent : offline/idle — jamais pendant recording/transcribing
                    if (stdout === "offline" && root.state !== "recording" && root.state !== "transcribing" && root.state !== "switching" && root.state !== "preparing" && root.state !== "diarize-ready" && root.state !== "diarizing") {
                        console.log("[dictee-plasmoid] daemonCheck: OFFLINE (root.state=" + root.state + ")")
                        root.state = "offline"
                    } else if (stdout !== "offline" && root.state === "offline") {
                        console.log("[dictee-plasmoid] daemonCheck: was offline → idle")
                        root.state = "idle"
                    }
                }
            } else if (source.indexOf("/dev/shm/.dictee_state") !== -1) {
                root.stateReadPending = false
                if (stdout.length > 0) {
                    parseState(stdout)
                }
            } else if (source === readConfCmd) {
                var parts = stdout.trim().split("|")
                if (parts.length >= 3) {
                    root.currentAsrBackend = parts[0] || "parakeet"
                    // Don't overwrite translate backend during grace period after user change
                    if (Date.now() - root.backendUserChangeTime > 3000) {
                        var tb = parts[1] || "trans"
                        var te = parts[2] || "google"
                        if (tb === "trans") {
                            root.currentTranslateBackend = te
                        } else {
                            root.currentTranslateBackend = tb
                        }
                    }
                }
                if (parts.length >= 4) {
                    root.currentAudioSource = parts[3] || ""
                }
                if (parts.length >= 5) {
                    root.currentLangTarget = parts[4] || "en"
                }
                if (parts.length >= 6) {
                    root.currentLangSource = parts[5] || "fr"
                }
                if (parts.length >= 7) {
                    root.audioContextEnabled = (parts[6] === "true")
                }
            } else if (source.indexOf("dictee-translate-langs") !== -1) {
                var langs = stdout.trim()
                var newList = langs.length > 0 ? langs.split(",") : []
                // Only update if the list actually changed (avoids resetting combo scroll)
                if (JSON.stringify(newList) !== JSON.stringify(root.availableLangTarget)) {
                    root.availableLangTarget = newList
                }
            } else if (source === checkInstalledCmd) {
                var parts = stdout.trim().split("---")
                var asrList = parts[0].trim().split("\n").filter(function(s) { return s.length > 0 })
                if (asrList.length > 0) {
                    root.installedAsr = asrList
                }
                if (parts.length > 1) {
                    var trList = parts[1].trim().split("\n").filter(function(s) { return s.length > 0 })
                    if (trList.length > 0) {
                        root.installedTranslate = trList
                    }
                }
                if (parts.length > 2) {
                    root.sortformerAvailable = parts[2].trim().indexOf("sortformer") !== -1
                }
            } else if (source === listAudioSourcesCmd) {
                var lines = stdout.trim().split("\n").filter(function(s) { return s.length > 0 })
                var sources = []
                for (var i = 0; i < lines.length; i++) {
                    var p = lines[i].split("|")
                    if (p.length >= 3) {
                        sources.push({ value: p[0], icon: p[1], label: p[2] })
                    }
                }
                root.audioSourceList = sources
            } else if (source === micVolumeCmd) {
                // Parse "Volume: 0.50" or "Volume: 0.50 [MUTED]"
                var volMatch = stdout.match(/Volume:\s+(\d+\.?\d*)/)
                if (volMatch) {
                    root.micVolume = parseFloat(volMatch[1])
                }
                root.micMuted = stdout.indexOf("[MUTED]") !== -1
            } else if (source === ltCheckCmd) {
                root.ltRunning = (stdout.trim() === "true")
            } else if (source === ollamaCheckCmd) {
                root.ollamaStatus = stdout.trim()  // "ok", "no-model", or "stopped"
            } else if (stdout.indexOf("DICTEE_DEBUG_ON") !== -1) {
                root.debugEnabled = true
                _dbg("debug enabled via DICTEE_DEBUG=true")
            } else if (source.indexOf("transcribe-client --last") !== -1) {
                if (stdout.length > 0) {
                    root.lastTranscription = stdout
                }
            }
            disconnectSource(source)
        }
        function run(cmd) {
            connectSource(cmd)
        }
    }

    // DataSource pour lire le niveau audio — ping-pong entre 2 sources
    Plasma5Support.DataSource {
        id: audioExec
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            var output = data["stdout"].trim()
            if (output.length > 0) {
                var gate = Plasmoid.configuration.noiseGate || 0.0
                var parts = output.split(" ")
                if (parts.length > 1) {
                    var bands = []
                    var sum = 0
                    for (var i = 0; i < parts.length; i++) {
                        var v = parseFloat(parts[i])
                        if (!isNaN(v)) {
                            v = Math.min(1.0, v)
                            if (v < gate) v = 0.0
                            bands.push(v)
                            sum += v
                        }
                    }
                    if (bands.length > 0) {
                        root.audioBands = bands
                        root.audioLevel = sum / bands.length
                    }
                } else {
                    var level = parseFloat(output)
                    if (!isNaN(level)) {
                        level = Math.min(1.0, level)
                        if (level < gate) level = 0.0
                        root.audioLevel = level
                    }
                }
            }
            root.audioReadPending = false
            disconnectSource(source)
        }
    }

    // Ping-pong : 2 noms de source seulement, jamais d'accumulation
    property int audioSlot: 0
    property bool audioReadPending: false
    readonly property var audioCmds: [
        "cat /dev/shm/.dictee_audio_bands #A",
        "cat /dev/shm/.dictee_audio_bands #B"
    ]

    // Timer de lecture niveau audio (~12 fps)
    Timer {
        id: audioTimer
        interval: 80
        running: root.effectiveState === "recording" || root.expanded
        repeat: true
        onTriggered: {
            if (!root.audioReadPending) {
                root.audioReadPending = true
                root.audioSlot = 1 - root.audioSlot
                audioExec.connectSource(root.audioCmds[root.audioSlot])
            }
        }
        onRunningChanged: {
            if (!running) {
                root.audioLevel = 0.0
                root.audioBands = []
            }
        }
    }

    // Commande lente : vérifier si le daemon tourne (pour offline/idle)
    property string daemonCheckCmd: "bash -c 'command -v dictee >/dev/null 2>&1 || { echo not-installed; exit; }; conf=${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf; [ -f \"$conf\" ] || { echo not-configured; exit; }; grep -q ^DICTEE_SETUP_DONE=true \"$conf\" || { echo not-configured; exit; }; for s in dictee dictee-vosk dictee-whisper dictee-canary; do systemctl --user is-active $s 2>/dev/null | grep -qx active && echo idle && exit; done; echo offline'"

    // Current backend state (read from config)
    property string currentAsrBackend: "parakeet"
    property string currentTranslateBackend: "google"
    property var installedAsr: ["parakeet", "canary", "vosk", "whisper"]  // updated by checkInstalledCmd
    property var installedTranslate: ["google", "bing", "ollama", "libretranslate"]  // updated by checkInstalledCmd
    property bool sortformerAvailable: false  // updated by checkInstalledCmd
    property real micVolume: 0.5  // microphone volume (0.0-1.5)
    property bool micMuted: false
    property string micVolumeCmd: "wpctl get-volume @DEFAULT_SOURCE@"
    property string activeButton: ""  // "dictate", "dictate-translate", or "diarize"
    property string currentLangSource: "fr"
    property string currentLangTarget: "en"
    property var availableLangTarget: []
    property real backendUserChangeTime: 0  // timestamp of last user-initiated backend change
    property string readConfCmd: "bash -c 'source \"${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf\" 2>/dev/null; echo \"$DICTEE_ASR_BACKEND|$DICTEE_TRANSLATE_BACKEND|$DICTEE_TRANS_ENGINE|$DICTEE_AUDIO_SOURCE|$DICTEE_LANG_TARGET|$DICTEE_LANG_SOURCE|$DICTEE_AUDIO_CONTEXT\"'"
    property string translateLangsCmd: "dictee-translate-langs"
    property bool audioContextEnabled: false
    property string currentAudioSource: ""
    property var audioSourceList: []
    property string listAudioSourcesCmd: "dictee-audio-sources"
    property string checkInstalledCmd: "bash -c '" +
        "dd=${XDG_DATA_HOME:-$HOME/.local/share}/dictee; " +
        "{ [ -d /usr/share/dictee/tdt ] || [ -d \"$dd/tdt\" ]; } && command -v transcribe-daemon >/dev/null 2>&1 && echo parakeet; " +
        // Canary: Rust native (transcribe-daemon --canary), needs CUDA libs bundled
        // (CPU-only install is too slow in practice → hide Canary from the UI)
        "{ [ -d /usr/share/dictee/canary ] || [ -f \"$dd/canary/encoder-model.onnx\" ]; } " +
        "  && command -v transcribe-daemon >/dev/null 2>&1 " +
        "  && [ -f /usr/lib/dictee/libonnxruntime_providers_cuda.so ] " +
        "  && echo canary; " +
        "[ -d \"$dd/vosk-env/lib\" ] && echo vosk; " +
        "[ -d \"$dd/whisper-env/lib\" ] && echo whisper; " +
        "echo ---; " +
        "command -v trans >/dev/null 2>&1 && echo google && echo bing; " +
        "command -v ollama >/dev/null 2>&1 && { m=$(. \"${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf\" 2>/dev/null; echo \"${DICTEE_OLLAMA_MODEL:-translategemma}\"); ollama list 2>/dev/null | grep -q \"${m%%:*}\" && echo ollama; }; " +
        "command -v docker >/dev/null 2>&1 && echo libretranslate; " +
        "echo ---; " +
        "{ [ -d /usr/share/dictee/sortformer ] || [ -d \"$dd/sortformer\" ]; } && echo sortformer'"

    property string lastTranslateBackendForLangs: ""
    property bool ltRunning: false
    property string ltCheckCmd: "bash -c 'docker inspect -f {{.State.Running}} dictee-libretranslate 2>/dev/null || echo false'"
    // Ollama status: "ok" = running + model present, "no-model" = running but model missing, "stopped" = service down
    property string ollamaStatus: "ok"
    property string ollamaCheckCmd: "bash -c '" +
        "if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then echo stopped; " +
        "else m=$(. \"${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf\" 2>/dev/null; echo \"${DICTEE_OLLAMA_MODEL:-translategemma}\"); " +
        "[[ \"$m\" == *:* ]] || m=\"${m}:latest\"; " +
        "if ollama list 2>/dev/null | awk \"NR>1{print \\$1}\" | grep -qx \"$m\"; then echo ok; else echo no-model; fi; fi'"
    function refreshBackends() {
        executable.run(readConfCmd)
        executable.run(checkInstalledCmd)
        executable.run(micVolumeCmd)
        executable.run(listAudioSourcesCmd)
        // Refresh translate langs (always — combo may be empty on first open)
        root.lastTranslateBackendForLangs = root.currentTranslateBackend
        executable.run(translateLangsCmd + " " + root.currentTranslateBackend)
        // Check translation backend status
        if (root.currentTranslateBackend === "libretranslate") {
            executable.run(ltCheckCmd)
        } else if (root.currentTranslateBackend === "ollama") {
            executable.run(ollamaCheckCmd)
        }
    }

    // Ping-pong pour l'état aussi
    property int stateSlot: 0
    property bool stateReadPending: false
    readonly property var stateCmds: [
        "cat /dev/shm/.dictee_state 2>/dev/null #A",
        "cat /dev/shm/.dictee_state 2>/dev/null #B"
    ]

    // Debug — reads DICTEE_DEBUG from config, logs to journalctl --user -u plasma-plasmashell
    property bool debugEnabled: false
    function _dbg(msg) {
        if (debugEnabled) console.log("[dictee-plasmoid] " + msg)
    }

    function parseState(output) {
        var newState = output.trim()
        if (newState === root.state || newState === "") return
        console.log("[dictee-plasmoid] parseState: " + root.state + " → " + newState)

        // Stop all safety timers on any transition
        transcribingTimer.stop()
        recordingTimer.stop()
        diarizingTimer.stop()
        switchingTimer.stop()
        preparingTimer.stop()
        diarizeReadyTimer.stop()

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

    // Timer rapide : lit /dev/shm/.dictee_state toutes les 150ms
    Timer {
        id: fastPollTimer
        interval: 150
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            if (!root.stateReadPending) {
                root.stateReadPending = true
                root.stateSlot = 1 - root.stateSlot
                executable.run(root.stateCmds[root.stateSlot])
            }
        }
    }

    // Timer lent : vérifie si le daemon est en ligne (toutes les N secondes)
    Timer {
        id: daemonPollTimer
        interval: Plasmoid.configuration.pollingInterval
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            executable.run(daemonCheckCmd)
            refreshBackends()
        }
    }

    // Timer pour l'etat transcribing (temporaire, 8s max)
    Timer {
        id: transcribingTimer
        interval: 8000
        running: false
        repeat: false
        onTriggered: {
            if (root.state === "transcribing") {
                root.state = "idle"
            }
        }
    }

    // Timer de sécurité pour recording (60s max — si le script crash)
    Timer {
        id: recordingTimer
        interval: 60000
        running: false
        repeat: false
        onTriggered: {
            if (root.state === "recording") {
                _dbg("TIMEOUT: recording 60s — forcing idle")
                root.state = "idle"
            }
        }
    }

    // Timer de sécurité pour diarizing (120s max — si dictee-transcribe crash)
    Timer {
        id: diarizingTimer
        interval: 120000
        running: false
        repeat: false
        onTriggered: {
            if (root.state === "diarizing") {
                _dbg("TIMEOUT: diarizing 120s — cancelling")
                executable.run("dictee --cancel")
            }
        }
    }

    // Timer de sécurité pour switching (15s max — si dictee-switch-backend crash)
    Timer {
        id: switchingTimer
        interval: 15000
        running: false
        repeat: false
        onTriggered: {
            if (root.state === "switching") {
                _dbg("TIMEOUT: switching 15s — forcing offline")
                root.state = "offline"
            }
        }
    }

    // Timer de sécurité pour preparing (30s max)
    Timer {
        id: preparingTimer
        interval: 30000
        running: false
        repeat: false
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
        running: false
        repeat: false
        onTriggered: {
            if (root.state === "diarize-ready") {
                _dbg("TIMEOUT: diarize-ready 120s — cancelling")
                executable.run("dictee --cancel")
            }
        }
    }

    compactRepresentation: CompactRepresentation {
        state: root.effectiveState
        // barColor calculated locally in the compact using its
        // Complementary palette (panel-aware contrast).
        audioLevel: root.audioLevel
        audioBands: root.audioBands
        sensitivity: root.activeSensitivity
    }

    fullRepresentation: FullRepresentation {
        state: root.state
        dicteeInstalled: root.dicteeInstalled
        dicteeConfigured: root.dicteeConfigured
        barColor: root.barColor
        lastTranscription: root.lastTranscription
        onActionRequested: function(action) {
            handleAction(action)
        }
    }

    function handleAction(action) {
        _dbg("action: " + action + " (state=" + root.state + ")")

        switch (action) {
        case "dictate":
            if (root.state === "recording" && !Plasmoid.configuration.pinPopup)
                root.expanded = false
            executable.run(root.activeButton === "diarize" ? "dictee --diarize" : "dictee")
            break
        case "dictate-translate":
            if (root.state === "recording" && !Plasmoid.configuration.pinPopup)
                root.expanded = false
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
                "systemctl --user enable --now $svc; echo idle > /dev/shm/.dictee_state'")
            break
        case "stop-daemon":
            executable.run("bash -c 'echo offline > /dev/shm/.dictee_state; for s in dictee dictee-vosk dictee-whisper dictee-canary; do systemctl --user disable --now $s 2>/dev/null; systemctl --user reset-failed $s 2>/dev/null; done'")
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
            if (root.dicteeConfigured) {
                executable.run("env QT_QPA_PLATFORMTHEME=kde dictee-setup")
            } else {
                executable.run("env QT_QPA_PLATFORMTHEME=kde dictee-setup --wizard")
            }
            break
        case "postprocess":
            executable.run("env QT_QPA_PLATFORMTHEME=kde dictee-setup --postprocess")
            break
        }
    }

    function preStartAudioDaemon() {
        var cmd = "dictee-plasmoid-level"
        var style = Plasmoid.configuration.animationStyle || "bars"
        if (style === "bars") {
            cmd += " " + Plasmoid.configuration.barCount
        } else if (style === "waveform") {
            cmd += " " + Plasmoid.configuration.waveformBars
        }
        if (root.currentAudioSource) {
            cmd += " " + root.currentAudioSource
        }
        executable.run(cmd)
    }

    onCurrentTranslateBackendChanged: {
        // Refresh available target languages when translation backend changes
        executable.run(translateLangsCmd + " " + root.currentTranslateBackend)
    }

    onCurrentAudioSourceChanged: {
        // Relancer le daemon level avec la nouvelle source (stop + délai + start)
        executable.run("bash -c 'dictee-plasmoid-level stop; sleep 0.3; " +
            "dictee-plasmoid-level " +
            (function() {
                var style = Plasmoid.configuration.animationStyle || "bars"
                var bars = (style === "waveform") ? Plasmoid.configuration.waveformBars : Plasmoid.configuration.barCount
                return bars + (root.currentAudioSource ? " " + root.currentAudioSource : "")
            })() + "'")
    }

    // Refresh config when popup opens (catches changes from dictee-setup Apply)
    onExpandedChanged: {
        if (expanded) {
            refreshBackends()
        }
    }

    // Load debug flag and start audio daemon
    Component.onCompleted: {
        executable.run("bash -c 'grep -q \"^DICTEE_DEBUG=true\" \"${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf\" 2>/dev/null && echo DICTEE_DEBUG_ON'")
        preStartAudioDaemon()
        refreshBackends()
    }

    Component.onDestruction: {
        executable.run("dictee-plasmoid-level stop")
    }
}
