#!/usr/bin/env python3
"""Read and apply the settings exposed by the local graphical panel."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).parent
MODIFIERS = {"SUPER": 64, "ALT": 8, "CTRL": 4, "SHIFT": 1}
BUTTONS = {"left": 272, "right": 273, "middle": 274}
DEFAULTS = {"modifiers": ["SUPER", "ALT"], "mouseButton": "left",
            "backgroundOpacity": .72, "previewMode": "thumbnails", "cardScale": 1, "zoom": 1.15}
OWN_DESCRIPTIONS = {"Workspace overview drag", "Drop window on workspace"}
LEGACY_HASH = "eb2a136a2eb54d2a2b0696e38098beee54a05c50cf93a8cdd0a2acfb51f006d4"
MANAGED_MARKER = "-- workspace-drag managed shortcut data v1"


def validate(draft):
    if not isinstance(draft, dict) or set(draft) != set(DEFAULTS):
        raise ValueError("Nieprawidłowy zestaw ustawień.")
    mods = draft["modifiers"]
    if (not isinstance(mods, list) or not mods or any(not isinstance(m, str) or m not in MODIFIERS for m in mods)
            or len(set(mods)) != len(mods)):
        raise ValueError("Wybierz co najmniej jeden modyfikator skrótu.")
    button = draft["mouseButton"]
    if not isinstance(button, str) or button not in BUTTONS:
        raise ValueError("Nieprawidłowy przycisk myszy.")
    opacity = draft["backgroundOpacity"]
    if type(opacity) not in (int, float) or not math.isfinite(opacity) or not .1 <= opacity <= 1:
        raise ValueError("Przyciemnienie musi wynosić od 10 do 100%.")
    for key, low, high, message in (("cardScale", .5, 2, "Rozmiar podglądów musi wynosić od 50 do 200%."),
                                    ("zoom", 1, 1.35, "Powiększenie po najechaniu musi wynosić od 100 do 135%.")):
        value = draft[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(message)
    if draft["previewMode"] not in ("thumbnails", "titles"):
        raise ValueError("Nieprawidłowy tryb podglądu.")
    return {**draft, "modifiers": [m for m in MODIFIERS if m in mods]}


def shortcut(draft):
    return " + ".join(draft["modifiers"] + ["mouse:" + str(BUTTONS[draft["mouseButton"]])])


def parse_shortcut(value, require_canonical=True):
    parts = value.strip().split(" + ")
    reverse = {"mouse:" + str(code): button for button, code in BUTTONS.items()}
    if not parts or parts[-1] not in reverse:
        raise ValueError("Skrót ma nieobsługiwany format. Dozwolone są Super, Alt, Ctrl, Shift i trzy przyciski myszy.")
    draft = validate({**DEFAULTS, "modifiers": parts[:-1], "mouseButton": reverse[parts[-1]]})
    if require_canonical and value.strip() != shortcut(draft):
        raise ValueError("Nieprawidłowa kolejność modyfikatorów. Użyj kolejności SUPER, ALT, CTRL, SHIFT.")
    return draft


def legacy_shortcut(content):
    match = re.search(r"^local shortcut = ([\"'])([^\"'\n]+)\1$", content, re.M)
    if not match:
        raise ValueError("Nieznany plik bindings.lua. Zachowano go bez zmian; wymagana jest ręczna migracja.")
    normalized = content[:match.start()] + 'local shortcut = "' + shortcut(DEFAULTS) + '"' + content[match.end():]
    if hashlib.sha256(normalized.encode()).hexdigest() != LEGACY_HASH:
        raise ValueError("Niestandardowy bindings.lua. Zachowano go bez zmian; wymagana jest ręczna migracja.")
    return parse_shortcut(match[2], require_canonical=False)


def read_settings(root=ROOT):
    config_path = root / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("config.json musi zawierać obiekt JSON.")
    data = dict(DEFAULTS)
    shortcut_path = root / "shortcut.conf"
    if shortcut_path.exists():
        data.update(parse_shortcut(shortcut_path.read_text()))
    else:
        data.update(legacy_shortcut((root / "bindings.lua").read_text()))
    data.update({k: config.get(k, DEFAULTS[k]) for k in ("backgroundOpacity", "previewMode", "cardScale", "zoom")})
    return validate(data), config


def hyprctl(*arguments):
    result = subprocess.run(["hyprctl", *arguments], capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError("Hyprland odrzucił polecenie " + arguments[0] + ". " + result.stderr.strip()[:400])
    return result.stdout.strip()


def check_conflicts(draft, bindings):
    mask = sum(MODIFIERS[m] for m in draft["modifiers"])
    key = "mouse:" + str(BUTTONS[draft["mouseButton"]])
    if not isinstance(bindings, list):
        raise ValueError("Nieprawidłowa odpowiedź listy skrótów Hyprland.")
    for binding in bindings:
        if (binding.get("modmask") == mask and binding.get("key") == key
                and binding.get("description") not in OWN_DESCRIPTIONS):
            description = binding.get("description") or binding.get("dispatcher") or "istniejąca akcja"
            raise ValueError("Skrót jest zajęty: " + str(description)[:160] + ". Wybierz inny skrót.")


def atomic_write(destination, content):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".workspace-drag-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            if destination.exists():
                temporary.chmod(destination.stat().st_mode & 0o777)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def reload_checked(run):
    output = run("reload")
    if output != "ok":
        raise RuntimeError("Hyprland nie potwierdził przeładowania konfiguracji.")
    errors = run("configerrors")
    if errors:
        raise RuntimeError("Błąd konfiguracji Hyprland: " + errors[:700])


def apply_settings(draft, root=ROOT, run=hyprctl):
    draft = validate(draft)
    before, config = read_settings(root)
    changing_shortcut = shortcut(before) != shortcut(draft)
    if changing_shortcut:
        if MANAGED_MARKER not in (root / "bindings.lua").read_text():
            raise ValueError("Najpierw zaktualizuj dodatek instalatorem, aby włączyć graficzną zmianę skrótu.")
        check_conflicts(draft, json.loads(run("-j", "binds")))
    config.update({k: draft[k] for k in ("backgroundOpacity", "previewMode", "cardScale", "zoom")})
    updates = {root / "config.json": (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode()}
    if changing_shortcut:
        updates[root / "shortcut.conf"] = (shortcut(draft) + "\n").encode()
    original = {p: p.read_bytes() if p.exists() else None for p in updates}
    backup = root / "settings-backups" / datetime.now().strftime("%Y%m%dT%H%M%S.%f")
    backup.mkdir(parents=True, mode=0o700)
    for destination, content in original.items():
        if content is not None:
            (backup / destination.name).write_bytes(content)
    try:
        for destination, content in updates.items():
            atomic_write(destination, content)
        if changing_shortcut:
            reload_checked(run)
    except Exception as error:
        rollback_errors = []
        for destination, content in original.items():
            try:
                if content is None:
                    destination.unlink(missing_ok=True)
                else:
                    atomic_write(destination, content)
            except OSError as restore_error:
                rollback_errors.append(str(restore_error))
        if changing_shortcut:
            try:
                reload_checked(run)
            except Exception as restore_error:
                rollback_errors.append(str(restore_error))
        if rollback_errors:
            raise RuntimeError(f"{error} Nie udało się w pełni przywrócić konfiguracji. Kopia: {backup}. " + "; ".join(rollback_errors)) from error
        raise RuntimeError(str(error) + " Przywrócono poprzednie ustawienia.") from error
    return {"settings": draft, "backup": str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("read", "apply"))
    args = parser.parse_args()
    try:
        result = {"settings": read_settings()[0]} if args.action == "read" else apply_settings(json.load(sys.stdin))
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
