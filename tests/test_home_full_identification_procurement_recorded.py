"""Captured 2026-10-08 Home-full identification-source stall.

The outside board is copied from the 01:58 autorecover state capture at the
source-unavailable decision. Home contents were not emitted in that capture,
so the 240-slot unknown-only catalogue is a declared construction preserving
the recorded Home-full condition and identify-first rule.
"""
import gzip
import json
from pathlib import Path
import unittest
from dataclasses import replace

import tests  # noqa: F401
from hengbot.model import (
    InventoryItem, STORE_HOME, STORE_MAGIC, STORE_WEAPON,
    SV_STAFF_IDENTIFY, TVAL_STAFF, parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import PACK_CAPACITY
from hengbot.policy_types import TownErrandPlan
from test_home_discard_incidents_recorded import PINS

BOARD = Path(__file__).parent / "fixtures/home-full-identification-procurement-20261008.json.gz"


class HomeFullIdentificationProcurementRecordedTest(unittest.TestCase):
    def recorded_board(self):
        raw = json.loads(gzip.decompress(BOARD.read_bytes()))
        raw.pop("visible_monsters", None)
        raw.pop("detected_monsters", None)
        return parse_snapshot(raw, monrace_knowledge={})

    def test_restored_destroy_wait_is_revalidated_against_the_board(self):
        board = self.recorded_board()
        policy = HengbotPolicy(monrace_knowledge={})
        target = board.inventory[0]
        policy._home_full_relief = {
            "deposits": ((policy._item_signature(target), target.count, target.count),),
            "remaining": 1, "sale": (policy._item_signature(target), STORE_HOME, 0),
            "withdrawn": True, "mode": "destroy", "destroy_posted": True,
            "destroy_before_count": 0, "town": policy._effective_town_id(board),
        }

        policy.prime(board)

        self.assertNotIn("destroy_posted", policy._home_full_relief)
        self.assertNotIn("destroy_before_count", policy._home_full_relief)
        self.assertTrue(policy._home_full_relief["withdrawn"])

    def test_no_legal_relief_defers_home_and_advances_the_recorded_plan(self):
        board = self.recorded_board()
        policy = HengbotPolicy(monrace_knowledge={})
        policy.prime(board)
        policy.consume_home_knowledge(())
        deposits = ((policy._item_signature(board.inventory[0]),
                     board.inventory[0].count, board.inventory[0].count),)
        policy._begin_home_full_relief(board, deposits, refused=True)
        policy._home_full_relief["skipped"] = {
            policy._item_signature(item): "recorded-protected"
            for item in board.inventory
        }
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_MAGIC, STORE_WEAPON], index=0,
        )

        key = policy._home_full_relief_key(board)

        self.assertIsNone(key)
        self.assertEqual(policy.last_reason,
                         "home:full-deposit-deferred-no-legal-relief")
        self.assertIsNone(policy._home_full_relief)
        self.assertEqual(policy._home_full_retry_deposits, deposits)
        self.assertEqual(policy._town_errand_plan.index, 1)
        self.assertIn(STORE_HOME, policy._town_errand_plan.blocked_this_visit)
        self.assertIsNone(policy._home_full_relief_key(board))
        self.assertEqual(policy._home_full_retry_deposits, deposits)

    def test_unidentified_only_relief_yields_to_identify_source_procurement(self):
        board = self.recorded_board()
        self.assertTrue(board.in_town)
        self.assertEqual(board.turn, 15372162)
        self.assertEqual(sum(item.charges for item in board.inventory
                             if item.tval == 55 and item.sval == 5), 0)

        policy = HengbotPolicy(monrace_knowledge={})
        policy.prime(board)
        skill = next(
            entry["row"] for entry in PINS["220530"]["states"]
            if entry["row"].get("knowledge", {}).get("category") == "skill_exp"
        )
        policy.consume_skill_knowledge(skill)
        catalogue = tuple(InventoryItem(
            str(index), f"unidentified reserve {index}", 1, 77, index % 8,
            False, False,
        ) for index in range(PACK_CAPACITY))
        policy.consume_home_knowledge(catalogue)
        deposit = board.inventory[0]
        policy._begin_home_full_relief(
            board, ((policy._item_signature(deposit), deposit.count, deposit.count),),
            refused=True,
        )
        key = policy._home_full_relief_key(board)
        self.assertIsNone(key, policy.last_reason)
        self.assertNotEqual(policy.last_reason, "town:blocked:home-full-no-sellable-surplus")
        self.assertIsNotNone(policy._home_full_relief)
        self.assertTrue(policy._home_full_relief.get("awaiting_identification_source"))
        self.assertIsNone(policy._home_errand.request)
        self.assertFalse(policy._identify_staff_ready(board))
        self.assertEqual(policy._next_required_store_type(board), STORE_MAGIC)
        self.assertEqual(policy._town_errand_plan.stops[0], STORE_MAGIC)
        self.assertFalse(policy._identify_staff_ready(board))

        staff = InventoryItem(
            "y", "Staff of Identify", 1, TVAL_STAFF, SV_STAFF_IDENTIFY,
            True, True, charges=20,
        )
        sourced = replace(board, turn=board.turn + 1,
                          inventory=(*board.inventory, staff))
        self.assertTrue(policy._identify_staff_ready(sourced))
        key = policy._home_full_relief_key(sourced)
        self.assertIsNotNone(key)
        self.assertIsNotNone(policy._home_errand.request)
        self.assertFalse(policy._home_full_relief.get("awaiting_identification_source"))

        signature, store_type, before_count = policy._home_full_relief["sale"]
        shelf_target = next(item for item in policy._home_knowledge_items
                            if policy._item_signature(item) == signature)
        carried = replace(shelf_target, slot="z")
        after_take = replace(sourced, turn=sourced.turn + 1,
                             inventory=(*sourced.inventory, carried))
        policy._home_full_relief["sale"] = (signature, store_type, before_count)
        policy._home_full_relief["withdrawn"] = True
        key = policy._home_full_relief_key(after_take)
        self.assertEqual(policy.last_reason, "identify:normal")
        self.assertIsNotNone(key)


if __name__ == "__main__":
    unittest.main()
