"""Constructed O6 boards: all classes share the pre-kit town order."""
import tests  # noqa: F401 -- runtime-file isolation

from dataclasses import replace
import unittest

from hengbot.model import (
    Position, Snapshot, StoreState, STORE_ALCHEMIST, STORE_GENERAL, STORE_HOME,
    TVAL_DIGGING, TVAL_FOOD, TVAL_LITE, TVAL_SCROLL, SV_DIGGING_SHOVEL,
    SV_LITE_FEANOR, SV_SCROLL_DETECT_TREASURE, SV_SCROLL_IDENTIFY,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import PACK_CAPACITY
from policy_fixtures import grid, item, player, store_item


def crowded_fundraiser(class_id):
    home = Position(10, 11)
    return Snapshot(
        player(10, 10, gold=200, class_id=class_id),
        {Position(10, 10): replace(grid(10, 10), store_number=STORE_GENERAL),
         home: replace(grid(10, 11), store_number=STORE_HOME)},
        [],
        inventory=[item(chr(97 + index), TVAL_FOOD, -1,
                        name=f"unknown {index}", aware=False, known=False)
                   for index in range(PACK_CAPACITY)],
        equipment=[item("light", TVAL_LITE, SV_LITE_FEANOR,
                        is_equipment=True)],
        floor_key=(0, 0, 0), town_flag=True, town_id=0,
        width=30, height=30, turn=100,
    )


class MagicEaterPrekitTest(unittest.TestCase):
    def assert_purchase_order(self, class_id):
        """Drive the real purchase selector as each kit piece becomes carried."""
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._request_identification("normal")
        detection = store_item("a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
                               price=20, count=10)
        identify = store_item("b", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=50)
        digger = store_item("c", TVAL_DIGGING, SV_DIGGING_SHOVEL, price=80)
        board = crowded_fundraiser(class_id)
        board = replace(
            board, player=replace(board.player, gold=400),
            inventory=[item("f", TVAL_FOOD, 35, count=5),
                       item("u", TVAL_LITE, SV_LITE_FEANOR,
                            known=False, is_equipment=True)],
            store=StoreState(STORE_ALCHEMIST, [identify, detection]),
        )
        self.assertIs(policy._next_purchase(board), detection)
        # Constructed observations after buying five scrolls, then a shovel.
        board = replace(
            board, player=replace(board.player, gold=300),
            inventory=[*board.inventory,
                       item("d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5)],
            store=StoreState(STORE_GENERAL, [digger]),
        )
        self.assertIs(policy._next_purchase(board), digger)
        board = replace(
            board, player=replace(board.player, gold=220),
            inventory=[*board.inventory, item("e", TVAL_DIGGING, SV_DIGGING_SHOVEL)],
            store=StoreState(STORE_ALCHEMIST, [identify]),
        )
        self.assertIs(policy._next_purchase(board), identify)

    def test_crowded_fundraiser_acquires_home_catalogue_like_warrior(self):
        results = []
        for class_id in (0, 16):
            with self.subTest(class_id=class_id):
                board = crowded_fundraiser(class_id)
                policy = HengbotPolicy()
                policy._fundraising_mode = "prepare"
                policy._request_identification("full")
                self.assertFalse(policy._fundraising_supplies_ready(board))
                key = policy.choose_key(board)
                results.append((str(key), policy.last_reason))
                self.assertEqual(policy._identification_need, "full")
                self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
                self.assert_purchase_order(class_id)
        self.assertEqual(results, [
            ("~9\x1b", "equipment-transaction:catalogue-request-knowledge"),
            ("~9\x1b", "equipment-transaction:catalogue-request-knowledge"),
        ])


if __name__ == "__main__":
    unittest.main()
