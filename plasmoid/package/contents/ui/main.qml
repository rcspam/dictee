import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // State: "offline", "idle", "recording", "transcribing", "switching"
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
                    root.state = "offline"
                } else if (stdout === "not-configured") {
                    root.dicteeInstalled = true
                    root.dicteeConfigured = false
                    root.state = "offline"
                } else {
                    root.dicteeInstalled = true
                    root.dicteeConfigured = true
                    // Polling lent : offline/idle — jamais pendant recording/transcribing
                    if (stdout === "offline" && root.state !== "recording" && root.state !== "transcribing" && root.state !== "switching") {
                        root.state = "offline"
                    } else if (stdout !== "offline" && root.state === "offline") {
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
                    var tb = parts[1] || "trans"
                    var te = parts[2] || "google"
                    if (tb === "trans") {
                        root.currentTranslateBackend = te
                    } else {
                        root.currentTranslateBackend = tb
                    }
                }
                if (parts.length >= 4) {
                    root.diarizeEnabled = (parts[3] === "true")
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
            } else if (source === micVolumeCmd) {
                // Parse "Volume: 0.50" or "Volume: 0.50 [MUTED]"
                var volMatch = stdout.match(/Volume:\s+(\d+\.?\d*)/)
                if (volMatch) {
                    root.micVolume = parseFloat(volMatch[1])
                }
                root.micMuted = stdout.indexOf("[MUTED]") !== -1
            } else if (stdout.indexOf("DIARIZE_READY") !== -1) {
                // Diarization backend ready
                root.diarizeEnabled = true
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
        running: root.effectiveState === "recording"
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
    property string daemonCheckCmd: "bash -c 'command -v dictee >/dev/null 2>&1 || { echo not-installed; exit; }; conf=${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf; [ -f \"$conf\" ] || { echo not-configured; exit; }; grep -q DICTEE_SETUP_DONE=true \"$conf\" || { echo not-configured; exit; }; for s in dictee dictee-vosk dictee-whisper dictee-canary; do systemctl --user is-active $s 2>/dev/null | grep -qx active && echo idle && exit; done; echo offline'"

    // Current backend state (read from config)
    property string currentAsrBackend: "parakeet"
    property string currentTranslateBackend: "google"
    property var installedAsr: ["parakeet", "canary", "vosk", "whisper"]  // updated by checkInstalledCmd
    property var installedTranslate: ["google", "bing", "ollama", "libretranslate"]  // updated by checkInstalledCmd
    property bool sortformerAvailable: false  // updated by checkInstalledCmd
    property real micVolume: 0.5  // microphone volume (0.0-1.5)
    property bool micMuted: false
    property string micVolumeCmd: "wpctl get-volume @DEFAULT_SOURCE@"
    property bool diarizeEnabled: false  // read from config
    property string activeButton: ""  // "dictate", "dictate-translate", or "diarize"
    property string readConfCmd: "bash -c 'source \"${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf\" 2>/dev/null; echo \"$DICTEE_ASR_BACKEND|$DICTEE_TRANSLATE_BACKEND|$DICTEE_TRANS_ENGINE|$DICTEE_DIARIZE\"'"
    property string checkInstalledCmd: "bash -c '" +
        "dd=${XDG_DATA_HOME:-$HOME/.local/share}/dictee; " +
        "{ [ -d /usr/share/dictee/tdt ] || [ -d \"$dd/tdt\" ]; } && command -v transcribe-daemon >/dev/null 2>&1 && echo parakeet; " +
        "[ -d \"$dd/canary-env/lib\" ] && echo canary; " +
        "[ -d \"$dd/vosk-env/lib\" ] && echo vosk; " +
        "[ -d \"$dd/whisper-env/lib\" ] && echo whisper; " +
        "echo ---; " +
        "command -v trans >/dev/null 2>&1 && echo google && echo bing; " +
        "command -v ollama >/dev/null 2>&1 && { m=$(. \"${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf\" 2>/dev/null; echo \"${DICTEE_OLLAMA_MODEL:-translategemma}\"); ollama list 2>/dev/null | grep -q \"${m%%:*}\" && echo ollama; }; " +
        "command -v docker >/dev/null 2>&1 && echo libretranslate; " +
        "echo ---; " +
        "{ [ -d /usr/share/dictee/sortformer ] || [ -d \"$dd/sortformer\" ]; } && echo sortformer'"

    function refreshBackends() {
        executable.run(readConfCmd)
        executable.run(checkInstalledCmd)
        executable.run(micVolumeCmd)
    }

    // Ping-pong pour l'état aussi
    property int stateSlot: 0
    property bool stateReadPending: false
    readonly property var stateCmds: [
        "cat /dev/shm/.dictee_state 2>/dev/null #A",
        "cat /dev/shm/.dictee_state 2>/dev/null #B"
    ]

    function parseState(output) {
        var newState = output.trim()
        if (newState === "cancelled") {
            transcribingTimer.stop()
            recordingTimer.stop()
            root.state = "idle"
            return
        }
        if (newState === "recording") {
            root.state = "recording"
            recordingTimer.restart()
        } else if (newState === "transcribing" && root.state !== "transcribing") {
            root.state = "transcribing"
            recordingTimer.stop()
            transcribingTimer.restart()
        } else if (newState === "switching") {
            root.state = "switching"
            transcribingTimer.stop()
            recordingTimer.stop()
            switchingTimer.restart()
        } else if (newState === "idle") {
            // Retour à idle depuis n'importe quel état actif
            if (root.state === "recording" || root.state === "transcribing" || root.state === "switching") {
                transcribingTimer.stop()
                recordingTimer.stop()
                switchingTimer.stop()
                root.state = "idle"
                root.activeButton = ""
            }
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
                root.state = "idle"
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
                root.state = "offline"
            }
        }
    }

    compactRepresentation: CompactRepresentation {
        state: root.effectiveState
        barColor: root.barColor
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

    property real lastActionTime: 0

    function handleAction(action) {
        // Debounce: ignore actions within 800ms
        var now = Date.now()
        if (now - lastActionTime < 800) return
        lastActionTime = now

        switch (action) {
        case "dictate":
            if (root.state === "recording") {
                if (!Plasmoid.configuration.pinPopup) root.expanded = false
                root.state = "transcribing"
                transcribingTimer.start()
            } else {
                root.state = "recording"
            }
            executable.run("dictee")
            break
        case "dictate-translate":
            if (root.state === "recording") {
                if (!Plasmoid.configuration.pinPopup) root.expanded = false
                root.state = "transcribing"
                transcribingTimer.start()
            } else {
                root.state = "recording"
            }
            executable.run("dictee --translate")
            break
        case "cancel":
            executable.run("dictee --cancel")
            root.state = "idle"
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
            root.state = "idle"
            break
        case "stop-daemon":
            executable.run("bash -c 'for s in dictee dictee-vosk dictee-whisper dictee-canary; do systemctl --user stop $s 2>/dev/null; systemctl --user reset-failed $s 2>/dev/null; done'")
            root.state = "offline"
            break
        case "reset":
            executable.run("bash -c 'echo idle > /dev/shm/.dictee_state; dictee --cancel 2>/dev/null'")
            transcribingTimer.stop()
            recordingTimer.stop()
            root.state = "idle"
            break
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

    function preStartAudioDaemon() {
        var cmd = "dictee-plasmoid-level"
        var style = Plasmoid.configuration.animationStyle || "bars"
        if (style === "bars") {
            cmd += " " + Plasmoid.configuration.barCount
        } else if (style === "waveform") {
            cmd += " " + Plasmoid.configuration.waveformBars
        }
        executable.run(cmd)
    }

    // Lancer le daemon audio au chargement pour éviter la latence
    Component.onCompleted: {
        preStartAudioDaemon()
        refreshBackends()
    }

    Component.onDestruction: {
        executable.run("dictee-plasmoid-level stop")
    }
}
