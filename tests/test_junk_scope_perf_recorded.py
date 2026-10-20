"""The junk predicate's cost on a recorded Home-heavy board (#95).

Step 1a (``_junk_class``) made the post-purchase Home decision of
``home-deposit-hang-20261004.json.gz`` about 1.4x slower in the merge gate:
the board gates (retention, ownership, the live purchase ladder) ran for every
one of the 240 Home wares, and each purchase ladder recomputed the supply
ledger once per rung.  The fix keeps every answer and changes only the cost:

* the item's own class is decided first; a ware without one never reaches the
  board gates;
* one ``_junk_class`` evaluation, and the whole Home-full junk scan, compute
  each board's supply ledger once (``supply_ledger_observer_memo``, shared by
  nested blocks).

Recorded input: ``home-deposit-hang-20261004.json.gz`` (restored exactly as
tests/test_home_deposit_hang_recorded.py restores it).  Nothing is constructed.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import unittest
from collections import Counter
from unittest.mock import patch

from hengbot.model import InventoryItem
from hengbot.policy import HengbotPolicy
from test_home_deposit_hang_recorded import restore


def _shelf(policy):
    return [item if isinstance(item, InventoryItem)
            else policy._inventory_item_from_store_item(item)
            for item in policy._home_knowledge_items]


class JunkScopePerfRecordedTest(unittest.TestCase):
    def test_a_ware_without_a_junk_class_never_consults_the_purchase_ladder(self):
        policy, snapshot = restore()
        shelf = _shelf(policy)
        consulted = []
        original = HengbotPolicy._item_is_procurement_protected

        def recording(self, board, item):
            consulted.append(item)
            return original(self, board, item)

        with patch.object(HengbotPolicy, "_item_is_procurement_protected", recording):
            classes = [(item, policy._junk_class(snapshot, item)) for item in shelf]
        # A ware with no class of its own: none without a board, and not of
        # the kinds whose class depends on the character (books, ammunition).
        plain = [item for item, _junk in classes
                 if policy._junk_class(None, item) is None
                 and not item.is_spellbook and not item.is_ammo]
        junk = [item for item, junk in classes if junk is not None]
        self.assertEqual(len(shelf), 240)
        self.assertGreater(len(plain), 0)
        self.assertGreater(len(junk), 0)
        consulted_ids = {id(item) for item in consulted}
        self.assertEqual([item.name for item in plain if id(item) in consulted_ids], [])
        # Control: a ware that has a class still passes the ownership gates.
        self.assertEqual([item.name for item in junk if id(item) not in consulted_ids], [])

    def test_one_junk_class_computes_its_board_ledger_once(self):
        policy, snapshot = restore()
        item = next(item for item in _shelf(policy)
                    if policy._junk_class(None, item) == "harmful-consumable")
        boards = []
        original = HengbotPolicy._compute_supply_ledger

        def recording(self, board, depth):
            boards.append(id(board))
            return original(self, board, depth)

        with patch.object(HengbotPolicy, "_compute_supply_ledger", recording):
            self.assertEqual(policy._junk_class(snapshot, item), "harmful-consumable")
        self.assertEqual(boards, [id(snapshot)])

    def test_home_full_junk_scan_computes_each_board_ledger_once(self):
        policy, snapshot = restore()
        boards = []
        scanning = []
        compute = HengbotPolicy._compute_supply_ledger
        candidate = HengbotPolicy._home_full_discard_candidate

        def recording_compute(self, board, depth):
            if scanning:
                boards.append(id(board))
            return compute(self, board, depth)

        def recording_candidate(self, board, item, **kwargs):
            scanning.append(item)
            try:
                return candidate(self, board, item, **kwargs)
            finally:
                scanning.pop()

        with patch.object(HengbotPolicy, "_compute_supply_ledger", recording_compute), \
                patch.object(HengbotPolicy, "_home_full_discard_candidate", recording_candidate):
            policy.choose_key(snapshot)
        # Control: the recorded decision is unchanged and the scan ran over
        # several junk wares, each on its own probe board.
        self.assertEqual(policy.last_reason, "home:full-queue-surplus-withdraw")
        self.assertGreater(len(set(boards)), 1)
        self.assertEqual([board for board, count in Counter(boards).items() if count > 1], [])


if __name__ == "__main__":
    unittest.main()
