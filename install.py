#!/usr/bin/env python3
"""Install this user-owned extension. Never reloads Hyprland or starts processes."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil

SOURCE = Path(__file__).parent
HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
SHARE = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "workspace-drag"
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "workspace-drag"
BINDING_LINE = 'require("hypr.workspace-drag") -- workspace-drag managed include'
AUTOSTART_LINE = 'o.launch_on_start("' + str(SHARE / "workspace-drag") + ' start") -- workspace-drag managed autostart'
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
    backup = STATE / "backups" / datetime.now().strftime("%Y%m%dT%H%M%S.%f")
    backup.mkdir(parents=True, mode=0o700)
    for name in ("bindings.lua", "autostart.lua", "workspace-drag.lua"):
        source = CONFIG / "hypr" / name
        if source.exists():
            shutil.copy2(source, backup / name)
    if SHARE.exists():
        shutil.copytree(SHARE, backup / "app")
    if not args.uninstall:
        SHARE.mkdir(parents=True, exist_ok=True)
        for name in ("shell.qml", "backend.py", "workspace-drag", "bindings.lua", "config.json", "README.md", "VERIFICATION.md"):
            if name in ("config.json", "bindings.lua") and (SHARE / name).exists():
                continue
            destination = SHARE / name
            temporary = destination.with_suffix(destination.suffix + ".new")
            shutil.copy2(SOURCE / name, temporary)
            temporary.replace(destination)
        atomic_write(module, MODULE)
    for filename, include in (("bindings.lua", BINDING_LINE), ("autostart.lua", AUTOSTART_LINE)):
        destination = CONFIG / "hypr" / filename
        content = destination.read_text() if destination.exists() else ""
        content = "\n".join(line for line in content.split("\n") if line != include)
        if not args.uninstall:
            content = content.rstrip() + "\n\n" + include + "\n"
        atomic_write(destination, content)
    if args.uninstall:
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
