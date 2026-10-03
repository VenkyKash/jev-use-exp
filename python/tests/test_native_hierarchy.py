import unittest
from dataclasses import replace
from test_native import snapshot, task, ScriptedTestChooser
from native_driver import normalize
from native_hierarchy import HierarchyView
from native_run import run_loop


class HierarchyTest(unittest.TestCase):
    def test_root_context_survives_deep_inspection_and_refreshes(self):
        raw = dict(snapshot_id='s1', elements=[
            dict(element_index=0, role='AXWindow', label='Home - Site'),
            dict(element_index=1, role='AXTextField', label='Address', value='site.test', parent_index=0),
            dict(element_index=2, role='AXWebArea', label='Home', parent_index=0),
            dict(element_index=3, role='AXButton', label='New', parent_index=2)])
        obs = normalize(raw, 1, 2)
        tree = HierarchyView(obs)
        root = tree.project().root_context
        tree.navigate('tree-expand-0', 's1')
        tree.navigate('tree-expand-2', 's1')
        view = tree.project()
        self.assertEqual(view.root_context, root)
        self.assertEqual(root['controls'][1]['value'], 'site.test')
        self.assertEqual([e.index for e in view.elements], [2, 3])
        from native_candidates import build_native_candidates
        from native_jev import decision_request
        choices = build_native_candidates(task(), view, lambda *_: True)
        request = decision_request(task(), view, choices, [], 10, 0)
        self.assertEqual(request['observation']['current']['root'], root)
        self.assertNotIn('before', request['observation'])
        self.assertNotIn('type-1-0', {c.id for c in choices.candidates})
        raw['snapshot_id'] = 's2'
        raw['elements'][1]['value'] = 'other.test'
        refreshed = HierarchyView(normalize(raw, 1, 2)).project().root_context
        self.assertEqual(refreshed['snapshot_id'], 's2')
        self.assertEqual(refreshed['controls'][1]['value'], 'other.test')

    def test_all_controls_reachable_including_flat_and_orphaned_nodes(self):
        rows = [dict(element_index=i, role='AXButton', label=str(i),
                     parent_index=None if i == 0 else 0 if i < 80 else 999) for i in range(100)]
        obs = normalize(dict(snapshot_id='s', elements=rows), 1, 2)
        tree = HierarchyView(obs, page_size=7)
        seen, states, todo = set(), set(), [(None, 0)]
        while todo:
            tree.parent, tree.offset = todo.pop()
            state = (tree.parent, tree.offset)
            if state in states:
                continue
            states.add(state)
            seen.update(e.index for e in tree.project().elements)
            for choice in tree.choices():
                tree.parent, tree.offset = state
                tree.navigate(choice.id, 's')
                todo.append((tree.parent, tree.offset))
        self.assertEqual(seen, set(range(100)))
        self.assertEqual(len(obs.elements), 100)

    def test_stale_or_invented_navigation_rejected(self):
        tree = HierarchyView(normalize(snapshot(), 1, 2), page_size=1)
        with self.assertRaisesRegex(ValueError, 'stale'):
            tree.navigate('tree-next', 'different')
        with self.assertRaisesRegex(ValueError, 'unknown'):
            tree.navigate('tree-expand-999', 's1')

    def test_projection_never_claims_full_coverage(self):
        tree = HierarchyView(normalize(snapshot(), 1, 2), page_size=1)
        view = tree.project()
        self.assertFalse(view.complete)
        self.assertEqual(view.inspection['total_controls'], 3)
        self.assertEqual(view.inspection['range_end'], 1)


class HierarchyLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_expand_has_no_io_and_action_uses_original_reference(self):
        class Driver:
            reads = 0
            calls = []
            def accepts(self, tool, args):
                return tool == 'click'
            async def observe(self, pid, window_id):
                self.reads += 1
                return normalize(dict(snapshot_id=f's{self.reads}', elements=[
                    dict(element_index=0, role='AXWindow', label='Window'),
                    dict(element_index=1, role='AXButton', label='Submit', parent_index=0,
                         element_token=f's{self.reads}:1')]), pid, window_id)
            async def call(self, tool, args):
                self.calls.append((tool, args))
                return {'status': 'ok'}
        driver = Driver()
        chooser = ScriptedTestChooser(['tree-expand-0', 'click-1', 'abstain'])
        outcome = await run_loop(task(), driver, chooser, lambda _: None, target=(1, 2), hierarchy=True)
        self.assertEqual(outcome, 'abstained')
        self.assertEqual(driver.reads, 2)
        self.assertEqual(len(driver.calls), 1)
        self.assertEqual(driver.calls[0][1]['element_token'], 's1:1')
        self.assertIsNone(chooser.requests[2]['observation']['current']['inspection']['parent'])
        self.assertEqual(chooser.requests[0]['observation']['current']['snapshot_id'],
                         chooser.requests[1]['observation']['current']['snapshot_id'])
