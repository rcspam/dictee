import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

// Button that follows Kirigami.Theme (adapts to Breeze Light/Dark) with
// visible hover/pressed feedback in both themes. Replaces PlasmaComponents.Button
// inside the plasmoid popup (PlasmaComponents buttons are styled for the panel,
// so they appear dark on a light popup background).
QQC2.Button {
    id: control

    leftPadding: Kirigami.Units.smallSpacing * 2
    rightPadding: Kirigami.Units.smallSpacing * 2
    topPadding: Kirigami.Units.smallSpacing
    bottomPadding: Kirigami.Units.smallSpacing

    background: Rectangle {
        radius: 3
        readonly property color _hl: Kirigami.Theme.highlightColor
        color: control.pressed
                ? Qt.rgba(_hl.r, _hl.g, _hl.b, 0.55)
             : control.hovered
                ? Qt.rgba(_hl.r, _hl.g, _hl.b, 0.22)
             : control.flat
                ? "transparent"
                : Kirigami.Theme.alternateBackgroundColor
        border.width: control.flat ? 0 : 1
        border.color: control.hovered
            ? Kirigami.Theme.highlightColor
            : Kirigami.Theme.disabledTextColor
        opacity: control.enabled ? 1.0 : 0.55
    }

    // Explicit contentItem so icon + text are always rendered regardless of
    // the active QQC2 style (Plasma's default style can drop them).
    // Respects control.display (IconOnly / TextOnly / TextBesideIcon / TextUnderIcon).
    contentItem: RowLayout {
        spacing: Kirigami.Units.smallSpacing
        Kirigami.Icon {
            source: control.icon.name
            visible: source !== "" && control.display !== QQC2.AbstractButton.TextOnly
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Kirigami.Units.iconSizes.small
            color: Kirigami.Theme.textColor
        }
        QQC2.Label {
            text: control.text
            visible: text !== "" && control.display !== QQC2.AbstractButton.IconOnly
            color: Kirigami.Theme.textColor
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
    }
}
