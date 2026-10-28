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

-- workspace-drag keyboard overview v1
-- This hook observes keys; only the explicit bindings below consume keys.
local keyboard_prefix = "ALT + SHIFT"
local keyboard_file = io.open(os.getenv("HOME") .. "/.local/share/workspace-drag/keyboard.conf", "r")
if keyboard_file then
  local configured = keyboard_file:read("*a"):match("^%s*(.-)%s*$")
  keyboard_file:close()
  local allowed, previous, count, parts = {SUPER=1, ALT=2, CTRL=3, SHIFT=4}, 0, 0, {}
  for raw_part in configured:gmatch("[^+]+") do
    local part = raw_part:match("^%s*(.-)%s*$")
    if not allowed[part] or allowed[part] <= previous then previous = -1; break end
    previous, count = allowed[part], count + 1
    table.insert(parts, part)
  end
  keyboard_prefix = count >= 2 and previous > 0 and table.concat(parts, " + ") == configured and configured or "disabled"
end
local keyboard_source = "active"
local source_file = io.open(os.getenv("HOME") .. "/.local/share/workspace-drag/keyboard-source.conf", "r")
if source_file then
  local configured = source_file:read("*a"):match("^%s*(.-)%s*$")
  source_file:close()
  if configured == "active" or configured == "pointer" then keyboard_source = configured
  else keyboard_prefix = "disabled" end
end
local function window_at_pointer()
  -- The pinned native API has no cursor selector or guaranteed stacking order.
  -- Freeze a single eligible hit now; ambiguous overlaps never choose a hidden window.
  local cursor, monitor = hl.get_cursor_pos(), hl.get_monitor_at_cursor()
  if not cursor or not monitor then return nil end
  local workspace = hl.get_active_workspace(monitor)
  if not workspace then return nil end
  local hit = nil
  for _, window in ipairs(hl.get_windows({monitor=monitor, workspace=workspace, mapped=true})) do
    local at, size = window.at, window.size
    if not window.hidden and window.accepts_input ~= false and at and size
      and at.x <= cursor.x and cursor.x < at.x + size.x
      and at.y <= cursor.y and cursor.y < at.y + size.y then
      if hit then return nil end
      hit = window
    end
  end
  return hit
end
if hl.on and hl.is_key_down and hl.get_active_window then
  hl.exec_cmd("'" .. command .. "' cancel manual")
  local down = {}
  local modifiers = {[64]="ALT", [50]="SHIFT", [62]="SHIFT", [37]="CTRL", [105]="CTRL", [133]="SUPER", [134]="SUPER", [108]="ALTGR"}
  for code in pairs(modifiers) do down[code] = hl.is_key_down(code) end
  local wanted = {}
  for modifier in keyboard_prefix:gmatch("%u+") do wanted[modifier] = true end
  local session, blocked = nil, false
  local function chord()
    local actual = {ALT=down[64], SHIFT=down[50] or down[62], CTRL=down[37] or down[105], SUPER=down[133] or down[134]}
    if down[108] then return false end -- Right Alt is AltGr on the Polish layout.
    for modifier, pressed in pairs(actual) do if not not pressed ~= not not wanted[modifier] then return false end end
    return keyboard_prefix ~= "disabled"
  end
  local function released()
    for code, modifier in pairs(modifiers) do if wanted[modifier] and down[code] then return false end end
    return true
  end
  local function send(action, digit)
    if not session then return end
    session.sequence = session.sequence + 1
    hl.exec_cmd(string.format("'%s' keyboard %s %s %s %d %s %d %d %d %d %s", command,
      session.token, action, session.address, session.workspace, session.monitor,
      session.sequence, session.monitorStep, session.workspaceStep, digit or 0, keyboard_source))
  end
  local function cancel()
    if session then send("cancel"); session = nil end
    blocked = true
  end
  local function begin()
    local window = keyboard_source == "pointer" and window_at_pointer() or nil
    if keyboard_source == "active" then window = hl.get_active_window() end
    if not window or not window.workspace or not window.monitor
      or not tostring(window.address):match("^0x%x+$")
      or not tostring(window.monitor.name):match("^[%w_.:-]+$") then blocked = true; return end
    sequence = sequence + 1
    session = {token=tostring(os.time()) .. "-k-" .. tostring(sequence), address=window.address,
      workspace=window.workspace.id, monitor=window.monitor.name, sequence=0, monitorStep=0, workspaceStep=0}
    send("begin")
  end
  local owned = {[113]="left", [114]="right", [111]="up", [116]="down", [36]="commit", [65]="pin"}
  for code=10,19 do owned[code] = "digit" end
  -- The current event precedes Hyprland's pressed-state update: update it directly.
  _G.workspace_drag_keyboard_hook = hl.on("input.keyboard.key", function(code, time_ms, state)
    if modifiers[code] then down[code] = state == 1 end
    if hl.get_current_submap() ~= "" then
      if session then cancel() end
      blocked = not released()
      return
    end
    if modifiers[code] then
      if released() then blocked = false end
      if session and not session.pinned and not chord() then cancel() end
      if not session and not blocked and chord() then begin() end
      return
    end
    if state ~= 1 or not session or session.pinned then return end
    if not chord() or not owned[code] then cancel() end
  end)
  local function invoke(code)
    if not session or session.pinned or not chord() or hl.get_current_submap() ~= "" then return end
    local operation = owned[code]
    if operation == "digit" then
      send("commit", code == 19 and 10 or code - 9); session = nil; blocked = true
    elseif operation == "commit" then
      send("commit"); session = nil; blocked = true
    elseif operation == "pin" then
      session.pinned = true; send("pin")
      -- QML owns all input after pinning. Do not retain a native stale session.
      session = nil; blocked = true
    else
      if operation == "left" then session.monitorStep = session.monitorStep - 1 end
      if operation == "right" then session.monitorStep = session.monitorStep + 1 end
      if operation == "up" then session.workspaceStep = session.workspaceStep - 1 end
      if operation == "down" then session.workspaceStep = session.workspaceStep + 1 end
      send("navigate")
    end
  end
  if keyboard_prefix ~= "disabled" then
    -- Native Lua binds store code:NN in sMkKeys. hyprctl's legacy key/keycode
    -- fields can consequently report an empty key and zero even for valid binds.
    for code in pairs(owned) do
      hl.bind(keyboard_prefix .. " + code:" .. code, function() invoke(code) end,
        {description="Workspace overview keyboard"})
    end
  end
end
