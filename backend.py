#!/usr/bin/env python3
"""Workspace drag state and Hyprland IPC. stdout is a private JSON UI stream."""
from collections import Counter
import dataclasses
import json
import math
import os
from pathlib import Path
import re
import select
import socket
import sys
import time

ROOT = Path(__file__).parent
DEFAULTS = {"groupColumns": 0, "cardWidth": 230, "cardHeight": 150, "gap": 24,
            "cardScale": 1, "zoom": 1.15, "backgroundOpacity": .72, "previewMode": "thumbnails", "animationPreset": "smooth",
            "hiddenMonitors": ["STUDIO-VIRTUAL"], "timeoutSeconds": 25, "pollMilliseconds": 35,
            "restoreCursor": True, "defaultWorkspaces": list(range(1, 11))}


def load_config():
    config = DEFAULTS.copy()
    try:
        config.update(json.loads((ROOT / "config.json").read_text()))
    except (OSError, ValueError):
        pass
    for key, low, high in [("groupColumns", 0, 10), ("cardWidth", 120, 600),
                            ("cardHeight", 90, 400), ("gap", 12, 80),
                            ("cardScale", .5, 2), ("zoom", 1, 1.35), ("backgroundOpacity", 0.1, 1), ("timeoutSeconds", 2, 120),
                            ("pollMilliseconds", 20, 200)]:
        value = config.get(key)
        config[key] = min(high, max(low, float(value))) if isinstance(value, (int, float)) and math.isfinite(value) else DEFAULTS[key]
    config["groupColumns"] = int(config["groupColumns"])
    if config.get("previewMode") not in ("thumbnails", "titles"):
        config["previewMode"] = "thumbnails"
    if config.get("animationPreset") not in ("none", "quick", "smooth"):
        config["animationPreset"] = DEFAULTS["animationPreset"]
    if not isinstance(config.get("hiddenMonitors"), list):
        config["hiddenMonitors"] = DEFAULTS["hiddenMonitors"]
    config["hiddenMonitors"] = [name for name in config["hiddenMonitors"] if isinstance(name, str)]
    return config


class HyprIPC:
    def request(self, command):
        signature = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(1)
            connection.connect(f"{runtime}/hypr/{signature}/.socket.sock")
            connection.sendall(command.encode())
            data = bytearray()
            while True:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 8_000_000:
                    raise ValueError("IPC response too large")
            return data.decode()

    def get(self, name):
        return json.loads(self.request("j/" + name))

    def dispatch(self, lua):
        result = self.request("eval " + lua)
        if result.strip() != "ok":
            raise RuntimeError("Hyprland dispatch rejected")


def logical_monitor(monitor):
    result = dict(monitor)
    width, height = monitor["width"], monitor["height"]
    if monitor.get("transform", 0) % 2:
        width, height = height, width
    result["logicalWidth"] = width / monitor.get("scale", 1)
    result["logicalHeight"] = height / monitor.get("scale", 1)
    return result


def normal_name(value):
    value = str(value)
    return bool(value and len(value) <= 100 and value != "special" and not value.startswith("special:")
                and all(ord(c) >= 32 and ord(c) != 127 for c in value))


def lua_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def selector(name):
    return name if name.isdigit() else "name:" + name.removeprefix("name:")


def monitor_for_rule(rule, monitors, fallback):
    wanted = str(rule.get("monitor") or "")
    for monitor in monitors:
        if wanted == monitor["name"] or wanted == "desc:" + monitor.get("description", ""):
            return monitor
    return fallback if not wanted else None


def load_workspace_blocks():
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    try:
        lines = (state / "omarchy/monitor-workspaces").read_text().splitlines()
    except (OSError, UnicodeError):
        return {}
    entries = []
    for line in lines:
        fields = line.split("\t")
        if len(fields) < 3 or not re.fullmatch(r"[0-9]+", fields[0]) or not normal_name(fields[1]) or fields[1] != fields[1].strip():
            continue
        try:
            entries.append((fields[1], int(fields[0])))
        except ValueError:
            continue
    connectors = Counter(connector for connector, _ in entries)
    blocks = Counter(block for _, block in entries)
    return {connector: block for connector, block in entries if connectors[connector] == 1 and blocks[block] == 1}


