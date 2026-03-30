import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import QtQuick.Controls as QQC2
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

RowLayout {
    id: fullRep

    property string state: "offline"
    property bool dicteeInstalled: true
    property bool dicteeConfigured: true
    property color barColor: Kirigami.Theme.textColor
    property string lastTranscription: ""
    // activeButton is stored in root (main.qml) to survive popup close/reopen
    signal actionRequested(string action)

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true

    // Rafraîchir les sources audio à l'ouverture, fermer les ComboBox à la fermeture
    onVisibleChanged: {
        if (visible) {
            executable.run(root.listAudioSourcesCmd)
        } else {
            if (asrCombo.popup && asrCombo.popup.visible) asrCombo.popup.close()
            if (transCombo.popup && transCombo.popup.visible) transCombo.popup.close()
            if (audioSourceCombo.popup && audioSourceCombo.popup.visible) audioSourceCombo.popup.close()
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
                case "diarizing":
                    return i18n("Diarization in progress…")
                default:
                    return ""
                }
            }
            Layout.minimumWidth: Kirigami.Units.gridUnit * 8
        }

        PlasmaComponents.ToolButton {
            icon.name: "view-refresh"
            display: PlasmaComponents.AbstractButton.IconOnly
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

        Item { Layout.fillWidth: true }

        QQC2.ComboBox {
            id: audioSourceCombo
            Kirigami.Theme.inherit: true
            Layout.preferredWidth: Kirigami.Units.gridUnit * 14
            visible: root.dicteeConfigured && root.audioSourceList.length > 0
            textRole: "label"
            model: root.audioSourceList
            delegate: QQC2.ItemDelegate {
                width: parent ? parent.width : 0
                contentItem: RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon {
                        source: modelData.icon || "audio-input-microphone"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    }
                    QQC2.Label {
                        text: modelData.label
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                }
                highlighted: audioSourceCombo.highlightedIndex === index
            }
            displayText: " "
            contentItem: RowLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Icon {
                    source: (root.audioSourceList.length > 0 && audioSourceCombo.currentIndex >= 0)
                            ? root.audioSourceList[audioSourceCombo.currentIndex].icon
                            : "audio-input-microphone"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                }
                QQC2.Label {
                    text: (root.audioSourceList.length > 0 && audioSourceCombo.currentIndex >= 0)
                          ? root.audioSourceList[audioSourceCombo.currentIndex].label
                          : ""
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
            currentIndex: {
                for (var i = 0; i < root.audioSourceList.length; i++) {
                    if (root.audioSourceList[i].value === root.currentAudioSource) return i
                }
                return 0
            }
            onActivated: function(index) {
                var val = root.audioSourceList[index].value
                root.currentAudioSource = val
                executable.run("bash -c 'conf=\"${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf\"; grep -q \"^DICTEE_AUDIO_SOURCE=\" \"$conf\" && sed -i \"s|^DICTEE_AUDIO_SOURCE=.*|DICTEE_AUDIO_SOURCE=" + val + "|\" \"$conf\" || echo \"DICTEE_AUDIO_SOURCE=" + val + "\" >> \"$conf\"'")
            }
            Connections {
                target: root
                function onAudioSourceListChanged() {
                    for (var i = 0; i < root.audioSourceList.length; i++) {
                        if (root.audioSourceList[i].value === root.currentAudioSource) {
                            audioSourceCombo.currentIndex = i
                            return
                        }
                    }
                    audioSourceCombo.currentIndex = 0
                }
            }
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
        visible: root.dicteeConfigured

        Item {
            Layout.fillWidth: true
            Layout.preferredWidth: 0
            implicitHeight: btnDictate.implicitHeight

            PlasmaComponents.Button {
                id: btnDictate
                anchors.fill: parent
                text: i18n("Dictation")
                icon.name: "audio-input-microphone"
                onClicked: { root.activeButton = "dictate"; fullRep.actionRequested("dictate") }
                enabled: (fullRep.state === "idle" || fullRep.state === "recording") && btnDiarize.dState === "idle"
                leftPadding: dictateDot.visible ? 20 : undefined
            }

            Rectangle {
                id: dictateDot
                property bool active: fullRep.state === "recording" && root.activeButton === "dictate"
                visible: active
                width: 10; height: 10; radius: 5
                color: "#ff0000"
                z: 100
                anchors.verticalCenter: parent.verticalCenter
                x: 6
                onActiveChanged: {
                    if (active) { dictateDotAnim.start() }
                    else { dictateDotAnim.stop(); opacity = 1.0 }
                }
            }
            SequentialAnimation {
                id: dictateDotAnim
                loops: Animation.Infinite
                NumberAnimation { target: dictateDot; property: "opacity"; to: 0.2; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { target: dictateDot; property: "opacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredWidth: 0
            implicitHeight: btnTranslate.implicitHeight

            PlasmaComponents.Button {
                id: btnTranslate
                anchors.fill: parent
                text: i18n("Translate")
                icon.name: "translate"
                onClicked: { root.activeButton = "dictate-translate"; fullRep.actionRequested("dictate-translate") }
                enabled: (fullRep.state === "idle" || fullRep.state === "recording") && btnDiarize.dState === "idle"
                leftPadding: translateDot.visible ? 20 : undefined
            }

            Rectangle {
                id: translateDot
                property bool active: fullRep.state === "recording" && root.activeButton === "dictate-translate"
                visible: active
                width: 10; height: 10; radius: 5
                color: "#ff0000"
                z: 100
                anchors.verticalCenter: parent.verticalCenter
                x: 6
                onActiveChanged: {
                    if (active) { translateDotAnim.start() }
                    else { translateDotAnim.stop(); opacity = 1.0 }
                }
            }
            SequentialAnimation {
                id: translateDotAnim
                loops: Animation.Infinite
                NumberAnimation { target: translateDot; property: "opacity"; to: 0.2; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { target: translateDot; property: "opacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            }
        }

        PlasmaComponents.Button {
            id: btnDiarize
            Layout.fillWidth: true
            Layout.preferredWidth: 0

            // States: idle → preparing → ready → recording
            property string dState: "idle"

            enabled: root.sortformerAvailable && dState !== "preparing" && fullRep.state !== "diarizing"

            contentItem: RowLayout {
                spacing: 4
                Kirigami.Icon {
                    source: "group"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                }
                PlasmaComponents.Label {
                    text: {
                        if (fullRep.state === "diarizing") return i18n("Diarization in progress...")
                        switch (btnDiarize.dState) {
                            case "preparing": return i18n("Preparing...")
                            case "ready":     return i18n("Start diarization")
                            case "recording": return i18n("Stop diarization")
                            default:          return i18n("Diarization")
                        }
                    }
                    color: {
                        if (btnDiarize.dState === "ready") return "#98c379"
                        if (btnDiarize.dState === "recording") return "#e06c75"
                        return Kirigami.Theme.textColor
                    }
                }
            }

            onClicked: {
                switch (dState) {
                    case "idle":
                        // Step 1: prepare — stop daemons, free VRAM
                        dState = "preparing"
                        root.diarizeEnabled = false
                        pulseAnim.start()
                        executable.run("bash -c 'dictee-switch-backend diarize true && echo DIARIZE_READY'")
                        break
                    case "ready":
                        // Step 2: start recording
                        dState = "recording"
                        root.diarizeEnabled = true
                        root.activeButton = "diarize"
                        fullRep.actionRequested("dictate")
                        break
                    case "recording":
                        // Step 3: stop recording → diarize → open window
                        fullRep.actionRequested("dictate")
                        dState = "idle"
                        break
                }
            }

            Connections {
                target: root
                function onDiarizeEnabledChanged() {
                    if (root.diarizeEnabled && btnDiarize.dState === "preparing") {
                        // DIARIZE_READY received — backend prêt
                        btnDiarize.dState = "ready"
                        pulseAnim.stop()
                        btnDiarize.opacity = 1.0
                    } else if (!root.diarizeEnabled) {
                        // Reset (annulation ou reset global)
                        btnDiarize.dState = "idle"
                        pulseAnim.stop()
                        btnDiarize.opacity = 1.0
                    }
                }
            }

            SequentialAnimation {
                id: pulseAnim
                loops: Animation.Infinite
                NumberAnimation { target: btnDiarize; property: "opacity"; to: 0.4; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { target: btnDiarize; property: "opacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            }

            QQC2.ToolTip.text: {
                if (!root.sortformerAvailable)
                    return i18n("Sortformer model not installed. Configure in dictee-setup.")
                switch (dState) {
                    case "preparing": return i18n("Freeing GPU memory...")
                    case "ready":     return i18n("Click to start recording with speaker identification")
                    case "recording": return i18n("Click to stop and identify speakers")
                    default:          return i18n("Record and identify speakers (max 4)")
                }
            }
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }
    }

    // Raccourci ESC pour annuler (recording ou diarisation en préparation)
    Keys.onEscapePressed: {
        if (fullRep.state === "recording") {
            fullRep.actionRequested("cancel")
        } else if (btnDiarize.dState === "preparing" || btnDiarize.dState === "ready") {
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

    // Actions + Preview
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

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

        Item { Layout.fillWidth: true }

        QQC2.CheckBox {
            text: i18n("Preview")
            checked: Plasmoid.configuration.previewMode
            onToggled: Plasmoid.configuration.previewMode = checked
            QQC2.ToolTip.text: i18n("Show live microphone animation preview")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }
    }



    // Focus pour recevoir ESC
    Component.onCompleted: forceActiveFocus()

    }  // end ColumnLayout

    // Séparateur vertical avant le slider micro
    Kirigami.Separator {
        Layout.fillHeight: true
        Layout.topMargin: Kirigami.Units.largeSpacing * 4
    }

    // Vertical microphone volume slider + level meter (right side)
    ColumnLayout {
        Layout.fillHeight: true
        Layout.preferredWidth: 50
        Layout.topMargin: Kirigami.Units.largeSpacing * 4
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            source: root.micMuted ? "microphone-sensitivity-muted" : "audio-input-microphone"
            color: root.micMuted ? "#e06c75" : Kirigami.Theme.textColor
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Kirigami.Units.iconSizes.small
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: Kirigami.Units.smallSpacing
            MouseArea {
                id: micIconMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    executable.run("wpctl set-mute @DEFAULT_SOURCE@ toggle")
                    root.micMuted = !root.micMuted
                }
            }
            QQC2.ToolTip.text: root.micMuted ? i18n("Microphone muted — click to unmute") : i18n("Microphone — click to mute")
            QQC2.ToolTip.visible: micIconMouse.containsMouse
            QQC2.ToolTip.delay: 300
        }

        RowLayout {
            Layout.fillHeight: true
            spacing: 4

            QQC2.Slider {
                id: micSlider
                Layout.fillHeight: true
                orientation: Qt.Vertical
                from: 0.0
                to: 0.6
                stepSize: 0.0
                snapMode: QQC2.Slider.NoSnap
                value: root.micVolume
                onMoved: {
                    root.micVolume = value
                    executable.run("wpctl set-volume @DEFAULT_SOURCE@ " + value.toFixed(2))
                }
                QQC2.ToolTip.text: i18n("Microphone volume: %1%", (value * 100).toFixed(0))
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: 300
            }

            // Level meter — barre verticale alignée sur le slider
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: 6
                radius: 3
                color: Kirigami.Theme.backgroundColor
                border.color: Kirigami.Theme.disabledTextColor
                border.width: 1
                clip: true

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 2
                    property real level: root.audioLevel || 0.0
                    height: Math.max(0, parent.height * Math.min(1.0, level * 1.5))
                    radius: 2
                    color: level > 0.8 ? Kirigami.Theme.negativeTextColor
                         : level > 0.4 ? Kirigami.Theme.neutralTextColor
                         : Kirigami.Theme.positiveTextColor

                    Behavior on height {
                        NumberAnimation { duration: 50 }
                    }
                }

                QQC2.ToolTip.text: i18n("Audio input level")
                QQC2.ToolTip.visible: levelMeterMouse.containsMouse
                QQC2.ToolTip.delay: 300
                MouseArea {
                    id: levelMeterMouse
                    anchors.fill: parent
                    hoverEnabled: true
                }
            }
        }
    }
}
