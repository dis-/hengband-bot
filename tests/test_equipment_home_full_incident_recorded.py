"""Recorded 2026-10-07 refusal: do not repost a transaction deposit to a full Home."""
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    PHASE_HOME_FINALIZE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import parse_snapshot, STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase

FIXTURE = Path(__file__).parent / "fixtures/equipment-home-full-20261007.json.gz"
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    "d633cdd4dd64fd317f986f0e089bda015cf8120d3a47d6d5cd0fed49458e1e3f"
)
BOARD = json.loads(gzip.decompress(FIXTURE.read_bytes()))["board"]


class EquipmentHomeFullIncidentRecordedTest(unittest.TestCase):
    def test_full_home_ends_transaction_deposit_with_visible_reason(self):
        self.assertEqual(BOARD["turn"], 12986317)
        self.assertEqual(BOARD["store"]["stock_num"], BOARD["store"]["capacity"])
        board = parse_snapshot({**BOARD, "visible_monsters": [], "detected_monsters": []})
        board = replace(board, player=replace(
            board.player, two_weapon_skill=0, shield_skill=0,
        ))
        target = next(item for item in board.inventory if item.slot == "p")
        action = EquipmentTransaction(
            PHASE_HOME_FINALIZE, "deposit", "pack:recorded-full-home:0", None,
            equipment_identity(target), equipment_move_identity(target),
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0), physical_context="home",
        )
        policy = HengbotPolicy()
        policy.prime(board)
        policy._in_store_ops_enabled = True
        policy._equipment_transaction_session = session
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        policy._store_visit = StoreVisit(
            "equipment-transaction", "equipment-work", STORE_HOME,
            StoreVisitPhase.OPERATING, opened_sequence=16,
        )

        key = policy.choose_key(board)

        self.assertNotEqual(key, "dp")
        self.assertEqual(policy.last_reason, "equipment-transaction:deposit-home-full")
        self.assertIn(action.item_id, policy._equipment_transaction_failed_items)
        self.assertIsNone(session.pending_action)


if __name__ == "__main__":
    unittest.main()