def workspace_label(name, monitor, blocks):
    if re.fullmatch(r"[1-9][0-9]*", name) and monitor in blocks:
        number = int(name)
        if (number - 1) // 10 == blocks[monitor]:
            return str((number - 1) % 10 + 1)
    return name


def workspace_targets(monitors, workspaces, rules, config, fallback, blocks=None):
    blocks = blocks or {}
    targets = {}
    # A slot has one owner even when a stale workspace is on another monitor.
    existing = {str(w.get("name", "")): w for w in workspaces}
    for monitor in monitors:
        if monitor["name"] not in blocks:
            continue
        for slot in range(1, 6):
            name = str(blocks[monitor["name"]] * 10 + slot)
            workspace = existing.get(name)
            targets[name] = {"name": name, "monitor": monitor["name"],
                             "existing": workspace is not None, "slot": True,
                             "disabled": workspace is not None and workspace.get("monitor") != monitor["name"]}
    by_name = {m["name"]: m for m in monitors}
    for workspace in workspaces:
        name = str(workspace.get("name", ""))
        if normal_name(name) and workspace.get("monitor") in by_name and name not in targets:
            targets[name] = {"name": name, "monitor": workspace["monitor"], "existing": True}
    configured = False
    for rule in rules:
        name = str(rule.get("workspaceString", "")).removeprefix("name:")
        if any(char in name for char in "[]()"):
            continue
        if not rule.get("enabled", True) or not normal_name(name):
            continue
        if not (rule.get("monitor") or rule.get("persistent") or rule.get("default")):
            continue
        configured = True
        if name in targets:
            continue
        monitor = monitor_for_rule(rule, monitors, fallback)
        if monitor and monitor["name"] not in blocks:
            targets[name] = {"name": name.removeprefix("name:"), "monitor": monitor["name"], "existing": False}
    if not configured:
        for name in config["defaultWorkspaces"]:
            name = str(name)
            if normal_name(name) and fallback["name"] not in blocks:
                targets.setdefault(name, {"name": name, "monitor": fallback["name"], "existing": False})
    return sorted(targets.values(), key=lambda t: (next(i for i, m in enumerate(monitors) if m["name"] == t["monitor"]),
                                                   (0, int(t["name"])) if t["name"].isdigit() else (1, t["name"])))


