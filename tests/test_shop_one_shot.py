import unittest
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    Position,
    Snapshot,
    STORE_ALCHEMIST,
    STORE_HOME,
    StoreItem,
    StoreState,
    SV_BOW_SLING,
    SV_DIGGING_SHOVEL,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_RESIST_COLD,
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
    SV_LITE_TORCH,
    SV_STAFF_IDENTIFY,
    TVAL_STAFF,
)
from hengbot.policy import (
    FOOD_MIN_SVAL, FOOD_TYPE_MANA, OIL_TARGET, HengbotPolicy,
    LEAVE_STORE_KEY, STORE_GENERAL, STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON,
    STORE_STUCK_LIMIT, TownErrandPlan, ProcurementHomeGate,
)
from hengbot.cli import _snapshot_entries_in_order
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
        self.assertEqual(entry, "5", policy.last_reason)
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

    def test_pending_inscription_bound_sale_outranks_purchase_and_composes_exact_tail(self):
        """The frozen low-level sale may not lose its second visit to buying."""
        sold = item("b", TVAL_POTION, SV_POTION_RESIST_COLD, name="potion")
        wanted = store_item(
            "m", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, price=24, count=46
        )
        inside = self._inside(STORE_ALCHEMIST, [sold], [wanted], gold=104)
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(inside), LEAVE_STORE_KEY)
        outside = self._outside(policy, inside)
        self.assertEqual(policy.choose_key(outside), "{b@0\r")

        tagged_outside = replace(
            outside,
            inventory=[replace(sold, inscription="@0")],
            turn=outside.turn + 1,
        )
        self.assertEqual(policy.choose_key(tagged_outside), "5")
        tagged_inside = replace(
            inside,
            inventory=tagged_outside.inventory,
            turn=tagged_outside.turn + 1,
        )
        self.assertEqual(policy.choose_key(tagged_inside), "d0y\x1b")
        self.assertEqual(policy.last_reason, "shop:one-shot-sell")

    def test_live_capture_name_only_sale_tag_composes_instead_of_reinscribing(self):
        """The S-3 capture emits @0 in name while inscription is null."""
        artifact = Path("evidence/evidence-sale-inflight-lines.jsonl")
        captured = None
        for line in artifact.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("type") == "store" and row.get("turn") == 192393:
                snapshots = _snapshot_entries_in_order([line])
                if snapshots and snapshots[-1].store is not None:
                    captured = snapshots[-1]
                    break
        self.assertIsNotNone(captured)
        sold = next(item for item in captured.inventory if item.slot == "b")
        self.assertEqual(sold.inscription, "")
        self.assertRegex(sold.name, r"\{@0\}$")

        policy = HengbotPolicy()
        key = policy._batch_sell_key(captured, [sold])

        # Every other captured surplus already displays @0, so the shared
        # allocator must see those collisions and bind this sale to @1.
        self.assertEqual(key, "{b@1\r")
        self.assertEqual(policy.last_reason, "shop:batch-inscribe")
        self.assertEqual(policy._batch_sell_pending["phase"], "await-inscription")

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

    def test_confirmed_store_five_buy_releases_visit_before_store_seven_approach(self):
        ware = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20
        )
        inside = self._inside(STORE_MAGIC, [], [ware])
        policy = HengbotPolicy(town_map=None)
        outside, key = self._compose(policy, inside)
        store_five_visit = policy._store_visit
        completed = self._consume_buy(outside, key, ware)

        policy.choose_key(completed)
        self.assertIs(policy._store_visit_last_closed, store_five_visit)
        self.assertNotEqual(policy._store_visit.store_type, STORE_MAGIC)

        home = Position(10, 13)
        town_grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 12)
            for x in range(9, 15)
        }
        town_grids[home] = replace(town_grids[home], store_number=STORE_HOME)
        next_decision = replace(
            completed,
            grids=town_grids,
            turn=completed.turn + 1,
            width=30,
            height=30,
        )
        # Confirmation may already open the next derived supply visit; isolate
        # the measured store-7 plan from that unrelated supply derivation.
        policy._close_store_visit("fixture-isolate-store-seven-plan")
        policy._town_blocked_reason = None
        policy._shopping_approach_goal = None
        policy._shopping_approach_store_type = None
        step = policy._shopping_approach_step(next_decision, STORE_HOME)

        self.assertIsNotNone(step, (
            policy._town_store_attempted,
            policy._town_visit_ledger.blocked_stores,
            policy._town_visit_ledger.approach_fails,
            policy._shopping_stuck,
        ))
        self.assertEqual(policy._direction_key(next_decision.player.position, step), "6")
        self.assertEqual(policy._store_visit.store_type, STORE_HOME)

    def test_observed_sale_releases_through_declared_store_visit_evaluator(self):
        sold = replace(item("j", TVAL_WAND, 1, name="wand"), inscription="@0")
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        outside, key = self._compose(policy, inside)
        visit = policy._store_visit
        confirmed = replace(
            outside,
            inventory=[],
            player=replace(outside.player, gold=outside.player.gold + 125),
            turn=outside.turn + 1,
        )

        policy.choose_key(confirmed)
        self.assertTrue(visit.operation_effect_observed)
        policy._evaluate_cross_decision_latches(
            replace(confirmed, turn=confirmed.turn + 1)
        )

        self.assertIs(policy._store_visit_last_closed, visit)
        self.assertIsNot(policy._store_visit, visit)

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

    def test_empty_one_shot_releases_visit_before_approaching_other_store(self):
        inside = self._inside(STORE_MAGIC, [], [])
        temple_entrance = replace(grid(10, 14), store_number=STORE_TEMPLE)
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(inside), LEAVE_STORE_KEY)
        outside = replace(
            self._outside(policy, inside),
            grids={**inside.grids, temple_entrance.position: temple_entrance},
        )
        step = policy.choose_key(outside)

        self.assertEqual(step, "6")
        self.assertEqual(policy._shopping_approach_store_type, STORE_TEMPLE)
        self.assertEqual(
            policy._store_visit_last_closed.outcome, "one-shot-no-operation"
        )

    def test_entry_flush_ledger_requires_two_stage_release(self):
        """70dcabc failure: one store iteration followed ``5d0y ESC``;
        only ``5`` entered the command loop, the entry flush lost its tail,
        and the unchanged ledger never completed the transaction.
        """
        fixture = Path(__file__).with_name("fixtures") / "oneshot_flush_ledger.jsonl"
        rows = [json.loads(line) for line in fixture.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["type"] for row in rows if row["kind"] == "snapshot"], ["store", "player_turn"])
        self.assertEqual([row["gold"] for row in rows if row["kind"] == "snapshot"], [7121, 7121])

        sold = replace(item("j", TVAL_WAND, 1, name="wand"), inscription="@0")
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(inside), LEAVE_STORE_KEY)
        outside = self._outside(policy, inside)

        entry_batch = policy.choose_key(outside)
        self.assertEqual(entry_batch, "5")
        buffered = list(entry_batch)
        self.assertEqual(buffered.pop(0), "5")
        buffered.clear()  # GAME-IO #2: entry disturb/flush/term_flush.
        self.assertEqual(buffered, [])

        operation_batch = policy.choose_key(replace(inside, turn=outside.turn + 1))
        self.assertEqual(operation_batch, "d0y\x1b")
        completed = replace(
            outside,
            inventory=[],
            player=replace(outside.player, gold=outside.player.gold + 125),
            turn=outside.turn + 2,
        )
        policy.choose_key(completed)
        self.assertIsNone(policy._batch_sell_pending)
        self.assertFalse(policy._store_visit.operation_posted)

    def test_stage_one_entry_wait_expires_and_routing_resumes(self):
        """2f449d2 returned 80 empty shop:one-shot-in-flight decisions."""
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        policy.choose_key(inside)
        outside = self._outside(policy, inside)
        self.assertEqual(policy.choose_key(outside), "5")

        waits = [
            policy.choose_key(replace(outside, turn=outside.turn + turn))
            for turn in range(1, STORE_STUCK_LIMIT + 2)
        ]
        self.assertEqual(waits[:STORE_STUCK_LIMIT], [""] * STORE_STUCK_LIMIT)
        self.assertNotEqual(waits[-1], "")
        self.assertEqual(
            policy._store_visit_last_closed.outcome,
            "one-shot-entry-unconfirmed",
        )

    def test_close_after_release_clears_buy_inflight(self):
        """2f449d2 stranded ``(3, ('wares', 70, 11), ...)`` after close."""
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, _key = self._compose(policy, inside)
        self.assertTrue(policy._store_visit.operation_released)
        self.assertIsNotNone(policy._store_buy_inflight)

        policy._close_store_visit("fixture-close-after-release")

        self.assertIsNone(policy._store_buy_inflight)
        self.assertIsNone(policy._store_visit)

    def test_close_after_release_clears_batch_sell_pending(self):
        """2f449d2 left an ownerless await-sale batch after released close."""
        sold = replace(item("j", TVAL_WAND, 1, name="wand"), inscription="@0")
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        self._compose(policy, inside)
        self.assertTrue(policy._store_visit.operation_released)
        self.assertEqual(policy._batch_sell_pending["phase"], "await-sale")

        policy._close_store_visit("fixture-close-after-release")

        self.assertIsNone(policy._batch_sell_pending)
        self.assertIsNone(policy._store_visit)

    def test_buy_budget_resolves_even_if_visit_owner_is_already_none(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        outside, _key = self._compose(policy, inside)
        policy._store_visit = None  # Reproduce the 2f449d2 orphaned shape.

        for turn in range(1, STORE_STUCK_LIMIT + 1):
            self._decision(policy, replace(outside, turn=outside.turn + turn))

        self.assertIsNone(policy._store_buy_inflight)

    def test_sale_budget_resolves_even_if_visit_owner_is_already_none(self):
        sold = replace(item("j", TVAL_WAND, 1, name="wand"), inscription="@0")
        inside = self._inside(STORE_MAGIC, [sold], [])
        policy = HengbotPolicy()
        outside, _key = self._compose(policy, inside)
        policy._store_visit = None  # Reproduce the 2f449d2 orphaned shape.

        for turn in range(1, STORE_STUCK_LIMIT + 1):
            self._decision(policy, replace(outside, turn=outside.turn + turn))

        self.assertIsNone(policy._batch_sell_pending)

    def test_stage_two_releases_fresh_page_and_enters_operating_phase(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = replace(self._inside(STORE_TEMPLE, [], [ware]), turn=99)
        policy = HengbotPolicy()
        policy.choose_key(inside)
        outside = replace(self._outside(policy, inside), turn=140)
        self.assertEqual(policy.choose_key(outside), "5")

        self.assertEqual(policy.choose_key(replace(inside, turn=140)), "pa\r\x1b")
        self.assertTrue(policy._store_visit.operation_released)
        self.assertEqual(policy._store_visit.phase.value, "operating")

    def test_stage_two_refuses_stale_store_page(self):
        """2f449d2 released a turn-99 page for a turn-140 stage-one post."""
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = replace(self._inside(STORE_TEMPLE, [], [ware]), turn=99)
        policy = HengbotPolicy()
        policy.choose_key(inside)
        outside = replace(self._outside(policy, inside), turn=140)
        self.assertEqual(policy.choose_key(outside), "5")

        self.assertEqual(policy.choose_key(inside), "")
        self.assertFalse(policy._store_visit.operation_released)

    def test_stage_two_refuses_a_different_visits_store_page(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
        inside = self._inside(STORE_TEMPLE, [], [ware])
        policy = HengbotPolicy()
        inside = replace(inside, turn=10)
        policy.choose_key(inside)
        outside = replace(self._outside(policy, inside), turn=11)
        self.assertEqual(policy.choose_key(outside), "5")
        first_visit = policy._store_visit
        policy._close_store_visit("fixture-other-visit")
        policy._shopping_approach_store_type = STORE_TEMPLE

        newer_inside = replace(inside, turn=12)
        self.assertEqual(policy.choose_key(newer_inside), "\x1b")
        newer_outside = replace(outside, turn=13)
        self.assertEqual(policy.choose_key(newer_outside), "5")
        self.assertIsNot(policy._store_visit, first_visit)
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertEqual(policy.choose_key(newer_inside), "")
        self.assertFalse(policy._store_visit.operation_released)


    def test_mandatory_torch_and_oil_precede_optional_surplus_across_entries(self):
        """Replay the 8/22 oil stall through public choose_key composition."""
        incident = Path(
            "jsonlog/incident-town-oil-claim-stall-20260822.jsonl"
        )
        policy_state = Path(
            "incident-captures/20260822-100522-posting-contract-"
            "identical-repost-unobserved/policy-state.json"
        )
        self.assertTrue(incident.exists())
        self.assertTrue(policy_state.exists())
        incident_rows = [json.loads(line) for line in incident.read_text(
            encoding="utf-8"
        ).splitlines()]
        self.assertTrue(any(
            row.get("procurement_requirements") == [{
                "item": "Flasks of oil", "current": 2,
                "target": 5, "missing": 3,
            }]
            for row in incident_rows
        ))
        self.assertEqual(
            json.loads(policy_state.read_text(encoding="utf-8"))["floor"],
            [0, 0, 0],
        )
        optional = store_item("a", TVAL_LITE, SV_LITE_TORCH, price=3, count=1)
        lantern = store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=5, count=1)
        oil = store_item("c", TVAL_FLASK, 0, price=4, count=1)
        supplies = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=12),
            item("f", TVAL_FOOD, FOOD_MIN_SVAL, count=5),
            item("o", TVAL_FLASK, 0, count=OIL_TARGET - 1),
        ]
        inside = self._inside(
            STORE_GENERAL, supplies, [optional, lantern, oil], gold=1000
        )
        policy = HengbotPolicy()
        policy._deepest_level = 2
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._home_scan_item_count = 0
        policy._town_errand_plan = TownErrandPlan([STORE_GENERAL])
        with mock.patch.object(
            policy, "_purchase_has_fresh_home_absence",
            return_value=ProcurementHomeGate.ALLOW_PURCHASE,
        ), mock.patch.object(
            policy, "_find_light_sale", return_value=None,
        ):
            outside, first = self._compose(policy, inside)
            self.assertEqual(first, "5pb\r\x1b")
            after_lantern = self._consume_buy(outside, first, lantern)
            policy.choose_key(after_lantern)
            self.assertNotIn(STORE_GENERAL, policy._town_store_attempted)

            second_inside = replace(
                inside,
                turn=after_lantern.turn + 1,
                inventory=after_lantern.inventory,
                player=after_lantern.player,
                store=StoreState(STORE_GENERAL, [optional, oil]),
            )
            second_outside, second = self._compose(policy, second_inside)
            self.assertEqual(second, "5pc\r\x1b")
            after_oil = self._consume_buy(second_outside, second, oil)
            policy.choose_key(after_oil)
            self.assertIn(policy._item_signature(oil), policy._town_visit_purchases)

            optional_page = replace(
                second_inside,
                turn=after_oil.turn + 1,
                inventory=after_oil.inventory,
                player=after_oil.player,
                store=StoreState(STORE_GENERAL, [optional]),
            )
            self.assertIs(
                policy._next_purchase_unreserved(optional_page),
                optional_page.store.items[0],
            )

    def test_met_mandatory_categories_leave_optional_torch_purchase_available(self):
        torch = store_item(
            "a", TVAL_LITE, SV_LITE_TORCH, price=3, count=1
        )
        inside = replace(
            self._inside(
                STORE_GENERAL,
                [
                    *self._ammo_supplies(),
                    item("q", TVAL_LITE, SV_LITE_TORCH, count=5, fuel=5000),
                ],
                [torch],
            ),
            equipment=[item(
                "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000,
                known=True, is_equipment=True,
            )],
        )
        profile = SimpleNamespace(
            required_force={"throwing_items": {"lit_torch": 5}},
            engagement_plan={},
        )
        policy = HengbotPolicy()
        with mock.patch.object(
            policy, "_carry_procurement_strategy", return_value=profile
        ):
            self.assertIs(policy._next_purchase_unreserved(inside), torch)

    def test_unaffordable_mandatory_page_can_latch_without_rearm(self):
        oil = store_item("a", TVAL_FLASK, 0, price=400, count=1)
        outside = replace(
            self._inside(
                STORE_GENERAL,
                [item("o", TVAL_FLASK, 0, count=OIL_TARGET - 1)],
                [oil],
                gold=3,
            ),
            store=None,
        )
        policy = HengbotPolicy()
        policy._town_supplier_stock[STORE_GENERAL] = StoreState(
            STORE_GENERAL, [oil]
        )
        policy._town_store_attempted[STORE_GENERAL] = outside.turn

        self.assertIsNone(policy._mandatory_purchase(
            replace(outside, store=policy._town_supplier_stock[STORE_GENERAL])
        ))
        self.assertIn(STORE_GENERAL, policy._town_store_attempted)

    def test_mandatory_selector_terminates_when_oil_requirement_is_met(self):
        oil = store_item("a", TVAL_FLASK, 0, price=4, count=20)
        snapshot = replace(
            self._inside(
                STORE_GENERAL,
                [*self._ammo_supplies(), item("extra", TVAL_FLASK, 0, count=5)],
                [oil],
                gold=10000,
            ),
            equipment=[item(
                "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000,
                known=True, is_equipment=True,
            )],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 2

        self.assertIsNone(policy._mandatory_purchase(snapshot))

    def test_mandatory_oil_precedes_optional_purchase_on_same_page(self):
        optional = store_item("a", TVAL_POTION, SV_POTION_RESIST_COLD, price=1)
        oil = store_item("b", TVAL_FLASK, 0, price=4)
        snapshot = replace(
            self._inside(
                STORE_GENERAL,
                [*self._ammo_supplies()[:-3], item("o", TVAL_FLASK, 0, count=2)],
                [optional, oil],
                gold=1000,
            ),
            equipment=[item(
                "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000,
                known=True, is_equipment=True,
            )],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 2

        with mock.patch.object(
            policy, "_restore_potion_purchase", return_value=optional
        ):
            self.assertIs(policy._next_purchase_unreserved(snapshot), oil)

    def test_mandatory_mana_food_respects_magic_hoard_liquidation_guard(self):
        identify = store_item(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY, price=200, count=1, pval=8
        )
        snapshot = replace(
            self._inside(STORE_MAGIC, [], [identify], gold=1000),
            player=replace(
                self._inside(STORE_MAGIC, [], [], gold=1000).player,
                food_type=FOOD_TYPE_MANA,
            ),
        )
        policy = HengbotPolicy()
        policy._home_identify_staff_sold_this_magic_visit = True

        self.assertIsNone(policy._mandatory_purchase(snapshot))


if __name__ == "__main__":
    unittest.main()
