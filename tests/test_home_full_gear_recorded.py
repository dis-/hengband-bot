"""The full Home's relief under the owner's gear ranking (2026-11-04).

Owner: per slot, by sale value, rank 21+ may be sold any time, ranks 11-20 when
room is needed, the top 10 are kept, artifacts are not sold.  Owner 10-04: a full
Home takes its surplus out and sells it, then deposits.

* home-full-stop (n1-c life-130, 20:40): weight 2028 over 1650, Home 240/240, no
  Home row legal to sell for a Magic-Eater: the dominance prune answers for
  Warriors alone.  Three stops retired her.
* home-full-2146 (life-134, 21:46): 1871 over 1350 (STR drained), 19 of 23 slots.
  The pack at the reserve floor refuses the take, so selling the Home's rows
  alone would not have helped; the pack must shrink first.
* home-full-2142 (life-134, 21:42): the Armoury's page sale took the pending
  ware and the producer stopped with the sword left to clear the last 32.

Recorded: the arrival checkpoints and journals
(tests/extract_home_full_gear_fixture.py), through the public chooser.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from hengbot import item_fate
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_ALCHEMIST, StoreState
from tests.test_input_executor import FaithfulHookGame, ProductionHarness, store_screen
from tests.test_spare_gear_recorded import Visit

STOP = "town:blocked:overweight-home-full-no-legal-relief"


class HomeFullGearRecordedTest(ProductionHarness):
    def visit(self, name):
        visit = Visit(name, True)
        self.addCleanup(visit.close)
        return visit

    def replay(self, visit, rows):
        """Decide the recorded rows, which must match; return the last board."""
        board = None
        for recorded, supply in visit.rows[:rows]:
            board = supply()
            key = visit.policy.choose_key(board)
            self.assertEqual((key, visit.policy.last_reason), (recorded["key"], recorded["reason"]))
            visit.post(key)
        return board

    def test_ranks_on_the_real_home(self):
        visit = self.visit("home-full-stop")
        policy = visit.policy
        board = self.replay(visit, 7)
        tier = lambda name: item_fate.gear_tier(policy, board, next(
            item for item in (*board.inventory, *policy._home_knowledge_items) if name in item.name))
        # Seven shields: the pack's is in the top 10 and is not sold.
        self.assertEqual(tier("耐火の金属製ラージ・シールド"), item_fate.KEEP)
        self.assertEqual(tier("ドワーフの鎖かたびら (-2) [19,+8]"), item_fate.ANY)
        self.assertEqual(tier("溶解のロング・ソード (2d5) (+10,+9)"), item_fate.ANY)
        for name in ("ドラゴン・グローブ [4,+4]", "ブラックドラゴン・スケイルメイル (-2) [40,+5]",
                     "ドラゴン・シールド [8,+1]", "★知識の石", "★ダサイ皮よろい"):
            self.assertEqual(tier(name), item_fate.KEEP, name)

    def test_the_stop_board_takes_the_cheapest_rank_21_plus_ware(self):
        visit = self.visit("home-full-stop")
        policy = visit.policy
        self.replay(visit, 7)
        recorded, supply = visit.rows[7]
        self.assertEqual(recorded["reason"], "home:full-leave-with-surplus")
        inside = supply()
        key = policy.choose_key(inside)
        self.assertEqual((key, policy.last_reason), ("\x1b", "home:full-queue-surplus-withdraw"))
        relief = policy._home_full_relief
        self.assertEqual(relief["mode"], "sale")
        ware = next(item for item in policy._home_knowledge_items
                    if policy._item_signature(item) == relief["sale"][0])
        self.assertEqual(item_fate.gear_tier(policy, inside, ware), item_fate.ANY)
        rest = [item_fate.sale_value(policy, item) for item in policy._home_knowledge_items
                if item_fate.gear_tier(policy, inside, item) == item_fate.ANY
                and policy._home_full_sale_candidate(inside, item)]
        self.assertLessEqual(item_fate.sale_value(policy, ware), min(rest))

    def test_a_pack_at_the_reserve_floor_sells_first_through_the_executor(self):
        visit = self.visit("home-full-2146")
        policy = visit.policy
        self.replay(visit, 6)
        recorded, supply = visit.rows[6]
        inside = supply()
        self.assertTrue(item_fate.home_take_blocked(inside))
        self.assertEqual(recorded["key"], "\x1b")
        key = policy.choose_key(inside)
        self.assertEqual((key, policy.last_reason), ("\x1b", "home:full-leave-with-surplus"))
        relief = policy._home_full_relief
        self.assertTrue(relief.get("pack_only"))
        self.assertEqual(relief["mode"], "sale")
        visit.post(key)
        recorded, supply = visit.rows[7]
        self.assertEqual(recorded["reason"], "home:full-destroy-surplus")
        outside = supply()
        key = policy.choose_key(outside)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(policy.last_reason, "shop:travel")

        # DECLARED CONSTRUCTED: the game's replies (the Alchemist's page, twice);
        # the sale's first key goes through the production executor.
        visit.post(key)
        buyer = replace(outside, turn=outside.turn + 1, store=StoreState(
            store_type=STORE_ALCHEMIST, stock_num=0, capacity=24, page_top=0, page_size=12, items=[]))
        key = policy.choose_key(buyer)
        self.assertTrue(key.startswith(("{", "d")), (key, policy.last_reason))
        game = FaithfulHookGame()
        state = dict(self.store_state(buyer.turn), store={"store_type": STORE_ALCHEMIST, "items": []})
        game.screens = [store_screen(), store_screen()]
        game.states = [state, dict(state, turn=buyer.turn + 1)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        posted = set()
        sent, _line = _send_new_decision_key(
            port, "entrance", "5", None, posted, in_store=False,
            decision={"sequence": 1, "reason": "shop:travel"},
            snapshot=outside, posting_contract=PostingContract())
        self.assertTrue(sent)
        sent, _line = _send_new_decision_key(
            port, "alchemist", key, None, posted, in_store=True,
            decision={"sequence": 2, "reason": policy.last_reason},
            snapshot=buyer, posting_contract=PostingContract())
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["5", key])

    def test_a_ware_the_page_sale_took_is_no_stop(self):
        visit = self.visit("home-full-2142")
        policy = visit.policy
        self.replay(visit, 7)
        board = None
        recorded = None
        for recorded, supply in visit.rows[7:]:
            board = supply()
        self.assertEqual(recorded["reason"], STOP)
        self.assertEqual(policy._inventory_weight(board), 1682)
        # DECLARED CONSTRUCTED: the live producer's state at this board (recorded
        # in the capture's policy state): the shield, already sold, still pending.
        shield = ("耐火の金属製ラージ・シールド [8,+11]", 34, 5)
        policy._home_full_relief = None
        policy._home_errand.finish()
        policy._overweight_surplus_disposal = {"town": 0, "pending": dict(
            signature=(shield[0] + " {r火}", 34, 5), identity=shield, before_count=1, count=1,
            mode="sale", posted=False, town=0, gold=150409, weight=2028, home_stock=240)}
        policy._home_capacity_observation = (240, 240, 0)
        policy._build_grid_index(board)
        policy._overweight_surplus_sale_key(board)
        self.assertIn("溶解のロング・ソード",
                      policy._overweight_surplus_disposal["pending"]["identity"][0])


if __name__ == "__main__":
    unittest.main()
