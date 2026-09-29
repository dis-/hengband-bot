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
    FundraisingFacts, FundraisingPurpose, FundraisingPurposeRecord,
    fundraising_run_verdict,
)
from hengbot.model import DUNGEON_YEEK_CAVE
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint


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

    def test_transport_completion_keeps_economic_purpose_open(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_run_purpose = self.purpose
        policy._decision_sequence = 29
        town = SimpleNamespace(floor_key=(0, 0, 0))
        policy._post_fundraising_transport(town, "depart")
        child = policy._fundraising_purpose_record.child
        self.assertEqual(child.purpose_id, self.purpose.identity)
        floor = SimpleNamespace(
            floor_key=(DUNGEON_YEEK_CAVE, 1, 1), in_town=False,
            dungeon_level=1, player=SimpleNamespace(gold=136),
        )
        self.assertTrue(policy._observe_fundraising_transport(floor))
        record = policy._fundraising_purpose_record
        self.assertEqual(record.child.state, "complete")
        self.assertEqual(record.status, "active")
        policy._post_fundraising_transport(floor, "return")
        arrived = SimpleNamespace(
            floor_key=(0, 0, 0), in_town=True, dungeon_level=0,
            player=SimpleNamespace(gold=136),
        )
        self.assertTrue(policy._observe_fundraising_transport(arrived))
        self.assertEqual(policy._fundraising_purpose_record.status, "active")
        self.assertEqual(policy._fundraising_purpose_record.child.state,
                         "complete")

    def test_wrong_destination_fails_purpose_and_bars_readmission(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_run_purpose = self.purpose
        policy._post_fundraising_transport(
            SimpleNamespace(floor_key=(0, 0, 0)), "depart"
        )
        wrong = SimpleNamespace(
            floor_key=(9, 3, 0), in_town=False, dungeon_level=3,
            player=SimpleNamespace(gold=136),
        )
        self.assertFalse(policy._observe_fundraising_transport(wrong))
        self.assertEqual(policy._fundraising_purpose_record.status, "failed")
        self.assertEqual(policy._fundraising_purpose_record.failure,
                         "wrong-destination")
        with patch.object(policy, "_fundraising_facts", return_value=self.facts):
            self.assertFalse(policy._fundraising_departure_ready(wrong))

    def test_checkpoint_keeps_waiver_and_legacy_checkpoint_gets_defaults(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_run_purpose = self.purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            self.purpose
        )
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertTrue(restored._crossarea_fundraising_enforced)
        self.assertEqual(restored._fundraising_run_purpose, self.purpose)
        self.assertEqual(restored._fundraising_purpose_record.status, "active")
        for name in ("_crossarea_fundraising_enforced",
                     "_fundraising_run_purpose", "_fundraising_purpose_record",
                     "_fundraising_runs_started"):
            delattr(policy, name)
        older = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertFalse(older._crossarea_fundraising_enforced)
        self.assertIsNone(older._fundraising_run_purpose)
        self.assertIsNone(older._fundraising_purpose_record)
        self.assertEqual(older._fundraising_runs_started, 0)


if __name__ == "__main__":
    unittest.main()
