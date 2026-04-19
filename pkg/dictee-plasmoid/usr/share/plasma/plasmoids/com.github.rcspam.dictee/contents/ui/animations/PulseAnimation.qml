import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: pulseAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0
    property var audioBands: []
    property real sensitivity: Plasmoid.configuration.audioSensitivity || 2.0

    readonly property real amplifiedLevel: {
        var sens = pulseAnim.sensitivity
        var raw = audioLevel
        if (audioBands.length > 0) {
            var maxBand = 0
            for (var i = 0; i < audioBands.length; i++) {
                if (audioBands[i] > maxBand) maxBand = audioBands[i]
            }
            raw = maxBand
        }
        raw = Math.min(1.0, raw)
        return raw > 0 ? Math.pow(raw, 1.0 / sens) : 0
    }

    Repeater {
        model: Plasmoid.configuration.pulseRings

        Rectangle {
            readonly property int ringIndex: index
            readonly property real ringLevel: {
                if (audioBands.length > 0 && pulseAnim.state === "recording") {
                    var bandIdx = Math.min(
                        Math.floor(ringIndex * audioBands.length / Plasmoid.configuration.pulseRings),
                        audioBands.length - 1)
                    var rv = Math.min(1.0, audioBands[bandIdx])
                    return rv > 0 ? Math.pow(rv, 1.0 / pulseAnim.sensitivity) : 0
                }
                return pulseAnim.amplifiedLevel
            }

            anchors.centerIn: parent
            width: Math.min(pulseAnim.width, pulseAnim.height) * (0.9 - ringIndex * 0.15)
            height: width
            radius: width / 2
            color: "transparent"
            border.color: {
                    if (!Plasmoid.configuration.useRainbow) return pulseAnim.barColor
                    var n = Plasmoid.configuration.pulseRings
                    var t = n > 1 ? ringIndex / (n - 1) : 0.5
                    var startH = Plasmoid.configuration.rainbowStartHue / 360.0
                    var endH = Plasmoid.configuration.rainbowEndHue / 360.0
                    return Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                }
            border.width: Plasmoid.configuration.pulseThickness || 2

            scale: {
                if (pulseAnim.state !== "recording") return 0.8
                return 0.5 + 0.5 * ringLevel
            }

            opacity: {
                if (pulseAnim.state !== "recording") {
                    return Kirigami.Theme.textColor.hslLightness > 0.5 ? 0.4 : 0.75
                }
                return 0.4 + 0.6 * ringLevel
            }

            Behavior on scale {
                NumberAnimation { duration: 80; easing.type: Easing.OutQuad }
            }
            Behavior on opacity {
                NumberAnimation { duration: 80; easing.type: Easing.OutQuad }
            }
        }
    }

    // Point central
    Rectangle {
        anchors.centerIn: parent
        width: Math.min(pulseAnim.width, pulseAnim.height) * 0.25
        height: width
        radius: width / 2
        color: {
            if (!Plasmoid.configuration.useRainbow) return pulseAnim.barColor
            var startH = Plasmoid.configuration.rainbowStartHue / 360.0
            var endH = Plasmoid.configuration.rainbowEndHue / 360.0
            return Qt.hsla((startH + endH) / 2, 0.8, 0.55, 1.0)
        }

        scale: pulseAnim.state === "recording" ? 0.5 + 0.5 * pulseAnim.amplifiedLevel : 0.8
        opacity: pulseAnim.state === "recording"
            ? 0.6 + 0.4 * pulseAnim.amplifiedLevel
            : (Kirigami.Theme.textColor.hslLightness > 0.5 ? 0.5 : 0.9)

        Behavior on scale {
            NumberAnimation { duration: 80; easing.type: Easing.OutQuad }
        }
        Behavior on opacity {
            NumberAnimation { duration: 80; easing.type: Easing.OutQuad }
        }
    }
}
