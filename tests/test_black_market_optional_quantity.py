"""Optional Black Market buys preserve full departure resupply costs.

User decision 2026-10-08: "always keep in hand the total price of re-buying
every departure necessity ... regardless of whether it is currently
satisfied." This replaces the 2026-09-15 unmet-shortage reserve.

CONSTRUCTED boards (declared): a town board at a depth that needs a 20-charge
Identify staff, a Magic-shop page that teaches the staff price (917g for 19
charges, the recorded 09-15 price), then a Black Market page with a 3-potion
Speed stack at 400g. Under the old shortage-only rule the reserve was 917g
with 1 Identify charge and 0g with 20; the new rule prices the full targets.
The emitted key is read at the public door-composed boundary.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest
from dataclasses import replace

from policy_fixtures import _public_shop_inner, grid, item, player, store_item
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import FOOD_TYPE_MANA
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
    LIVE_SPEED_PRICE = 1299

    def _town(self, *, staff_charges, store, gold, food_type=None):
        board_player = player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR)
        if food_type is not None:
            board_player = replace(board_player, food_type=food_type)
        return Snapshot(
            board_player,
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
        for category, price, units in (
            ("recall", 100, 1),
            ("teleport", 50, 1),
            ("cure-critical", 200, 1),
            ("food", 80, 1),
            ("oil", 20, 1),
            ("light", 400, 1),
        ):
            policy._remember_departure_price(category, price, units)
        black_market = self._town(
            staff_charges=staff_charges,
            store=StoreState(STORE_BLACK, [store_item(
                "n", TVAL_POTION, SV_POTION_SPEED,
                price=self.SPEED_PRICE, count=3,
            )]),
            gold=gold,
        )
        return policy, black_market

    def test_multi_unit_optional_buy_preserves_full_resupply_reserve(self):
        # The prior shortage-only reserve was 917g. Full departure targets cost
        # 6,484g, so this board cannot make even a one-potion optional purchase.
        policy, board = self._black_market(staff_charges=1, gold=1400)
        self.assertEqual(policy._required_departure_supply_reserve(board), 6484)
        self.assertEqual(1400 // self.SPEED_PRICE, 3)

        self.assertFalse(_public_shop_inner(self, policy, board).startswith("p"))

    def test_satisfied_stock_still_reserves_its_full_rebuy_cost(self):
        policy, board = self._black_market(staff_charges=20, gold=1400)
        reserve = policy._required_departure_supply_reserve(board)
        self.assertGreater(reserve, 0)

        self.assertIsNone(policy._next_purchase(board))
        self.assertFalse(_public_shop_inner(self, policy, board).startswith("p"))

    def test_reserve_not_kept_by_one_unit_buys_nothing(self):
        # 1300 - 400 = 900 < 917.
        policy, board = self._black_market(staff_charges=1, gold=1300)
        self.assertEqual(policy._required_departure_supply_reserve(board), 6484)

        self.assertIsNone(policy._next_purchase(board))
        self.assertFalse(
            _public_shop_inner(self, policy, board).startswith("p")
        )

    def test_recorded_20261008_speed_board_is_blocked_and_affordable_control_passes(self):
        # Decision sequence 33 at 09:10:38: 3,956g, Black Market slot w,
        # Speed potions at 1,299g each (the emitted pw3\r\r spent 3,897g).
        policy, board = self._black_market(staff_charges=36, gold=3956)
        board = replace(
            board,
            player=replace(board.player, food_type=FOOD_TYPE_MANA),
            store=StoreState(STORE_BLACK, [store_item(
                "w", TVAL_POTION, SV_POTION_SPEED,
                price=self.LIVE_SPEED_PRICE, count=3,
            )]),
        )
        # The Magic-shop observation supplies the known mana-device price.
        policy._remember_departure_price("food", self.STAFF_PRICE, 19)
        reserve = policy._required_departure_supply_reserve(board)
        self.assertIsNotNone(reserve)
        self.assertGreaterEqual(board.player.gold, 3 * self.LIVE_SPEED_PRICE)
        self.assertLess(board.player.gold, reserve + self.LIVE_SPEED_PRICE)
        self.assertIsNone(policy._next_purchase(board))

        control = replace(
            board,
            player=replace(
                board.player,
                gold=reserve + self.LIVE_SPEED_PRICE + 1,
            ),
        )
        self.assertIsNotNone(policy._next_purchase(control))


if __name__ == "__main__":
    unittest.main()
