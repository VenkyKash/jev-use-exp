import unittest
from dataclasses import replace
from test_native import task
from native_driver import normalize
from native_candidates import build_native_candidates
from native_geometry import AreaClick, center, validate_pixel_target


def observation():
    return normalize(dict(snapshot_id='s1', elements=[
        dict(element_index=0, role='AXButton', label='Row', actions=['AXPress'],
             frame=dict(x=-80, y=70, w=100, h=40), element_token='s1:0'),
        dict(element_index=1, role='AXImage', label='Icon', parent_index=0,
             frame=dict(x=-75, y=75, w=20, h=20), element_token='s1:1')],
        screenshot_frame_valid=True, window_bounds=dict(x=-100, y=50, width=400, height=300),
        screenshot_width=800, screenshot_height=600), 1, 2)


class GeometryTest(unittest.TestCase):
    def test_retina_and_negative_screen_origin(self):
        obs = observation()
        self.assertEqual(center(obs.elements[0], obs), (140, 80))
        self.assertEqual(center(obs.elements[1], obs), (70, 70))
        self.assertEqual(obs.compact()[1]['frame'], [-75, 75, 20, 20])

    def test_scaled_capture(self):
        obs = observation()
        obs = replace(obs, geometry={**obs.geometry, 'width': 200, 'height': 150})
        self.assertEqual(center(obs.elements[0], obs), (35, 20))

    def test_missing_clipped_tiny_disabled_bounds_have_no_pixel_choice(self):
        obs = observation()
        for frame in (None, (-110,70,100,40), (-80,70,1,40), (290,70,20,20)):
            self.assertIsNone(center(replace(obs.elements[0], frame=frame), obs))
        self.assertIsNone(center(replace(obs.elements[0], enabled=False), obs))
        self.assertIsNone(center(obs.elements[0], replace(obs, geometry=None)))

    def test_alternatives_are_schema_checked_and_child_specific(self):
        obs = observation()
        built = build_native_candidates(task(), obs, lambda *_: True)
        points = [c for c in built.candidates if isinstance(c, AreaClick)]
        self.assertEqual(len(points), 6)
        self.assertEqual((points[2].target_index, points[2].area_index), (0, 1))
        self.assertTrue(all('element_token' in c.arguments for c in points))
        self.assertNotEqual(points[0].arguments['x'], points[2].arguments['x'])
        with self.assertRaisesRegex(ValueError, 'stale'):
            built.resolve(points[0].id, 'new-snapshot')
        denied = build_native_candidates(task(), obs, lambda t,a: 'x' not in a)
        self.assertFalse(any(isinstance(c, AreaClick) for c in denied.candidates))
        read_only = build_native_candidates(task(), obs, lambda *_: True, read_only=True)
        self.assertFalse(any(c.tool for c in read_only.candidates))

    def test_no_geometry_means_no_invented_areas(self):
        obs = replace(observation(), geometry=None)
        choices = build_native_candidates(task(), obs, lambda *_: True).candidates
        self.assertNotIn('capture-geometry', {c.id for c in choices})
        self.assertFalse(any(isinstance(c, AreaClick) for c in choices))
        self.assertIn('click-0', {c.id for c in choices})

    def test_child_outside_target_is_not_its_click_area(self):
        obs = observation()
        child = replace(obs.elements[1], frame=(100, 75, 20, 20))
        choices = build_native_candidates(task(), replace(obs, elements=(obs.elements[0], child)), lambda *_: True).candidates
        self.assertFalse(any(isinstance(c, AreaClick) and c.target_index == 0 and c.area_index == 1 for c in choices))

    def test_payload_identifies_target_and_area(self):
        from native_jev import decision_request
        obs = observation()
        built = build_native_candidates(task(), obs, lambda *_: True)
        request = decision_request(task(), obs, built, [], 10, 1)
        self.assertEqual(request['observation']['current']['click_targets']['click-0-area-1-background'],
                         dict(target=0, area=1, method='coordinates'))

    def test_overlaps_do_not_expand_hitboxes_or_shift_centers(self):
        obs = observation()
        overlap = replace(obs.elements[1], frame=obs.elements[0].frame)
        self.assertEqual(center(overlap, obs), center(obs.elements[0], obs))


class GeometryPreflightTest(unittest.IsolatedAsyncioTestCase):
    async def test_compound_choice_dispatches_one_click_without_retry(self):
        from native_run import run_loop
        from test_native import ScriptedTestChooser
        obs = observation()
        class Driver:
            def __init__(self):
                self.calls = []
            def accepts(self, tool, args):
                return tool == 'click'
            async def observe(self, *args):
                return obs
            async def call(self, tool, args):
                self.calls.append((tool, args))
                if tool == 'list_windows':
                    return {'windows': [dict(pid=1, window_id=2, is_on_screen=True,
                        on_current_space=True, bounds=obs.geometry['window_bounds'])]}
                return {'effect': 'unverifiable'}
        driver = Driver()
        events = []
        result = await run_loop(task(), driver,
            ScriptedTestChooser(['click-0-area-1-background', 'abstain']), events.append, target=(1, 2))
        clicks = [args for tool, args in driver.calls if tool == 'click']
        self.assertEqual(len(clicks), 1)
        self.assertEqual((clicks[0]['x'], clicks[0]['y']), (70, 70))
        self.assertIn('element_token', clicks[0])
        targeting = next(e['targeting'] for e in events if e['event'] == 'step_result')
        self.assertEqual((targeting['target'], targeting['area']), (0, 1))
        self.assertEqual(result, 'abstained')

    async def test_moved_hidden_or_foreign_window_refuses(self):
        obs = observation()
        class Driver:
            window = dict(pid=1, window_id=2, is_on_screen=True, on_current_space=True,
                          bounds=obs.geometry['window_bounds'])
            async def call(self, tool, arguments):
                return {'windows': [self.window]}
        driver = Driver()
        await validate_pixel_target(driver, obs)
        for change in ({'pid':3}, {'is_on_screen':False}, {'on_current_space':False},
                       {'bounds':dict(x=0,y=0,width=400,height=300)}):
            driver.window = {**Driver.window, **change}
            with self.assertRaises(ValueError):
                await validate_pixel_target(driver, obs)
