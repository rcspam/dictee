import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: dotsAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0
    property var audioBands: []
    property real sensitivity: Plasmoid.configuration.audioSensitivity || 2.0

    clip: true

    Row {
        id: dotRow
        anchors.centerIn: parent
        spacing: Plasmoid.configuration.dotSpacing || Math.max(2, (dotsAnim.width - Plasmoid.configuration.dotCount * Plasmoid.configuration.dotSize) / (Plasmoid.configuration.dotCount + 1))

        Repeater {
            model: Plasmoid.configuration.dotCount

            Rectangle {
                readonly property int dotIndex: index

                readonly property real dotLevel: {
                    var sens = dotsAnim.sensitivity
                    var raw
                    if (dotsAnim.audioBands.length > 0) {
                        var bandIdx = Math.min(
                            Math.floor(dotIndex * dotsAnim.audioBands.length / Plasmoid.configuration.dotCount),
                            dotsAnim.audioBands.length - 1)
                        raw = Math.min(1.0, dotsAnim.audioBands[bandIdx])
                    } else {
                        raw = Math.min(1.0, dotsAnim.audioLevel)
                    }
                    return raw > 0 ? Math.pow(raw, 1.0 / sens) : 0
                }

                width: {
                    var base = Plasmoid.configuration.dotSize
                    if (dotsAnim.state !== "recording") return base
                    return base * (0.6 + 0.8 * dotLevel)
                }
                height: width
                radius: width / 2
                color: {
                    if (!Plasmoid.configuration.useRainbow) return dotsAnim.barColor
                    var n = Plasmoid.configuration.dotCount
                    var t = n > 1 ? dotIndex / (n - 1) : 0.5
                    var startH = Plasmoid.configuration.rainbowStartHue / 360.0
                    var endH = Plasmoid.configuration.rainbowEndHue / 360.0
                    return Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                }

                opacity: {
                    if (dotsAnim.state !== "recording") return 0.5
                    return 0.4 + 0.6 * dotLevel
                }

                y: {
                    if (dotsAnim.state !== "recording" || dotLevel <= 0.01) {
                        return dotsAnim.height / 2 - Plasmoid.configuration.dotSize / 2
                    }
                    var dotSz = Plasmoid.configuration.dotSize
                    var centerY = dotsAnim.height / 2 - dotSz / 2
                    var bounce = (Plasmoid.configuration.dotBounce || 40) / 100.0
                    var phase = Math.sin(dotIndex * 1.8 + dotLevel * 8)
                    var displacement = dotsAnim.height * bounce * dotLevel * phase
                    var raw = centerY - displacement
                    return Math.max(0, Math.min(raw, dotsAnim.height - dotSz))
                }

                Behavior on y {
                    NumberAnimation { duration: 60; easing.type: Easing.OutQuad }
                }
                Behavior on width {
                    NumberAnimation { duration: 60; easing.type: Easing.OutQuad }
                }
                Behavior on opacity {
                    NumberAnimation { duration: 60; easing.type: Easing.OutQuad }
                }
            }
        }
    }
}
