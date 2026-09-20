import unittest
from unittest.mock import patch
from native_core import Decision
from native_jev import validate_decision
from native_run import parse_args, run_loop
from native_fixture import FixtureDriver
from test_native import task


class ConfidenceCutoffTest(unittest.TestCase):
    def test_cli_default_and_override(self):
        with patch('sys.argv', ['native_run.py', '--task', 'task.json']):
            self.assertEqual(parse_args().minimum_confidence, .4)
        with patch('sys.argv', ['native_run.py', '--task', 'task.json', '--minimum-confidence', '.5']):
            self.assertEqual(parse_args().minimum_confidence, .5)

    def test_boundary(self):
        for confidence in (.4, .49):
            validate_decision(Decision('abstain', confidence, {'abstain': 1}, None),
                              {'criteria': {'abstain': 'Stop'}}, .4)
        with self.assertRaises(ValueError):
            validate_decision(Decision('abstain', .39, {'abstain': 1}, None),
                              {'criteria': {'abstain': 'Stop'}}, .4)


class LoopDefaultTest(unittest.IsolatedAsyncioTestCase):
    async def test_loop_default_accepts_point_four(self):
        class Chooser:
            async def choose(self, request):
                return Decision('abstain', .4,
                                {key: float(key == 'abstain') for key in request['criteria']}, None)
        self.assertEqual(await run_loop(task(), FixtureDriver(), Chooser(), lambda e: None,
                                       target=(1, 2)), 'abstained')
