import QtQuick
import QtQuick.Window
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
    // ASR provider effectif depuis /dev/shm/.dictee_provider (via main.qml).
    // 'cuda' = vert | 'cpu' = rouge (panne) | 'cpu-forced'/'cpu-only'/'cpu-int8' = bleu.
    property string provider: ""
    // Singleton flag from main.qml — when false, this widget is a duplicate
    // instance; we overlay a passive banner and disable all actions to avoid
    // racing with the active master instance.
    property bool isActive: true
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

    // Passive-instance overlay — covers the popup when this widget is not
    // the active master. Swallows clicks, displays explanation + "Take over"
    // escape hatch.
    Rectangle {
        parent: fullRep
        anchors.fill: fullRep
        anchors.margins: -Kirigami.Units.largeSpacing
        z: 10000
        visible: !fullRep.isActive
        color: Kirigami.Theme.backgroundColor
        opacity: 0.98
        radius: Kirigami.Units.largeSpacing * 1.5

        // Swallow any click/scroll — prevents interaction with the disabled
        // widgets behind and keeps focus where the user can read the banner.
        MouseArea {
            anchors.fill: parent
            onClicked: {}
            onWheel: function(wheel) { wheel.accepted = true }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing * 2
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Icon {
                source: "dialog-warning"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: Kirigami.Units.iconSizes.huge
                Layout.preferredHeight: Kirigami.Units.iconSizes.huge
                color: Kirigami.Theme.neutralTextColor
            }

            PlasmaComponents.Label {
                text: i18n("Another Dictée widget is active")
                Layout.alignment: Qt.AlignHCenter
                font.bold: true
                font.pointSize: Kirigami.Theme.defaultFont.pointSize + 2
                color: Kirigami.Theme.neutralTextColor
            }

            PlasmaComponents.Label {
                text: i18n("Two instances on the same panel or desktop cause conflicts — duplicated daemon start/stop calls and races on the backend config. This widget is passive until the other is removed.")
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                color: Kirigami.Theme.textColor
            }

            PlasmaComponents.Label {
                text: i18n("Right-click this widget in the panel, then choose \"Remove\" to clean up.")
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                color: Kirigami.Theme.disabledTextColor
                font.italic: true
            }

            Item { Layout.fillHeight: true }

            ThemedButton {
                Layout.alignment: Qt.AlignHCenter
                text: i18n("Take over anyway")
                icon.name: "edit-copy"
                onClicked: fullRep.actionRequested("take-over")
                PlasmaComponents.ToolTip {
                    text: i18n("Force this widget to become active. The other instance will become passive at the next refresh (3 s).")
                }
            }
        }
    }

    // Close any open ComboBox dropdown when the plasmoid window becomes
    // inactive (panel icon clicked, focus lost…). Otherwise the dropdown
    // is a separate Popup that outlives a plasmoid collapse and reappears
    // when the user reopens the plasmoid. Watching fullRep.visible is not
    // enough — the Item stays visible when the window is hidden; Window.active
    // is the signal that actually fires on panel collapse.
    function _closeAllDropdowns() {
        if (audioSourceCombo.popup.visible) audioSourceCombo.popup.close()
        if (asrCombo.popup.visible) asrCombo.popup.close()
        if (transCombo.popup.visible) transCombo.popup.close()
        if (langCombo.popup.visible) langCombo.popup.close()
    }
    property bool windowActive: Window.active
    onWindowActiveChanged: if (!windowActive) _closeAllDropdowns()
    Connections {
        target: Plasmoid
        function onExpandedChanged() {
            if (!Plasmoid.expanded) fullRep._closeAllDropdowns()
        }
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
            // hideOnWindowDeactivate is a binding in main.qml — only update
            // the persisted setting; the binding picks up the change.
            onToggled: Plasmoid.configuration.pinPopup = checked
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

                // Provider badge (point) : vert=cuda | rouge=cpu (panne) | bleu=CPU voulu.
                // Caché quand le daemon est offline ou provider inconnu.
                Rectangle {
                    visible: fullRep.provider !== ""
                             && fullRep.state !== "offline"
                    width: Kirigami.Units.smallSpacing * 3
                    height: width
                    radius: width / 2
                    color: fullRep.provider === "cuda" ? "#27ae60"
                         : fullRep.provider === "cpu"  ? "#c0392b"
                         : "#3498db"
                    border.color: fullRep.provider === "cuda" ? "#1e8449"
                                : fullRep.provider === "cpu"  ? "#922b21"
                                : "#21618c"
                    border.width: 1
                    PlasmaComponents.ToolTip {
                        text: fullRep.provider === "cuda"
                            ? i18n("Daemon running on GPU")
                            : fullRep.provider === "cpu"
                            ? i18n("GPU unavailable — running on CPU")
                            : i18n("Daemon running on CPU")
                    }
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

        Item {
            Layout.fillWidth: true
            Layout.preferredWidth: 0
            implicitHeight: btnMeeting.implicitHeight

            ThemedButton {
                id: btnMeeting
                anchors.fill: parent
                text: i18n("Meeting")
                icon.name: "meeting-attending"
                enabled: fullRep.state !== "meeting-ui-open" && fullRep.state !== "meeting-recording"
                onClicked: fullRep.actionRequested("meeting-live")
                leftPadding: meetingDot.visible ? 20 : undefined
                tooltipText: fullRep.state === "meeting-ui-open"
                    ? i18n("Meeting window is open")
                    : fullRep.state === "meeting-recording"
                    ? i18n("Meeting recording in progress")
                    : i18n("Open live meeting capture (record, then send to diarization)")
            }

            Rectangle {
                id: meetingDot
                property bool active: fullRep.state === "meeting-recording"
                visible: active
                width: 10; height: 10; radius: 5
                color: "#ff0000"
                z: 100
                anchors.verticalCenter: parent.verticalCenter
                x: 6
                onActiveChanged: {
                    if (active) { meetingDotAnim.start() }
                    else { meetingDotAnim.stop(); opacity = 1.0 }
                }
            }
            SequentialAnimation {
                id: meetingDotAnim
                loops: Animation.Infinite
                NumberAnimation { target: meetingDot; property: "opacity"; to: 0.2; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { target: meetingDot; property: "opacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            }
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
            // Parakeet has two variants visible as separate entries (cosmetic
            // split — same backend, different quantization). When the user
            // picks one, we switch backend AND quantization.
            // Labels are built dynamically with i18n() (not stored as plain
            // strings in the ListModel) so they translate properly.
            model: ListModel {
                id: asrModel
                Component.onCompleted: {
                    append({ "text": i18n("Parakeet (precise)"), "value": "parakeet", "quant": "fp32" })
                    append({ "text": i18n("Parakeet (fast)"),    "value": "parakeet", "quant": "int8" })
                    append({ "text": "Canary",   "value": "canary",  "quant": "" })
                    append({ "text": "Vosk",     "value": "vosk",    "quant": "" })
                    append({ "text": "Whisper",  "value": "whisper", "quant": "" })
                    append({ "text": "Whisper-Rust", "value": "whisper-rust", "quant": "" })
                }
            }
            textRole: "text"
            function syncIndex() {
                // Match both backend AND (for Parakeet) the active quantization
                for (var i = 0; i < asrModel.count; i++) {
                    var item = asrModel.get(i)
                    if (item.value !== root.currentAsrBackend) continue
                    if (item.value === "parakeet") {
                        if (item.quant === root.currentParakeetQuant) {
                            currentIndex = i
                            return
                        }
                    } else {
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
                function onCurrentParakeetQuantChanged() { asrCombo.syncIndex() }
            }
            delegate: QQC2.ItemDelegate {
                width: parent ? parent.width : 0
                text: model.text
                enabled: root.installedAsr.indexOf(model.value) !== -1
                opacity: enabled ? 1.0 : 0.4
            }
            onActivated: function(index) {
                var item = asrModel.get(index)
                if (root.installedAsr.indexOf(item.value) === -1) {
                    syncIndex()
                    return
                }
                // Switch backend + quant. Pour éviter double load du daemon
                // (asr restart avec l'ancien quant/FORCE_CPU, puis quant
                // re-restart avec les bonnes valeurs), on chaîne `quant` AVANT
                // `asr` quand les 2 sont nécessaires.
                // - quant AVANT asr : set_conf int8+FORCE_CPU=1, pas de
                //   restart car Whisper actif (wrapper skip si backend != parakeet)
                // - puis asr parakeet : démarre direct avec int8+FORCE_CPU=1 → CPU
                var needQuant = (item.value === "parakeet" && item.quant !== "" &&
                                 item.quant !== root.currentParakeetQuant)
                var needAsr = (item.value !== root.currentAsrBackend)
                if (needQuant && needAsr) {
                    // Plasma5Support.DataSource.run() ne passe PAS par un shell
                    // automatique pour `&&` — wrap dans `bash -c` pour exécution
                    // séquentielle. Sinon les 2 commandes tournent en parallèle
                    // et le daemon peut démarrer avec un état conf transitoire
                    // incohérent → spike VRAM (vérifié 2026-05-21).
                    executable.run("bash -c 'dictee-switch-backend quant " +
                                   item.quant + " && dictee-switch-backend asr " +
                                   item.value + "'")
                } else if (needAsr) {
                    executable.run("dictee-switch-backend asr " + item.value)
                } else if (needQuant) {
                    executable.run("dictee-switch-backend quant " + item.quant)
                }
            }
            Layout.preferredWidth: Kirigami.Units.gridUnit * 10
        }

        QQC2.CheckBox {
            id: chkLlm
            text: i18n("LLM")
            checked: root.llmPostprocessEnabled
            onToggled: executable.run("dictee-switch-backend llm " + (checked ? "true" : "false"))
            PlasmaComponents.ToolTip {
                text: i18n("Enable LLM post-processing (grammar and spell correction via local Ollama model).")
            }
            // Restore the binding after a user click may have broken it, so
            // changes from the tray / CLI / dictee-setup keep propagating.
            Connections {
                target: root
                function onLlmPostprocessEnabledChanged() {
                    if (chkLlm.checked !== root.llmPostprocessEnabled) {
                        chkLlm.checked = root.llmPostprocessEnabled
                    }
                }
            }
        }

        QQC2.CheckBox {
            id: chkAudioContext
            text: i18n("Context")
            checked: root.audioContextEnabled
            onToggled: executable.run("dictee-switch-backend context " + (checked ? "true" : "false"))
            PlasmaComponents.ToolTip {
                text: i18n("Accumulate audio from previous dictations to improve recognition of short or technical words.")
            }
            Connections {
                target: root
                function onAudioContextEnabledChanged() {
                    if (chkAudioContext.checked !== root.audioContextEnabled) {
                        chkAudioContext.checked = root.audioContextEnabled
                    }
                }
            }
        }

        QQC2.CheckBox {
            id: chkShortText
            text: i18n("Short")
            checked: root.shortTextEnabled
            onToggled: executable.run("dictee-switch-backend short_text " + (checked ? "true" : "false"))
            PlasmaComponents.ToolTip {
                text: i18n("Enable short-text fix on both normal and translation pipelines.")
            }
            Connections {
                target: root
                function onShortTextEnabledChanged() {
                    if (chkShortText.checked !== root.shortTextEnabled) {
                        chkShortText.checked = root.shortTextEnabled
                    }
                }
            }
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
            // Keep combo compact; force dropdown popup wider than the combo
            // so long codes (pt-BR, zh-CN…) fit without eliding.
            Layout.preferredWidth: Kirigami.Units.gridUnit * 3.5
            Component.onCompleted: popup.width = Kirigami.Units.gridUnit * 6
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

    // Actions + Preview — also hosts the GPU/CPU toggle in-line, so the
    // toggle sits on the same row as the action buttons (compact layout).
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        ThemedButton {
            text: i18n("Transcribe file")
            icon.name: "document-open"
            flat: true
            onClicked: fullRep.actionRequested("transcribe-file")
            tooltipText: i18n("Open an audio file for transcription")
        }

        Item { Layout.fillWidth: true }

        // GPU / CPU toggle (visible once dictee is configured). Both side
        // labels stay at full opacity — the slider position alone signals
        // the active mode.
        PlasmaComponents.Label {
            text: "GPU"
            Layout.alignment: Qt.AlignVCenter
            visible: fullRep.dicteeConfigured
        }

        QQC2.Switch {
            id: forceCpuSwitch
            visible: fullRep.dicteeConfigured
            // Disabled when the constraint locks the position (Canary/Vosk/INT8/no-GPU),
            // or during cooldown debounce, or when dictee is not configured.
            enabled: root.forceCpuSensitive && !cooldownTimer.running && fullRep.dicteeConfigured
            // CPU vs GPU n'est PAS un on/off — custom indicator avec couleur
            // unique dans les 2 positions. Plasma 6 ignore palette.highlight
            // et Kirigami.Theme.highlightColor pour le QQC2.Switch natif, on
            // redessine track + knob nous-mêmes.
            indicator: Rectangle {
                implicitWidth: Kirigami.Units.gridUnit * 2.2
                implicitHeight: Kirigami.Units.gridUnit * 1.1
                x: forceCpuSwitch.leftPadding
                y: forceCpuSwitch.height / 2 - height / 2
                radius: height / 2
                color: Kirigami.Theme.alternateBackgroundColor
                border.color: Kirigami.Theme.disabledTextColor
                border.width: 1
                Rectangle {
                    x: forceCpuSwitch.checked ? parent.width - width - 2 : 2
                    y: 2
                    width: parent.height - 4
                    height: width
                    radius: width / 2
                    color: Kirigami.Theme.textColor
                    Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.InOutQuad } }
                }
            }
            // Plasma 6 style ignore le visuel disabled sur QQC2.Switch → on
            // force opacité + overlay gris pour signaler explicitement le
            // verrou (Parakeet INT8 / Canary / Vosk / no-GPU). Sans ça, le
            // switch est silencieusement non-cliquable mais visuellement
            // normal — confusion utilisateur.
            opacity: enabled ? 1.0 : 0.4
            Rectangle {
                visible: !forceCpuSwitch.enabled
                anchors.fill: parent
                color: Kirigami.Theme.disabledTextColor
                opacity: 0.25
                radius: 4
                z: 10
                // Bloquer le clic pour cohérence avec enabled:false
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.NoButton }
            }
            // When constrained, show the forced position; otherwise follow conf.
            checked: !root.forceCpuSensitive
                ? (root.forceCpuForcedPosition === "cpu")
                : root.forceCpuActive
            property bool syncing: false  // skip onToggled when syncing from main.qml
            // Restaure le binding via Qt.binding() quand la contrainte change.
            // Sans ça, un assignment direct à `checked` (via onToggled user OU
            // les handlers ci-dessous) casse le binding QML initial : checked
            // ne suit plus l'évolution de forceCpuConstraint. Bug observé
            // 2026-05-21 : passer à Parakeet INT8 grisait le switch mais le
            // laissait en position GPU au lieu de CPU.
            function _rebindChecked() {
                forceCpuSwitch.syncing = true
                forceCpuSwitch.checked = Qt.binding(function() {
                    return !root.forceCpuSensitive
                        ? (root.forceCpuForcedPosition === "cpu")
                        : root.forceCpuActive
                })
                forceCpuSwitch.syncing = false
            }
            Connections {
                target: root
                function onForceCpuActiveChanged()         { forceCpuSwitch._rebindChecked() }
                function onForceCpuSensitiveChanged()      { forceCpuSwitch._rebindChecked() }
                function onForceCpuForcedPositionChanged() { forceCpuSwitch._rebindChecked() }
            }
            // Debounce: visually disable the toggle for 2 s after each user
            // click. The flock in dictee-switch-backend serialises any
            // concurrent calls anyway (defence-in-depth), this is just to
            // prevent visual flicker from rapid taps.
            Timer {
                id: cooldownTimer
                interval: 2000
                repeat: false
            }
            onToggled: {
                if (syncing) return
                if (!root.forceCpuSensitive) return  // constrained — ignore spurious toggles
                executable.run("dictee-switch-backend force_cpu " + (checked ? "1" : "0"))
                cooldownTimer.restart()
            }
            // Short tooltip — when constrained, return the constraint reason;
            // otherwise the same 6 cases as the tray's _force_cpu_warning.
            function _forceCpuWarning() {
                if (!root.forceCpuSensitive) {
                    return root.forceCpuConstrainedTooltip
                }
                var vram = root.gpuVramGb
                if (forceCpuSwitch.checked) {
                    if (vram >= 4)
                        return i18n("Force CPU (loses GPU acceleration)")
                    if (vram > 0)
                        return i18n("Force CPU")
                    return i18n("Force CPU (no GPU anyway)")
                }
                if (vram >= 4)
                    return i18n("GPU active")
                if (vram > 0)
                    return i18n("GPU active (low VRAM)")
                return i18n("No GPU detected")
            }
            QQC2.ToolTip.text: _forceCpuWarning()
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: 500
        }

        PlasmaComponents.Label {
            text: "CPU"
            Layout.alignment: Qt.AlignVCenter
            visible: fullRep.dicteeConfigured
        }

        Item { Layout.preferredWidth: Kirigami.Units.largeSpacing; visible: fullRep.dicteeConfigured }

        ThemedButton {
            text: i18n("Configure Dictée")
            icon.name: "configure"
            flat: root.dicteeConfigured
            onClicked: fullRep.actionRequested("setup")
            tooltipText: i18n("Open dictee-setup to configure ASR, translation, shortcuts")

            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.color: "#e90"
                border.width: 2
                radius: 4
                visible: !root.dicteeConfigured
            }
        }

        PlasmaComponents.ToolButton {
            icon.name: "view-list-text"
            display: PlasmaComponents.AbstractButton.IconOnly
            onClicked: fullRep.actionRequested("cheatsheet")
            PlasmaComponents.ToolTip { text: i18n("Toggle voice commands cheatsheet") }
        }

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
