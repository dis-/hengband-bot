"""n1-c life-207's recall countdown re-entering Home (2026-11-14 05:50, owner-retired-burst).

Recorded: the town-arrival checkpoint of the 05:50:38 visit (build bot-3eef22a25),
journal rows 0-34 and sidecar files (tests/extract_n1c_207_wait_recall_1114_fixture.py),
through the public choose_key; the keys are posted through the production
executor (``_ExecutorInputPort``).

Row 21 began the Home junk sweep (policy_home ``_begin_home_junk_sweep``) on the two
Potions of Intelligence it took for surplus, Intelligence being at the character's
maximum.  Row 24 read the recall (town:recall-to-alt-dungeon) and row 25 stepped off the
Home entrance.  The relief in ``_decide`` ran before the departure's recall guard
(ladder_objectives town:wait-recall), so row 32 walked the sweep back onto the entrance
('1' under the label town:wait-recall); the page was left for the recall
(town:wait-recall-leave) and the entrance re-entered (shop:travel:await-entry '5'), 40
decisions in 7 seconds, until the supervisor stopped the owner.  Fix c4e02d7694: the relief
waits while a town recall counts down.

stat-potion-ownership-1114: those two potions were not in Home.  Row 16 had taken the whole
stack (``5pl2``) and rows 18 and 20 drank both; the confirmed take left the emptied stack in
the catalogue, and the sweep filed the take of that absent stack.  The take now leaves the
catalogue (policy_home._remove_taken_from_home_catalogue), so row 21 starts no sweep: it takes
the Potions of Strength, drinks them and reads the recall
(tests/test_stat_potion_ownership_1114_recorded.py).  The recorded rows from 21 on follow the
old sweep and are not replayed; the countdown guard is pinned on the new flow's own read.

DECLARED CONSTRUCTED: the Home and its entrance (StatPotionHomeGame); the countdown's boards
after the read (the recall is set, each wait spends a turn).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace

from hengbot import item_use_route
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.policy import WAIT_KEY
from tests.support import recorded as executor_harness
from tests import test_stat_potion_ownership_1114_recorded as ownership

DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


class N1c207WaitRecall1114RecordedTest(ownership.StatPotionOwnership1114RecordedTest,
                                       executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    # The inherited pins run in their own module.
    test_the_whole_taken_stack_leaves_the_catalogue = None
    test_row_21_takes_the_useful_stack_and_never_the_absent_one = None
    test_a_surplus_home_stack_is_the_sweeps_and_sold = None
    test_a_carried_potion_past_the_maximum_is_released_to_the_sale = None

    def read_recall(self):
        """Row 21 on: the Strength take, both drunk, the recall read; the read's board."""
        policy, board = self.to_row_21()
        key = policy.choose_key(board)
        shelf = [ownership.store_row(item) for item in policy._home_knowledge_items]
        game, reasons = self.drive(policy, board, key, shelf)
        self.assertEqual(reasons[-1], ("rei", "town:recall-to-alt-dungeon"), reasons)
        self.assertEqual(game.quaffed, ["腕力の薬", "腕力の薬"], reasons)
        self.assertIsNone(policy._home_full_relief)
        policy.confirm_key_posted("rei")
        # DECLARED CONSTRUCTED: the read's effect, the recall counting down.
        raw = self.later(game._state(), turns=1)
        raw["player"] = dict(raw["player"], recalling=True)
        return policy, raw

    def test_the_visit_ends_in_the_recall_without_a_sweep(self):
        policy, raw = self.read_recall()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        entrance = next(grid.position for grid in board.grids.values()
                        if grid.store_number == STORE_HOME)
        self.assertEqual(board.player.position, entrance)
        self.assertTrue(board.player.recalling)

    def test_recall_countdown_stays_off_the_home_entrance(self):
        policy, raw = self.read_recall()
        # DECLARED CONSTRUCTED: a surplus ware on the Home shelf, the Home sweep's (the old row 21's
        # 知能の薬 x2, now real): the countdown still never walks back to Home for it.
        catalogue = list(policy._home_knowledge_items)
        potion = next(index for index, item in enumerate(catalogue) if item.tval == ownership.INT_KIND[0])
        catalogue.insert(potion, replace(catalogue[potion], name="知能の薬", sval=ownership.INTELLIGENCE,
                                         count=2))
        policy.consume_home_knowledge(tuple(catalogue))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        home_int = next(item for item in policy._home_knowledge_items
                        if (item.tval, item.sval) == ownership.INT_KIND)
        self.assertTrue(item_use_route.surplus(policy, board, home_int))
        entrance = board.player.position
        # On the entrance the countdown steps off (the recorded row 25 '9').
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:wait-recall-step-off")
        self.assertIn(key, DIRECTIONS)
        dy, dx = DIRECTIONS[key]
        following = self.later(raw)
        following["player"] = dict(following["player"], y=raw["player"]["y"] + dy,
                                   x=raw["player"]["x"] + dx)
        self.assertEqual(self.post(policy, raw, key, [], following), [key])
        policy.confirm_key_posted(key)
        raw = following
        reasons = []
        for _ in range(8):
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            self.assertEqual(board.player.position.distance_to(entrance), 1)
            key = policy.choose_key(board)
            reasons.append((key, policy.last_reason))
            self.assertEqual(reasons[-1], (WAIT_KEY, "town:wait-recall"), reasons)
            following = self.later(raw)
            self.assertEqual(self.post(policy, raw, key, [], following), [key])
            policy.confirm_key_posted(key)
            raw = following


if __name__ == "__main__":
    unittest.main()
