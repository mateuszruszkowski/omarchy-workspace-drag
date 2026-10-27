# Workspace drag for rogo

Hold **Super+Alt+left mouse button** over a normal window. The source display shows
normal workspaces arranged in separate circles around each monitor label.
Existing workspaces and individually configured empty workspaces are included.
When Omarchy provides its per-monitor block map, workspace cards use local slot
numbers: for example, Hyprland workspace 13 is shown as workspace 3 on the monitor
that owns block 11–20. Real workspace names still identify previews and drop
targets. If two real targets share a displayed number on one monitor, their
labels include the internal ID to distinguish them. Existing guest workspaces remain on their actual monitor. Empty targets
are declared by monitor, persistent or default rules; appearance-only rules do
not create extra cards. Without a usable block mapping, labels retain real names.
The dimmed desktop remains visible behind the overview. A small dragged-window
preview follows the pointer. The virtual STUDIO-VIRTUAL output is hidden by default;
its group is included when it is the source display. Move to a preview and release the mouse
button to move that window there. The window leaves fullscreen, becomes tiled,
and moves silently. The active source workspace stays visible. The pointer returns
to its starting position so the next window can be moved immediately.

The hovered preview enlarges. Hit testing always uses its original slot, including
on mixed-scale and rotated displays. Release outside a slot, release on the source
workspace, press Escape, or hold longer than 25 seconds to cancel. Very short holds
under 120 ms cancel. Press and release carry a sequence token so an early release
cannot accidentally start a stuck drag.

## Install and remove

Requires Hyprland with Lua dispatchers, Quickshell 0.3.2,
Python 3. No additional packages or compiled Hyprland plugins are needed.

```bash
python3 ./install.py
omarchy plugin enable local.workspace-drag --section centerBegin
hyprctl reload
hyprctl configerrors
~/.local/share/workspace-drag/workspace-drag start
```

The installer copies the extension into `~/.local/share/workspace-drag`, appends
one marked include to `~/.config/hypr/bindings.lua`, and one marked autostart call
to `~/.config/hypr/autostart.lua`. It creates only its own
`~/.config/hypr/workspace-drag.lua` module. Every run saves affected files and any
previous extension under `~/.local/state/workspace-drag/backups/`. It does not reload
Hyprland, start processes, or change monitor configuration. Existing extension
`config.json` and `shortcut.conf` are preserved on update. An older shipped
`bindings.lua` is migrated after saving its original custom shortcut. Unknown
custom Lua is refused before installation changes any files. A launcher named
**Workspace Drag — Ustawienia** is installed in the application menu.

```bash
~/.local/share/workspace-drag/workspace-drag stop
python3 ./install.py --uninstall
hyprctl reload
hyprctl configerrors
```

Uninstall removes only the marked includes and the extension's own paths, keeping
the rest of user configuration and all backups. A modified include module is kept.
Do not restore entire backed-up binding files over concurrent edits. Restore only
the extension's changes when necessary.

## Settings

Open **Workspace Drag — Ustawienia** in the application menu, or run:

```bash
~/.local/share/workspace-drag/workspace-drag settings
```

The grid icon immediately to the left of the clock also opens settings. Clicking
it while the panel is open focuses the existing window. The installer copies the
user-owned `local.workspace-drag` bar plugin; the enable command above places it
in `centerBegin` without changing the clock's center section. Other bar entries
and plugin files are preserved.

The Polish settings window provides Super, Alt, Ctrl and Shift checkboxes, a
left/right/middle mouse selector, a backdrop dimming slider and a choice between
window thumbnails and window titles. Two additional sliders control workspace
preview size (50–200%) and hover enlargement (100–135%). Size scales both
dimensions together, preserving custom card proportions. The overview still fits
the available display, so large settings may be constrained by screen space.
The shortcut summary updates while editing.
At least one modifier is required. **Domyślne** resets only the displayed draft.
**Zapisz i zastosuj** writes it; **Wczytaj ponownie** discards the draft and reads
the current saved settings. Closing the window discards unsaved edits.

**Podgląd** opens the actual workspace overview using the current dimming and
preview-mode, preview-size and hover-enlargement controls, including unsaved edits. It displays real windows without
grabbing one. **Zamknij podgląd** or Escape returns to the unchanged settings
draft. The configured timeout also closes it. Preview neither saves settings nor
moves windows, switches workspaces or restores the pointer. A running drag must
finish before preview can open.

A higher dimming percentage hides more of the desktop behind the overview.
Appearance changes take effect on the next drag. A shortcut change checks live
Hyprland bindings, then reloads and checks the compositor configuration. An
occupied shortcut is rejected without changing files. The existing Super+mouse
move/resize bindings are therefore preserved. The helper saves copies under
`~/.local/share/workspace-drag/settings-backups/`, writes files atomically, and
restores the previous files and reloads them if application fails. Errors stay
visible in the window.

