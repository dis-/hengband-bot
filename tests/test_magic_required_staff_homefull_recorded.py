"""Pin required Identify staff purchase on the captured Home-full Magic page."""

import json
from pathlib import Path
import unittest

import tests  # noqa: F401 -- isolate runtime files
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


FIXTURE = Path(__file__).parent / "fixtures" / "magic-homefull-required-identify-20261008.json"


def _captured_board():
    row = json.loads(FIXTURE.read_text(encoding="utf-8"))["board"]
    lore = {
        monster["race_id"]: MonraceKnowledge(10, 110, False, False)
        for monster in row.get("visible_monsters", []) + row.get("detected_monsters", [])
    }
    return parse_snapshot(row, lore)


class RequiredStaffHomeFullRecordedTest(unittest.TestCase):
    def test_required_staff_is_bought_while_reserved_sale_is_skipped(self):
        board = _captured_board()
        policy = HengbotPolicy()
        policy.prime(board)
        policy._in_store_ops_enabled = True
        policy.observe_store_screen(True)
        policy._store_visit = StoreVisit(
            "town-errand", "shopping", board.store.store_type,
            StoreVisitPhase.LEAVING, opened_sequence=18,
            posted_sequence=20, posted_turn=board.turn,
        )

        reserved_sale = next(
            item for item in board.inventory
            if item.tval == 55 and item.sval == 5 and item.charges == 0
        )
        # DECLARED CONSTRUCTED: assign this captured sale candidate to the
        # Home-full retry owner recorded in the live selector-skip telemetry.
        policy._home_full_retry_deposits = (
            (policy._item_signature(reserved_sale), 1, 1),
        )

        # Captured board: 0/20 Identify charges, wanted shelf row i has 21
        # charges for 851 gold, and the player has 13,695 gold.
        self.assertEqual(policy._total_identify_staff_charges(board), 0)
        wanted = next(
            item for item in board.store.items
            if item.tval == 55 and item.sval == 5 and item.charges == 21
        )
        self.assertEqual((wanted.letter, wanted.price, wanted.charges), ("i", 851, 21))
        self.assertGreaterEqual(board.player.gold, 851)
        self.assertIsNone(policy._find_device_sale(board))

        key = policy._in_store_try_start(board)

        self.assertEqual((key, policy.last_reason), ("pi\r", "shop:in-store-buy"))
        self.assertEqual(policy._in_store_entry_ledger["pending"]["kind"], "buy")
        self.assertEqual(policy._store_visit.phase, StoreVisitPhase.OPERATING)


if __name__ == "__main__":
    unittest.main()
