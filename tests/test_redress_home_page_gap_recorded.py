"""Recorded pins for the 2026-09-16 calibration redress Home page gap."""

from __future__ import annotations

import gzip
import hashlib
import json
import unittest
from dataclasses import fields, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_planner import (
    PHASE_HOME_PREPARE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import StoreItem, StoreState, parse_snapshot
from hengbot.policy import HengbotPolicy


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "redress-home-page-gap-20260916.jsonl.gz"
PROVENANCE = FIXTURE.with_suffix("").with_suffix(".provenance.txt")
PRIOR_FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "calibration-restore-deposits-equipment-20260916.jsonl.gz"
)
LIVE_BLOCKED_DECISION = ("9", "town:blocked:equipment-transaction:withdraw-not-on-current-home-page")
TARGET_ITEM_ID = "home:a6c0f2beabc20770:0"
TARGET_IDENTITY = "a6c0f2beabc20770"


def recorded_rows() -> list[dict]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def original_loadout():
    with gzip.open(PRIOR_FIXTURE, "rt", encoding="utf-8") as stream:
        return parse_snapshot(json.loads(next(stream)), {})


class RedressHomePageGapRecordedTest(unittest.TestCase):
    def test_fixture_is_the_byte_faithful_recorded_window(self):
        with gzip.open(FIXTURE, "rb") as stream:
            frozen = stream.read()
        provenance = PROVENANCE.read_text(encoding="utf-8")
        expected_hash = next(
            line.split(":", 1)[1].strip()
            for line in provenance.splitlines()
            if line.startswith("Decompressed sha256:")
        )
        rows = recorded_rows()
        self.assertEqual(hashlib.sha256(frozen).hexdigest(), expected_hash)
        self.assertEqual(len(rows), 150)
        self.assertEqual((rows[0]["turn"], rows[-1]["turn"]), (3_038_685, 3_043_494))

    def test_recorded_page_one_replans_by_paging_without_dropping_session(self):
        rows = recorded_rows()
        page_one = parse_snapshot(rows[33], {})
        target = next(item for item in original_loadout().equipment if item.slot == "feet")
        self.assertEqual(equipment_identity(target), TARGET_IDENTITY)
        policy = HengbotPolicy()
        page_items = tuple(
            policy._inventory_item_from_store_item(item)
            for item in page_one.store.items
        )
        catalogue = page_items + (target,) + page_items[:35]
        policy.consume_home_knowledge(catalogue)
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", TARGET_ITEM_ID,
            item_identity=TARGET_IDENTITY,
        )
        policy._set_equipment_transaction_session(EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), len(page_one.inventory)),
            physical_context="home",
        ))

        key = policy.choose_key(page_one)
        replay = (key, policy.last_reason)
        print(f"replay={replay!r} live={LIVE_BLOCKED_DECISION!r}")

        self.assertEqual(replay, (" ", "equipment-transaction:seek-home-page"))
        self.assertEqual(LIVE_BLOCKED_DECISION, (
            "9", "town:blocked:equipment-transaction:withdraw-not-on-current-home-page",
        ))
        self.assertIsNotNone(policy._equipment_transaction_session)
        self.assertTrue(policy._equipment_transaction_session.executable)

    def test_persisted_strip_debt_keeps_departure_false_on_recorded_empty_slots(self):
        final = parse_snapshot(recorded_rows()[-1], {})
        dressed = original_loadout()
        obligation = [
            [item.slot, equipment_identity(item)] for item in dressed.equipment
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "character-calibration.json"
            path.write_text(json.dumps({"redress_obligation": obligation}), encoding="utf-8")
            policy = HengbotPolicy()
            policy._character_calibration_path = path
            policy.choose_key(final)

            values = policy._town_departure_conjuncts(final)
            self.assertFalse(values["calibration_loadout_restored"])
            self.assertTrue(policy._calibration_stripped_unrestored)
            self.assertNotEqual(policy.last_reason, "town:blocked:departure-unsatisfiable")

    def test_home_target_on_second_page_pages_then_withdraws(self):
        rows = recorded_rows()
        first = parse_snapshot(rows[33], {})
        target = next(item for item in original_loadout().equipment if item.slot == "feet")
        policy = HengbotPolicy()
        first_items = tuple(
            policy._inventory_item_from_store_item(item) for item in first.store.items
        )
        policy.consume_home_knowledge(first_items + (target,) + first_items[:35])
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", TARGET_ITEM_ID,
            item_identity=equipment_identity(target),
        )
        policy._set_equipment_transaction_session(EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), len(first.inventory)),
            physical_context="home",
        ))
        self.assertEqual(policy.choose_key(first), " ")

        values = {
            field.name: getattr(target, field.name)
            for field in fields(StoreItem)
            if field.name not in {"letter", "price", "exported_fields"}
        }
        second_target = StoreItem(letter="a", price=0, **values)
        second = replace(
            first,
            store=StoreState(
                7, [second_target], stock_num=53, page_top=52, page_size=52
            ),
            turn=first.turn + 1,
        )
        self.assertEqual(policy.choose_key(second), "pa")
        self.assertEqual(policy.last_reason, "equipment-transaction:withdraw")


if __name__ == "__main__":
    unittest.main()
