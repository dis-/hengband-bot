"""Home dispatch keeps observations while the actual operation asks admission."""
import tests  # noqa: F401

from dataclasses import replace
import pickle
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import STORE_GENERAL, STORE_HOME, StoreState, TVAL_SCROLL, SV_SCROLL_IDENTIFY
from hengbot.policy_constants import LEAVE_STORE_KEY
from hengbot.policy_state import normalize_policy_state
from hengbot.home_visit import HomeVisitKind, HomeVisitRequest
from hengbot.item_reservation import ITEM_RESERVATION_SOURCES
from policy_fixtures import grid, item
import test_policy_home as home_fixtures
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


KNOWLEDGE = {
    "_home_catalogue_work_key", "_home_full_knowledge_key", "home-errand-knowledge",
    "home-full-knowledge", "home-knowledge-after-exit",
}


class HomeAdmissionTest(unittest.TestCase):
    def test_scoped_operation_contexts_are_registered_as_nonexclusive_selection(self):
        for field in ("_terminal_home_take", "_terminal_store_sale"):
            self.assertEqual(ITEM_RESERVATION_SOURCES[field][0], "selection")

    def test_atomic_surface_refusal_preserves_the_exact_no_step_offer(self):
        for blocked in ("surface", "entrance"):
            outcomes = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                snap = board()
                policy = policy_on(snap)
                policy._shopping_approach_store_type = STORE_GENERAL if blocked == "surface" else STORE_HOME
                with patch.dict(tt.TERMINALS, {"home-atomic-withdraw":
                        tt.TERMINALS["home-atomic-withdraw"]._replace(mode=mode)}), \
                        patch.object(policy, "_atomic_home_withdraw_dispatch_key",
                                     wraps=policy._atomic_home_withdraw_dispatch_key) as body:
                    self.assertIsNone(policy._atomic_home_withdraw_key(snap, snap.player.position))
                self.assertEqual(body.call_count, int(mode == tt.SHADOW))
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["codes"], ["wrong-surface-or-pending" if blocked == "surface"
                                                else "not-at-home-entrance"])
                self.assertEqual(row["live"], [])
                self.assertEqual(row["mode"], mode)
                self.assertIsNone(policy._home_atomic_withdraw_pending)
                outcomes.append((policy.last_reason, repr(policy._decision_offer_buffer())))
            self.assertEqual(outcomes[0], outcomes[1])

    def test_home_entrance_admits_the_actual_dispatch(self):
        snap = board()
        pos = snap.player.position
        snap = replace(snap, grids={pos: replace(grid(pos.y, pos.x), store_number=STORE_HOME)})
        policy = policy_on(snap)
        policy._shopping_approach_store_type = STORE_HOME
        before = pickle.dumps(vars(policy))
        for _ in range(2):
            material = tt.gather_home_atomic_withdraw(policy, snap)
            self.assertTrue(tt.verdict_home_atomic_withdraw(material).admitted)
            self.assertEqual(tt.rung_terminal(policy, "home-atomic-withdraw", snap),
                             tt.TerminalRef("home-atomic-withdraw", ()))
            self.assertEqual(pickle.dumps(vars(policy)), before)
        with patch.object(policy, "_atomic_home_withdraw_dispatch_key", return_value="take") as body:
            self.assertEqual(policy._atomic_home_withdraw_key(snap, pos), "take")
        body.assert_called_once_with(snap, pos)

    def test_knowledge_entries_and_reactive_dispatch_are_never_refused(self):
        snap = board()
        for name in KNOWLEDGE | {"_home_full_relief_key", "_home_rearm_key"}:
            policy = policy_on(snap)
            terminal = tt.rung_terminal(policy, name, snap)
            self.assertEqual(terminal.terminal_id, tt.NO_REFUSAL)
            self.assertTrue(tt.terminal_admission(policy, snap, terminal).admitted)
            self.assertEqual(tt.TERMINALS[name].mode,
                             tt.NO_REFUSAL if name in KNOWLEDGE else tt.ENFORCE)
            self.assertNotIn(name, tt.SHADOW_RUNGS)
            self.assertEqual(policy._town_producer_entry(
                name, lambda: "observe", family="home-scan" if name in KNOWLEDGE else "home-visit"), "observe")
            self.assertEqual(policy._decision_terminal_admissions, [])

    def test_scoped_sale_refuses_the_callers_item_and_preserves_its_leave_reason(self):
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        for missing in (False, True):
            outcomes = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                snap = replace(board(), inventory=[] if missing else [target],
                               store=StoreState(STORE_GENERAL, []))
                policy = policy_on(snap)
                policy._unsellable_items.add(policy._item_signature(target))
                with patch.dict(tt.TERMINALS, {"_store_sell_key":
                        tt.TERMINALS["_store_sell_key"]._replace(mode=mode)}), \
                        patch.object(policy, "_store_sell_key", wraps=policy._store_sell_key) as body:
                    key = policy._store_sale_entry_key(snap, target, "sale",
                        rejected_reason="shop:unsellable-home-full-surplus-sale-refused")
                self.assertEqual(body.call_count, int(mode == tt.SHADOW))
                self.assertEqual(key, LEAVE_STORE_KEY)
                self.assertIsNone(policy._terminal_store_sale)
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["codes"], ["sale-item-unavailable" if missing else "sale-not-accepted"])
                outcomes.append((key, policy.last_reason, policy._last_sell_sig,
                                 policy._store_sell_stuck_count, repr(policy._decision_offer_buffer())))
            self.assertEqual(outcomes[0], outcomes[1])

    def test_sale_context_is_restored_on_exception_and_old_checkpoints_default_it(self):
        snap = board()
        policy = policy_on(snap)
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        previous = ("outer",)
        policy._terminal_store_sale = previous
        with patch.object(policy, "_town_producer_entry", side_effect=RuntimeError("sale failed")):
            with self.assertRaisesRegex(RuntimeError, "sale failed"):
                policy._store_sale_entry_key(snap, target, "sale")
        self.assertIs(policy._terminal_store_sale, previous)
        del policy.__dict__["_terminal_store_sale"]
        self.assertIsNone(normalize_policy_state(policy)._terminal_store_sale)

    def test_actual_take_refuses_an_unobserved_target_and_admits_the_observed_control(self):
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        for present in (False, True):
            snap = board()
            policy = policy_on(snap)
            policy._home_knowledge_items = (target,) if present else ()
            with patch("hengbot.policy_home.store_item_key", return_value="take") as composer:
                key = policy._home_take_entry_key(snap, target, "home-errand", 1, "a")
            self.assertEqual(key, "take" if present else None)
            self.assertEqual(composer.call_count, int(present))
            self.assertIsNone(policy._terminal_home_take)
            if not present:
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["terminal"][0], "home-take")
                self.assertEqual(row["codes"], ["reservation-unavailable"])
        policy._terminal_home_take = (target, "home-errand", 1, "a")
        before = pickle.dumps(vars(policy))
        first = tt.gather_home_take(policy, snap)
        self.assertEqual(tt.gather_home_take(policy, snap), first)
        self.assertEqual(pickle.dumps(vars(policy)), before)

    def test_take_context_restores_on_exception_and_defaults_on_restore(self):
        snap = board()
        policy = policy_on(snap)
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        with patch.object(policy, "_town_producer_entry", side_effect=RuntimeError("take failed")):
            with self.assertRaisesRegex(RuntimeError, "take failed"):
                policy._home_take_entry_key(snap, target, "home-errand", 1, "a")
        self.assertIsNone(policy._terminal_home_take)
        del policy.__dict__["_terminal_home_take"]
        self.assertIsNone(normalize_policy_state(policy)._terminal_home_take)

    def test_relief_sale_uses_its_target_admission_without_losing_its_dispatch(self):
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True,
                      fully_known=True)
        outcomes = []
        for mode in (tt.SHADOW, tt.ENFORCE):
            snap = replace(board(), inventory=[target], store=StoreState(STORE_GENERAL, []))
            policy = policy_on(snap)
            policy._home_full_relief = {
                "town": policy._effective_town_id(snap),
                "sale": (policy._item_signature(target), STORE_GENERAL, 0),
                "withdrawn": True, "mode": "sale"}
            with patch.dict(tt.TERMINALS, {"_store_sell_key":
                    tt.TERMINALS["_store_sell_key"]._replace(mode=mode)}), \
                    patch.object(policy, "_retention_reservation", return_value=0), \
                    patch.object(policy, "_disposal_protected_by_identification", return_value=False), \
                    patch.object(policy, "_store_accepts_sale", return_value=False):
                key = policy._town_producer_entry(
                    "_home_full_relief_key", lambda: policy._home_full_relief_key(snap), family="home-visit")
            self.assertEqual(key, LEAVE_STORE_KEY)
            row, = policy._decision_terminal_admissions
            self.assertEqual(row["rung"], "_store_sell_key")
            self.assertEqual(row["codes"], ["sale-not-accepted"])
            outcomes.append((key, policy.last_reason, policy._unsellable_items,
                             policy._home_full_relief, repr(policy._decision_offer_buffer())))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_dispatch_cannot_bypass_the_final_take_verdict(self):
        fixture = home_fixtures.HomeOneOperationPerEntryTest()
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        snap = fixture._entrance_snapshot([])
        for available in (False, True):
            policy = fixture._catalogued_withdrawal_policy([target])
            policy._home_pending_item = policy._item_signature(target)
            policy._begin_map_predicate_cache(snap)
            with patch.object(tt, "gather_home_take", return_value=tt.HomeWithdrawMaterial(True, available)):
                key = policy._atomic_home_withdraw_key(snap, snap.player.position)
            self.assertEqual(key is not None, available)
            self.assertEqual(policy._home_atomic_withdraw_pending is not None, available)
            self.assertIsNone(policy._terminal_home_take)
            if not available:
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["terminal"][0], "home-take")
                self.assertEqual(row["codes"], ["reservation-unavailable"])

    def test_relief_retry_walk_cannot_bypass_the_withdrawal_admission(self):
        self._assert_relief_route_refused(retry=True)

    def test_relief_surplus_walk_cannot_bypass_the_withdrawal_admission(self):
        self._assert_relief_route_refused(retry=False)

    def _assert_relief_route_refused(self, *, retry):
        snap = board()
        policy = policy_on(snap)
        target = item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify", known=True)
        signature = policy._item_signature(target)
        if retry:
            policy._home_full_retry_deposits = ((signature, 1, 1),)
        else:
            policy._home_full_relief = {
                "town": policy._effective_town_id(snap), "sale": (signature, STORE_GENERAL, 0),
                "withdrawn": False, "mode": "sale"}
        policy._home_knowledge_current = True
        policy._home_visit.file(HomeVisitRequest(
            HomeVisitKind.WITHDRAW, "home-visit", signature, address=signature))

        def route(*args, **kwargs):
            policy._shopping_approach_store_type = STORE_HOME
            return snap.player.position

        with patch.object(policy, "_find_home_deposit", return_value=target), \
                patch.object(policy, "_ensure_home_visit_request", return_value=True), \
                patch.object(policy, "_shopping_approach_step", side_effect=route):
            key = policy._town_producer_entry(
                "_home_full_relief_key", lambda: policy._home_full_relief_key(snap), family="home-visit")
        self.assertIsNone(key)
        row, = policy._decision_terminal_admissions
        self.assertEqual(row["rung"], "_shopping_approach_key")
        self.assertEqual(row["codes"], ["reservation-unavailable"])


if __name__ == "__main__":
    unittest.main()
