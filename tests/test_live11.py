"""Recorded General Store entry and declaration continuation regressions."""

import gzip
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path

import tests  # noqa: F401 -- isolate runtime files
from hengbot.model import parse_snapshot, StoreState
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, TownErrandPlan
from hengbot.claim_register import observe


LOG = Path(r"C:\hengband\bot-client\jsonlog") / (
    "incident-20260930-2231-s33-live-one-shot-buy-stale")


def capture():
    with gzip.open(str(LOG) + ".decisions.jsonl.gz", "rt", encoding="utf-8") as f:
        rows = {r["decision_sequence"]: r for r in map(json.loads, f)
                if r.get("decision_sequence") in (919, 920, 921)}
    with gzip.open(str(LOG) + ".state.jsonl.gz", "rt", encoding="utf-8") as f:
        states = [r for r in map(json.loads, f)
                  if r.get("turn") in {rows[919]["turn"], rows[920]["turn"]}]
    outside = parse_snapshot(next(r for r in states
        if r["type"] == "player_turn" and r["turn"] == rows[920]["turn"]), {})
    shelf = parse_snapshot(next(r for r in states
        if r["type"] == "store" and r["turn"] == rows[919]["turn"]), {})
    inside = parse_snapshot(next(r for r in states
        if r["type"] == "store" and r["turn"] == rows[921]["turn"]), {})
    return rows, outside, shelf, inside


class Live11Test(unittest.TestCase):
    def test_recorded_composition_binds_observed_store_after_plan_advance(self):
        rows, outside, shelf, inside = capture()
        self.assertEqual((rows[919]["store_type"], rows[920]["store_type"],
                          rows[921]["store_type"]), (0, None, 0))
        self.assertEqual(rows[920]["store_visit"]["store_type"], 5)
        self.assertEqual(rows[921]["reason"], "ownership:declaration-stale:shop-buy")
        for checkpoint in (False, True):
            policy = HengbotPolicy()
            policy._town_claim_bar_enforced = True
            policy._crossarea_fundraising_enforced = True
            policy._decision_sequence = 920
            policy._shop_observation = (shelf.store, 919)
            policy._town_errand_plan = TownErrandPlan([5, 4])
            policy._store_visit = StoreVisit("town-errand", "shopping", 5,
                                             opened_sequence=920)
            policy._home_knowledge_current = True
            key = policy._atomic_shop_transaction_key(outside)
            self.assertEqual(key, rows[920]["key"])
            visit = policy._store_visit
            operation = rows[920]["claim"]["execution"]["arguments"][1]
            self.assertEqual((visit.store_type, visit.operation_key), (0, operation))
            claim = policy._claim_register.declare(
                "shop-buy", observe(visit.claim_operation_identity, 8, "store-operation"))
            policy._record_execution_declaration(claim, key, policy.last_reason)
            policy.confirm_key_posted(key)
            self.assertEqual(policy._claim_register.current.execution.state, "awaiting")
            if checkpoint:
                policy = pickle.loads(pickle.dumps(policy))
            policy.last_reason = "shop:one-shot-in-flight"
            self.assertEqual(policy._enforce_town_claim_result(outside, ""), "")
            policy._record_execution_declaration(policy._claim_register.current,
                                                  "", policy.last_reason)
            policy._decision_sequence = 921
            tail = policy._town_holder_declared_key(policy._claim_register.current, inside)
            self.assertEqual(tail, operation)
            self.assertEqual(policy._enforce_town_claim_result(inside, tail), operation)
            policy._record_execution_declaration(policy._claim_register.current,
                                                  tail, policy.last_reason)
            policy.confirm_key_posted(tail)
            self.assertEqual(policy._claim_register.current.execution.continuation,
                             "shop.one-shot.observe")
            self.assertEqual(policy._claim_register.current.execution.operation_ref,
                             "decision:921:" + operation)

    def test_changed_store_still_stops_after_checkpoint(self):
        rows, outside, shelf, inside = capture()
        for checkpoint in (False, True):
            policy = HengbotPolicy()
            policy._town_claim_bar_enforced = True
            policy._decision_sequence = 920
            policy._shop_observation = (shelf.store, 919)
            policy._home_knowledge_current = True
            key = policy._atomic_shop_transaction_key(outside)
            self.assertEqual(key, "5")
            claim = policy._claim_register.declare("shop-buy", observe(
                policy._store_visit.claim_operation_identity, 8, "store-operation"))
            policy._record_execution_declaration(claim, key, policy.last_reason)
            policy.confirm_key_posted(key)
            if checkpoint:
                policy = pickle.loads(pickle.dumps(policy))
            changed = replace(inside, store=StoreState(5, inside.store.items))
            self.assertIsNone(policy._town_holder_declared_key(
                policy._claim_register.current, changed))
            self.assertEqual(policy.last_reason, "ownership:declaration-stale:shop-buy")


if __name__ == "__main__":
    unittest.main()
