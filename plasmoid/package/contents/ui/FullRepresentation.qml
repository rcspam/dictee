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

    // Le popup est un PlasmaQuick.Dialog dont le fond suit le thème du panel
    // (souvent sombre, même en Breeze Light). On recouvre ce fond par un
    // Rectangle qui suit Kirigami.Theme.backgroundColor du colorSet View
    // (défini sur PlasmoidItem dans main.qml) pour un popup blanc en thème
    // clair, sombre en thème sombre.
    Rectangle {
        parent: fullRep
        anchors.fill: fullRep
        anchors.margins: -Kirigami.Units.largeSpacing
        z: -1
        color: Kirigami.Theme.backgroundColor
        radius: Kirigami.Units.largeSpacing * 1.5
    }

    ColumnLayout {
        id: leftColumn
        Layout.fillWidth: true
        Layout.fillHeight: false
        Layout.alignment: Qt.AlignTop

    // Rafraîchir les sources audio à l'ouverture, fermer les ComboBox à la fermeture
    onVisibleChanged: {
        if (!visible) {
            if (asrCombo.popup && asrCombo.popup.visible) asrCombo.popup.close()
            if (transCombo.popup && transCombo.popup.visible) transCombo.popup.close()
            if (audioSourceCombo.popup && audioSourceCombo.popup.visible) audioSourceCombo.popup.close()
        }
    }

    Layout.preferredWidth: Kirigami.Units.gridUnit * 40
    Layout.preferredHeight: implicitHeight
    Layout.minimumWidth: Kirigami.Units.gridUnit * 40
    Layout.maximumWidth: Kirigami.Units.gridUnit * 48

    spacing: Kirigami.Units.smallSpacing

    // En-tete avec pin
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaExtras.Heading {
            level: 3
            text: i18n("Dictée")
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

        // Daemon status group (framed)
        Rectangle {
            Layout.preferredHeight: daemonRow.implicitHeight + Kirigami.Units.smallSpacing * 2
            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
            radius: 4
            color: "transparent"
            border.color: Kirigami.Theme.disabledTextColor
            border.width: 1

            RowLayout {
                id: daemonRow
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                Rectangle {
                    width: Kirigami.Units.smallSpacing * 3
                    height: width
                    radius: width / 2
                    color: {
                        switch (fullRep.state) {
                        case "offline":
                            return "#e74c3c"  // rouge
                        case "recording":
                            return "#3498db"  // bleu
                        case "transcribing":
                            return "#2ecc71"  // vert
                        case "switching":
                            return "#e67e22"  // orange
                        case "preparing":
                        case "diarize-ready":
                        case "diarizing":
                            return "#9B59B6"  // violet
                        default:
                            return "#2ecc71"  // vert (idle)
                        }
                    }
                }

                PlasmaComponents.Label {
                    text: {
                        switch (fullRep.state) {
                        case "offline":
                            if (!fullRep.dicteeInstalled) return i18n("Not installed")
                            if (!fullRep.dicteeConfigured) return i18n("Not configured")
                            return i18n("Stopped")
                        case "idle":
                            return i18n("Active")
                        case "recording":
                            return i18n("Recording…")
                        case "transcribing":
                            return i18n("Transcribing…")
                        case "switching":
                            return i18n("Switching…")
                        case "preparing":
                            return i18n("Preparing…")
                        case "diarize-ready":
                            return i18n("Diarize ready")
                        case "diarizing":
                            return i18n("Diarizing…")
                        default:
                            return ""
                        }
                    }
                    Layout.fillWidth: true
                }

                Item { Layout.fillWidth: true }

                PlasmaComponents.ToolButton {
                    icon.name: fullRep.state === "offline" ? "media-playback-start" : "media-playback-stop"
                    display: PlasmaComponents.AbstractButton.IconOnly
                    implicitHeight: Kirigami.Units.gridUnit * 1.5
                    implicitWidth: implicitHeight
                    PlasmaComponents.ToolTip {
                        text: fullRep.state === "offline" ? i18n("Start daemon") : i18n("Stop daemon")
                    }
                    onClicked: fullRep.actionRequested(fullRep.state === "offline" ? "start-daemon" : "stop-daemon")
                }
            }
        }

        Item { Layout.fillWidth: true }

        // Banner dictée (dark/light theme)
        Image {
            source: Kirigami.Theme.textColor.hslLightness > 0.5
                ? "assets/banner-dark.svg" : "assets/banner-light.svg"
            Layout.preferredWidth: Kirigami.Units.gridUnit * 8
            Layout.preferredHeight: Kirigami.Units.gridUnit * 2
            Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
            fillMode: Image.PreserveAspectFit
            smooth: true
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

    // Message when not configured
    PlasmaComponents.Label {
        Layout.fillWidth: true
        visible: !root.dicteeConfigured
        text: i18n("Press the Configure Dictée button below to get started.")
        color: Kirigami.Theme.neutralTextColor
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.1
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

            ThemedButton {
                id: btnDictate
                anchors.fill: parent
                text: i18n("Dictation")
                icon.name: "audio-input-microphone"
                onClicked: { root.activeButton = "dictate"; fullRep.actionRequested("dictate") }
                enabled: fullRep.state === "idle" || fullRep.state === "recording"
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

            ThemedButton {
                id: btnTranslate
                anchors.fill: parent
                text: i18n("Translate")
                icon.name: "translate"
                onClicked: { root.activeButton = "dictate-translate"; fullRep.actionRequested("dictate-translate") }
                enabled: fullRep.state === "idle" || fullRep.state === "recording"
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

        ThemedButton {
            id: btnDiarize
            Layout.fillWidth: true
            Layout.preferredWidth: 0

            enabled: root.sortformerAvailable && (
                fullRep.state === "idle" ||
                fullRep.state === "preparing" ||
                fullRep.state === "diarize-ready" ||
                (fullRep.state === "recording" && root.activeButton === "diarize")
            )

            contentItem: RowLayout {
                spacing: 4
                Kirigami.Icon {
                    source: "group"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                }
                PlasmaComponents.Label {
                    text: {
                        switch (fullRep.state) {
                            case "preparing":     return i18n("Preparing… (click to cancel)")
                            case "diarize-ready":  return i18n("Start diarization")
                            case "diarizing":     return i18n("Diarization in progress...")
                            default:
                                if (fullRep.state === "recording" && root.activeButton === "diarize")
                                    return i18n("Stop diarization")
                                return i18n("Diarization")
                        }
                    }
                    color: {
                        if (fullRep.state === "diarize-ready") return Kirigami.Theme.positiveTextColor
                        if (fullRep.state === "recording" && root.activeButton === "diarize") return Kirigami.Theme.negativeTextColor
                        return Kirigami.Theme.textColor
                    }
                }
            }

            onClicked: {
                switch (fullRep.state) {
                    case "idle":
                        root.activeButton = "diarize"
                        fullRep.actionRequested("diarize-prepare")
                        break
                    case "preparing":
                        fullRep.actionRequested("cancel")
                        break
                    case "diarize-ready":
                        fullRep.actionRequested("dictate")
                        break
                    case "recording":
                        fullRep.actionRequested("dictate")
                        break
                }
            }

            opacity: fullRep.state === "preparing" ? pulseAnim.pulseOpacity : 1.0

            SequentialAnimation {
                id: pulseAnim
                property real pulseOpacity: 1.0
                running: fullRep.state === "preparing"
                loops: Animation.Infinite
                NumberAnimation { target: pulseAnim; property: "pulseOpacity"; to: 0.4; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { target: pulseAnim; property: "pulseOpacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            }

            QQC2.ToolTip.text: {
                if (!root.sortformerAvailable)
                    return i18n("Sortformer model not installed. Configure in dictee-setup.")
                switch (fullRep.state) {
                    case "preparing": return i18n("Freeing GPU memory...")
                    case "diarize-ready": return i18n("Click to start recording with speaker identification")
                    case "recording": return root.activeButton === "diarize"
                        ? i18n("Click to stop and identify speakers")
                        : i18n("Record and identify speakers (max 4)")
                    default: return i18n("Record and identify speakers (max 4)")
                }
            }

            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
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
            Layout.preferredWidth: Kirigami.Units.gridUnit * 8
        }

        QQC2.CheckBox {
            id: chkAudioContext
            text: i18n("Context")
            checked: root.audioContextEnabled
            onToggled: executable.run("dictee-switch-backend context " + (checked ? "true" : "false"))
            QQC2.ToolTip.text: i18n("Accumulate audio from previous dictations to improve recognition of short or technical words.")

            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        Item { Layout.fillWidth: true }

        PlasmaComponents.Label {
            text: i18n("Translation:")
            Layout.alignment: Qt.AlignVCenter
            enabled: root.currentAsrBackend !== "canary"
        }

        QQC2.ComboBox {
            id: transCombo
            Kirigami.Theme.inherit: true
            property bool ltWarning: root.currentTranslateBackend === "libretranslate" && !root.ltRunning
            property bool ollamaError: root.currentTranslateBackend === "ollama" && root.ollamaStatus !== "ok"
            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.color: transCombo.ltWarning ? "#e04040"
                            : (root.currentTranslateBackend === "ollama" && root.ollamaStatus === "stopped") ? "#e04040"
                            : (root.currentTranslateBackend === "ollama" && root.ollamaStatus === "no-model") ? "#e90"
                            : "transparent"
                border.width: (transCombo.ltWarning || transCombo.ollamaError) ? 2 : 0
                radius: 4
                visible: transCombo.ltWarning || transCombo.ollamaError
            }
            displayText: transCombo.ltWarning ? i18n("LT arrêté")
                       : (root.currentTranslateBackend === "ollama" && root.ollamaStatus === "stopped") ? i18n("Ollama arrêté")
                       : (root.currentTranslateBackend === "ollama" && root.ollamaStatus === "no-model") ? i18n("Modèle absent")
                       : currentText
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
                    root.backendUserChangeTime = Date.now()
                    root.currentTranslateBackend = val
                    executable.run("dictee-switch-backend translate " + val)
                    executable.run(root.translateLangsCmd + " " + val)
                    if (val === "libretranslate") {
                        executable.run(root.ltCheckCmd)
                    } else if (val === "ollama") {
                        executable.run(root.ollamaCheckCmd)
                    } else {
                        root.ltRunning = false
                        root.ollamaStatus = "ok"
                    }
                } else {
                    // Revert
                    for (var i = 0; i < transModel.count; i++) {
                        if (transModel.get(i).value === root.currentTranslateBackend) {
                            currentIndex = i; break
                        }
                    }
                }
            }
            Layout.preferredWidth: Kirigami.Units.gridUnit * 8
            enabled: root.currentAsrBackend !== "canary"
        }

        QQC2.ComboBox {
            id: langCombo
            Kirigami.Theme.inherit: true
            model: ListModel { id: langModel }
            textRole: "text"
            Layout.preferredWidth: Kirigami.Units.gridUnit * 4
            onPressedChanged: {
                if (pressed) {
                    root.lastTranslateBackendForLangs = ""
                    root.availableLangTarget = []
                    executable.run(root.translateLangsCmd + " " + root.currentTranslateBackend)
                }
            }
            function syncLangCombo() {
                var target = root.currentLangTarget
                for (var j = 0; j < langModel.count; j++) {
                    if (langModel.get(j).value === target) {
                        langCombo.currentIndex = j
                        return
                    }
                }
            }
            Connections {
                target: root
                function onCurrentLangTargetChanged() {
                    langCombo.syncLangCombo()
                }
                function onAvailableLangTargetChanged() {
                    langModel.clear()
                    for (var i = 0; i < root.availableLangTarget.length; i++) {
                        var code = root.availableLangTarget[i]
                        langModel.append({ text: code, value: code })
                    }
                    langCombo.syncLangCombo()
                }
            }
            delegate: QQC2.ItemDelegate {
                width: parent ? parent.width : 0
                text: model.value === "---" ? "───" : model.text
                enabled: model.value !== "---" && model.value !== root.currentLangSource
                opacity: model.value === "---" ? 0.3 : (enabled ? 1.0 : 0.4)
            }
            onActivated: function(index) {
                if (index < 0 || index >= langModel.count) return
                var val = langModel.get(index).value
                if (val === "---" || val === root.currentLangSource) return
                root.currentLangTarget = val
                executable.run("bash -c 'conf=\"${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf\"; grep -q \"^DICTEE_LANG_TARGET=\" \"$conf\" && sed -i \"s|^DICTEE_LANG_TARGET=.*|DICTEE_LANG_TARGET=" + val + "|\" \"$conf\" || echo \"DICTEE_LANG_TARGET=" + val + "\" >> \"$conf\"'")
            }
            enabled: root.currentAsrBackend !== "canary"
            QQC2.ToolTip.text: root.currentTranslateBackend === "libretranslate"
                ? i18n("Target language — add languages in Configure Dictée (LibreTranslate)")
                : i18n("Target language for translation")

            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }
    }

    // Actions + Preview
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        ThemedButton {
            text: i18n("Transcribe file")
            icon.name: "document-open"
            flat: true
            onClicked: fullRep.actionRequested("transcribe-file")
            QQC2.ToolTip.text: i18n("Open an audio file for transcription")

            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        ThemedButton {
            text: i18n("Post-processing...")
            icon.name: "document-edit"
            flat: true
            onClicked: fullRep.actionRequested("postprocess")
            QQC2.ToolTip.text: i18n("Configure post-processing rules (regex, dictionary, continuation)")

            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        ThemedButton {
            text: i18n("Configure Dictée")
            icon.name: "configure"
            flat: root.dicteeConfigured
            onClicked: fullRep.actionRequested("setup")
            QQC2.ToolTip.text: i18n("Open dictee-setup to configure ASR, translation, shortcuts")

            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500

            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.color: "#e90"
                border.width: 2
                radius: 4
                visible: !root.dicteeConfigured
            }
        }

        Item { Layout.fillWidth: true }

        PlasmaComponents.ToolButton {
            icon.name: "edit-reset"
            display: PlasmaComponents.AbstractButton.IconOnly
            Kirigami.Theme.inherit: false
            Kirigami.Theme.textColor: Kirigami.Theme.negativeTextColor
            onClicked: fullRep.actionRequested("reset")
            PlasmaComponents.ToolTip { text: i18n("Reset everything — stop all processes, restart daemon") }
        }

        PlasmaComponents.ToolButton {
            icon.name: Plasmoid.configuration.previewMode ? "view-visible" : "view-hidden"
            display: PlasmaComponents.AbstractButton.IconOnly
            checkable: true
            checked: Plasmoid.configuration.previewMode
            onToggled: Plasmoid.configuration.previewMode = checked
            PlasmaComponents.ToolTip { text: i18n("Live microphone animation preview") }
        }
    }



    }  // end ColumnLayout

    // Séparateur vertical avant le slider micro
    Kirigami.Separator {
        Layout.fillHeight: false
        Layout.preferredHeight: leftColumn.implicitHeight
        Layout.maximumHeight: leftColumn.implicitHeight
        Layout.alignment: Qt.AlignTop
    }

    // Vertical microphone volume slider + level meter (right side)
    ColumnLayout {
        Layout.fillHeight: false
        Layout.preferredHeight: leftColumn.implicitHeight
        Layout.maximumHeight: leftColumn.implicitHeight
        Layout.alignment: Qt.AlignTop
        Layout.preferredWidth: 50
        spacing: Kirigami.Units.smallSpacing

        // Top spacer — pushes mic icon down so it sits just above the slider,
        // which itself starts at the audio source combo row.
        Item {
            Layout.preferredHeight: Kirigami.Units.gridUnit * 2
        }

        Kirigami.Icon {
            source: root.micMuted ? "microphone-sensitivity-muted" : "audio-input-microphone"
            color: root.micMuted ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Kirigami.Units.iconSizes.small
            Layout.alignment: Qt.AlignHCenter
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

        // Vertical slider with integrated peak meter overlay.
        // Inspired by plasma-pa's VolumeSlider: the slider groove is drawn
        // manually so a second highlighted bar, driven by root.audioLevel,
        // can be superimposed on top of the volume fill.
        QQC2.Slider {
            id: micSlider
            Layout.fillHeight: true
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Kirigami.Units.gridUnit
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

            // Draggable knob — round handle over the vertical groove
            handle: Rectangle {
                x: micSlider.leftPadding + (micSlider.availableWidth - width) / 2
                y: micSlider.topPadding + (micSlider.availableHeight - height) * (1 - micSlider.position)
                width: Kirigami.Units.gridUnit * 0.9
                height: width
                radius: width / 2
                color: micSlider.pressed
                    ? Kirigami.Theme.highlightColor
                    : Kirigami.Theme.alternateBackgroundColor
                border.color: Kirigami.Theme.highlightColor
                border.width: 2
                z: 10
            }

            background: Rectangle {
                x: micSlider.leftPadding + (micSlider.availableWidth - width) / 2
                y: micSlider.topPadding
                width: 8
                height: micSlider.availableHeight
                radius: 4
                color: Kirigami.Theme.backgroundColor
                border.color: Kirigami.Theme.disabledTextColor
                border.width: 1
                clip: true

                // Volume fill — shows the slider's current value
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 2
                    height: Math.max(0, (parent.height - 2) * micSlider.position)
                    radius: 2
                    color: Kirigami.Theme.highlightColor
                    opacity: 0.35
                }

                // Peak meter — shows the live audio level
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 2
                    property real level: root.audioLevel || 0.0
                    height: Math.max(0, (parent.height - 2) * Math.min(1.0, level * 1.5))
                    radius: 2
                    color: level > 0.8 ? Kirigami.Theme.negativeTextColor
                         : level > 0.4 ? Kirigami.Theme.neutralTextColor
                         : Kirigami.Theme.positiveTextColor
                    Behavior on height {
                        NumberAnimation { duration: 50 }
                    }
                }
            }
        }
    }
}
