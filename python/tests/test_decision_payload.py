import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Candidate
from decision_payload import compact_catalog, structured_choices
from driver_candidates import choice_menu, thaw
from jev_adapter import choose_bounded_with_typesafe


class PayloadTest(unittest.TestCase):
    def test_hierarchy_instruction_explains_exploration_not_ui_actions(self):
        from decision_payload import INSTRUCTIONS
        rule = next(r for r in INSTRUCTIONS['rules'] if 'hierarchy inspection' in r)
        for control in ('tree-next', 'tree-previous', 'tree-expand-*', 'tree-parent', 'tree-root'):
            self.assertIn(control, rule)
        self.assertIn('read-only', rule)
        self.assertIn('unseen control', rule)

    def test_native_prompt_is_verbatim_without_extra_task_plan(self):
        from native_core import Task, Observation
        from native_candidates import CandidateSet
        from native_jev import decision_request
        brief = {"required_sequence": ["Open website", "Use page search"],
                 "success": ["Evidence with source"], "input_purposes": ["Query"]}
        raw = dict(goal="Research", app="Browser", inputs=["query"], checks=[], brief=brief)
        task = Task.parse(raw)
        request = decision_request(task, Observation("s1", 1, 2, ()),
                                   CandidateSet("s1", ()), [], 10, 0)
        self.assertNotIn("task", request)
        self.assertEqual(request["goal"], raw["goal"])
        with self.assertRaises(ValueError):
            Task.parse({**raw, "brief": {"success": "unbounded wrong shape"}})

    def test_transport_compaction_preserves_catalog_and_explicit_omissions(self):
        from decision_payload import compact_request
        schemas = json.loads((Path(__file__).parent / "fixtures/driver_schemas.json").read_text())
        state = {"tools": schemas, "observation": {"before": None, "current": {"readback_text": "x"*3000}}}
        options = {"g": {"kind": "group", "count": 100, "children": {
            str(i): {"tool": "click", "args": {"element_index": i}} for i in range(100)}}}
        compact, choices = compact_request(state, options)
        self.assertEqual(set(compact["tools"]), set(schemas))
        self.assertEqual(choices["g"]["children_omitted"], 97)
        self.assertEqual(len(choices["g"]["preview"]), 3)
        self.assertEqual(compact["observation"]["current"]["readback_characters_omitted"], 1000)
        self.assertEqual(len(options["g"]["children"]), 100)

    def test_all_advertised_tools_and_constraints_survive(self):
        schemas = json.loads((Path(__file__).parent / "fixtures/driver_schemas.json").read_text())
        compact = compact_catalog(schemas)
        self.assertEqual(set(compact), set(schemas))
        self.assertEqual(len(compact), 56)
        for name, schema in schemas.items():
            self.assertEqual(compact[name].get("required"), schema.get("required"))
            self.assertEqual(set(compact[name].get("properties", {})), set(schema.get("properties", {})))
        schema = {"title": "Display", "properties": {"title": {"type": "string", "enum": ["A", "B"]}},
                  "required": ["title"], "additionalProperties": False,
                  "oneOf": [{"required": ["title"]}]}
        result = compact_catalog({"future_tool": schema})["future_tool"]
        self.assertNotIn("title", result)
        self.assertEqual(result["properties"], schema["properties"])
        self.assertEqual(result["oneOf"], schema["oneOf"])
        self.assertFalse(result["additionalProperties"])

    def test_groups_expose_all_children_and_bindings_are_lossless(self):
        candidates = [Candidate(str(i), "Observed target", "click",
                      {"pid": 10, "window_id": 20, "element_index": i}) for i in range(100)]
        menu, groups = choice_menu(candidates)
        criteria, bindings = structured_choices(menu, groups)
        children = {key: value for group in criteria.values() for key, value in group["children"].items()}
        self.assertEqual(set(children), {c.id for c in candidates})
        for candidate in candidates:
            item = children[candidate.id]
            resolved = {**{key: bindings[key] for key in item.get("inherit", [])}, **item["args"]}
            self.assertEqual(resolved, thaw(candidate.arguments))

    def test_sdk_receives_structured_options_catalog_and_instructions(self):
        class Client:
            def system_one(self, **request):
                self.request = request
                # Exercise actual installed SDK serialization, not merely a dict mock.
                import msgspec
                msgspec.json.encode(request["questions"]["driver_action"])
                return SimpleNamespace(model="test", choices={"driver_action": SimpleNamespace(
                    choice="a", confidence=.9, probabilities={"a": 1.0})})
        client = Client()
        criteria, bindings = structured_choices([Candidate("a", "Enter", "press_key", {"key": "return"})])
        choose_bounded_with_typesafe(client, goal="Task", observation={"before": None, "current": {}},
                                     criteria=criteria, history=[], tools={"press_key": {"type": "object"}}, bindings=bindings)
        self.assertEqual(client.request["questions"]["driver_action"].criteria, criteria)
        self.assertIsInstance(client.request["questions"]["driver_action"].instructions, dict)
        self.assertIn("press_key", client.request["state"]["tools"])
