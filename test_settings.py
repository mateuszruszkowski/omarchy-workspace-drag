import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import settings
import open_settings

SOURCE = Path(__file__).parent


def legacy(chord="SUPER + ALT + mouse:272"):
    content = (SOURCE / "bindings.lua").read_text()
    start = content.index("local shortcut_file =")
    end = content.index("local command =")
    return (content[:start] + content[end:]).replace(settings.MANAGED_MARKER,
        "-- Change this shortcut, then reload Hyprland. Mouse buttons use their evdev code.").replace(
        'local shortcut = "SUPER + ALT + mouse:272"', 'local shortcut = "' + chord + '"')


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "config.json").write_text(json.dumps({"backgroundOpacity": .45,
            "previewMode": "titles", "hiddenMonitors": ["PRIVATE"], "extension": {"x": 7}}))
        (self.root / "bindings.lua").write_text((SOURCE / "bindings.lua").read_text())
        (self.root / "shortcut.conf").write_text("SUPER + ALT + mouse:272\n")

    def test_read_preserves_custom_settings(self):
        draft, config = settings.read_settings(self.root)
        self.assertEqual(draft["backgroundOpacity"], .45)
        self.assertEqual(draft["previewMode"], "titles")
        self.assertEqual(config["extension"], {"x": 7})

    def test_validation_rejects_injection_duplicates_unmodified_mouse_and_invalid_values(self):
        for key, value in [("modifiers", ["SUPER';os.execute('false')"]), ("modifiers", ["SUPER", "SUPER"]),
                           ("modifiers", []), ("mouseButton", "left; exit"), ("backgroundOpacity", float("nan")),
                           ("backgroundOpacity", True), ("backgroundOpacity", .09), ("previewMode", "execute")]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                settings.validate({**settings.DEFAULTS, key: value})
        for chord in ("SUPER + mouse:272 + shell:bad", "ALT + SUPER + mouse:273", "SUPER+mouse:272"):
            with self.subTest(chord=chord), self.assertRaises(ValueError):
                settings.parse_shortcut(chord)

    def test_appearance_apply_preserves_other_values_without_reload(self):
        calls = []
        result = settings.apply_settings(settings.DEFAULTS.copy(), self.root, lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        config = json.loads((self.root / "config.json").read_text())
        self.assertEqual(config["extension"], {"x": 7})
        self.assertEqual(config["hiddenMonitors"], ["PRIVATE"])
        self.assertEqual(config["backgroundOpacity"], .72)
        self.assertTrue(Path(result["backup"], "config.json").exists())

    def test_live_conflict_leaves_files_unchanged(self):
        original = (self.root / "config.json").read_bytes()
        draft = {**settings.DEFAULTS, "modifiers": ["SUPER"]}
        def run(*args):
            self.assertEqual(args, ("-j", "binds"))
            return json.dumps([{"modmask": 64, "key": "mouse:272", "dispatcher": "movewindow"}])
        with self.assertRaisesRegex(ValueError, "zajęty"):
            settings.apply_settings(draft, self.root, run)
        self.assertEqual((self.root / "config.json").read_bytes(), original)
        self.assertFalse((self.root / "settings-backups").exists())

    def test_own_descriptions_are_ignored_but_other_release_conflicts_are_checked(self):
        draft = settings.DEFAULTS.copy()
        settings.check_conflicts(draft, [{"modmask": 72, "key": "mouse:272", "description": name}
                                       for name in settings.OWN_DESCRIPTIONS])
        with self.assertRaises(ValueError):
            settings.check_conflicts(draft, [{"modmask": 72, "key": "mouse:272", "release": True}])

    def test_shortcut_apply_reloads_checks_errors_and_preserves_bindings(self):
        lua = (self.root / "bindings.lua").read_bytes()
        calls = []
        def run(*args):
            calls.append(args)
            return {"-j": "[]", "reload": "ok", "configerrors": ""}[args[0]]
        settings.apply_settings({**settings.DEFAULTS, "modifiers": ["SHIFT", "ALT"], "mouseButton": "middle"}, self.root, run)
        self.assertEqual((self.root / "shortcut.conf").read_text(), "ALT + SHIFT + mouse:274\n")
        self.assertEqual((self.root / "bindings.lua").read_bytes(), lua)
        self.assertEqual(calls, [("-j", "binds"), ("reload",), ("configerrors",)])

    def test_reload_error_rolls_back_both_files_and_reloads_previous_config(self):
        originals = {name: (self.root / name).read_bytes() for name in ("config.json", "shortcut.conf")}
        calls = []
        def run(*args):
            calls.append(args)
            if args[0] == "-j": return "[]"
            if args[0] == "reload": return "ok"
            return "bad config" if calls.count(("configerrors",)) == 1 else ""
        with self.assertRaisesRegex(RuntimeError, "Przywrócono"):
            settings.apply_settings({**settings.DEFAULTS, "mouseButton": "right"}, self.root, run)
        self.assertEqual({name: (self.root / name).read_bytes() for name in originals}, originals)
        self.assertEqual(calls.count(("reload",)), 2)

    def test_partial_write_failure_rolls_back(self):
        originals = {name: (self.root / name).read_bytes() for name in ("config.json", "shortcut.conf")}
        actual_write = settings.atomic_write
        attempts = 0
        def write(destination, content):
            nonlocal attempts
            attempts += 1
            if attempts == 2: raise OSError("test disk error")
            actual_write(destination, content)
        with patch.object(settings, "atomic_write", write), self.assertRaisesRegex(RuntimeError, "Przywrócono"):
            settings.apply_settings({**settings.DEFAULTS, "mouseButton": "right"}, self.root,
                lambda *args: "[]" if args[0] == "-j" else "ok" if args[0] == "reload" else "")
        self.assertEqual({name: (self.root / name).read_bytes() for name in originals}, originals)

    def test_malformed_config_is_visible_and_never_overwritten(self):
        (self.root / "config.json").write_text("broken")
        with self.assertRaises(ValueError):
            settings.apply_settings(settings.DEFAULTS.copy(), self.root)
        self.assertEqual((self.root / "config.json").read_text(), "broken")

    def test_legacy_custom_shortcut_is_recognized_unknown_code_refused(self):
        self.assertEqual(settings.legacy_shortcut(legacy("CTRL + SHIFT + mouse:273"))["mouseButton"], "right")
        self.assertEqual(settings.shortcut(settings.legacy_shortcut(legacy("ALT + SUPER + mouse:273"))), "SUPER + ALT + mouse:273")
        self.assertEqual(settings.legacy_shortcut(legacy("CTRL + mouse:274").replace('"CTRL + mouse:274"', "'CTRL + mouse:274'"))["mouseButton"], "middle")
        with self.assertRaisesRegex(ValueError, "Niestandardowy"):
            settings.legacy_shortcut(legacy() + "\nprint('custom')\n")

    @unittest.skipUnless(shutil.which("lua"), "Lua interpreter unavailable")
    def test_lua_reader_accepts_only_canonical_allowlisted_data(self):
        script = """
local configured = ...
local original_getenv = os.getenv
os.getenv = function(name) if name == "HOME" then return "/test-home" else return original_getenv(name) end end
io.open = function() return {read=function() return configured end, close=function() end} end
hl = {bind=function(chord) print(chord) end}
dofile(arg[1])
"""
        for value, expected in [("CTRL + SHIFT + mouse:273", "CTRL + SHIFT + mouse:273"),
                                ("ALT + SUPER + mouse:273", "SUPER + ALT + mouse:272"),
                                ("SUPER + mouse:272 +", "SUPER + ALT + mouse:272"),
                                ("SUPER + SUPER + mouse:272", "SUPER + ALT + mouse:272"),
                                ("SUPER + mouse:272; os.execute('bad')", "SUPER + ALT + mouse:272"),
                                ("mouse:272", "SUPER + ALT + mouse:272")]:
            with self.subTest(value=value):
                result = subprocess.run(["lua", "-", str(SOURCE / "bindings.lua"), value],
                    input=script.replace("local configured = ...", "local configured = arg[2]"),
                    capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.splitlines()[:2], [expected, expected])


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.env = {**os.environ, "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"),
                    "XDG_DATA_HOME": str(self.home / ".local/share"), "XDG_STATE_HOME": str(self.home / ".local/state")}
        self.app = self.home / ".local/share/workspace-drag"
        self.desktop = self.home / ".local/share/applications/workspace-drag-settings.desktop"

    def install(self, *args):
        return subprocess.run([sys.executable, str(SOURCE / "install.py"), *args], env=self.env,
                              capture_output=True, text=True)

    def test_legacy_migration_preserves_custom_chord_and_repeat_install(self):
        self.app.mkdir(parents=True)
        (self.app / "bindings.lua").write_text(legacy("CTRL + SHIFT + mouse:273"))
        (self.app / "config.json").write_text('{"custom": true, "backgroundOpacity": 0.4}')
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual((self.app / "shortcut.conf").read_text(), "CTRL + SHIFT + mouse:273\n")
        self.assertIn(settings.MANAGED_MARKER, (self.app / "bindings.lua").read_text())
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual((self.app / "shortcut.conf").read_text(), "CTRL + SHIFT + mouse:273\n")
        self.assertTrue(json.loads((self.app / "config.json").read_text())["custom"])
        self.assertIn(" settings\n", self.desktop.read_text())
        self.assertEqual((self.home / ".config/hypr/bindings.lua").read_text().count("managed include"), 1)
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertFalse(self.desktop.exists())

    def test_unknown_custom_lua_refused_before_any_changes(self):
        self.app.mkdir(parents=True)
        original = legacy() + "\nprint('custom')\n"
        (self.app / "bindings.lua").write_text(original)
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual((self.app / "bindings.lua").read_text(), original)
        self.assertFalse((self.home / ".config").exists())
        self.assertFalse(self.desktop.exists())
        self.assertFalse((self.home / ".local/state").exists())

    def test_uninstall_preserves_modified_desktop_entry(self):
        self.assertEqual(self.install().returncode, 0)
        self.desktop.write_text("custom desktop")
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(self.desktop.read_text(), "custom desktop")

    def test_bar_plugin_install_preserves_layout_and_unrelated_plugins(self):
        shell = self.home / ".config/omarchy/shell.json"
        shell.parent.mkdir(parents=True)
        original = '{"custom": true, "bar": {"layout": {"center": [{"id": "clock"}], "right": [{"id": "other"}]}}}'
        shell.write_text(original)
        unrelated = shell.parent / "plugins/other/custom.qml"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("operator plugin")
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("omarchy plugin enable local.workspace-drag --section centerBegin", result.stdout)
            self.assertEqual(shell.read_text(), original)
        plugin = shell.parent / "plugins/local.workspace-drag"
        self.assertTrue((plugin / "BarWidget.qml").exists())
        self.assertTrue((self.app / "open_settings.py").exists())
        custom = plugin / "operator-note.txt"
        custom.write_text("keep")
        config = json.loads(original)
        config["bar"]["layout"]["right"].append({"id": "local.workspace-drag"})
        shell.write_text(json.dumps(config))
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(json.loads(shell.read_text()), json.loads(original))
        self.assertEqual(unrelated.read_text(), "operator plugin")
        self.assertEqual(custom.read_text(), "keep")
        self.assertFalse((plugin / "BarWidget.qml").exists())
        self.assertTrue(list((self.home / ".local/state/workspace-drag/backups").glob("*/shell.json")))

    def test_unknown_bar_plugin_collision_is_refused_before_changes(self):
        custom = self.home / ".config/omarchy/plugins/local.workspace-drag/BarWidget.qml"
        custom.parent.mkdir(parents=True)
        custom.write_text("operator plugin")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(custom.read_text(), "operator plugin")
        self.assertFalse(self.app.exists())
        self.assertFalse((self.home / ".local/state").exists())

    def test_uninstall_preserves_modified_owned_plugin_file(self):
        self.assertEqual(self.install().returncode, 0)
        custom = self.home / ".config/omarchy/plugins/local.workspace-drag/BarWidget.qml"
        custom.write_text("operator changes")
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(custom.read_text(), "operator changes")


