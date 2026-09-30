"""Live8 recorded facts and focused production-seam regression pins."""

import gzip
import json
import pickle
import unittest
from pathlib import Path
from types import SimpleNamespace

import tests  # noqa: F401 -- isolate runtime files
from hengbot.model import Position, STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownErrandPlan


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


if __name__ == "__main__":
    unittest.main()
