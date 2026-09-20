import unittest
from evidence import browser_handoff
from test_native import task, snapshot, ScriptedTestChooser
from native_driver import normalize
from native_candidates import build_native_candidates
from native_run import run_loop
from native_fixture import FixtureDriver


class EvidenceTest(unittest.TestCase):
    def test_probability_rounding_boundary_is_inclusive(self):
        from native_jev import validate_decision
        from native_core import Decision
        for total in (.99, 1.01):
            validate_decision(Decision("a", .9, {"a": .8, "b": total-.8}, None),
                              {"criteria": {"a": "a", "b": "b"}}, .5)
        with self.assertRaises(ValueError):
            validate_decision(Decision("a", .9, {"a": .8, "b": .18}, None),
                              {"criteria": {"a": "a", "b": "b"}}, .5)

    def test_browser_handoff_preserves_source_and_uncertainty(self):
        raw = dict(page=dict(url="https://example.org/article"), snapshot=dict(id="p1", scope="subtree", complete=False, omitted={"budget": 4}), outline="Uncertain cause.")
        event = browser_handoff("Find cause", raw)
        self.assertEqual(event["status"], "review_required")
        self.assertFalse(event["independently_verified"])
        self.assertFalse(event["source_complete"])
        self.assertEqual(event["source"]["url"], raw["page"]["url"])
        self.assertEqual(event["text"], "Uncertain cause.")

    def test_native_static_text_is_evidence_not_a_click_target(self):
        raw = snapshot()
        raw.update(elements_complete=False, tree_markdown='- [0] AXWindow "Test"\n  - AXStaticText = "48"\n- [20] AXMenuBar\n  - private menu')
        obs = normalize(raw, 1, 2)
        self.assertIn('"48"', obs.readback_text)
        self.assertNotIn("private menu", obs.readback_text)
        built = build_native_candidates(task(), obs, lambda *_: True)
        self.assertIn("review", {c.id for c in built.candidates})
        self.assertNotIn("48", {e.value for e in obs.elements})
        changed = {**raw, "tree_markdown": raw["tree_markdown"].replace('"48"', '"49"')}
        self.assertNotEqual(obs.fingerprint(), normalize(changed, 1, 2).fingerprint())


class EvidenceLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_provider_failure_still_hands_off_observed_evidence(self):
        class Driver(FixtureDriver):
            async def observe(self, *args):
                return normalize({**snapshot(), "tree_markdown": '- AXStaticText = "partial"'}, 1, 2)
        driver, events = Driver(), []
        outcome = await run_loop(task(), driver, ScriptedTestChooser(["invented"]), events.append, target=(1, 2))
        self.assertEqual(outcome, "provider_failed")
        evidence = next(e for e in events if e["event"] == "evidence_handoff")
        self.assertEqual(evidence["reason"], "decision_failed")
        self.assertIn("partial", evidence["text"])
        self.assertEqual(driver.calls, [])

    async def test_native_review_handoff_does_not_mutate_or_verify(self):
        class Driver(FixtureDriver):
            async def observe(self, *args):
                raw = snapshot()
                raw["tree_markdown"] = '- AXStaticText = "48"'
                return normalize(raw, 1, 2)
        driver, events = Driver(), []
        outcome = await run_loop(task(), driver, ScriptedTestChooser(["review"]), events.append, target=(1, 2))
        self.assertEqual(outcome, "review_required")
        self.assertEqual(driver.calls, [])
        event = next(e for e in events if e["event"] == "evidence_handoff")
        self.assertFalse(event["independently_verified"])
        self.assertEqual(event["source"]["window_id"], 2)
