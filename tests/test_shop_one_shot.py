import unittest
import json
from dataclasses import replace
from pathlib import Path

from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    Position,
    Snapshot,
    StoreItem,
    StoreState,
    SV_BOW_SLING,
    SV_DIGGING_SHOVEL,
    SV_POTION_CURE_CRITICAL,
    SV_SCROLL_DETECT_TREASURE,
    SV_SCROLL_TELEPORT,
    SV_SCROLL_WORD_OF_RECALL,
    TVAL_BOW,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_POTION,
    TVAL_SCROLL,
    TVAL_SHOT,
    TVAL_WAND,
    TVAL_LITE,
    SV_LITE_LANTERN,
)
from hengbot.policy import (
    FOOD_MIN_SVAL, OIL_TARGET, HengbotPolicy, LEAVE_STORE_KEY, STORE_GENERAL,
    STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON, STORE_STUCK_LIMIT,
)
from tests.test_policy import grid, hostile, item, player, store_item


class ShopOneShotTest(unittest.TestCase):
    @staticmethod
    def _decision(policy, snapshot):
        return policy.choose_key(snapshot)

    @staticmethod
    def _ammo_supplies():
        return [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=12),
            item("f", TVAL_FOOD, FOOD_MIN_SVAL, count=5),
            item("o", TVAL_FLASK, 0, count=OIL_TARGET),
            item("z", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            item("v", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5),
        ]

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
            elif state == "confirm" and pressed.isdigit():
                state = "quantity"
            elif state == "quantity" and pressed == "\r":
                state = "confirm"
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

    def _consume_buy_with_lagged_surface(self, policy, outside, key, inside, ware):
        """Consume a macro while exposing the entrance and store snapshots."""
        state, gold, inventory = "surface", outside.player.gold, list(outside.inventory)
        policy_keys = []
        for pressed in key:
            if state == "surface" and pressed == "5":
                state = "store"
                lagged = replace(outside, turn=outside.turn + 1)
                policy_keys.append(policy.choose_key(lagged))
                intermediate = replace(inside, turn=outside.turn + 2)
                policy_keys.append(policy.choose_key(intermediate))
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
        completed = replace(
            outside,
            player=replace(outside.player, gold=gold),
            inventory=inventory,
            turn=outside.turn + 3,
        )
        policy_keys.append(policy.choose_key(completed))
        return completed, policy_keys

    def _consume_sale_with_lagged_pages(self, policy, outside, key, inside):
        """Consume a sale while exposing the same pages as the buy probe."""
        state, gold, inventory = "surface", outside.player.gold, list(outside.inventory)
        policy_keys = []
        for pressed in key:
            if state == "surface" and pressed == "5":
                state = "store"
                policy_keys.append(self._decision(policy, replace(outside, turn=2)))
                policy_keys.append(self._decision(policy, replace(inside, turn=3)))
            elif state == "store" and pressed == "d": state = "item"
            elif state == "item" and pressed == "0": state = "confirm"
            elif state == "confirm" and pressed == "y":
                inventory.clear()
                gold += 125
                state = "store"
            elif state == "store" and pressed == "\x1b": state = "surface"
            else: self.fail((state, pressed))
        completed = replace(
            outside, inventory=inventory, player=replace(outside.player, gold=gold),
            turn=4,
        )
        policy_keys.append(policy.choose_key(completed))
        return completed, policy_keys

    def _compose(self, policy, inside):
        """Drive the public observation boundary and return its one-shot."""
        self.assertEqual(policy.choose_key(inside), LEAVE_STORE_KEY)
        outside = self._outside(policy, inside)
        entry = policy.choose_key(outside)
        self.assertEqual(entry, "5")
        operation = policy.choose_key(replace(inside, turn=outside.turn + 1))
        return outside, entry + operation

    def test_sale_observe_then_driven_one_shot_changes_pack_and_gold(self):
        sold = replace(
            item("j", TVAL_WAND, 1, name="wand"), inscription="@0"
        )
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(inside), "\x1b")
        outside = self._outside(policy, inside)
        entry = policy.choose_key(outside)
        self.assertEqual(entry, "5")
        key = entry + policy.choose_key(replace(inside, turn=outside.turn + 1))
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
        entry = policy.choose_key(outside)
        self.assertEqual(entry, "5")
        key = entry + policy.choose_key(replace(inside, turn=outside.turn + 1))
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
        self.assertEqual(policy.choose_key(outside), "5")
        self.assertEqual(policy.choose_key(replace(changed, turn=outside.turn + 1)), "pb\r\x1b")

    def test_intermediate_one_shot_pages_emit_no_foreign_keys(self):
        ware = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20
        )
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        policy.choose_key(inside)
        outside = self._outside(policy, inside)
        self.assertEqual(policy.choose_key(outside), "5")
        intermediate = replace(inside, turn=inside.turn + 2)
        self.assertEqual(policy.choose_key(intermediate), "pa\r\x1b")
        intermediate = replace(inside, turn=inside.turn + 3)
        self.assertEqual(policy.choose_key(intermediate), "")
        self.assertEqual(policy.last_reason, "shop:one-shot-in-flight")

    def test_lagged_surface_inside_live_macro_confirms_exactly_one_buy(self):
        """ecf55de produced ['5', '\\x1b', '5pa\\r\\x1b'] (reviewer-measured):
        the lagged page dropped the latch, a foreign ESC entered the live
        macro, and the SAME buy was composed again. None of that is allowed."""
        ware = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20
        )
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)

        completed, policy_keys = self._consume_buy_with_lagged_surface(
            policy, outside, key, inside, ware
        )

        self.assertEqual(key, "5pa\r\x1b")
        self.assertEqual(policy_keys[:2], ["", ""])
        self.assertNotIn("pa", policy_keys[-1])
        self.assertEqual(completed.player.gold, outside.player.gold - 20)
        self.assertIn(
            policy._item_signature(ware), policy._town_visit_purchases
        )
        self.assertFalse(policy._store_visit.operation_posted)

    def test_completed_one_shot_new_store_page_is_not_permanent_silence(self):
        """9f05878 returned ten empty shop:one-shot-in-flight decisions."""
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(inside), "\x1b")
        outside = self._outside(policy, inside)
        self.assertEqual(policy.choose_key(outside), "5")
        key = "5" + policy.choose_key(replace(inside, turn=outside.turn + 1))
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
        outside, key = self._compose(policy, inside)
        completed = self._consume_buy(outside, key, ware)
        policy.choose_key(completed)

        signature = policy._item_signature(ware)
        self.assertIn(signature, policy._town_visit_purchases)

    def test_confirmed_sale_clears_posted_operation_latch(self):
        sold = replace(item("j", TVAL_WAND, 1, name="wand"), inscription="@0")
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        self.assertEqual(key, "5d0y\x1b")
        self.assertTrue(policy._store_visit.operation_posted)

        confirmed = replace(
            outside,
            inventory=[],
            player=replace(outside.player, gold=outside.player.gold + 125),
            turn=outside.turn + 1,
        )
        policy.choose_key(confirmed)

        self.assertFalse(policy._store_visit.operation_posted)
        self.assertIsNone(policy._batch_sell_pending)

    def test_lagged_surface_inside_live_macro_confirms_exactly_one_sale(self):
        sold = replace(item("j", TVAL_WAND, 1, name="wand"), inscription="@0")
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)

        completed, policy_keys = self._consume_sale_with_lagged_pages(
            policy, outside, key, inside
        )

        self.assertEqual(key, "5d0y\x1b")
        self.assertEqual(policy_keys[:2], ["", ""])
        self.assertEqual(completed.player.gold, outside.player.gold + 125)
        self.assertIsNone(policy._batch_sell_pending)
        self.assertIsNone(policy._store_sell_attempt)
        self.assertFalse(policy._store_visit.operation_posted)

    def test_unconfirmed_sale_releases_at_budget_without_early_attempt_advance(self):
        sold = replace(item("j", TVAL_WAND, 1, name="wand"), inscription="@0")
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        visit = policy._store_visit
        self.assertEqual(key, "5d0y\x1b")

        for wait in range(1, STORE_STUCK_LIMIT):
            self.assertEqual(self._decision(policy, replace(outside, turn=wait + 1)), "")
            self.assertIs(policy._store_visit, visit)
            self.assertIsNone(policy._store_sell_attempt)
        policy.choose_key(replace(outside, turn=STORE_STUCK_LIMIT + 1))

        self.assertIs(policy._store_visit_last_closed, visit)
        self.assertEqual(visit.outcome, "one-shot-sale-unconfirmed")
        self.assertFalse(visit.operation_posted)
        self.assertIsNotNone(policy._store_sell_attempt)

    def test_unaccepted_purchase_is_not_recorded_as_completed(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        self.assertEqual(key, "5pa\r\x1b")
        policy.choose_key(replace(outside, turn=outside.turn + 1))
        self.assertNotIn(policy._item_signature(ware), policy._town_visit_purchases)

    def test_leaves_store_when_purchase_never_registers(self):
        ware = store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120)
        inside = self._inside(STORE_GENERAL, [], [ware], gold=1000)
        policy = HengbotPolicy()
        outside, first = self._compose(policy, inside)
        self.assertEqual(first, "5pb\r\x1b")
        decisions = [first]
        for turn in range(2, STORE_STUCK_LIMIT + 2):
            decisions.append(self._decision(policy, replace(outside, turn=turn)))
        self.assertEqual(sum("pb" in key for key in decisions), 1)
        self.assertEqual(policy._store_visit_last_closed.outcome, "one-shot-buy-unconfirmed")

    def test_rejected_purchase_times_out_and_stuck_backstop_leaves(self):
        ware = store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120)
        inside = self._inside(STORE_GENERAL, [], [ware], gold=1000)
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        decisions = [key]
        for turn in range(10, 10 + STORE_STUCK_LIMIT):
            decisions.append(self._decision(policy, replace(outside, turn=turn)))
        self.assertEqual(sum("pb" in value for value in decisions), 1)
        self.assertEqual(policy._store_visit_last_closed.outcome, "one-shot-buy-unconfirmed")

    def test_alchemist_context_flicker_does_not_repeat_unconfirmed_purchase(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        surface_key = policy.choose_key(replace(outside, turn=2))
        store_key = policy.choose_key(replace(inside, turn=3))
        surface_key_2 = policy.choose_key(replace(outside, turn=4))
        self.assertLessEqual(sum("pa" in value for value in (key, surface_key, store_key, surface_key_2)), 1)

    def test_alchemist_combat_flicker_does_not_repeat_unconfirmed_purchase(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        combat = replace(
            outside, turn=2,
            visible_monsters=[hostile(1, 10, 11, max_melee_damage=10)],
        )
        decisions = [key, policy.choose_key(combat), policy.choose_key(replace(inside, turn=3))]
        self.assertEqual(sum("pa" in value for value in decisions), 1)
        self.assertTrue(policy._store_visit.operation_posted)

    def test_alchemist_interleaved_unconfirmed_purchase_keeps_bounded_window(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        other_store = replace(inside, store=StoreState(STORE_MAGIC, []), turn=2)
        decisions = [key, policy.choose_key(other_store), policy.choose_key(replace(outside, turn=3))]
        self.assertEqual(sum("pa" in value for value in decisions), 1)
        self.assertEqual(decisions[1:], ["", ""])

    def test_completed_stacked_buy_stops_three_page_retry_construction(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20, count=3)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        completed = self._consume_buy(outside, key, ware)
        policy.choose_key(completed)
        self.assertIsNone(policy._store_buy_inflight)
        self.assertIn(policy._item_signature(ware), policy._town_visit_purchases)
        keys = [policy.choose_key(replace(completed, turn=turn)) for turn in range(3, 15)]
        self.assertFalse(any("pa" in value for value in keys))

    def test_partial_low_gold_ammo_purchase_completes_without_looping(self):
        ware = StoreItem("d", "iron shot", 7, TVAL_SHOT, 1, price=10)
        inside = replace(
            self._inside(
                STORE_WEAPON,
                self._ammo_supplies(),
                [ware],
                gold=20,
            ),
            equipment=[
                item("b", TVAL_BOW, SV_BOW_SLING, name="sling", is_equipment=True),
                item(
                    "l", TVAL_LITE, SV_LITE_LANTERN,
                    fuel=5000, is_equipment=True,
                ),
            ],
        )
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        self.assertEqual(key, "5pd2\r\r\x1b")
        completed = replace(
            outside,
            player=replace(outside.player, gold=0),
            inventory=[
                item("a", TVAL_SHOT, 1, name="iron shots", count=2),
                *outside.inventory,
            ],
            turn=outside.turn + 1,
        )
        policy.choose_key(completed)
        self.assertIsNone(policy._store_buy_inflight)
        self.assertIn(policy._item_signature(ware), policy._town_visit_purchases)
        later = [policy.choose_key(replace(completed, turn=turn)) for turn in range(3, 6)]
        self.assertFalse(any("pd" in value for value in later))

    def test_choose_key_purchase_watch_records_only_confirmed_buy(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        signature = policy._item_signature(ware)
        self.assertNotIn(signature, policy._town_visit_purchases)
        policy.choose_key(self._consume_buy(outside, key, ware))
        self.assertIn(signature, policy._town_visit_purchases)

    def test_store_wait_is_noop_and_never_emits_page_turn_key(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        self.assertEqual(key, "5pa\r\x1b")
        waiting = policy.choose_key(replace(inside, turn=inside.turn + 2))
        self.assertEqual(waiting, "")
        self.assertNotIn(waiting, (" ", "-"))

    def test_atomic_composition_accepts_page_zero(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = replace(
            self._inside(STORE_TEMPLE, [], [ware]),
            store=StoreState(STORE_TEMPLE, [ware], page_top=0, page_size=12),
        )
        _, key = self._compose(HengbotPolicy(), inside)
        self.assertEqual(key, "5pa\r\x1b")

    def test_atomic_composition_refuses_nonzero_page_and_reobserves(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = replace(
            self._inside(STORE_TEMPLE, [], [ware]),
            store=StoreState(STORE_TEMPLE, [ware], page_top=12, page_size=12),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(inside), LEAVE_STORE_KEY)
        outside = self._outside(policy, inside)
        self.assertNotIn("pa", policy.choose_key(outside))
        self.assertIsNone(policy._shop_observation)

    def test_entry_flush_ledger_requires_two_stage_release(self):
        """70dcabc failure: one store iteration followed ``5d0y ESC``;
        only ``5`` entered the command loop and the entry flush lost its tail.
        """
        fixture = Path(__file__).with_name("fixtures") / "oneshot_flush_ledger.jsonl"
        rows = [json.loads(line) for line in fixture.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["type"] for row in rows if row["kind"] == "snapshot"], ["store", "player_turn"])
        self.assertEqual([row["gold"] for row in rows if row["kind"] == "snapshot"], [7121, 7121])

        def consume(entry_batch, operation_batch=None):
            buffered = list(entry_batch)
            self.assertEqual(buffered.pop(0), "5")
            buffered.clear()  # GAME-IO #2: entry disturb/flush/term_flush.
            if operation_batch is not None:
                buffered.extend(operation_batch)
            return "".join(buffered)

        self.assertEqual(consume("5d0y\x1b"), "")
        self.assertEqual(consume("5", "d0y\x1b"), "d0y\x1b")

    def test_stage_two_refuses_a_different_visits_store_page(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        policy.choose_key(inside)
        outside = self._outside(policy, inside)
        self.assertEqual(policy.choose_key(outside), "5")
        first_visit = policy._store_visit
        policy._close_store_visit("fixture-other-visit")
        policy._shopping_approach_store_type = STORE_TEMPLE

        self.assertIsNot(policy._store_visit, first_visit)
        self.assertEqual(policy.choose_key(replace(inside, turn=outside.turn + 1)), "\x1b")
        self.assertFalse(policy._store_visit.operation_released)


if __name__ == "__main__":
    unittest.main()
