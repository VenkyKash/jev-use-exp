import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_core import Task, verify
from native_driver import normalize


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
