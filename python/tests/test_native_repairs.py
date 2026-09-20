import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx2
from native_audit import HttpAudit
from native_candidates import build_native_candidates
from native_core import Task
from native_driver import normalize, select_window
from native_errors import DiagnosticError, error_details
from native_fixture import FixtureDriver
from native_jev import JevChooser
from native_run import run_loop
from test_native import ScriptedTestChooser, snapshot, task


class WindowSelectionTest(unittest.TestCase):
    def test_unnamed_auxiliary_windows_do_not_block_unique_named_window(self):
        windows = [dict(window_id=i, title="", is_on_screen=False, pid=7) for i in range(1,5)]
        windows += [dict(window_id=5, title="Document", is_on_screen=False, pid=7)]
        self.assertEqual(select_window(windows, 7), 5)

    def test_named_documents_remain_ambiguous_despite_visibility_or_order(self):
        windows = [dict(window_id=1, title="A", is_on_screen=False),
                   dict(window_id=2, title="B", is_on_screen=True)]
        self.assertIsNone(select_window(windows, 7))
        self.assertIsNone(select_window(windows[::-1], 7))
        self.assertIsNone(select_window([dict(window_id=1, title="A"),
                                         dict(window_id=2, title="", is_on_screen=True)], 7))

    def test_other_process_invalid_and_duplicate_ids_not_selected(self):
        self.assertIsNone(select_window([dict(window_id=1, title="A", pid=8)], 7))
        self.assertIsNone(select_window([dict(window_id=True, title="A")], 7))
        self.assertIsNone(select_window([dict(window_id=1, title="A")]*2, 7))
        self.assertIsNone(select_window([dict(window_id=1, title="", is_on_screen=False)], 7))


class ScopeTest(unittest.TestCase):
    def test_menu_descendants_excluded_before_observation_and_candidate_limits(self):
        raw = snapshot()
        raw["elements"].append(dict(element_index=10, role="AXMenuBar", label=None))
        raw["elements"] += [dict(element_index=i, role="AXMenuItem", label=f"Menu {i}",
                                 actions=["AXPress"], parent_index=10) for i in range(11,240)]
        raw["elements"].append(dict(element_index=240, role="AXButton", label="Nested", parent_index=12))
        obs = normalize(raw, 1, 2)
        self.assertEqual(len(obs.elements), 3)
        self.assertEqual(obs.excluded_menu_elements, 231)
        options = build_native_candidates(task(), obs, lambda *_: True)
        self.assertEqual({c.id for c in options.candidates}, {"type-0-0", "click-1", "reobserve", "abstain"})
        self.assertEqual(options.resolve("click-1", obs.id).arguments["element_token"], "s1:1")

    def test_window_controls_are_not_pruned_to_fit_budget(self):
        raw = dict(snapshot_id="s", elements=[dict(element_index=i, role="AXButton", label=str(i)) for i in range(63)])
        obs = normalize(raw, 1, 2)
        with self.assertRaises(DiagnosticError) as raised:
            build_native_candidates(task(), obs, lambda *_: True)
        self.assertEqual(raised.exception.code, "candidate_limit")

    def test_null_label_normalized_but_not_clickable(self):
        raw = snapshot()
        raw["elements"][1]["label"] = None
        obs = normalize(raw, 1, 2)
        self.assertEqual(obs.elements[1].label, "")
        self.assertNotIn("click-1", {c.id for c in build_native_candidates(task(), obs, lambda *_: True).candidates})

    def test_incomplete_observation_cannot_prove_unique_completion(self):
        from native_core import verify
        raw = dict(**snapshot(value="Done"), elements_complete=False)
        self.assertFalse(verify(task(), normalize(raw, 1, 2)))

    def test_parent_cycles_fail_closed(self):
        raw = snapshot()
        raw["elements"][0]["parent_index"] = 1
        raw["elements"][1]["parent_index"] = 0
        with self.assertRaises(DiagnosticError):
            normalize(raw, 1, 2)


class AuditTest(unittest.TestCase):
    def test_http_audit_excludes_credentials_bodies_and_query(self):
        events = []
        hooks = HttpAudit(events.append)
        request = httpx2.Request("POST", "https://user:pass@example.test/v1/systemone?secret=hidden",
                                headers={"Authorization": "Bearer TOP_SECRET"}, content=b"PRIVATE BODY")
        hooks.request(request)
        response = httpx2.Response(200, request=request,
            headers={"x-typesafe-request-id": "test-request", "set-cookie": "PRIVATE_COOKIE"})
        hooks.response(response)
        rendered = json.dumps(events)
        for secret in ["TOP_SECRET", "PRIVATE", "hidden", "pass", "user:"]:
            self.assertNotIn(secret, rendered)
        self.assertEqual(events[0]["audit_id"], events[1]["audit_id"])
        self.assertEqual(events[1]["request_id"], "test-request")
        self.assertEqual(events[1]["status"], 200)

    def test_nested_diagnostics_keep_codes_but_not_arbitrary_error_messages(self):
        try:
            group = ExceptionGroup("SECRET", [DiagnosticError("missing_snapshot", "not logged", has_snapshot=False),
                                              RuntimeError("Bearer TOP_SECRET")])
        except NameError:
            self.skipTest("ExceptionGroup requires Python 3.11")
        info = error_details(group)
        self.assertEqual(info["causes"][0]["code"], "missing_snapshot")
        self.assertNotIn("SECRET", json.dumps(info))


class RuntimeRepairTest(unittest.IsolatedAsyncioTestCase):
    async def test_unique_titled_window_allows_jev_actions_after_launch(self):
        class MultipleWindows(FixtureDriver):
            async def call(self, tool, arguments):
                result = await super().call(tool, arguments)
                if tool == "launch_app":
                    result["windows"] = [dict(window_id=8, title="", is_on_screen=False), dict(window_id=2, title="Form")]
                return result
        spec = Task.parse(dict(goal="Fill form", app="Fixture", inputs=["Ada", "Paris"],
            checks=[dict(role="AXStaticText", label="Receipt", equals="Ada | Paris")]))
        driver = MultipleWindows()
        events = []
        chooser = ScriptedTestChooser(["type-0-0", "type-1-1", "click-2"])
        self.assertEqual(await run_loop(spec, driver, chooser, events.append), "verified")
        self.assertEqual(next(e["window_id"] for e in events if e["event"] == "target_bound"), 2)

    async def test_provider_answer_is_retained_before_rejection(self):
        events = []
        class Client:
            def system_one(self, **kwargs):
                return SimpleNamespace(model="test", usage=SimpleNamespace(input_tokens=3, output_tokens=1),
                    choices={"candidate": SimpleNamespace(choice="invented", confidence=.9, probabilities={"invented": 1})})
        with self.assertRaises(DiagnosticError):
            await JevChooser(Client(), emit=events.append).choose(dict(goal="x", observation={}, criteria={"abstain": "stop"}))
        self.assertEqual(events[0]["selected_id"], "invented")
        self.assertEqual(events[0]["input_tokens"], 3)

    async def test_low_confidence_failure_records_policy_code(self):
        class LowConfidence:
            async def choose(self, request):
                from native_core import Decision
                return Decision("abstain", .1, {key: float(key == "abstain") for key in request["criteria"]}, "test")
        events = []
        driver = FixtureDriver()
        self.assertEqual(await run_loop(task(), driver, LowConfidence(), events.append), "provider_failed")
        self.assertEqual(events[-1]["code"], "confidence_rejected")
        self.assertEqual(len(driver.calls), 1)  # Explicit setup only; no Jev mutation.
