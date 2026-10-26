"""Issue #47 round 2: the recorded 329G pack funds an Outpost return.

Uses the round-1 extracted life-192 stop board (same original save), not a
live bot. Subsequent store pages, sale proceeds and arrival are explicitly
constructed protocol controls: no post-fix gameplay replay is claimed.
"""
import tests  # noqa: F401
import copy
import unittest

from hengbot.model import parse_snapshot
from hengbot.item_reservation import store_item_key
from hengbot.policy_constants import TOWN_TELEPORT_COST
from tests import test_broke_prevent_recorded as recorded
from tests.test_input_executor import ProductionHarness


class ReservedFareTest(ProductionHarness):
    setUpClass = classmethod(recorded.BrokePreventRecordedTest.setUpClass.__func__)
    raw = recorded.BrokePreventRecordedTest.raw
    policy = recorded.BrokePreventRecordedTest.policy
    decide = recorded.BrokePreventRecordedTest.decide
    follow = recorded.BrokePreventRecordedTest.follow

    def broke(self):
        return self.raw(2942109, gold=329)

    def shop(self, raw):
        raw = copy.deepcopy(raw)
        # Constructed arrival at this policy's current Telmora Alchemist.
        raw["player"].update(y=37, x=42)
        raw["store"] = {"store_type": 4, "items": [], "stock_num": 0,
                        "page_top": 0, "page_size": 52}
        return raw

    def test_recorded_reserved_sale_observed_price_minimum_and_outpost_follow(self):
        for enforced in (False, True):
            with self.subTest(claim_bar=enforced):
                raw = self.broke()
                p = self.policy(raw)
                p._town_claim_bar_enforced = enforced
                original = copy.deepcopy(raw["inventory"])
                key, reason, board = self.decide(p, raw)
                self.assertEqual(reason, "shop:outpost-fare-sale-approach")
                self.assertTrue(p._outpost_fare_recovering)
                self.follow(key, reason, raw)
                page = self.shop(raw)
                page["store"]["store_type"] = p._shopping_approach_store_type
                page["player"].update(y=p._shopping_approach_goal.y,
                                       x=p._shopping_approach_goal.x)
                key, reason, _ = self.decide(p, page)
                # Teleport: 15 - return floor 4 = 11; cure: 10 - 2 = 8.
                # First obtain an observed unit price, never sell all 15.
                self.assertEqual((key, reason), ("{d@1\r", "shop:batch-inscribe"))
                self.follow(key, reason, page, inside=True)
                page["inventory"][3]["inscription"] = "@1"
                key, reason, _ = self.decide(p, page)
                self.assertEqual((key, reason), ("d11\ry", "shop:one-shot-sale-compose"))
                self.assertEqual(self.follow(key, reason, page, inside=True), [key])
                # Constructed observed sale: first unit earns 60G. 171G was
                # missing, so two more at the same observed price suffice.
                page["inventory"][3]["count"] -= 1
                page["player"]["gold"] += 60
                key, reason, _ = self.decide(p, page)
                self.assertEqual((key, reason), ("\x1b", "shop:one-shot-sale-observed"))
                self.follow(key, reason, page, inside=True)
                outside = copy.deepcopy(page)
                outside.pop("store")
                key, reason, _ = self.decide(p, outside)
                self.assertEqual(reason, "shop:outpost-fare-sale-approach:await-entry")
                self.follow(key, reason, outside)
                key, reason, _ = self.decide(p, page)
                self.assertEqual((key, reason), ("d12\ry", "shop:one-shot-sale-compose"))
                self.follow(key, reason, page, inside=True)
                page["inventory"][3]["count"] -= 2
                page["player"]["gold"] += 120
                self.assertGreaterEqual(page["player"]["gold"], TOWN_TELEPORT_COST)
                self.assertLess(page["player"]["gold"] - 60, TOWN_TELEPORT_COST)
                key, reason, _ = self.decide(p, page)
                self.assertEqual(reason, "shop:one-shot-sale-observed")
                self.follow(key, reason, page, inside=True)
                outside = copy.deepcopy(page)
                outside.pop("store")
                outside["player"].update(y=27, x=55)
                key, reason, _ = self.decide(p, outside)
                self.assertEqual((key, reason), ("3ma", "town:cross-town-outpost-fare-return"))
                self.assertEqual(self.follow(key, reason, outside), [key])
                self.assertEqual(outside["inventory"][3]["count"], 12)
                self.assertEqual(outside["inventory"][:3], original[:3])
                self.assertEqual(outside["inventory"][4:], original[4:])
                outside["floor"].update(town_id=0, town_index=1)
                outside["player"]["gold"] -= TOWN_TELEPORT_COST
                self.decide(p, outside)
                self.assertFalse(p._outpost_fare_recovering)

    def test_ordinary_sales_cannot_borrow_the_fare_grant(self):
        raw = self.shop(self.broke())
        p = self.policy(raw)
        for enforced in (False, True):
            p._town_claim_bar_enforced = enforced
            board = parse_snapshot(raw, self.monrace)
            item = board.inventory[3]
            self.assertEqual(p._retention_surplus(board, item), 0)
            self.assertIsNone(store_item_key(p, board, "sell", item, "shop-sell", quantity=1))
        self.decide(p, raw)  # recovery's inscription selection
        raw["inventory"][3]["inscription"] = "@1"
        key, _, board = self.decide(p, raw)
        self.assertEqual(key, "d11\ry")
        self.assertEqual(p._retention_surplus(board, board.inventory[3]), 0)
        self.assertIsNone(store_item_key(p, board, "sell", board.inventory[3],
                                        "shop-sell", quantity=1))
        self.assertEqual(p._retention_reservation(board, board.inventory[3]), 15)

    def test_single_unit_covers_fare_without_a_second_sale(self):
        raw = self.shop(self.broke())
        raw["inventory"][3]["inscription"] = "@1"
        p = self.policy(raw)
        key, reason, _ = self.decide(p, raw)
        self.assertEqual(key, "d11\ry")
        self.follow(key, reason, raw, inside=True)
        raw["inventory"][3]["count"] -= 1
        raw["player"]["gold"] = TOWN_TELEPORT_COST
        self.assertEqual(self.decide(p, raw)[1], "shop:one-shot-sale-observed")
        self.assertEqual(self.decide(p, raw)[:2], ("\x1b", "shop:outpost-fare-earned-leave"))

    def test_observed_price_quantity_never_crosses_existing_return_floor(self):
        raw = self.shop(self.broke())
        # Constructed: only two Teleports above the existing floor of four;
        # cure already stands at its existing floor of two.
        raw["inventory"][3].update(count=6, inscription="@1")
        raw["inventory"][1]["count"] = 2
        p = self.policy(raw)
        self.assertEqual(self.decide(p, raw)[0], "d11\ry")
        raw["inventory"][3]["count"] -= 1
        raw["player"]["gold"] += 1
        self.decide(p, raw)
        self.assertEqual(self.decide(p, raw)[0], "d11\ry")
        raw["inventory"][3]["count"] -= 1
        raw["player"]["gold"] += 1
        self.decide(p, raw)
        raw.pop("store")
        self.assertEqual(self.decide(p, raw)[1], "town:blocked:outpost-fare-no-sale")
        self.assertEqual(raw["inventory"][3]["count"], 4)

    def test_reserved_refusal_is_not_retried_forever(self):
        raw = self.shop(self.broke())
        raw["inventory"][3]["inscription"] = "@1"
        p = self.policy(raw)
        self.assertEqual(self.decide(p, raw)[0], "d11\ry")
        self.assertEqual(self.decide(p, raw)[1], "shop:one-shot-sale-observed")
        raw.pop("store")
        # Cure may still be tried at the Temple, but the refusing Alchemist
        # cannot reinscribe/sell Teleport on each unchanged decision.
        p._store_sale_refused.update((3, 5))
        self.assertEqual(self.decide(p, raw)[1], "town:blocked:outpost-fare-no-sale")

    def test_plentiful_is_releasable_count_not_pack_order_or_raw_count(self):
        raw = self.shop(self.broke())
        # Teleport is now only one above its return floor; cure is eight
        # above its floor, so cure wins despite Teleport's usual priority.
        raw["inventory"][3]["count"] = 5
        p = self.policy(raw)
        self.assertEqual(self.decide(p, raw)[:2], ("{b@1\r", "shop:batch-inscribe"))

    def test_surplus_still_precedes_reserved_supplies(self):
        raw = recorded.BrokePreventRecordedTest._with_surplus_book(self)
        p = self.policy(raw)
        self.decide(p, raw)
        raw["store"] = {"store_type": 3, "items": [], "stock_num": 0,
                        "page_top": 0, "page_size": 52}
        self.assertEqual(self.decide(p, raw)[:2], ("{q@1\r", "shop:batch-inscribe"))


if __name__ == "__main__":
    unittest.main()
