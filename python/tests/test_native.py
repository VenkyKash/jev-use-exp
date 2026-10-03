import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_core import Task, verify
from native_driver import normalize, NativeDriver, DriverFailure
from native_candidates import build_native_candidates
from native_core import Decision
from native_jev import decision_request, validate_decision
from native_fixture import FixtureDriver
from native_run import run_loop


def task():
    return Task.parse(dict(goal="Enter supplied name then submit", app="Fixture",
                           inputs=["Ada"], checks=[dict(role="AXStaticText", label="Result", equals="Done")]))


def snapshot(snapshot_id="s1", value="Pending"):
    return dict(snapshot_id=snapshot_id, elements=[
        dict(element_index=0, role="AXTextField", label="Name", value="", element_token=f"{snapshot_id}:0"),
        dict(element_index=1, role="AXButton", label="Submit", actions=["AXPress"], element_token=f"{snapshot_id}:1"),
        dict(element_index=2, role="AXStaticText", label="Result", value=value),
    ])


class NativeModelsTest(unittest.TestCase):
    def test_unique_exact_readback_required(self):
        self.assertFalse(verify(task(), normalize(snapshot(), 1, 2)))
        self.assertTrue(verify(task(), normalize(snapshot(value="Done"), 1, 2)))
        raw = snapshot(value="Done")
        raw["elements"].append(dict(element_index=3, role="AXStaticText", label="Result", value="Done"))
        self.assertFalse(verify(task(), normalize(raw, 1, 2)))

    def test_web_readback_not_independent_proof(self):
        raw = snapshot(value="Done")
        raw["elements"][2]["in_web_content"] = True
        self.assertFalse(verify(task(), normalize(raw, 1, 2)))

    def test_rotating_references_are_not_progress(self):
        self.assertEqual(normalize(snapshot("s1"), 1, 2).fingerprint(),
                         normalize(snapshot("s2"), 1, 2).fingerprint())

    def test_malformed_and_truncated_observations_fail(self):
        for raw in [{"elements": []}, {**snapshot(), "truncated": True},
                    {**snapshot(), "elements": snapshot()["elements"] * 2}]:
            with self.assertRaises(ValueError):
                normalize(raw, 1, 2)

    def test_inputs_are_bounded(self):
        with self.assertRaises(ValueError):
            Task.parse(dict(goal="x", app="y", inputs=["z"] * 9, checks=[]))


class NativeCandidatesTest(unittest.TestCase):
    def test_all_buttons_offered_independent_of_goal_or_verifier(self):
        raw = snapshot()
        raw["elements"].append(dict(element_index=3, role="AXButton", label="Cancel"))
        obs = normalize(raw, 1, 2)
        built = build_native_candidates(task(), obs, lambda *_: True)
        self.assertTrue({"type-0-0", "click-1", "click-3", "reobserve", "abstain"}
                        <= {c.id for c in built.candidates})
        other = Task("Different goal", "Different app", task().inputs, ())
        self.assertEqual(built, build_native_candidates(other, obs, lambda *_: True))

    def test_stale_choices_and_argument_mutation_rejected(self):
        built = build_native_candidates(task(), normalize(snapshot(), 1, 2), lambda *_: True)
        with self.assertRaisesRegex(ValueError, "stale"):
            built.resolve("click-1", "s2")
        with self.assertRaises(ValueError):
            built.resolve("invented", "s1")
        with self.assertRaises(TypeError):
            built.resolve("click-1", "s1").arguments["pid"] = 999

    def test_web_actions_offered_but_disabled_and_unsupported_are_not(self):
        raw = snapshot()
        raw["elements"][0]["in_web_content"] = True
        raw["elements"][1]["enabled"] = False
        ids = {c.id for c in build_native_candidates(task(), normalize(raw, 1, 2), lambda *_: True).candidates}
        self.assertIn("type-0-0", ids)
        self.assertNotIn("click-1", ids)
        self.assertEqual(len(build_native_candidates(task(), normalize(snapshot(), 1, 2), lambda *_: False).candidates), 2)


class NativeDecisionTest(unittest.TestCase):
    def request(self):
        obs = normalize(snapshot(), 1, 2)
        return decision_request(task(), obs, build_native_candidates(task(), obs, lambda *_: True), [], 20, 42)

    def test_request_has_no_verifier_or_executable_arguments(self):
        import json
        payload = json.dumps(self.request())
        for forbidden in ['"checks"', '"equals"', '"Done"', '"element_token"', '"delivery_mode"']:
            self.assertNotIn(forbidden, payload)

    def test_probabilities_and_confidence_fail_closed(self):
        request = self.request()
        valid = {key: float(key == "click-1") for key in request["criteria"]}
        validate_decision(Decision("click-1", .9, valid, "jev"), request, .5)
        for choice in [Decision("invented", 1, valid, None), Decision("click-1", float("nan"), valid, None),
                       Decision("click-1", .2, valid, None), Decision("click-1", 1, {"click-1": 1}, None),
                       Decision("click-1", 1, {key: .9 for key in valid}, None)]:
            with self.assertRaises(ValueError):
                validate_decision(choice, request, .5)


class ScriptedTestChooser:
    """Test-only sequence; never connected to live desktop runs."""
    def __init__(self, ids):
        self.ids = iter(ids)
        self.requests = []

    async def choose(self, request):
        self.requests.append(request)
        selected = next(self.ids)
        return Decision(selected, 1, {key: float(key == selected) for key in request["criteria"]}, "scripted-test")


