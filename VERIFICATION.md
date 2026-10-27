# Verification on rogo, 2026-10-27

Tested on the running Hyprland 0.56.2 compositor with Quickshell 0.3.2,
eDP-1 at scale 1.6 and DP-6 at scale 1. The third, virtual output is
excluded from the overview by the default setting.

## Automated checks

- 19 Python behavior tests pass. They cover logical coordinates, radial card
  separation, named workspaces with negative IDs and Unicode names, stale
  targets, delayed begin/release/cancel, and preserving source identity.
- `bash -n workspace-drag` and `luac -p bindings.lua` pass.
- The installer was exercised with a temporary HOME. Repeat installation keeps
  one include, preserves unrelated edits and existing settings, and refuses a
  conflicting module. Uninstall preserves unrelated configuration.
- The installed QML loads. `hyprctl reload` succeeds and `hyprctl configerrors`
  is empty.
- Independent Sol review approved the functional changes after corrections.

## Real desktop checks

A temporary Foot window and a private uinput device exercised the real compositor
bindings. The user provided a quiet input interval for these checks.

- Super+Alt+left press opens the overview and records the exact test-window
  address. Moving onto workspace 5 highlights and enlarges its card.
- Release moves that window from workspace 3 on eDP-1 to workspace 5 on DP-6,
  tiled and without fullscreen. Every monitor keeps its active workspace;
  every other window keeps its workspace. The cursor returns to its origin.
- Releasing Alt and Super before the mouse button also completes the move.
  A fullscreen test window becomes tiled at the destination.
- Escape while the chord is held cancels without moving the test window.
- Ordinary left-click does not open the overview. The existing Super+mouse
  binding is retained unchanged.
- Live screenshots confirm two monitor circles, monitor labels, translucent
  dimming, workspace contents and hover highlighting. `ghostReady: true`
  confirms a compositor frame in the dragged-window miniature; the frame was
  also inspected visually.
- Both `thumbnails` and `titles` modes were rendered and inspected. Settings
  were restored to thumbnails with opacity 0.72 and cursor restoration enabled.

The test window, probe process and private input daemon were closed. Captures
containing the real desktop stayed outside Git in the ephemeral runtime directory.

## Boundaries

The physical mouse was not the event source for automated acceptance; uinput
events traversed the running compositor and installed bindings. Reboot/login
persistence and physical monitor unplug were not exercised. Autostart is installed;
topology-change cancellation has unit coverage. A live preview can use the last
buffer supplied by an application that stops drawing while hidden.

Opening another keyboard-interactive layer, such as a launcher, during the hold
can cause Hyprland to discard the release event. Escape or the 25-second timeout
closes the overview. The overview itself never requests keyboard focus.

## Corrections established during verification

- Hyprland clears held mouse buttons when a keyboard-interactive layer maps.
  The overview uses `WlrKeyboardFocus.None` and guarded native Escape handling.
- Press and release coordinates are sampled inside their native callbacks, not
  after launching the IPC client. Cancellation carries the same gesture token.
- Quickshell toplevel addresses omit `0x`; Hyprland client addresses include it.
  Lookup normalizes both formats. This was verified with a no-window runtime probe.
- The persistent ghost retains its QML binding. An imperative signal handler
  had replaced that binding with null before a source window was selected.
- Native Lua cursor movement replaces the obsolete textual dispatcher syntax.

