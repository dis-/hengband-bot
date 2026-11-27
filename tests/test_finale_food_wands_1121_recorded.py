"""The preparation phase's food step: three Wands of Wonder under three inscriptions (n1-b).

Owner 2026-11-21 (verbatim, LOCKED) 「99F 100Fでは謎の魔法棒を銘を分けて3本持って食料とする」, with
「謎の魔法棒=本物の食料」「種族ゾンビは魔法棒のチャージを食べて空腹を満たす」.  n1-b life-411 (a Zombie
Magic-Eater) carried its food as one stack of six Wands of Wonder {@3} (111 charges); on Angband
100F a monster's UN_POWER blow drained the whole stack to 0 (capture n1b-411-20261121-100f-hunger).
The food step splits it into separate stacks: a stack is inscribed, one wand dropped on the town
floor (it keeps its inscription), the pack's stack inscribed anew, the dropped one picked up (two
stacks merge when one is uninscribed: stack_force_notes, system/item/item-entity.cpp:1146-1150).

Recorded: n1-b's town board of 2026-11-21 15:31:51 (tests/fixtures/n1b-hunger-100f-1121, journal
row 0): the stack of six {@3}, 111 charges, nothing on the floor.

DECLARED CONSTRUCTED: the phase at its food step; the boards after each posted key (the drop: five
in the pack and a wand on the floor; the new inscription; the pick-up: two stacks), as the game
answers them (a split stack shares its charges).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import finale_prep
from hengbot.model import TVAL_WAND
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-hunger-100f-1121"


class FinaleFoodWandsRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        self.board = steps[0][1]()
        self.held = finale_prep.phase(self.policy)
        self.held.in_town, self.held.step = True, finale_prep.FOOD  # DECLARED
        self.held.since = self.policy._decision_sequence
        self.wand = next(item for item in self.board.inventory if item.tval == TVAL_WAND)
        self.assertEqual((self.wand.count, self.wand.charges, self.wand.inscription), (6, 111, "@3"))

    def tearDown(self):
        self.scratch.cleanup()

    def board_with(self, stacks, floor=False):
        """DECLARED: the pack's Wonder stacks [(slot, count, charges, inscription)] and the
        player's floor cell holding a wand or not."""
        others = [item for item in self.board.inventory if item.tval != TVAL_WAND]
        wands = [replace(self.wand, slot=slot, count=count, charges=charges, inscription=label)
                 for slot, count, charges, label in stacks]
        board = replace(self.board, inventory=tuple(others + wands))
        here = board.grid_at(board.player.position)
        cell = replace(here, object_tvals=(TVAL_WAND,) if floor else (), object_count=int(floor))
        return replace(board, grids={**board.grids, here.position: cell})

    def key(self, board):
        return finale_prep.town_key(self.policy, board), self.policy.last_reason

    def test_three_stacks_by_drop_inscribe_and_pick_up(self):
        reason = finale_prep.FOOD_REASON
        board = self.board_with([("m", 6, 111, "@3")])
        self.assertEqual(self.key(board), ("dm1\r", f"{reason}:drop"))
        self.assertEqual(self.held.food_dropped, "@3")
        board = self.board_with([("m", 5, 93, "@3")], floor=True)
        self.assertEqual(self.key(board), ("{m@E1\r", f"{reason}:inscribe"))
        board = self.board_with([("m", 5, 93, "@E1")], floor=True)
        self.assertEqual(self.key(board), ("g", f"{reason}:pickup"))
        board = self.board_with([("m", 5, 93, "@E1"), ("n", 1, 18, "@3")])
        self.assertIsNone(finale_prep.town_key(self.policy, board))  # the pick-up seen
        self.assertIsNone(self.held.food_dropped)
        self.assertEqual(self.key(board), ("dm1\r", f"{reason}:drop"))  # the second split
        board = self.board_with([("m", 4, 75, "@E1"), ("n", 1, 18, "@3")], floor=True)
        self.assertEqual(self.key(board), ("{m@E2\r", f"{reason}:inscribe"))
        board = self.board_with([("m", 4, 75, "@E2"), ("n", 1, 18, "@3")], floor=True)
        self.assertEqual(self.key(board), ("g", f"{reason}:pickup"))
        done = self.board_with([("m", 4, 75, "@E2"), ("n", 1, 18, "@3"), ("o", 1, 18, "@E1")])
        self.assertIsNone(finale_prep.town_key(self.policy, done))
        self.assertTrue(finale_prep.food_done(done))
        finale_prep.observe(self.policy, done, {"owned": {}, "carried": {}})
        self.assertEqual(self.held.step, finale_prep.LOADOUT)

    def test_an_uninscribed_stack_is_inscribed_before_any_drop(self):
        board = self.board_with([("m", 6, 111, "")])
        self.assertEqual(self.key(board), ("{m@E1\r", f"{finale_prep.FOOD_REASON}:inscribe"))

    def test_a_drained_stack_is_split_and_waits_for_the_charges_without_a_stop(self):
        # MAINTAINABILITY.md 2 (n1-b life-419 2026-11-28, tests/test_n1b_419_finale_food_1128_recorded.py):
        # a drained stack is split as a charged one; three drained stacks wait for the ordinary
        # town supply's refill (staple_needs_recharge) under the step's own limit, never a stop.
        board = self.board_with([("m", 6, 0, "@3")])
        self.assertEqual(self.key(board), ("dm1\r", f"{finale_prep.FOOD_REASON}:drop"))
        drained = self.board_with([("m", 4, 0, "@E2"), ("n", 1, 0, "@3"), ("o", 1, 0, "@E1")])
        self.assertFalse(finale_prep.food_done(drained))
        self.assertIsNone(finale_prep.town_key(self.policy, drained))
        self.assertEqual(self.held.step, finale_prep.FOOD)
        self.assertIsNone(self.held.stopped)


if __name__ == "__main__":
    unittest.main()
