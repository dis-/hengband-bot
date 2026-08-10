import unittest
from dataclasses import replace

from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    Position,
    Snapshot,
    StoreState,
    SV_SCROLL_WORD_OF_RECALL,
    TVAL_SCROLL,
    TVAL_WAND,
)
from hengbot.policy import HengbotPolicy, STORE_MAGIC, STORE_TEMPLE
from tests.test_policy import grid, item, player, store_item


class ShopOneShotTest(unittest.TestCase):
    def _inside(self, store_type, inventory, wares, *, gold=7589):
        entrance = replace(grid(10, 10), store_number=store_type)
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): entrance}, [], inventory=inventory,
            store=StoreState(store_type, wares), town_flag=True,
        )

    def _outside(self, policy, inside):
        return replace(inside, store=None, turn=inside.turn + 1)

    def _consume_buy(self, outside, key, ware):
        state, gold, inventory = "surface", outside.player.gold, list(outside.inventory)
        for pressed in key:
            if state == "surface" and pressed == "5": state = "store"
            elif state == "store" and pressed == "p": state = "item"
            elif state == "item" and pressed == ware.letter: state = "confirm"
            elif state == "confirm" and pressed == "\r":
                gold -= ware.price
                inventory.append(item(
                    "z", ware.tval, ware.sval, name=ware.name, count=1
                ))
                state = "store"
            elif state == "store" and pressed == "\x1b": state = "surface"
            else: self.fail((state, pressed))
        self.assertEqual(state, "surface")
        return replace(
            outside,
            player=replace(outside.player, gold=gold),
            inventory=inventory,
            turn=outside.turn + 1,
        )

    def test_sale_observe_then_driven_one_shot_changes_pack_and_gold(self):
        sold = replace(
            item("j", TVAL_WAND, 1, name="wand"), inscription="@0"
        )
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(inside), "\x1b")
        outside = self._outside(policy, inside)
        key = policy.choose_key(outside)
        self.assertEqual(key, "5d0y\x1b")

        state = "surface"
        pack = list(outside.inventory)
        gold = outside.player.gold
        for pressed in key:
            if state == "surface" and pressed == "5":
                state = "store"
            elif state == "store" and pressed == "d":
                state = "item"
            elif state == "item" and pressed == "0":
                state = "confirm"
            elif state == "confirm" and pressed == "y":
                pack.pop()
                gold += 125
                state = "store"
            elif state == "store" and pressed == "\x1b":
                state = "surface"
            else:
                self.fail((state, pressed))
        self.assertEqual((state, len(pack), gold), ("surface", 0, 7714))

    def test_buy_observe_then_driven_one_shot_debits_gold_and_adds_pack(self):
        ware = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20
        )
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(inside), "\x1b")
        outside = self._outside(policy, inside)
        key = policy.choose_key(outside)
        self.assertEqual(key, "5pa\r\x1b")

        state, gold, count = "surface", outside.player.gold, 0
        for pressed in key:
            if state == "surface" and pressed == "5": state = "store"
            elif state == "store" and pressed == "p": state = "item"
            elif state == "item" and pressed == "a": state = "confirm"
            elif state == "confirm" and pressed == "\r":
                gold -= 20; count += 1; state = "store"
            elif state == "store" and pressed == "\x1b": state = "surface"
            else: self.fail((state, pressed))
        self.assertEqual((state, gold, count), ("surface", 7569, 1))

    def test_newer_page_invalidates_old_letter_and_recomposes(self):
        recall = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20
        )
        old = self._inside(STORE_TEMPLE, [], [recall])
        policy = HengbotPolicy()
        policy.choose_key(old)
        changed = replace(
            old,
            store=StoreState(
                STORE_TEMPLE,
                [store_item("b", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)],
            ),
            turn=old.turn + 1,
        )
        policy.choose_key(changed)
        outside = self._outside(policy, changed)
        self.assertEqual(policy.choose_key(outside), "5pb\r\x1b")

    def test_intermediate_one_shot_pages_emit_no_foreign_keys(self):
        ware = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20
        )
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        policy.choose_key(inside)
        outside = self._outside(policy, inside)
        self.assertEqual(policy.choose_key(outside), "5pa\r\x1b")
        intermediate = replace(inside, turn=inside.turn + 2)
        self.assertEqual(policy.choose_key(intermediate), "")
        self.assertEqual(policy.last_reason, "shop:one-shot-in-flight")

    def test_completed_one_shot_new_store_page_is_not_permanent_silence(self):
        """9f05878 returned ten empty shop:one-shot-in-flight decisions."""
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(inside), "\x1b")
        outside = self._outside(policy, inside)
        key = policy.choose_key(outside)
        completed = self._consume_buy(outside, key, ware)
        policy.choose_key(completed)

        new_page = replace(inside, inventory=completed.inventory, turn=completed.turn + 1)
        decision = policy.choose_key(new_page)
        self.assertNotEqual((decision, policy.last_reason), ("", "shop:one-shot-in-flight"))

    def test_door_composed_buy_survives_to_outside_purchase_accounting(self):
        """9f05878 completed with town_visit_purchases: set() and gold -20."""
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        policy.choose_key(inside)
        outside = self._outside(policy, inside)
        key = policy.choose_key(outside)
        completed = self._consume_buy(outside, key, ware)
        policy.choose_key(completed)

        signature = policy._item_signature(ware)
        self.assertIn(signature, policy._town_visit_purchases)
        repeat_page = replace(inside, inventory=completed.inventory, turn=completed.turn + 1)
        self.assertNotIn("pa", policy.choose_key(repeat_page))


if __name__ == "__main__":
    unittest.main()
