"""Live8 recorded facts and focused production-seam regression pins."""

import gzip
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import tests  # noqa: F401 -- isolate runtime files
from hengbot.model import Position, STORE_HOME, parse_snapshot
from hengbot.equipment_optimizer import equipment_identity
from hengbot.claim_register import observe
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, TownErrandPlan
from test_execution_declaration import short_route_board


LOG = Path(r"C:\hengband\bot-client\jsonlog") / (
    "incident-20260930-1932-s33-live-one-shot-in-flight-after-calibration-strip"
)


def recorded_rows():
    with gzip.open(str(LOG) + ".decisions.jsonl.gz", "rt", encoding="utf-8") as source:
        return {row["decision_sequence"]: row for row in map(json.loads, source)
                if 207 <= row.get("decision_sequence", 0) <= 220}


class Live8RestoreTest(unittest.TestCase):
    def test_recorded_strip_drained_pack_and_plan_deferred_calibration(self):
        rows = recorded_rows()
        self.assertEqual([rows[n]["reason"] for n in range(207, 211)],
                         ["home:atomic-deposit"] * 4)
        self.assertEqual(rows[211]["inventory"]["used"], 0)
        self.assertEqual(rows[212]["reason"],
                         "town:blocked:home-claim-uncomposable:"
                         "calibration-restore:home-knowledge-invalidated")
        self.assertIn({"holder_family": "town-plan", "holder_claim_id": None,
                       "deferred_family": "calibration",
                       "deferred_reason": "plan-next:7:_calibration_town_key",
                       "token_would_admit": False, "token_work_identity": None},
                      rows[211]["claim"]["errand_deferred"])








class Live8OneShotTest(unittest.TestCase):
    def test_recorded_220_has_cross_store_identity_and_no_declaration(self):
        row = recorded_rows()[220]
        self.assertEqual((row["key"], row["reason"], row["store_type"]),
                         ("", "shop:one-shot-in-flight", 5))
        self.assertEqual(row["store_visit"]["store_type"], STORE_HOME)
        self.assertEqual(row["claim"]["goal"]["expectation"],
                         ["219", "7", "pj2\r\r\x1b"])
        self.assertIsNone(row["claim"]["execution"])

    def test_empty_wait_requires_matching_live_post_and_declaration(self):
        for defect in (None, "missing", "sequence", "store", "identity", "effect"):
            for checkpoint in (False, True):
                with self.subTest(defect=defect, checkpoint=checkpoint):
                    policy = HengbotPolicy()
                    policy._town_claim_bar_enforced = True
                    operation = "pj2\r\r\x1b"
                    identity = (5, 219, operation)
                    policy._store_visit = StoreVisit(
                        "town-errand", "shopping", 5, opened_sequence=219,
                        operation_posted=True, operation_key=operation,
                        posted_sequence=219, claim_operation_identity=identity,
                        operation_producer_family="shop-buy")
                    claim = policy._claim_register.declare(
                        "shop-buy", observe(identity, 8, "store-operation"))
                    if defect != "missing":
                        policy._claim_register.declare_execution(
                            claim.claim_id, work_id="shop-operation:219:5:" + operation,
                            producer="shop-buy", state="awaiting",
                            operation_ref=("decision:218:" if defect == "sequence"
                                           else "decision:219:") + operation,
                            expected_effect="inventory/gold-effect",
                            continuation="shop.one-shot.dispatch")
                    if defect == "identity":
                        policy._store_visit.claim_operation_identity = (7, 219, operation)
                    if defect == "effect":
                        policy._store_visit.operation_effect_observed = True
                    if checkpoint:
                        policy = pickle.loads(pickle.dumps(policy))
                    board = SimpleNamespace(in_town=True,
                        store=SimpleNamespace(store_type=7 if defect == "store" else 5))
                    policy.last_reason = "shop:one-shot-in-flight"
                    key = policy._enforce_town_claim_result(board, "")
                    if defect is None:
                        self.assertEqual(key, "")
                        policy._record_execution_declaration(
                            policy._claim_register.current, key, policy.last_reason)
                        self.assertEqual(policy._claim_register.current.execution.operation_ref,
                                         "decision:219:" + operation)
                        self.assertEqual(policy._claim_register.current.execution.state,
                                         "awaiting")
                    else:
                        self.assertIsNone(key)
                        self.assertEqual(policy.last_reason,
                                         "ownership:declaration-stale:shop-buy")


class Live8RewriteTest(unittest.TestCase):
    def test_recorded_219_rewrite_changed_owner_and_bound_wrong_store(self):
        row = recorded_rows()[219]
        self.assertEqual((row["key"], row["reason"], row["claim"]["owner"]),
                         ("5", "town-progress-invariant:defect:"
                          "town:wait-restock:temple=>shop:one-shot-buy", "detectors"))
        self.assertEqual((row["store_visit"]["store_type"],
                          row["store_visit"]["operation_posted"]), (STORE_HOME, True))

    def test_holder_key_and_reason_pass_through_progress_seam(self):
        for checkpoint in (False, True):
            policy = HengbotPolicy()
            policy._town_claim_bar_enforced = True
            claim = policy._claim_register.declare(
                "shop-buy", observe((5, 219, "pj2\r\r\x1b"), 8,
                                    "store-operation"))
            policy.last_reason = "town:wait-restock:temple"
            if checkpoint:
                policy = pickle.loads(pickle.dumps(policy))
            board = short_route_board()
            self.assertEqual(policy._town_procurement_decision(board, "R300\r"),
                             "R300\r")
            self.assertEqual(policy.last_reason, "town:wait-restock:temple")
            self.assertEqual(policy._decision_rewrite_refused[-1], {
                "stage": "procurement", "holder_family": "shop-buy",
                "holder_claim_id": claim.claim_id})

    def test_progress_composer_cannot_bypass_home_plan_gate(self):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], requester_families={STORE_HOME: ("home-visit",)})
        board = short_route_board()
        self.assertIsNone(policy._town_procurement_progress_key(board))
        self.assertTrue(any(row["deferred_family"] == "shop-buy"
                            and row["deferred_reason"].startswith("plan-next:7:")
                            for row in policy._decision_errand_deferred))


if __name__ == "__main__":
    unittest.main()
