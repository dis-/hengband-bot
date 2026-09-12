"""Focused E1/E2 pins; all scenarios are constructed, never historical replay."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from hengbot.model import DUNGEON_ANGBAND, Position, Snapshot, SV_SCROLL_WORD_OF_RECALL, TVAL_SCROLL
from hengbot.policy import HengbotPolicy, WAIT_KEY
from hengbot.purchase_rungs import PurchaseContext, PurchaseMatch, PurchaseSelection
from hengbot.cli import POLICY_FINAL_STOP_REASONS, _policy_final_stop_banner
from policy_fixtures import grid, item, player


class RecallReadinessContradictionTest(unittest.TestCase):
    def _active_four_slot(self):
        position = Position(10, 10)
        base = Snapshot(
            player(10, 10, class_id=0), {position: grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
        )
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10)
        slots = "abcdefghijklmnopqs"
        filler = [item(slot, 5, i, name=f"junk-{i}") for i, slot in enumerate(slots)]
        snapshot = replace(
            base,
            player=replace(base.player, recalling=True),
            inventory=[recall, *filler],
            recall_dungeon_id=DUNGEON_ANGBAND,
            dungeon_recall_depths={DUNGEON_ANGBAND: 1},
        )
        policy = HengbotPolicy()
        policy._terminal_pack_space_signature = policy._town_pack_space_signature(snapshot)
        return policy, snapshot

    def test_p4a_four_slot_certificate_has_no_pack_blocker(self):
        """Incident-shaped differential: HEAD pack-too-full; patch none; E1 revert HEAD."""
        policy, snapshot = self._active_four_slot()
        self.assertNotIn("pack-too-full", policy._recall_unready_blockers(snapshot, DUNGEON_ANGBAND))

    def test_p4b_future_contradiction_stops_before_read(self):
        """SEAM supplies a future blocker and true conjunct map; E1 makes old incident blocker dormant."""
        policy, snapshot = self._active_four_slot()
        with patch.object(policy, "_recall_unready_blockers", return_value=["future-clause"]), \
             patch.object(policy, "_recall_town_departure_conjuncts", return_value={"all-real-leaves": True}), \
             patch.object(policy, "_town_blocked_key", return_value=WAIT_KEY):
            key = policy._town_cancel_unsafe_recall_key(snapshot)
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:blocked:recall-readiness-contradiction")
        self.assertIsNone(policy._read_binding)

    def test_p6_self_restore_refusal_preserves_shortage(self):
        """SEAM supplies binding and typed selection because E2 makes this proposal dormant."""
        policy, snapshot = self._active_four_slot()
        recall = snapshot.inventory[0]
        proposed = policy._read_key(snapshot, recall)
        match = PurchaseMatch(
            "mandatory:recall", "recall", policy._purchase_item_identity(recall),
            current=10, target=10, shortage=0, rationale="constructed selector",
        )
        selection = PurchaseSelection(match, recall, 6, PurchaseContext(snapshot), 1)
        self.assertTrue(policy._progress_only_restores_consumed_resource(
            snapshot, proposed, "town:cancel-unready-recall",
            progress_selection=selection,
        ))
        short_match = PurchaseMatch(
            "mandatory:recall", "recall", policy._purchase_item_identity(recall),
            current=10, target=11, shortage=1, rationale="pre-existing shortage",
        )
        self.assertFalse(policy._progress_only_restores_consumed_resource(
            snapshot, proposed, "town:cancel-unready-recall",
            progress_selection=PurchaseSelection(
                short_match, recall, 6, PurchaseContext(snapshot), 1
            ),
        ))

    def test_p4c_contradiction_terminal_is_registered_with_exact_banner(self):
        reason = "town:blocked:recall-readiness-contradiction"
        self.assertIn(reason, POLICY_FINAL_STOP_REASONS)
        self.assertIn(
            "a recall was authorised and then contradicted with no state change",
            _policy_final_stop_banner(reason),
        )


if __name__ == "__main__":
    unittest.main()
