import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: barsAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0
    property var audioBands: []
    property real sensitivity: Plasmoid.configuration.audioSensitivity || 2.0

    property int tick: 0
    Timer {
        running: barsAnim.state === "recording" && Plasmoid.configuration.barIdleAnimation
        interval: 60
        repeat: true
        onTriggered: barsAnim.tick++
    }

    Row {
        id: barRow
        anchors.centerIn: parent
        anchors.fill: parent
        spacing: Plasmoid.configuration.barSpacing

        Repeater {
            id: barRepeater
            model: Plasmoid.configuration.barCount

            Rectangle {
                id: bar

                readonly property int barIndex: index

                // Enveloppe Hanning avec centre et puissance configurables
                readonly property real envelope: {
                    var n = Plasmoid.configuration.barCount
                    if (n <= 1) return 1.0
                    var t = barIndex / (n - 1)
                    var c = Plasmoid.configuration.envelopeCenter
                    var r = (c > 0.01 && t <= c) ? 0.5 * t / c
                          : (c < 0.99 && t > c)  ? 0.5 + 0.5 * (t - c) / (1.0 - c)
                          : (c <= 0.01)           ? 0.5 + 0.5 * t
                          :                         0.5 * t
                    var h = 0.5 - 0.5 * Math.cos(2 * Math.PI * r)
                    var p = Plasmoid.configuration.envelopePower
                    return p > 0.01 ? Math.pow(h, p) : 1.0
                }

                readonly property real targetHeight: {
                    var minRatio = Plasmoid.configuration.barMinHeight

                    if (barsAnim.state !== "recording") {
                        return barRow.height * (minRatio * envelope + minRatio * (1 - envelope) * 0.3)
                    }

                    var sens = barsAnim.sensitivity
                    var raw

                    if (barsAnim.audioBands.length > 0) {
                        var bandIdx = Math.min(
                            Math.floor(barIndex * barsAnim.audioBands.length / Plasmoid.configuration.barCount),
                            barsAnim.audioBands.length - 1)
                        raw = Math.min(1.0, barsAnim.audioBands[bandIdx])
                    } else {
                        raw = Math.min(1.0, barsAnim.audioLevel)
                    }
                    var level = raw > 0 ? Math.pow(raw, 1.0 / sens) : 0

                    level *= envelope

                    if (level <= 0.005) {
                        if (Plasmoid.configuration.barIdleAnimation) {
                            var idle = 0.5 + 0.5 * Math.sin(barsAnim.tick * 0.15 + barIndex * 1.2)
                            return barRow.height * (minRatio + 0.05 * idle) * envelope
                        }
                        return barRow.height * minRatio * Math.max(0.3, envelope)
                    }

                    return barRow.height * (minRatio + (1.0 - minRatio) * level)
                }

                width: Math.max(1, (barRow.width - (Plasmoid.configuration.barCount - 1) * Plasmoid.configuration.barSpacing) / Plasmoid.configuration.barCount)
                height: targetHeight
                anchors.bottom: barRow.bottom
                radius: Plasmoid.configuration.barRadius
                color: {
                    if (!Plasmoid.configuration.useRainbow) return barsAnim.barColor
                    var n = Plasmoid.configuration.barCount
                    var t = n > 1 ? barIndex / (n - 1) : 0.5
                    var startH = Plasmoid.configuration.rainbowStartHue / 360.0
                    var endH = Plasmoid.configuration.rainbowEndHue / 360.0
                    return Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                }

                Behavior on height {
                    NumberAnimation {
                        duration: 50
                        easing.type: Easing.OutQuad
                    }
                }
            }
        }
    }
}
