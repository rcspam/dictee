import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: waveAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0
    property real phase: 0.0

    NumberAnimation on phase {
        id: phaseAnim
        running: waveAnim.state === "recording"
        from: 0
        to: 2 * Math.PI
        duration: Plasmoid.configuration.waveSpeed * 4
        loops: Animation.Infinite
    }

    onPhaseChanged: canvas.requestPaint()
    onStateChanged: canvas.requestPaint()
    onAudioLevelChanged: if (state === "recording") canvas.requestPaint()

    Canvas {
        id: canvas
        anchors.fill: parent

        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.strokeStyle = waveAnim.barColor
            ctx.lineWidth = Plasmoid.configuration.waveThickness
            ctx.lineCap = "round"
            ctx.lineJoin = "round"

            var maxAmplitude = height * 0.5 * Plasmoid.configuration.waveAmplitude
            var frequency = Plasmoid.configuration.waveFrequency
            var centerY = height / 2

            // Amplitude modulee par le niveau audio + sensibilite
            var sens = Plasmoid.configuration.audioSensitivity
            var amplified = Math.min(1.0, waveAnim.audioLevel * sens)
            var effectiveAmplitude = waveAnim.state === "recording"
                ? maxAmplitude * Math.max(0.1, amplified)
                : maxAmplitude * 0.1

            ctx.beginPath()
            for (var x = 0; x <= width; x += 2) {
                var ratio = x / width
                var y = centerY + effectiveAmplitude * Math.sin(ratio * frequency * 2 * Math.PI + waveAnim.phase)
                if (x === 0) {
                    ctx.moveTo(x, y)
                } else {
                    ctx.lineTo(x, y)
                }
            }
            ctx.stroke()
        }
    }
}
