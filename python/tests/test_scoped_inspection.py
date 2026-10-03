import unittest

from test_native import snapshot, task, ScriptedTestChooser
from native_candidates import build_native_candidates
from native_driver import normalize
from native_core import verify
from native_jev import decision_request
from native_run import run_loop


class ScopedInspectionTest(unittest.TestCase):
    def test_queries_are_observed_deduplicated_and_schema_checked(self):
        raw = snapshot()
        raw['elements'].append(dict(element_index=9, role='AXStaticText', label='SUBMIT'))
        obs = normalize(raw, 1, 2)
        choices = build_native_candidates(task(), obs, lambda t, a: t == 'get_window_state').candidates
        inspections = [c for c in choices if c.tool]
        self.assertEqual([c.arguments['query'] for c in inspections], ['Name', 'Submit', 'Result'])
        self.assertTrue(all(c.arguments['include_screenshot'] is True for c in inspections))
        denied = build_native_candidates(task(), obs, lambda *_: False)
        self.assertFalse(any(c.tool == 'get_window_state' for c in denied.candidates))

    def test_partial_result_never_verifies_even_with_matching_value(self):
        raw = dict(snapshot(value='Done'), element_count=100)
        obs = normalize(raw, 1, 2, query='Result')
        self.assertFalse(verify(task(), obs))
        self.assertEqual(obs.inspection['total_element_count'], 100)
        candidates = build_native_candidates(task(), obs, lambda *_: False)
        current = decision_request(task(), obs, candidates, [], 5, 0)['observation']['current']
        self.assertEqual(current['inspection']['query'], 'Result')
        self.assertFalse(current['complete'])

    def test_empty_scope_is_partial_and_can_return_to_full(self):
        obs = normalize(dict(snapshot_id='empty', elements=[]), 1, 2, query='gone')
        self.assertFalse(obs.complete)
        self.assertIn('reobserve', [c.id for c in build_native_candidates(task(), obs, lambda *_: True).candidates])
        self.assertIsNone(normalize(snapshot(), 1, 2).inspection)


class ScopedLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_scoped_snapshot_used_directly_then_full_view_restored(self):
        class Driver:
            def __init__(self):
                self.reads = 0
                self.calls = []

            def accepts(self, tool, arguments):
                return tool in {'click', 'get_window_state'}

            async def observe(self, pid, window_id):
                self.reads += 1
                return normalize(snapshot(f'full-{self.reads}'), pid, window_id)

            async def call(self, tool, arguments):
                self.calls.append((tool, arguments))
                if tool == 'get_window_state':
                    raw = snapshot('scoped')
                    raw['elements'] = [raw['elements'][1]]
                    return raw
                self_outer.assertEqual(arguments['element_token'], 'scoped:1')
                return {'status': 'ok'}

        self_outer = self
        driver = Driver()
        chooser = ScriptedTestChooser(['inspect-1', 'click-1', 'abstain'])
        events = []
        result = await run_loop(task(), driver, chooser, events.append, target=(1, 2))
        self.assertEqual(result, 'abstained')
        self.assertEqual(driver.reads, 2)
        self.assertEqual(chooser.requests[1]['observation']['current']['snapshot_id'], 'scoped')
        self.assertEqual(chooser.requests[1]['observation']['current']['inspection']['query'], 'Submit')
        self.assertIsNone(chooser.requests[2]['observation']['current']['inspection'])
        self.assertEqual(chooser.requests[1]['history'][-1]['outcome'], 'inspection_read_not_task_progress')

    async def test_reobserve_leaves_scope(self):
        class Driver:
            def accepts(self, tool, arguments):
                return tool == 'get_window_state'

            async def observe(self, pid, window_id):
                return normalize(snapshot(), pid, window_id)

            async def call(self, tool, arguments):
                return dict(snapshot_id='empty', elements=[])

        chooser = ScriptedTestChooser(['inspect-1', 'reobserve', 'abstain'])
        await run_loop(task(), Driver(), chooser, lambda _: None, target=(1, 2))
        self.assertIsNone(chooser.requests[2]['observation']['current']['inspection'])
