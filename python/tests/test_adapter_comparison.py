"""Offline adapter comparison: no SDK client, network, or Driver construction."""
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import Candidate
from jev_adapter import choose_with_typesafe
from native_jev import JevChooser, validate_decision


class ReplayClient:
    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    def system_one(self, **request):
        self.requests.append(request)
        # Only adapt the question name; the answer values remain identical.
        name, = request["questions"]
        return SimpleNamespace(choices={name: self.answer}, model="recorded-replay")


def compare(selected, confidence, probabilities, ids):
    answer = SimpleNamespace(choice=selected, confidence=confidence,
                             probabilities=probabilities)
    candidates = [Candidate(key, key, None, {}) for key in ids]
    clients = [ReplayClient(answer), ReplayClient(answer)]
    request = dict(goal="Enter the verification token, then submit the form.",
                   observation=dict(before=None, current=dict(page=None, outline=None, visual=None)),
                   criteria={key: key for key in ids})
    outcomes = []
    for native, client in zip((False, True), clients):
        try:
            if native:
                result = asyncio.run(JevChooser(client).choose(request))
                validate_decision(result, request, 0.5)
            else:
                choose_with_typesafe(client, candidates, {}, None, [])
            outcomes.append("accepted")
        except ValueError as error:
            outcomes.append(getattr(error, "code", "ValueError"))
    return outcomes, clients


class AdapterComparisonTest(unittest.TestCase):
    def test_five_retained_provider_answers_pass_both_paths(self):
        # Values copied from ignored runs/api-audit-01/probe.jsonl and
        # runs/live-suite-01/chrome-{provider-probe,validation-probes}.json.
        # These are successful diagnostic responses, NOT the lost failed answers.
        rows = [
            ("acknowledge", .87, {"acknowledge": .94, "abstain": .06}),
            ("launch", .69, {"launch": .8, "reobserve": .16, "abstain": .04}),
            ("launch", .68, {"launch": .78, "reobserve": .17, "abstain": .05}),
            ("launch", .63, {"launch": .75, "reobserve": .2, "abstain": .05}),
            ("launch", .71, {"launch": .81, "reobserve": .15, "abstain": .04}),
        ]
        for selected, confidence, probabilities in rows:
            with self.subTest(confidence=confidence):
                outcomes, clients = compare(selected, confidence, probabilities, list(probabilities))
                self.assertEqual(outcomes, ["accepted", "accepted"])
                self.assertEqual([len(c.requests) for c in clients], [1, 1])
                original, native = [c.requests[0] for c in clients]
                self.assertEqual(original["state"]["goal"], native["state"]["goal"])
                self.assertEqual(original["state"]["observation"], native["state"]["observation"])
                self.assertEqual(original["questions"]["driver_action"].criteria,
                                 native["questions"]["candidate"].criteria)

    def test_synthetic_boundary_differences(self):
        rows = [
            ("launch", .49, {"launch": .9, "abstain": .1}, "confidence_rejected"),
            ("launch", .9, {"launch": .9}, "probability_keys"),
            ("launch", .9, {"launch": .6, "abstain": .1}, "probability_sum"),
            ("launch", 1.1, {"launch": .9, "abstain": .1}, "provider_response_invalid"),
            ("launch", .9, {"launch": 1.1, "abstain": -.1}, "provider_response_invalid"),
        ]
        for selected, confidence, probabilities, expected in rows:
            with self.subTest(expected=expected, probabilities=probabilities):
                outcomes, _ = compare(selected, confidence, probabilities, ["launch", "abstain"])
                self.assertEqual(outcomes, ["accepted", expected])

    def test_unknown_selected_id_is_rejected_by_both(self):
        outcomes, _ = compare("invented", .9, {"launch": 1}, ["launch"])
        self.assertEqual(outcomes, ["ValueError", "provider_response_invalid"])
