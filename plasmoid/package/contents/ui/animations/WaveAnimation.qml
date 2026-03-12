import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: waveAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0
    property var audioBands: []
    property real sensitivity: Plasmoid.configuration.audioSensitivity || 2.0
    property real phase: 0.0

    NumberAnimation on phase {
        running: waveAnim.state === "recording"
        from: 0
        to: 2 * Math.PI
        duration: Plasmoid.configuration.waveSpeed * 4
        loops: Animation.Infinite
    }

    onPhaseChanged: canvas.requestPaint()
    onStateChanged: canvas.requestPaint()
    onAudioLevelChanged: if (state === "recording") canvas.requestPaint()
    onAudioBandsChanged: if (state === "recording") canvas.requestPaint()

    Canvas {
        id: canvas
        anchors.fill: parent
        onWidthChanged: if (width > 0 && height > 0) requestPaint()
        onHeightChanged: if (width > 0 && height > 0) requestPaint()

        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (width <= 0 || height <= 0) return

            var thickness = Plasmoid.configuration.waveThickness
            var maxAmplitude = height * 0.45 * Plasmoid.configuration.waveAmplitude
            var frequency = Plasmoid.configuration.waveFrequency
            var centerY = height / 2
            var sens = waveAnim.sensitivity
            var bands = waveAnim.audioBands
            var hasBands = bands.length > 0

            var useRainbow = Plasmoid.configuration.useRainbow
            var startH = Plasmoid.configuration.rainbowStartHue / 360.0
            var endH = Plasmoid.configuration.rainbowEndHue / 360.0

            var points = []
            for (var x = 0; x <= width; x += 2) {
                var ratio = x / width
                // Enveloppe Hanning avec centre et puissance configurables
                var c = Plasmoid.configuration.envelopeCenter
                var rr = (c > 0.01 && ratio <= c) ? 0.5 * ratio / c
                       : (c < 0.99 && ratio > c)  ? 0.5 + 0.5 * (ratio - c) / (1.0 - c)
                       : (c <= 0.01)               ? 0.5 + 0.5 * ratio
                       :                             0.5 * ratio
                var h = 0.5 - 0.5 * Math.cos(2 * Math.PI * rr)
                var envPow = Plasmoid.configuration.envelopePower
                var envelope = envPow > 0.01 ? Math.pow(h, envPow) : 1.0
                var localLevel
                var rawLevel
                if (hasBands && waveAnim.state === "recording") {
                    var bandIdx = Math.min(Math.floor(ratio * bands.length), bands.length - 1)
                    rawLevel = Math.min(1.0, bands[bandIdx])
                } else {
                    rawLevel = Math.min(1.0, waveAnim.audioLevel)
                }
                localLevel = rawLevel > 0 ? Math.pow(rawLevel, 1.0 / sens) : 0
                var amp = waveAnim.state === "recording"
                    ? maxAmplitude * Math.max(0.15, localLevel) * envelope
                    : maxAmplitude * 0.15 * envelope
                var y = amp * Math.sin(ratio * frequency * 2 * Math.PI + waveAnim.phase)
                points.push({ x: x, y: y })
            }

            // Remplissage semi-transparent
            if (Plasmoid.configuration.waveFill !== false) {
                ctx.fillStyle = Qt.rgba(waveAnim.barColor.r, waveAnim.barColor.g, waveAnim.barColor.b, 0.15)
                ctx.beginPath()
                ctx.moveTo(0, centerY)
                for (var i = 0; i < points.length; i++) {
                    ctx.lineTo(points[i].x, centerY + points[i].y)
                }
                ctx.lineTo(width, centerY)
                ctx.closePath()
                ctx.fill()
            }

            // Ligne principale (rainbow = segments de couleur, sinon trait uni)
            ctx.lineWidth = thickness
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            if (useRainbow && points.length > 1) {
                for (var s = 0; s < points.length - 1; s++) {
                    var t = s / (points.length - 1)
                    var hue = startH + (endH - startH) * t
                    ctx.strokeStyle = Qt.hsla(hue, 0.8, 0.55, 1.0)
                    ctx.beginPath()
                    ctx.moveTo(points[s].x, centerY + points[s].y)
                    ctx.lineTo(points[s+1].x, centerY + points[s+1].y)
                    ctx.stroke()
                }
            } else {
                ctx.strokeStyle = waveAnim.barColor
                ctx.beginPath()
                for (var j = 0; j < points.length; j++) {
                    var px = points[j].x
                    var py = centerY + points[j].y
                    if (j === 0) ctx.moveTo(px, py)
                    else ctx.lineTo(px, py)
                }
                ctx.stroke()
            }
        }
    }
}
