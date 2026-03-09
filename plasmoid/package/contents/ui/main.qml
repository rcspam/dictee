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

            if (source === stateCheckCmd) {
                parseState(stdout)
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

    // DataSource pour lire le niveau audio (comme animation-speech: simple et direct)
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
    }

    property int audioTick: 0

    // Timer de lecture niveau audio (~12 fps)
    Timer {
        id: audioTimer
        interval: 80
        running: root.effectiveState === "recording"
        repeat: true
        onTriggered: {
            root.audioTick++
            var cmd = "env _=" + root.audioTick + " dictee-plasmoid-level"
            if (Plasmoid.configuration.animationStyle === "bars") {
                cmd += " " + Plasmoid.configuration.barCount
            }
            audioExec.connectSource(cmd)
        }
        onRunningChanged: {
            if (!running) {
                root.audioLevel = 0.0
                root.audioBands = []
                executable.run("dictee-plasmoid-level stop")
            }
        }
    }

    // Commande de verification d'etat
    property string stateCheckCmd: "bash -c '" +
        "SOCK=/tmp/transcribe.sock; " +
        "PID=/tmp/recording_dictee_pid; " +
        "if [ ! -S \"$SOCK\" ] && ! pgrep -x transcribe-daemon >/dev/null 2>&1; then " +
        "  echo offline; " +
        "elif [ -f \"$PID\" ] && kill -0 $(cat \"$PID\") 2>/dev/null; then " +
        "  echo recording; " +
        "else " +
        "  echo idle; " +
        "fi'"

    function parseState(output) {
        var newState = output.trim()
        if (newState === "recording" || newState === "idle" || newState === "offline") {
            if (root.state === "recording" && newState === "idle") {
                root.state = "transcribing"
                transcribingTimer.start()
            } else {
                // Pré-démarrer le daemon audio dès la détection de recording
                if (newState === "recording" && root.state !== "recording") {
                    preStartAudioDaemon()
                }
                root.state = newState
            }
        }
    }

    // Timer de polling principal
    Timer {
        id: pollTimer
        interval: root.state === "recording" ? 500 : Plasmoid.configuration.pollingInterval
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            executable.run(stateCheckCmd)
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
            // Pré-démarrer le daemon audio pour réduire la latence
            preStartAudioDaemon()
            executable.run("dictee")
            break
        case "dictate-translate":
            preStartAudioDaemon()
            executable.run("dictee --translate")
            break
        case "cancel":
            executable.run("dictee --cancel")
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

    Component.onDestruction: {
        executable.run("dictee-plasmoid-level stop")
    }
}
