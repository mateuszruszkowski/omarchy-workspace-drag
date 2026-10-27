#!/usr/bin/env python3
"""Open the settings window, or focus the existing Quickshell window."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

TITLE = "Workspace Drag — Ustawienia"


def main():
    try:
        result = subprocess.run(["hyprctl", "-j", "clients"], capture_output=True,
                                text=True, check=True, timeout=5)
        clients = json.loads(result.stdout)
        if not isinstance(clients, list):
            raise ValueError("Invalid Hyprland clients response")
        for client in clients:
            if (not isinstance(client, dict) or client.get("title") != TITLE
                    or client.get("class") != "org.quickshell" or not client.get("mapped")):
                continue
            address = client.get("address", "")
            if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", address):
                raise ValueError("Invalid settings window address")
            expression = 'hl.dispatch(hl.dsp.focus({window="address:' + address + '"}))'
            focused = subprocess.run(["hyprctl", "eval", expression], capture_output=True,
                                     text=True, check=True, timeout=5)
            if focused.stdout.strip() != "ok":
                raise RuntimeError("Hyprland did not confirm settings window focus")
            return 0
        os.execvp("qs", ["qs", "--no-duplicate", "--path", str(Path(__file__).parent / "settings.qml")])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Cannot open Workspace Drag settings: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
