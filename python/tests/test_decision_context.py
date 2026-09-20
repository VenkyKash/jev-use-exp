import copy
import unittest
from decision_context import format_context, readable_state


class ContextTest(unittest.TestCase):
    def request(self):
        return dict(goal="Do task", criteria={"x": "Click control", "abstain": "Stop"},
            observation=dict(elements=[dict(role="AXWindow", label="Any app", value=None)],
                readback_text='- AXStaticText = "\u200e42\u200e+"', complete=False,
                history=[dict(selected_id="x", description="Click control", outcome="observed_change")]))

    def test_goal_and_ordered_choices_are_unchanged(self):
        request = self.request()
        before = copy.deepcopy(request)
        result = format_context(request)
        self.assertEqual(result["goal"], request["goal"])
        self.assertEqual(list(result["criteria"].items()), list(request["criteria"].items()))
        self.assertEqual(request, before)

    def test_before_after_are_facts_not_success_inferences(self):
        old = dict(readback_text='- AXStaticText = "42+1"')
        context = format_context(self.request(), old)["observation"]
        self.assertEqual(context["last_action"]["before"][0]["text"], "42+1")
        self.assertEqual(context["last_action"]["after"][0]["text"], "42+")
        self.assertEqual(context["last_action"]["task_completion"], "not_evaluated")

    def test_unknown_values_are_not_empty_success(self):
        context = format_context(dict(goal="inspect", criteria={}, observation={}))["observation"]
        self.assertIsNone(context["current_state"]["dialogs"])
        self.assertIsNone(context["observation_quality"]["readable_values_complete"])
        self.assertIsNone(context["last_action"])

    def test_unsupported_text_shape_is_disclosed(self):
        values, unsupported = readable_state(dict(readback_text='- AXStaticText (Label) = "value"'))
        self.assertEqual(values, [])
        self.assertEqual(unsupported, 1)

    def test_arbitrary_app_structured_values(self):
        request = self.request()
        request["observation"]["readback_text"] = ""
        request["observation"]["elements"].append(dict(role="AXTextArea", label="Draft", value="Hello"))
        self.assertEqual(format_context(request)["observation"]["current_state"]["readable_values"][0]["text"], "Hello")
