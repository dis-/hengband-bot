"""A Home take merged into a carried stack is not a failed take (n1-c life-216, 2026-11-18 02:01).

Live (n1-c life-216, Magic-Eater Lv50, tests/extract_home_withdraw_merge_1118_fixture.py):
the Black Market offered 耐性の薬 and the Home-first gate sent the bot to the Home, which held
耐性の薬 {50%引き} x80.  The take ``5pp1`` (row 69) moved one into the pack, where it merged
into the carried 耐性の薬 {75%引き}: x13 became x14 under the carried name (row 70).  The game
merges them (C:/hengband/src system/item/item-entity.cpp: ``is_similar_part`` stacks unequal
discounts under ``stack_force_costs``, and ``absorb`` keeps the larger discount, so the
display keeps {75%引き}); a new pack slot never appeared (11 used before and after).

``_observe_home_atomic_withdrawal_outside`` confirmed the take by the pack's count of the
kind, but the town item processing looked the pending item up by its stored name, found no
耐性の薬 {50%引き} and deferred it as a failed take
(``town-item-processing-missing-pending``).  The gate retried it once, the same merge
deferred it again, and after the Black Market tour (owner 2026-11-17) took the bot to
Telmora, that town's Black Market offered 耐性の薬 again with the Home's stack deferred and
its one retry spent: ``town:blocked:home-withdraw-failed-stock-present``.

Now a pending item whose own take was confirmed is found by its kind in the pack, so the
take completes; an unconfirmed take is still deferred as before.

DECLARED CONSTRUCTED: the arrival policy is armed with the posted take of row 69 (pending
item, the Home stack of row 68, the pack's count of the kind on row 69, the posting turn)
instead of replaying rows 0-68, which diverge from the live visit at row 9 (the over-limit
loadout report is not in the checkpoint's sidecars).  The failed-take case is row 69's
board read one turn later (the pack unchanged).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "home-withdraw-merge-1118" / "n1c-216-0200"
STORED = ("耐性の薬 {50%引き}", 75, 60)
KIND = (75, 60)
HOME_ROW, TAKE_ROW, OUTSIDE_ROW = 68, 69, 70


class HomeWithdrawMerge1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.arrival, cls.recorded, steps = load(FIXTURE, Path(scratch.name))
        cls.home = steps[HOME_ROW][1]()
        cls.take = steps[TAKE_ROW][1]()
        cls.outside = steps[OUTSIDE_ROW][1]()

    def armed(self):
        """The arrival policy with row 69's take posted."""
        policy = copy.deepcopy(self.arrival)
        stored = next(item for item in self.home.store.items
                      if policy._item_signature(item) == STORED)
        policy._home_pending_item = STORED
        policy._home_pending_quantity = 1
        policy._home_pending_quantities[STORED] = 1
        policy._home_atomic_withdraw_pending = (
            STORED, policy._home_take_count(self.take, KIND), stored, 1)
        policy._home_atomic_withdraw_move_identity = KIND
        policy._home_atomic_withdraw_posted_turn = self.take.turn
        return policy

    def carried(self, board):
        return [(item.name, item.count) for item in board.inventory
                if (item.tval, item.sval) == KIND]

    def test_the_recorded_take_merged_into_the_carried_stack(self):
        self.assertEqual(self.recorded[TAKE_ROW]["reason"], "home:atomic-withdraw")
        self.assertEqual(self.recorded[TAKE_ROW]["key"], "5pp1\r\x1b")
        self.assertEqual(self.carried(self.take), [("耐性の薬 {75%引き}", 13)])
        self.assertEqual(self.carried(self.outside), [("耐性の薬 {75%引き}", 14)])
        self.assertEqual(len(self.take.inventory), len(self.outside.inventory))

    def test_a_confirmed_merged_take_completes(self):
        policy = self.armed()
        policy.choose_key(self.outside)
        # Live: the take was deferred as failed (town-item-processing-missing-pending).
        self.assertNotIn(STORED, policy._deferred_home_items)
        self.assertIsNone(policy._home_pending_item)
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertNotEqual(policy.last_reason, "home:withdraw-failed-deferred")

    def test_the_item_processing_finds_the_merged_stack(self):
        policy = self.armed()
        policy._observe_home_atomic_withdrawal_outside(self.outside)
        self.assertEqual(policy._home_pending_take_confirmed, STORED)
        found = policy._pending_inventory_item(self.outside)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "耐性の薬 {75%引き}")
        policy._town_item_processing_key(self.outside)
        self.assertEqual(policy.last_reason, "identify:complete")
        self.assertNotIn(STORED, policy._deferred_home_items)

    def test_an_unconfirmed_take_is_still_deferred(self):
        policy = self.armed()
        unchanged = replace(self.take, turn=self.outside.turn)
        policy._observe_home_atomic_withdrawal_outside(unchanged)
        self.assertIsNone(policy._home_pending_take_confirmed)
        self.assertIsNone(policy._pending_inventory_item(unchanged))
        policy._town_item_processing_key(unchanged)
        self.assertIn(STORED, policy._deferred_home_items)


if __name__ == "__main__":
    unittest.main()