class OpenSettingsTest(unittest.TestCase):
    @patch.object(open_settings.os, "execvp")
    @patch.object(open_settings.subprocess, "run")
    def test_existing_exact_mapped_window_is_focused(self, run, launch):
        clients = [{"title": open_settings.TITLE, "class": "browser", "mapped": True, "address": "0x1"},
                   {"title": open_settings.TITLE, "class": "org.quickshell", "mapped": True, "address": "0xaB12"}]
        run.side_effect = [subprocess.CompletedProcess([], 0, json.dumps(clients)), subprocess.CompletedProcess([], 0, "ok\n")]
        self.assertEqual(open_settings.main(), 0)
        self.assertEqual(run.call_args.args[0], ["hyprctl", "eval", 'hl.dispatch(hl.dsp.focus({window="address:0xaB12"}))'])
        launch.assert_not_called()

    @patch.object(open_settings.os, "execvp")
    @patch.object(open_settings.subprocess, "run")
    def test_no_matching_window_launches_single_instance(self, run, launch):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps([
            {"title": open_settings.TITLE + " other", "class": "org.quickshell", "mapped": True},
            {"title": open_settings.TITLE, "class": "org.quickshell", "mapped": False}]))
        open_settings.main()
        launch.assert_called_once_with("qs", ["qs", "--no-duplicate", "--path", str(SOURCE / "settings.qml")])

    @patch.object(open_settings.os, "execvp")
    @patch.object(open_settings.subprocess, "run")
    def test_focus_failure_is_reported_without_duplicate_launch(self, run, launch):
        run.side_effect = [subprocess.CompletedProcess([], 0, json.dumps([
            {"title": open_settings.TITLE, "class": "org.quickshell", "mapped": True, "address": "0x12"}])),
            subprocess.TimeoutExpired("hyprctl", 5)]
        with patch("sys.stderr") as stderr:
            self.assertEqual(open_settings.main(), 1)
            self.assertTrue(stderr.write.called)
        launch.assert_not_called()

    @patch.object(open_settings.os, "execvp")
    @patch.object(open_settings.subprocess, "run")
    def test_invalid_window_address_never_reaches_eval(self, run, launch):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps([
            {"title": open_settings.TITLE, "class": "org.quickshell", "mapped": True,
             "address": '0x12"}); os.execute("unexpected")'}]))
        with patch("sys.stderr"):
            self.assertEqual(open_settings.main(), 1)
        self.assertEqual(run.call_count, 1)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
