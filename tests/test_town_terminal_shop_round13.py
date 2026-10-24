"""Round 13: the observed shop page owns composition admission and its close."""
import tests  # noqa: F401

from dataclasses import replace
import pickle
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from hengbot import town_terminal as tt
from hengbot.model import STORE_ALCHEMIST, STORE_GENERAL, STORE_HOME, StoreState
from policy_fixtures import grid
from policy_fixtures import item
from hengbot.model import TVAL_SCROLL, SV_SCROLL_IDENTIFY
from hengbot.policy_constants import LEAVE_STORE_KEY
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


RUNG = "_atomic_shop_transaction_key"


def page_board(*, at_entrance=True, page_top=0, store_type=STORE_GENERAL):
    snap = board()
    pos = snap.player.position
    snap = replace(snap, grids={pos: replace(grid(pos.y, pos.x),
        store_number=store_type if at_entrance else -1)})
    policy = policy_on(snap)
    policy._shop_observation = (StoreState(store_type, [], page_top=page_top), 1)
    return policy, snap


class ShopPageAdmissionTest(unittest.TestCase):
    def test_page_context_refusal_keeps_the_body_confirmation_without_selecting(self):
        for kwargs in ({"at_entrance": False}, {"page_top": 1}, {"store_type": STORE_HOME}):
            outcomes = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                policy, snap = page_board(**kwargs)
                with patch.dict(tt.TERMINALS, {RUNG: tt.TERMINALS[RUNG]._replace(mode=mode)}), \
                        patch.object(policy, "_atomic_shop_transaction_key", wraps=policy._atomic_shop_transaction_key) as body, \
                        patch.object(policy, "_shop", side_effect=AssertionError("refused page selected an operation")):
                    self.assertIsNone(policy._town_producer_entry(
                        RUNG, lambda: policy._atomic_shop_transaction_key(snap), family="store-router"))
                self.assertEqual(body.call_count, int(mode == tt.SHADOW))
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["codes"], ["page-not-composable"])
                self.assertEqual(row["mode"], mode)
                self.assertEqual(row["live"], [])
                self.assertEqual(row["closed"], "terminal-refused-unserved:page-not-composable")
                # Compare the actual no-step settlement, including its writer.
                offers = policy._decision_offer_buffer()
                outcomes.append((policy.last_reason, policy._shop_observation, repr(offers)))
            self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(tt.TERMINALS[RUNG].mode, tt.ENFORCE)

    def test_composable_control_keeps_the_selector_and_its_result(self):
        policy, snap = page_board()
        with patch.object(policy, "_shop", return_value="{a-test\\r") as selector:
            self.assertEqual(policy._town_producer_entry(
                RUNG, lambda: policy._atomic_shop_transaction_key(snap), family="store-router"), "{a-test\\r")
        selector.assert_called_once()
        self.assertEqual(policy._decision_terminal_admissions, [])

    def test_repeated_material_and_intent_reads_are_pure(self):
        for at_entrance in (False, True):
            policy, snap = page_board(at_entrance=at_entrance)
            before = pickle.dumps(vars(policy))
            terminal = tt.rung_terminal(policy, RUNG, snap)
            material = tt.gather_shop_page(policy, snap)
            self.assertEqual(tt.rung_terminal(policy, RUNG, snap), terminal)
            self.assertEqual(tt.gather_shop_page(policy, snap), material)
            self.assertEqual(tt.verdict_shop_page(material).admitted, at_entrance)
            self.assertEqual(pickle.dumps(vars(policy)), before)


