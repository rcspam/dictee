import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasma5support as Plasma5Support

KCM.SimpleKCM {
    id: configPage

    property alias cfg_pollingInterval: pollingIntervalSpin.value
    property alias cfg_showLastTranscription: showTranscriptionCheck.checked
    property alias cfg_previewMode: previewModeCheck.checked
    property double cfg_audioSensitivity: 2.0
    property alias cfg_animationStyle: animationStyleCombo.currentValue

    // Bars
    property alias cfg_barCount: barCountSpin.value
    property alias cfg_barSpacing: barSpacingSpin.value
    property alias cfg_barRadius: barRadiusSpin.value
    property double cfg_barMinHeight: 0.2
    property alias cfg_barIdleAnimation: barIdleAnimCheck.checked
    property alias cfg_animationSpeed: animationSpeedSpin.value

    // Wave
    property alias cfg_waveThickness: waveThicknessSpin.value
    property double cfg_waveFrequency: 2.0
    property double cfg_waveAmplitude: 0.8
    property alias cfg_waveSpeed: waveSpeedSpin.value

    // Pulse
    property alias cfg_pulseRings: pulseRingsSpin.value
    property alias cfg_pulseSpeed: pulseSpeedSpin.value

    // Dots
    property alias cfg_dotCount: dotCountSpin.value
    property alias cfg_dotSize: dotSizeSpin.value
    property alias cfg_dotSpeed: dotSpeedSpin.value

    // Lecture niveau micro pour la preview
    property real previewAudioLevel: 0.0
    property var previewAudioBands: []
    property int previewTick: 0

    Plasma5Support.DataSource {
        id: previewExec
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            var output = data["stdout"].trim()
            if (output.length === 0) { disconnectSource(source); return }
            var parts = output.split(" ")
            if (parts.length > 1) {
                var bands = []
                var sum = 0
                for (var i = 0; i < parts.length; i++) {
                    var v = parseFloat(parts[i])
                    if (!isNaN(v)) { bands.push(Math.min(1.0, v)); sum += v }
                }
                if (bands.length > 0) {
                    configPage.previewAudioBands = bands
                    configPage.previewAudioLevel = sum / bands.length
                }
            } else {
                var level = parseFloat(output)
                if (!isNaN(level)) configPage.previewAudioLevel = Math.min(1.0, level)
            }
            disconnectSource(source)
        }
    }

    Timer {
        id: previewAudioTimer
        interval: 80
        running: true
        repeat: true
        onTriggered: {
            configPage.previewTick++
            var cmd = "env _=" + configPage.previewTick + " dictee-plasmoid-level"
            if ((animationStyleCombo.currentValue || "bars") === "bars") {
                cmd += " " + cfg_barCount
            }
            previewExec.connectSource(cmd)
        }
    }

    Component.onDestruction: previewExec.connectSource("dictee-plasmoid-level stop")

    Kirigami.FormLayout {
        // === General ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("General")
            Kirigami.FormData.isSection: true
        }

        QQC2.SpinBox {
            id: pollingIntervalSpin
            Kirigami.FormData.label: i18n("Polling interval (ms):")
            from: 500
            to: 10000
            stepSize: 100
        }

        QQC2.CheckBox {
            id: showTranscriptionCheck
            Kirigami.FormData.label: i18n("Show last transcription:")
        }

        QQC2.CheckBox {
            id: previewModeCheck
            Kirigami.FormData.label: i18n("Preview mode (test with mic):")
        }

        // === Sensibilite ===
        RowLayout {
            Kirigami.FormData.label: i18n("Audio sensitivity:")
            spacing: Kirigami.Units.smallSpacing

            QQC2.Slider {
                id: sensitivitySlider
                from: 0.1
                to: 3.5
                stepSize: 0.1
                value: cfg_audioSensitivity
                onMoved: cfg_audioSensitivity = value
                Layout.fillWidth: true
            }

            QQC2.Label {
                text: sensitivitySlider.value.toFixed(1) + "x"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
            }
        }

        // === Animation ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("Animation")
            Kirigami.FormData.isSection: true
        }

        QQC2.ComboBox {
            id: animationStyleCombo
            Kirigami.FormData.label: i18n("Animation style:")
            model: [
                { text: i18n("Bars (default)"), value: "bars" },
                { text: i18n("Wave"), value: "wave" },
                { text: i18n("Pulse"), value: "pulse" },
                { text: i18n("Dots"), value: "dots" }
            ]
            textRole: "text"
            valueRole: "value"
            Component.onCompleted: {
                currentIndex = indexOfValue(cfg_animationStyle)
            }
        }

        // Apercu en direct
        Rectangle {
            Kirigami.FormData.label: i18n("Preview:")
            width: Kirigami.Units.gridUnit * 6
            height: Kirigami.Units.gridUnit * 3
            color: Kirigami.Theme.backgroundColor
            border.color: Kirigami.Theme.separatorColor
            border.width: 1
            radius: 4

            Loader {
                anchors.fill: parent
                anchors.margins: 4
                source: {
                    var style = animationStyleCombo.currentValue || "bars"
                    return "animations/" + style.charAt(0).toUpperCase() + style.slice(1) + "Animation.qml"
                }
                onLoaded: {
                    if (item) {
                        item.state = "recording"
                        item.barColor = Kirigami.Theme.highlightColor
                        item.audioLevel = Qt.binding(function() { return configPage.previewAudioLevel })
                        if (item.hasOwnProperty("audioBands")) {
                            item.audioBands = Qt.binding(function() { return configPage.previewAudioBands })
                        }
                    }
                }
            }
        }

        // === Bars settings ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("Bars settings")
            Kirigami.FormData.isSection: true
            visible: animationStyleCombo.currentValue === "bars"
        }

        QQC2.SpinBox {
            id: barCountSpin
            Kirigami.FormData.label: i18n("Number of bars:")
            from: 2
            to: 20
            visible: animationStyleCombo.currentValue === "bars"
        }

        QQC2.SpinBox {
            id: barSpacingSpin
            Kirigami.FormData.label: i18n("Bar spacing (px):")
            from: 0
            to: 10
            visible: animationStyleCombo.currentValue === "bars"
        }

        QQC2.SpinBox {
            id: barRadiusSpin
            Kirigami.FormData.label: i18n("Bar corner radius:")
            from: 0
            to: 10
            visible: animationStyleCombo.currentValue === "bars"
        }

        QQC2.SpinBox {
            id: barMinHeightSpin
            Kirigami.FormData.label: i18n("Min height (%):")
            from: 5
            to: 80
            stepSize: 5
            value: cfg_barMinHeight * 100
            property real realValue: value / 100.0
            visible: animationStyleCombo.currentValue === "bars"
            onValueModified: cfg_barMinHeight = value / 100.0
        }

        QQC2.CheckBox {
            id: barIdleAnimCheck
            Kirigami.FormData.label: i18n("Idle breathing animation:")
            visible: animationStyleCombo.currentValue === "bars"
        }

        QQC2.SpinBox {
            id: animationSpeedSpin
            Kirigami.FormData.label: i18n("Animation speed (ms):")
            from: 100
            to: 2000
            stepSize: 50
            visible: animationStyleCombo.currentValue === "bars"
        }

        // === Wave settings ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("Wave settings")
            Kirigami.FormData.isSection: true
            visible: animationStyleCombo.currentValue === "wave"
        }

        QQC2.SpinBox {
            id: waveThicknessSpin
            Kirigami.FormData.label: i18n("Line thickness:")
            from: 1
            to: 10
            visible: animationStyleCombo.currentValue === "wave"
        }

        QQC2.SpinBox {
            id: waveFrequencySpin
            Kirigami.FormData.label: i18n("Wave frequency:")
            from: 5
            to: 80
            stepSize: 5
            value: cfg_waveFrequency * 10
            visible: animationStyleCombo.currentValue === "wave"
            onValueModified: cfg_waveFrequency = value / 10.0
        }

        QQC2.SpinBox {
            id: waveAmplitudeSpin
            Kirigami.FormData.label: i18n("Amplitude (%):")
            from: 10
            to: 100
            stepSize: 5
            value: cfg_waveAmplitude * 100
            visible: animationStyleCombo.currentValue === "wave"
            onValueModified: cfg_waveAmplitude = value / 100.0
        }

        QQC2.SpinBox {
            id: waveSpeedSpin
            Kirigami.FormData.label: i18n("Wave speed (ms):")
            from: 100
            to: 2000
            stepSize: 50
            visible: animationStyleCombo.currentValue === "wave"
        }

        // === Pulse settings ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("Pulse settings")
            Kirigami.FormData.isSection: true
            visible: animationStyleCombo.currentValue === "pulse"
        }

        QQC2.SpinBox {
            id: pulseRingsSpin
            Kirigami.FormData.label: i18n("Number of rings:")
            from: 1
            to: 5
            visible: animationStyleCombo.currentValue === "pulse"
        }

        QQC2.SpinBox {
            id: pulseSpeedSpin
            Kirigami.FormData.label: i18n("Pulse speed (ms):")
            from: 200
            to: 3000
            stepSize: 100
            visible: animationStyleCombo.currentValue === "pulse"
        }

        // === Dots settings ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("Dots settings")
            Kirigami.FormData.isSection: true
            visible: animationStyleCombo.currentValue === "dots"
        }

        QQC2.SpinBox {
            id: dotCountSpin
            Kirigami.FormData.label: i18n("Number of dots:")
            from: 3
            to: 12
            visible: animationStyleCombo.currentValue === "dots"
        }

        QQC2.SpinBox {
            id: dotSizeSpin
            Kirigami.FormData.label: i18n("Dot size (px):")
            from: 2
            to: 12
            visible: animationStyleCombo.currentValue === "dots"
        }

        QQC2.SpinBox {
            id: dotSpeedSpin
            Kirigami.FormData.label: i18n("Bounce speed (ms):")
            from: 100
            to: 2000
            stepSize: 50
            visible: animationStyleCombo.currentValue === "dots"
        }
    }
}
