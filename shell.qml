import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland

ShellRoot {
    id: root
    property var dashboard: ({state: "idle", cards: [], groups: [], clients: []})
    property string hovered: ""
    property var pointer: ({localX: 0, localY: 0})
    property bool ready: false
    property string configHome: Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config"
    property string stateHome: Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state"
    property string language: Quickshell.env("LANG") || "en"
    property color background: "#171b24"
    property color foreground: "#e8ecf3"
    property color accent: "#8aadf4"
    readonly property bool active: dashboard.state === "dragging"
    readonly property bool polish: language.indexOf("pl") === 0

    function send(command, token, position) {
        if (backend.running && ready)
            backend.write(JSON.stringify({command: command, token: token || "manual", pointer: position ? JSON.parse(position) : null}) + "\n")
    }
    function receive(line) {
        try {
            const data = JSON.parse(line)
            if (data.state === "pointer") {
                hovered = data.hovered || ""
                pointer = data.pointer || pointer
            }
            else {
                dashboard = data
                hovered = data.hovered || ""
                pointer = data.pointer || pointer
                ready = true
            }
        } catch (error) { console.warn("Workspace drag received invalid state") }
    }
    function colorValue(text, name, fallback) {
        const match = text.match(new RegExp("^\\s*" + name + "\\s*=\\s*[\"'](#[a-fA-F0-9]{6})[\"']", "m"))
        return match ? match[1] : fallback
    }
    function monitorData(name) {
        const monitors = dashboard.monitors || []
        for (let i = 0; i < monitors.length; i++) if (monitors[i].name === name) return monitors[i]
        return {x: 0, y: 0, logicalWidth: 1920, logicalHeight: 1080}
    }
    function clientsFor(name) {
        return (dashboard.clients || []).filter(function(c) { return c.workspace.name === name })
    }
    function toplevel(address) {
        const wanted = String(address).replace(/^0x/, "").toLowerCase()
        const all = Hyprland.toplevels.values
        for (let i = 0; i < all.length; i++)
            if (String(all[i].address).replace(/^0x/, "").toLowerCase() === wanted) return all[i]
        return null
    }

    Process {
        id: backend
        command: ["python3", Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, "")]
        running: true
        stdinEnabled: true
        stdout: SplitParser { onRead: data => root.receive(data) }
        stderr: SplitParser { onRead: data => console.warn("Workspace drag backend diagnostic") }
        onExited: {
            root.dashboard = {state: "idle", cards: [], groups: [], clients: []}
            root.ready = false
            restart.restart()
        }
    }
    Timer { id: restart; interval: 1000; onTriggered: backend.running = true }
    IpcHandler {
        target: "workspaceDrag"
        function begin(token: string, position: string): void { root.send("begin", token, position) }
        function end(token: string, position: string): void { root.send("end", token, position) }
        function cancel(token: string): void { root.send("cancel", token) }
        function demo(): void { root.send("demo") }
        function status(): string { return JSON.stringify({ready: root.ready, state: root.dashboard.state, screen: root.dashboard.screen || "", hovered: root.hovered, source: root.dashboard.source || "", sourceWorkspace: root.dashboard.sourceWorkspace || "", previewMode: root.dashboard.previewMode || "", ghostReady: ghostCapture.hasContent, error: root.dashboard.error || ""}) }
    }
    FileView {
        id: theme
        path: root.stateHome + "/omarchy/current/theme/colors.toml"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            root.background = root.colorValue(text(), "background", "#171b24")
            root.foreground = root.colorValue(text(), "foreground", "#e8ecf3")
            root.accent = root.colorValue(text(), "accent", "#8aadf4")
        }
    }
    FileView {
        id: locale
        path: root.configHome + "/omarchy/language"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: root.language = text().trim() || Quickshell.env("LANG") || "en"
    }
    Timer { interval: 1500; running: true; repeat: true; onTriggered: theme.reload() }

    PanelWindow {
        id: panel
        screen: Quickshell.screens.find(function(s) { return s.name === root.dashboard.screen }) || Quickshell.screens[0]
        visible: root.active
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        anchors { top: true; bottom: true; left: true; right: true }
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "workspace-drag"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        mask: Region {}

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(root.background.r, root.background.g, root.background.b, root.dashboard.demo ? 1 : (root.dashboard.backgroundOpacity || .72))
            Text {
                textFormat: Text.PlainText
                x: 48; y: 26
                text: root.polish ? "Przenieś okno na pulpit" : "Move window to workspace"
                color: root.foreground
                font.pixelSize: 26; font.bold: true
            }
            Text {
                textFormat: Text.PlainText
                x: 48; y: 64
                text: root.dashboard.demo
                    ? (root.polish ? "Podgląd układu. Zamknie się automatycznie." : "Layout preview. Closes automatically.")
                    : (root.polish ? "Wskaż podgląd i puść przycisk. Esc anuluje." : "Point at a preview and release. Esc cancels.")
                color: root.foreground; opacity: 0.7
                font.pixelSize: 15
            }
            Text {
                textFormat: Text.PlainText
                anchors { right: parent.right; bottom: parent.bottom; margins: 24 }
                text: root.dashboard.demo ? "DEMO · " + (root.polish ? "Dane syntetyczne · Automatyczne zamknięcie" : "Synthetic data · Closes automatically") : (root.polish ? "Pulpit źródłowy " : "Source workspace ") + (root.dashboard.sourceWorkspace || "")
                color: root.foreground; opacity: 0.65; font.pixelSize: 13
            }
            Repeater {
                model: root.active ? root.dashboard.groups : []
                delegate: Item {
                    required property var modelData
                    x: modelData.center.x; y: modelData.center.y
                    Rectangle {
                        x: -parent.modelData.radius; y: -parent.modelData.radius
                        width: parent.modelData.radius * 2; height: width
                        radius: width / 2
                        color: "transparent"
                        border.width: 1
                        border.color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, .28)
                    }
                    Column {
                        x: -parent.modelData.labelWidth / 2
                        y: -parent.modelData.labelHeight / 2
                        width: parent.modelData.labelWidth
                        spacing: 5
                        Text {
                            textFormat: Text.PlainText
                            width: parent.width
                            text: "▣"
                            color: root.accent
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: Math.min(32, parent.parent.modelData.labelHeight * .35)
                        }
                        Text {
                            textFormat: Text.PlainText
                            width: parent.width
                            text: parent.parent.modelData.monitor
                            color: root.foreground
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: Math.min(17, Math.max(11, parent.width / 11))
                            font.bold: true
                        }
                        Text {
                            textFormat: Text.PlainText
                            width: parent.width
                            text: root.monitorData(parent.parent.modelData.monitor).model || "MONITOR"
                            color: root.foreground; opacity: .65
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight
                            font.pixelSize: 11
                        }
                    }
                }
            }
            Repeater {
                model: root.active ? root.dashboard.cards : []
                delegate: Rectangle {
                    id: card
                    required property var modelData
                    readonly property bool selected: root.hovered === modelData.name
                    readonly property var workspaceMonitor: root.monitorData(modelData.monitor)
                    x: modelData.x; y: modelData.y
                    width: modelData.width; height: modelData.height
                    z: selected ? 10 : 1
                    scale: selected ? root.dashboard.zoom : 1
                    radius: root.dashboard.rounding || 0
                    color: Qt.lighter(root.background, 1.3)
                    border.width: selected ? 3 : 1
                    border.color: selected ? root.accent : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, .24)
                    Behavior on scale { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
                    Text {
                        textFormat: Text.PlainText
                        x: 12; y: 9
                        width: parent.width - 24; elide: Text.ElideRight
                        text: (root.polish ? "Pulpit " : "Workspace ") + card.modelData.name + (root.dashboard.sourceWorkspace === card.modelData.name ? "  ●" : "")
                        color: root.foreground; font.pixelSize: 14; font.bold: true
                    }
                    Text {
                        textFormat: Text.PlainText
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 9 }
                        text: card.modelData.monitor
                        color: root.foreground; opacity: .65; font.pixelSize: 11
                    }
                    Item {
                        id: miniature
                        x: 9; y: 35
                        width: parent.width - 18; height: parent.height - 62
                        clip: true
                        Repeater {
                            model: root.dashboard.demo || root.dashboard.previewMode === "titles" ? [] : root.clientsFor(card.modelData.name)
                            delegate: Rectangle {
                                id: preview
                                required property var modelData
                                property var captureToplevel: root.toplevel(modelData.address)
                                readonly property real ratio: Math.min(miniature.width / card.workspaceMonitor.logicalWidth, miniature.height / card.workspaceMonitor.logicalHeight)
                                x: (modelData.at[0] - card.workspaceMonitor.x) * ratio
                                y: (modelData.at[1] - card.workspaceMonitor.y) * ratio
                                width: Math.max(16, modelData.size[0] * ratio)
                                height: Math.max(14, modelData.size[1] * ratio)
                                color: Qt.lighter(root.background, 1.8)
                                border.color: modelData.address === root.dashboard.source ? root.accent : root.foreground
                                border.width: modelData.address === root.dashboard.source ? 2 : 1
                                radius: Math.min(3, root.dashboard.rounding || 0)
                                ScreencopyView {
                                    id: capture
                                    anchors.fill: parent; anchors.margins: 2
                                    captureSource: preview.captureToplevel ? preview.captureToplevel.wayland : null
                                    live: root.active
                                    paintCursor: false
                                }
                                Text {
                                    textFormat: Text.PlainText
                                    anchors.centerIn: parent
                                    width: parent.width - 8; elide: Text.ElideRight
                                    horizontalAlignment: Text.AlignHCenter
                                    visible: !capture.hasContent
                                    text: preview.modelData.class || "□"
                                    color: root.foreground; font.pixelSize: 11
                                }
                            }
                        }
                        Column {
                            anchors.fill: parent
                            spacing: 5
                            visible: root.dashboard.previewMode === "titles"
                            Repeater {
                                model: root.dashboard.previewMode === "titles" ? root.clientsFor(card.modelData.name) : []
                                delegate: Text {
                                    required property var modelData
                                    textFormat: Text.PlainText
                                    width: miniature.width
                                    text: modelData.title || modelData.class || "□"
                                    color: modelData.address === root.dashboard.source ? root.accent : root.foreground
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                            }
                        }
                        Text {
                            textFormat: Text.PlainText
                            anchors.centerIn: parent
                            visible: root.clientsFor(card.modelData.name).length === 0 && !root.dashboard.demo
                            text: root.polish ? "Pusty pulpit" : "Empty workspace"
                            color: root.foreground; opacity: .35; font.pixelSize: 13
                        }
                        Repeater {
                            model: root.dashboard.demo && root.dashboard.previewMode !== "titles" ? 3 : 0
                            delegate: Rectangle {
                                required property int index
                                x: 8 + index * miniature.width * .26
                                y: 8 + (index % 2) * 20
                                width: miniature.width * .39; height: miniature.height * .68
                                radius: Math.min(5, root.dashboard.rounding || 0)
                                color: index === 1 ? Qt.darker(root.accent, 1.9) : Qt.lighter(root.background, 1.8)
                                border.color: root.accent
                                Text {
                                    textFormat: Text.PlainText
                                    anchors.centerIn: parent
                                    text: ["Terminal", "Browser", "Files"][parent.index]
                                    color: root.foreground; font.pixelSize: 11
                                }
                            }
                        }
                    }
                }
            }
            Rectangle {
                id: dragGhost
                property var sourceData: root.dashboard.sourceClient || ({})
                property var captureToplevel: root.toplevel(sourceData.address || "")
                x: Math.max(0, Math.min(root.pointer.localX + 22, panel.width - width - 8))
                y: Math.max(0, Math.min(root.pointer.localY + 22, panel.height - height - 8))
                width: 146
                height: 104
                z: 100
                opacity: .82
                color: root.background
                radius: root.dashboard.rounding || 0
                border.color: root.accent; border.width: 2
                ScreencopyView {
                    id: ghostCapture
                    anchors { fill: parent; margins: 4; bottomMargin: 25 }
                    captureSource: root.dashboard.previewMode !== "titles" && dragGhost.captureToplevel ? dragGhost.captureToplevel.wayland : null
                    live: root.active && root.dashboard.previewMode !== "titles"
                    paintCursor: false
                }
                Text {
                    textFormat: Text.PlainText
                    anchors { fill: parent; margins: 8; bottomMargin: 25 }
                    visible: !ghostCapture.hasContent
                    text: root.dashboard.previewMode === "titles" ? (dragGhost.sourceData.title || dragGhost.sourceData.class || "□") : (dragGhost.sourceData.class || "□")
                    color: root.foreground
                    wrapMode: Text.Wrap; elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: 12
                }
                Text {
                    textFormat: Text.PlainText
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 7 }
                    text: dragGhost.sourceData.class || "□"
                    color: root.foreground; elide: Text.ElideRight
                    font.pixelSize: 11
                }
            }
        }
    }
}
