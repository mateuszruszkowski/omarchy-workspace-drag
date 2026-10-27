import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

ShellRoot {
    id: root
    property string phase: "loading"
    property string message: "Wczytywanie ustawień…"
    property var saved: null
    property bool closeRequested: false
    property string helper: Qt.resolvedUrl("settings.py").toString().replace(/^file:\/\//, "")
    property color background: "#171b24"
    property color foreground: "#e8ecf3"
    property color accent: "#8aadf4"
    readonly property bool busy: phase === "loading" || phase === "saving"
    readonly property string chord: [superKey.checked ? "Super" : "", altKey.checked ? "Alt" : "", ctrlKey.checked ? "Ctrl" : "", shiftKey.checked ? "Shift" : "", mouse.currentText].filter(x => x !== "").join(" + ")
    readonly property bool hasModifier: superKey.checked || altKey.checked || ctrlKey.checked || shiftKey.checked

    function colorValue(text, name, fallback) {
        const match = text.match(new RegExp("^\\s*" + name + "\\s*=\\s*[\"'](#[a-fA-F0-9]{6})[\"']", "m"))
        return match ? match[1] : fallback
    }
    function draft() {
        return {modifiers: [superKey.checked ? "SUPER" : "", altKey.checked ? "ALT" : "", ctrlKey.checked ? "CTRL" : "", shiftKey.checked ? "SHIFT" : ""].filter(x => x !== ""), mouseButton: ["left", "right", "middle"][mouse.currentIndex], backgroundOpacity: Math.round(dimming.value) / 100, previewMode: previews.currentIndex === 0 ? "thumbnails" : "titles"}
    }
    function populate(data) {
        superKey.checked = data.modifiers.indexOf("SUPER") >= 0
        altKey.checked = data.modifiers.indexOf("ALT") >= 0
        ctrlKey.checked = data.modifiers.indexOf("CTRL") >= 0
        shiftKey.checked = data.modifiers.indexOf("SHIFT") >= 0
        mouse.currentIndex = ["left", "right", "middle"].indexOf(data.mouseButton)
        dimming.value = Math.round(data.backgroundOpacity * 100)
        previews.currentIndex = data.previewMode === "thumbnails" ? 0 : 1
    }
    function edited() {
        if (saved !== null && !busy) { phase = "editing"; message = "Zmiany czekają na zapisanie." }
    }
    function receive(output, exitCode) {
        try {
            const result = JSON.parse(output)
            if (!result.ok || exitCode !== 0) throw new Error(result.error || "Nie udało się wykonać operacji.")
            const wasSaving = phase === "saving"
            saved = result.settings
            populate(saved)
            phase = wasSaving ? "saved" : "ready"
            if (closeRequested) { Qt.quit(); return }
            message = wasSaving ? "Zapisano. Wygląd zmieni się przy następnym przeciągnięciu. Skrót jest już aktywny." : "Ustawienia wczytane."
        } catch (error) {
            phase = "error"
            message = String(error.message || error)
            closeRequested = false
            window.visible = true
        }
    }
    FileView {
        path: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/omarchy/current/theme/colors.toml"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            root.background = root.colorValue(text(), "background", "#171b24")
            root.foreground = root.colorValue(text(), "foreground", "#e8ecf3")
            root.accent = root.colorValue(text(), "accent", "#8aadf4")
        }
    }
    Process {
        id: reader
        command: ["python3", root.helper, "read"]
        running: true
        stdout: StdioCollector { id: readOutput }
        onExited: (exitCode, exitStatus) => root.receive(readOutput.text, exitCode)
    }
    Process {
        id: writer
        command: ["python3", root.helper, "apply"]
        stdinEnabled: true
        onStarted: { write(JSON.stringify(root.draft())); stdinEnabled = false }
        stdout: StdioCollector { id: writeOutput }
        onExited: (exitCode, exitStatus) => root.receive(writeOutput.text, exitCode)
    }
    FloatingWindow {
        id: window
        title: "Workspace Drag — Ustawienia"
        visible: true
        implicitWidth: 640
        implicitHeight: 790
        minimumSize: Qt.size(560, 680)
        color: root.background
        onClosed: visible = false
        onVisibleChanged: {
            if (!visible) {
                if (root.phase === "saving") root.closeRequested = true
                else Qt.quit()
            }
        }
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 16
            Material.theme: Material.Dark
            Material.accent: root.accent
            Material.background: root.background
            Material.foreground: root.foreground
            Label { text: "Workspace Drag"; font.pixelSize: 27; font.bold: true }
            Label { text: "Skrót i wygląd przeglądu pulpitów"; color: root.foreground; opacity: 0.75 }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: 16
                    enabled: root.saved !== null && !root.busy
                    GroupBox {
                        title: "Skrót przeciągania"
                        Layout.fillWidth: true
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 10
                            RowLayout {
                                CheckBox { id: superKey; text: "Super"; onToggled: root.edited() }
                                CheckBox { id: altKey; text: "Alt"; onToggled: root.edited() }
                                CheckBox { id: ctrlKey; text: "Ctrl"; onToggled: root.edited() }
                                CheckBox { id: shiftKey; text: "Shift"; onToggled: root.edited() }
                            }
                            Label { text: "Przycisk myszy" }
                            ComboBox {
                                id: mouse
                                Layout.fillWidth: true
                                model: ["Lewy przycisk myszy", "Prawy przycisk myszy", "Środkowy przycisk myszy"]
                                Accessible.name: "Przycisk myszy skrótu"
                                onActivated: root.edited()
                            }
                            Label { text: root.chord; font.bold: true; color: root.accent; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label {
                                text: root.hasModifier ? "Przytrzymaj skrót nad oknem, wskaż pulpit i puść przycisk." : "Wybierz co najmniej jeden modyfikator."
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                                color: root.hasModifier ? root.foreground : "#ffb4ab"
                            }
                        }
                    }
                    GroupBox {
                        title: "Wygląd przeglądu"
                        Layout.fillWidth: true
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 10
                            Label { text: "Przyciemnienie tła: " + Math.round(dimming.value) + "%" }
                            Slider {
                                id: dimming
                                Layout.fillWidth: true
                                from: 10; to: 100; stepSize: 1; value: 72
                                Accessible.name: "Przyciemnienie tła w procentach"
                                onMoved: root.edited()
                            }
                            Label { text: "Mniej = bardziej przezroczyste tło. Więcej = ciemniejszy pulpit."; wrapMode: Text.WordWrap; Layout.fillWidth: true; opacity: 0.75 }
                            Label { text: "Zawartość podglądów" }
                            ComboBox {
                                id: previews
                                Layout.fillWidth: true
                                model: ["Miniatury okien", "Tytuły okien"]
                                Accessible.name: "Zawartość podglądów pulpitów"
                                onActivated: root.edited()
                            }
                        }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: statusText.implicitHeight + 24
                radius: 8
                color: root.phase === "error" ? "#432a2b" : "#263242"
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    BusyIndicator { running: root.busy; visible: running; implicitWidth: 26; implicitHeight: 26 }
                    Label {
                        id: statusText
                        text: root.message
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        color: root.phase === "error" ? "#ffb4ab" : root.foreground
                        Accessible.role: Accessible.AlertMessage
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Button { text: "Domyślne"; enabled: root.saved !== null && !root.busy; onClicked: { root.populate({modifiers: ["SUPER", "ALT"], mouseButton: "left", backgroundOpacity: 0.72, previewMode: "thumbnails"}); root.edited() } }
                Button { text: "Wczytaj ponownie"; enabled: !root.busy; onClicked: { root.phase = "loading"; root.message = "Wczytywanie ustawień…"; reader.running = true } }
                Item { Layout.fillWidth: true }
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button { text: "Zamknij"; enabled: !root.busy; onClicked: Qt.quit() }
                Button {
                    text: "Zapisz i zastosuj"
                    highlighted: true
                    enabled: root.saved !== null && !root.busy && root.hasModifier
                    onClicked: { root.phase = "saving"; root.message = "Zapisywanie i sprawdzanie konfiguracji…"; writer.stdinEnabled = true; writer.running = true }
                }
            }
        }
    }
}
