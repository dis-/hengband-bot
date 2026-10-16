from __future__ import annotations

import gzip
import json
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

import tests  # noqa: F401

from hengbot.model import (
    STORE_ALCHEMIST,
    SV_SCROLL_WORD_OF_RECALL,
    TVAL_SCROLL,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import LEAVE_STORE_KEY


FIXTURE = Path(__file__).parent / "fixtures" / "alchemist-home-cycle-20261017.jsonl.gz"


def retained_boards():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        rows = [parse_snapshot(json.loads(line), {}) for line in stream if line.strip()]
    # DECLARED CONSTRUCTED: the retained protocol-3 frames predate these two
    # skill fields; use the values in the neighboring captured policy run.
    return [
        replace(board, player=replace(
            board.player, two_weapon_skill=0, shield_skill=0
        ))
        for board in rows
    ]


def recorded_policy():
    policy = HengbotPolicy()
    # DECLARED CONSTRUCTED: restore the relevant captured checkpoint inputs.
    policy._equipment_optimization_last_depth = 19
    policy._fundraising_mode = "prepare"
    policy._home_knowledge_current = True
    return policy


class AlchemistRecallSelectionRecordedTest(unittest.TestCase):
    def test_replay_selects_recall_and_clears_procurement_shortage(self):
        alchemist, outside, _home = retained_boards()
        policy = recorded_policy()

        status = policy._supply_ledger(alchemist, policy._planned_depth())["recall"]
        self.assertEqual(
            (status.count, status.required_departure,
             policy._fundraising_kit_reserve(alchemist)),
            (8, 9, 0),
        )
        requirement = next(
            row for row in policy.procurement_requirements(alchemist)
            if row["item"] == "Word of Recall scrolls"
        )
        self.assertEqual(
            (requirement["current"], requirement["target"], requirement["missing"]),
            (8, 9, 1),
        )

        first_key = policy.choose_key(alchemist)
        self.assertEqual(
            (first_key, policy.last_reason),
            (LEAVE_STORE_KEY, "town-progress-invariant:continue-observed-shop"),
        )
        self.assertEqual(
            policy._shop_selector_diagnostics["considered_candidate"]["category"],
            "recall",
        )

        key = policy.choose_key(outside)
        self.assertEqual((key, policy.last_reason), ("5", "shop:one-shot-buy"))

        # DECLARED CONSTRUCTED: observe the emitted one-scroll purchase in the
        # next inventory frame before checking the planner's live view.
        inventory = list(outside.inventory)
        recall = next(item for item in inventory if item.is_recall_scroll)
        inventory[inventory.index(recall)] = replace(recall, count=recall.count + 1)
        after_purchase = replace(outside, inventory=inventory)
        after_status = policy._supply_ledger(
            after_purchase, policy._planned_depth()
        )["recall"]
        self.assertEqual(
            (after_status.count, after_status.required_departure), (9, 9)
        )
        after_requirements = policy.procurement_requirements(after_purchase)
        self.assertNotIn(
            "Word of Recall scrolls",
            [row["item"] for row in after_requirements],
        )
        needs = policy._town_need_candidates(after_purchase)
        plan = policy._build_town_errand_plan(after_purchase, needs)
        self.assertIsNotNone(plan)
        self.assertIn(STORE_ALCHEMIST, plan.stops)
        self.assertNotIn(
            "recall", plan.need_categories.get(STORE_ALCHEMIST, ())
        )

    def test_no_recall_on_shelf_still_leaves(self):
        alchemist, _outside, _home = retained_boards()
        shelf = replace(
            alchemist.store,
            items=[item for item in alchemist.store.items if not item.is_recall_scroll],
        )
        board = replace(alchemist, store=shelf)
        policy = recorded_policy()
        self.assertEqual(
            (policy.choose_key(board), policy.last_reason),
            (LEAVE_STORE_KEY, "shop:observe-and-leave"),
        )

    def test_recall_that_breaks_existing_reserve_is_refused(self):
        alchemist, _outside, _home = retained_boards()
        policy = recorded_policy()
        recall = next(item for item in alchemist.store.items if item.is_recall_scroll)
        self.assertEqual((recall.tval, recall.sval), (TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL))
        self.assertIsNotNone(
            policy._legacy_next_purchase_unreserved(alchemist, commit_state=False)
        )
        with patch.object(policy, "_fundraising_kit_reserve", return_value=1_500):
            self.assertIsNone(policy._next_purchase(alchemist))


if __name__ == "__main__":
    unittest.main()
