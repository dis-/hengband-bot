"""Constructed dispatch pins for the newly admitted direct producers."""

import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.policy import HengbotPolicy
from test_goldburn_shopping_constructed import board


class DirectEntryTest(unittest.TestCase):
    def test_normal_town_dispatch_asks_before_each_direct_body(self):
        for name in (
                "_warning_prompt_response_key", "_darkness_recovery_key",
                "_opening_q34_town_key", "_unprofitable_unique_disengage_key",
                "_fundraising_combat_equipment_key", "_town_cancel_unsafe_recall_key",
                "_pack_pressure_identify_key", "_town_destroy_key", "_town_special_key"):
            with self.subTest(rung=name):
                policy = HengbotPolicy()
                seen = []

                def entry(rung, producer, **kwargs):
                    if rung == name:
                        seen.append(kwargs["family"])
                        return "entry-owned-key"
                    return None

                with patch.object(policy, "_town_producer_entry", side_effect=entry), \
                        patch.object(policy, "_shopping_approach_step", return_value=None), \
                        patch.object(policy, name,
                                     side_effect=AssertionError("body ran before admission")):
                    self.assertEqual(policy.choose_key(board()), "entry-owned-key")
                self.assertEqual(len(seen), 1)
                if name == "_town_destroy_key":
                    self.assertEqual(seen, ["equipment-txn"])

    def test_committed_departure_block_asks_before_dispatch(self):
        policy = HengbotPolicy()
        policy._visit_departure_committed = True
        seen = []

        def entry(rung, producer, **kwargs):
            seen.append((rung, kwargs["family"]))
            return "block-entry-key" if rung == "_town_blocked_key" else None

        with patch.object(policy, "_town_producer_entry", side_effect=entry), \
                patch.object(policy, "_town_blocked_key",
                             side_effect=AssertionError("body ran before admission")):
            self.assertEqual(policy._decide(board()), "block-entry-key")
        self.assertEqual(seen, [("_town_cancel_unsafe_recall_key", "survival"),
                                ("_town_blocked_key", "town-plan")])

    def test_town_shelter_walk_keeps_its_survival_entry(self):
        snap = board()
        policy = HengbotPolicy()
        policy.prime(snap)
        injured = replace(snap, player=replace(snap.player, hp=snap.player.hp - 1))
        seen = []

        def entry(rung, producer, **kwargs):
            if rung == "_step_toward:survival":
                seen.append(kwargs["family"])
                return "shelter-entry-key"
            return None

        with patch.object(policy, "_town_producer_entry", side_effect=entry), \
                patch.object(policy, "_nearest_goal_step", return_value=snap.player.position), \
                patch.object(policy, "_step_toward",
                             side_effect=AssertionError("walk ran before admission")):
            self.assertEqual(policy.choose_key(injured), "shelter-entry-key")
        self.assertEqual(seen, ["survival"])


if __name__ == "__main__":
    unittest.main()
