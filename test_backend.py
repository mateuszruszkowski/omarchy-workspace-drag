import copy
import os
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import patch

from backend import Controller, DEFAULTS, layout_dashboard, logical_monitor, target_at, workspace_targets


class FakeIPC:
    def __init__(self):
        self.data = {
            "monitors": [dict(id=0, name="eDP-1", description="Laptop", x=0, y=0, width=2560,
                              height=1600, scale=1.6, activeWorkspace={"id": 1}),
                         dict(id=1, name="DP-6", description="External", x=1600, y=0, width=3440,
                              height=1440, scale=1, activeWorkspace={"id": 4})],
            "cursorpos": {"x": 600, "y": 400},
            "clients": [dict(address="0xabc", mapped=True, hidden=False, workspace={"id": 1, "name": "1"},
                             at=[0, 0], size=[1600, 1000], monitor=0, floating=True, fullscreen=2,
                             title="PRIVATE NEVER SERIALIZE", **{"class": "test"})],
            "workspaces": [{"id": 1, "name": "1", "monitor": "eDP-1"}, {"id": 4, "name": "4", "monitor": "DP-6"}],
            "workspacerules": [{"workspaceString": "2", "monitor": "desc:Laptop", "enabled": True},
                               {"workspaceString": "5", "monitor": "desc:External", "enabled": True}]
        }
        self.dispatches = []
        self.requests = []

    def get(self, name):
        return copy.deepcopy(self.data[name])

    def dispatch(self, lua):
        self.dispatches.append(lua)

    def request(self, command):
        self.requests.append(command)
        return "ok"


