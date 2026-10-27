-- workspace-drag managed shortcut data v1
local shortcut = "SUPER + ALT + mouse:272"
local shortcut_file = io.open(os.getenv("HOME") .. "/.local/share/workspace-drag/shortcut.conf", "r")
if shortcut_file then
  local configured = shortcut_file:read("*a"):match("^%s*(.-)%s*$")
  shortcut_file:close()
  local allowed = { SUPER = 1, ALT = 2, CTRL = 3, SHIFT = 4 }
  local previous = 0
  local valid = false
  local parts = {}
  for raw_part in configured:gmatch("[^+]+") do
    local part = raw_part:match("^%s*(.-)%s*$")
    table.insert(parts, part)
    if allowed[part] and allowed[part] > previous and not valid then
      previous = allowed[part]
    elseif previous > 0 and not valid and (part == "mouse:272" or part == "mouse:273" or part == "mouse:274") then
      valid = true
    else
      valid = false
      previous = -1
      break
    end
  end
  if valid and table.concat(parts, " + ") == configured then shortcut = configured end
end
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
