import unittest
from v2_payload.perception import (
    VisualRegion,
    parse_raw_regions,
    cluster_into_lines,
    format_visual_lines_for_prompt,
    should_trigger_adaptive_perception,
    build_visual_click_candidates,
)


class TestPerceptionModule(unittest.TestCase):
    def test_parse_and_cluster(self):
        raw = [
            {"id": "t1", "kind": "text", "text": "Even", "bounds": {"x": 50, "y": 100, "width": 40, "height": 20}, "confidence": 0.9},
            {"id": "t2", "kind": "text", "text": "Odd", "bounds": {"x": 150, "y": 102, "width": 40, "height": 20}, "confidence": 0.85},
            {"id": "t3", "kind": "text", "text": "2", "bounds": {"x": 50, "y": 130, "width": 20, "height": 20}, "confidence": 0.95},
            {"id": "t4", "kind": "text", "text": "1", "bounds": {"x": 150, "y": 131, "width": 20, "height": 20}, "confidence": 0.91},
            {"id": "i1", "kind": "icon", "label": "save_icon", "bounds": {"x": 10, "y": 10, "width": 24, "height": 24}, "confidence": 0.99, "interactive": True},
        ]
        parsed = parse_raw_regions(raw, min_confidence=0.5)
        self.assertEqual(len(parsed), 5)

        lines = cluster_into_lines(parsed, window_width=800, window_height=600)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].text, "Even Odd")
        self.assertEqual(lines[0].location, "top-left")
        self.assertEqual(lines[1].text, "2 1")

        formatted = format_visual_lines_for_prompt(lines, max_lines=10, max_bytes=500)
        self.assertEqual(len(formatted), 2)
        self.assertIn("[top-left] Even Odd", formatted[0])

    def test_format_visual_lines_head_tail_preservation(self):
        from v2_payload.perception import VisualLine
        mock_lines = [
            VisualLine(text=f"Line {i}", y_center=i * 10.0, location="top-left" if i < 10 else "bottom-left", regions=[])
            for i in range(30)
        ]
        # Request max 10 lines: should retain 5 head lines, 5 tail lines, and 1 intermediate omission marker
        formatted = format_visual_lines_for_prompt(mock_lines, max_lines=10, max_bytes=2000)
        self.assertEqual(len(formatted), 11)
        self.assertIn("[top-left] Line 0", formatted[0])
        self.assertIn("[top-left] Line 4", formatted[4])
        self.assertIn("intermediate visually detected lines omitted", formatted[5])
        self.assertIn("[bottom-left] Line 25", formatted[6])
        self.assertIn("[bottom-left] Line 29", formatted[10])

    def test_adaptive_trigger(self):
        class DummyObs:
            capture_id = "cap_123"
            elements = ()

        obs = DummyObs()
        should_run, cached = should_trigger_adaptive_perception(obs, has_dominant_canvas=False)
        self.assertTrue(should_run)
        self.assertFalse(cached)

        # Same capture cached
        should_run_2, cached_2 = should_trigger_adaptive_perception(obs, has_dominant_canvas=False, last_capture_id="cap_123")
        self.assertFalse(should_run_2)
        self.assertTrue(cached_2)

    def test_visual_click_candidates(self):
        class DummyElement:
            def __init__(self, frame):
                self.frame = frame

        class DummyObs:
            pid = 100
            window_id = 200
            capture_id = "cap_123"
            elements = (DummyElement([50, 100, 40, 20]),)  # Overlaps t1

        regions = [
            VisualRegion("t1", "text", "Even", {"x": 50, "y": 100, "width": 40, "height": 20}, 0.9),
            VisualRegion("t2", "text", "Odd", {"x": 150, "y": 102, "width": 40, "height": 20}, 0.85),
            VisualRegion("i1", "icon", "play", {"x": 300, "y": 300, "width": 30, "height": 30}, 0.9, interactive=True),
        ]
        obs = DummyObs()
        candidates = build_visual_click_candidates(regions, obs, lambda tool, args: True, {})
        
        # t1 overlaps AX element, so only t2 and i1 should produce click candidates
        c_ids = {c.id for c in candidates}
        self.assertNotIn("visual-click-t1", c_ids)
        self.assertIn("visual-click-t2", c_ids)
        self.assertIn("visual-click-i1", c_ids)

    def test_no_effect_annotation_pattern(self):
        did_not_work = [
            "Click AXPopUpButton 'Summary' (element 85, parent 84). (no_effect)"
        ]
        action_criteria = {
            "click-85": "Click AXPopUpButton 'Summary' (element 85, parent 84).",
            "double_click-85": "Double-click AXPopUpButton 'Summary' (element 85) to edit, rename, or open inline.",
            "regions": "None of these fit; go back to the region list"
        }
        for act_id, act_desc in list(action_criteria.items()):
            if act_id in ("done", "look_closely", "regions"):
                continue
            for dnw in did_not_work[-5:]:
                if "no_effect" in dnw:
                    act_parts = act_id.split("-")
                    el_id = act_parts[-1] if (act_parts and act_parts[-1].isdigit()) else None
                    if act_desc in dnw or (el_id and f"element {el_id}" in dnw):
                        action_criteria[act_id] = f"{act_desc} (previously attempted; had no effect)"
                        break

        self.assertIn("(previously attempted; had no effect)", action_criteria["click-85"])
        self.assertNotIn("(previously attempted; had no effect)", action_criteria["regions"])


if __name__ == "__main__":
    unittest.main()

