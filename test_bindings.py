"""Execute the native keyboard hook with Hyprland's pre-update key semantics."""
from pathlib import Path
import shutil
import subprocess
import unittest

SOURCE = Path(__file__).parent

MOCK = r'''
local binds, commands, pressed, hook = {}, {}, {}, nil
local submap, overlap = "", nil
local pointed = {address="0xdef", workspace={id=1}, monitor={name="eDP-1"}, at={x=0,y=0}, size={x=500,y=500}, mapped=true, hidden=false, accepts_input=true}
io.open = function(file)
  if file:match("keyboard%-source.conf$") then return {read=function() return arg[3] or "active" end, close=function() end} end
  local value = file:match("keyboard.conf$") and (arg[2] or "ALT + SHIFT") or "SUPER + ALT + mouse:272"
  return {read=function() return value end, close=function() end}
end
hl = {
  get_current_submap=function() return submap end,
  bind=function(chord, callback, options) binds[chord] = {callback=callback, options=options} end,
  is_key_down=function(code) return pressed[code] == true end,
  on=function(event, callback) assert(event == "input.keyboard.key"); hook = callback; return {} end,
  exec_cmd=function(command) table.insert(commands, command) end,
  get_cursor_pos=function() return {x=100,y=100} end,
  get_monitor_at_cursor=function() return {name="eDP-1"} end,
  get_active_workspace=function() return {id=1} end,
  get_windows=function(filter)
    assert(filter.monitor.name == "eDP-1" and filter.workspace.id == 1 and filter.mapped)
    local windows = {}
    if pointed then table.insert(windows, pointed) end
    if overlap then table.insert(windows, overlap) end
    return windows
  end,
  get_active_window=function() return {address="0xabc", workspace={id=1}, monitor={name="eDP-1"}} end,
}
dofile(arg[1])
local function key(code, state)
  hook(code, 123, state)
  pressed[code] = state == 1
  if state == 1 then
    local mods = {}
    if pressed[133] or pressed[134] then table.insert(mods, "SUPER") end
    if pressed[64] then table.insert(mods, "ALT") end
    if pressed[37] then table.insert(mods, "CTRL") end
    if pressed[50] or pressed[62] then table.insert(mods, "SHIFT") end
    local binding = binds[table.concat(mods, " + ") .. " + code:" .. code]
    if binding then binding.callback() end
  end
end
local function count(action)
  local count = 0
  for _, command in ipairs(commands) do if command:match(" keyboard %S+ " .. action .. " ") then count = count + 1 end end
  return count
end
'''


