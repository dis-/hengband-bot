"""Recorded production-policy pin for unaffordable departure supplies."""

from __future__ import annotations

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.cli import _parse_items
from hengbot.model import STORE_ALCHEMIST, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STAFF_IDENTIFY_MIN_CHARGES


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "town-unaffordable-supplies-20260915.jsonl.gz"
)
RESTART_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "town-unaffordable-supplies-restart-20260915.jsonl.gz"
)


class TownUnaffordableSuppliesReplay(unittest.TestCase):
    def _replay_restart(self, *, funded: bool = False):
        with gzip.open(RESTART_FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]

        policy = HengbotPolicy()
        snapshots = []
        decisions = []
        measures = None
        for raw in rows:
            if raw["type"] == "knowledge":
                self.assertEqual(
                    (raw["knowledge"]["category"], raw["knowledge"]["menu_key"]),
                    ("home", "9"),
                )
                policy.consume_home_knowledge(
                    tuple(_parse_items(raw["knowledge"]["items"]))
                )
                continue
            snapshot = parse_snapshot(raw, {})
            if funded:
                snapshot = replace(
                    snapshot, player=replace(snapshot.player, gold=10_000)
                )
            if snapshot.turn == 2_911_820:
                conjuncts = policy._recall_town_departure_conjuncts(snapshot)
                supplier = policy._actionable_departure_supplier(snapshot)
                measures = {
                    "mode": policy._fundraising_mode,
                    "gold": snapshot.player.gold,
                    "restock_wait": policy._town_restock_wait_until,
                    "departure_ready": policy._town_departure_ready(snapshot),
                    "fundraising_departure_ready": (
                        policy._fundraising_departure_ready(snapshot)
                    ),
                    "store": snapshot.store,
                    "store_visit_released": (
                        policy._store_visit is None
                        or policy._store_visit.operation_released
                    ),
                    "supplier": supplier,
                    "supplier_attempted": (
                        supplier in policy._town_store_attempted
                        if supplier is not None else False
                    ),
                    "conjuncts": conjuncts,
                    "identify_source": policy._find_identification_source(
                        snapshot, full=True, reliable_only=True
                    ),
                }
            decisions.append((snapshot.turn, policy.choose_key(snapshot), policy.last_reason))
            snapshots.append(snapshot)
        return policy, snapshots[-1], decisions, measures

    def test_restart_recording_routes_to_detection_kit(self):
        policy, snapshot, decisions, measures = self._replay_restart()

        self.assertEqual(measures["mode"], "prepare")
        self.assertEqual(measures["gold"], 185)
        self.assertIsNone(measures["restock_wait"])
        self.assertFalse(measures["departure_ready"])
        self.assertTrue(measures["fundraising_departure_ready"])
        self.assertIsNone(measures["store"])
        self.assertTrue(measures["store_visit_released"])
        self.assertIsNone(measures["supplier"])
        self.assertFalse(measures["supplier_attempted"])
        self.assertFalse(measures["conjuncts"]["recall_departure_ready"])
        self.assertFalse(measures["conjuncts"]["identify_staff_ready"])
        self.assertFalse(measures["conjuncts"]["home_candidate_resolved"])
        self.assertFalse(measures["conjuncts"]["identification_need_clear"])
        self.assertFalse(
            measures["conjuncts"]["departure_identification_need_clear"]
        )
        self.assertIsNone(measures["identify_source"])
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._town_errand_plan.stops[0], STORE_ALCHEMIST)
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_ALCHEMIST],
            ("low-level-sale", "fundraising-detection"),
        )
        self.assertNotEqual(decisions[-1][2], "stuck:wander")

    def test_restart_funded_counterfactual_keeps_identification_owner(self):
        policy, _snapshot, decisions, measures = self._replay_restart(funded=True)

        self.assertEqual(measures["gold"], 10_000)
        self.assertIsNotNone(measures["supplier"])
        self.assertNotEqual(policy._fundraising_mode, "scavenge")
        self.assertTrue(any(reason == "shop:approach" for _, _, reason in decisions))

    def _replay(self, *, funded: bool = False, store_board: bool = False):
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
        if store_board:
            rows = [*rows[:3], *rows[-2:]]
        for raw in rows:
            snapshot = parse_snapshot(raw, {})
            if funded:
                # Counterfactual: retain every recorded field except gold.
                snapshot = replace(
                    snapshot, player=replace(snapshot.player, gold=10_000)
                )
            if snapshot.turn == 2_911_111 or store_board and raw is rows[-1]:
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
            if not store_board and snapshot.turn == 2_911_111:
                break
        assert final_snapshot is not None
        return policy, final_snapshot, decisions, final_measures

    def test_recorded_board_routes_to_detection_kit_instead_of_wandering(self):
        policy, snapshot, decisions, measures = self._replay()

        self.assertEqual(measures["recall"], 8)
        self.assertEqual(measures["identify_charges"], 1)
        self.assertEqual(measures["recall_required"], 9)
        self.assertEqual(STAFF_IDENTIFY_MIN_CHARGES, 20)
        self.assertFalse(measures["town_departure_ready"])
        self.assertTrue(measures["fundraising_departure_ready"])
        self.assertEqual(decisions[-1], (2_911_111, "9", "explore"))
        self.assertFalse(policy._dungeon_entry_allowed(
            snapshot, via_recall=False, destination_depth=1
        ))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._town_errand_plan.stops[0], STORE_ALCHEMIST)
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_ALCHEMIST],
            ("low-level-sale", "fundraising-detection"),
        )
        self.assertNotEqual(decisions[-1][2], "stuck:wander")

    def test_affordable_counterfactual_keeps_purchase_route(self):
        policy, snapshot, decisions, _measures = self._replay(funded=True)

        approaches = [row for row in decisions if row[2] == "shop:approach"]
        self.assertEqual(approaches[0], (2_911_096, "9", "shop:approach"))
        self.assertEqual(policy._actionable_departure_supplier(snapshot), 7)
        self.assertIsNone(policy._fundraising_mode)

    def test_recorded_low_gold_store_board_leaves_through_store_path(self):
        policy, snapshot, decisions, _measures = self._replay(store_board=True)

        self.assertIsNone(snapshot.store)
        self.assertEqual(snapshot.player.gold, 185)
        self.assertEqual(
            decisions[-2], (2_911_293, "\x1b", "shop:observe-and-leave")
        )
        self.assertEqual(decisions[-1], (2_911_306, "\x1b`n(.", "shop:travel"))
        self.assertEqual(policy._fundraising_mode, "prepare")


if __name__ == "__main__":
    unittest.main()
