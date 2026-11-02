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
from hengbot.town_hold import observe_goal as observe
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, TownErrandPlan
from test_execution_declaration import short_route_board


LOG = Path(__file__).parent / "fixtures" / "live8-one-shot.decisions.jsonl.gz"


def recorded_rows():
    with gzip.open(LOG, "rt", encoding="utf-8") as source:
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


class Live8RewriteTest(unittest.TestCase):
    def test_recorded_219_rewrite_changed_owner_and_bound_wrong_store(self):
        row = recorded_rows()[219]
        self.assertEqual((row["key"], row["reason"], row["claim"]["owner"]),
                         ("5", "town-progress-invariant:defect:"
                          "town:wait-restock:temple=>shop:one-shot-buy", "detectors"))
        self.assertEqual((row["store_visit"]["store_type"],
                          row["store_visit"]["operation_posted"]), (STORE_HOME, True))


if __name__ == "__main__":
    unittest.main()
