from __future__ import annotations

from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest

from hengbot.equipment_mutation import EquipmentMutationState
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "destroy-superior-digger-20260910.json.gz"


def captured_rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def snapshot_at(rows, sequence: int):
    row = next(
        row for row in rows
        if row["decision"]["decision_sequence"] == sequence
    )
    return parse_snapshot(row["snapshot"], {})


class DestroySuperiorItemGuardTest(unittest.TestCase):
    def test_captured_superior_digger_never_reaches_destroy_key(self):
        rows = captured_rows()
        policy = HengbotPolicy()

        keys = []
        for row in rows:
            snapshot = parse_snapshot(row["snapshot"], {})
            key = policy.choose_key(snapshot)
            keys.append((row["decision"]["decision_sequence"], key))
            if key:
                policy.confirm_key_posted(key)
            if row["decision"]["decision_sequence"] == 2108:
                break

        self.assertNotIn("01ko", [key for _, key in keys])
        incident = snapshot_at(rows, 2107)
        pick = next(item for item in incident.inventory if item.is_digging_tool)
        self.assertFalse(policy._is_surplus_digging_tool(incident, pick))
        self.assertNotEqual(policy._full_pack_destroy_key(incident), "01ko")

    def test_zero_pack_capacity_keeps_the_best_two_overall(self):
        snapshot = snapshot_at(captured_rows(), 2107)
        policy = HengbotPolicy()
        pick = next(item for item in snapshot.inventory if item.is_digging_tool)

        self.assertEqual(
            sum(item.is_digging_tool for item in snapshot.equipment),
            2,
        )
        self.assertIsNot(policy._find_disposable_item(snapshot), pick)
        self.assertFalse(policy._is_surplus_digging_tool(snapshot, pick))

    def test_destroy_choke_advances_after_superior_candidate(self):
        snapshot = snapshot_at(captured_rows(), 2107)
        pick = next(item for item in snapshot.inventory if item.is_digging_tool)
        # "average" is a real explicit disposable classification.  It makes the
        # normal finder offer this captured superior pick independently of the
        # top-two digger retention rule, so this pin binds the choke-point guard.
        offered_pick = replace(pick, pseudo_feeling="average")
        next_disposable = next(
            item
            for item in snapshot_at(captured_rows(), 2105).inventory
            if item.is_potion and item.sval == 31
        )
        snapshot = replace(
            snapshot,
            inventory=[
                next(item for item in snapshot.inventory if item.slot == "n"),
                offered_pick,
                replace(next_disposable, slot="p"),
            ],
        )
        policy = HengbotPolicy()

        self.assertIs(policy._find_disposable_item(snapshot), offered_pick)
        key = policy._full_pack_destroy_key(snapshot)

        self.assertNotEqual(key, "01ko")
        self.assertEqual(
            policy.last_reason,
            "inventory:destroy-after-superior-item-refusal",
        )

    def test_posted_equipment_mutation_does_not_run_destroy_finder(self):
        rows = captured_rows()
        policy = HengbotPolicy()
        posted_snapshot = None
        for row in rows:
            snapshot = parse_snapshot(row["snapshot"], {})
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(key)
            if row["decision"]["decision_sequence"] == 2109:
                self.assertEqual(key, "wna")
                posted_snapshot = snapshot
                break

        self.assertEqual(policy._equipment_mutation.state, EquipmentMutationState.POSTED)
        potion = next(
            item
            for item in snapshot_at(rows, 2105).inventory
            if item.is_potion and item.sval == 31
        )
        self.assertIsNotNone(posted_snapshot)
        pressure_snapshot = replace(
            posted_snapshot,
            inventory=[*posted_snapshot.inventory, replace(potion, slot="s")],
        )

        self.assertIsNone(policy._full_pack_destroy_key(pressure_snapshot))
        self.assertEqual(
            policy.last_reason,
            "inventory:destroy-deferred-equipment-mutation",
        )


if __name__ == "__main__":
    unittest.main()
