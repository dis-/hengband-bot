"""Pins for the first cross-area fundraising switch and captured stair facts."""

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tests  # noqa: F401 -- isolate runtime files

from hengbot.policy import HengbotPolicy
from hengbot.policy_fundraising import (
    FundraisingFacts, FundraisingPurpose, fundraising_run_verdict,
)


CAPTURE = Path(r"C:\hengband\bot-client\jsonlog") / (
    "incident-20260929-1154-s33-live-holder-silent-travel-short"
)


class CrossAreaFundraisingTest(unittest.TestCase):
    def setUp(self):
        self.facts = FundraisingFacts(
            carried_edible=False, hungry=False, light_ready=True,
            pack_full=False, objective_achieved=False,
            procurement_exhausted=True, first_run=True,
        )
        self.purpose = FundraisingPurpose(29, "mine", True)

    def test_captured_29_30_pair_has_unchanged_normal_food_premise(self):
        with gzip.open(str(CAPTURE) + ".decisions.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            decisions = [json.loads(row) for row in source]
        pair = [row for row in decisions
                if row.get("decision_sequence") in {29, 30}]
        self.assertEqual([(row["key"], row["reason"]) for row in pair[:2]],
                         [(">\ry", "descend"), ("<", "fundraise:ascend")])
        with gzip.open(str(CAPTURE) + ".state.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            states = [json.loads(row) for row in source]
        town, floor = states[1818:1820]
        for state in (town, floor):
            self.assertEqual(state["player"]["food_state"], "normal")
            self.assertEqual(state["player"]["gold"], 136)
            self.assertFalse(any(item["tval"] in {55, 65}
                                 for item in state["inventory"]))
        admitted = fundraising_run_verdict(self.facts, self.purpose)
        self.assertTrue(admitted.may_depart)
        self.assertTrue(admitted.may_continue)
        self.assertFalse(admitted.must_return)

    def test_waiver_is_first_run_only_and_hunger_still_returns(self):
        self.assertFalse(fundraising_run_verdict(
            replace(self.facts, first_run=False), None
        ).may_depart)
        self.assertFalse(fundraising_run_verdict(
            replace(self.facts, procurement_exhausted=False), None
        ).may_depart)
        hungry = fundraising_run_verdict(
            replace(self.facts, hungry=True), self.purpose
        )
        self.assertTrue(hungry.must_return)
        self.assertFalse(hungry.may_continue)
        self.assertTrue(fundraising_run_verdict(
            replace(self.facts, carried_edible=True, first_run=False), None
        ).may_depart)

    def test_suppressed_restock_still_checks_shared_admission(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._town_restock_suppressed = True
        policy._fundraising_mode = "mine"
        snapshot = SimpleNamespace(
            in_town=True, inventory=[],
            player=SimpleNamespace(gold=136),
        )
        with (patch.object(policy, "_next_depth_supply_shortage",
                           return_value=False),
              patch.object(policy, "_recall_departure_shortage",
                           return_value=False),
              patch.object(policy, "_fundraising_departure_ready",
                           return_value=False)):
            self.assertTrue(policy._descent_is_blocked(snapshot))
        self.assertEqual(policy._descent_refusal_reason,
                         "fundraising-departure-not-ready")


if __name__ == "__main__":
    unittest.main()
