"""Optional Black Market buys never spend the required-supply reserve.

User decision 2026-09-15 (black-market-optional-reserve-decision): optional
Black Market purchases happen only when the gold left AFTER the purchase still
covers the outstanding required departure supplies at known prices; required
first.  User 2026-10-02: 「これは改善する必要がある」 -- the reserve was checked
against ONE unit while ``_purchase_quantity`` bought the whole shelf stack.

CONSTRUCTED boards (declared): a town board at a depth that needs a 20-charge
Identify staff, a Magic-shop page that teaches the staff price (917g for 19
charges, the recorded 09-15 price), then a Black Market page with a 3-potion
Speed stack at 400g.  With the 1-charge staff carried the reserve is 917g; with
a 20-charge staff it is 0.  The emitted key is read at the public
door-composed boundary.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest
from dataclasses import replace

from policy_fixtures import _public_shop_inner, grid, item, player, store_item
from hengbot.policy import HengbotPolicy
from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    STORE_BLACK,
    STORE_MAGIC,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_HEALING,
    SV_POTION_SPEED,
    SV_SCROLL_TELEPORT,
    SV_SCROLL_WORD_OF_RECALL,
    SV_STAFF_IDENTIFY,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_SCROLL,
    TVAL_STAFF,
    Position,
    Snapshot,
    StoreState,
)


class BlackMarketOptionalQuantityReserveTest(unittest.TestCase):
    STAFF_PRICE = 917
    SPEED_PRICE = 400

    def _town(self, *, staff_charges, store, gold):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=11),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
                item("i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=staff_charges),
                item("s", TVAL_POTION, SV_POTION_SPEED, count=5),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=5),
            ],
            equipment=[
                item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)
            ],
            store=store,
        )

    def _black_market(self, *, staff_charges, gold):
        """Return the policy that has seen the staff price, and the BM page."""
        policy = HengbotPolicy()
        policy.choose_key(replace(
            self._town(staff_charges=staff_charges, store=None, gold=gold),
            floor_key=(1, 18, 0),
            town_flag=False,
        ))
        policy.choose_key(self._town(
            staff_charges=staff_charges,
            store=StoreState(STORE_MAGIC, [store_item(
                "a", TVAL_STAFF, SV_STAFF_IDENTIFY,
                price=self.STAFF_PRICE, charges=19, pval=19,
            )]),
            gold=500,
        ))
        black_market = self._town(
            staff_charges=staff_charges,
            store=StoreState(STORE_BLACK, [store_item(
                "n", TVAL_POTION, SV_POTION_SPEED,
                price=self.SPEED_PRICE, count=3,
            )]),
            gold=gold,
        )
        return policy, black_market

    def test_multi_unit_optional_buy_stops_at_the_reserve(self):
        # 1400g affords all 3 (3 * 400), but only 1 leaves the 917g reserve.
        policy, board = self._black_market(staff_charges=1, gold=1400)
        self.assertEqual(policy._required_departure_supply_reserve(board), 917)
        self.assertEqual(1400 // self.SPEED_PRICE, 3)

        self.assertEqual(_public_shop_inner(self, policy, board), "pn1\r\r")

    def test_zero_reserve_still_empties_the_bounded_stack(self):
        policy, board = self._black_market(staff_charges=20, gold=1400)
        self.assertEqual(policy._required_departure_supply_reserve(board), 0)

        self.assertEqual(_public_shop_inner(self, policy, board), "pn3\r\r")

    def test_reserve_not_kept_by_one_unit_buys_nothing(self):
        # 1300 - 400 = 900 < 917.
        policy, board = self._black_market(staff_charges=1, gold=1300)
        self.assertEqual(policy._required_departure_supply_reserve(board), 917)

        self.assertIsNone(policy._next_purchase(board))
        self.assertFalse(
            _public_shop_inner(self, policy, board).startswith("p")
        )


if __name__ == "__main__":
    unittest.main()
