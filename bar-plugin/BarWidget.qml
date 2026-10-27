import QtQuick
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "local.workspace-drag"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "\uf009"
        slotSize: Style.bar.statusSlot
        tooltipText: strings.t("settings")
        onPressed: function(mouseButton) {
            if (mouseButton === Qt.LeftButton)
                Util.execArgv([Quickshell.env("HOME") + "/.local/share/workspace-drag/workspace-drag", "settings"])
        }
    }
}
