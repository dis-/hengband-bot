from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import STORE_MAGIC, TVAL_WAND, StoreItem, StoreState
from hengbot.policy import (
    HengbotPolicy,
    ProcurementHomeGate,
    StoreVisit,
    WAIT_KEY,
)
from trajectory_harness import checkpoint_row, restore_incident_checkpoint


class DevicePurchasePreemptionTrajectoryTest(unittest.TestCase):
    FIXTURE = (
        Path(__file__).parent
        / "fixtures"
        / "device-purchase-preempted-checkpoint.jsonl.gz"
    )

    @staticmethod
    def _incident_page(policy, snapshot, *, price):
        wand = StoreItem(
            "e",
            "Sleep Monster wand (31 charges)",
            3,
            TVAL_WAND,
            0,
            price,
            charges=31,
        )
        store = StoreState(STORE_MAGIC, [wand], page_top=0)
        position = snapshot.player.position
        snapshot = replace(
            snapshot,
            grids={
                **snapshot.grids,
                position: replace(snapshot.grids[position], store_number=STORE_MAGIC),
            },
        )
        policy._shopping_approach_store_type = STORE_MAGIC
        policy._shop_observation = (store, policy._decision_sequence)
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_MAGIC)
        policy._town_store_attempted.pop(STORE_MAGIC, None)
        policy._town_blocked_reason = "repetition"
        policy._town_cycle_pending = True
        # Decision 253 predates the final Home pass in the measured window.
        # Seed only that later captured fact so this replay reaches the same
        # already-observed purchase arbitration point.
        policy._purchase_has_fresh_home_absence = (
            lambda _snapshot, _item: ProcurementHomeGate.ALLOW_PURCHASE
        )
        return snapshot

    def _restore(self):
        _row, policy_blob, snapshot_blob = checkpoint_row(self.FIXTURE, 253)
        return restore_incident_checkpoint(
            HengbotPolicy, policy_blob, snapshot_blob
        )

    def test_affordable_device_composes_before_repetition_terminal(self):
        policy, snapshot = self._restore()
        snapshot = self._incident_page(policy, snapshot, price=1083)

        key = policy.choose_key(snapshot)

        self.assertEqual(
            policy.last_reason,
            "town-progress-invariant:defect:town:blocked:repetition"
            "=>shop:one-shot-buy",
        )
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, "pe3\r\r\x1b")
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertEqual(
            policy._town_progress_invariant_defect["marker"],
            "TOWN_PROGRESS_INVARIANT_DEFECT",
        )

    def test_unaffordable_device_still_reaches_repetition_terminal(self):
        policy, snapshot = self._restore()
        snapshot = self._incident_page(
            policy, snapshot, price=snapshot.player.gold + 1
        )

        key = policy.choose_key(snapshot)

        self.assertNotEqual(key, "pe1\r\r\x1b")
        self.assertEqual(policy.last_reason, "town:blocked:repetition")
        self.assertFalse(policy._store_visit.operation_posted)

    def test_affordable_device_composes_on_adjacent_outside_page(self):
        policy, snapshot = self._restore()
        snapshot = self._incident_page(policy, snapshot, price=1083)
        policy._town_blocked_reason = None
        policy._town_cycle_pending = False

        key = policy.choose_key(snapshot)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")
        self.assertEqual(policy._store_visit.operation_key, "pe3\r\r\x1b")
        self.assertTrue(policy._store_visit.operation_posted)


if __name__ == "__main__":
    unittest.main()
