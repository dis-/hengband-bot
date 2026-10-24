"""The route projection uses supplier and withdrawal admissions before walking."""

import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.model import (STORE_HOME, STORE_TEMPLE, StoreItem, StoreState,
                           TVAL_POTION, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownNeed, TownErrandPlan
from hengbot import town_terminal
import test_town_terminal_n1a_recorded as n1a


class PlanAdmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        n1a.N1aTerminalAdmissionTest.setUpClass()
        cls.board = replace(n1a.N1aTerminalAdmissionTest.boards[1], player=replace(
            n1a.N1aTerminalAdmissionTest.boards[1].player, gold=51))

    def policy(self):
        return n1a.N1aTerminalAdmissionTest().policy(self.board)

    def test_no_matching_offer_is_not_a_plan_stop(self):
        policy = self.policy()
        policy._town_store_attempted[STORE_TEMPLE] = 1
        policy._town_supplier_stock[STORE_TEMPLE] = StoreState(STORE_TEMPLE, [
            StoreItem("a", "potion", 5, TVAL_POTION, 0, 20)])
        need = TownNeed(STORE_TEMPLE, "recall", "normal")
        with patch.object(HengbotPolicy, "_town_need_supplier_reachable", return_value=True):
            self.assertIsNone(policy._build_town_errand_plan(self.board, [need]))
            # A matching affordable ware restores this supplier.
            policy._town_supplier_stock[STORE_TEMPLE] = StoreState(STORE_TEMPLE, [
                StoreItem("a", "recall", 5, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, 40)])
            self.assertEqual(policy._build_town_errand_plan(self.board, [need]).stops,
                             [STORE_TEMPLE])

    def test_unknown_and_unreachable_store_controls(self):
        policy = self.policy()
        need = TownNeed(STORE_TEMPLE, "recall", "normal")
        with patch.object(HengbotPolicy, "_town_need_supplier_reachable", return_value=True):
            self.assertEqual(policy._build_town_errand_plan(self.board, [need]).stops,
                             [STORE_TEMPLE])
        with patch.object(HengbotPolicy, "_town_need_supplier_reachable", return_value=False):
            self.assertIsNone(policy._build_town_errand_plan(self.board, [need]))

    def test_native_route_and_new_category_keep_the_router_rearm(self):
        policy = self.policy()
        need = TownNeed(STORE_TEMPLE, "recall", "normal")
        policy._town_store_attempted[STORE_TEMPLE] = self.board.turn
        with patch.object(HengbotPolicy, "_town_map_active", return_value=False), \
                patch.object(HengbotPolicy, "_town_need_supplier_reachable", return_value=False):
            self.assertEqual(policy._build_town_errand_plan(self.board, [need]).stops,
                             [STORE_TEMPLE])
            # An unchanged category on an attempted route is not fresh work.
            policy._town_errand_plan = TownErrandPlan(
                [STORE_TEMPLE], need_categories={STORE_TEMPLE: ("recall",)})
            self.assertIsNone(policy._build_town_errand_plan(self.board, [need]))
            # Strict supplier counting has no native-route fallback.
            self.assertFalse(town_terminal.verdict_store_buy(
                town_terminal.gather_store_buy(policy, self.board, need)).admitted)

    def test_missing_withdrawal_is_refused_before_visit_filing(self):
        policy = self.policy()
        target = ("missing-reserved-item",)
        policy._home_pending_item = target
        policy._home_knowledge_current = True
        policy._home_knowledge_items = ()
        need = TownNeed(STORE_HOME, "identification-withdrawal", "home-first")
        with patch.object(HengbotPolicy, "_town_need_supplier_reachable", return_value=True):
            self.assertIsNone(policy._build_town_errand_plan(self.board, [need]))
            self.assertIsNone(policy._home_visit.request)
            self.assertIsNone(policy._store_visit)
            # An unknown catalogue is still allowed its observation visit.
            policy._home_knowledge_current = False
            self.assertEqual(policy._build_town_errand_plan(self.board, [need]).stops,
                             [STORE_HOME])

    def test_home_without_withdrawal_does_not_need_a_stored_target(self):
        policy = self.policy()
        policy._home_pending_item = None
        policy._home_pending_batch = []
        policy._home_knowledge_current = False
        need = TownNeed(STORE_HOME, "home-scan", "home-first")
        with patch.object(HengbotPolicy, "_town_need_supplier_reachable", return_value=True):
            self.assertEqual(policy._build_town_errand_plan(self.board, [need]).stops,
                             [STORE_HOME])


if __name__ == "__main__":
    unittest.main()
