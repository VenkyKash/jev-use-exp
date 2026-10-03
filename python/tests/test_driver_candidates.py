"""Coverage against schemas captured from the installed Driver's list_tools.

Schema tests do not execute maintenance, permission, upload or destructive tools.
"""
import json
from pathlib import Path
import unittest

from core import BrowserTask, Candidate, build_browser_candidates
from driver_candidates import ToolOption, catalog, choice_menu, explicit_candidates, thaw
from native_candidates import build_native_candidates
from native_core import Task, Decision, verify
from native_driver import NativeDriver, normalize
from native_run import run_loop

SCHEMAS = json.loads((Path(__file__).parent / "fixtures/driver_schemas.json").read_text())


def sample(schema):
    """Schema-valid synthetic inputs, deliberately not authority or live targets."""
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("oneOf", "anyOf"):
        if key in schema:
            return sample(schema[key][0])
    kind = schema.get("type", "string")
    if isinstance(kind, list):
        kind = next(k for k in kind if k != "null")
    if kind == "object":
        return {k: sample(schema["properties"][k]) for k in schema.get("required", [])}
    if kind == "array":
        return [sample(schema.get("items", {})) for _ in range(max(1, schema.get("minItems", 1)))]
    if kind in ("number", "integer"):
        return max(1, schema.get("minimum", 1))
    if kind == "boolean":
        return False
    return "s12345678" if schema.get("pattern") == "^s[0-9a-f]{8}$" else "test-value"


def task(**extra):
    return Task.parse(dict(goal="Complete requested interaction", app="Test", inputs=["hello"], checks=[], **extra))


def observation(count=1):
    return normalize(dict(snapshot_id="s12345678", elements=[
        dict(element_index=i, element_token=f"s12345678:{i}", role="AXTextField" if i == 0 else "AXButton",
             label=f"Control {i}", actions=["press", "showmenu"], in_web_content=True)
        for i in range(count)]), 10, 20)


