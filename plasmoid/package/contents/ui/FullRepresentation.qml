import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import QtQuick.Controls as QQC2
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: fullRep

    property string state: "offline"
    property color barColor: Kirigami.Theme.textColor
    property string lastTranscription: ""
    signal actionRequested(string action)

    Layout.preferredWidth: Kirigami.Units.gridUnit * 18
    Layout.preferredHeight: implicitHeight
    Layout.minimumWidth: Kirigami.Units.gridUnit * 14
    Layout.maximumWidth: Kirigami.Units.gridUnit * 24

    spacing: Kirigami.Units.smallSpacing

    // En-tete avec pin
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaExtras.Heading {
            level: 3
            text: "Dictée"
            Layout.fillWidth: true
        }

        PlasmaComponents.ToolButton {
            id: pinButton
            checkable: true
            checked: Plasmoid.configuration.pinPopup
            icon.name: "window-pin"
            display: PlasmaComponents.AbstractButton.IconOnly
            PlasmaComponents.ToolTip { text: pinButton.checked ? i18n("Unpin popup") : i18n("Pin popup") }
            onToggled: {
                Plasmoid.configuration.pinPopup = checked
                root.hideOnWindowDeactivate = !checked
            }
            Component.onCompleted: {
                root.hideOnWindowDeactivate = !Plasmoid.configuration.pinPopup
            }
        }
    }

    // Statut daemon + bouton start/stop discret
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        Rectangle {
            width: Kirigami.Units.smallSpacing * 3
            height: width
            radius: width / 2
            color: {
                switch (fullRep.state) {
                case "offline":
                    return Kirigami.Theme.negativeTextColor
                case "recording":
                    return Kirigami.Theme.highlightColor
                case "transcribing":
                    return Kirigami.Theme.positiveTextColor
                default:
                    return Kirigami.Theme.positiveTextColor
                }
            }
        }

        PlasmaComponents.Label {
            text: {
                switch (fullRep.state) {
                case "offline":
                    return i18n("Daemon stopped")
                case "idle":
                    return i18n("Daemon active")
                case "recording":
                    return i18n("Recording…")
                case "transcribing":
                    return i18n("Transcribing…")
                default:
                    return ""
                }
            }
            Layout.fillWidth: true
        }

        PlasmaComponents.ToolButton {
            icon.name: fullRep.state === "offline" ? "media-playback-start" : "media-playback-stop"
            display: PlasmaComponents.AbstractButton.IconOnly
            PlasmaComponents.ToolTip {
                text: fullRep.state === "offline" ? i18n("Start daemon") : i18n("Stop daemon")
            }
            onClicked: fullRep.actionRequested(fullRep.state === "offline" ? "start-daemon" : "stop-daemon")
        }
    }

    // Separateur
    Kirigami.Separator {
        Layout.fillWidth: true
    }

    // Boutons dictee
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        visible: fullRep.state !== "offline"

        PlasmaComponents.Button {
            text: i18n("Voice dictation")
            icon.name: "audio-input-microphone"
            onClicked: fullRep.actionRequested("dictate")
            Layout.fillWidth: true
            enabled: fullRep.state === "idle" || fullRep.state === "recording"
        }

        PlasmaComponents.Button {
            text: i18n("Dictation + Translation")
            icon.name: "translate"
            onClicked: fullRep.actionRequested("dictate-translate")
            Layout.fillWidth: true
            enabled: fullRep.state === "idle"
        }
    }

    // Bouton annuler (visible uniquement en recording)
    PlasmaComponents.Button {
        visible: fullRep.state === "recording"
        Layout.fillWidth: true
        onClicked: fullRep.actionRequested("cancel")

        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Icon {
                source: "dialog-cancel"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                color: Kirigami.Theme.negativeTextColor
            }
            PlasmaComponents.Label {
                text: i18n("Cancel recording")
                color: Kirigami.Theme.negativeTextColor
                Layout.fillWidth: true
            }
        }
    }

    // Raccourci ESC pour annuler
    Keys.onEscapePressed: {
        if (fullRep.state === "recording") {
            fullRep.actionRequested("cancel")
        }
    }

    // Separateur avant transcription
    Kirigami.Separator {
        Layout.fillWidth: true
        visible: transcriptionArea.visible
    }

    // Derniere transcription
    ColumnLayout {
        id: transcriptionArea
        Layout.fillWidth: true
        visible: Plasmoid.configuration.showLastTranscription && fullRep.lastTranscription.length > 0
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.Label {
            text: i18n("Last transcription:")
            font.bold: true
            Layout.fillWidth: true
        }

        PlasmaComponents.Label {
            text: fullRep.lastTranscription
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            opacity: 0.8
            maximumLineCount: 5
            elide: Text.ElideRight
        }
    }

    // Separateur
    Kirigami.Separator {
        Layout.fillWidth: true
    }

    // Preview + configuration
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        QQC2.CheckBox {
            text: i18n("Preview (mic test)")
            checked: Plasmoid.configuration.previewMode
            onToggled: Plasmoid.configuration.previewMode = checked
        }

        Item { Layout.fillWidth: true }

        PlasmaComponents.Button {
            text: i18n("Configuration…")
            icon.name: "configure"
            flat: true
            onClicked: fullRep.actionRequested("setup")
        }
    }

    // Focus pour recevoir ESC
    Component.onCompleted: forceActiveFocus()
}
