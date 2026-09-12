"""D3 retirement-key pins using constructed incident-shaped events."""

import unittest

from dataclasses import replace

from hengbot.cli import POLICY_FINAL_STOP_REASONS
from hengbot.model import DUNGEON_ANGBAND
from hengbot.town_arbiter import _new_town_turn_arbiter


class RetirementSelfClearingTest(unittest.TestCase):
    def _arbiter(self):
        arbiter = _new_town_turn_arbiter()
        arbiter.registry["departure"] = replace(
            arbiter.registry["departure"], budget=1
        )
        arbiter.registry["detectors"] = replace(
            arbiter.registry["detectors"], budget=99
        )
        return arbiter

    @staticmethod
    def _public_ready_departure():
        """Use the established ready-town builder; policy state starts normally."""
        from tests.test_policy_town import TownRecallReturnTest
        return TownRecallReturnTest()._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )

    def _public_retired_departure(self):
        policy, snapshot = self._public_ready_departure()
        emitted = []
        for _ in range(20):
            key = policy.choose_key(snapshot)
            emitted.append((key, policy.last_reason))
            if "departure" in policy._town_turn_arbiter._retired:
                break
        self.assertIn("departure", policy._town_turn_arbiter._retired)
        return policy, snapshot, emitted

    def test_p7b_resource_churn_does_not_clear_narrow_retirement(self):
        """SEAM: real observe/may_select; constructed full vectors and canonical clearance keys."""
        arbiter = self._arbiter()
        key = ("departure", "floor", True, 0, 4, (("ready", True),), None)
        arbiter.observe(in_town=True, reason="town:recall-to-angband",
                        progress_vector=("gold", 7567, "recall", 10), retirement_key=key)
        arbiter.observe(in_town=True, reason="town:recall-to-angband",
                        progress_vector=("gold", 7567, "recall", 10), retirement_key=key)
        self.assertFalse(arbiter.may_select("town:recall-to-angband",
                                           ("gold", 7567, "recall", 9), retirement_key=key))
        arbiter.observe(in_town=True, reason="shop:buy-recall",
                        progress_vector=("gold", 7320, "recall", 10), probe=True,
                        retirement_key_for=lambda owner: key if owner == "departure" else ("other",))
        self.assertFalse(arbiter.may_select("town:recall-to-angband", ("changed",), retirement_key=key))

    def test_p8a_slot_change_clears_retirement(self):
        arbiter = self._arbiter()
        old = ("departure", "floor", True, 0, 4, (("ready", True),), None)
        new = ("departure", "floor", True, 0, 5, (("ready", True),), None)
        arbiter.observe(in_town=True, reason="town:recall-to-angband", progress_vector=(1,), retirement_key=old)
        arbiter.observe(in_town=True, reason="town:recall-to-angband", progress_vector=(1,), retirement_key=old)
        arbiter.observe(in_town=True, reason="shop:one-shot-sell", progress_vector=(2,), probe=True,
                        retirement_key_for=lambda owner: new if owner == "departure" else (2,))
        self.assertTrue(arbiter.may_select("town:recall-to-angband", (2,), retirement_key=new))

    def test_p7c_public_choose_key_resource_churn_keeps_visible_retirement(self):
        """PUBLIC constructed differential: HEAD/old call sites self-clear; patched/lone mechanism reverts retain."""
        policy, snapshot, emitted = self._public_retired_departure()
        self.assertEqual(emitted[0], ("rra", "town:recall-to-angband"))
        recall = next(entry for entry in snapshot.inventory if entry.is_recall_scroll)
        churned = replace(
            snapshot,
            player=replace(snapshot.player, gold=snapshot.player.gold - 237),
            inventory=[
                replace(entry, count=entry.count - 1) if entry is recall else entry
                for entry in snapshot.inventory
            ],
            turn=snapshot.turn + 1,
        )
        policy.choose_key(churned)
        self.assertIn("departure", policy._town_turn_arbiter._retired)
        self.assertEqual(policy.last_reason, "town:blocked:owner-retired")
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_p8c_public_exit_observed_before_landing_and_slot_release_resets(self):
        """PUBLIC constructed response wall: observe exit, retire, slot completion, then outside-town landing."""
        policy, snapshot, emitted = self._public_retired_departure()
        exit_key, exit_reason = emitted[0]
        self.assertEqual((exit_key, exit_reason), ("rra", "town:recall-to-angband"))

        # The accepted non-departure completion is represented only after its
        # response observation: one carried slot is now free.
        completed = replace(
            snapshot, inventory=snapshot.inventory[:-1], turn=snapshot.turn + 1
        )
        policy.choose_key(completed)
        self.assertNotIn("departure", policy._town_turn_arbiter._retired)

        landed = replace(
            completed, town_flag=False, floor_key=(DUNGEON_ANGBAND, 1, 0),
            turn=completed.turn + 1,
        )
        policy.choose_key(landed)
        self.assertEqual(policy._town_turn_arbiter._retired, {})


if __name__ == "__main__":
    unittest.main()