Relevant upstream interfaces: [Hyprland dispatchers](https://wiki.hypr.land/configuring/core/dispatchers/)
and [Quickshell ScreencopyView](https://quickshell.org/docs/v0.2.1/types/Quickshell.Wayland/ScreencopyView/).

## Graphical settings panel checks, 2026-10-27

The implementation lane ran these checks on the repository files and temporary
copies only. They do not establish live graphical acceptance of the new panel.

- All 33 Python behavior tests pass, including the 19 existing gesture tests.
  The 14 new tests cover validated settings and rejection of injected or invalid
  values, preservation of unknown JSON fields, live binding conflict preflight,
  rollback after a partial write or a Hyprland configuration error, and checked
  reloads. A Lua runtime test verifies allowlisted shortcut reading and fallback
  on invalid data.
- Temporary-HOME installer tests verify custom legacy shortcut migration,
  repeat-install preservation, early refusal of unknown custom Lua, owned
  desktop-launcher installation/removal and preservation of a modified launcher.
- `bash -n workspace-drag`, `luac -p bindings.lua` and Python compilation pass.
- Quickshell 0.3.2 loads `settings.qml` with Qt's offscreen backend. A synthetic
  temporary-copy round trip reads settings, saves opacity 0.63 and titles, then
  saves opacity 0.61 in the same panel process. Both writes persist and the UI
  reaches its saved state. There are no QML runtime errors; Qt prints its expected
  offscreen window-mask warning.
- Two further temporary-copy QML checks close the window during a deliberately
  slow save. A successful save persists before the process quits. A failed save
  reopens the window in the error state with no pending close request.

The integration lane installed the update on rogo and opened the desktop entry
with `gtk-launch workspace-drag-settings`.

- Real pointer and keyboard interaction selected Ctrl, dimming 55%, and titles.
  Clicking Save persisted those values. Hyprland reported the new press/release
  bindings with modifier mask 76; the normal Super move/resize bindings retained
  mask 64. `hyprctl configerrors` remained empty.
- Closing and reopening the panel displayed the saved values. Selecting the
  occupied Super+left shortcut displayed the conflict and left files unchanged.
- Defaults and Save restored Super+Alt, dimming 72%, and thumbnails. A JSON
  comparison with the pre-update backup confirmed every original configuration
  value was preserved after testing.
- Live screenshots verified readable theme colors, all controls and status
  messages at scale 1.6. Material properties belong to the content item so that
  child controls inherit the dark theme. The desktop entry passes
  `desktop-file-validate`. Independent final source review approved the fixes.

The earlier real drag checks above concern the overview before the panel was
added. This update exercised graphical settings and native binding reassignment;
it did not repeat cross-monitor drag acceptance or reboot the machine.

The panel uses Quickshell's documented [FloatingWindow](https://quickshell.org/docs/v0.3.2/types/Quickshell/FloatingWindow/)
and [Process](https://quickshell.org/docs/v0.3.2/types/Quickshell.Io/Process/)
interfaces. Close requests retain the save process until completion.

## Draft preview and bar icon checks, 2026-10-27

- All 47 Python tests pass. Preview tests cover real workspace data, empty
  desktops, invalid overrides, busy rejection, reload of saved config on the
  next drag, and no window or cursor dispatch after release/cancel/timeout.
- Isolated launcher checks cover ready, stopped, busy and readiness-timeout
  states. QML syntax checks pass with `/usr/lib/qt6/bin/qmllint --silent`.
  Native `omarchy plugin validate` accepts the bar plugin.
- The user granted a quiet input interval for live GUI acceptance. Clicking the
  grid icon to the left of the clock opened settings. Clicking it again focused
  the same window, with exactly one settings window present.
- Real GUI controls set an unsaved dimming value of 55%. The Preview button
  displayed real workspace cards, two monitor circles, visible desktop through
  the background, and actual window thumbnails. Switching the draft to titles
  displayed the actual application titles instead. No dragged-window ghost was
  present. Escape closed both previews and backend status returned to idle.
- The settings draft survived preview closure. Reload restored the saved
  settings. Config and shortcut files remained byte-identical to the pre-test
  copies. No Save operation was used for the preview tests.
- Omarchy shell configuration differs only by the new `local.workspace-drag`
  entry in `centerBegin`. The installer itself does not enable or reposition
  widgets. Installation and native enablement are distinct steps.
- Independent Sol source review approved the implementation. The matching
  installed code was tested; real-desktop captures remain outside Git.

The close button is implemented alongside Escape; the live quiet-interval checks
used Escape. This change did not repeat physical mouse drag or reboot tests.
Existing gestures retain a click-through layer without keyboard focus; preview
alone takes input until dismissed.

## Workspace size and hover controls — 2026-10-27

- Added preview size 50–200% and hover enlargement 100–135% to the settings
  draft, defaults, validation, persistence and unsaved Preview request.
- `cardScale` preserves existing custom card dimensions and aspect ratio.
  Fit-to-screen remains active and is explained next to the size control.
- Full local discovery: 52 tests pass. Coverage includes numeric rejection,
  persistence with custom dimensions, preview boundaries, resetting draft
  appearance on the next drag, sparse-layout scale and dense-layout fit at
  maximum hover enlargement. Python compilation, QML lint and diff checks pass.
- Installed on rogo with backup `20261027T235644.077460`; the resident process
  restarted and reported ready/idle. Installed sources match the reviewed diff.
  Existing config and shortcut remained byte-identical after installation.
- Independent Sol review approved the diff with no findings. Live slider and
  hover interaction has not yet been tested; awaiting an idle desktop interval.
