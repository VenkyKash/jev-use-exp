import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_core import Task, verify
from native_driver import normalize
from native_candidates import build_native_candidates
from native_core import Decision
from native_jev import decision_request, validate_decision


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
        self.assertEqual({c.id for c in built.candidates},
                         {"type-0-0", "click-1", "click-3", "reobserve", "abstain"})
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

    def test_disabled_web_and_unsupported_actions_not_offered(self):
        raw = snapshot()
        raw["elements"][0]["in_web_content"] = True
        raw["elements"][1]["enabled"] = False
        self.assertEqual(len(build_native_candidates(task(), normalize(raw, 1, 2), lambda *_: True).candidates), 2)
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