class NativeLoopTest(unittest.IsolatedAsyncioTestCase):
    def form_task(self):
        return Task.parse(dict(goal="Enter Ada in Name and Paris in City and submit", app="Fixture",
            inputs=["Ada", "Paris"], checks=[dict(role="AXStaticText", label="Receipt", equals="Ada | Paris")]))

    async def test_multi_step_form_and_independent_submission(self):
        driver, events = FixtureDriver(), []
        chooser = ScriptedTestChooser(["type-0-0", "type-1-1", "click-2"])
        result = await run_loop(self.form_task(), driver, chooser, events.append)
        self.assertEqual(result, "verified")
        self.assertEqual(driver.submitted, ("Ada", "Paris"))
        self.assertEqual(len(driver.calls), len(chooser.requests) + 1)
        self.assertTrue(all("launch" not in r["criteria"] for r in chooser.requests))
        self.assertTrue(all(r["observation"]["current"]["elements"] for r in chooser.requests))
        self.assertTrue(all("before" not in r["observation"] for r in chooser.requests))
        self.assertIn("probabilities", chooser.requests[1]["history"][0])
        self.assertTrue(all(len(r["criteria"]) >= 3 for r in chooser.requests))
        self.assertEqual(len([e for e in events if e["event"] == "dispatch"]), 3)
        self.assertEqual(len([e for e in events if e["event"] == "setup_dispatch"]), 1)

    async def test_calculator_same_runner_and_builder(self):
        driver = FixtureDriver("calculator")
        calculator = Task.parse(dict(goal="Calculate 17 × 23", app="Calculator", inputs=[],
            checks=[dict(role="AXStaticText", label="Display", equals="391")]))
        chooser = ScriptedTestChooser(["click-1", "click-7", "click-10", "click-2", "click-3", "click-11"])
        self.assertEqual(await run_loop(calculator, driver, chooser, lambda e: None), "verified")
        self.assertEqual(driver.display, "391")

    async def test_dry_run_never_launches_or_mutates(self):
        driver = FixtureDriver()
        self.assertEqual(await run_loop(self.form_task(), driver, ScriptedTestChooser(["launch"]),
                                       lambda e: None, dry_run=True), "dry_run")
        self.assertEqual(driver.calls, [])

    async def test_no_progress_bounded_without_mutations(self):
        driver = FixtureDriver()
        self.assertEqual(await run_loop(self.form_task(), driver,
            ScriptedTestChooser(["reobserve"]*3), lambda e: None, target=(1,2)), "no_progress")
        self.assertEqual(driver.calls, [])

    async def test_provider_error_has_no_fallback(self):
        driver = FixtureDriver()
        self.assertEqual(await run_loop(self.form_task(), driver, ScriptedTestChooser(["invented"]),
                                       lambda e: None, target=(1,2)), "provider_failed")
        self.assertEqual(driver.calls, [])

    async def test_uncertain_action_observes_and_never_retries(self):
        class Uncertain(FixtureDriver):
            async def call(self, tool, arguments):
                await super().call(tool, arguments)
                raise TimeoutError()
        driver = Uncertain()
        self.assertEqual(await run_loop(self.form_task(), driver, ScriptedTestChooser(["type-0-0"]),
                                       lambda e: None, target=(1,2)), "unknown")
        self.assertEqual(len(driver.calls), 1)
        self.assertEqual(driver.fields[0], "Ada")
        self.assertEqual(driver.version, 2)

    async def test_final_action_verified_at_step_limit(self):
        driver = FixtureDriver()
        chooser = ScriptedTestChooser(["type-0-0", "type-1-1", "click-2"])
        self.assertEqual(await run_loop(self.form_task(), driver, chooser, lambda e: None,
                                       target=(1,2), max_steps=3), "verified")

    async def test_changing_but_cyclic_ui_stops(self):
        driver = FixtureDriver()
        chooser = ScriptedTestChooser(["type-0-0", "click-3"]*3)
        self.assertEqual(await run_loop(self.form_task(), driver, chooser, lambda e: None,
                                       target=(1,2)), "repeated_state")
        self.assertEqual(len(driver.calls), 4)


class NativeTransportTest(unittest.IsolatedAsyncioTestCase):
    async def test_schema_and_refusal_no_automatic_retry(self):
        from types import SimpleNamespace
        class Session:
            calls = []
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return SimpleNamespace(isError=False, structuredContent={"status": "refused"})
        session = Session()
        schema = {"type": "object", "properties": {"pid": {"type": "integer"},
                    "session": {"type": "string"}}, "required": ["pid"]}
        driver = NativeDriver(session, "test-session", {"click": schema})
        self.assertFalse(driver.accepts("click", {"pid": "wrong"}))
        self.assertFalse(driver.accepts("click", {"pid": 1, "capture_id": "unsupported"}))
        with self.assertRaises(DriverFailure):
            await driver.call("click", {"pid": 1})
        self.assertEqual(session.calls, [("click", {"pid": 1, "session": "test-session"})])

    async def test_jev_sdk_receives_exact_auditable_request(self):
        from native_jev import JevChooser
        from types import SimpleNamespace
        requests = []
        class Client:
            def system_one(self, **kwargs):
                requests.append(kwargs)
                return SimpleNamespace(model="test-jev", choices={"driver_action": SimpleNamespace(
                    choice="click-1", confidence=.9,
                    probabilities={key: float(key == "click-1") for key in kwargs["questions"]["driver_action"].criteria})})
        obs = normalize(snapshot(), 1, 2)
        request = decision_request(task(), obs, build_native_candidates(task(), obs, lambda *_: True), [], 20, 1)
        decision = await JevChooser(Client()).choose(request)
        validate_decision(decision, request, .5)
        from decision_payload import compact_request
        expected, _ = compact_request({"goal": task().goal, "observation": request["observation"], "history": [], "application": request["application"]}, request["criteria"])
        self.assertEqual(requests[0]["state"], expected)
        self.assertEqual(requests[0]["questions"]["driver_action"].criteria, request["criteria"])
