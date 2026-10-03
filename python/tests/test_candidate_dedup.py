import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from decision_payload import deduplicate_choices
from core import Candidate
from driver_candidates import normalize_candidates, choice_menu
from decision_payload import structured_choices


class CandidateNormalizationTest(unittest.TestCase):
    def test_exact_calls_merge_before_grouping_with_aliases(self):
        candidates = [Candidate(str(i), f'Observed area {i}', 'click',
                                {'x': 10, 'y': 20, 'pid': 1}) for i in range(80)]
        menu, groups = choice_menu(candidates)
        self.assertFalse(groups)
        self.assertEqual(len(menu), 1)
        self.assertEqual(menu[0].id, '0')
        self.assertEqual(menu[0].arguments, candidates[0].arguments)
        self.assertEqual(len(menu[0].aliases), 79)
        self.assertEqual(normalize_candidates(menu), menu)
        criteria, _ = structured_choices(menu)
        self.assertEqual(criteria['0']['aliases'][0], '1: Observed area 1')

    def test_different_calls_and_capture_guards_remain_distinct(self):
        args = [dict(x=10, y=20), dict(x=11, y=20),
                dict(x=10, y=20, delivery_mode='foreground'),
                dict(x=10, y=20, delivery_mode='background'),
                dict(element_token='s1:1'), dict(element_token='s2:1'),
                dict(x=10, y=20, extra=None)]
        candidates = [Candidate(str(i), 'target', 'click', a) for i,a in enumerate(args)]
        candidates += [Candidate('capture', 'target', 'click', args[0], capture_id='s1'),
                       Candidate('other-tool', 'target', 'double_click', args[0]),
                       Candidate('review', 'review', None, {}),
                       Candidate('abstain', 'abstain', None, {})]
        self.assertEqual(normalize_candidates(candidates), candidates)

    def test_argument_key_order_does_not_matter_and_duplicate_ids_reject(self):
        a = Candidate('a', 'a', 'click', dict(x=10, y=20))
        b = Candidate('b', 'b', 'click', dict(y=20, x=10))
        self.assertEqual(len(normalize_candidates([a, b])), 1)
        with self.assertRaisesRegex(ValueError, 'duplicate candidate IDs'):
            normalize_candidates([a, a])

    def test_compound_click_subclass_and_alternate_area_preserved(self):
        from native_geometry import AreaClick
        args = dict(x=10, y=20)
        a = AreaClick('a', 'target 1 area 1', 'click', args, target_index=1, area_index=1)
        b = AreaClick('b', 'target 1 area 2', 'click', args, target_index=1, area_index=2)
        result = normalize_candidates([a, b])
        self.assertIsInstance(result[0], AreaClick)
        self.assertEqual(result[0].target_index, 1)
        self.assertIn('target 1 area 2', result[0].aliases[0])


class DedupTest(unittest.TestCase):
    def test_multiple_tool_families(self):
        choices = {str(i): {"tool": tool, "args": {"pid": 1}, "description": tool}
                   for i, tool in enumerate(["click", "click", "press_key", "press_key"])}
        result, templates, _ = deduplicate_choices(choices)
        self.assertEqual(len(templates), 2)
        self.assertEqual(set(result), set(choices))

    def test_exact_round_trip(self):
        import json
        original = {str(i): {"tool": "type_text", "inherit": ["pid", "window_id"],
                    "description": "Insert supplied text into observed field " + str(i),
                    "args": {"text": "Repeated task input "*20, "element_index": i}}
                    for i in range(40)}
        choices, templates, shared = deduplicate_choices(original)
        def resolve(v):
            if isinstance(v, dict):
                if set(v) == {"$ref"}: return shared[v["$ref"]]
                return {k: resolve(x) for k,x in v.items()}
            if isinstance(v,list): return [resolve(x) for x in v]
            return v
        for key, row in choices.items():
            row = resolve(row)
            template = resolve(templates[row.pop("template")])
            args = {**template.pop("args"), **row.pop("args")}
            prefix = template.pop("description_prefix", "")
            suffix = row.pop("description_suffix", None)
            restored = {**template, **row, "args": args}
            if suffix is not None: restored["description"] = prefix+suffix
            self.assertEqual(restored, original[key])
        self.assertLess(len(json.dumps([choices,templates,shared])), len(json.dumps(original)))
