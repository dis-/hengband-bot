"""destruction3-1104: 50F+ only with a means destruction_use can use.

Owner 2026-11-04 (after 69 live uses): 「使える手段がある時だけ解く」.

Recorded board: the stop of tests/fixtures/unsafe-recall-fallback-20260923.jsonl.gz,
the warrior refused Angband 50 for ``missing-destruction`` alone, decided through
the public town key as test_unsafe_recall_fallback_recorded does.

DECLARED CONSTRUCTED: class 16 and the displayed absorbed list (rate and charges) on
that board; the scrolls of the warrior variant (the module's stocked stack); the
floor of the mid-dive variants (51F, the means held and then spent).
"""
import tests  # noqa: F401 -- isolate live runtime files

from dataclasses import replace
import unittest

from hengbot import destruction_use
from hengbot.me_device_attacks import observe_lists
from hengbot.policy_constants import DESTRUCTION_GATE_LABEL
from tests.test_destruction_gate_procurement import _RecordedDestructionBoard
from tests.test_unsafe_recall_fallback_recorded import (
    ANGBAND_ARRIVAL_DEPTH, DUNGEON_ANGBAND, FALLBACK_REASON,
)

NAME = "*破壊*"
CLASS_MAGIC_EATER = 16


def listed(fail, current=6):
    return {"kind": "staff", "rows": [{"name": NAME, "current": current, "max": 9,
                                       "fail": fail, "success": 100 - fail}]}


class DivePermissionTest(_RecordedDestructionBoard, unittest.TestCase):
    def magic_eater(self, fail, current=6):
        """The recorded policy and board as a Magic-Eater who saw the list."""
        board = replace(self.board, player=replace(self.board.player,
                                                   class_id=CLASS_MAGIC_EATER))
        policy = self._independent()
        observe_lists(policy, replace(board, magic_eater_power_list=listed(fail, current)))
        return policy, board

    def assert_refused(self, policy, board):
        self.assertIn(DESTRUCTION_GATE_LABEL,
                      policy._missing_required_abilities(board, ANGBAND_ARRIVAL_DEPTH))
        self.assertFalse(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        self.assertEqual(policy._intended_dive_depth(board), ANGBAND_ARRIVAL_DEPTH - 1)

    def test_magic_eater_with_the_power_may_take_50f(self):
        policy, board = self.magic_eater(20)
        self.assertEqual(policy._missing_required_abilities(board, ANGBAND_ARRIVAL_DEPTH),
                         frozenset())
        self.assertTrue(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        self.assertEqual(policy._intended_dive_depth(board), ANGBAND_ARRIVAL_DEPTH)
        self.assertIsNone(policy._town_special_key(board))
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)

    def test_magic_eater_below_eighty_percent_may_not(self):
        policy, board = self.magic_eater(21)
        self.assert_refused(policy, board)
        policy._town_special_key(board)
        self.assertEqual(policy.last_reason, FALLBACK_REASON)

    def test_magic_eater_with_no_charge_may_not(self):
        self.assert_refused(*self.magic_eater(20, current=0))

    def test_warrior_with_scrolls_may_not(self):
        policy = self._independent()
        stocked = self._fully_stocked(self.board)
        self.assertEqual(policy._total_destruction_uses(stocked), 20)
        self.assertFalse(destruction_use.holds_means(policy, stocked))
        self.assert_refused(policy, stocked)

    def test_telepathy_still_applies(self):
        policy, board = self.magic_eater(20)
        blind = replace(board, player=replace(
            board.player, abilities=board.player.abilities - {"telepathy"}))
        self.assertEqual(policy._missing_required_abilities(blind, ANGBAND_ARRIVAL_DEPTH),
                         frozenset({"telepathy"}))

    def deep(self, board, level=51):
        return replace(board, floor_key=(DUNGEON_ANGBAND, level, 0), town_flag=False)

    def test_means_spent_on_51f_refuses_the_descent_but_is_no_gap(self):
        policy, board = self.magic_eater(20)
        floor = self.deep(board)
        destruction_use.observe(policy, floor)
        observe_lists(policy, replace(floor, magic_eater_power_list=listed(20, current=0)))
        self.assertFalse(destruction_use.holds_means(policy, floor))
        self.assertIn(DESTRUCTION_GATE_LABEL, policy._missing_required_abilities(floor, 52))
        missing = policy._missing_required_abilities(floor, 51)
        self.assertIn(DESTRUCTION_GATE_LABEL, missing)
        self.assertEqual(destruction_use.gap_here(policy, floor, missing), frozenset())
        policy._should_start_town_return(floor)
        self.assertNotEqual(policy._last_return_trigger, "resist-gap")

    def test_a_floor_reached_without_the_means_stays_a_gap(self):
        # A warrior's trapdoor from 49F: the existing resist-gap return answers it.
        policy = self._independent()
        floor = self.deep(self.board, level=50)
        destruction_use.observe(policy, floor)
        missing = policy._missing_required_abilities(floor, 50)
        self.assertIn(DESTRUCTION_GATE_LABEL, destruction_use.gap_here(policy, floor, missing))
        self.assertTrue(policy._should_start_town_return(floor))
        self.assertEqual(policy._last_return_trigger, "resist-gap")


if __name__ == "__main__":
    unittest.main()
