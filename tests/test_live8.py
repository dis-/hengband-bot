"""Live8 recorded facts and focused production-seam regression pins."""

import gzip
import json
import pickle
import unittest
from pathlib import Path
from types import SimpleNamespace

import tests  # noqa: F401 -- isolate runtime files
from hengbot.model import Position, STORE_HOME
from hengbot.claim_register import observe
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, TownErrandPlan


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

    def test_plan_refusal_stops_with_restore_debt_after_checkpoint(self):
        board = SimpleNamespace(in_town=True, store=None,
                                visible_monsters=(),
                                player=SimpleNamespace(position=Position(45, 123)))
        for checkpoint in (False, True):
            policy = HengbotPolicy()
            policy._town_claim_bar_enforced = True
            policy._crossarea_fundraising_enforced = True
            policy._calibration_phase = "deposit"
            debt = [("oil", 77, 0), ("recall", 70, 11)]
            policy._calibration_restore_signatures = debt.copy()
            policy._town_errand_plan = TownErrandPlan(
                [STORE_HOME], requester_families={STORE_HOME: ("home-visit",)})
            if checkpoint:
                policy = pickle.loads(pickle.dumps(policy))
            self.assertIsNone(policy._town_producer_entry(
                "_calibration_town_key", lambda: self.fail("deferred producer ran")))
            policy.last_reason = "shop:travel:await-entry"
            self.assertIsNone(policy._enforce_town_claim_result(board, "5"))
            self.assertEqual(policy.last_reason,
                             "ownership:declaration-unrestored:calibration")
            self.assertEqual(policy._calibration_restore_signatures, debt)
            self.assertEqual(policy._calibration_phase, "deposit")

    def test_off_keeps_recorded_key(self):
        policy = HengbotPolicy()
        policy._calibration_restore_signatures = [("oil", 77, 0)]
        policy._decision_errand_deferred = [{"deferred_family": "calibration",
            "deferred_reason": "plan-next:7:_calibration_town_key"}]
        policy.last_reason = "shop:travel:await-entry"
        self.assertEqual(policy._enforce_town_claim_result(
            SimpleNamespace(in_town=True, store=None), "5"), "5")


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


if __name__ == "__main__":
    unittest.main()