def layout_dashboard(targets, monitor, config):
    groups = []
    for target in targets:
        group = next((g for g in groups if g["monitor"] == target["monitor"]), None)
        if group is None:
            group = {"monitor": target["monitor"], "cards": []}
            groups.append(group)
        group["cards"].append(dict(target))
    if not groups:
        return [], []
    card_w = config["cardWidth"] * config["cardScale"]
    card_h = config["cardHeight"] * config["cardScale"]
    gap = config["gap"]
    zoom = config["zoom"]
    for group in groups:
        points = [(math.cos(-math.pi / 2 + 2 * math.pi * i / len(group["cards"])),
                   math.sin(-math.pi / 2 + 2 * math.pi * i / len(group["cards"])))
                  for i in range(len(group["cards"]))]
        # Separate the enlarged cards from each other and from the monitor label.
        constraints = [(abs(x), abs(y), card_w * zoom / 2 + 88 + gap,
                        card_h * zoom / 2 + 48 + gap) for x, y in points]
        constraints += [(abs(x1 - x2), abs(y1 - y2), card_w * zoom + gap, card_h * zoom + gap)
                        for i, (x1, y1) in enumerate(points) for x2, y2 in points[i + 1:]]
        radius = max(min(w / dx if dx > 1e-6 else math.inf,
                         h / dy if dy > 1e-6 else math.inf) for dx, dy, w, h in constraints)
        group.update(radius=radius, points=points,
                     width=2 * radius + card_w * zoom, height=2 * radius + card_h * zoom)
    available_w, available_h = monitor["logicalWidth"] - 80, monitor["logicalHeight"] - 170
    group_gap = 48
    requested = config.get("groupColumns", 0)
    candidates = [min(len(groups), requested)] if requested else range(1, len(groups) + 1)
    arrangements = []
    for columns in candidates:
        rows = math.ceil(len(groups) / columns)
        cell_w, cell_h = max(g["width"] for g in groups), max(g["height"] for g in groups)
        content_w = columns * cell_w + (columns - 1) * group_gap
        content_h = rows * cell_h + (rows - 1) * group_gap
        scale = min(1, available_w / content_w, available_h / content_h)
        arrangements.append((scale, columns, rows, cell_w, cell_h, content_w, content_h))
    scale, columns, rows, cell_w, cell_h, content_w, content_h = max(arrangements)
    origin_x = (monitor["logicalWidth"] - content_w * scale) / 2
    origin_y = 110 + (available_h - content_h * scale) / 2
    cards = []
    for index, group in enumerate(groups):
        center_x = origin_x + (index % columns * (cell_w + group_gap) + cell_w / 2) * scale
        center_y = origin_y + (index // columns * (cell_h + group_gap) + cell_h / 2) * scale
        group["center"] = {"x": center_x, "y": center_y}
        group["radius"] *= scale
        group["labelWidth"], group["labelHeight"] = 176 * scale, 96 * scale
        for target, (cosine, sine) in zip(group["cards"], group.pop("points")):
            target.update(x=center_x + cosine * group["radius"] - card_w * scale / 2,
                          y=center_y + sine * group["radius"] - card_h * scale / 2,
                          width=card_w * scale, height=card_h * scale)
            cards.append(target)
        del group["width"], group["height"]
    return cards, groups


def pointer_data(pointer, monitor):
    return {"x": pointer["x"], "y": pointer["y"],
            "localX": pointer["x"] - monitor["x"], "localY": pointer["y"] - monitor["y"]}


def target_at(cards, monitor, pointer):
    x, y = pointer["x"] - monitor["x"], pointer["y"] - monitor["y"]
    return next((card for card in cards if not card.get("disabled") and card["x"] <= x < card["x"] + card["width"]
                 and card["y"] <= y < card["y"] + card["height"]), None)


@dataclasses.dataclass
class Dragging:
    token: str
    source: dict
    monitor: dict
    origin: dict
    monitors: list
    cards: list
    groups: list
    clients: list
    started: float
    mode: str = "drag"
    selected_monitor: str = ""
    selected_name: str = ""
    keyboard_sequence: int = -1
    keyboard_source: str = "active"


class Controller:
    def __init__(self, ipc, emit, clock=time.monotonic):
        self.ipc, self.emit, self.clock = ipc, emit, clock
        self.drag = None
        self.ended = {}
        self.restore = None
        self.config = load_config()
        self.workspace_blocks = {}

    def publish(self, pointer=None):
        drag = self.drag
        if not drag:
            self.emit({"state": "idle"})
            return
        hovered = (next((card for card in drag.cards if card["name"] == drag.selected_name and card["monitor"] == drag.selected_monitor), None)
                   if drag.mode.startswith("keyboard") else target_at(drag.cards, drag.monitor, pointer or drag.origin))
        source_workspace = drag.source.get("workspace", {}).get("name", "")
        source_label = next((card.get("label", source_workspace) for card in drag.cards
                             if card["name"] == source_workspace),
                            workspace_label(source_workspace, drag.monitor["name"], self.workspace_blocks))
        self.emit({"state": "dragging", "token": drag.token, "screen": drag.monitor["name"],
                   "monitor": drag.monitor, "monitors": drag.monitors, "cards": drag.cards,
                   "groups": drag.groups, "source": drag.source.get("address", ""),
                   "sourceClient": {k: drag.source.get(k, "") for k in ("address", "class", "title", "size")},
                   "pointer": pointer_data(pointer or drag.origin, drag.monitor),
                   "backgroundOpacity": self.config["backgroundOpacity"], "previewMode": self.config["previewMode"],
                   "sourceWorkspace": source_workspace, "sourceWorkspaceLabel": source_label,
                   "clients": drag.clients, "hovered": hovered["name"] if hovered else "",
                   "zoom": self.config["zoom"], "rounding": self.config.get("rounding", 0),
                   "animationPreset": self.config["animationPreset"],
                   "animationsEnabled": self.config.get("animationsEnabled", True),
                   "mode": drag.mode, "keyboardPrefix": self.keyboard_prefix(),
                   "selectedMonitor": drag.selected_monitor, "demo": drag.mode == "demo"})

    def keyboard_prefix(self):
        from settings import read_keyboard, keyboard_shortcut
        try:
            return keyboard_shortcut(read_keyboard(ROOT))
        except (OSError, ValueError):
            return ""

    def keyboard(self, action):
        token = action.get("token")
        operation = action.get("action")
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,100}", token):
            raise ValueError("invalid keyboard token")
        if operation not in ("begin", "pin", "navigate", "commit", "cancel"):
            raise ValueError("invalid keyboard action")
        if operation == "cancel":
            self.finish(token, cancel=True)
            return
        if token in self.ended:
            return
        drag = self.drag
        if drag and (drag.token != token or not drag.mode.startswith("keyboard")):
            return
        if not drag:
            snapshot = action.get("source", {})
            source_mode = snapshot.get("mode", "active") if isinstance(snapshot, dict) else None
            if (not isinstance(snapshot, dict) or not re.fullmatch(r"0x[0-9a-fA-F]+", str(snapshot.get("address", "")))
                    or source_mode not in ("active", "pointer") or type(snapshot.get("workspace")) is not int or not isinstance(snapshot.get("monitor"), str)):
                raise ValueError("invalid keyboard source")
            self.config = load_config()
            self.read_native_appearance(self.config)
            monitors = [logical_monitor(m) for m in self.ipc.get("monitors") if not m.get("disabled")]
            clients = self.ipc.get("clients")
            source = next((c for c in clients if c.get("address") == snapshot["address"] and c.get("mapped")
                           and not c.get("hidden") and c.get("workspace", {}).get("id") == snapshot["workspace"]), None)
            monitor = next((m for m in monitors if m["name"] == snapshot["monitor"] and source
                            and m["id"] == source.get("monitor") and m["activeWorkspace"]["id"] == snapshot["workspace"]), None)
            if not monitor or (source_mode == "active" and self.ipc.get("activewindow").get("address") != snapshot["address"]):
                self.finish(token, cancel=True)
                return
            cards, groups, previews = self.dashboard_data(monitors, monitor, clients, self.config)
            origin = {"x": monitor["x"], "y": monitor["y"]}
            drag = Dragging(token, source, monitor, origin, monitors, cards, groups, previews, self.clock(), "keyboard-prefix")
            drag.keyboard_source = source_mode
            drag.selected_monitor, drag.selected_name = monitor["name"], source["workspace"]["name"]
            self.drag = drag
            self.restore = None
        sequence = action.get("sequence", drag.keyboard_sequence + 1)
        if type(sequence) is not int or sequence <= drag.keyboard_sequence:
            return
        drag.keyboard_sequence = sequence
        if operation == "pin":
            drag.mode = "keyboard"
        if "monitorStep" in action or "workspaceStep" in action:
            # Native messages contain absolute navigation offsets, so launch order is irrelevant.
            monitors = [g["monitor"] for g in drag.groups]
            ms, ws = action.get("monitorStep", 0), action.get("workspaceStep", 0)
            if type(ms) is not int or type(ws) is not int or abs(ms) > 100000 or abs(ws) > 100000:
                raise ValueError("invalid keyboard navigation")
            drag.selected_monitor = monitors[(monitors.index(drag.monitor["name"]) + ms) % len(monitors)]
            cards = [c for c in drag.cards if c["monitor"] == drag.selected_monitor and not c.get("disabled")]
            if cards:
                base = next((i for i, c in enumerate(cards) if c["name"] == drag.source["workspace"]["name"]), 0)
                drag.selected_name = cards[(base + ws) % len(cards)]["name"]
        elif operation == "navigate":
            direction = action.get("direction")
            monitors = [g["monitor"] for g in drag.groups]
            if direction in ("left", "right"):
                drag.selected_monitor = monitors[(monitors.index(drag.selected_monitor) + (-1 if direction == "left" else 1)) % len(monitors)]
                cards = [c for c in drag.cards if c["monitor"] == drag.selected_monitor and not c.get("disabled")]
                drag.selected_name = cards[0]["name"] if cards else ""
            elif direction in ("up", "down"):
                cards = [c for c in drag.cards if c["monitor"] == drag.selected_monitor and not c.get("disabled")]
                if cards:
                    index = next((i for i, c in enumerate(cards) if c["name"] == drag.selected_name), 0)
                    drag.selected_name = cards[(index + (-1 if direction == "up" else 1)) % len(cards)]["name"]
            else:
                raise ValueError("invalid keyboard direction")
        if operation == "commit":
            digit = action.get("digit")
            if digit is not None:
                if type(digit) is not int or not 1 <= digit <= 10:
                    raise ValueError("invalid keyboard digit")
                target = next((c for c in drag.cards if c["monitor"] == drag.selected_monitor and c.get("label") == str(digit)), None)
                drag.selected_name = target["name"] if target else ""
            self.finish(token)
        else:
            self.publish()

    def read_native_appearance(self, config):
        try:
            config["rounding"] = max(0, min(40, self.ipc.get("getoption decoration:rounding")["int"]))
        except (KeyError, ValueError, TypeError):
            config["rounding"] = 0
        try:
            config["animationsEnabled"] = self.ipc.get("getoption animations:enabled")["bool"] is not False
        except (KeyError, ValueError, TypeError):
            config["animationsEnabled"] = True

    def begin(self, token, pointer=None):
        if token in self.ended or self.drag:
            return
        self.restore = None
        self.config = load_config()
        self.read_native_appearance(self.config)
        monitors = [logical_monitor(m) for m in self.ipc.get("monitors") if not m.get("disabled")]
        pointer = pointer or self.ipc.get("cursorpos")
        monitor = next((m for m in monitors if m["x"] <= pointer["x"] < m["x"] + m["logicalWidth"]
                        and m["y"] <= pointer["y"] < m["y"] + m["logicalHeight"]), None)
        if not monitor:
            return
        clients = self.ipc.get("clients")
        candidates = [c for c in clients if c.get("mapped") and not c.get("hidden")
                      and c.get("workspace", {}).get("id") == monitor["activeWorkspace"]["id"]
                      and c["at"][0] <= pointer["x"] < c["at"][0] + c["size"][0]
                      and c["at"][1] <= pointer["y"] < c["at"][1] + c["size"][1]]
        if not candidates:
            return
        if pointer.get("sourceAddress"):
            candidates = [c for c in candidates if c["address"] == pointer["sourceAddress"]]
        if not candidates:
            return
        candidates.sort(key=lambda c: (c.get("focusHistoryID", 99999) if c.get("focusHistoryID", 99999) >= 0 else 99999,
                                       not bool(c.get("floating")), not bool(c.get("fullscreen"))))
        source = candidates[0]
        if not re.fullmatch(r"0x[0-9a-fA-F]+", source["address"]):
            return
        cards, groups, previews = self.dashboard_data(monitors, monitor, clients, self.config)
        self.drag = Dragging(token, source, monitor, pointer, monitors, cards, groups, previews, self.clock())
        self.publish(pointer)

    def dashboard_data(self, monitors, monitor, clients, config):
        visible_monitors = [m for m in monitors if m["name"] not in config["hiddenMonitors"] or m["name"] == monitor["name"]]
        self.workspace_blocks = load_workspace_blocks()
        targets = workspace_targets(visible_monitors, self.ipc.get("workspaces"), self.ipc.get("workspacerules"), config, monitor, self.workspace_blocks)
        for target in targets:
            target["label"] = workspace_label(target["name"], target["monitor"], self.workspace_blocks)
        monitor_order = {m["name"]: index for index, m in enumerate(visible_monitors)}
        targets.sort(key=lambda target: (monitor_order[target["monitor"]],
                                         (0, int(target["label"])) if target["label"].isdigit() else (1, target["label"])))
        labels = Counter((target["monitor"], target["label"]) for target in targets)
        for target in targets:
            if labels[target["monitor"], target["label"]] > 1:
                target["label"] += " (ID " + target["name"] + ")"
        cards, groups = layout_dashboard(targets, monitor, config)
        # Titles travel only over the local UI pipe and are never logged.
        previews = [{k: c[k] for k in ("address", "at", "size", "workspace", "monitor", "class", "title", "floating") if k in c}
                    for c in clients if c.get("mapped") and not c.get("hidden")
                    and normal_name(c.get("workspace", {}).get("name", ""))]
        return cards, groups, previews

    def preview(self, token, appearance):
        valid = isinstance(appearance, dict) and not (appearance.keys() - {"backgroundOpacity", "previewMode", "cardScale", "zoom", "animationPreset"})
        for key, low, high in (("backgroundOpacity", .1, 1), ("cardScale", .5, 2), ("zoom", 1, 1.35)):
            if valid and key in appearance:
                value = appearance[key]
                valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
        if valid and "previewMode" in appearance:
            valid = appearance["previewMode"] in ("thumbnails", "titles")
        if valid and "animationPreset" in appearance:
            valid = appearance["animationPreset"] in ("none", "quick", "smooth")
        if not valid or self.drag:
            self.emit({"state": "preview-result", "token": token, "ok": False,
                       "error": "Trwa przeciąganie lub podgląd." if self.drag else "Nieprawidłowe ustawienia podglądu."})
            return False
        config = load_config()
        config.update(appearance)
        self.read_native_appearance(config)
        monitors = [logical_monitor(m) for m in self.ipc.get("monitors") if not m.get("disabled")]
        if not monitors:
            self.emit({"state": "preview-result", "token": token, "ok": False, "error": "Brak dostępnego monitora."})
            return False
        pointer = self.ipc.get("cursorpos")
        monitor = next((m for m in monitors if m["x"] <= pointer["x"] < m["x"] + m["logicalWidth"]
                        and m["y"] <= pointer["y"] < m["y"] + m["logicalHeight"]), None)
        monitor = monitor or next((m for m in monitors if m.get("focused")), monitors[0])
        cards, groups, clients = self.dashboard_data(monitors, monitor, self.ipc.get("clients"), config)
        self.restore = None
        self.config = config
        self.drag = Dragging(token, {}, monitor, pointer, monitors, cards, groups, clients, self.clock(), "preview")
        self.publish(pointer)
        return True

    def finish(self, token, cancel=False, pointer=None):
        self.ended[token] = self.clock()
        self.ended = {key: stamp for key, stamp in self.ended.items() if self.clock() - stamp < 60}
        drag = self.drag
        if not drag or token != drag.token:
            return
        self.drag = None
        self.emit({"state": "idle"})
        keyboard = drag.mode.startswith("keyboard")
        if drag.mode != "drag" and not keyboard:
            return
        if not keyboard:
            self.restore = (self.clock() + .12, drag)
        if cancel or (not keyboard and self.clock() - drag.started < .12):
            return
        if not keyboard:
            pointer = pointer or self.ipc.get("cursorpos")
        target = (next((c for c in drag.cards if c["name"] == drag.selected_name and c["monitor"] == drag.selected_monitor and not c.get("disabled")), None)
                  if keyboard else target_at(drag.cards, drag.monitor, pointer))
        if not target or target["name"] == drag.source["workspace"]["name"]:
            return
        monitors = [logical_monitor(m) for m in self.ipc.get("monitors") if not m.get("disabled")]
        current_source_monitor = next((m for m in monitors if m["name"] == drag.monitor["name"]), None)
        if not current_source_monitor or current_source_monitor["activeWorkspace"]["id"] != drag.source["workspace"]["id"] or any(current_source_monitor.get(k) != drag.monitor.get(k)
                                             for k in ("x", "y", "logicalWidth", "logicalHeight")):
            return
        clients = self.ipc.get("clients")
        source = next((c for c in clients if c["address"] == drag.source["address"]), None)
        if not source or source["workspace"]["id"] != drag.source["workspace"]["id"] or source.get("monitor") != drag.source.get("monitor"):
            return
        if keyboard and drag.keyboard_source == "active" and self.ipc.get("activewindow").get("address") != drag.source["address"]:
            return
        blocks = load_workspace_blocks()
        available = workspace_targets(monitors, self.ipc.get("workspaces"), self.ipc.get("workspacerules"), self.config, current_source_monitor, blocks)
        fresh_target = next((t for t in available if t["name"] == target["name"] and t["monitor"] == target["monitor"]
                             and not t.get("disabled")), None)
        if not fresh_target or bool(fresh_target.get("slot")) != bool(target.get("slot")):
            return
        address = lua_string("address:" + source["address"])
        workspace = lua_string(selector(target["name"]))
        expected = lua_string(source["address"])
        target_monitor = lua_string(target["monitor"])
        lookup = (f"local target_ws=hl.get_workspace({int(target['name'])})" if target["name"].isdigit()
                  else f"local target_ws=nil;for _,ws in ipairs(hl.get_workspaces()) do if ws.name=={lua_string(target['name'])} then target_ws=ws;break end end")
        guards = [f"local m=hl.get_monitor({target_monitor})",
                  "assert(m,'Workspace drag target monitor disappeared')",
                  f"local w=hl.get_window({address})",
                  f"assert(w and w.address=={expected} and w.workspace and w.workspace.id=={source['workspace']['id']},'Workspace drag source changed')",
                  lookup,
                  f"assert(not target_ws or (target_ws.monitor and target_ws.monitor.name=={target_monitor}),'Workspace drag target changed monitor')"]
        if keyboard and drag.keyboard_source == "active":
            guards.append(f"assert(hl.get_active_window() and hl.get_active_window().address=={expected},'Workspace overview focus changed')")
        if fresh_target.get("slot"):
            guards.append(f"if not target_ws then hl.workspace_rule({{workspace={lua_string(target['name'])},monitor={target_monitor}}}) end")
        elif fresh_target["existing"]:
            guards.append("assert(target_ws,'Workspace drag target disappeared')")
        self.ipc.dispatch(";".join(guards + [
            "hl.dispatch(hl.dsp.window.fullscreen_state({window=w,internal=0,client=0,action='set'}))",
            "hl.dispatch(hl.dsp.window.float({window=w,action='disable'}))",
            f"hl.dispatch(hl.dsp.window.move({{window=w,workspace={workspace},follow=false}}))"]))

    def tick(self):
        if self.restore and self.clock() >= self.restore[0]:
            _, drag = self.restore
            self.restore = None
            if drag.mode == "drag" and self.config.get("restoreCursor"):
                monitors = self.ipc.get("monitors")
                if any(m["name"] == drag.monitor["name"] and m["activeWorkspace"]["id"] == drag.source["workspace"]["id"] for m in monitors):
                    self.ipc.dispatch(f"hl.dispatch(hl.dsp.cursor.move({{x={int(drag.origin['x'])},y={int(drag.origin['y'])}}}))")
        if self.drag:
            if self.clock() - self.drag.started >= self.config["timeoutSeconds"]:
                self.finish(self.drag.token, cancel=True)
            elif self.drag.mode.startswith("keyboard"):
                drag = self.drag
                clients, monitors = self.ipc.get("clients"), self.ipc.get("monitors")
                source = next((c for c in clients if c.get("address") == drag.source["address"]), None)
                def stable_monitor(monitor):
                    logical = logical_monitor(monitor)
                    return tuple(logical.get(key) for key in ("id", "name", "x", "y", "logicalWidth", "logicalHeight", "scale", "transform")) + (logical.get("activeWorkspace", {}).get("id"),)
                # Opening screencopy changes directScanoutBlockedBy and other telemetry.
                # Only display identity, geometry and active workspace invalidate this snapshot.
                valid_monitors = sorted(stable_monitor(m) for m in monitors if not m.get("disabled")) == sorted(stable_monitor(m) for m in drag.monitors)
                if not source or source.get("workspace") != drag.source.get("workspace") or source.get("monitor") != drag.source.get("monitor") or not valid_monitors or (drag.keyboard_source == "active" and self.ipc.get("activewindow").get("address") != drag.source["address"]):
                    self.finish(drag.token, cancel=True)
            else:
                pointer = self.ipc.get("cursorpos")
                hovered = target_at(self.drag.cards, self.drag.monitor, pointer)
                self.emit({"state": "pointer", "hovered": hovered["name"] if hovered else "",
                           "pointer": pointer_data(pointer, self.drag.monitor)})

    def demo(self):
        if self.drag:
            return
        self.workspace_blocks = {}
        monitors = [logical_monitor(m) for m in self.ipc.get("monitors") if not m.get("disabled")]
        monitor = next((m for m in monitors if m.get("focused")), monitors[0])
        monitors = [m for m in monitors if m["name"] not in self.config["hiddenMonitors"] or m["name"] == monitor["name"]]
        targets = [{"name": str(i + 1), "monitor": m["name"], "existing": True}
                   for i, m in enumerate(monitors * 4)]
        targets.sort(key=lambda t: t["monitor"])
        cards, groups = layout_dashboard(targets, monitor, self.config)
        source = {"address": "demo", "workspace": {"name": "1", "id": 1}, "class": "Terminal", "title": "Synthetic window", "size": [1000, 700]}
        previews = [{"address": "demo-" + target["name"] + str(i), "workspace": {"name": target["name"]},
                     "class": name, "title": title} for target in targets
                    for i, (name, title) in enumerate((("Terminal", "Build and test"), ("Browser", "Project documentation"), ("Files", "Downloads")))]
        self.drag = Dragging("demo", source, monitor, self.ipc.get("cursorpos"), monitors, cards, groups, previews, self.clock(), "demo")
        self.publish()


