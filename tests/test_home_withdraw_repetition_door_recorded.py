"""Pin the captured Home door handoff under the town repetition latch."""

from __future__ import annotations

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

import tests  # noqa: F401
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.policy import HengbotPolicy, TownErrandPlan


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "home-withdraw-repetition-door-20261016.jsonl.gz"
)


def _captured_boards():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        home_page = parse_snapshot(json.loads(next(stream)))
        door = parse_snapshot(json.loads(next(stream)))
    return home_page, door


def _policy_for_captured_withdrawal(*, latched: bool) -> HengbotPolicy:
    home_page, door = _captured_boards()
    policy = HengbotPolicy()
    policy._floor_t = {
        (grid.position.y, grid.position.x)
        for grid in door.grids.values()
        if grid.passable
    }
    policy._home_knowledge_current = True
    policy._home_knowledge_items = list(home_page.store.items)
    policy._home_knowledge_valid_before = len(home_page.store.items)
    policy._home_page_size = home_page.store.page_size

    # DECLARED CONSTRUCTED: the decision log omits the private pending
    # signature. Bind the first item from the captured Home page through the
    # same pending fields populated by the catalogue queue owner.
    item = home_page.store.items[0]
    signature = policy._item_signature(item)
    policy._home_pending_item = signature
    policy._home_pending_quantity = 1
    policy._home_pending_quantities[signature] = 1
    policy._home_withdrawal_queued = True
    policy._town_errand_plan = TownErrandPlan(
        [STORE_HOME],
        need_categories={STORE_HOME: ("identification-withdrawal",)},
    )
    if latched:
        policy._town_blocked_reason = "repetition"
        policy._visit_departure_committed = False
    return policy


class HomeWithdrawRepetitionDoorRecordedTest(unittest.TestCase):
    def test_captured_latched_door_composes_the_bound_home_withdrawal(self):
        _home_page, door = _captured_boards()
        policy = _policy_for_captured_withdrawal(latched=True)

        key = policy._town_blocked_key(door)

        self.assertEqual(key, "5pa\x1b")
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")

    def test_latched_door_without_bound_withdrawal_still_steps_off(self):
        _home_page, door = _captured_boards()
        policy = HengbotPolicy()
        policy._floor_t = {
            (grid.position.y, grid.position.x)
            for grid in door.grids.values()
            if grid.passable
        }
        policy._town_blocked_reason = "repetition"
        policy._visit_departure_committed = False

        key = policy._town_blocked_key(door)

        self.assertEqual(key, "9")
        self.assertEqual(policy.last_reason, "town:blocked:repetition")

    def test_other_door_and_committed_departure_still_step_off(self):
        _home_page, door = _captured_boards()
        policy = _policy_for_captured_withdrawal(latched=True)
        entrance = door.grid_at(door.player.position)
        other_store_door = replace(
            door,
            grids={
                **door.grids,
                door.player.position: replace(entrance, store_number=STORE_HOME - 1),
            },
        )

        self.assertEqual(policy._town_blocked_key(other_store_door), "9")
        self.assertEqual(policy.last_reason, "town:blocked:repetition")

        policy._visit_departure_committed = True
        self.assertEqual(policy._town_blocked_key(door), "9")
        self.assertEqual(policy.last_reason, "town:blocked:repetition")

    def test_unlatched_home_withdrawal_key_is_unchanged(self):
        _home_page, door = _captured_boards()
        policy = _policy_for_captured_withdrawal(latched=False)

        step = policy._shopping_approach_step(door, router_plan_stop=True)
        key = policy._shopping_approach_key(door, step, "shop:travel")

        self.assertEqual(key.encode("utf-8"), b"5pa\x1b")
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")


if __name__ == "__main__":
    unittest.main()
