"""Recorded pins for the 2026-09-16 calibration restore/deposit incident."""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_equipment import observe_equipment_transactions


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "calibration-restore-deposits-equipment-20260916.jsonl.gz"
)
PROVENANCE = FIXTURE.with_suffix("").with_suffix(".provenance.txt")
LIVE_FIRST_DIVERGENCE = ("wh", "calibration:redress")


def recorded_rows() -> list[dict]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def stripped_obligation(rows: list[dict]) -> tuple[tuple[str, str], ...]:
    dressed = parse_snapshot(rows[0], {})
    return tuple(
        (item.slot, equipment_identity(item))
        for item in dressed.equipment
        if item.is_equipment
    )


class CalibrationRestoreDepositsRecordedTest(unittest.TestCase):
    def test_fixture_is_the_byte_faithful_incident_window(self):
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
        self.assertEqual(len(rows), 58)
        self.assertEqual((rows[0]["turn"], rows[-1]["turn"]), (
            3_038_486, 3_038_685,
        ))

    def test_capture_replay_diverges_to_restore_session_before_any_deposit(self):
        rows = recorded_rows()
        naked = parse_snapshot(rows[34], {})
        policy = HengbotPolicy()
        policy._equipment_catalog.home_scan_complete = True
        policy._calibration_phase = "capture"
        policy._calibration_naked_dump_requested = True
        policy._calibration_naked_flags = frozenset()
        policy._calibration_worn_before = stripped_obligation(rows)
        policy._calibration_stripped_unrestored = True
        policy._calibration_restore_signatures = [("supply", 1, 1)]

        key = policy.choose_key(naked)
        replay = (key, policy.last_reason)
        print(f"replay={replay!r} live={LIVE_FIRST_DIVERGENCE!r}")

        self.assertEqual(replay, ("wi", "equipment-transaction:equip"))
        self.assertEqual(LIVE_FIRST_DIVERGENCE, ("wh", "calibration:redress"))
        self.assertEqual(policy._calibration_phase, "restore-equip")
        self.assertTrue(policy._calibration_restore_signatures)
        actions = policy._equipment_transaction_session.plan.actions
        self.assertEqual(len(actions), len(policy._calibration_worn_before))
        self.assertEqual({action.kind for action in actions}, {"equip"})
        stripped = {identity for _slot, identity in policy._calibration_worn_before}
        self.assertFalse(any(
            action.kind == "deposit" and action.item_identity in stripped
            for action in actions
        ))

    def test_recorded_deposit_missing_effect_board_replans_exact_wear(self):
        rows = recorded_rows()
        # This is the first outside board after the live deposit-missing page.
        # The lance is observed worn, so its stale pack id is satisfied; the
        # next observed carried obligation is the ring in pack slot a.
        board = parse_snapshot(rows[50], {})
        policy = HengbotPolicy()
        policy._calibration_redress_loaded = True
        policy._calibration_phase = "restore-supplies"
        policy._calibration_worn_before = stripped_obligation(rows)
        policy._calibration_stripped_unrestored = True

        key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), ("we", "calibration:redress"))
        self.assertNotIn("redress-abandoned", policy.last_reason)
        self.assertIsNone(policy._town_blocked_reason)

    def test_mid_restore_board_rewears_the_entire_recorded_stripped_set(self):
        rows = recorded_rows()
        current = parse_snapshot(rows[35], {})
        policy = HengbotPolicy()
        policy._calibration_redress_loaded = True
        policy._calibration_worn_before = stripped_obligation(rows)
        policy._calibration_stripped_unrestored = True

        for _ in range(8):
            key = policy.choose_key(current)
            self.assertTrue(key.startswith("w"), (key, policy.last_reason))
            letter = key[1]
            carried = next(item for item in current.inventory if item.slot == letter)
            target_slot = next(
                slot for slot, identity in policy._calibration_worn_before
                if identity == equipment_identity(carried)
            )
            remaining = [item for item in current.inventory if item is not carried]
            remaining = [replace(item, slot=chr(ord("a") + index))
                         for index, item in enumerate(remaining)]
            current = replace(
                current,
                inventory=tuple(remaining),
                equipment=current.equipment + [replace(carried, slot=target_slot)],
            )

        policy.choose_key(current)
        self.assertFalse(policy._calibration_stripped_unrestored)
        self.assertEqual(
            {equipment_identity(item) for item in current.equipment},
            {identity for _slot, identity in stripped_obligation(rows)},
        )
        self.assertNotEqual(policy.last_reason, "town:blocked:owner-retired")

    def test_completed_redress_precedes_the_saved_supply_restore_queue(self):
        rows = recorded_rows()
        dressed = parse_snapshot(rows[0], {})
        lance = next(item for item in dressed.equipment if item.slot == "main_hand")
        packed = replace(lance, slot="a")
        naked = replace(dressed, equipment=[], inventory=[packed])
        policy = HengbotPolicy()
        policy._calibration_worn_before = (("main_hand", equipment_identity(lance)),)
        policy._calibration_stripped_unrestored = True
        policy._calibration_restore_signatures = [("supply", 1, 1)]
        self.assertTrue(policy._install_calibration_restore_session(naked))
        session = policy._equipment_transaction_session
        session.dispatch(
            session.current_action, observe_equipment_transactions(naked)
        )
        redressed = replace(dressed, inventory=[])
        session.observe(observe_equipment_transactions(redressed))

        policy._calibration_observe(redressed)

        self.assertEqual(policy._calibration_phase, "restore-supplies")
        self.assertFalse(policy._calibration_stripped_unrestored)

    def test_exhausted_home_restore_keeps_debt_and_stops_explicitly(self):
        rows = recorded_rows()
        policy = HengbotPolicy()
        identity = next(
            identity for slot, identity in stripped_obligation(rows)
            if slot == "body"
        )
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [("missing", 1, 1)]
        policy._calibration_worn_before = (("main_hand", identity),)
        policy._calibration_stripped_unrestored = True
        policy._equipment_catalog.home_scan_complete = True
        policy._town_visit_ledger.blocked_stores.add(7)

        policy._calibration_observe(parse_snapshot(rows[57], {}))

        self.assertEqual(
            policy._town_blocked_reason,
            f"calibration-redress-home-visit-exhausted:{identity}",
        )
        self.assertTrue(policy._calibration_stripped_unrestored)
        self.assertEqual(len(policy._calibration_worn_before), 1)


if __name__ == "__main__":
    unittest.main()
