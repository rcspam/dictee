import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: pulseAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0

    readonly property real amplifiedLevel: {
        var sens = Plasmoid.configuration.audioSensitivity
        return Math.min(1.0, audioLevel * sens)
    }

    Repeater {
        model: Plasmoid.configuration.pulseRings

        Rectangle {
            id: ring
            readonly property int ringIndex: index

            anchors.centerIn: parent
            width: Math.min(pulseAnim.width, pulseAnim.height) * 0.8
            height: width
            radius: width / 2
            color: "transparent"
            border.color: pulseAnim.barColor
            border.width: 2

            scale: {
                if (pulseAnim.state !== "recording") return 1.0
                var base = 0.4 + 0.6 * pulseAnim.amplifiedLevel
                var offset = ringIndex * 0.15
                return Math.max(0.3, Math.min(1.0, base - offset))
            }

            opacity: {
                if (pulseAnim.state !== "recording") return 0.5
                return 0.3 + 0.7 * pulseAnim.amplifiedLevel * (1.0 - ringIndex * 0.3)
            }

            Behavior on scale {
                NumberAnimation { duration: 120; easing.type: Easing.OutQuad }
            }
            Behavior on opacity {
                NumberAnimation { duration: 120; easing.type: Easing.OutQuad }
            }
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(pulseAnim.width, pulseAnim.height) * 0.2
        height: width
        radius: width / 2
        color: pulseAnim.barColor
        opacity: pulseAnim.state === "recording" ? 0.5 + 0.5 * pulseAnim.amplifiedLevel : 0.5
        scale: pulseAnim.state === "recording" ? 0.6 + 0.4 * pulseAnim.amplifiedLevel : 1.0

        Behavior on opacity {
            NumberAnimation { duration: 120; easing.type: Easing.OutQuad }
        }
        Behavior on scale {
            NumberAnimation { duration: 120; easing.type: Easing.OutQuad }
        }
    }
}
