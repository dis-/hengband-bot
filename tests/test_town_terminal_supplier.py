"""ROOT-FIX S2: the store-buy verdict (design 3.4 S2 rows) and the
departure supplier counting through it (design 3.6 item 2, S type #66 #68 #94).

Boards are the recorded n1a boards (test_town_terminal_n1a_recorded), in town
with the town map.  The departure-blocking need is constructed (recall at the
Temple, the c4-a life-016 shape: the Temple attempted, recall unaffordable).
"""

import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import town_terminal
from hengbot.model import STORE_TEMPLE, StoreItem, StoreState, TVAL_POTION, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownNeed
import test_town_terminal_n1a_recorded as n1a

RECALL = TownNeed(STORE_TEMPLE, "recall", "normal")


class DepartureSupplierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        n1a.N1aTerminalAdmissionTest.setUpClass()
        cls.board = replace(n1a.N1aTerminalAdmissionTest.boards[1], player=replace(
            n1a.N1aTerminalAdmissionTest.boards[1].player, gold=51))

    def supplier(self, ware):
        policy = n1a.N1aTerminalAdmissionTest().policy(self.board)
        policy._town_store_attempted[STORE_TEMPLE] = 1
        policy._town_supplier_stock[STORE_TEMPLE] = StoreState(STORE_TEMPLE, [ware])
        with patch.object(HengbotPolicy, "_departure_blocking_town_needs",
                          side_effect=lambda _board: [RECALL]),                 patch.object(HengbotPolicy, "_supply_ledger", return_value={}),                 patch.object(HengbotPolicy, "_ledger_departure_shortages", return_value=[]):
            return policy._departure_supplier_core(self.board)

    def test_affordable_other_ware_is_not_a_recall_supplier(self):
        potion = StoreItem("a", "cheap potion", 5, TVAL_POTION, 0, 20)
        self.assertEqual(self.supplier(potion), (None, False))

    def test_control_affordable_recall_is_a_supplier(self):
        recall = StoreItem("a", "recall", 5, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, 40)
        self.assertEqual(self.supplier(recall), (STORE_TEMPLE, False))


class StoreBuyVerdictTest(unittest.TestCase):
    def material(self, ware, *, attempted=True, gold=500):
        policy = HengbotPolicy()
        if attempted:
            policy._town_store_attempted[STORE_TEMPLE] = 1
        policy._town_supplier_stock[STORE_TEMPLE] = StoreState(STORE_TEMPLE, [ware])
        board = n1a.N1aTerminalAdmissionTest.boards[1]
        board = replace(board, player=replace(board.player, gold=gold))
        with patch.object(HengbotPolicy, "_town_need_supplier_reachable", return_value=True):
            return town_terminal.gather_store_buy(
                policy, board, TownNeed(STORE_TEMPLE, "recall", "normal"))

    @classmethod
    def setUpClass(cls):
        n1a.N1aTerminalAdmissionTest.setUpClass()

    def test_affordable_other_ware_is_no_recall_supplier(self):
        potion = StoreItem("a", "cheap potion", 5, TVAL_POTION, 0, 20)
        self.assertEqual(town_terminal.verdict_store_buy(self.material(potion)),
                         town_terminal.refused(("no-matching-offer",)))

    def test_control_affordable_recall_and_unattempted_store_admit(self):
        recall = StoreItem("a", "recall", 5, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, 150)
        self.assertTrue(town_terminal.verdict_store_buy(self.material(recall)).admitted)
        potion = StoreItem("a", "cheap potion", 5, TVAL_POTION, 0, 20)
        self.assertTrue(town_terminal.verdict_store_buy(
            self.material(potion, attempted=False)).admitted)

    def test_store_buy_codes_are_declared_without_a_town_server(self):
        # No town owner serves a supplier that cannot serve the need: the
        # refused supplier is simply not counted (design 3.4 S2 rows).
        for code in town_terminal.STORE_BUY_CODES:
            self.assertEqual(town_terminal.REFUSAL_SERVERS[code], (), code)
            self.assertEqual(town_terminal.declared_code(code), code)

    def test_unreachable_supplier_is_refused(self):
        self.assertEqual(town_terminal.verdict_store_buy(town_terminal.StoreBuyMaterial(
            STORE_TEMPLE, reachable=False, home=False, attempted=False, page_offers=True)),
            town_terminal.refused(("supplier-unreachable",)))


if __name__ == "__main__":
    unittest.main()
