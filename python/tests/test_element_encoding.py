import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from decision_payload import encode_elements, decode_elements, encode_before, decode_before


class ElementEncodingTest(unittest.TestCase):
    def test_exact_roundtrip_and_smaller_payload(self):
        import json
        original = [dict(id=i, role="AXButton", label=f"Control {i}", value=None,
                         actions=["AXPress", "AXShowMenu"], enabled=True, parent=0) for i in range(481)]
        table = encode_elements(original)
        restored = decode_elements(table)
        self.assertEqual(restored, original)
        self.assertLess(len(json.dumps(table)), len(json.dumps(original))/2)

    def test_missing_is_not_null(self):
        original = [{"id": 1}, {"id": 2, "value": None}]
        self.assertEqual(encode_elements(original), original)

    def test_defaults_exceptions_and_duplicate_labels(self):
        original = [dict(id=i, enabled=i != 9, value=None if i != 9 else "changed", label="Repeated label "*5) for i in range(10)]
        table = encode_elements(original)
        self.assertEqual(table["defaults"]["enabled"], True)
        self.assertEqual(table["overrides"]["9"]["value"], "changed")
        self.assertEqual(decode_elements(table), original)

    def test_before_current_roundtrip_including_null_and_reordered_controls(self):
        import copy, json
        current = {"snapshot_id": "new", "rows": [[i, "label", None] for i in range(300)], "new_only": None}
        before = copy.deepcopy(current)
        before["snapshot_id"] = "old"
        before["rows"][4], before["rows"][5] = before["rows"][5], before["rows"][4]
        before.pop("new_only")
        before["old_only"] = False
        encoded = encode_before(before, current)
        self.assertEqual(encoded["encoding"], "current_patch_v1")
        self.assertEqual(decode_before(encoded, current), before)
        self.assertLess(len(json.dumps(encoded)), len(json.dumps(before)))
        self.assertEqual(current["snapshot_id"], "new")
        self.assertEqual(decode_before(encode_before({"x": 1}, {"y": 2}), {"y": 2}), {"x": 1})
