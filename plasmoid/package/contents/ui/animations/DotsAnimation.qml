import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: dotsAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0

    readonly property real amplifiedLevel: {
        var sens = Plasmoid.configuration.audioSensitivity
        return Math.min(1.0, audioLevel * sens)
    }

    Row {
        id: dotRow
        anchors.centerIn: parent
        spacing: Math.max(2, (dotsAnim.width - Plasmoid.configuration.dotCount * Plasmoid.configuration.dotSize) / (Plasmoid.configuration.dotCount + 1))

        Repeater {
            model: Plasmoid.configuration.dotCount

            Rectangle {
                id: dot
                readonly property int dotIndex: index

                width: Plasmoid.configuration.dotSize
                height: Plasmoid.configuration.dotSize
                radius: width / 2
                color: dotsAnim.barColor

                // Position Y modulee par le niveau audio + sensibilite
                y: {
                    if (dotsAnim.state !== "recording" || dotsAnim.amplifiedLevel <= 0.01) {
                        return dotsAnim.height / 2 - height / 2
                    }
                    var centerY = dotsAnim.height / 2 - height / 2
                    var level = dotsAnim.amplifiedLevel
                    // Chaque point rebondit differemment
                    var phase = Math.sin(dotIndex * 1.8 + level * 8)
                    var displacement = dotsAnim.height * 0.35 * level * phase
                    return centerY - displacement
                }

                Behavior on y {
                    NumberAnimation { duration: 100; easing.type: Easing.OutQuad }
                }
            }
        }
    }
}
