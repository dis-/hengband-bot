"""Rank 21+ gear leaves without pressure on the Home (owner 2026-11-04).

Owner: rank 21+ may be sold any time; 10-04 「自宅の余り物を取り出して売る」.  The walk
is bounded per town stay and never runs with a recall on its way.

* home-room-n1b (n1-b Lv40, 21:47): Home 237/240, 51 rows of rank 21+.
* home-full-stop (n1-c life-130): rank 21+ in the pack goes to its buyer, not to
  Home and out again, and back to Home when the buyer is spent.

Recorded: tests/extract_home_full_gear_fixture.py, through the public chooser.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from hengbot import item_fate
from hengbot.model import STORE_ARMOURY
from tests.test_input_executor import ProductionHarness
from tests.test_spare_gear_recorded import Visit


class ItemFateRecordedTest(ProductionHarness):
    def visit(self, name, rows):
        visit = Visit(name, True)
        self.addCleanup(visit.close)
        board = None
        for recorded, supply in visit.rows[:rows]:
            board = supply()
            key = visit.policy.choose_key(board)
            self.assertEqual((key, visit.policy.last_reason), (recorded["key"], recorded["reason"]))
            visit.post(key)
        return visit, board

    def test_a_home_with_room_walks_back_to_take_a_ware_bounded_per_stay(self):
        visit, _board = self.visit("home-room-n1b", 9)
        policy = visit.policy
        recorded, supply = visit.rows[9]
        self.assertEqual(recorded["reason"], "shop:approach")
        board = supply()
        ware = item_fate.sweep_ware(policy, board, policy._home_knowledge_items)
        self.assertEqual(item_fate.gear_tier(policy, board, ware[1]), item_fate.ANY)
        # Never with a recall running.
        recalling = replace(board, player=replace(board.player, recalling=True))
        self.assertFalse(policy._begin_home_junk_sweep(recalling))
        # Never past the stay's bound.
        policy._home_junk_sweep_count = (policy._town_visit_epoch, item_fate.SWEEP_LIMIT_PER_STAY)
        self.assertFalse(policy._begin_home_junk_sweep(board))
        policy._home_junk_sweep_count = None
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assertTrue(policy._home_full_relief["sweep"])
        self.assertEqual(policy._home_junk_sweep_count, (policy._town_visit_epoch, 1))

    def test_rank_21_plus_in_the_pack_is_sold_and_the_top_ten_is_shelved(self):
        visit, board = self.visit("home-full-stop", 7)
        policy = visit.policy
        pick = lambda name: next(item for item in board.inventory if name in item.name)
        mail, shield = pick("ドワーフの鎖かたびら"), pick("耐火の金属製ラージ・シールド")
        self.assertTrue(item_fate.sold_not_shelved(policy, board, mail))
        self.assertFalse(policy._home_deposit_candidate(mail, board))
        self.assertTrue(policy._home_deposit_candidate(shield, board))
        self.assertFalse(item_fate.sold_not_shelved(policy, board, shield))
        # A spent buyer gives it back to Home: no loop, no held departure.
        policy._town_store_attempted[STORE_ARMOURY] = board.turn
        self.assertFalse(item_fate.sold_not_shelved(policy, board, mail))
        self.assertTrue(policy._home_deposit_candidate(mail, board))


if __name__ == "__main__":
    unittest.main()
