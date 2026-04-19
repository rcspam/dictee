import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: compact

    // Use the app-theme palette (Window/View) so idle bars are as dark as
    // the app textColor in light mode (~#232629) — "bien noir" on a light
    // theme. In dark mode this stays light. Complementary would invert the
    // logic and give white on white, which we don't want here.
    Kirigami.Theme.colorSet: Kirigami.Theme.Window
    Kirigami.Theme.inherit: false

    property string state: "offline"
    property color barColor: {
        switch (state) {
        case "recording":    return Kirigami.Theme.highlightColor
        case "transcribing": return Kirigami.Theme.positiveTextColor
        case "offline":      return Kirigami.Theme.negativeTextColor
        default:             return Kirigami.Theme.textColor
        }
    }
    property real audioLevel: 0.0
    property var audioBands: []
    property real sensitivity: 2.0

    readonly property bool animActive: state === "recording" || state === "transcribing"

    Layout.preferredWidth: {
        var style = Plasmoid.configuration.animationStyle || "bars"
        if (style === "bars") {
            var count = Plasmoid.configuration.barCount
            var spacing = Plasmoid.configuration.barSpacing
            var barWidth = Math.max(3, (Kirigami.Units.iconSizes.medium - (count - 1) * spacing) / count)
            return count * barWidth + (count - 1) * spacing
        }
        if (style === "wave") {
            return Plasmoid.configuration.waveWidth
        }
        if (style === "dots") {
            var dotCount = Plasmoid.configuration.dotCount
            var dotSize = Plasmoid.configuration.dotSize
            var dotSpacing = Plasmoid.configuration.dotSpacing
            return dotCount * dotSize + (dotCount + 1) * dotSpacing
        }
        if (style === "waveform") {
            var wfBars = Plasmoid.configuration.waveformBars
            var wfSpacing = Plasmoid.configuration.waveformSpacing
            var wfBarWidth = Math.max(2, (Kirigami.Units.iconSizes.medium - (wfBars - 1) * wfSpacing) / wfBars)
            return wfBars * wfBarWidth + (wfBars - 1) * wfSpacing
        }
        // pulse : carré
        return Kirigami.Units.iconSizes.medium
    }
    Layout.preferredHeight: Kirigami.Units.iconSizes.medium

    opacity: state === "offline" ? 0.7 : 1.0

    Behavior on opacity {
        NumberAnimation { duration: 300 }
    }

    // Pulsation globale en transcribing
    SequentialAnimation on opacity {
        id: transcribingPulse
        running: compact.state === "transcribing"
        loops: Animation.Infinite
        NumberAnimation { to: 0.4; duration: 600; easing.type: Easing.InOutSine }
        NumberAnimation { to: 1.0; duration: 600; easing.type: Easing.InOutSine }
        onRunningChanged: {
            if (!running) compact.opacity = compact.state === "offline" ? 0.4 : 1.0
        }
    }

    // Forme d'onde statique quand l'animation n'est pas active
    Canvas {
        id: idleWaveform
        anchors.fill: parent
        visible: !compact.animActive
        opacity: 0.6

        onWidthChanged: if (width > 0 && height > 0) requestPaint()
        onHeightChanged: if (width > 0 && height > 0) requestPaint()
        onVisibleChanged: if (visible && width > 0 && height > 0) requestPaint()

        Connections {
            target: compact
            function onBarColorChanged() { if (idleWaveform.visible && idleWaveform.width > 0) idleWaveform.requestPaint() }
        }

        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (width <= 0 || height <= 0) return

            var centerY = height / 2
            var maxAmp = height * 0.35
            var color = compact.barColor

            // Forme d'onde stylisée avec des segments de hauteur variable
            ctx.strokeStyle = color
            ctx.lineWidth = Math.max(1.5, height * 0.06)
            ctx.lineCap = "round"
            ctx.lineJoin = "round"

            // Pattern de forme d'onde avec enveloppe Hanning (zéro aux bords, max au centre)
            var rawSegments = [0.6, 0.85, 0.7, 0.95, 1.0, 0.75, 0.9, 0.65, 0.8, 0.5, 0.7, 0.55, 0.6]
            var nSeg = rawSegments.length
            var segWidth = width / nSeg

            ctx.beginPath()
            for (var i = 0; i < nSeg; i++) {
                var x = (i + 0.5) * segWidth
                // Enveloppe Hanning : 0 aux extrémités, 1 au centre
                var tEnv = i / (nSeg - 1)
                var cEnv = Plasmoid.configuration.envelopeCenter
                cEnv = (cEnv !== undefined) ? cEnv : 0.5
                var rEnv = (cEnv > 0.01 && tEnv <= cEnv) ? 0.5 * tEnv / cEnv
                         : (cEnv < 0.99 && tEnv > cEnv)  ? 0.5 + 0.5 * (tEnv - cEnv) / (1.0 - cEnv)
                         : (cEnv <= 0.01)                  ? 0.5 + 0.5 * tEnv
                         :                                   0.5 * tEnv
                var hEnv = 0.5 - 0.5 * Math.cos(2 * Math.PI * rEnv)
                var envPow = Plasmoid.configuration.envelopePower
                var envelope = (envPow !== undefined && envPow > 0.01) ? Math.pow(hEnv, envPow) : hEnv
                var amp = rawSegments[i] * envelope * maxAmp
                if (amp < 1) amp = 1
                ctx.moveTo(x, centerY - amp)
                ctx.lineTo(x, centerY + amp)
            }
            ctx.stroke()
        }
    }

    // Propriété intermédiaire pour forcer une destruction propre au changement de style
    property string currentAnimStyle: Plasmoid.configuration.animationStyle || "bars"
    onCurrentAnimStyleChanged: {
        animLoader.source = ""
        animLoader.source = "animations/" + currentAnimStyle.charAt(0).toUpperCase() + currentAnimStyle.slice(1) + "Animation.qml"
    }

    Loader {
        id: animLoader
        anchors.fill: parent
        visible: compact.animActive
        source: "animations/" + compact.currentAnimStyle.charAt(0).toUpperCase() + compact.currentAnimStyle.slice(1) + "Animation.qml"
        onLoaded: {
            if (item) {
                item.state = Qt.binding(function() { return compact.state })
                item.barColor = Qt.binding(function() { return compact.barColor })
                item.audioLevel = Qt.binding(function() { return compact.audioLevel })
                if (item.hasOwnProperty("audioBands")) {
                    item.audioBands = Qt.binding(function() { return compact.audioBands })
                }
                if (item.hasOwnProperty("sensitivity")) {
                    item.sensitivity = Qt.binding(function() { return compact.sensitivity })
                }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        onClicked: function(mouse) {
            if (mouse.button === Qt.LeftButton) {
                root.expanded = !root.expanded
            } else if (mouse.button === Qt.MiddleButton) {
                root.handleAction("dictate")
            }
        }
    }
}
