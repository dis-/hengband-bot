"""A full Home's spare gear is sold when the pack is over the weight limit.

Owner 2026-10-04: 自宅が満杯なら余り物を売って空ける.  n1-c life-130 (Magic-Eater
Lv42, 2026-11-04 20:40:46): weight 2028 over 1650, Home 240/240, five pieces of
spare gear in the pack.  The only gear test the relief asked, the dominance
prune, answers for Warriors alone, so 20 of weight (five potions) was legal
against 378 of excess and the visit stopped as
town:blocked:overweight-home-full-no-legal-relief; three stops retired her.

Recorded: the arrival checkpoint and the visit's journal
(tests/extract_home_full_gear_fixture.py), decided through the public chooser.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import StoreState
from hengbot import spare_gear
from tests.test_input_executor import (
    FaithfulHookGame, ProductionHarness, store_screen,
)
from tests.test_spare_gear_recorded import Visit

STOP_ROW = 9
STOP = "town:blocked:overweight-home-full-no-legal-relief"
# Cheapest first, gear ahead of the potions; the sword clears the last 32.
SOLD_ORDER = ("耐火の金属製ラージ・シールド", "ドワーフの鎖かたびら", "オログの防護服", "溶解のロング・ソード")


class HomeFullGearRecordedTest(ProductionHarness):
    def stop_board(self):
        visit = Visit("home-full-stop", True)
        self.addCleanup(visit.close)
        policy = visit.policy
        for recorded, supply in visit.rows[:STOP_ROW]:
            key = policy.choose_key(supply())
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            visit.post(key)
        recorded, supply = visit.rows[STOP_ROW]
        self.assertEqual(recorded["reason"], STOP)
        return visit, supply()

    @staticmethod
    def sold_board(policy, board, identity):
        """DECLARED CONSTRUCTED: the shop's reply to the producer's own sale."""
        return replace(board, player=replace(board.player, gold=board.player.gold + 1000),
                       inventory=tuple(item for item in board.inventory
                                       if policy._sale_item_identity(item) != identity))

    @staticmethod
    def buyer_page(policy, board, identity):
        """DECLARED CONSTRUCTED: the entered buyer's page, with no stock."""
        buyer = next(entry[4][0] for entry in policy._overweight_surplus_candidates(board)
                     if policy._sale_item_identity(entry[2]) == identity)
        return replace(board, turn=board.turn + 1, store=StoreState(
            store_type=buyer, stock_num=0, capacity=24, page_top=0, page_size=12, items=()))

    def test_the_stop_board_walks_to_sell_the_cheapest_spare_gear(self):
        visit, board = self.stop_board()
        policy = visit.policy
        key = policy.choose_key(board)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual((key, policy.last_reason), ('\x1b`n".', "shop:travel"))
        relief = policy._weight_relief_selection(board)
        self.assertEqual((relief.weight, relief.limit, relief.route),
                         (2028, 1650, "sell-or-destroy"))
        self.assertTrue(policy._overweight_surplus_disposal["pending"]["identity"][0]
                        .startswith(SOLD_ORDER[0]))

        # Through the production executor: the sale's first key at the Armoury.
        visit.post(key)
        identity = policy._overweight_surplus_disposal["pending"]["identity"]
        inside = self.buyer_page(policy, board, identity)
        key = policy.choose_key(inside)
        self.assertTrue(key.startswith("{"), key)
        # DECLARED CONSTRUCTED: the game's replies (the Armoury page, twice).
        game = FaithfulHookGame()
        state = dict(self.store_state(inside.turn), store={
            "store_type": inside.store.store_type, "items": []})
        game.screens = [store_screen(), store_screen()]
        game.states = [state, dict(state, turn=inside.turn + 1)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        posted = set()
        sent, _line = _send_new_decision_key(
            port, "armoury-entrance", "5", None, posted, in_store=False,
            decision={"sequence": 1, "reason": "shop:travel"},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent)
        sent, _line = _send_new_decision_key(
            port, "armoury", key, None, posted, in_store=True,
            decision={"sequence": 2, "reason": policy.last_reason},
            snapshot=inside, posting_contract=PostingContract())
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["5", key])

    def test_the_visit_sells_gear_until_under_the_limit_and_keeps_the_potions(self):
        visit, board = self.stop_board()
        policy = visit.policy
        sold = []
        potions = sum(item.is_potion for item in board.inventory)
        for _ in range(60):
            if sold and not policy._inventory_overweight(board):
                break
            key = policy.choose_key(board)
            self.assertNotIn("blocked", policy.last_reason)
            disposal = policy._overweight_surplus_disposal
            pending = disposal.get("pending") if disposal else None
            visit.post(key)
            if key.startswith("{"):
                # DECLARED CONSTRUCTED: the inscription the sale asked for.
                tag = policy._batch_sell_pending["entries"][0]["tag"]
                board = replace(board, inventory=tuple(
                    replace(item, name=f"{policy._sale_item_identity(item)[0]} {{@{tag}}}",
                            inscription=f"@{tag}")
                    if policy._sale_item_identity(item) == pending["identity"] else item
                    for item in board.inventory))
            elif board.store is None and pending is not None:
                board = self.buyer_page(policy, board, pending["identity"])
            elif pending is not None and pending.get("posted"):
                sold.append(pending["identity"][0])
                board = self.sold_board(policy, board, pending["identity"])
            elif key == "\x1b":
                board = replace(board, store=None, turn=board.turn + 1)
        else:
            self.fail(f"no end: {sold}, {policy.last_reason}")
        self.assertEqual(len(sold), len(SOLD_ORDER), sold)
        for name, expected in zip(sold, SOLD_ORDER):
            self.assertTrue(name.startswith(expected), name)
        self.assertLessEqual(policy._inventory_weight(board), 1650)
        self.assertEqual(sum(item.is_potion for item in board.inventory), potions)

    def test_gear_that_cannot_clear_the_excess_keeps_the_cheapest_order(self):
        visit, board = self.stop_board()
        policy = visit.policy
        policy.choose_key(board)
        rows = policy._overweight_surplus_candidates(board)
        self.assertTrue(rows[0][1][0].startswith(SOLD_ORDER[0]))
        cheapest = sorted(rows, key=lambda entry: entry[0])
        self.assertTrue(cheapest[0][2].is_potion)
        # DECLARED CONSTRUCTED: bolts heavy enough that the gear cannot clear it.
        heavy = replace(board, inventory=tuple(
            replace(item, weight=2000) if item.is_ammo else item for item in board.inventory))
        self.assertEqual(spare_gear.gear_first_when_it_covers(policy, heavy, cheapest), cheapest)

    def test_a_home_with_room_or_an_artifact_is_never_sold_as_spare(self):
        visit, board = self.stop_board()
        policy = visit.policy
        sword = next(item for item in board.inventory if "溶解のロング" in item.name)
        self.assertTrue(spare_gear.sold_for_weight(policy, board, sword))
        self.assertFalse(spare_gear.sold_for_weight(policy, board, replace(sword, is_artifact=True)))
        # DECLARED CONSTRUCTED: the capacity fact of a Home with a free slot.
        policy._home_capacity_observation = (239, 240, policy._effective_town_id(board))
        self.assertFalse(spare_gear.sold_for_weight(policy, board, sword))


if __name__ == "__main__":
    unittest.main()
