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
                // Polling rapide : état écrit par dictee
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

    // DataSource pour lire le niveau audio — cat direct sur /dev/shm
    Plasma5Support.DataSource {
        id: audioExec
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            var output = data["stdout"].trim()
            if (output.length > 0) {
                var parts = output.split(" ")
                if (parts.length > 1) {
                    var bands = []
                    var sum = 0
                    for (var i = 0; i < parts.length; i++) {
                        var v = parseFloat(parts[i])
                        if (!isNaN(v)) {
                            bands.push(Math.min(1.0, v))
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
                        root.audioLevel = Math.min(1.0, level)
                    }
                }
            }
            disconnectSource(source)
        }
        function read(tick) {
            // Commentaire unique pour éviter le cache DataSource
            connectSource("cat /dev/shm/.dictee_audio_bands #" + tick)
        }
    }

    property int audioTick: 0

    // Timer de lecture niveau audio (~20 fps)
    Timer {
        id: audioTimer
        interval: 50
        running: root.effectiveState === "recording"
        repeat: true
        onTriggered: {
            root.audioTick++
            // Lecture directe du fichier /dev/shm — pas de script bash intermédiaire
            audioExec.read(root.audioTick)
        }
        onRunningChanged: {
            if (!running) {
                root.audioLevel = 0.0
                root.audioBands = []
            }
        }
    }

    // Commande rapide : lire l'état depuis /dev/shm (écrit par dictee)
    property string fastStateCmd: "cat /dev/shm/.dictee_state 2>/dev/null"

    // Commande lente : vérifier si le daemon tourne (pour offline/idle)
    property string daemonCheckCmd: "bash -c '" +
        "if [ ! -S /tmp/transcribe.sock ] && ! pgrep -x transcribe-daemon >/dev/null 2>&1; then " +
        "  echo offline; " +
        "else " +
        "  echo idle; " +
        "fi'"

    property int stateTick: 0

    function parseState(output) {
        var newState = output.trim()
        if (newState === "recording" || newState === "idle" || newState === "offline" || newState === "transcribing") {
            if (newState === "transcribing" && root.state !== "transcribing") {
                root.state = "transcribing"
                transcribingTimer.start()
            } else if (root.state === "recording" && newState === "idle") {
                root.state = "transcribing"
                transcribingTimer.start()
            } else {
                root.state = newState
            }
        }
    }

    // Timer rapide : lit /dev/shm/.dictee_state toutes les 200ms
    Timer {
        id: fastPollTimer
        interval: 200
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            root.stateTick++
            executable.run("cat /dev/shm/.dictee_state 2>/dev/null #" + root.stateTick)
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
    }

    fullRepresentation: FullRepresentation {
        state: root.effectiveState
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
            break
        case "stop-daemon":
            executable.run("systemctl --user stop dictee")
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
