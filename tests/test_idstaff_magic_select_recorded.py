from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import InventoryItem, SV_STAFF_IDENTIFY, TVAL_STAFF, parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "idstaff-magic-select-20261017.jsonl.gz"


class IdentifyStaffMagicSelectRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        cls.magic = parse_snapshot(rows[0], {})
        cls.home = parse_snapshot(rows[1], {})
        cls.decisions = [row for row in rows if "decision_sequence" in row]
        assert len(cls.decisions) == 1

    def _policy(self, board):
        policy = HengbotPolicy()
        policy.prime(board)
        # DECLARED CONSTRUCTED: the captured preceding Home scan (row 53,
        # source "~9", 95 items) established this catalogue before decision 4304.
        policy._home_knowledge_current = True
        policy._home_knowledge_items = tuple(
            InventoryItem(
                slot=item.letter,
                name=item.name,
                count=item.count,
                tval=item.tval,
                sval=item.sval,
                aware=item.aware,
                known=item.known,
                fully_known=item.fully_known,
                charges=max(item.charges, item.pval),
                pval=max(item.charges, item.pval),
            )
            for item in self.home.store.items
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
        )
        policy._home_scan_item_count = 95
        policy._home_scan_source = "~9"
        return policy

    def test_captured_magic_page_offers_worthwhile_swap_after_fix(self):
        recorded = self.decisions[0]
        self.assertEqual(recorded["decision_sequence"], 4304)
        self.assertEqual(recorded["reason"], "shop:observe-and-leave")
        self.assertIsNone(recorded["shop_selector"]["wanted_purchase"])
        self.assertEqual(
            recorded["shop_selector"]["rejection_reason"],
            "observed-page-nothing-wanted",
        )

        policy = self._policy(self.magic)
        staves = policy._carried_identify_staves(self.magic)
        self.assertEqual([(item.charges, item.count) for item in staves], [(4, 1), (3, 4)])
        self.assertEqual(policy._total_identify_staff_charges(self.magic), 16)
        self.assertEqual(policy._identify_staff_release_plan(self.magic), {"l": 1})
        self.assertTrue(policy._identify_staff_acquisition_worthwhile(self.magic, 13))
        self.assertTrue(policy._identify_staff_acquisition_worthwhile(self.magic, 12))

        operation = policy._departure_blocking_page_operation(self.magic)
        self.assertEqual(operation["op"], "release-sale")
        self.assertEqual((operation["item"].slot, operation["quantity"]), ("l", 2))
        purchase = operation["purchase"]
        self.assertEqual((purchase.item.sval, purchase.item.charges, purchase.item.price),
                         (SV_STAFF_IDENTIFY, 13, 794))
        self.assertEqual(policy._shop(self.magic), "{l@0\r")
        self.assertEqual(policy.last_reason, "shop:batch-inscribe")
        self.assertEqual(
            sum(item.count for item in staves)
            - operation["quantity"] + purchase.quantity,
            4,
        )
        after_release = replace(
            self.magic,
            inventory=tuple(
                replace(item, count=item.count - operation["quantity"])
                if item.slot == operation["item"].slot else item
                for item in self.magic.inventory
            ),
        )
        after_policy = self._policy(after_release)
        self.assertEqual(after_policy._shop(after_release), "pi\r")
        self.assertEqual(after_policy.last_reason, "shop:buy-device-food")

    def test_no_worthwhile_staff_still_leaves_selector_empty(self):
        items = [
            replace(item, charges=2, pval=2)
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
            else item
            for item in self.magic.store.items
        ]
        board = replace(self.magic, store=replace(self.magic.store, items=items))
        policy = self._policy(board)
        self.assertIsNone(policy._next_purchase(board))

    def test_unaffordable_staff_is_still_refused(self):
        items = [
            replace(item, price=6000)
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
            else item
            for item in self.magic.store.items
        ]
        board = replace(self.magic, store=replace(self.magic.store, items=items))
        policy = self._policy(board)
        self.assertIsNone(policy._next_purchase(board))


if __name__ == "__main__":
    unittest.main()
