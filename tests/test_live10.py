"""Recorded weapon restoration actions and their observed effects."""
import gzip
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
import tests  # noqa: F401
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.claim_register import observe
from hengbot.equipment_optimizer import equipment_identity

LOG = Path(r"C:\hengband\bot-client\jsonlog") / "incident-20260930-2149-s33-live-restore-weapon-stale-equipment"

def boards():
    result = {}
    with gzip.open(str(LOG) + ".state.jsonl.gz", "rt", encoding="utf8") as source:
        for raw in map(json.loads, source):
            if raw.get("type") != "knowledge" and raw.get("turn") in (458183, 458195, 458200):
                result[raw["turn"]] = parse_snapshot(raw, {})
    return [result[n] for n in (458183, 458195, 458200)]

class Live10Test(unittest.TestCase):
    def posted(self, policy, key):
        claim = policy._claim_register.current
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual(declaration.continuation, "equipment.restore-observe")
        policy._claim_register.declare_execution(
            claim.claim_id, producer="equipment-txn", work_id=declaration.work_id,
            state="awaiting", arguments=declaration.arguments,
            operation_ref="decision:435:" + key,
            expected_effect=declaration.expected_effect,
            continuation=declaration.continuation)

    def test_recorded_435_437_restore_finishes_after_checkpoint(self):
        first, second, third = boards()
        for checkpoint in (False, True):
            policy = HengbotPolicy()
            policy._town_claim_bar_enforced = True
            policy._normal_sub_hand_is_optimal = True
            policy._claim_register.declare("equipment-txn", observe(("transaction",), 10, "transaction"))
            key = policy._town_restore_weapon_key(first)
            self.assertEqual(key, "wga")
            self.posted(policy, key)
            if checkpoint:
                policy = pickle.loads(pickle.dumps(policy))
            key = policy._town_holder_declared_key(policy._claim_register.current, second)
            self.assertEqual(key, "tb")
            self.posted(policy, key)
            self.assertEqual(policy._claim_register.current.execution.arguments,
                             ("sub_hand", equipment_identity(second.equipment[1])))
            if checkpoint:
                policy = pickle.loads(pickle.dumps(policy))
            self.assertIsNone(policy._town_holder_declared_key(policy._claim_register.current, third))
            self.assertEqual(policy.last_reason, "ownership:holder-released:equipment-txn")
            self.assertEqual(policy._claim_register.current.closed_reason,
                             "no-step:no-restoration-required")

    def test_different_equipped_item_still_stops_stale(self):
        first, second, _ = boards()
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._claim_register.declare("equipment-txn", observe(("transaction",), 10, "transaction"))
        self.posted(policy, policy._town_restore_weapon_key(first))
        second.equipment[0] = replace(second.equipment[0], name="different sword")
        policy = pickle.loads(pickle.dumps(policy))
        self.assertIsNone(policy._town_holder_declared_key(policy._claim_register.current, second))
        self.assertEqual(policy.last_reason, "ownership:declaration-stale:equipment-txn")

