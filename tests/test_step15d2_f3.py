"""Step 1.5d2 F3 release, relief-yield, and empty-staff pins."""

from __future__ import annotations

import json
import unittest
import tests
from dataclasses import replace
from pathlib import Path

from hengbot.model import (
    STORE_ALCHEMIST, STORE_ARMOURY, STORE_GENERAL, STORE_MAGIC, STORE_TEMPLE,
    STORE_WEAPON, SV_STAFF_IDENTIFY, TVAL_STAFF,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from policy_fixtures import item
from test_step15d2_f2 import _board


class Step15d2F3Test(unittest.TestCase):
    def _required_board(self):
        board = _board("step1.5d2-224534-shelf.json")
        policy = HengbotPolicy()
        policy._observe(board)
        policy._build_grid_index(board)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        return policy, board

    def test_same_entry_after_sale_selects_required_buy_before_other_work(self):
        policy, board = self._required_board()
        # DECLARED CONSTRUCTED: confirmed release sale on a fresh page of the
        # 224534 supplier boundary; one earlier entry operation is observed.
        policy._in_store_entry_ledger = {
            "store": STORE_MAGIC, "opened_sequence": 4,
            "ops": 1, "pending": None, "ended": False,
        }
        policy._store_visit = StoreVisit(
            "shop-buy", "identify-staff", STORE_MAGIC,
            phase=StoreVisitPhase.OPERATING, opened_sequence=4,
        )
        selection = policy._in_store_selection(board)
        self.assertEqual(selection["op"], "buy")
        self.assertEqual(selection["letter"], "o")

    def test_cap_page_operation_is_release_sale_then_strictly_fuller_buy(self):
        policy, board = self._required_board()
        policy._deepest_level = 44
        carried = tuple(
            item(chr(ord("a") + index), TVAL_STAFF, SV_STAFF_IDENTIFY,
                 charges=charge, pval=charge)
            for index, charge in enumerate((1, 4, 5, 5))
        )
        cap_board = replace(board, inventory=carried)
        self.assertIsNone(policy._departure_blocking_page_purchase(cap_board))
        operation = policy._departure_blocking_page_operation(cap_board)
        self.assertEqual(operation["op"], "release-sale")
        self.assertEqual(operation["item"].slot, "a")
        self.assertGreater(
            max(operation["purchase"].item.charges,
                operation["purchase"].item.pval),
            max(operation["item"].charges, operation["item"].pval),
        )

    def test_unsellable_empty_staff_remains_a_destroy_candidate(self):
        policy, board = self._required_board()
        policy._deepest_level = 30
        empty = item("j", TVAL_STAFF, SV_STAFF_IDENTIFY,
                     charges=0, pval=0, name="Staff of Identify")
        outside = replace(board, store=None)
        policy._store_sale_refused.update({
            STORE_ALCHEMIST, STORE_ARMOURY, STORE_GENERAL, STORE_MAGIC,
            STORE_TEMPLE, STORE_WEAPON,
        })
        self.assertIsNone(policy._home_full_sale_candidate(outside, empty))
        self.assertIsNotNone(policy._home_full_discard_candidate(outside, empty))

    def test_relief_yields_entire_dispatch_while_required_buy_is_pending(self):
        policy, board = self._required_board()
        # DECLARED CONSTRUCTED: 040900 S11 follow-up decision after relief
        # accounting, with a live same-entry purchase awaiting confirmation.
        policy._in_store_entry_ledger = {
            "store": STORE_MAGIC, "opened_sequence": 7, "ops": 0,
            "pending": {"kind": "buy", "sequence": 10}, "ended": False,
        }
        policy._store_visit = StoreVisit(
            "shop-buy", "identify-staff", STORE_MAGIC,
            phase=StoreVisitPhase.OPERATING, opened_sequence=7,
        )
        policy._in_store_screen_verified = True
        policy._home_full_relief = {
            "town": policy._effective_town_id(board), "sale": None,
            "withdrawn": False, "remaining": 1, "deposits": (),
            "skipped": {}, "skipped_home_counts": {},
        }
        policy._home_knowledge_current = False
        self.assertTrue(policy._home_full_relief_yields_to_store_operation(board))
        offers = len(policy._execution_offers_for())
        self.assertIsNone(policy._home_full_relief_key(board))
        self.assertFalse(policy._home_knowledge_current)
        self.assertEqual(len(policy._execution_offers_for()), offers)

    def test_entry_budget_stop_is_visible_and_keeps_the_existing_budget(self):
        policy, board = self._required_board()
        # DECLARED CONSTRUCTED from the 040322 release boundary: the same
        # entry has exhausted its eight operation budget while a required
        # replacement remains selectable on the fresh observed page.
        policy._in_store_entry_ledger = {
            "store": STORE_MAGIC, "opened_sequence": 9,
            "ops": 8, "pending": None, "ended": False,
        }
        policy._store_visit = StoreVisit(
            "shop-buy", "identify-staff", STORE_MAGIC,
            phase=StoreVisitPhase.OPERATING, opened_sequence=9,
        )
        policy._in_store_screen_verified = True
        key = policy._in_store_entry_key(board)
        self.assertEqual(key, "\x1b")
        self.assertEqual(
            policy.last_reason,
            "town:blocked:shop-required-operation-uncomposable",
        )
        self.assertEqual(policy._in_store_entry_ledger["ops"], 8)
        self.assertEqual(
            policy._shop_selector_diagnostics["required-page-continuation"]["cause"],
            "entry-budget",
        )

    def test_reconciled_014739_no_effect_sale_stops_without_retry(self):
        policy, board = self._required_board()
        # DECLARED CONSTRUCTED from 014739 S49: pending old input has been
        # reconciled, so operation_posted=False; the unchanged sale board has
        # no effect and a required page operation remains.
        policy._decision_sequence = 50
        policy._in_store_entry_ledger = {
            "store": STORE_MAGIC, "opened_sequence": 12, "ops": 1,
            "pending": {"kind": "sell", "sequence": 49}, "ended": False,
        }
        policy._store_visit = StoreVisit(
            "shop-buy", "identify-staff", STORE_MAGIC,
            phase=StoreVisitPhase.OPERATING, opened_sequence=12,
            operation_posted=False,
        )
        key = policy._in_store_entry_key(board)
        self.assertEqual(key, "\x1b")
        self.assertEqual(policy._in_store_entry_ledger["ops"], 1)
        self.assertEqual(
            policy._shop_selector_diagnostics["required-page-continuation"]["cause"],
            "sale-no-effect",
        )

    def test_charged_cap_take_rejected_but_empty_surplus_is_unrestricted(self):
        policy, board = self._required_board()
        policy._deepest_level = 30
        carried = tuple(
            item(chr(ord("a") + index), TVAL_STAFF, SV_STAFF_IDENTIFY,
                 charges=5, pval=5)
            for index in range(3)
        )
        unready = replace(board, inventory=carried)
        charged = item("j", TVAL_STAFF, SV_STAFF_IDENTIFY,
                       charges=1, pval=1, count=2)
        empty = item("k", TVAL_STAFF, SV_STAFF_IDENTIFY,
                     charges=0, pval=0, count=3)
        self.assertTrue(policy._home_full_relief_take_blocks_identify(
            unready, charged, 2
        ))
        self.assertFalse(policy._home_full_relief_take_blocks_identify(
            unready, empty, 3
        ))
        over_cap_items = tuple(
            item(chr(ord("a") + index), TVAL_STAFF, SV_STAFF_IDENTIFY,
                 charges=2, pval=2)
            for index in range(5)
        )
        self.assertTrue(policy._home_full_relief_take_blocks_identify(
            replace(board, inventory=over_cap_items), charged, 1
        ))
        for carried_count, quantity in ((2, 2), (3, 1)):
            board_items = tuple(
                item(chr(ord("a") + index), TVAL_STAFF, SV_STAFF_IDENTIFY,
                     charges=5, pval=5)
                for index in range(carried_count)
            )
            self.assertTrue(policy._home_full_relief_take_blocks_identify(
                replace(board, inventory=board_items), charged, quantity
            ))
        ready_items = tuple(
            item(chr(ord("a") + index), TVAL_STAFF, SV_STAFF_IDENTIFY,
                 charges=20, pval=20)
            for index in range(3)
        )
        self.assertFalse(policy._home_full_relief_take_blocks_identify(
            replace(board, inventory=ready_items), charged, 1
        ))

    def test_capacity_skip_reopens_only_after_count_or_readiness_changes(self):
        policy, board = self._required_board()
        policy._deepest_level = 30
        staff = item("a", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=4, pval=4)
        unready = replace(board, inventory=(staff,))
        # DECLARED CONSTRUCTED: a cap rejection is visit-local and keyed to
        # carried count plus readiness, not gold or decision turns.
        policy._home_full_relief = {
            "town": policy._effective_town_id(unready), "sale": None,
            "withdrawn": False, "remaining": 1, "deposits": (),
            "skipped": {}, "skipped_home_counts": {},
            "stock_count": 1,
        }
        empty = item("j", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=0, pval=0)
        policy._home_full_record_identify_cap_skip(unready, empty, 1)
        signature = policy._item_signature(empty)
        fingerprint = policy._home_full_relief["identify_cap_skip_fingerprint"][signature]
        self.assertEqual(fingerprint, (1, False, 1))
        ready_staff = replace(staff, charges=20, pval=20)
        ready = replace(unready, inventory=(ready_staff,))
        self.assertNotEqual(
            fingerprint[:2],
            (sum(x.count for x in policy._carried_identify_staves(ready)),
             bool(policy._identify_staff_ready(ready))),
        )

    def test_three_plus_one_and_four_plus_two_empty_staff_relief_is_queued(self):
        """3+1 primary pin; 184438 four+two state is separately constructed."""
        for carried_count, home_count in ((3, 1), (4, 2)):
            policy, board = self._required_board()
            policy._deepest_level = 30
            carried = tuple(
                item(chr(ord("a") + index), TVAL_STAFF, SV_STAFF_IDENTIFY,
                     charges=5, pval=5)
                for index in range(carried_count)
            )
            surplus = item("j", TVAL_STAFF, SV_STAFF_IDENTIFY,
                           charges=0, pval=0, count=home_count,
                           name="Staff of Identify")
            outside = replace(board, store=None, inventory=carried)
            # No supplier shelf offer exists in this constructed relief pin.
            policy._town_supplier_stock.clear()
            policy._town_supplier_stock_observations.clear()
            policy.consume_home_knowledge((surplus,))
            policy._home_full_relief = {
                "town": policy._effective_town_id(outside), "sale": None,
                "withdrawn": False, "remaining": 1, "deposits": (),
                "skipped": {}, "skipped_home_counts": {},
            }
            # DECLARED CONSTRUCTED primary 10-10 control: an empty Home staff
            # is surplus even when it temporarily fills or exceeds the cap.
            policy._home_full_relief_key(outside)
            self.assertEqual(policy._home_pending_item,
                             policy._item_signature(surplus))
            self.assertEqual(policy._home_pending_quantity, home_count)
            self.assertEqual(policy._home_full_relief["sale"][0],
                             policy._item_signature(surplus))


if __name__ == "__main__":
    unittest.main()
