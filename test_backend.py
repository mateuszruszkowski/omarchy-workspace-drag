import copy
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
            self.aim("5")
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
                [dict(name=c["name"], monitor=c["monitor"], existing=c["existing"]) for c in data["cards"]],
                self.controller.drag.monitor, self.controller.config)
            self.assertEqual(data["cards"], expected)
            self.assertEqual(self.controller.config["cardScale"], 1.7)
            self.assertEqual(data["source"], "")
            self.assertEqual(data["sourceWorkspace"], "")
            self.assertEqual([c["name"] for c in data["cards"]], ["1", "2", "4", "5"])
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
        self.assertEqual(len(self.controller.drag.cards), 4)
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


if __name__ == "__main__":
    unittest.main()
