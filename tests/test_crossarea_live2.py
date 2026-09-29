"""Pins from the 2026-09-29 Home chain-mail withdrawal stop."""

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_planner import (
    EquipmentTransaction, EquipmentTransactionPlan,
    PHASE_EQUIP, PHASE_HOME_PREPARE,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


FIXTURE = Path(__file__).parent / "fixtures/crossarea-live2-home-23-24.json.gz"
FIXTURE_SHA256 = "b7ab4c709226043f3bb17dd0312467eadc74162e7a3a73968e1a863e4ab114db"


class CrossareaLive2Test(unittest.TestCase):
    def setUp(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         FIXTURE_SHA256)
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            recorded = json.load(stream)
        self.before = parse_snapshot(recorded["before"])
        self.after = parse_snapshot(recorded["after"])
        self.assertEqual((self.before.store.store_type,
                          len(self.before.inventory), len(self.after.inventory)),
                         (STORE_HOME, 6, 7))
        self.chain = next(item for item in self.before.store.items
                          if item.tval == 37 and item.ac == 14)
        self.assertTrue(any(item.tval == 37 and item.ac == 14
                            for item in self.after.inventory))

    def _policy(self):
        identity = equipment_identity(self.chain)
        actions = (
            EquipmentTransaction(PHASE_HOME_PREPARE, "withdraw",
                                 "home:523d457d37cb5b14:0",
                                 item_identity=identity),
            EquipmentTransaction(PHASE_EQUIP, "equip",
                                 "home:523d457d37cb5b14:0",
                                 target_slot="body", item_identity=identity),
        )
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._prepare_equipment_optimization = Mock()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan(actions, (), 6), physical_context="home"
        )
        policy._store_visit = StoreVisit(
            "equipment-transaction", "equipment-work", STORE_HOME,
            phase=StoreVisitPhase.OPERATING, opened_sequence=3,
        )
        policy._claim_register.declare(
            "equipment-txn", observe(("transaction",), 8,
                                     source="transaction"),
            floor=self.before.floor_key,
        )
        return policy

    def test_recorded_withdraw_effect_dispatches_equip_on_next_board(self):
        policy = self._policy()
        key = policy._equipment_transaction_home_key(self.before)
        self.assertEqual((key, policy.last_reason),
                         ("ph", "equipment-transaction:withdraw"))
        policy._home_entry_operation_posted = True
        self.assertTrue(policy.confirm_key_posted(key))
        self.assertEqual(policy._store_visit.operation_key, "ph")
        equip = policy._choose_key(self.after)
        session = policy._equipment_transaction_session
        self.assertEqual(session.index, 1)
        self.assertTrue(policy._store_visit.operation_effect_observed)
        self.assertTrue(policy._store_visit.operation_released)
        self.assertIsNotNone(equip)
        self.assertEqual(policy.last_reason, "equipment-transaction:equip")
        self.assertEqual(equip, "wd")
        self.assertTrue(policy.confirm_key_posted(equip))
        self.assertEqual(policy._equipment_transaction_session.pending_action.kind,
                         "equip")
        self.assertEqual(policy._store_visit.operation_key, "wd")

    def test_unobserved_store_action_keeps_atomic_wait(self):
        policy = self._policy()
        key = policy._equipment_transaction_home_key(self.before)
        policy._home_entry_operation_posted = True
        self.assertTrue(policy.confirm_key_posted(key))
        result = policy._choose_key(self.before)
        self.assertIsNotNone(policy._equipment_transaction_session.pending_action)
        self.assertFalse(policy._store_visit.operation_effect_observed)
        # The S3.3 town fixture pins this open operation's atomic wait.
        self.assertEqual(result, "\r")
        self.assertEqual(policy.last_reason,
                         "equipment-transaction:atomic-deposit")

    def test_withdraw_effect_does_not_finish_another_visit_operation(self):
        policy = self._policy()
        key = policy._equipment_transaction_home_key(self.before)
        policy._home_entry_operation_posted = True
        self.assertTrue(policy.confirm_key_posted(key))
        visit = policy._store_visit
        visit.operation_key = "different-posted-operation"
        visit.operation_producer_family = "home-visit"
        policy._choose_key(self.after)
        self.assertEqual(policy._equipment_transaction_session.index, 1)
        self.assertFalse(visit.operation_effect_observed)
        self.assertFalse(visit.operation_released)

if __name__ == "__main__":
    unittest.main()
