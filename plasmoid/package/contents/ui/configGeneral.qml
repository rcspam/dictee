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
    property alias cfg_audioContext: audioContextCheck.checked
    property double cfg_audioSensitivity: 2.0
    property double cfg_barSensitivity: 2.0
    property double cfg_waveSensitivity: 2.0
    property double cfg_pulseSensitivity: 2.0
    property double cfg_dotSensitivity: 2.0
    property alias cfg_animationStyle: animationStyleCombo.currentValue

    // Bars
    property alias cfg_barCount: barCountSpin.value
    property alias cfg_barSpacing: barSpacingSpin.value
    property alias cfg_barRadius: barRadiusSpin.value
    property double cfg_barMinHeight: 0.2
    property alias cfg_barIdleAnimation: barIdleAnimCheck.checked
    property alias cfg_animationSpeed: animationSpeedSpin.value

    // Wave
    property alias cfg_waveWidth: waveWidthSpin.value
    property alias cfg_waveThickness: waveThicknessSpin.value
    property double cfg_waveFrequency: 2.0
    property double cfg_waveAmplitude: 0.8
    property alias cfg_waveSpeed: waveSpeedSpin.value
    property alias cfg_waveFill: waveFillCheck.checked

    // Pulse
    property alias cfg_pulseRings: pulseRingsSpin.value
    property alias cfg_pulseSpeed: pulseSpeedSpin.value
    property alias cfg_pulseThickness: pulseThicknessSpin.value

    // Dots
    property alias cfg_dotCount: dotCountSpin.value
    property alias cfg_dotSize: dotSizeSpin.value
    property alias cfg_dotBounce: dotBounceSpin.value
    property alias cfg_dotSpacing: dotSpacingSpin.value
    property alias cfg_dotSpeed: dotSpeedSpin.value

    // Rainbow
    property alias cfg_useRainbow: rainbowCheck.checked
    property alias cfg_rainbowStartHue: rainbowStartSpin.value
    property alias cfg_rainbowEndHue: rainbowEndSpin.value

    // Waveform
    property double cfg_waveformSensitivity: 2.0
    property alias cfg_waveformBars: waveformBarsSpin.value
    property alias cfg_waveformSpacing: waveformSpacingSpin.value
    property alias cfg_waveformRadius: waveformRadiusSpin.value
    property double cfg_waveformMinHeight: 0.1
    property double cfg_noiseGate: 0.05
    property double cfg_envelopePower: 1.0
    property double cfg_envelopeCenter: 0.5

    // Sensibilité active selon le style courant
    readonly property real activeSensitivity: {
        var style = animationStyleCombo.currentValue || "bars"
        switch (style) {
        case "bars":  return cfg_barSensitivity
        case "wave":  return cfg_waveSensitivity
        case "pulse": return cfg_pulseSensitivity
        case "dots":     return cfg_dotSensitivity
        case "waveform": return cfg_waveformSensitivity
        default:         return cfg_audioSensitivity
        }
    }

    // Lecture niveau micro pour la preview
    property real previewAudioLevel: 0.0
    property var previewAudioBands: []
    property int previewTick: 0

    property string calibrationStatus: ""
    property real micVolume: 0.5
    property bool micVolumeReady: false

    // Lire le volume micro au chargement
    Plasma5Support.DataSource {
        id: micVolumeExec
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            var stdout = data["stdout"].trim()
            // wpctl get-volume → "Volume: 0.30" ou "Volume: 0.30 [MUTED]"
            var match = stdout.match(/Volume:\s+([\d.]+)/)
            if (match) {
                configPage.micVolume = parseFloat(match[1])
                configPage.micVolumeReady = true
            }
            disconnectSource(source)
        }
    }
    Component.onCompleted: micVolumeExec.connectSource("wpctl get-volume @DEFAULT_SOURCE@")

    // Appliquer le changement de volume
    Plasma5Support.DataSource {
        id: micVolumeSetExec
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) { disconnectSource(source) }
    }

    Plasma5Support.DataSource {
        id: calibrateExec
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            var stdout = data["stdout"].trim()
            if (stdout.indexOf("Calibration OK") !== -1) {
                configPage.calibrationStatus = i18n("Calibration done!")
            } else {
                configPage.calibrationStatus = i18n("Calibration failed")
            }
            calibrationResetTimer.start()
            disconnectSource(source)
        }
    }

    Timer {
        id: calibrationResetTimer
        interval: 3000
        onTriggered: configPage.calibrationStatus = ""
    }

    Plasma5Support.DataSource {
        id: previewExec
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            var output = data["stdout"].trim()
            if (output.length === 0) { disconnectSource(source); return }
            var gate = configPage.cfg_noiseGate || 0.0
            var parts = output.split(" ")
            if (parts.length > 1) {
                var bands = []
                var sum = 0
                for (var i = 0; i < parts.length; i++) {
                    var v = parseFloat(parts[i])
                    if (!isNaN(v)) {
                        v = Math.min(1.0, v)
                        if (v < gate) v = 0.0
                        bands.push(v); sum += v
                    }
                }
                if (bands.length > 0) {
                    configPage.previewAudioBands = bands
                    configPage.previewAudioLevel = sum / bands.length
                }
            } else {
                var level = parseFloat(output)
                if (!isNaN(level)) {
                    level = Math.min(1.0, level)
                    if (level < gate) level = 0.0
                    configPage.previewAudioLevel = level
                }
            }
            disconnectSource(source)
        }
    }

    Component.onDestruction: previewExec.connectSource("dictee-plasmoid-level stop")

    Timer {
        id: previewAudioTimer
        interval: 80
        running: true
        repeat: true
        onTriggered: {
            configPage.previewTick++
            var cmd = "env _=" + configPage.previewTick + " dictee-plasmoid-level"
            var style = animationStyleCombo.currentValue || "bars"
            if (style === "bars") {
                cmd += " " + cfg_barCount
            } else if (style === "waveform") {
                cmd += " " + cfg_waveformBars
            }
            previewExec.connectSource(cmd)
        }
    }

    Kirigami.FormLayout {
        // === General ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("General")
            Kirigami.FormData.isSection: true
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Polling interval (ms):")
            spacing: Kirigami.Units.smallSpacing
            QQC2.SpinBox {
                id: pollingIntervalSpin
                from: 500
                to: 10000
                stepSize: 100
            }
            Kirigami.ContextualHelpButton {
                toolTipText: i18n("How often the widget checks if the daemon is running (in milliseconds).")
            }
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Show last transcription:")
            spacing: Kirigami.Units.smallSpacing
            QQC2.CheckBox {
                id: showTranscriptionCheck
            }
            Kirigami.ContextualHelpButton {
                toolTipText: i18n("Display the last transcribed text in the popup window.")
            }
        }

        QQC2.CheckBox {
            id: previewModeCheck
            Kirigami.FormData.label: i18n("Preview mode (test with mic):")
        }

        QQC2.CheckBox {
            id: audioContextCheck
            Kirigami.FormData.label: i18n("Audio context buffer:")
        }

        // === Volume micro ===
        RowLayout {
            Kirigami.FormData.label: i18n("Microphone volume:")
            spacing: Kirigami.Units.smallSpacing
            visible: configPage.micVolumeReady

            Kirigami.Icon {
                source: "audio-input-microphone"
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: Kirigami.Units.iconSizes.small
            }
            QQC2.Slider {
                id: micVolumeSlider
                from: 0.0; to: 1.5; stepSize: 0.01
                value: configPage.micVolume
                onMoved: {
                    configPage.micVolume = value
                    micVolumeSetExec.connectSource("wpctl set-volume @DEFAULT_SOURCE@ " + value.toFixed(2))
                }
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: (configPage.micVolume * 100).toFixed(0) + "%"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2.5
            }
            Kirigami.ContextualHelpButton {
                toolTipText: i18n("Adjust the microphone input volume (PipeWire/PulseAudio default source).")
            }
        }

        // === Calibration bruit de fond ===
        RowLayout {
            Kirigami.FormData.label: i18n("Noise floor:")
            spacing: Kirigami.Units.smallSpacing
            QQC2.Button {
                text: i18n("Calibrate")
                icon.name: "audio-input-microphone"
                onClicked: {
                    configPage.calibrationStatus = i18n("Recording silence…")
                    var n = (animationStyleCombo.currentValue || "bars") === "bars" ? cfg_barCount : 6
                    calibrateExec.connectSource("dictee-plasmoid-level-fft --calibrate " + n + " 5")
                }
            }
            Kirigami.ContextualHelpButton {
                toolTipText: i18n("Record 5 seconds of silence to calibrate the background noise level. This improves animation accuracy.")
            }
        }

        QQC2.Label {
            visible: configPage.calibrationStatus.length > 0
            text: configPage.calibrationStatus
            opacity: 0.7
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Noise gate:")
            spacing: Kirigami.Units.smallSpacing

            QQC2.Slider {
                from: 0.0; to: 0.8; stepSize: 0.01
                value: cfg_noiseGate
                onMoved: cfg_noiseGate = value
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: (cfg_noiseGate * 100).toFixed(0) + "%"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
            }
            Kirigami.ContextualHelpButton {
                toolTipText: i18n("Audio levels below this threshold are zeroed. Increase to suppress background noise and get clean silence.")
            }
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Envelope shape:")
            spacing: Kirigami.Units.smallSpacing

            QQC2.Slider {
                from: 0.0; to: 3.0; stepSize: 0.1
                value: cfg_envelopePower
                onMoved: cfg_envelopePower = value
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: {
                    if (cfg_envelopePower < 0.05) return i18n("Flat")
                    if (cfg_envelopePower < 0.5) return cfg_envelopePower.toFixed(1)
                    if (Math.abs(cfg_envelopePower - 1.0) < 0.05) return i18n("Normal")
                    return cfg_envelopePower.toFixed(1)
                }
                Layout.minimumWidth: Kirigami.Units.gridUnit * 3
            }
            Kirigami.ContextualHelpButton {
                toolTipText: i18n("Controls the Hanning envelope shape. 0 = flat (uniform bars), 1 = normal, higher = more peaked at the center.")
            }
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Envelope center:")
            spacing: Kirigami.Units.smallSpacing
            enabled: cfg_envelopePower >= 0.05

            QQC2.Slider {
                from: 0.0; to: 1.0; stepSize: 0.05
                value: cfg_envelopeCenter
                onMoved: cfg_envelopeCenter = value
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: Math.round(80 * Math.pow(50, cfg_envelopeCenter)) + " Hz"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 3.5
                horizontalAlignment: Text.AlignRight
            }
            Kirigami.ContextualHelpButton {
                toolTipText: i18n("Shift the envelope peak across the frequency range (80–4000 Hz). Useful with rainbow colors to emphasize different frequency bands.")
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
                { text: i18n("Dots"), value: "dots" },
                { text: i18n("Waveform"), value: "waveform" }
            ]
            textRole: "text"
            valueRole: "value"
            Component.onCompleted: {
                currentIndex = indexOfValue(cfg_animationStyle)
            }
        }

        QQC2.CheckBox {
            id: rainbowCheck
            Kirigami.FormData.label: i18n("Rainbow colors:")
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Start hue:")
            spacing: Kirigami.Units.smallSpacing
            visible: cfg_useRainbow

            QQC2.Slider {
                id: rainbowStartSpin
                from: 0; to: 360; stepSize: 5
                Layout.fillWidth: true
            }
            Rectangle {
                width: Kirigami.Units.gridUnit; height: width; radius: 3
                color: Qt.hsla(cfg_rainbowStartHue / 360.0, 0.8, 0.55, 1.0)
            }
        }

        RowLayout {
            Kirigami.FormData.label: i18n("End hue:")
            spacing: Kirigami.Units.smallSpacing
            visible: cfg_useRainbow

            QQC2.Slider {
                id: rainbowEndSpin
                from: 0; to: 360; stepSize: 5
                Layout.fillWidth: true
            }
            Rectangle {
                width: Kirigami.Units.gridUnit; height: width; radius: 3
                color: Qt.hsla(cfg_rainbowEndHue / 360.0, 0.8, 0.55, 1.0)
            }
        }

        // Apercu en direct (inline, sans charger les fichiers animation)
        Rectangle {
            Kirigami.FormData.label: i18n("Preview:")
            implicitWidth: Kirigami.Units.gridUnit * 8
            implicitHeight: Kirigami.Units.gridUnit * 3
            Layout.preferredWidth: Kirigami.Units.gridUnit * 8
            Layout.preferredHeight: Kirigami.Units.gridUnit * 3
            Layout.minimumHeight: Kirigami.Units.gridUnit * 3
            color: "transparent"
            clip: true

            property string currentStyle: animationStyleCombo.currentValue || "bars"
            property real sens: configPage.activeSensitivity
            property real audioLvl: configPage.previewAudioLevel
            property var audioBnds: configPage.previewAudioBands
            property color animColor: Kirigami.Theme.highlightColor

            // === Bars preview ===
            Row {
                id: barsPreview
                visible: parent.currentStyle === "bars"
                anchors.fill: parent
                anchors.margins: 4
                spacing: cfg_barSpacing

                Repeater {
                    model: cfg_barCount
                    Rectangle {
                        readonly property int bi: index
                        readonly property real envelope: {
                            var n = cfg_barCount
                            if (n <= 1) return 1.0
                            var t = bi / (n - 1)
                            var c = cfg_envelopeCenter
                            var r = (c > 0.01 && t <= c) ? 0.5 * t / c
                                  : (c < 0.99 && t > c)  ? 0.5 + 0.5 * (t - c) / (1.0 - c)
                                  : (c <= 0.01)           ? 0.5 + 0.5 * t
                                  :                         0.5 * t
                            var h = 0.5 - 0.5 * Math.cos(2 * Math.PI * r)
                            return cfg_envelopePower > 0.01 ? Math.pow(h, cfg_envelopePower) : 1.0
                        }
                        readonly property real lvl: {
                            var s = barsPreview.parent.sens
                            var bands = barsPreview.parent.audioBnds
                            var raw
                            if (bands.length > 0) {
                                var bidx = Math.min(Math.floor(bi * bands.length / cfg_barCount), bands.length - 1)
                                raw = Math.min(1.0, bands[bidx])
                            } else {
                                raw = Math.min(1.0, barsPreview.parent.audioLvl)
                            }
                            var level = raw > 0 ? Math.pow(raw, 1.0 / s) : 0
                            return level * envelope
                        }
                        width: Math.max(1, (barsPreview.width - (cfg_barCount - 1) * cfg_barSpacing) / cfg_barCount)
                        height: {
                            var minR = cfg_barMinHeight
                            return barsPreview.height * (minR + (1.0 - minR) * lvl)
                        }
                        anchors.bottom: parent.bottom
                        radius: cfg_barRadius
                        color: {
                            if (!cfg_useRainbow) return barsPreview.parent.animColor
                            var n = cfg_barCount
                            var t = n > 1 ? bi / (n - 1) : 0.5
                            var startH = cfg_rainbowStartHue / 360.0
                            var endH = cfg_rainbowEndHue / 360.0
                            return Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                        }
                        Behavior on height { NumberAnimation { duration: 50; easing.type: Easing.OutQuad } }
                    }
                }
            }

            // === Wave preview ===
            Item {
                id: wavePreview
                visible: parent.currentStyle === "wave"
                anchors.fill: parent
                anchors.margins: 4
                property real phase: 0.0
                NumberAnimation on phase {
                    running: wavePreview.visible
                    from: 0; to: 6.2832
                    duration: cfg_waveSpeed * 4
                    loops: Animation.Infinite
                }
                onPhaseChanged: waveCanvas.requestPaint()
                Canvas {
                    id: waveCanvas
                    anchors.fill: parent
                    onWidthChanged: if (width > 0 && height > 0) requestPaint()
                    onHeightChanged: if (width > 0 && height > 0) requestPaint()

                    Connections {
                        target: configPage
                        function onPreviewAudioLevelChanged() { waveCanvas.requestPaint() }
                        function onPreviewAudioBandsChanged() { waveCanvas.requestPaint() }
                    }

                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        if (width <= 0 || height <= 0) return
                        var previewRect = wavePreview.parent
                        var s = previewRect.sens
                        var maxAmp = height * 0.45 * cfg_waveAmplitude
                        var freq = cfg_waveFrequency
                        var centerY = height / 2
                        var bands = previewRect.audioBnds
                        var hasBands = bands.length > 0
                        var points = []
                        for (var x = 0; x <= width; x += 2) {
                            var ratio = x / width
                            var cEnv = cfg_envelopeCenter
                            var rEnv = (cEnv > 0.01 && ratio <= cEnv) ? 0.5 * ratio / cEnv
                                     : (cEnv < 0.99 && ratio > cEnv)  ? 0.5 + 0.5 * (ratio - cEnv) / (1.0 - cEnv)
                                     : (cEnv <= 0.01)                  ? 0.5 + 0.5 * ratio
                                     :                                   0.5 * ratio
                            var hEnv = 0.5 - 0.5 * Math.cos(2 * Math.PI * rEnv)
                            var envelope = cfg_envelopePower > 0.01 ? Math.pow(hEnv, cfg_envelopePower) : 1.0
                            var rawLvl
                            if (hasBands) {
                                var bidx = Math.min(Math.floor(ratio * bands.length), bands.length - 1)
                                rawLvl = Math.min(1.0, bands[bidx])
                            } else {
                                rawLvl = Math.min(1.0, previewRect.audioLvl)
                            }
                            var localLvl = rawLvl > 0 ? Math.pow(rawLvl, 1.0 / s) : 0
                            var amp = maxAmp * Math.max(0.15, localLvl) * envelope
                            var y = amp * Math.sin(ratio * freq * 6.2832 + wavePreview.phase)
                            points.push({ x: x, y: y })
                        }
                        if (cfg_waveFill) {
                            ctx.fillStyle = Qt.rgba(previewRect.animColor.r, previewRect.animColor.g, previewRect.animColor.b, 0.15)
                            ctx.beginPath()
                            ctx.moveTo(0, centerY)
                            for (var i = 0; i < points.length; i++)
                                ctx.lineTo(points[i].x, centerY + points[i].y)
                            ctx.lineTo(width, centerY)
                            ctx.closePath()
                            ctx.fill()
                        }
                        ctx.lineWidth = cfg_waveThickness
                        ctx.lineCap = "round"
                        ctx.lineJoin = "round"
                        if (cfg_useRainbow && points.length > 1) {
                            var startH = cfg_rainbowStartHue / 360.0
                            var endH = cfg_rainbowEndHue / 360.0
                            for (var si = 0; si < points.length - 1; si++) {
                                var t = si / (points.length - 1)
                                ctx.strokeStyle = Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                                ctx.beginPath()
                                ctx.moveTo(points[si].x, centerY + points[si].y)
                                ctx.lineTo(points[si+1].x, centerY + points[si+1].y)
                                ctx.stroke()
                            }
                        } else {
                            ctx.strokeStyle = previewRect.animColor
                            ctx.beginPath()
                            for (var j = 0; j < points.length; j++) {
                                if (j === 0) ctx.moveTo(points[j].x, centerY + points[j].y)
                                else ctx.lineTo(points[j].x, centerY + points[j].y)
                            }
                            ctx.stroke()
                        }
                    }
                }
            }

            // === Pulse preview ===
            Item {
                id: pulsePreview
                visible: parent.currentStyle === "pulse"
                anchors.fill: parent
                anchors.margins: 4

                readonly property real ampLevel: {
                    var s = pulsePreview.parent.sens
                    var bands = pulsePreview.parent.audioBnds
                    var raw
                    if (bands.length > 0) {
                        var mx = 0
                        for (var i = 0; i < bands.length; i++)
                            if (bands[i] > mx) mx = bands[i]
                        raw = Math.min(1.0, mx)
                    } else {
                        raw = Math.min(1.0, pulsePreview.parent.audioLvl)
                    }
                    return raw > 0 ? Math.pow(raw, 1.0 / s) : 0
                }

                Repeater {
                    model: cfg_pulseRings
                    Rectangle {
                        readonly property int ri: index
                        anchors.centerIn: parent
                        width: Math.min(pulsePreview.width, pulsePreview.height) * (0.9 - ri * 0.15)
                        height: width; radius: width / 2
                        color: "transparent"
                        border.color: {
                            if (!cfg_useRainbow) return pulsePreview.parent.animColor
                            var n = cfg_pulseRings
                            var t = n > 1 ? ri / (n - 1) : 0.5
                            var startH = cfg_rainbowStartHue / 360.0
                            var endH = cfg_rainbowEndHue / 360.0
                            return Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                        }
                        border.width: cfg_pulseThickness
                        scale: 0.5 + 0.5 * pulsePreview.ampLevel
                        opacity: 0.4 + 0.6 * pulsePreview.ampLevel
                        Behavior on scale { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
                        Behavior on opacity { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
                    }
                }
                Rectangle {
                    anchors.centerIn: parent
                    width: Math.min(pulsePreview.width, pulsePreview.height) * 0.25
                    height: width; radius: width / 2
                    color: {
                        if (!cfg_useRainbow) return pulsePreview.parent.animColor
                        var startH = cfg_rainbowStartHue / 360.0
                        var endH = cfg_rainbowEndHue / 360.0
                        return Qt.hsla((startH + endH) / 2, 0.8, 0.55, 1.0)
                    }
                    scale: 0.5 + 0.5 * pulsePreview.ampLevel
                    opacity: 0.6 + 0.4 * pulsePreview.ampLevel
                    Behavior on scale { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
                    Behavior on opacity { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
                }
            }

            // === Dots preview ===
            Item {
                id: dotsPreview
                visible: parent.currentStyle === "dots"
                anchors.fill: parent
                anchors.margins: 4
                clip: true

                Row {
                    anchors.centerIn: parent
                    spacing: cfg_dotSpacing

                    Repeater {
                        model: cfg_dotCount
                        Rectangle {
                            readonly property int di: index
                            readonly property real dl: {
                                var s = dotsPreview.parent.sens
                                var bands = dotsPreview.parent.audioBnds
                                var raw
                                if (bands.length > 0) {
                                    var bidx = Math.min(Math.floor(di * bands.length / cfg_dotCount), bands.length - 1)
                                    raw = Math.min(1.0, bands[bidx])
                                } else {
                                    raw = Math.min(1.0, dotsPreview.parent.audioLvl)
                                }
                                return raw > 0 ? Math.pow(raw, 1.0 / s) : 0
                            }
                            width: cfg_dotSize * (0.6 + 0.8 * dl)
                            height: width; radius: width / 2
                            color: {
                                if (!cfg_useRainbow) return dotsPreview.parent.animColor
                                var n = cfg_dotCount
                                var t = n > 1 ? di / (n - 1) : 0.5
                                var startH = cfg_rainbowStartHue / 360.0
                                var endH = cfg_rainbowEndHue / 360.0
                                return Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                            }
                            opacity: 0.4 + 0.6 * dl
                            y: {
                                var dotSz = cfg_dotSize
                                var centerY = dotsPreview.height / 2 - dotSz / 2
                                if (dl <= 0.01) return centerY
                                var bounce = cfg_dotBounce / 100.0
                                var phase = Math.sin(di * 1.8 + dl * 8)
                                var disp = dotsPreview.height * bounce * dl * phase
                                var raw = centerY - disp
                                return Math.max(0, Math.min(raw, dotsPreview.height - dotSz))
                            }
                            Behavior on y { NumberAnimation { duration: 60; easing.type: Easing.OutQuad } }
                            Behavior on width { NumberAnimation { duration: 60; easing.type: Easing.OutQuad } }
                            Behavior on opacity { NumberAnimation { duration: 60; easing.type: Easing.OutQuad } }
                        }
                    }
                }
            }

            // === Waveform preview ===
            Row {
                id: waveformPreview
                visible: parent.currentStyle === "waveform"
                anchors.fill: parent
                anchors.margins: 4
                spacing: cfg_waveformSpacing

                Repeater {
                    model: cfg_waveformBars
                    Rectangle {
                        readonly property int wi: index
                        readonly property real envelope: {
                            var n = cfg_waveformBars
                            if (n <= 1) return 1.0
                            var t = wi / (n - 1)
                            var c = cfg_envelopeCenter
                            var r = (c > 0.01 && t <= c) ? 0.5 * t / c
                                  : (c < 0.99 && t > c)  ? 0.5 + 0.5 * (t - c) / (1.0 - c)
                                  : (c <= 0.01)           ? 0.5 + 0.5 * t
                                  :                         0.5 * t
                            var h = 0.5 - 0.5 * Math.cos(2 * Math.PI * r)
                            return cfg_envelopePower > 0.01 ? Math.pow(h, cfg_envelopePower) : 1.0
                        }
                        readonly property real wl: {
                            var s = waveformPreview.parent.sens
                            var bands = waveformPreview.parent.audioBnds
                            var raw
                            if (bands.length > 0) {
                                var bidx = Math.min(Math.floor(wi * bands.length / cfg_waveformBars), bands.length - 1)
                                raw = Math.min(1.0, bands[bidx])
                            } else {
                                raw = Math.min(1.0, waveformPreview.parent.audioLvl)
                            }
                            var level = raw > 0 ? Math.pow(raw, 1.0 / s) : 0
                            return level * envelope
                        }
                        readonly property real minR: cfg_waveformMinHeight

                        width: Math.max(1, (waveformPreview.width - (cfg_waveformBars - 1) * cfg_waveformSpacing) / cfg_waveformBars)
                        height: {
                            var h = waveformPreview.height * (minR + (1.0 - minR) * wl)
                            return Math.max(2, h)
                        }
                        radius: cfg_waveformRadius
                        color: {
                            if (!cfg_useRainbow) return waveformPreview.parent.animColor
                            var n = cfg_waveformBars
                            var t = n > 1 ? wi / (n - 1) : 0.5
                            var startH = cfg_rainbowStartHue / 360.0
                            var endH = cfg_rainbowEndHue / 360.0
                            return Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                        }
                        y: (waveformPreview.height - height) / 2
                        opacity: 0.4 + 0.6 * wl

                        Behavior on height { NumberAnimation { duration: 50; easing.type: Easing.OutQuad } }
                        Behavior on opacity { NumberAnimation { duration: 50; easing.type: Easing.OutQuad } }
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

        RowLayout {
            Kirigami.FormData.label: i18n("Sensitivity:")
            spacing: Kirigami.Units.smallSpacing
            visible: animationStyleCombo.currentValue === "bars"

            QQC2.Slider {
                from: 0.5; to: 5.0; stepSize: 0.1
                value: cfg_barSensitivity
                onMoved: cfg_barSensitivity = value
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: cfg_barSensitivity.toFixed(1) + "x"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
            }
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

        RowLayout {
            Kirigami.FormData.label: i18n("Sensitivity:")
            spacing: Kirigami.Units.smallSpacing
            visible: animationStyleCombo.currentValue === "wave"

            QQC2.Slider {
                from: 0.5; to: 5.0; stepSize: 0.1
                value: cfg_waveSensitivity
                onMoved: cfg_waveSensitivity = value
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: cfg_waveSensitivity.toFixed(1) + "x"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
            }
        }

        QQC2.SpinBox {
            id: waveWidthSpin
            Kirigami.FormData.label: i18n("Width (px):")
            from: 15
            to: 80
            visible: animationStyleCombo.currentValue === "wave"
        }

        QQC2.SpinBox {
            id: waveThicknessSpin
            Kirigami.FormData.label: i18n("Line thickness (px):")
            from: 1
            to: 15
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

        QQC2.CheckBox {
            id: waveFillCheck
            Kirigami.FormData.label: i18n("Fill under wave:")
            visible: animationStyleCombo.currentValue === "wave"
        }

        // === Pulse settings ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("Pulse settings")
            Kirigami.FormData.isSection: true
            visible: animationStyleCombo.currentValue === "pulse"
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Sensitivity:")
            spacing: Kirigami.Units.smallSpacing
            visible: animationStyleCombo.currentValue === "pulse"

            QQC2.Slider {
                from: 0.5; to: 5.0; stepSize: 0.1
                value: cfg_pulseSensitivity
                onMoved: cfg_pulseSensitivity = value
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: cfg_pulseSensitivity.toFixed(1) + "x"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
            }
        }

        QQC2.SpinBox {
            id: pulseRingsSpin
            Kirigami.FormData.label: i18n("Number of rings:")
            from: 1
            to: 5
            visible: animationStyleCombo.currentValue === "pulse"
        }

        QQC2.SpinBox {
            id: pulseThicknessSpin
            Kirigami.FormData.label: i18n("Ring thickness (px):")
            from: 1
            to: 8
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

        RowLayout {
            Kirigami.FormData.label: i18n("Sensitivity:")
            spacing: Kirigami.Units.smallSpacing
            visible: animationStyleCombo.currentValue === "dots"

            QQC2.Slider {
                from: 0.5; to: 5.0; stepSize: 0.1
                value: cfg_dotSensitivity
                onMoved: cfg_dotSensitivity = value
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: cfg_dotSensitivity.toFixed(1) + "x"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
            }
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
            to: 20
            visible: animationStyleCombo.currentValue === "dots"
        }

        QQC2.SpinBox {
            id: dotSpacingSpin
            Kirigami.FormData.label: i18n("Dot spacing (px):")
            from: 0
            to: 15
            visible: animationStyleCombo.currentValue === "dots"
        }

        QQC2.SpinBox {
            id: dotBounceSpin
            Kirigami.FormData.label: i18n("Bounce amplitude (%):")
            from: 10
            to: 100
            stepSize: 5
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

        // === Waveform settings ===
        Kirigami.Separator {
            Kirigami.FormData.label: i18n("Waveform settings")
            Kirigami.FormData.isSection: true
            visible: animationStyleCombo.currentValue === "waveform"
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Sensitivity:")
            spacing: Kirigami.Units.smallSpacing
            visible: animationStyleCombo.currentValue === "waveform"

            QQC2.Slider {
                from: 0.5; to: 5.0; stepSize: 0.1
                value: cfg_waveformSensitivity
                onMoved: cfg_waveformSensitivity = value
                Layout.fillWidth: true
            }
            QQC2.Label {
                text: cfg_waveformSensitivity.toFixed(1) + "x"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
            }
        }

        QQC2.SpinBox {
            id: waveformBarsSpin
            Kirigami.FormData.label: i18n("Number of bars:")
            from: 4
            to: 32
            visible: animationStyleCombo.currentValue === "waveform"
        }

        QQC2.SpinBox {
            id: waveformSpacingSpin
            Kirigami.FormData.label: i18n("Bar spacing (px):")
            from: 0
            to: 10
            visible: animationStyleCombo.currentValue === "waveform"
        }

        QQC2.SpinBox {
            id: waveformRadiusSpin
            Kirigami.FormData.label: i18n("Bar corner radius:")
            from: 0
            to: 10
            visible: animationStyleCombo.currentValue === "waveform"
        }

        QQC2.SpinBox {
            id: waveformMinHeightSpin
            Kirigami.FormData.label: i18n("Min height (%):")
            from: 5
            to: 50
            stepSize: 5
            value: cfg_waveformMinHeight * 100
            visible: animationStyleCombo.currentValue === "waveform"
            onValueModified: cfg_waveformMinHeight = value / 100.0
        }
    }
}
