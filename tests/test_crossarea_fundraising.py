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
from hengbot.model import DUNGEON_YEEK_CAVE, STORE_MAGIC
from hengbot.policy_constants import FOOD_TYPE_MANA
from policy_fixtures import store_item
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
        self.assertFalse(fundraising_run_verdict(
            replace(self.facts, first_run=False), self.purpose
        ).may_continue)
        for change in ({"light_ready": False}, {"pack_full": True},
                       {"objective_achieved": True}):
            self.assertTrue(fundraising_run_verdict(
                replace(self.facts, **change), self.purpose
            ).must_return)

    def test_home_copy_and_affordable_shop_prevent_first_run_waiver(self):
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._town_store_attempted[STORE_MAGIC] = 1
        snapshot = SimpleNamespace(
            in_town=True, inventory=[], store=None,
            player=SimpleNamespace(food_type=FOOD_TYPE_MANA,
                                   gold=136, hungry=False),
        )
        with (patch.object(policy, "_home_available_for_probe",
                           return_value=True),
              patch.object(policy, "_find_edible", return_value=None),
              patch.object(policy, "_fundraising_light_ready",
                           return_value=True),
              patch.object(policy, "_home_mana_food_candidate",
                           return_value=object())):
            facts = policy._fundraising_facts(snapshot)
        self.assertFalse(facts.procurement_exhausted)
        self.assertFalse(facts.first_run)
        self.assertFalse(fundraising_run_verdict(facts, None).may_depart)
        policy._home_knowledge_current = True
        snapshot.store = SimpleNamespace(
            store_type=STORE_MAGIC,
            items=[store_item("a", 55, 1, price=100)],
        )
        with (patch.object(policy, "_home_available_for_probe",
                           return_value=True),
              patch.object(policy, "_find_edible", return_value=None),
              patch.object(policy, "_fundraising_light_ready",
                           return_value=True),
              patch.object(policy, "_home_mana_food_candidate",
                           return_value=None)):
            facts = policy._fundraising_facts(snapshot)
        self.assertFalse(facts.procurement_exhausted)
        self.assertFalse(fundraising_run_verdict(facts, None).may_depart)

    def test_fresh_attachment_needs_save_backed_first_run_evidence(self):
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._town_store_attempted[STORE_MAGIC] = 1
        snapshot = SimpleNamespace(
            in_town=True, inventory=[], store=None, protocol_version=3,
            visited_town_ids=(0,),
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            player=SimpleNamespace(food_type=FOOD_TYPE_MANA,
                                   gold=136, hungry=False),
        )
        with (patch.object(policy, "_home_available_for_probe",
                           return_value=False),
              patch.object(policy, "_find_edible", return_value=None),
              patch.object(policy, "_fundraising_light_ready",
                           return_value=True),
              patch.object(policy, "_home_mana_food_candidate",
                           return_value=None)):
            facts = policy._fundraising_facts(snapshot)
            self.assertFalse(facts.first_run)
            self.assertFalse(fundraising_run_verdict(facts, None).may_depart)
            snapshot.entered_dungeon_ids = ()
            facts = policy._fundraising_facts(snapshot)
        self.assertTrue(facts.first_run)
        self.assertTrue(fundraising_run_verdict(facts, None).may_depart)

    def test_magic_shop_uses_home_device_before_affordable_ware(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "mine"
        policy._home_knowledge_current = True
        ware = store_item("a", 55, 1, price=100)
        snapshot = SimpleNamespace(
            store=SimpleNamespace(store_type=STORE_MAGIC, items=[ware]),
            player=SimpleNamespace(food_type=FOOD_TYPE_MANA, gold=136),
        )
        with (patch.object(policy, "_find_edible", return_value=None),
              patch.object(policy, "_home_available_for_probe",
                           return_value=True),
              patch.object(policy, "_home_mana_food_candidate",
                           return_value=object()),
              patch.object(policy, "_item_signature",
                           return_value=("food staff", 55, 1))):
            self.assertIsNone(policy._legacy_next_purchase_unreserved(snapshot))
        self.assertEqual(policy._home_pending_item, ("food staff", 55, 1))
        self.assertTrue(policy._fundraising_affordable_food_seen)
        policy._home_pending_item = None
        with (patch.object(policy, "_find_edible", return_value=None),
              patch.object(policy, "_home_available_for_probe",
                           return_value=True),
              patch.object(policy, "_home_mana_food_candidate",
                           return_value=None),
              patch.object(policy, "_mana_food_purchase", return_value=ware)):
            self.assertIs(policy._legacy_next_purchase_unreserved(snapshot), ware)

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

    def test_missing_transport_grant_stops_before_dungeon_work(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "mine"
        board = SimpleNamespace(
            floor_key=(DUNGEON_YEEK_CAVE, 1, 1), dungeon_level=1,
            in_town=False, player=SimpleNamespace(hungry=False),
        )
        self.assertEqual(policy._fundraising_key(board, []), "5")
        self.assertEqual(policy.last_reason,
                         "ownership:contract-conflict:fundraising:missing-purpose")
        board.player.hungry = True
        with (patch.object(policy, "_find_edible", return_value=None),
              patch.object(policy, "_leave_fundraising_floor",
                           return_value="<")):
            self.assertEqual(policy._fundraising_key(board, []), "<")

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
                     "_fundraising_runs_started",
                     "_fundraising_affordable_food_seen"):
            delattr(policy, name)
        older = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertFalse(older._crossarea_fundraising_enforced)
        self.assertIsNone(older._fundraising_run_purpose)
        self.assertIsNone(older._fundraising_purpose_record)
        self.assertIsNone(older._fundraising_runs_started)
        self.assertFalse(older._fundraising_affordable_food_seen)


if __name__ == "__main__":
    unittest.main()
