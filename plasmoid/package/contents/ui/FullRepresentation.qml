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
    property bool dicteeInstalled: true
    property bool dicteeConfigured: true
    property color barColor: Kirigami.Theme.textColor
    property string lastTranscription: ""
    signal actionRequested(string action)

    // Fermer les ComboBox quand le popup se ferme
    onVisibleChanged: {
        if (!visible) {
            if (asrCombo.popup && asrCombo.popup.visible) asrCombo.popup.close()
            if (transCombo.popup && transCombo.popup.visible) transCombo.popup.close()
        }
    }

    Layout.preferredWidth: Kirigami.Units.gridUnit * 36
    Layout.preferredHeight: implicitHeight
    Layout.minimumWidth: Kirigami.Units.gridUnit * 36
    Layout.maximumWidth: Kirigami.Units.gridUnit * 40

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
                case "switching":
                    return Kirigami.Theme.neutralTextColor
                default:
                    return Kirigami.Theme.positiveTextColor
                }
            }
        }

        PlasmaComponents.Label {
            text: {
                switch (fullRep.state) {
                case "offline":
                    if (!fullRep.dicteeInstalled) return i18n("Dictée not installed — install dictee package")
                    if (!fullRep.dicteeConfigured) return i18n("Not configured — click Configure Dictée below")
                    return i18n("Daemon stopped")
                case "idle":
                    return i18n("Daemon active")
                case "recording":
                    return i18n("Recording…")
                case "transcribing":
                    return i18n("Transcribing…")
                case "switching":
                    return i18n("Switching backend…")
                default:
                    return ""
                }
            }
            Layout.fillWidth: true
        }

        PlasmaComponents.ToolButton {
            icon.name: "view-refresh"
            display: PlasmaComponents.AbstractButton.IconOnly
            visible: fullRep.state !== "offline"
            PlasmaComponents.ToolTip { text: i18n("Reset") }
            onClicked: fullRep.actionRequested("reset")
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
            QQC2.ToolTip.text: fullRep.state === "idle"
                ? i18n("Press to start recording. Press again to stop and transcribe.")
                : fullRep.state === "recording"
                    ? i18n("Press to stop recording and transcribe.")
                    : ""
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        PlasmaComponents.Button {
            text: i18n("Dictation + Translation")
            icon.name: "translate"
            onClicked: fullRep.actionRequested("dictate-translate")
            Layout.fillWidth: true
            enabled: fullRep.state === "idle" || fullRep.state === "recording"
            QQC2.ToolTip.text: fullRep.state === "idle"
                ? i18n("Press to start recording. Press again to stop, transcribe, and translate.")
                : fullRep.state === "recording"
                    ? i18n("Press to stop recording, transcribe, and translate.")
                    : ""
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        PlasmaComponents.Button {
            id: btnDiarize
            text: btnDiarize.switching
                ? i18n("Preparing...")
                : (fullRep.state === "recording" && root.diarizeEnabled)
                    ? i18n("Stop diarization")
                    : i18n("Diarization")
            icon.name: "group"
            Layout.fillWidth: true
            enabled: root.sortformerAvailable
                && (fullRep.state === "idle" || (fullRep.state === "recording" && root.diarizeEnabled))
                && !btnDiarize.switching
            property bool switching: false

            onClicked: {
                if (fullRep.state === "recording" && root.diarizeEnabled) {
                    // Stop recording → diarize
                    fullRep.actionRequested("dictate")
                } else {
                    // Start: stop daemons to free VRAM, set flag, then record
                    switching = true
                    pulseAnim.start()
                    executable.run("dictee-switch-backend diarize true")
                    diarizeStartTimer.start()
                }
            }

            Timer {
                id: diarizeStartTimer
                interval: 2000
                onTriggered: {
                    btnDiarize.switching = false
                    pulseAnim.stop()
                    btnDiarize.opacity = 1.0
                    root.diarizeEnabled = true
                    fullRep.actionRequested("dictate")
                }
            }

            SequentialAnimation {
                id: pulseAnim
                loops: Animation.Infinite
                NumberAnimation { target: btnDiarize; property: "opacity"; to: 0.4; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { target: btnDiarize; property: "opacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            }

            QQC2.ToolTip.text: !root.sortformerAvailable
                ? i18n("Sortformer model not installed. Configure in dictee-setup.")
                : i18n("Record and identify speakers (max 4). Frees GPU memory automatically.")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
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

    // Backend selectors (hidden until configured)
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        visible: fullRep.dicteeConfigured

        PlasmaComponents.Label {
            text: i18n("ASR:")
            Layout.alignment: Qt.AlignVCenter
        }

        QQC2.ComboBox {
            id: asrCombo
            Kirigami.Theme.inherit: true
            model: ListModel {
                id: asrModel
                ListElement { text: "Parakeet"; value: "parakeet" }
                ListElement { text: "Canary"; value: "canary" }
                ListElement { text: "Vosk"; value: "vosk" }
                ListElement { text: "Whisper"; value: "whisper" }
            }
            textRole: "text"
            function syncIndex() {
                for (var i = 0; i < asrModel.count; i++) {
                    if (asrModel.get(i).value === root.currentAsrBackend) {
                        currentIndex = i
                        return
                    }
                }
                currentIndex = 0
            }
            Component.onCompleted: syncIndex()
            Connections {
                target: root
                function onCurrentAsrBackendChanged() { asrCombo.syncIndex() }
            }
            delegate: QQC2.ItemDelegate {
                width: parent ? parent.width : 0
                text: model.text
                enabled: root.installedAsr.indexOf(model.value) !== -1
                opacity: enabled ? 1.0 : 0.4
            }
            onActivated: function(index) {
                var val = asrModel.get(index).value
                if (root.installedAsr.indexOf(val) !== -1) {
                    executable.run("dictee-switch-backend asr " + val)
                } else {
                    syncIndex()
                }
            }
            Layout.fillWidth: true
        }

        PlasmaComponents.Label {
            text: i18n("Translation:")
            Layout.alignment: Qt.AlignVCenter
            enabled: root.currentAsrBackend !== "canary"
        }

        QQC2.ComboBox {
            id: transCombo
            Kirigami.Theme.inherit: true
            model: ListModel {
                id: transModel
                ListElement { text: "Google"; value: "google" }
                ListElement { text: "Bing"; value: "bing" }
                ListElement { text: "Ollama"; value: "ollama" }
                ListElement { text: "LibreTranslate"; value: "libretranslate" }
            }
            textRole: "text"
            currentIndex: {
                for (var i = 0; i < transModel.count; i++) {
                    if (transModel.get(i).value === root.currentTranslateBackend) return i
                }
                return 0
            }
            delegate: QQC2.ItemDelegate {
                width: parent ? parent.width : 0
                text: model.text
                enabled: root.installedTranslate.indexOf(model.value) !== -1
                opacity: enabled ? 1.0 : 0.4
            }
            onActivated: function(index) {
                var val = transModel.get(index).value
                if (root.installedTranslate.indexOf(val) !== -1) {
                    executable.run("dictee-switch-backend translate " + val)
                } else {
                    // Revert
                    for (var i = 0; i < transModel.count; i++) {
                        if (transModel.get(i).value === root.currentTranslateBackend) {
                            currentIndex = i; break
                        }
                    }
                }
            }
            Layout.fillWidth: true
            enabled: root.currentAsrBackend !== "canary"
        }
    }

    // Preview + actions
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        QQC2.CheckBox {
            text: i18n("Preview")
            checked: Plasmoid.configuration.previewMode
            onToggled: Plasmoid.configuration.previewMode = checked
            QQC2.ToolTip.text: i18n("Show live microphone animation preview")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        Item { Layout.fillWidth: true }

        PlasmaComponents.Button {
            text: i18n("Transcribe file")
            icon.name: "document-open"
            flat: true
            onClicked: fullRep.actionRequested("transcribe-file")
            QQC2.ToolTip.text: i18n("Open an audio file for transcription")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        PlasmaComponents.Button {
            text: i18n("Post-processing...")
            icon.name: "document-edit"
            flat: true
            onClicked: fullRep.actionRequested("postprocess")
            QQC2.ToolTip.text: i18n("Configure post-processing rules (regex, dictionary, continuation)")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        PlasmaComponents.Button {
            text: i18n("Configure Dictée")
            icon.name: "configure"
            flat: true
            onClicked: fullRep.actionRequested("setup")
            QQC2.ToolTip.text: i18n("Open dictee-setup to configure ASR, translation, shortcuts")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }
    }

    // Focus pour recevoir ESC
    Component.onCompleted: forceActiveFocus()
}
