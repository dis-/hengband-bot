"""Calibration Home deposits remain owed through interruption and retirement."""

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tests  # noqa: F401 -- isolate runtime files

from hengbot.model import PLAYER_CLASS_WARRIOR, STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.model import Position, Snapshot
from policy_fixtures import grid, item, player


CAPTURE = Path(r"C:\hengband\bot-client\jsonlog") / (
    "incident-20260928-1712-newchar-calibration-identify-first"
)


class CalibrationCrossAreaDebtTest(unittest.TestCase):
    def test_recorded_deposit_precedes_owner_retirement(self):
        with gzip.open(str(CAPTURE) + ".decisions.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            decisions = [json.loads(row) for row in source]
        selected = {row["decision_sequence"]: row for row in decisions
                    if row.get("decision_sequence") in {176, 177, 178, 179, 191}}
        self.assertEqual([selected[index]["reason"]
                          for index in (176, 177, 178, 179)],
                         ["home:atomic-deposit"] * 4)
        self.assertEqual(selected[191]["reason"], "town:blocked:owner-retired")
        self.assertEqual(selected[176]["turn"], 79437)
        self.assertEqual(selected[179]["turn"], 79448)
        with gzip.open(str(CAPTURE) + ".state.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            states = [json.loads(row) for row in source]
        self.assertTrue(any(item.get("tval") == 55
                            and item.get("charges") == 20
                            for item in states[406]["inventory"]))
        self.assertFalse(any(item.get("tval") == 55
                             for item in states[407]["inventory"]))

    def test_floor_interruption_preserves_restore_debt(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._calibration_phase = "deposit"
        signature = ("food staff", 55, 1)
        policy._calibration_restore_signatures = [signature]
        with (patch.object(policy, "_release_cured_calibration_deferral"),
              patch.object(policy, "_restore_calibration_redress_obligation"),
              patch.object(policy, "_calibration_redress_observe")):
            policy._calibration_observe(SimpleNamespace(in_town=False))
        self.assertEqual(policy._calibration_phase, "restore-supplies")
        self.assertEqual(policy._calibration_restore_signatures, [signature])

    def test_blocked_home_restore_is_typed_stop_with_debt_intact(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._calibration_phase = "restore-supplies"
        signature = ("food staff", 55, 1)
        policy._calibration_restore_signatures = [signature]
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        policy._calibration_home_rearm_eligible = False
        snapshot = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            town_flag=True,
        )
        policy._calibration_observe(snapshot)
        self.assertEqual(
            policy.last_reason,
            "town:blocked:calibration-restore-home-visit-exhausted",
        )
        self.assertEqual(policy._calibration_restore_signatures, [signature])
        self.assertEqual(policy._calibration_phase, "restore-supplies")

    def test_orphaned_restore_queue_reopens_its_phase(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        signature = ("food staff", 55, 1)
        policy._calibration_restore_signatures = [signature]
        with (patch.object(policy, "_release_cured_calibration_deferral"),
              patch.object(policy, "_restore_calibration_redress_obligation"),
              patch.object(policy, "_calibration_redress_observe")):
            policy._calibration_observe(SimpleNamespace(in_town=True))
        self.assertEqual(policy._calibration_phase, "restore-supplies")
        self.assertEqual(policy._calibration_restore_signatures, [signature])

    def test_overweight_restore_stops_without_foreign_deposit_or_erasing_debt(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._calibration_phase = "restore-supplies"
        signature = ("Stone-to-Mud wand", 65, 6)
        policy._calibration_restore_signatures = [signature]
        carried = replace(item("a", 65, 6), weight=10000)
        snapshot = Snapshot(
            replace(player(10, 10, class_id=PLAYER_CLASS_WARRIOR), stat_index=(0,)),
            {Position(10, 10): grid(10, 10)}, [],
            inventory=[carried], town_flag=True,
        )
        self.assertTrue(policy._inventory_overweight(snapshot))
        key = policy._calibration_town_key(snapshot)
        self.assertEqual(key, "5")
        self.assertIsNone(policy._enforce_town_claim_result(snapshot, key))
        self.assertEqual(policy.last_reason,
                         "town:blocked:calibration-restore-weight-limit")
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertEqual(policy._calibration_restore_signatures, [signature])
        self.assertEqual(policy._calibration_phase, "restore-supplies")


if __name__ == "__main__":
    unittest.main()
