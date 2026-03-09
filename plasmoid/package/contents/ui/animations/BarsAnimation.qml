import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: barsAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0
    // Bandes de frequences (une par barre, fournies par dictee-plasmoid-level-fft)
    property var audioBands: []

    // Compteur temporel pour l'animation idle
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

                readonly property real targetHeight: {
                    var minRatio = Plasmoid.configuration.barMinHeight

                    if (barsAnim.state !== "recording") {
                        return barRow.height * minRatio
                    }

                    var level

                    var sens = Plasmoid.configuration.audioSensitivity

                    if (barsAnim.audioBands.length > 0 && barIndex < barsAnim.audioBands.length) {
                        // Mode spectre FFT : valeurs calibrees 0-1 (noise floor soustrait)
                        // Sensibilite amplifie directement (defaut 2.0 = x2)
                        level = Math.min(1.0, barsAnim.audioBands[barIndex] * sens)
                    } else {
                        // Fallback : niveau global unique
                        level = Math.min(1.0, barsAnim.audioLevel * sens)
                    }

                    if (level <= 0.005) {
                        // Silence : respiration idle ou statique
                        if (Plasmoid.configuration.barIdleAnimation) {
                            var idle = 0.5 + 0.5 * Math.sin(barsAnim.tick * 0.15 + barIndex * 1.2)
                            return barRow.height * (minRatio + 0.05 * idle)
                        }
                        return barRow.height * minRatio
                    }

                    return barRow.height * (minRatio + (1.0 - minRatio) * level)
                }

                width: Math.max(1, (barRow.width - (Plasmoid.configuration.barCount - 1) * Plasmoid.configuration.barSpacing) / Plasmoid.configuration.barCount)
                height: targetHeight
                anchors.bottom: barRow.bottom
                radius: Plasmoid.configuration.barRadius
                color: barsAnim.barColor

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
