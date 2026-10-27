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
