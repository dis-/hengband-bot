"""Pins for the shared disposal gate and routed destroy producers."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from hengbot.model import (
    Position, Snapshot, SV_SCROLL_DETECT_TREASURE, SV_SCROLL_WORD_OF_RECALL,
    TVAL_SCROLL,
)
from hengbot.policy import HengbotPolicy, WAIT_KEY
from hengbot.cli import POLICY_FINAL_STOP_REASONS, _policy_final_stop_banner
from policy_fixtures import grid, item, player
from tests.test_destroy_superior_item_guard import captured_rows, snapshot_at


def active_detection_fixture():
    snapshot = snapshot_at(captured_rows(), 2107)
    protected = item("z", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
                     name="Detect Treasure", count=1, fully_known=True)
    snapshot = replace(snapshot, inventory=[protected])
    policy = HengbotPolicy()
    policy._fundraising_mode = "mine"
    return policy, snapshot, protected


class DestroyProcurementGuardTest(unittest.TestCase):
    def _active(self):
        return active_detection_fixture()

    def test_p1a_incident_shaped_constructed_item_has_live_provenance(self):
        """PUBLIC-shape differential: HEAD destroys; patch/relevant revert refuse/restore HEAD."""
        policy, snapshot, protected = self._active()
        matches = policy._matching_live_purchase_rungs(snapshot, protected)
        self.assertIn("mining:treasure-detection", {match.rung_id for match in matches})

    def test_p1b_verified_gate_refuses_active_consumable(self):
        """SEAM: supplies finder and surplus=True; public prefilter masks this gate."""
        policy, snapshot, protected = self._active()
        with patch.object(policy, "_entire_stack_is_surplus", return_value=True):
            finder = lambda current: next(
                (candidate for candidate in current.inventory if candidate is protected), None
            )
            self.assertIsNone(policy._verified_destroy_key(snapshot, finder, "test"))
        self.assertEqual(policy.last_reason, "inventory:destroy-refused-superior-item")

    def test_p1c_overflow_selection_excludes_active_consumable(self):
        """SEAM: calls selection directly because the verified gate masks selection errors."""
        policy, snapshot, protected = self._active()
        with patch.object(policy, "_entire_stack_is_surplus", return_value=True), \
             patch.object(policy, "_find_disposable_item", return_value=None):
            self.assertIsNone(policy._overflow_disposal_item(snapshot))

    @staticmethod
    def _public_overflow_snapshot(count=20, *, legal_candidate=False):
        """Construct a quiet town observation; choose_key owns all policy state."""
        position = Position(10, 10)
        inventory = [
            item(
                chr(ord("a") + index), TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                name="Word of Recall", count=1, fully_known=True,
            )
            for index in range(count)
        ]
        if legal_candidate:
            inventory[-1] = item(
                inventory[-1].slot, TVAL_SCROLL, 1,
                name="Disposable Scroll", count=1, fully_known=True,
            )
        return Snapshot(
            player(10, 10, class_id=-1), {position: grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True, inventory=inventory,
        )

    def test_p3c_public_choose_key_protected_overflow_and_controls(self):
        """PUBLIC constructed response-free producer: free=3 stops; free=4 certifies; legal item destroys."""
        policy = HengbotPolicy()
        snapshot = self._public_overflow_snapshot()
        provenance = {
            carried.slot: policy._retention_reservation_detail(snapshot, carried)
            for carried in snapshot.inventory
        }
        self.assertTrue(all(
            reservation > 0
            or policy._survival_essential(carried)
            or policy._is_useful_device(carried)
            or policy._has_town_economic_path(carried)
            for carried, (reservation, _) in zip(snapshot.inventory, provenance.values())
        ))
        claims_before = policy._town_claims_active(snapshot)
        key = policy.choose_key(snapshot)
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:blocked:overflow-no-legal-disposal")
        self.assertNotIn("k", key)
        self.assertIsInstance(claims_before, bool)

        four_slot = HengbotPolicy()
        four_snapshot = self._public_overflow_snapshot(19)
        self.assertNotEqual(four_slot.choose_key(four_snapshot), WAIT_KEY)
        self.assertEqual(
            four_slot._terminal_pack_space_signature,
            four_slot._town_pack_space_signature(four_snapshot),
        )

        legal = HengbotPolicy()
        legal_key = legal.choose_key(
            self._public_overflow_snapshot(20, legal_candidate=True)
        )
        self.assertIn("k", legal_key)
        self.assertEqual(legal.last_reason, "town:destroy-overflow")

    def test_p3c_overflow_terminal_is_registered_with_exact_banner(self):
        reason = "town:blocked:overflow-no-legal-disposal"
        self.assertIn(reason, POLICY_FINAL_STOP_REASONS)
        self.assertIn(
            "overflow disposal is required but no legally destructible item exists",
            _policy_final_stop_banner(reason),
        )


if __name__ == "__main__":
    unittest.main()
