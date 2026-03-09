import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

Item {
    id: wfAnim

    property string state: "idle"
    property color barColor: Kirigami.Theme.textColor
    property real audioLevel: 0.0
    property var audioBands: []
    property real sensitivity: Plasmoid.configuration.audioSensitivity || 2.0

    Row {
        id: wfRow
        anchors.fill: parent
        spacing: Plasmoid.configuration.waveformSpacing

        Repeater {
            model: Plasmoid.configuration.waveformBars

            Rectangle {
                readonly property int barIndex: index
                // Enveloppe Hanning : ~0 aux extrémités, 1 au centre
                readonly property real envelope: {
                    var n = Plasmoid.configuration.waveformBars
                    if (n <= 1) return 1.0
                    return 0.5 - 0.5 * Math.cos(2 * Math.PI * barIndex / (n - 1))
                }
                readonly property real barLevel: {
                    var sens = wfAnim.sensitivity
                    var raw
                    if (wfAnim.audioBands.length > 0) {
                        var bandIdx = Math.min(
                            Math.floor(barIndex * wfAnim.audioBands.length / Plasmoid.configuration.waveformBars),
                            wfAnim.audioBands.length - 1)
                        raw = Math.min(1.0, wfAnim.audioBands[bandIdx] * sens)
                    } else {
                        raw = Math.min(1.0, wfAnim.audioLevel * sens)
                    }
                    return raw * envelope
                }

                readonly property real minRatio: Plasmoid.configuration.waveformMinHeight
                readonly property real effectiveLevel: {
                    if (wfAnim.state !== "recording") return 0.0
                    return barLevel
                }

                width: Math.max(1, (wfRow.width - (Plasmoid.configuration.waveformBars - 1) * Plasmoid.configuration.waveformSpacing) / Plasmoid.configuration.waveformBars)
                height: {
                    var h = wfRow.height * (minRatio + (1.0 - minRatio) * effectiveLevel)
                    return Math.max(2, h)
                }
                radius: Plasmoid.configuration.waveformRadius
                color: {
                    if (!Plasmoid.configuration.useRainbow) return wfAnim.barColor
                    var n = Plasmoid.configuration.waveformBars
                    var t = n > 1 ? barIndex / (n - 1) : 0.5
                    var startH = Plasmoid.configuration.rainbowStartHue / 360.0
                    var endH = Plasmoid.configuration.rainbowEndHue / 360.0
                    return Qt.hsla(startH + (endH - startH) * t, 0.8, 0.55, 1.0)
                }

                // Centré verticalement
                y: (wfRow.height - height) / 2

                opacity: {
                    if (wfAnim.state !== "recording") return 0.5
                    return 0.4 + 0.6 * effectiveLevel
                }

                Behavior on height {
                    NumberAnimation { duration: 50; easing.type: Easing.OutQuad }
                }
                Behavior on opacity {
                    NumberAnimation { duration: 50; easing.type: Easing.OutQuad }
                }
            }
        }
    }
}
