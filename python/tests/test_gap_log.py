import json
from pathlib import Path
import tempfile
import unittest

from gap_log import record_gap, summarize
from native_candidates import build_native_candidates
from native_core import Element, Observation, Task


class GapTests(unittest.TestCase):
    def test_diagnostics_preserve_candidates_and_explain_omissions(self):
        elements = tuple(Element(i, role, label, None, None, actions, True, None, False)
                         for i, role, label, actions in (
                             (1, "AXButton", "Go", ("AXPress",)),
                             (2, "AXRow", "Workspace", ("AXShowDefaultUI",)),
                             (3, "AXTextField", "", ()),
                             (4, "AXTextField", "Search", ())))
        observation = Observation("s1", 1, 2, elements)
        task = Task("Explore", "Example", (), ())
        coverage = []
        baseline = build_native_candidates(task, observation, lambda *_: True)
        diagnosed = build_native_candidates(task, observation, lambda *_: True,
                                            diagnostics=coverage)
        self.assertEqual(baseline, diagnosed)
        self.assertIn("click-1", coverage[0]["candidate_ids"])
        self.assertEqual(coverage[1]["reasons"], [])
        self.assertIn("click-2", coverage[1]["candidate_ids"])
        self.assertEqual(coverage[2]["reasons"], ["no_supplied_text"])
        self.assertEqual(coverage[3]["reasons"], ["no_supplied_text"])
        for read_only, reason in ((True, "read_only_policy"), (False, "click_schema_rejected")):
            coverage = []
            build_native_candidates(task, observation, lambda *_: False,
                                    diagnostics=coverage, read_only=read_only)
            self.assertEqual(coverage[0]["reasons"], [reason])

    def test_reports_are_unique_and_resolution_preserves_original(self):
        root = Path(__file__).resolve().parents[2] / "runs"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            directory = Path(temporary)
            run = directory / "trace.jsonl"
            run.write_text('{"event":"decision_failed"}\n{interrupted')
            summary = summarize(run)
            self.assertFalse(summary["coverage_available"])
            self.assertEqual(summary["malformed_lines"], 1)
            kwargs = dict(run=run, category="candidate", expected="row selectable",
                          actual="no row option", evidence="decision-1")
            first = record_gap(directory / "gaps", **kwargs)
            original = first.read_text()
            with self.assertRaises(ValueError):
                record_gap(directory / "gaps", **kwargs, status="resolved")
            second = record_gap(directory / "gaps", **kwargs, status="resolved",
                                related=json.loads(original)["id"])
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_text(), original)

    def test_summary_counts_facts_without_copying_ui(self):
        root = Path(__file__).resolve().parents[2] / "runs"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            run = Path(temporary) / "trace.jsonl"
            run.write_text(json.dumps(dict(event="candidate_coverage", elements=[
                dict(label="private text", reasons=["no_supported_action"])])))
            result = summarize(run)
            self.assertTrue(result["coverage_available"])
            self.assertEqual(result["coverage_reason_occurrences"], {"no_supported_action": 1})
            self.assertNotIn("private text", json.dumps(result))
