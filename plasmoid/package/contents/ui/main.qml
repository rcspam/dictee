import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // State: "offline", "idle", "recording", "transcribing"
    property string state: "offline"
    property string lastTranscription: ""
    // Niveau audio micro (0.0 - 1.0)
    property real audioLevel: 0.0
    // Bandes de frequences (pour le mode spectre des barres)
    property var audioBands: []
    // Etat effectif (preview force recording)
    readonly property string effectiveState: Plasmoid.configuration.previewMode ? "recording" : state

    // Sensibilité active selon le style d'animation
    readonly property real activeSensitivity: {
        var style = Plasmoid.configuration.animationStyle || "bars"
        switch (style) {
        case "bars":  return Plasmoid.configuration.barSensitivity  || 2.0
        case "wave":  return Plasmoid.configuration.waveSensitivity || 2.0
        case "pulse": return Plasmoid.configuration.pulseSensitivity || 2.0
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

    switchWidth: Kirigami.Units.gridUnit * 12
    switchHeight: Kirigami.Units.gridUnit * 12

    toolTipMainText: "Dictee"
    toolTipSubText: {
        switch (state) {
        case "offline":
            return i18n("Daemon stopped")
        case "idle":
            return i18n("Daemon active")
        case "recording":
            return i18n("Recording…")
        case "transcribing":
            return i18n("Transcribing…")
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
                // Polling lent : offline ou idle (seulement si pas en recording/transcribing)
                if (stdout === "offline") {
                    root.state = "offline"
                } else if (root.state === "offline") {
                    root.state = "idle"
                }
            } else if (source.indexOf("/dev/shm/.dictee_state") !== -1) {
                root.stateReadPending = false
                if (stdout.length > 0) {
                    parseState(stdout)
                }
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
    property string daemonCheckCmd: "bash -c 'systemctl --user is-active dictee 2>/dev/null | grep -qx active && echo idle || echo offline'"

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
            root.state = "idle"
            return
        }
        // Le fichier d'état ne gère que les transitions actives
        // offline/idle sont gérés exclusivement par daemonCheckCmd (systemctl)
        if (newState === "recording") {
            root.state = "recording"
        } else if (newState === "transcribing" && root.state !== "transcribing") {
            root.state = "transcribing"
            transcribingTimer.start()
        } else if (newState === "idle" && root.state === "recording") {
            root.state = "transcribing"
            transcribingTimer.start()
        }
    }

    // Timer rapide : lit /dev/shm/.dictee_state toutes les 500ms
    Timer {
        id: fastPollTimer
        interval: 500
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

    compactRepresentation: CompactRepresentation {
        state: root.effectiveState
        barColor: root.barColor
        audioLevel: root.audioLevel
        audioBands: root.audioBands
        sensitivity: root.activeSensitivity
    }

    fullRepresentation: FullRepresentation {
        state: root.state
        barColor: root.barColor
        lastTranscription: root.lastTranscription
        onActionRequested: function(action) {
            handleAction(action)
        }
    }

    function handleAction(action) {
        switch (action) {
        case "dictate":
            if (root.state === "recording") {
                root.expanded = false
                root.state = "transcribing"
                transcribingTimer.start()
            } else {
                root.state = "recording"
            }
            executable.run("dictee")
            break
        case "dictate-translate":
            if (root.state === "recording") {
                root.expanded = false
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
            executable.run("systemctl --user start dictee")
            root.state = "idle"
            break
        case "stop-daemon":
            executable.run("systemctl --user stop dictee")
            root.state = "offline"
            break
        case "setup":
            executable.run("dictee-setup")
            break
        }
    }

    function preStartAudioDaemon() {
        var cmd = "dictee-plasmoid-level"
        if (Plasmoid.configuration.animationStyle === "bars") {
            cmd += " " + Plasmoid.configuration.barCount
        }
        executable.run(cmd)
    }

    // Lancer le daemon audio au chargement pour éviter la latence
    Component.onCompleted: preStartAudioDaemon()

    Component.onDestruction: {
        executable.run("dictee-plasmoid-level stop")
    }
}
