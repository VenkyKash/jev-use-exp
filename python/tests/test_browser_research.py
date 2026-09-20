import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import BrowserTask, build_browser_candidates, validate_choice
from jev_adapter import choose_with_typesafe
from run import run_research_loop, run


def task():
    return BrowserTask.parse(dict(goal="Research a topic", start_url="https://example.org",
        allowed_hosts=["example.org"], search_text="Topic", navigation_terms=["Topic", "History"],
        observation_queries=["history"]))


def snapshot(generation="p1"):
    def row(i, role, name, actions):
        return dict(ref=f"{generation}:{i}", role=role, name=name, actions=actions)
    return dict(target_id="target", tab_id="tab", snapshot=dict(id=generation),
        page=dict(url="https://example.org", title="Public reference"), outline="Evidence text",
        refs=[row(0, "searchbox", "Search", ["type"]), row(1, "button", "Search", ["click"]),
              row(2, "link", "Topic", ["click"]), row(3, "button", "Save", ["click"]),
              row(4, "textbox", "Password", ["type"]), row(5, "link", "Log in", ["click"])])


class BrowserResearchTest(unittest.TestCase):
    def test_generic_candidates_exclude_editing_and_login(self):
        built = build_browser_candidates(snapshot(), task())
        self.assertEqual({c.id for c in built},
            {"type-p1:0", "click-p1:1", "click-p1:2", "read-0", "finish", "reobserve", "abstain"})
        self.assertEqual(next(c for c in built if c.id == "type-p1:0").arguments["text"], "Topic")

    def test_stale_duplicate_and_disabled_refs(self):
        for bad in ("p0:1", "p1:0"):
            raw = snapshot()
            raw["refs"][1]["ref"] = bad
            with self.assertRaises(ValueError):
                build_browser_candidates(raw, task())
        raw = snapshot()
        raw["refs"][0]["states"] = {"disabled": True}
        self.assertNotIn("type-p1:0", {c.id for c in build_browser_candidates(raw, task())})

    def test_external_or_credential_urls_rejected(self):
        for url in ["https://evil.test", "http://example.org", "https://secret@example.org", "https://example.org:99"]:
            with self.assertRaises(ValueError):
                task().check_url(url)

    def test_scoped_evidence_and_exact_link_match(self):
        raw = snapshot()
        raw["refs"][2]["name"] = "Book about Topic"
        raw["content_refs"] = [dict(ref="p1:10", role="region", name="History and aftermath")]
        built = build_browser_candidates(raw, task())
        self.assertNotIn("click-p1:2", {c.id for c in built})
        self.assertEqual(next(c for c in built if c.id == "scope-p1:10").arguments["scope_ref"], "p1:10")

    def test_selected_action_is_immutable_and_generation_bound(self):
        built = build_browser_candidates(snapshot(), task())
        with self.assertRaises(TypeError):
            built[0].arguments["text"] = "changed"
        with self.assertRaises(ValueError):
            validate_choice("click-p0:2", built)

    def test_adapter_uses_task_goal_without_changing_sdk_shape(self):
        class Client:
            def system_one(self, **request):
                self.request = request
                return SimpleNamespace(choices={"driver_action": SimpleNamespace(
                    choice="finish", confidence=.9, probabilities={"finish": 1})})
        client = Client()
        choose_with_typesafe(client, build_browser_candidates(snapshot(), task()), snapshot(), None, [], goal=task().goal)
        self.assertEqual(client.request["state"]["goal"], "Research a topic")
        self.assertIn("driver_action", client.request["questions"])


class BrowserResearchLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_research_dry_run_does_not_reset_fixture_or_open_browser(self):
        args = SimpleNamespace(task="plan.json", provider="live", token=None, log=None, dry_run=True)
        with patch("run.Path.read_text", return_value="{}"), patch("run.BrowserTask.parse", return_value=task()), \
             patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-only"}), \
             patch("run.reset_fixture") as reset, patch("run.stdio_client") as connect, patch("run.write_event"):
            self.assertEqual(await run(args), "dry_run")
        reset.assert_not_called()
        connect.assert_not_called()

    async def test_host_boundary_stops_before_jev_sees_external_content(self):
        class Driver:
            async def call(self, *args):
                raw = snapshot()
                raw["page"]["url"] = "https://external.example/"
                return raw
        async def chooser(*args):
            self.fail("external content must not reach Jev")
        with patch("run.write_event"):
            self.assertEqual(await run_research_loop(Driver(), task(), "target", "tab", 3, None, chooser), "outside_allowed_hosts")

    async def test_read_result_is_used_without_invalidating_snapshot(self):
        class Driver:
            calls = []
            async def call(self, name, arguments):
                self.calls.append((name, arguments))
                return snapshot("p" + str(len(self.calls)))
        requests = []
        async def chooser(candidates, state, history):
            requests.append(state["snapshot"]["id"])
            return ("read-0" if len(requests) == 1 else "finish"), .9, {}
        driver = Driver()
        with patch("run.write_event") as emit:
            outcome = await run_research_loop(driver, task(), "target", "tab", 3, None, chooser)
        self.assertEqual(outcome, "review_required")
        self.assertEqual(requests, ["p1", "p2"])
        self.assertEqual(len(driver.calls), 2)
        self.assertTrue(any(c.args[1]["event"] == "browser_evidence" for c in emit.call_args_list))

    async def test_repeated_state_stops_without_unbounded_calls(self):
        class Driver:
            async def call(self, *args):
                return snapshot()
        async def chooser(*args):
            return "reobserve", .9, {}
        with patch("run.write_event"):
            self.assertEqual(await run_research_loop(Driver(), task(), "target", "tab", 10, None, chooser), "no_progress")

    async def test_uncertain_click_is_never_retried(self):
        class Driver:
            clicks = 0
            async def call(self, name, args):
                if name == "get_browser_state":
                    return snapshot()
                self.clicks += 1
                raise TimeoutError()
        async def chooser(*args):
            return "click-p1:2", .9, {}
        driver = Driver()
        with patch("run.write_event"):
            self.assertEqual(await run_research_loop(driver, task(), "target", "tab", 5, None, chooser), "unknown")
        self.assertEqual(driver.clicks, 1)
