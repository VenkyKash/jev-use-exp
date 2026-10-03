import unittest
from test_native import task, ScriptedTestChooser
from native_fixture import FixtureDriver
from native_run import run_loop


class SetupBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_without_target_never_calls_chooser(self):
        driver, chooser = FixtureDriver(), ScriptedTestChooser([])
        self.assertEqual(await run_loop(task(), driver, chooser, lambda e: None,
                                       dry_run=True), "dry_run")
        self.assertEqual(driver.calls, [])
        self.assertEqual(chooser.requests, [])

    async def test_uncertain_launch_is_not_retried_or_sent_to_jev(self):
        class Broken(FixtureDriver):
            async def call(self, tool, arguments):
                await super().call(tool, arguments)
                raise TimeoutError()
        driver, chooser = Broken(), ScriptedTestChooser([])
        self.assertEqual(await run_loop(task(), driver, chooser, lambda e: None), "unknown")
        self.assertEqual(len(driver.calls), 1)
        self.assertEqual(chooser.requests, [])

    async def test_read_only_launches_once_then_offers_no_mutations(self):
        driver, chooser = FixtureDriver(), ScriptedTestChooser(["abstain"])
        self.assertEqual(await run_loop(task(), driver, chooser, lambda e: None,
                                       read_only=True), "abstained")
        self.assertEqual(len(driver.calls), 1)
        self.assertEqual(driver.calls[0][0], "launch_app")
        self.assertEqual(set(chooser.requests[0]["criteria"]), {"reobserve", "abstain"})
        self.assertTrue(chooser.requests[0]["observation"]["current"]["elements"])