class WorkspaceDragTests(unittest.TestCase):
    def setUp(self):
        blocks = patch("backend.load_workspace_blocks", return_value={"eDP-1": 0, "DP-6": 1})
        self.blocks = blocks.start()
        self.addCleanup(blocks.stop)
        self.ipc = FakeIPC()
        self.time = 10
        self.output = []
        self.controller = Controller(self.ipc, self.output.append, lambda: self.time)
        self.controller.config = DEFAULTS.copy()

    def begin(self):
        self.controller.begin("a")
        self.time += .5
        self.assertIsNotNone(self.controller.drag)

    def aim(self, name):
        drag = self.controller.drag
        card = next(c for c in drag.cards if c["name"] == name)
        self.ipc.data["cursorpos"] = {"x": drag.monitor["x"] + card["x"] + card["width"] / 2,
                                      "y": drag.monitor["y"] + card["y"] + card["height"] / 2}

    def test_release_uses_fresh_pointer_and_moves_address_without_following(self):
        self.begin()
        self.aim("2")
        self.controller.tick()
        self.aim("5")
        self.controller.finish("a")
        lua = self.ipc.dispatches[0]
        self.assertIn('local w=hl.get_window("address:0xabc")', lua)
        self.assertIn('w.address=="0xabc"', lua)
        self.assertEqual(lua.count("window=w"), 3)
        self.assertIn("internal=0,client=0", lua)
        self.assertIn("action='disable'", lua)
        self.assertIn('workspace="5",follow=false', lua)
        self.assertNotIn("focus", lua)
        self.assertEqual(self.output[-1], {"state": "idle"})

    def test_early_release_before_begin_is_tombstoned(self):
        self.controller.finish("a")
        self.controller.begin("a")
        self.assertIsNone(self.controller.drag)
        self.assertFalse(self.ipc.dispatches)

    def test_escape_before_begin_prevents_late_overlay(self):
        self.controller.finish("escaped", cancel=True)
        self.controller.begin("escaped")
        self.assertIsNone(self.controller.drag)
        self.assertFalse(self.ipc.dispatches)

    def test_very_short_hold_does_not_move(self):
        self.controller.begin("a")
        self.aim("2")
        self.controller.finish("a")
        self.assertFalse(self.ipc.dispatches)

    def test_same_workspace_is_noop_even_if_floating_fullscreen(self):
        self.begin()
        self.aim("1")
        self.controller.finish("a")
        self.assertFalse(self.ipc.dispatches)

    def test_cancel_timeout_and_mismatched_release(self):
        self.begin()
        self.aim("2")
        self.controller.finish("other")
        self.assertIsNotNone(self.controller.drag)
        self.time += 30
        self.controller.tick()
        self.assertIsNone(self.controller.drag)
        self.assertFalse(self.ipc.dispatches)

    def test_closed_source_and_unplugged_target_cancel(self):
        for mutation in (lambda: self.ipc.data["clients"].clear(),
                         lambda: self.ipc.data["monitors"].pop()):
            self.setUp()
            self.begin()
            self.aim("15")
            mutation()
            self.controller.finish("a")
            self.assertFalse(self.ipc.dispatches)

    def test_changed_monitor_scale_cancels(self):
        self.begin()
        self.aim("2")
        self.ipc.data["monitors"][0]["scale"] = 2
        self.controller.finish("a")
        self.assertFalse(self.ipc.dispatches)

    def test_no_window_under_cursor_does_not_begin(self):
        self.ipc.data["cursorpos"] = {"x": 1700, "y": 20}
        self.controller.begin("a")
        self.assertIsNone(self.controller.drag)

    def test_only_pointer_delta_during_drag_and_titles_stay_in_local_ui(self):
        self.begin()
        self.controller.tick()
        self.assertEqual(set(self.output[-1]), {"state", "hovered", "pointer"})
        self.assertEqual(self.output[-1]["pointer"], {"x": 600, "y": 400, "localX": 600, "localY": 400})
        self.assertNotIn("title", str(self.output[-1]))
        self.assertEqual(self.output[-2]["sourceClient"]["title"], "PRIVATE NEVER SERIALIZE")
        self.assertEqual(self.output[-2]["previewMode"], "thumbnails")

    def test_ring_layout_packs_disjoint_zoomed_cards_for_two_and_three_monitors(self):
        for count in (2, 3):
            for workspace_count in (1, 3, 5, 8, 12):
                for width, height in ((1600, 1000), (3440, 1440)):
                    monitor = dict(logicalWidth=width, logicalHeight=height)
                    targets = [dict(name=f"{group}-{i}", monitor=f"monitor-{group}")
                               for group in range(count) for i in range(workspace_count)]
                    cards, groups = layout_dashboard(targets, monitor, DEFAULTS)
                    self.assertEqual(len(groups), count)
                    self.assertEqual(sum(len(g["cards"]) for g in groups), len(targets))
                    zoom = DEFAULTS["zoom"]
                    bounds = [(c["x"] - c["width"] * (zoom - 1) / 2,
                               c["y"] - c["height"] * (zoom - 1) / 2,
                               c["width"] * zoom, c["height"] * zoom) for c in cards]
                    for x, y, w, h in bounds:
                        self.assertGreaterEqual(x, 39.9)
                        self.assertGreaterEqual(y, 109.9)
                        self.assertLessEqual(x + w, width - 39.9)
                        self.assertLessEqual(y + h, height - 59.9)
                    for i, (x, y, w, h) in enumerate(bounds):
                        for x2, y2, w2, h2 in bounds[i + 1:]:
                            self.assertFalse(x < x2 + w2 and x2 < x + w and y < y2 + h2 and y2 < y + h)

    def test_card_scale_preserves_custom_ratio_and_changes_requested_size(self):
        targets = [dict(name="1", monitor="monitor-1")]
        monitor = dict(logicalWidth=12000, logicalHeight=8000)
        for scale in (.5, 1, 2):
            with self.subTest(scale=scale):
                cards, _ = layout_dashboard(targets, monitor, DEFAULTS | {
                    "cardWidth": 320, "cardHeight": 180, "cardScale": scale})
                self.assertAlmostEqual(cards[0]["width"], 320 * scale)
                self.assertAlmostEqual(cards[0]["height"], 180 * scale)

    def test_scaled_cards_still_fit_monitor_with_maximum_hover_zoom(self):
        targets = [dict(name=f"{group}-{i}", monitor=f"monitor-{group}")
                   for group in range(3) for i in range(12)]
        for scale in (.5, 1, 2):
            config = DEFAULTS | {"cardScale": scale, "zoom": 1.35}
            cards, _ = layout_dashboard(targets, dict(logicalWidth=1600, logicalHeight=1000), config)
            bounds = [(c["x"] - c["width"] * .35 / 2,
                       c["y"] - c["height"] * .35 / 2,
                       c["width"] * 1.35, c["height"] * 1.35) for c in cards]
            for i, (x, y, w, h) in enumerate(bounds):
                self.assertGreaterEqual(x, 39.9)
                self.assertGreaterEqual(y, 109.9)
                self.assertLessEqual(x + w, 1560.1)
                self.assertLessEqual(y + h, 940.1)
                for x2, y2, w2, h2 in bounds[i + 1:]:
                    self.assertFalse(x < x2 + w2 and x2 < x + w and y < y2 + h2 and y2 < y + h)

    def test_hidden_virtual_monitor_is_omitted_but_source_is_always_visible(self):
        virtual = copy.deepcopy(self.ipc.data["monitors"][1])
        virtual.update(id=2, name="STUDIO-VIRTUAL", x=5040)
        virtual["activeWorkspace"]["id"] = 21
        self.ipc.data["monitors"].append(virtual)
        self.ipc.data["workspaces"].append({"id": 21, "name": "21", "monitor": "STUDIO-VIRTUAL"})
        self.begin()
        self.assertEqual(len(self.controller.drag.groups), 2)
        self.assertNotIn("STUDIO-VIRTUAL", [g["monitor"] for g in self.controller.drag.groups])
        self.controller.finish("a", cancel=True)
        self.ipc.data["clients"][0].update(workspace={"id": 21, "name": "21"}, at=[5040, 0], size=[1920, 1080])
        self.ipc.data["cursorpos"] = {"x": 5100, "y": 100}
        self.controller.begin("b")
        self.assertIn("STUDIO-VIRTUAL", [g["monitor"] for g in self.controller.drag.groups])

    def test_global_logical_hit_test_and_rotated_monitor(self):
        m = logical_monitor(dict(x=1600, y=300, width=1600, height=2560, scale=1.6, transform=1))
        self.assertEqual((m["logicalWidth"], m["logicalHeight"]), (1600, 1000))
        cards, _ = layout_dashboard([dict(name="1", monitor="DP-6")], m, DEFAULTS)
        c = cards[0]
        self.assertEqual(target_at(cards, m, {"x": 1600 + c["x"] + 1, "y": 300 + c["y"] + 1})["name"], "1")
        self.assertIsNone(target_at(cards, m, {"x": 0, "y": 0}))

    def test_configured_empty_and_existing_workspaces_not_arbitrary_defaults(self):
        monitors = [logical_monitor(m) for m in self.ipc.data["monitors"]]
        targets = workspace_targets(monitors, self.ipc.data["workspaces"], self.ipc.data["workspacerules"], DEFAULTS, monitors[0])
        self.assertEqual([t["name"] for t in targets], ["1", "2", "4", "5"])
        self.assertEqual(targets[-1]["monitor"], "DP-6")

    def test_incidental_rules_do_not_synthesize_phantom_targets(self):
        self.ipc.data["workspacerules"] += [
            {"workspaceString": "12", "enabled": True},
            {"workspaceString": "13", "gapsOut": 0},
            {"workspaceString": "7", "persistent": True},
            {"workspaceString": "8", "default": True}]
        self.begin()
        self.assertEqual([c["name"] for c in self.controller.drag.cards], ["1", "2", "3", "4", "5", "11", "12", "13", "14", "15"])

    def test_only_incidental_rules_preserve_configured_default_fallback(self):
        monitors = [logical_monitor(m) for m in self.ipc.data["monitors"]]
        targets = workspace_targets(monitors, self.ipc.data["workspaces"],
                                    [{"workspaceString": "12", "enabled": True}],
                                    DEFAULTS | {"defaultWorkspaces": [7]}, monitors[0])
        self.assertEqual([c["name"] for c in targets], ["1", "7", "4"])

    def test_local_label_preserves_dispatch_hover_and_thumbnail_identity(self):
        self.ipc.data["workspaces"] += [{"id": 13, "name": "13", "monitor": "DP-6"},
                                        {"id": 6, "name": "6", "monitor": "DP-6"}]
        client = copy.deepcopy(self.ipc.data["clients"][0])
        client.update(address="0xdef", workspace={"id": 13, "name": "13"}, monitor=1)
        self.ipc.data["clients"].append(client)
        self.begin()
        card = next(c for c in self.controller.drag.cards if c["name"] == "13")
        self.assertEqual(card["label"], "3")
        external = [c for c in self.controller.drag.cards if c["monitor"] == "DP-6"]
        self.assertEqual([(c["name"], c["label"]) for c in external], [("11", "1"), ("12", "2"), ("13", "3"), ("14", "4"), ("15", "5"), ("6", "6")])
        guest = next(c for c in self.controller.drag.cards if c["name"] == "4")
        self.assertEqual(guest["label"], "4")
        self.assertTrue(guest["disabled"])
        self.assertEqual(next(c for c in self.output[-1]["clients"] if c["address"] == "0xdef")["workspace"]["name"], "13")
        self.assertEqual(self.output[-1]["sourceWorkspace"], "1")
        self.assertEqual(self.output[-1]["sourceWorkspaceLabel"], "1")
        self.aim("13")
        self.controller.tick()
        self.assertEqual(self.output[-1]["hovered"], "13")
        self.controller.finish("a")
        self.assertIn('workspace="13",follow=false', self.ipc.dispatches[0])

    def test_reserved_guest_id_is_not_duplicated_on_its_current_monitor(self):
        self.ipc.data["workspaces"].append({"id": 14, "name": "14", "monitor": "DP-6"})
        self.begin()
        external = [c for c in self.controller.drag.cards if c["monitor"] == "DP-6"]
        self.assertEqual([(c["name"], c["label"]) for c in external],
                         [("11", "1"), ("12", "2"), ("13", "3"), ("14", "4"), ("15", "5")])
        self.assertEqual(next(c for c in self.controller.drag.cards if c["name"] == "1")["label"], "1")
        self.aim("14")
        self.controller.finish("a")
        self.assertIn('workspace="14",follow=false', self.ipc.dispatches[0])

    def test_source_label_matches_card_and_misassigned_destination_cancels(self):
        self.ipc.data["monitors"][1]["activeWorkspace"] = {"id": 14}
        self.ipc.data["clients"][0].update(workspace={"id": 14, "name": "14"},
                                             monitor=1, at=[1600, 0], size=[3440, 1440])
        self.ipc.data["workspaces"].append({"id": 14, "name": "14", "monitor": "DP-6"})
        self.ipc.data["cursorpos"] = {"x": 1800, "y": 400}
        self.begin()
        self.assertEqual(self.output[-1]["sourceWorkspace"], "14")
        self.assertEqual(self.output[-1]["sourceWorkspaceLabel"], "4")
        self.assertEqual(self.output[-1]["sourceWorkspaceLabel"],
                         next(c for c in self.controller.drag.cards if c["name"] == "14")["label"])
        self.aim("4")
        self.controller.finish("a")
        self.assertFalse(self.ipc.dispatches)

    def test_extra_guest_and_local_labels_remain_distinct(self):
        self.ipc.data["workspaces"] += [{"id": 8, "name": "8", "monitor": "DP-6"},
                                        {"id": 18, "name": "18", "monitor": "DP-6"}]
        self.begin()
        self.assertEqual({c["name"]: c["label"] for c in self.controller.drag.cards if c["name"] in ("8", "18")},
                         {"8": "8 (ID 8)", "18": "8 (ID 18)"})
        self.aim("18")
        self.controller.finish("a")
        self.assertIn('workspace="18",follow=false', self.ipc.dispatches[0])

    def test_source_label_uses_source_monitor_and_keeps_global_identity(self):
        self.ipc.data["monitors"][1]["activeWorkspace"] = {"id": 13}
        self.ipc.data["clients"][0].update(workspace={"id": 13, "name": "13"},
                                             monitor=1, at=[1600, 0], size=[3440, 1440])
        self.ipc.data["workspaces"].append({"id": 13, "name": "13", "monitor": "DP-6"})
        self.ipc.data["cursorpos"] = {"x": 1800, "y": 400}
        self.begin()
        self.assertEqual(self.output[-1]["sourceWorkspace"], "13")
        self.assertEqual(self.output[-1]["sourceWorkspaceLabel"], "3")
        self.aim("13")
        self.controller.finish("a")
        self.assertFalse(self.ipc.dispatches)

    def test_preview_refreshes_blocks_and_preserves_named_and_guest_labels(self):
        self.ipc.data["workspaces"] += [{"id": 13, "name": "13", "monitor": "DP-6"},
                                        {"id": -1337, "name": "Praca Żółć", "monitor": "DP-6"}]
        self.controller.preview("preview-a", {})
        labels = {c["name"]: c["label"] for c in self.output[-1]["cards"]}
        self.assertEqual(labels, {**{str(i): str(i) for i in range(1, 6)},
                                  **{str(i + 10): str(i) for i in range(1, 6)}, "Praca Żółć": "Praca Żółć"})
        self.controller.finish("preview-a")
        self.blocks.return_value = {}
        self.controller.preview("preview-b", {})
        self.assertEqual(next(c for c in self.output[-1]["cards"] if c["name"] == "13")["label"], "13")
        self.assertEqual(self.blocks.call_count, 2)

    def test_empty_monitors_keep_five_local_slots_without_legacy_phantoms(self):
        self.ipc.data["workspaces"] = []
        self.ipc.data["workspacerules"] += [{"workspaceString": "6", "monitor": "eDP-1"},
                                            {"workspaceString": "18", "persistent": True}]
        self.controller.preview("empty", {})
        for group, base in zip(self.controller.drag.groups, (0, 10)):
            self.assertEqual([c["name"] for c in group["cards"]], [str(base + i) for i in range(1, 6)])
            self.assertEqual([c["label"] for c in group["cards"]], list("12345"))
            self.assertFalse(any(c["existing"] or c["disabled"] for c in group["cards"]))
        self.assertEqual(self.blocks.call_count, 1)

    def test_extra_existing_numeric_named_and_guest_workspaces_remain_unique(self):
        self.ipc.data["workspaces"] += [{"id": 18, "name": "18", "monitor": "DP-6"},
                                        {"id": 28, "name": "28", "monitor": "DP-6"},
                                        {"id": -1337, "name": "Praca", "monitor": "DP-6"}]
        self.begin()
        cards = self.controller.drag.cards
        self.assertEqual(len(cards), len({c["name"] for c in cards}))
        self.assertEqual({c["name"]: c["label"] for c in cards if not c.get("slot")},
                         {"18": "8", "28": "28", "Praca": "Praca"})
        self.assertTrue(next(c for c in cards if c["name"] == "4")["disabled"])

    def test_unmapped_monitor_keeps_legacy_rules(self):
        self.blocks.return_value = {"eDP-1": 0}
        self.ipc.data["workspaces"][1].update(id=6, name="6")
        self.ipc.data["workspacerules"][1]["workspaceString"] = "7"
        self.begin()
        self.assertEqual([c["name"] for c in self.controller.drag.cards if c["monitor"] == "DP-6"], ["6", "7"])

    def test_misassigned_slot_is_visible_disabled_and_cannot_be_hit(self):
        self.begin()
        self.aim("4")
        self.controller.tick()
        self.assertEqual(self.output[-1]["hovered"], "")
        self.controller.finish("a")
        self.assertFalse(self.ipc.dispatches)

    def test_target_becoming_misassigned_cancels_release(self):
        self.begin()
        self.aim("15")
        self.ipc.data["workspaces"].append({"id": 15, "name": "15", "monitor": "eDP-1"})
        self.controller.finish("a")
        self.assertFalse(self.ipc.dispatches)

    def test_changed_or_removed_block_mapping_cancels_release(self):
        for mapping in ({"eDP-1": 0, "DP-6": 3}, {}):
            with self.subTest(mapping=mapping):
                self.controller.ended.clear()
                self.blocks.return_value = {"eDP-1": 0, "DP-6": 1}
                self.begin()
                self.aim("15")
                self.blocks.return_value = mapping
                self.controller.finish("a")
                self.assertFalse(self.ipc.dispatches)
        self.assertEqual(self.blocks.call_count, 4)

    def test_hidden_virtual_keeps_five_slots_when_it_is_the_source(self):
        self.blocks.return_value = {"eDP-1": 0, "DP-6": 1, "STUDIO-VIRTUAL": 2}
        self.ipc.data["monitors"][1]["name"] = "STUDIO-VIRTUAL"
        self.ipc.data["monitors"][1]["activeWorkspace"] = {"id": 21}
        self.ipc.data["clients"][0].update(workspace={"id": 21, "name": "21"}, at=[1600, 0])
        self.ipc.data["cursorpos"] = {"x": 1800, "y": 100}
        self.begin()
        self.assertEqual([c["name"] for c in self.controller.drag.cards if c["monitor"] == "STUDIO-VIRTUAL"],
                         ["21", "22", "23", "24", "25"])

    @unittest.skipUnless(shutil.which("lua"), "Lua interpreter unavailable")
    def test_lua_guards_and_new_slot_binding_run_before_any_window_mutation(self):
        self.begin()
        self.aim("15")
        self.controller.finish("a")
        lua = self.ipc.dispatches[0]
        self.assertIn('hl.workspace_rule({workspace="15",monitor="DP-6"})', lua)
        self.assertLess(lua.index("hl.workspace_rule"), lua.index("hl.dsp.window.move"))
        self.assertNotIn("move({window=w,monitor", lua)
        # Execute the exact generated Lua with deterministic objects, including races
        # after the Python snapshot. A failed guard must leave all mutations at zero.
        for scenario in ("empty", "existing", "wrong-monitor", "missing-monitor", "changed-source", "missing-source"):
            with self.subTest(scenario=scenario):
                harness = """
local scenario = %s
local calls = {}
local w = {address="0xabc",workspace={id=scenario=="changed-source" and 2 or 1}}
local target = scenario=="empty" and nil or {monitor={name=scenario=="wrong-monitor" and "eDP-1" or "DP-6"}}
if scenario=="empty" then target=nil end
hl = {
 get_monitor=function(name) assert(name=="DP-6"); if scenario~="missing-monitor" then return {name=name} end end,
 get_window=function(address) assert(address=="address:0xabc"); if scenario~="missing-source" then return w end end,
 get_workspace=function(id) assert(id==15); return target end,
 workspace_rule=function(rule) assert(rule.workspace=="15" and rule.monitor=="DP-6"); table.insert(calls,"bind") end,
 dispatch=function(command) table.insert(calls,command) end,
 dsp={window={
 fullscreen_state=function(args) assert(args.window==w); return "fullscreen" end,
 float=function(args) assert(args.window==w); return "float" end,
 move=function(args) assert(args.window==w and args.workspace=="15" and args.follow==false and args.monitor==nil); return "move" end}}
}
local ok = pcall(function() %s end)
if scenario=="empty" then assert(ok and table.concat(calls,",")=="bind,fullscreen,float,move")
elseif scenario=="existing" then assert(ok and table.concat(calls,",")=="fullscreen,float,move")
else assert(not ok and #calls==0) end
""" % ('"' + scenario + '"', lua)
                result = subprocess.run(["lua", "-"], input=harness, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_demo_never_moves_real_windows(self):
        self.controller.demo()
        self.time += .5
        self.controller.finish("demo")
        self.assertFalse(self.ipc.dispatches)
        self.assertFalse(self.controller.drag)

    def test_preview_uses_real_workspaces_clients_and_draft_appearance(self):
        appearance = {"backgroundOpacity": .34, "previewMode": "titles", "cardScale": 1.7, "zoom": 1.3}
        with patch("pathlib.Path.write_text", side_effect=AssertionError("preview wrote a file")):
            self.assertTrue(self.controller.preview("preview-a", appearance))
            data = self.output[-1]
            self.assertEqual(data["mode"], "preview")
            self.assertFalse(data["demo"])
            self.assertEqual(data["backgroundOpacity"], .34)
            self.assertEqual(data["previewMode"], "titles")
            self.assertEqual(data["zoom"], 1.3)
            expected, _ = layout_dashboard(
                [{k: v for k, v in c.items() if k not in ("x", "y", "width", "height")} for c in data["cards"]],
                self.controller.drag.monitor, self.controller.config)
            self.assertEqual(data["cards"], expected)
            self.assertEqual(self.controller.config["cardScale"], 1.7)
            self.assertEqual(data["source"], "")
            self.assertEqual(data["sourceWorkspace"], "")
            self.assertEqual([c["name"] for c in data["cards"]], ["1", "2", "3", "4", "5", "11", "12", "13", "14", "15"])
            self.assertEqual([g["monitor"] for g in data["groups"]], ["eDP-1", "DP-6"])
            self.assertEqual(data["clients"][0]["address"], "0xabc")
            self.assertEqual(data["clients"][0]["title"], "PRIVATE NEVER SERIALIZE")
        self.assertFalse(self.ipc.dispatches)
        self.assertFalse(self.ipc.requests)

    def test_preview_release_cancel_and_timeout_never_restore_cursor_or_move(self):
        for ending in ("release", "cancel", "timeout"):
            with self.subTest(ending=ending):
                self.setUp()
                self.controller.preview("preview-a", {})
                self.time += .5
                self.aim("5")
                if ending == "timeout":
                    self.time += 130
                    self.controller.tick()
                else:
                    self.controller.finish("preview-a", cancel=ending == "cancel")
                self.time += 1
                self.controller.tick()
                self.assertIsNone(self.controller.drag)
                self.assertIsNone(self.controller.restore)
                self.assertFalse(self.ipc.dispatches)
                self.assertFalse(self.ipc.requests)

    def test_preview_reloads_saved_config_and_next_drag_discards_draft(self):
        saved = DEFAULTS | {"backgroundOpacity": .8, "previewMode": "thumbnails", "cardWidth": 345, "cardScale": .8, "zoom": 1.1}
        self.controller.config = DEFAULTS | {"cardWidth": 123}
        with patch("backend.load_config", side_effect=lambda: saved.copy()):
            self.controller.preview("preview-a", {"backgroundOpacity": .22, "previewMode": "titles", "cardScale": 2, "zoom": 1.35})
            self.assertEqual(self.controller.config["cardWidth"], 345)
            self.assertEqual(self.controller.config["backgroundOpacity"], .22)
            self.controller.finish("preview-a", cancel=True)
            self.begin()
        self.assertEqual(self.controller.config["backgroundOpacity"], .8)
        self.assertEqual(self.controller.config["previewMode"], "thumbnails")
        self.assertEqual(self.controller.config["cardScale"], .8)
        self.assertEqual(self.controller.config["zoom"], 1.1)
        self.assertEqual(saved["cardScale"], .8)
        self.assertEqual(saved["zoom"], 1.1)
        self.assertEqual(saved["backgroundOpacity"], .8)

    def test_invalid_preview_does_not_replace_active_drag(self):
        invalid = (None, [], {"backgroundOpacity": True}, {"backgroundOpacity": float("nan")},
                           {"backgroundOpacity": float("inf")}, {"backgroundOpacity": .09},
                           {"backgroundOpacity": 1.01}, {"previewMode": "unknown"}, {"restoreCursor": False})
        invalid += tuple({key: value} for key, outside in (("cardScale", (.49, 2.01)), ("zoom", (.99, 1.36)))
                         for value in (*outside, True, False, float("nan"), float("inf"), -float("inf"), "1", None))
        for appearance in invalid:
            self.assertFalse(self.controller.preview("invalid", appearance))
            self.assertIsNone(self.controller.drag)
        self.begin()
        original = self.controller.drag
        for appearance in invalid:
            with self.subTest(appearance=appearance):
                self.assertFalse(self.controller.preview("preview-a", appearance))
                self.assertIs(self.controller.drag, original)
        self.assertFalse(self.controller.preview("preview-a", {}))
        self.controller.demo()
        self.assertIs(self.controller.drag, original)
        self.assertFalse(self.ipc.dispatches)

    def test_preview_accepts_partial_size_and_hover_at_range_limits(self):
        saved = DEFAULTS.copy()
        for appearance in ({"cardScale": .5}, {"cardScale": 2}, {"zoom": 1}, {"zoom": 1.35}):
            with self.subTest(appearance=appearance), patch("backend.load_config", return_value=saved.copy()):
                self.assertTrue(self.controller.preview("partial", appearance))
                self.assertEqual(self.controller.config["cardScale"], appearance.get("cardScale", saved["cardScale"]))
                self.assertEqual(self.controller.config["zoom"], appearance.get("zoom", saved["zoom"]))
                self.controller.finish("partial", cancel=True)
        self.assertEqual(saved, DEFAULTS)
        self.assertFalse(self.ipc.dispatches)
        self.assertFalse(self.ipc.requests)

    def test_preview_prevents_drag_start_and_supports_empty_clients(self):
        self.ipc.data["clients"] = []
        self.controller.preview("preview-a", {})
        self.assertEqual(self.output[-1]["clients"], [])
        self.assertEqual(len(self.controller.drag.cards), 10)
        original = self.controller.drag
        self.controller.begin("a")
        self.assertIs(self.controller.drag, original)
        self.controller.finish("a")
        self.assertIs(self.controller.drag, original)
        self.assertFalse(self.ipc.dispatches)

    def test_preview_chooses_pointer_monitor_then_focused_fallback(self):
        self.ipc.data["monitors"][0]["focused"] = True
        self.ipc.data["cursorpos"] = {"x": 2000, "y": 100}
        self.controller.preview("preview-a", {})
        self.assertEqual(self.output[-1]["screen"], "DP-6")
        self.controller.finish("preview-a", cancel=True)
        self.ipc.data["cursorpos"] = {"x": -100, "y": -100}
        self.controller.preview("preview-b", {})
        self.assertEqual(self.output[-1]["screen"], "eDP-1")

    def test_preview_without_monitor_is_rejected_truthfully(self):
        self.ipc.data["monitors"] = []
        self.assertFalse(self.controller.preview("preview-a", {}))
        self.assertEqual(self.output[-1]["state"], "preview-result")
        self.assertFalse(self.output[-1]["ok"])
        self.assertIsNone(self.controller.drag)
        self.assertFalse(self.ipc.dispatches)

    def test_native_press_source_address_is_authoritative(self):
        background = copy.deepcopy(self.ipc.data["clients"][0])
        background.update(address="0xdef", fullscreen=2, floating=False, focusHistoryID=1)
        self.ipc.data["clients"][0].update(fullscreen=0, focusHistoryID=0)
        self.ipc.data["clients"].append(background)
        self.controller.begin("a", {"x": 600, "y": 400, "sourceAddress": "0xabc"})
        self.assertEqual(self.controller.drag.source["address"], "0xabc")
        self.assertEqual(self.output[-1]["source"], "0xabc")

    def test_press_and_release_coordinates_survive_ipc_delay(self):
        self.ipc.data["cursorpos"] = {"x": 1700, "y": 20}
        self.controller.begin("a", {"x": 600, "y": 400})
        self.assertIsNotNone(self.controller.drag)
        self.time += .5
        self.aim("2")
        release = self.ipc.data["cursorpos"]
        self.ipc.data["cursorpos"] = {"x": 1700, "y": 20}
        self.controller.finish("a", pointer=release)
        self.assertIn('workspace="2",follow=false', self.ipc.dispatches[0])

    def test_named_unicode_workspace_is_preserved_and_lua_quoted(self):
        self.ipc.data["workspaces"].append({"id": -1337, "name": 'Praca Żółć "test"', "monitor": "DP-6"})
        named = copy.deepcopy(self.ipc.data["clients"][0])
        named.update(address="0xdef", workspace={"id": -1337, "name": 'Praca Żółć "test"'})
        self.ipc.data["clients"].append(named)
        special = copy.deepcopy(named)
        special.update(address="0xaaa", workspace={"id": -99, "name": "special:dock"})
        self.ipc.data["clients"].append(special)
        self.begin()
        self.assertIn("0xdef", [c["address"] for c in self.controller.drag.clients])
        self.assertNotIn("0xaaa", [c["address"] for c in self.controller.drag.clients])
        self.aim('Praca Żółć "test"')
        self.controller.finish("a")
        self.assertIn('name:Praca Żółć', self.ipc.dispatches[0])
        self.assertIn('\\"test\\"', self.ipc.dispatches[0])

    def test_cursor_returns_only_after_overlay_is_hidden(self):
        self.begin()
        self.aim("2")
        self.controller.finish("a", cancel=True)
        self.controller.tick()
        self.assertFalse(self.ipc.requests)
        self.time += .2
        self.controller.tick()
        self.assertEqual(self.ipc.dispatches, ["hl.dispatch(hl.dsp.cursor.move({x=600,y=400}))"])
        self.assertFalse(self.ipc.requests)


class WorkspaceBlockTests(unittest.TestCase):
    def test_map_loader_handles_missing_malformed_and_ambiguous_entries(self):
        from backend import load_workspace_blocks, workspace_label
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_STATE_HOME": directory}):
            state = Path(directory) / "omarchy" / "monitor-workspaces"
            self.assertEqual(load_workspace_blocks(), {})
            state.parent.mkdir()
            state.write_text("0\teDP-1\tLaptop\n1\tDP-6\tExternal\n2\tSTUDIO-VIRTUAL\tVirtual\n")
            self.assertEqual(load_workspace_blocks(), {"eDP-1": 0, "DP-6": 1, "STUDIO-VIRTUAL": 2})
            self.assertEqual(workspace_label("13", "DP-6", load_workspace_blocks()), "3")
            state.write_text("bogus\tDP-6\tExternal\n-1\teDP-1\tLaptop\n2\t\tBlank\n3\tIncomplete\n")
            self.assertEqual(load_workspace_blocks(), {})
            self.assertEqual(workspace_label("13", "DP-6", load_workspace_blocks()), "13")
            state.write_text("0\teDP-1\tLaptop\n1\tDP-6\tExternal\n2\tDP-6\tDuplicate\n0\tOTHER\tDuplicate block\n")
            self.assertEqual(load_workspace_blocks(), {})

    def test_labels_change_only_numeric_workspaces_in_the_monitors_own_block(self):
        from backend import workspace_label
        blocks = {"eDP-1": 0, "DP-6": 1}
        for name, monitor, expected in [("13", "DP-6", "3"), ("20", "DP-6", "10"),
                                         ("1", "eDP-1", "1"), ("4", "DP-6", "4"),
                                         ("13", "eDP-1", "13"), ("13", "UNKNOWN", "13"),
                                         ("0", "eDP-1", "0"), ("Praca", "DP-6", "Praca")]:
            with self.subTest(name=name, monitor=monitor):
                self.assertEqual(workspace_label(name, monitor, blocks), expected)


if __name__ == "__main__":
    unittest.main()
