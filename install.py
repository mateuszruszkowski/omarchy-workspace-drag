#!/usr/bin/env python3
"""Install this user-owned extension. Never reloads Hyprland or starts processes."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
from settings import legacy_shortcut, parse_shortcut, shortcut

SOURCE = Path(__file__).parent
HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
SHARE = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "workspace-drag"
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "workspace-drag"
BINDING_LINE = 'require("hypr.workspace-drag") -- workspace-drag managed include'
AUTOSTART_LINE = 'o.launch_on_start("' + str(SHARE / "workspace-drag") + ' start") -- workspace-drag managed autostart'
DESKTOP_NAME = 'workspace-drag-settings.desktop'
DESKTOP = '[Desktop Entry]\nType=Application\nName=Workspace Drag — Ustawienia\nComment=Skrót, przyciemnienie i podglądy pulpitów\nExec=' + str(SHARE / 'workspace-drag') + ' settings\nIcon=preferences-desktop\nTerminal=false\nCategories=Settings;DesktopSettings;\nX-Workspace-Drag-Managed=true\n'
MODULE = 'dofile(os.getenv("HOME") .. "/.local/share/workspace-drag/bindings.lua")\n'
PLUGIN_ID = "local.workspace-drag"
PLUGIN = CONFIG / "omarchy/plugins" / PLUGIN_ID
PLUGIN_SOURCE = SOURCE / "bar-plugin"
PLUGIN_MARKER = ".workspace-drag-managed"
PREVIOUS_KEYBOARD_BINDINGS_HASHES = {
    "a4cdbdecfaf3952affcbce42c7358f7c012b162a00d9939478cf74722cd0e988",
    "0c5a1dc626c5625e2911a4b7e81bde2ef0a1c02cbf313537d920382125cffddd",
}


def owned_plugin():
    marker = PLUGIN / PLUGIN_MARKER
    if marker.is_file() and marker.read_text() == PLUGIN_ID + "\n":
        return True
    return all((PLUGIN / item.relative_to(PLUGIN_SOURCE)).is_file()
               and (PLUGIN / item.relative_to(PLUGIN_SOURCE)).read_bytes() == item.read_bytes()
               for item in PLUGIN_SOURCE.rglob("*") if item.is_file())


def clean_bar_config(content):
    config = json.loads(content)
    layout = config.get("bar", {}).get("layout", {})
    if not isinstance(layout, dict):
        raise ValueError("Invalid Omarchy bar layout")
    changed = False
    for section, entries in layout.items():
        if isinstance(entries, list):
            kept = [entry for entry in entries if not
                    (entry == PLUGIN_ID or isinstance(entry, dict) and entry.get("id") == PLUGIN_ID)]
            if kept != entries:
                layout[section] = kept
                changed = True
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n" if changed else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if str(SHARE) != str(HOME / ".local/share/workspace-drag"):
        parser.error("Custom XDG_DATA_HOME needs a matching bindings.lua command path; standard home installation only")
    module = CONFIG / "hypr/workspace-drag.lua"
    if not args.uninstall and module.exists() and module.read_text() != MODULE:
        parser.error("workspace-drag.lua already exists with different content; refusing to overwrite")
    desktop_path = SHARE.parent / "applications" / DESKTOP_NAME
    plugin_owned = PLUGIN.exists() and owned_plugin()
    if not args.uninstall and PLUGIN.exists() and not plugin_owned:
        parser.error("Bar plugin directory already exists and is not managed; refusing to overwrite")
    shell_path = CONFIG / "omarchy/shell.json"
    cleaned_shell = None
    if args.uninstall and plugin_owned and shell_path.exists():
        try:
            cleaned_shell = clean_bar_config(shell_path.read_text())
        except (ValueError, AttributeError) as error:
            parser.error(f"Cannot safely remove bar entry: {error}")
    shortcut_content = None
    if not args.uninstall:
        if desktop_path.exists() and desktop_path.read_text() != DESKTOP:
            parser.error("Settings desktop entry already exists with different content; refusing to overwrite")
        installed_bindings = SHARE / "bindings.lua"
        if installed_bindings.exists():
            content = installed_bindings.read_text()
            if content != (SOURCE / "bindings.lua").read_text():
                try:
                    previous_managed = (SOURCE / "bindings.lua").read_text().split("\n-- workspace-drag keyboard overview v1")[0].rstrip() + "\n"
                    initial = parse_shortcut((SHARE / "shortcut.conf").read_text()) if (content == previous_managed or hashlib.sha256(content.encode()).hexdigest() in PREVIOUS_KEYBOARD_BINDINGS_HASHES) and (SHARE / "shortcut.conf").exists() else legacy_shortcut(content)
                except ValueError as error:
                    parser.error(str(error))
                shortcut_content = shortcut(initial) + "\n"
        source_path = SHARE / "keyboard-source.conf"
        if source_path.exists() and source_path.read_text().strip() not in ("active", "pointer"):
            parser.error("Invalid keyboard-source.conf; refusing to overwrite")
        shortcut_path = SHARE / "shortcut.conf"
        if shortcut_path.exists():
            try:
                parse_shortcut(shortcut_path.read_text())
            except ValueError as error:
                parser.error(str(error))
            shortcut_content = None
    backup = STATE / "backups" / datetime.now().strftime("%Y%m%dT%H%M%S.%f")
    backup.mkdir(parents=True, mode=0o700)
    for name in ("bindings.lua", "autostart.lua", "workspace-drag.lua"):
        source = CONFIG / "hypr" / name
        if source.exists():
            shutil.copy2(source, backup / name)
    if desktop_path.exists():
        shutil.copy2(desktop_path, backup / DESKTOP_NAME)
    if SHARE.exists():
        shutil.copytree(SHARE, backup / "app")
    if plugin_owned:
        shutil.copytree(PLUGIN, backup / "bar-plugin")
    if cleaned_shell is not None:
        shutil.copy2(shell_path, backup / "shell.json")
    if not args.uninstall:
        SHARE.mkdir(parents=True, exist_ok=True)
        for name in ("shell.qml", "settings.qml", "backend.py", "settings.py", "open_settings.py", "workspace-drag", "bindings.lua", "shortcut.conf", "keyboard.conf", "keyboard-source.conf", "config.json", "README.md", "VERIFICATION.md"):
            if name in ("config.json", "shortcut.conf", "keyboard.conf", "keyboard-source.conf") and (SHARE / name).exists():
                continue
            destination = SHARE / name
            temporary = destination.with_suffix(destination.suffix + ".new")
            shutil.copy2(SOURCE / name, temporary)
            temporary.replace(destination)
        if shortcut_content is not None:
            atomic_write(SHARE / "shortcut.conf", shortcut_content)
        atomic_write(module, MODULE)
        atomic_write(desktop_path, DESKTOP)
        shutil.copytree(PLUGIN_SOURCE, PLUGIN, dirs_exist_ok=True)
        atomic_write(PLUGIN / PLUGIN_MARKER, PLUGIN_ID + "\n")
    for filename, include in (("bindings.lua", BINDING_LINE), ("autostart.lua", AUTOSTART_LINE)):
        destination = CONFIG / "hypr" / filename
        content = destination.read_text() if destination.exists() else ""
        content = "\n".join(line for line in content.split("\n") if line != include)
        if not args.uninstall:
            content = content.rstrip() + "\n\n" + include + "\n"
        atomic_write(destination, content)
    if args.uninstall:
        if cleaned_shell is not None:
            atomic_write(shell_path, cleaned_shell)
        if plugin_owned:
            # Preserve files edited by the operator and unrelated additions.
            for source in PLUGIN_SOURCE.rglob("*"):
                destination = PLUGIN / source.relative_to(PLUGIN_SOURCE)
                if source.is_file() and destination.is_file() and destination.read_bytes() == source.read_bytes():
                    destination.unlink()
            (PLUGIN / PLUGIN_MARKER).unlink(missing_ok=True)
            for directory in sorted(PLUGIN.rglob("*"), reverse=True):
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
            if not any(PLUGIN.iterdir()):
                PLUGIN.rmdir()
        if desktop_path.exists() and desktop_path.read_text() == DESKTOP:
            desktop_path.unlink()
        if module.exists() and module.read_text() == MODULE:
            module.unlink()
        if SHARE.exists():
            shutil.rmtree(SHARE)
        print(f"Removed managed includes and extension. Backup: {backup}")
    else:
        print(f"Installed: {SHARE}\nBackup: {backup}\nEnable bar icon: omarchy plugin enable {PLUGIN_ID} --section centerBegin\nNext: hyprctl reload; hyprctl configerrors; {SHARE}/workspace-drag start")


def atomic_write(destination, content):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".workspace-drag-new")
    temporary.write_text(content)
    if destination.exists():
        temporary.chmod(destination.stat().st_mode & 0o777)
    temporary.replace(destination)


if __name__ == "__main__":
    main()