def main():
    controller = Controller(HyprIPC(), lambda data: print(json.dumps(data, ensure_ascii=False), flush=True))
    controller.publish()
    buffer = b""
    while True:
        timeout = controller.config["pollMilliseconds"] / 1000 if controller.drag or controller.restore else None
        readable, _, _ = select.select([sys.stdin.buffer], [], [], timeout)
        try:
            if readable:
                chunk = os.read(sys.stdin.fileno(), 65536)
                if not chunk:
                    return
                buffer += chunk
                if len(buffer) > 65536:
                    raise ValueError("command too large")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    action = json.loads(line)
                    command, token = action.get("command"), str(action.get("token", "manual"))[:100]
                    pointer = action.get("pointer")
                    if pointer is not None and not (isinstance(pointer, dict) and all(isinstance(pointer.get(k), (int, float)) and math.isfinite(pointer[k]) for k in ("x", "y"))):
                        raise ValueError("invalid pointer")
                    if command == "keyboard":
                        controller.keyboard(action)
                    elif command == "begin":
                        controller.begin(token, pointer)
                    elif command == "end":
                        controller.finish(token, pointer=pointer)
                    elif command == "cancel":
                        cancelled = controller.drag.token if token == "manual" and controller.drag else token
                        controller.finish(cancelled, cancel=True)
                    elif command == "preview":
                        controller.preview(token, action.get("appearance"))
                    elif command == "demo":
                        controller.demo()
            controller.tick()
        except (OSError, ValueError, KeyError, RuntimeError, TypeError):
            controller.drag = None
            controller.restore = None
            controller.emit({"state": "idle", "error": "Workspace drag cancelled after an IPC or configuration error"})


if __name__ == "__main__":
    main()