class DriverCatalogTest(unittest.TestCase):
    def setUp(self):
        self.driver = NativeDriver(None, "test", SCHEMAS)

    def test_every_advertised_tool_accepts_explicit_schema_valid_options(self):
        for tool, schema in SCHEMAS.items():
            with self.subTest(tool=tool):
                arguments = sample(schema)
                arguments.pop("session", None)  # Runner supplies lifecycle identity.
                candidates = explicit_candidates([ToolOption(tool, arguments)], {}, self.driver.accepts)
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0].tool, tool)
                self.assertTrue(self.driver.accepts(tool, candidates[0].arguments))
        self.assertEqual({r["tool"] for r in catalog(SCHEMAS, [])}, set(SCHEMAS))

    def test_new_driver_tools_need_no_builder_allowlist_change(self):
        driver = NativeDriver(None, "test", {"new_driver_tool": {
            "type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}})
        c = explicit_candidates([ToolOption("new_driver_tool", {"value": 3})], {}, driver.accepts)[0]
        self.assertEqual(c.tool, "new_driver_tool")

    def test_unknown_tool_bad_parameters_and_foreign_session_rejected(self):
        for tool, args in (("invented", {}), ("press_key", {"key": 123}),
                           ("press_key", {"key": "return", "invented": True}),
                           ("press_key", {"key": "return", "session": "another"})):
            with self.subTest(tool=tool, args=args), self.assertRaises(ValueError):
                explicit_candidates([ToolOption(tool, args)], {}, self.driver.accepts)

    def test_native_keys_replace_secondary_clicks_web_and_unlabelled(self):
        obs = observation()
        c = build_native_candidates(task(), obs, self.driver.accepts)
        by_id = {x.id: x for x in c.candidates}
        for id in ("key-return", "key-tab", "hotkey-cmd-a", "scroll-down", "set-0-0",
                   "type-0-0", "click-0", "double_click-0", "right_click-0", "action-0-show_menu"):
            self.assertIn(id, by_id)
            self.assertTrue(self.driver.accepts(by_id[id].tool, by_id[id].arguments))
        self.assertEqual(by_id["set-0-0"].arguments["value"], "hello")
        self.assertNotIn("type-focused-0", by_id)
        self.assertEqual(by_id["key-return"].arguments["window_id"], 20)
        self.assertNotIn("kill_app", {x.tool for x in c.candidates})
        self.assertNotIn("set_config", {x.tool for x in c.candidates})
        self.assertFalse(verify(task(), obs))  # Empty checks require evidence review.

    def test_task_options_are_choices_with_fresh_bindings_not_sequences(self):
        t = task(tool_options=[dict(tool="press_key", arguments={"pid": "$pid", "window_id": "$window_id",
                               "element_token": "$element_token", "key": "return"})])
        built = build_native_candidates(t, observation(2), self.driver.accepts)
        options = [c for c in built.candidates if c.id.startswith("tool-option-")]
        self.assertEqual(len(options), 2)
        self.assertEqual({c.arguments["element_token"] for c in options}, {"s12345678:0", "s12345678:1"})
        with self.assertRaises(ValueError):
            built.resolve(options[0].id, "s87654321")
        self.assertFalse(any(c.tool for c in build_native_candidates(t, observation(), self.driver.accepts, read_only=True).candidates))

    def test_menu_paths_and_nested_arguments(self):
        obs = normalize(dict(snapshot_id="s12345678", elements=[
            dict(element_index=0, role="AXMenuBar"),
            dict(element_index=1, role="AXMenuBarItem", label="File", parent_index=0),
            dict(element_index=2, role="AXMenu", parent_index=1),
            dict(element_index=3, role="AXMenuItem", label="New", parent_index=2)]), 10, 20)
        built = build_native_candidates(task(), obs, self.driver.accepts)
        c = next(c for c in built.candidates if c.tool == "invoke_menu")
        self.assertEqual(thaw(c.arguments)["path"], ["File", "New"])
        self.assertTrue(self.driver.accepts(c.tool, c.arguments))

    def test_web_context_menus_are_not_mistaken_for_system_menu_bar(self):
        obs = normalize(dict(snapshot_id="s12345678", elements=[
            dict(element_index=0, role="AXMenu", in_web_content=True),
            dict(element_index=1, role="AXMenuItem", label="New", parent_index=0, in_web_content=True),
            dict(element_index=2, role="AXRow", label="", actions=["AXShowDefaultUI"]),
            dict(element_index=3, role="AXStaticText", value="Workspace", parent_index=2)]), 10, 20)
        built = build_native_candidates(task(), obs, self.driver.accepts)
        self.assertEqual(len(obs.elements), 4)
        self.assertEqual(obs.excluded_menu_elements, 0)
        self.assertIn("click-1", {c.id for c in built.candidates})
        self.assertIn("Workspace", next(c.description for c in built.candidates if c.id == "click-2"))

    def test_result_dependent_arguments_wait_for_observed_result(self):
        opt = ToolOption("browser_dialog", dict(target_id="$result.target_id", tab_id="$result.tab_id",
                         action="dismiss", dialog_id="$result.dialog_id"))
        self.assertEqual(explicit_candidates([opt], {"result": {}}, self.driver.accepts), [])
        result = dict(target_id="target", tab_id="tab", dialog_id="dialog")
        self.assertEqual(len(explicit_candidates([opt], {"result": result}, self.driver.accepts)), 1)

    def test_browser_generic_controls_pointer_and_upload_parameters(self):
        t = BrowserTask.parse(dict(goal="Populate a new document", start_url="https://example.org",
            allowed_hosts=["example.org"], inputs=["content"], tool_options=[
                dict(tool="browser_set_input_files", arguments={"target_id": "$target_id", "tab_id": "$tab_id",
                     "ref": "$ref", "files": ["/explicit/user/selected/file.txt"]})]))
        raw = dict(target_id="target", tab_id="tab", snapshot={"id": "p1"}, page={"url": "https://example.org"},
            refs=[dict(ref="p1:1", role="menuitem", name="New", actions=["click"]),
                  dict(ref="p1:2", role="textbox", name="", actions=["type"])])
        built = build_browser_candidates(raw, t, self.driver.accepts)
        self.assertTrue({"click-p1:1", "type-p1:2", "pointer-double_click-p1:1"} <= {c.id for c in built})
        self.assertTrue(all(self.driver.accepts(c.tool, c.arguments) for c in built if c.tool))


class GroupingTest(unittest.TestCase):
    def test_all_large_set_options_reachable_without_tool_dispatch_or_pruning(self):
        options = [Candidate(f"click-{i}", f"Control {i}", "click", {"element_index": i}) for i in range(3000)]
        options += [Candidate("abstain", "Stop", None, {})]
        found = set()
        def visit(path):
            menu, groups = choice_menu(options, path)
            self.assertLessEqual(len(menu), 64)
            self.assertIn("abstain", {c.id for c in menu})
            if groups:
                for key in groups:
                    visit(path + (key,))
            else:
                found.update(c.id for c in menu if c.tool)
        visit(())
        self.assertEqual(found, {c.id for c in options if c.tool})


class GroupLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_driver_dispatch_thaws_arrays_and_owns_session(self):
        from types import SimpleNamespace
        class Session:
            calls = []
            async def call_tool(self, tool, arguments):
                self.calls.append((tool, arguments))
                return SimpleNamespace(isError=False, structuredContent={"status": "ok"})
        session = Session()
        driver = NativeDriver(session, "owned-session", SCHEMAS)
        candidate = Candidate("menu", "Menu", "invoke_menu", {"pid": 10, "window_id": 20, "path": ["File", "New"]})
        await driver.call(candidate.tool, candidate.arguments)
        self.assertEqual(session.calls[0][1]["path"], ["File", "New"])
        self.assertEqual(session.calls[0][1]["session"], "owned-session")

    async def test_group_decisions_do_not_execute_or_refresh_targets(self):
        class Driver:
            calls = []
            observations = 0
            def accepts(self, tool, args):
                return tool in {"click", "press_key"}
            async def observe(self, *args):
                self.observations += 1
                return observation(100)
            async def call(self, tool, args):
                self.calls.append((tool, args))
                return {"effect": "confirmed"}
        class Chooser:
            async def choose(self, request):
                criteria = request["criteria"]
                if "key-return" in criteria:
                    key = "key-return"
                else:
                    key = next(k for k, v in criteria.items() if k.startswith("group-")
                               and any(child.get("tool") == "press_key" for child in v["children"].values()))
                return Decision(key, .9, {k: float(k == key) for k in criteria}, "test")
        driver, events = Driver(), []
        outcome = await run_loop(task(), driver, Chooser(), events.append, target=(10, 20), max_steps=2)
        self.assertEqual(outcome, "budget_exhausted")
        self.assertEqual(len(driver.calls), 1)
        self.assertEqual(driver.calls[0][0], "press_key")
        self.assertEqual(driver.observations, 2)
        self.assertTrue(any(e["event"] == "candidate_group_selected" for e in events))
