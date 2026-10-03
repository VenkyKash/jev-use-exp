import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_core import Observation, Task
from driver_candidates import native_extras
from native_driver import NativeDriver, DriverFailure, normalize


class DeliveryTest(unittest.TestCase):
    def test_unresolved_window_without_snapshot_allows_only_unindexed_observation(self):
        raw = dict(pid=10, window_id=20, elements=[], degraded=True,
                   background_input={"exact_window": {"status": "ax_unresolved"},
                                     "routes": [{"route": "pid_keyboard", "status": "refused"}]})
        obs = normalize(raw, 10, 20)
        self.assertFalse(obs.complete)
        self.assertTrue(obs.id.startswith("unindexed-"))
        candidates = native_extras(Task("Task", "App", (), ()), obs, lambda *_: True)
        self.assertEqual({c.id for c in candidates}, {"activate-window"})
        self.assertNotIn("hotkey-cmd-t", {c.id for c in candidates})
        self.assertTrue(all("element_token" not in c.arguments and "element_index" not in c.arguments for c in candidates))
        with self.assertRaises(Exception):
            normalize({**raw, "pid": 11}, 10, 20)
    def test_native_candidates_do_not_automatically_attach_browser(self):
        from native_core import Element
        web = Element(1, "AXLink", "Page", None, "s1:1", ("AXPress",), True, None, True)
        obs = Observation("s1", 10, 20, (web,))
        candidates = native_extras(Task("Task", "Browser", (), ()), obs, lambda *_: True,
                                  result={"target_id": "browser", "tabs": [{"tab_id": "tab"}]})
        self.assertNotIn("get_browser_state", {c.tool for c in candidates})

    def test_refused_background_keyboard_keeps_explicit_foreground_option(self):
        report = {"routes": [{"route": "pid_keyboard", "status": "refused", "reason": "ambiguous"}]}
        from native_core import Element
        obs = Observation("s1", 10, 20,
                          (Element(0, "AXTextField", "Field", "", "s1:0", (), True, None, False),),
                          background_input=report)
        task = Task("Task", "App", ("text",), ())
        candidates = native_extras(task, obs, lambda *_: True)
        keyboard = [c for c in candidates if c.tool in {"press_key", "hotkey", "type_text"}]
        self.assertTrue(keyboard)
        self.assertTrue(all(c.arguments["delivery_mode"] == "foreground" for c in keyboard))
        self.assertTrue(all(c.arguments["window_id"] == 20 for c in keyboard))
        available = replace(obs, background_input={"routes": [{"route": "pid_keyboard", "status": "available"}]})
        self.assertIn("key-return", {c.id for c in native_extras(task, available, lambda *_: True)})
        self.assertNotIn("key-return-foreground", {c.id for c in native_extras(task, obs,
            lambda tool, args: args.get("delivery_mode") != "foreground")})

    def test_normalization_preserves_report(self):
        report = {"routes": [{"route": "pid_keyboard", "status": "refused"}]}
        obs = normalize({"snapshot_id": "s1", "elements": [], "background_input": report}, 10, 20)
        self.assertEqual(obs.background_input, report)


class DiagnosticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_tool_action_failure_is_observed_before_jev_reselection(self):
        from test_native import FixtureDriver, ScriptedTestChooser
        from native_run import run_loop
        class Driver(FixtureDriver):
            async def call(self, tool, args):
                if tool != "launch_app":
                    raise DriverFailure("driver_tool_error", "AX failed", driver_code="tool_invocation_failed",
                                        driver_response="AXShowMenu returned -25204")
                return await super().call(tool, args)
        chooser = ScriptedTestChooser(["type-0-0", "abstain"])
        events = []
        result = await run_loop(Task("Fill", "Fixture", ("Ada",), ()), Driver(), chooser, events.append)
        self.assertEqual(result, "abstained")
        history = chooser.requests[1]["history"][-1]
        self.assertEqual(history["outcome"], "action_failed_effect_unknown")
        self.assertIn("-25204", history["error_details"])
        self.assertTrue(any(e["event"] == "failure_readback" for e in events))

    async def test_off_space_refusal_recovers_but_uncertain_action_does_not(self):
        from test_native import FixtureDriver, ScriptedTestChooser
        from native_run import run_loop
        for effect, expected in (("refused", "abstained"), ("unverifiable", "unknown")):
            class Driver(FixtureDriver):
                async def call(self, tool, args):
                    if tool != "launch_app":
                        raise DriverFailure("driver_tool_error", "route failure", driver_effect=effect,
                                            driver_code="off_space_or_ax_unresolved")
                    return await super().call(tool, args)
            chooser = ScriptedTestChooser(["type-0-0", "abstain"])
            events = []
            result = await run_loop(Task("Fill", "Fixture", ("Ada",), ()), Driver(), chooser, events.append)
            self.assertEqual(result, expected)
            self.assertEqual(any(e["event"] == "refusal_recovery" for e in events), effect == "refused")

    async def test_explicit_refusal_refreshes_and_returns_control_to_jev(self):
        from test_native import FixtureDriver, ScriptedTestChooser
        from native_run import run_loop
        class RefusingDriver(FixtureDriver):
            async def call(self, tool, args):
                if tool != "launch_app":
                    raise DriverFailure("driver_tool_error", "refused", driver_effect="refused",
                                        driver_code="element_outside_target_window")
                return await super().call(tool, args)
        chooser = ScriptedTestChooser(["type-0-0", "abstain"])
        events = []
        outcome = await run_loop(Task("Fill", "Fixture", ("Ada",), ()), RefusingDriver(), chooser, events.append)
        self.assertEqual(outcome, "abstained")
        self.assertEqual(chooser.requests[1]["history"][-1]["outcome"], "refused_before_execution")
        self.assertTrue(any(e["event"] == "refusal_recovery" for e in events))

    async def test_error_retains_text_and_structured_reason_without_api_key(self):
        class Session:
            async def call_tool(self, *args):
                return SimpleNamespace(isError=True, structuredContent={"refusal": "ambiguous_target"},
                                       content=[SimpleNamespace(text="Refused test-secret " + "x"*5000)])
        driver = NativeDriver(Session(), "test", {"press_key": {"type": "object", "properties": {}}})
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-secret"}):
            with self.assertRaises(DriverFailure) as raised:
                await driver.call("press_key", {})
        details = raised.exception.details
        self.assertIn("ambiguous_target", details["driver_response"])
        self.assertNotIn("test-secret", details["driver_response"])
        self.assertEqual(len(details["driver_response"]), 4000)
        self.assertGreater(details["omitted_characters"], 0)
