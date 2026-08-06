import os
import unittest

from absorbing_state_catalog import SEEDED_STATES
from absorbing_state_harness import drive


class AbsorbingStateHarnessTest(unittest.TestCase):
    def test_catalogue_is_cheap_and_grows_by_data(self):
        self.assertEqual(len(SEEDED_STATES), 6)
        self.assertEqual(len({state.name for state in SEEDED_STATES}), 6)
        self.assertTrue(all(state.build and state.arrived for state in SEEDED_STATES))


if os.environ.get("HENGBOT_LONG_ABSORBING_STATES") == "1":
    class SeededAbsorbingStateTest(unittest.TestCase):
        def test_six_seeded_states_reach_progress_or_visible_terminal(self):
            failures = []
            for state in SEEDED_STATES:
                with self.subTest(state=state.name):
                    result = drive(state)
                    if not result.passed:
                        failures.append(result.report())
            self.assertEqual(failures, [], "\n" + "\n".join(failures))
