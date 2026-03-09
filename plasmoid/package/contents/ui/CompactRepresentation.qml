import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: compact

    property string state: "offline"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0
    property var audioBands: []

    Layout.preferredWidth: {
        var style = Plasmoid.configuration.animationStyle || "bars"
        if (style === "bars") {
            var count = Plasmoid.configuration.barCount
            var spacing = Plasmoid.configuration.barSpacing
            // Largeur minimale par barre : 3px
            var barWidth = Math.max(3, (Kirigami.Units.iconSizes.medium - (count - 1) * spacing) / count)
            return count * barWidth + (count - 1) * spacing
        }
        if (style === "dots") {
            var dotCount = Plasmoid.configuration.dotCount
            var dotSize = Plasmoid.configuration.dotSize
            return dotCount * dotSize + (dotCount + 1) * Math.max(2, dotSize * 0.5)
        }
        // wave, pulse : carre
        return Kirigami.Units.iconSizes.medium
    }
    Layout.preferredHeight: Kirigami.Units.iconSizes.medium

    opacity: state === "offline" ? 0.4 : 1.0

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

    Loader {
        id: animLoader
        anchors.fill: parent
        source: {
            var style = Plasmoid.configuration.animationStyle || "bars"
            return "animations/" + style.charAt(0).toUpperCase() + style.slice(1) + "Animation.qml"
        }
        onLoaded: {
            if (item) {
                item.state = Qt.binding(function() { return compact.state })
                item.barColor = Qt.binding(function() { return compact.barColor })
                item.audioLevel = Qt.binding(function() { return compact.audioLevel })
                // Passer les bandes de frequences si le composant les supporte
                if (item.hasOwnProperty("audioBands")) {
                    item.audioBands = Qt.binding(function() { return compact.audioBands })
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
