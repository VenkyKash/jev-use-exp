import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_driver import normalize
from decision_payload import compact_request, validate_request_budget
from native_errors import DiagnosticError
from typesafe_sdk import Choice


class ObservationBudgetTest(unittest.TestCase):
    def test_request_above_old_ceiling_is_accepted(self):
        validate_request_budget({"text": "x"*35000}, {"action": Choice(criteria={"observe": "Read state"})})

    def test_all_controls_survive_request_and_transport_projection(self):
        from native_core import Task
        from native_candidates import CandidateSet
        from native_jev import decision_request
        raw = dict(snapshot_id="s1", elements=[dict(element_index=i, role="AXButton", label=f"Control {i}") for i in range(490)])
        obs = normalize(raw, 1, 2)
        request = decision_request(Task("Task", "App", (), ()), obs, CandidateSet("s1", ()), [], 10, 0)
        state, _ = compact_request({k:v for k,v in request.items() if k != "criteria"}, request["criteria"])
        current = state["observation"]["current"]
        table = current["elements"]
        self.assertEqual(len(table["rows"]), 490)
        self.assertEqual(table["rows"][-1][table["columns"].index("label")], "Control 489")
        self.assertEqual(current["context_elements_omitted"], 0)

    def test_large_readback_is_retained_and_projection_is_bounded(self):
        text = "Page text " * 30000
        observation = normalize(dict(snapshot_id="s1", elements=[], tree_markdown=text), 1, 2)
        self.assertEqual(observation.readback_text, text)
        state = {"task": {"objective": "Read evidence"}, "observation": {
            "before": None, "current": {"readback_text": text, "elements": []}}}
        compact, criteria = compact_request(state, {"reobserve": "Observe"})
        self.assertEqual(state["observation"]["current"]["readback_text"], text)
        current = compact["observation"]["current"]
        self.assertEqual(len(current["readback_text"]), 2000)
        self.assertEqual(current["readback_characters_omitted"], len(text)-2000)
        validate_request_budget(compact, {"action": Choice(criteria=criteria)})

    def test_oversized_task_or_action_fails_before_network_without_truncation(self):
        args = {"text": "x"*40000}
        state, criteria = compact_request({"task": "Preserve"}, {"type": {"args": args}})
        self.assertEqual(criteria["type"]["args"], args)
        with self.assertRaises(DiagnosticError) as caught:
            validate_request_budget(state, {"action": Choice(criteria=criteria)})
        self.assertEqual(caught.exception.code, "request_budget_exceeded")
