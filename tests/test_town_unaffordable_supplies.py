"""Recorded production-policy pin for unaffordable departure supplies."""

from __future__ import annotations

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.cli import _parse_items
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STAFF_IDENTIFY_MIN_CHARGES


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "town-unaffordable-supplies-20260915.jsonl.gz"
)


class TownUnaffordableSuppliesReplay(unittest.TestCase):
    def _replay(self, *, funded: bool = False):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]

        policy = HengbotPolicy()
        knowledge = rows.pop(0)
        self.assertEqual(
            (knowledge["type"], knowledge["turn"],
             knowledge["knowledge"]["category"],
             knowledge["knowledge"]["menu_key"]),
            ("knowledge", 2_902_792, "home", "9"),
        )
        policy.consume_home_knowledge(
            tuple(_parse_items(knowledge["knowledge"]["items"]))
        )

        decisions = []
        final_snapshot = None
        final_measures = None
        for raw in rows:
            snapshot = parse_snapshot(raw, {})
            if funded:
                # Counterfactual: retain every recorded field except gold.
                snapshot = replace(
                    snapshot, player=replace(snapshot.player, gold=10_000)
                )
            if raw is rows[-1]:
                final_measures = {
                    "recall": policy._count_recall_scrolls(snapshot),
                    "recall_required": policy._recall_departure_minimum(snapshot),
                    "identify_charges": policy._total_identify_staff_charges(snapshot),
                    "town_departure_ready": policy._town_departure_ready(snapshot),
                    "fundraising_departure_ready":
                        policy._fundraising_departure_ready(snapshot),
                }
            key = policy.choose_key(snapshot)
            decisions.append((snapshot.turn, key, policy.last_reason))
            final_snapshot = snapshot
        assert final_snapshot is not None
        return policy, final_snapshot, decisions, final_measures

    def test_recorded_board_scavenges_instead_of_wandering(self):
        policy, snapshot, decisions, measures = self._replay()

        self.assertEqual(measures["recall"], 8)
        self.assertEqual(measures["identify_charges"], 1)
        self.assertEqual(measures["recall_required"], 9)
        self.assertEqual(STAFF_IDENTIFY_MIN_CHARGES, 20)
        self.assertFalse(measures["town_departure_ready"])
        self.assertTrue(measures["fundraising_departure_ready"])
        self.assertEqual(
            decisions[-1],
            (2_911_111, "9",
             "town:entrance-step-off:fundraise:unaffordable-supplies"),
        )
        self.assertTrue(policy._dungeon_entry_allowed(
            snapshot, via_recall=False, destination_depth=1
        ))
        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertNotEqual(decisions[-1][2], "stuck:wander")

    def test_affordable_counterfactual_keeps_purchase_route(self):
        policy, snapshot, decisions, _measures = self._replay(funded=True)

        approaches = [row for row in decisions if row[2] == "shop:approach"]
        self.assertEqual(approaches[0], (2_911_096, "9", "shop:approach"))
        self.assertEqual(policy._actionable_departure_supplier(snapshot), 7)
        self.assertIsNone(policy._fundraising_mode)


if __name__ == "__main__":
    unittest.main()
