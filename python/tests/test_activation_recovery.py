import unittest
from types import SimpleNamespace
from test_native import snapshot, task, ScriptedTestChooser
from native_driver import NativeDriver, normalize
from native_candidates import build_native_candidates
from native_run import run_loop


class ActivationTest(unittest.IsolatedAsyncioTestCase):
    async def test_activation_precedes_fresh_observation_and_actions(self):
        class Driver:
            active = False
            calls = []

            def accepts(self, tool, args):
                return tool in {'bring_to_front', 'click', 'type_text'}

            async def observe(self, pid, window_id):
                if self.active:
                    return normalize(snapshot('fresh'), pid, window_id)
                return normalize(dict(pid=pid, window_id=window_id, elements=[], degraded=True,
                    degraded_reason='ax_window_unresolved',
                    background_input={'exact_window': {'status': 'ax_unresolved'}},
                    window_visibility={'on_current_space': False}), pid, window_id)

            async def call(self, tool, args):
                self.calls.append((tool, args))
                if tool == 'bring_to_front':
                    self.active = True
                    return {'status': 'activated', 'exact_window_effect': {'verified': True}}
                self_outer.assertEqual(args['element_token'], 'fresh:1')
                return {'status': 'ok'}

        self_outer = self
        driver = Driver()
        chooser = ScriptedTestChooser(['activate-window', 'click-1', 'abstain'])
        result = await run_loop(task(), driver, chooser, lambda _: None, target=(1, 2))
        self.assertEqual(result, 'abstained')
        first = chooser.requests[0]
        self.assertEqual(set(first['criteria']), {'activate-window', 'reobserve', 'abstain'})
        self.assertEqual(first['observation']['current']['availability']['reason'], 'ax_window_unresolved')
        self.assertEqual(chooser.requests[1]['observation']['current']['snapshot_id'], 'fresh')

    async def test_focus_is_held_until_explicit_cleanup(self):
        class Session:
            calls = []

            async def call_tool(self, tool, args):
                self.calls.append((tool, args))
                data = {'list_apps': {'apps': [{'pid': 99, 'active': True}]},
                        'list_windows': {'windows': [{'window_id': 88, 'is_on_screen': True, 'title': 'Prior', 'z_index': 1}]},
                        'bring_to_front': {'status': 'activated', 'exact_window_effect': {'verified': True}}}[tool]
                return SimpleNamespace(isError=False, structuredContent=data)

        session = Session()
        schemas = {t: {'type': 'object', 'properties': {k: {} for k in ('pid', 'window_id')}}
                   for t in ('list_apps', 'list_windows', 'bring_to_front')}
        driver = NativeDriver(session, 'test', schemas)
        await driver.call('bring_to_front', {'pid': 1, 'window_id': 2})
        self.assertEqual([a for t, a in session.calls if t == 'bring_to_front'], [{'pid': 1, 'window_id': 2}])
        await driver.restore_focus()
        self.assertEqual(session.calls[-1], ('bring_to_front', {'pid': 99, 'window_id': 88}))
        self.assertIsNone(driver.restore_target)

    def test_healthy_background_observation_does_not_force_activation(self):
        obs = normalize(snapshot(), 1, 2)
        choices = build_native_candidates(task(), obs, lambda *_: True)
        self.assertNotIn('activate-window', {c.id for c in choices.candidates})

    def test_read_only_does_not_activate(self):
        obs = normalize(dict(snapshot_id='s', elements=[]), 1, 2)
        choices = build_native_candidates(task(), obs, lambda *_: True, read_only=True)
        self.assertFalse(any(c.tool for c in choices.candidates))
