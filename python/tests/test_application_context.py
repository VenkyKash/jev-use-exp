import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_driver import normalize
from native_core import Task
from native_jev import application_context


class ApplicationContextTest(unittest.TestCase):
    def test_observed_identity_takes_precedence_and_unknown_stays_unknown(self):
        task = Task("Task", "Google Chrome", (), ())
        for name, kind in [("Visual Studio Code", "code_editor"), ("Google Chrome", "web_browser"), ("Unknown App", "unknown")]:
            observation = normalize(dict(snapshot_id="s", elements=[], app_name=name, window_title="Document"), 1, 2)
            context = application_context(task, observation)
            self.assertEqual(context["name"], name)
            self.assertEqual(context["type"], kind)
            self.assertEqual(context["name_source"], "observed")
            self.assertEqual(context["window_title"], "Document")

    def test_task_fallback_is_explicit(self):
        context = application_context(Task("Task", "Google Chrome", (), ()), None)
        self.assertEqual(context["name_source"], "task")
        self.assertEqual(context["type_source"], "inferred_from_app_name")
