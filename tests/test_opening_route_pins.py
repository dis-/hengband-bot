"""Issue #47: public decisions pin the opening route's return and stop seams."""
import tests  # noqa: F401

from dataclasses import replace
import unittest

from hengbot.cli import _policy_final_stop_banner
from hengbot.model import parse_snapshot
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
import tests.test_opening_route_recorded as opening_harness


class OpeningRoutePinsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = opening_harness.captured()

    def harness(self):
        harness = opening_harness.OpeningRouteRecordedTest()
        harness.data = self.data
        return harness

    def test_unaffordable_route_is_an_operator_visible_final_stop(self):
        policy, raw, _ = self.harness().shopping_case(gold=0)
        raw["store"] = None
        board = parse_snapshot(raw, policy._monrace_knowledge)

        key = policy.choose_key(board)

        self.assertEqual(str(key), "")
        self.assertEqual(policy.last_reason, "quest:blocked:opening-route")
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)
        banner = _policy_final_stop_banner(policy.last_reason)
        self.assertIn("Q34 -> mining kit -> Q1", banner)
        self.assertIn("_opening_q1_failure", banner)

    def test_restarted_income_run_returns_to_the_fixed_route(self):
        # DECLARED CONSTRUCTED from the recorded "throw" Yeek Cave 1F board:
        # the target has gone, the player stands on known upstairs, and HP=250
        # rules out emergency recovery. Q34 reward, protocol and kit are copied.
        # No Q1 funding debt exists: an old ordinary mining/scavenge run must
        # ascend even when it still has supplies and could continue earning.
        for mode in ("mine", "scavenge", None):
            with self.subTest(mode=mode):
                harness = self.harness()
                policy = harness.policy()
                board = harness.seed("throw")
                grids = dict(board.grids)
                grids[board.player.position] = replace(
                    grids[board.player.position], has_up_stairs=True)
                board = replace(
                    board, grids=grids, visible_monsters=[], detected_monsters=[],
                    player=replace(board.player, hp=250, max_hp=250))
                harness.prepare(policy, board)
                policy._fundraising_mode = mode

                key = policy.choose_key(board)

                self.assertEqual((str(key), policy.last_reason),
                                 ("<", "fundraise:ascend"))
                self.assertTrue(policy._returning_to_town)


if __name__ == "__main__":
    unittest.main()
