#!/usr/bin/env python3
"""Install this user-owned extension. Never reloads Hyprland or starts processes."""
import argparse
from datetime import datetime
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
    shortcut_content = None
    if not args.uninstall:
        if desktop_path.exists() and desktop_path.read_text() != DESKTOP:
            parser.error("Settings desktop entry already exists with different content; refusing to overwrite")
        installed_bindings = SHARE / "bindings.lua"
        if installed_bindings.exists():
            content = installed_bindings.read_text()
            if content != (SOURCE / "bindings.lua").read_text():
                try:
                    initial = legacy_shortcut(content)
                except ValueError as error:
                    parser.error(str(error))
                shortcut_content = shortcut(initial) + "\n"
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
    if not args.uninstall:
        SHARE.mkdir(parents=True, exist_ok=True)
        for name in ("shell.qml", "settings.qml", "backend.py", "settings.py", "workspace-drag", "bindings.lua", "shortcut.conf", "config.json", "README.md", "VERIFICATION.md"):
            if name in ("config.json", "shortcut.conf") and (SHARE / name).exists():
                continue
            destination = SHARE / name
            temporary = destination.with_suffix(destination.suffix + ".new")
            shutil.copy2(SOURCE / name, temporary)
            temporary.replace(destination)
        if shortcut_content is not None:
            atomic_write(SHARE / "shortcut.conf", shortcut_content)
        atomic_write(module, MODULE)
        atomic_write(desktop_path, DESKTOP)
    for filename, include in (("bindings.lua", BINDING_LINE), ("autostart.lua", AUTOSTART_LINE)):
        destination = CONFIG / "hypr" / filename
        content = destination.read_text() if destination.exists() else ""
        content = "\n".join(line for line in content.split("\n") if line != include)
        if not args.uninstall:
            content = content.rstrip() + "\n\n" + include + "\n"
        atomic_write(destination, content)
    if args.uninstall:
        if desktop_path.exists() and desktop_path.read_text() == DESKTOP:
            desktop_path.unlink()
        if module.exists() and module.read_text() == MODULE:
            module.unlink()
        if SHARE.exists():
            shutil.rmtree(SHARE)
        print(f"Removed managed includes and extension. Backup: {backup}")
    else:
        print(f"Installed: {SHARE}\nBackup: {backup}\nNext: hyprctl reload; hyprctl configerrors; {SHARE}/workspace-drag start")


def atomic_write(destination, content):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".workspace-drag-new")
    temporary.write_text(content)
    if destination.exists():
        temporary.chmod(destination.stat().st_mode & 0o777)
    temporary.replace(destination)


if __name__ == "__main__":
    main()
