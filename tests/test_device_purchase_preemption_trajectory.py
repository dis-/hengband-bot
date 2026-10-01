import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

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

    # Equipped C-sheet calibration rework: decision 253 was recorded while
    # the retired strip calibration (deposit phase) held every equipment
    # change, so an exhausted torch stayed worn beside a pack lantern.  The
    # base code reached the purchase / repetition arbitration only because
    # that hold suppressed the light owner.  Without the strip phase the
    # public decision on this board is the ordinary light swap, before the
    # latched repetition terminal and before any purchase is composed; the
    # arbitration itself is no longer observable on this recorded board.
    def _assert_light_swap_first(self, policy, key, *, blocked):
        self.assertEqual((policy.last_reason, key), ("wield-light", "wd"))
        self.assertFalse(policy._store_visit.operation_posted)
        self.assertIsNone(policy._store_visit.operation_key)
        self.assertEqual(policy._town_blocked_reason, blocked)

    def test_affordable_device_composes_before_repetition_terminal(self):
        policy, snapshot = self._restore()
        snapshot = self._incident_page(policy, snapshot, price=1083)

        key = policy.choose_key(snapshot)

        self._assert_light_swap_first(policy, key, blocked="repetition")

    def test_unaffordable_device_still_reaches_repetition_terminal(self):
        policy, snapshot = self._restore()
        snapshot = self._incident_page(
            policy, snapshot, price=snapshot.player.gold + 1
        )

        key = policy.choose_key(snapshot)

        self.assertNotEqual(key, "pe1\r\r\x1b")
        self._assert_light_swap_first(policy, key, blocked="repetition")

    def test_component_restored_checkpoint_does_not_give_magic_visit_to_calibration(self):
        """Public choose_key pin for an unrelated post-calibration store visit."""
        policy, snapshot = self._restore()
        snapshot = self._incident_page(
            policy, snapshot, price=snapshot.player.gold + 1
        )
        # The older trajectory helper overrides this producer for its purchase
        # assertions.  This lifecycle pin deliberately uses the production
        # Home gate instead: no policy predicate is patched when choose_key runs.
        del policy.__dict__["_purchase_has_fresh_home_absence"]

        policy.choose_key(snapshot)

        self.assertIsNotNone(policy._store_visit)
        self.assertEqual(policy._store_visit.store_type, STORE_MAGIC)
        self.assertFalse(policy._store_visit.operation_posted)

    def test_affordable_device_composes_on_adjacent_outside_page(self):
        policy, snapshot = self._restore()
        snapshot = self._incident_page(policy, snapshot, price=1083)
        policy._town_blocked_reason = None
        policy._town_cycle_pending = False

        key = policy.choose_key(snapshot)

        self._assert_light_swap_first(policy, key, blocked=None)


if __name__ == "__main__":
    unittest.main()
