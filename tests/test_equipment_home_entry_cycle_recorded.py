"""Pin the recorded full-Home equipment-entry cycle from 2026-10-08."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    PHASE_HOME_PREPARE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


FIXTURE = Path(__file__).parent / "fixtures/equipment-home-entry-cycle-20261008.json.gz"
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    "0c327c0d647bd7217ad982a4b075477cf28c7ff608032ef3c681af835ec79dd2"
)
BOARD = json.loads(gzip.decompress(FIXTURE.read_bytes()))


class EquipmentHomeEntryCycleRecordedTest(unittest.TestCase):
    def test_full_home_refusal_retires_transaction_instead_of_reapproaching(self):
        """The live Home page must reach the equipment owner's refusal path."""
        snapshot = parse_snapshot(BOARD)
        target = next(item for item in snapshot.inventory if item.slot == "m")
        identity = equipment_identity(target)
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE,
            "deposit",
            f"pack:{identity}:0",
            item_identity=identity,
            move_identity=equipment_move_identity(target),
        )
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._in_store_ops_enabled = True
        policy._town_claim_bar_enforced = True
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0), physical_context="home",
        )
        policy._store_visit = StoreVisit(
            "equipment-transaction", "equipment-work", STORE_HOME,
            StoreVisitPhase.ENTERING, opened_sequence=0,
        )
        policy._home_capacity_observation = (
            snapshot.store.stock_num,
            snapshot.store.capacity,
            policy._effective_town_id(snapshot),
        )
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        # The captured decision deferred home-visit relief under the active
        # equipment-txn holder and fell through to the generic store ESC.
        policy._home_full_relief = {
            "deposits": (), "remaining": 1, "sale": None,
            "withdrawn": False, "town": policy._effective_town_id(snapshot),
        }

        with patch.object(policy, "_skill_exp_request_key", return_value=None), \
                patch.object(policy, "_home_full_relief_key", return_value=None):
            key = policy.choose_key(snapshot)

        self.assertEqual(key, "\x1b")
        self.assertEqual(policy.last_reason, "equipment-transaction:deposit-home-full")
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)


if __name__ == "__main__":
    unittest.main()