The shortcut is plain data in `~/.local/share/workspace-drag/shortcut.conf`, for
example `SUPER + ALT + mouse:272`. Modifiers use the order SUPER, ALT, CTRL, SHIFT;
buttons are 272 (left), 273 (right) and 274 (middle). `bindings.lua` reads only this
allowlisted format and never evaluates the data as Lua. Keep manual shortcut
changes in this file, then reload Hyprland and check `hyprctl configerrors`.
The shortcut uses a normal press/release bind, without `mouse=true`, because
Hyprland's mouse dispatcher bindings cannot run shell actions.

Other settings remain in `~/.local/share/workspace-drag/config.json`. The panel
preserves fields it does not edit. They load at the next drag without restart.

| Setting | Default | Meaning |
| --- | --- | --- |
| `groupColumns` | 0 | Monitor circles per row. Zero chooses the largest fitting layout automatically. |
| `cardWidth`, `cardHeight` | 230, 150 | Logical card size before fitting the source display. |
| `cardScale` | 1.0 | Workspace preview size multiplier, 0.5–2.0, applied before fitting the source display. |
| `gap` | 24 | Space between slots. |
| `zoom` | 1.15 | Hover scale from 1.0 to 1.35. |
| `backgroundOpacity` | 0.72 | Dimmed theme backdrop opacity. The desktop remains visible underneath. |
| `previewMode` | `thumbnails` | Set to `titles` to show application window titles instead of captures. |
| `hiddenMonitors` | `["STUDIO-VIRTUAL"]` | Hide these monitor groups, except when one is the source. Set `[]` to show every output. |
| `timeoutSeconds` | 25 | Cancel a stuck hold. |
| `pollMilliseconds` | 35 | Cursor update interval during an active drag. |
| `restoreCursor` | true | Return to the source location after dropping or cancelling. |
| `defaultWorkspaces` | 1 through 10 | Fallback used only when no individual normal workspace rules exist. |

The dashboard uses Omarchy's current `colors.toml`, watches language changes, and
supports Polish and English. If no language file exists, it follows `LANG`. Rounded
corners follow `decoration:rounding` from Hyprland at drag start. All dynamic labels
are plain text. Workspace names are validated before use in dispatchers.

## Architecture and limits

`settings.qml` is a separate normal window; it does not change the click-through
overview. `settings.py` validates its JSON draft and applies changes without shell
interpolation. `bindings.lua` reads the chord and owns the unique press/release token. `shell.qml` is an
isolated resident Quickshell UI and exposes `workspaceDrag` IPC. `backend.py` owns
the state machine, source-window selection, card layout, final global cursor hit
test and address-selected Hyprland dispatch. Its state is idle or a `Dragging`
record. `end` commits a valid target; cancel, timeout and stale topology return to
idle. A 120 ms deferred pointer restoration lets the layer close first.

A shell plugin was considered but would put this experiment in Omarchy's main
shell process. An external screenshot tool was considered but would need subprocess
capture and risks recursive monitor thumbnails. This standalone process uses native
`ScreencopyView` with each Hyprland toplevel's Wayland handle. No whole-output
capture, network access, or screenshot cache is used. Window titles stay in the
local UI pipe, are rendered as plain text in titles mode, and are never logged.
Only pointer deltas are sent each frame; static models are published once per drag.
The click-through overlay does not depend on receiving a mouse release and never
takes keyboard focus. Native Lua bindings supply release and guarded Escape.
Taking exclusive or on-demand layer keyboard focus would clear Hyprland
mouse-button state and lose the release event. Slots remain fixed while hovered
cards enlarge. Circle placement reserves room for enlarged cards and center labels
and packs groups into an adaptive grid on the source output.

Captures of inactive workspaces depend on the compositor and application continuing
to supply buffers. If unavailable, the miniature shows the application class. A
workspace with no monitor rule is assigned to the source display for empty-target
planning. Monitor description rules are supported. Dynamic workspace selectors
such as `w[1-10]` are not expanded. All existing normal workspaces are still shown.
Special workspaces are excluded. Named normal workspaces, including those with
negative Hyprland IDs, are supported. The overlay is shown only on the source
display, so every visible monitor group can be reached without crossing outputs.

## Diagnostics and verification

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
~/.local/share/workspace-drag/workspace-drag status
~/.local/share/workspace-drag/workspace-drag cancel
~/.local/share/workspace-drag/workspace-drag demo
qs log --path ~/.local/share/workspace-drag/shell.qml --tail 40
```

`demo` creates synthetic targets and illustrative windows without moving any
real window. Its backdrop is solid so a screenshot does not expose the desktop. It still follows the real pointer to exercise hover zoom. The timeout or
`cancel` closes it. `begin TOKEN` and `end TOKEN` are also available for controlled
integration testing. `status` contains state, monitor and hovered workspace, without
window titles. Unit tests fake the IPC boundary and cover fresh release coordinates,
silent address-targeted movement, early release, cancel/timeout, source close,
monitor unplug and scale changes, empty configured targets, mixed-scale hit testing,
pointer restoration, demo safety, non-overlapping two/three-monitor circle layouts,
and virtual-output filtering. Real compositor acceptance, visual checks and
remaining limits are recorded in [VERIFICATION.md](VERIFICATION.md).