@unittest.skipUnless(shutil.which("lua"), "Lua interpreter unavailable")
class NativeKeyboardTests(unittest.TestCase):
    def run_lua(self, body, prefix="ALT + SHIFT", source="active"):
        result = subprocess.run(["lua", "-", str(SOURCE / "bindings.lua"), prefix, source], input=MOCK + body,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_both_modifier_orders_and_both_shift_keys(self):
        self.run_lua('''
for _, shift in ipairs({50, 62}) do
  key(64, 1); key(shift, 1); assert(count("begin") >= 1)
  key(10, 1); key(10, 0); key(64, 0); key(shift, 0)
  key(shift, 1); key(64, 1); key(19, 1); key(19, 0); key(shift, 0); key(64, 0)
end
assert(count("begin") == 4 and count("commit") == 4)
assert(commands[#commands]:match(" 10 active$"))
''')

    def test_altgr_is_never_prefix_and_extra_modifiers_cancel(self):
        self.run_lua('''
key(108, 1); key(50, 1); assert(count("begin") == 0)
key(108, 0); key(50, 0)
key(64, 1); key(50, 1); key(37, 1)
assert(count("cancel") == 1)
key(37, 0); assert(count("begin") == 1)
key(50, 0); key(64, 0)
key(64, 1); key(62, 1); assert(count("begin") == 2)
''')

    def test_tab_and_unrelated_key_cancel_without_consuming_or_reopening(self):
        self.run_lua('''
assert(not binds["ALT + SHIFT + code:23"] and not binds["ALT + SHIFT + TAB"])
for _, code in ipairs({23, 38, 9, 172}) do
  key(64, 1); key(50, 1); key(code, 1); key(code, 0)
  key(62, 1); key(62, 0)
  key(50, 0); key(64, 0)
end
assert(count("begin") == 4 and count("cancel") == 4 and count("commit") == 0)
''')

    def test_pin_releases_native_state_for_new_prefix_after_qml_close(self):
        self.run_lua('''
key(64, 1); key(50, 1); key(65, 1); key(65, 0)
assert(count("pin") == 1)
key(50, 0); key(64, 0)
-- QML may close/cancel/time out; native no longer owns a pinned token.
key(64, 1); key(50, 1); key(10, 1)
assert(count("begin") == 2 and count("commit") == 1)
''')

    def test_owned_keys_consume_and_existing_mouse_release_is_unchanged(self):
        self.run_lua('''
for code=10,19 do assert(not binds["ALT + SHIFT + code:" .. code].options.non_consuming) end
assert(binds["ESCAPE"].options.non_consuming)
assert(not binds["ALT + SHIFT + code:172"])
key(64, 1); key(50, 1); key(114, 1); key(116, 1); key(36, 1)
assert(count("navigate") == 2 and count("commit") == 1)
assert(commands[#commands]:match(" %d+ 1 1 0 active$"))
''')

    def test_custom_prefix_and_invalid_data_are_allowlisted(self):
        self.run_lua('''
key(133, 1); key(37, 1); key(10, 1)
assert(count("begin") == 1 and count("commit") == 1)
assert(not binds["ALT + SHIFT + code:10"])
''', "SUPER + CTRL")
        for prefix in ("disabled", "ALT + ALT", "ALT + SHIFT +", "ALT + SHIFT; print(1)", "SHIFT + ALT", "ALT"):
            self.run_lua('''
key(64, 1); key(50, 1); key(10, 1)
assert(count("begin") == 0 and count("commit") == 0)
assert(not binds["ALT + SHIFT + code:10"])
''', prefix)

    def test_pointer_source_is_frozen_at_chord_press_even_if_pointer_changes(self):
        self.run_lua('''
key(64, 1); key(50, 1)
assert(commands[#commands]:match(" begin 0xdef 1 eDP%-1 "))
pointed = {address="0xbeef", workspace={id=4}, monitor={name="DP-6"}}
key(10, 1)
assert(commands[#commands]:match(" commit 0xdef 1 eDP%-1 "))
assert(commands[#commands]:match(" pointer$"))
''', source="pointer")

    def test_pointer_empty_space_does_not_fall_back_to_active_window(self):
        self.run_lua('''
pointed = nil
key(64, 1); key(50, 1); key(10, 1)
assert(count("begin") == 0 and count("commit") == 0)
''', source="pointer")

    def test_nondefault_submap_suppresses_prefix_and_cancels_existing_session(self):
        self.run_lua('''
submap = "parsec"
key(64, 1); key(50, 1); assert(count("begin") == 0)
key(64, 0); key(50, 0)
submap = ""
key(64, 1); key(50, 1); assert(count("begin") == 1)
submap = "parsec"
key(10, 1); assert(count("cancel") == 1 and count("commit") == 0)
''')

    def test_pointer_overlap_never_guesses_which_window_is_on_top(self):
        self.run_lua('''
overlap = {address="0xaaa", workspace={id=1}, monitor={name="eDP-1"}, at={x=0,y=0}, size={x=500,y=500}, hidden=false, accepts_input=true}
key(64, 1); key(50, 1); key(10, 1)
assert(count("begin") == 0 and count("commit") == 0)
''', source="pointer")

    def test_keypad_enter_commits_selected_workspace_without_cancelling_prefix(self):
        self.run_lua('''
key(64, 1); key(50, 1)
key(116, 1); key(116, 0)
key(104, 1)
assert(count("begin") == 1 and count("navigate") == 1)
assert(count("commit") == 1 and count("cancel") == 0)
assert(commands[#commands]:match(" %d+ 0 1 0 active$"))
assert(binds["ALT + SHIFT + code:104"] and not binds["ALT + SHIFT + code:104"].options.non_consuming)
''')