class StoreOperationAdmissionTest(unittest.TestCase):
    def test_restock_direct_route_cannot_bypass_the_supplier_verdict(self):
        for reachable in (False, True):
            snap = board()
            policy = policy_on(snap)
            policy._town_errand_plan = SimpleNamespace(
                need_categories={STORE_GENERAL: ("food",)})
            origin = snap.player.position
            step = type(origin)(origin.y, origin.x + 1)

            def choose_step(*args, **kwargs):
                policy._shopping_approach_store_type = STORE_GENERAL
                policy._shopping_approach_goal = step
                return step

            with patch.object(policy, "_food_ready", return_value=True), \
                    patch.object(policy, "_shopping_approach_step", side_effect=choose_step), \
                    patch.object(policy, "_town_need_supplier_reachable", return_value=reachable):
                key = policy._town_producer_entry(
                    "_released_restock_store_key",
                    lambda: policy._released_restock_store_key(snap, (STORE_GENERAL,)),
                    family="store-router")
            self.assertEqual(key is not None, reachable)
            if not reachable:
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["codes"], ["supplier-unreachable"])
                self.assertEqual(row["rung"], "_shopping_approach_key")

    def test_staged_tail_waits_for_its_matching_fresh_page(self):
        for fresh in (False, True):
            snap = board()
            policy = policy_on(snap)
            policy._store_visit = SimpleNamespace(
                operation_posted=True, operation_released=False,
                operation_key="purchase", store_type=STORE_GENERAL,
                posted_turn=snap.turn)
            if fresh:
                snap = replace(snap, store=StoreState(STORE_GENERAL, []))
            policy._begin_map_predicate_cache(snap)
            with patch.object(policy, "_release_staged_store_operation", return_value="tail") as body:
                key = policy._town_producer_entry(
                    "_release_staged_store_operation",
                    lambda: policy._release_staged_store_operation(snap), family="store-router")
            self.assertEqual(key, "tail" if fresh else None)
            self.assertEqual(body.call_count, int(fresh))
            self.assertFalse(policy._store_visit.operation_released)
            if not fresh:
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["codes"], ["store-page-not-fresh"])

    def test_sale_refusal_keeps_the_leave_key_and_confirmation(self):
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        for missing, rejected in ((True, False), (False, True), (False, False)):
            outcomes = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                snap = replace(board(), inventory=[] if missing else [target],
                               store=StoreState(STORE_GENERAL, []))
                policy = policy_on(snap)
                policy._overweight_surplus_disposal = {"pending": {
                    "identity": policy._sale_item_identity(target),
                    "signature": policy._item_signature(target)}}
                if rejected:
                    policy._unsellable_items.add(policy._item_signature(target))
                with patch.dict(tt.TERMINALS, {"_store_sell_key":
                        tt.TERMINALS["_store_sell_key"]._replace(mode=mode)}), \
                        patch.object(policy, "_store_sell_key", wraps=policy._store_sell_key) as body:
                    key = policy._town_producer_entry(
                        "_store_sell_key", lambda: policy._store_sell_key(snap, target, "sale"),
                        family="shop-sell")
                self.assertEqual(key, LEAVE_STORE_KEY)
                self.assertEqual(body.call_count, int(mode == tt.SHADOW))
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["codes"], ["sale-item-unavailable" if missing else "sale-not-accepted"])
                outcomes.append((key, policy.last_reason, policy._unsellable_items,
                                 policy._last_sell_sig, policy._store_sell_stuck_count,
                                 repr(policy._decision_offer_buffer())))
            self.assertEqual(outcomes[0], outcomes[1])

    def test_admitted_sale_keeps_the_real_body_and_its_operation(self):
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        snap = replace(board(), inventory=[target], store=StoreState(STORE_ALCHEMIST, []))
        policy = policy_on(snap)
        policy._overweight_surplus_disposal = {"pending": {
            "identity": policy._sale_item_identity(target),
            "signature": policy._item_signature(target)}}
        with patch.object(policy, "_batch_sell_key", return_value="sale") as composer:
            self.assertEqual(policy._town_producer_entry(
                "_store_sell_key", lambda: policy._store_sell_key(snap, target, "sale"),
                family="shop-sell"), "sale")
        composer.assert_called_once_with(snap, [target])
        self.assertEqual(policy._decision_terminal_admissions, [])
        self.assertIsNotNone(policy._store_sell_attempt)

    def test_sale_and_staged_material_reads_do_not_confirm_operations(self):
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        snap = replace(board(), inventory=[target], store=StoreState(STORE_ALCHEMIST, []))
        policy = policy_on(snap)
        policy._overweight_surplus_disposal = {"pending": {
            "identity": policy._sale_item_identity(target),
            "signature": policy._item_signature(target)}}
        policy._store_visit = SimpleNamespace(
            operation_posted=True, operation_released=False, operation_key="purchase",
            store_type=STORE_ALCHEMIST, posted_turn=snap.turn)
        before = pickle.dumps(vars(policy))
        for _ in range(2):
            sale = tt.gather_store_sale(policy, snap)
            staged = tt.gather_staged_store(policy, snap)
            self.assertTrue(tt.verdict_store_sale(sale).admitted)
            self.assertTrue(tt.verdict_staged_store(staged).admitted)
            self.assertEqual(tt.store_sale_intended_terminal(policy, snap),
                             tt.TerminalRef("store-sell", (policy._item_signature(target),)))
            self.assertEqual(tt.staged_store_intended_terminal(policy, snap),
                             tt.TerminalRef("staged-store-operation", (STORE_ALCHEMIST, "purchase")))
            self.assertEqual(pickle.dumps(vars(policy)), before)

    def test_route_intent_and_material_are_repeatable_without_a_visit(self):
        snap = board()
        policy = policy_on(snap)
        policy._shopping_approach_store_type = STORE_GENERAL
        policy._town_errand_plan = SimpleNamespace(
            need_categories={STORE_GENERAL: ("food",)})
        before = pickle.dumps(vars(policy))
        materials = tt.gather_store_route(policy, snap)
        terminal = tt.shopping_intended_terminal(policy, snap)
        self.assertEqual(terminal, tt.TerminalRef("store-route", (STORE_GENERAL, ("food",))))
        admission = tt.verdict_store_route(materials)
        self.assertEqual(tt.gather_store_route(policy, snap), materials)
        self.assertEqual(tt.shopping_intended_terminal(policy, snap), terminal)
        self.assertEqual(tt.verdict_store_route(materials), admission)
        self.assertEqual(pickle.dumps(vars(policy)), before)


if __name__ == "__main__":
    unittest.main()
