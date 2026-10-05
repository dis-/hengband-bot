import tests  # isolate runtime writes, including in subprocesses
import unittest

from hengbot.cli import _build_argument_parser
from hengbot.town_arbiter import _new_town_turn_arbiter


class OwnerRetiredLogOnlyTest(unittest.TestCase):
    """User decision 2026-10-05: owner-retired is recorded, not a stop, until
    the town progress definition is rebuilt; the switch is opt-in."""

    def test_flag_is_opt_in(self):
        parser = _build_argument_parser()
        self.assertFalse(parser.parse_args(["--state-file", "x"]).owner_retired_log_only)
        self.assertTrue(parser.parse_args(["--state-file", "x", "--owner-retired-log-only"]).owner_retired_log_only)

    def test_forgive_retirement_clears_budgets_and_retirements(self):
        arbiter = _new_town_turn_arbiter()
        arbiter._retired["town-plan"] = ("vector",)
        arbiter._no_progress_by_owner["town-plan"] = 5
        arbiter._owner = "town-plan"
        arbiter._tenure = 5
        arbiter._transfer_exhausted = True
        arbiter.forgive_retirement()
        self.assertEqual(arbiter._retired, {})
        self.assertEqual(dict(arbiter._no_progress_by_owner), {})
        self.assertIsNone(arbiter._owner)
        self.assertEqual(arbiter._tenure, 0)
        self.assertFalse(arbiter._transfer_exhausted)


class OwnerRetiredLogOnlyBurstTest(unittest.TestCase):
    def test_third_retirement_within_the_window_stops_again(self):
        from hengbot import cli

        class Policy:
            pass

        policy = Policy()
        self.assertTrue(cli._owner_retired_log_only_allows(policy))
        self.assertTrue(cli._owner_retired_log_only_allows(policy))
        self.assertFalse(cli._owner_retired_log_only_allows(policy))


if __name__ == "__main__":
    unittest.main()
