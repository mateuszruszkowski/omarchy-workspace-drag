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
- Independent Sol review approved the diff with no findings.
- Live verification on 2026-10-28: GUI sliders set unsaved preview size 51%
  and 199%, with hover enlargement 135%. Preview showed visibly different card
  sizes at both values; hovering a card enlarged it and highlighted its border.
  Both previews closed with Escape. Config and shortcut stayed byte-identical.
  Settings were closed without saving the test values. Captures remain outside Git.
  The preview button was reachable by scrolling the settings panel.
  This run did not repeat the persisted-settings GUI save test.

## Per-monitor numbering — 2026-10-28

- Live Omarchy bar source and monitor-workspaces TSV confirm per-monitor blocks:
  eDP-1 owns block 0, DP-6 block 1, STUDIO-VIRTUAL block 2. Actual workspace 13
  on DP-6 is local slot 3. Appearance rules for 12/13 do not declare empty targets.
- Cards and source footer now separate display labels from dispatch identities.
  Real guest workspaces remain on their actual monitors. Colliding labels include
  both real IDs; regression tests cover guest 4 and own-block 14 on DP-6.
- Live preview showed two monitor circles, workspace 3 on DP-6 with the actual
  Parsec thumbnail, and no phantom workspace 12 on eDP-1. Preview closed to idle.
  Final installed backend rechecked the same mapping against live Hyprland IPC.
- Config and shortcut remained byte-identical; active workspaces stayed eDP-1=3,
  DP-6=13, STUDIO-VIRTUAL=21. ChatGPT and Parsec stayed on 3 and 13.
- Final installation backup: `20261028T002240.976719`. Installed source files
  match the reviewed repository files. Resident service reports ready/idle.
- 61 tests pass; independent Sol review approved the final collision fix.
  Python compilation and diff checks pass. QML has no errors; its 62 warnings
  are unchanged from the preceding revision. Graphify AST index updated.
- No physical drag, creation of workspace 14, or reboot was performed in this
  verification pass; routing to colliding targets is covered by IPC unit tests.

## Stable slots and monitor profile cleanup — 2026-10-28

- Omarchy block map is the authority for five base slots per connected mapped
  monitor. Existing extras remain available; misplaced base slots are disabled
  without duplicate cards. Fresh mapping and Lua guards protect each drop.
- 70 tests pass, including execution of generated Lua with absent/changed targets.
  Independent Sol review approved. QML exits 0 with no errors (63 style/type
  warnings, one more unqualified warning than the previous revision).
- Live test launched a disposable foot window on laptop workspace 3 and used the
  installed begin/end IPC to drop it onto absent ID 14, local slot 4 on DP-6.
  It arrived tiled on monitor 1/workspace 14. Active workspace IDs remained
  eDP-1=3, DP-6=13, virtual=21. The test window was closed afterward.
  This tests the running drop path, not physical mouse-button delivery.
- Live preview visibly showed local 1–5 around each physical monitor; installed
  backend snapshot independently returned exactly those ten cards.
- Removed old explicit 1–3/4–6 pins from user monitors.lua. Updated saved
  hyprmoncfg profile to enabled manual workspace planning without numbered rules,
  preserving its existing scratchpad entry and all output geometry. Applied the
  profile through hyprmoncfg; generated files were not manually edited.
- Important hyprmoncfg 1.25.1 behavior: disabled planning falls back to sequential
  groups of three when an unknown output extends a profile. This was reproduced
  and corrected with explicit enabled/manual planning. Old empty guest workspaces
  disappeared; the DP-6 bar changed from duplicate 4/5 entries to a single 1–5 set.
- Baseline backup: `~/.local/state/workspace-drag/backups/slots-20261028T013156`.
  Physical resolution, refresh, position, scale and transform matched the baseline
  exactly after profile application. User windows stayed on workspace 3 and 13.
- Addon installation backup: `20261028T013357.122216`.

## Source highlight, animations and keyboard chooser — 2026-10-28

- 112 behavior tests pass. Native Lua tests execute modifier ordering, AltGr,
  submap suppression, frozen source choice and binding callbacks; Python tests
  cover early commit/cancel, reordered navigation, stable monitor topology,
  five shared slots, settings validation, conflict rejection and rollback.
- Independent Sol review approved the final pointer hit test, topology guards,
  defaults contract and conservative native-bind conflict detection.
- Native `code:N` bindings are valid despite empty legacy key/keycode fields in
  `hyprctl -j binds`. Existing foreign physical binds with those ambiguous fields
  cause a settings conflict refusal instead of an unchecked prefix assignment.
- A live thumbnail changes monitor `directScanoutBlockedBy` telemetry. Comparing
  whole monitor JSON cancelled the chooser; the corrected guard compares stable
  identity, geometry, scale, transform and active workspace only.
- Private uinput on the running compositor proved left Alt+Shift opens a passive
  overview for the active disposable Foot window. Alt+Shift+4 moved it locally;
  Alt+Shift+Right then 4 moved it to ID 14 (local 4 on DP-6). Both active views
  remained 3 and 13, and ChatGPT/Parsec kept their original workspaces.
- Alt+Shift+Space pinned the chooser; releasing modifiers, Tab then 4 moved Foot
  to the second monitor. Escape cancelled a pinned session, and the next prefix
  opened normally. Reverse Shift/Alt press order worked; releasing modifiers
  cancelled. Right Alt+Shift did not open the chooser. Parsec submap suppressed it.
- Pointer mode was saved through the production settings helper. With ChatGPT
  active and the cursor above Foot, the native prefix captured Foot. Moving the
  cursor away did not retarget; digit 4 moved Foot alone. A temporary no-warp
  option enabled that differing-focus test and was restored immediately afterward.
- Live settings showed the source selector, animation presets and fixed footer
  Preview button. Defaults restored Active window without QML errors; Preview
  opened and Escape closed it; Save persisted Active window and reported success.
  Earlier GUI testing also previewed an unsaved disabled-animation choice.
- Final keyboard screenshot shows exactly local 1–5 around both monitors, source
  card border/tint and “Tu jest okno”. Source selection is active by default.
- Installed code matches the source. Final feature installation backup is
  `20261028T022338.227748`; settings saves have their own backups. Test windows,
  temporary native probes and private input daemon were removed, and the initial
  Parsec focus/submap restored. Desktop captures remain outside Git.

Pointer mode deliberately declines overlapping eligible windows because this
Hyprland API exposes no reliable stacking query. The panel states this limitation.
This pass did not repeat physical mouse dragging, reboot or monitor unplug.
Animation timing was not measured with frame instrumentation.
