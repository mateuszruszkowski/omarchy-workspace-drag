-- Change this shortcut, then reload Hyprland. Mouse buttons use their evdev code.
local shortcut = "SUPER + ALT + mouse:272"
local command = os.getenv("HOME") .. "/.local/share/workspace-drag/workspace-drag"
local sequence = 0
local token = ""
local held = false

hl.bind(shortcut, function()
  if held then return end
  held = true
  sequence = sequence + 1
  token = tostring(os.time()) .. "-" .. tostring(sequence)
  local cursor = hl.get_cursor_pos()
  hl.exec_cmd(string.format("'%s' begin %s %.4f %.4f", command, token, cursor.x, cursor.y))
end, { description = "Workspace overview drag" })

-- A release must reach this callback even when modifiers were released first.
hl.bind(shortcut, function()
  if not held then return end
  held = false
  local cursor = hl.get_cursor_pos()
  hl.exec_cmd(string.format("'%s' end %s %.4f %.4f", command, token, cursor.x, cursor.y))
end, {
  description = "Drop window on workspace",
  release = true,
  transparent = true,
  ignore_mods = true,
  non_consuming = true,
})

hl.bind("ESCAPE", function()
  if not held then return end
  held = false
  hl.exec_cmd("'" .. command .. "' cancel " .. token)
end, { description = "Cancel workspace drag", ignore_mods = true,
       non_consuming = true, transparent = true })
