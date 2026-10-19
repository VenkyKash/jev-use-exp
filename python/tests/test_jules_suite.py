from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
from native_core import Task
from run_jules_suite import load_tasks, run_single_task, run_suite, generate_improvement_report
from native_jev import FirstCandidateBaseline


class JulesSuiteTests(unittest.TestCase):
    def test_load_tasks_finds_open_libre_apps(self):
        tasks = dict(load_tasks(BASE / "tasks"))
        self.assertIn("gnumeric_budget", tasks)
        self.assertIn("mousepad_notes", tasks)
        self.assertIn("galculator_calc", tasks)

    def test_open_libre_task_definitions_are_valid(self):
        tasks_dir = BASE / "tasks"
        for task_name in ["gnumeric_budget", "mousepad_notes", "galculator_calc"]:
            path = tasks_dir / f"{task_name}.json"
            content = json.loads(path.read_text())
            task = Task.parse(content)
            self.assertIsNotNone(task.app)
            self.assertTrue(len(task.goal) > 0)

    def test_run_jules_suite_generates_summary_and_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            log_dir = temp_path / "runs"
            report_dir = temp_path / "reports"
            log_dir.mkdir()
            report_dir.mkdir()

            # Create a small simulated fixture task to test execution through the harness
            fixture_task = temp_path / "test_fixture.json"
            fixture_task.write_text(json.dumps({
                "app": "Fixture",
                "goal": "Calculate 8 × 6 using buttons",
                "inputs": [],
                "checks": [{"role": "AXStaticText", "label": "Display", "equals": "48"}]
            }))

            import asyncio
            summary = asyncio.run(run_suite(temp_path, log_dir, provider="first"))
            self.assertEqual(summary["total_tasks"], 1)
            self.assertEqual(summary["results"][0]["task"], "test_fixture")

            report_file = generate_improvement_report(summary, report_dir)
            self.assertTrue(report_file.exists())
            report_content = report_file.read_text()
            self.assertIn("# Jules Autonomous Task Evaluation & Improvement Report", report_content)
            self.assertIn("test_fixture", report_content)


if __name__ == "__main__":
    unittest.main()
