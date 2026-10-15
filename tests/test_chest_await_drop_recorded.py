import tests  # noqa: F401

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from policy_fixtures import grid, item, player
from hengbot.model import (
    DUNGEON_YEEK_CAVE, PLAYER_CLASS_WARRIOR, Position, Snapshot, TVAL_CHEST,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy, WAIT_KEY


FIXTURE = Path(__file__).parent / "fixtures" / "chest-await-q34-20261015.jsonl.gz"
RESERVED = Position(8, 10)
ORIGIN = Position(8, 17)


def captured_boards():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return {
            data["turn"]: parse_snapshot(data, {})
            for data in (json.loads(line) for line in stream)
        }


class ChestAwaitRecordedTest(unittest.TestCase):
    def test_captured_drop_board_waits_for_posted_item_confirmation(self):
        boards = captured_boards()
        before = boards[77068]
        after = boards[77073]
        policy = HengbotPolicy()

        # The captured board is outside the reserved square. This pins the
        # recorded route failure and the real policy's posted drop key.
        policy._build_grid_index(before)
        with patch.object(
            policy, "approved_quest_strategy", return_value=SimpleNamespace(quest_id=34)
        ), patch.object(policy, "_quest_strategy_route_step", return_value=None):
            self.assertEqual(
                policy._chest_processing_key(before, [], {RESERVED}), "di"
            )
        self.assertEqual(policy.last_reason, "chest:drop-unreachable-reserved")

        # DECLARED CONSTRUCTED: repeat the captured post-drop board to model the
        # stable snapshots from the soak and pin the underfoot fallback.
        policy._with_grid_memory(after)
        policy._build_grid_index(after)
        for _ in range(3):
            self.assertEqual(
                policy._chest_processing_key(after, [], {RESERVED}), "7"
            )
            self.assertEqual(policy.last_reason, "chest:step-off")

    def test_pending_drop_still_waits_while_posted_chest_is_carried(self):
        boards = captured_boards()
        before = boards[77068]
        policy = HengbotPolicy()
        with patch.object(
            policy, "approved_quest_strategy", return_value=SimpleNamespace(quest_id=34)
        ), patch.object(policy, "_quest_strategy_route_step", return_value=None):
            policy._chest_processing_key(before, [], {RESERVED})
        self.assertEqual(
            policy._chest_processing_key(before, [], {RESERVED}), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "chest:await-drop")

    def test_displaced_chest_within_three_squares_is_adopted(self):
        after = captured_boards()[77073]
        displaced = Position(8, 16)
        grids = dict(after.grids)
        grids[displaced] = grid(8, 16, objects=1, object_tvals=(TVAL_CHEST,))
        snapshot = replace(after, grids=grids)
        policy = HengbotPolicy()
        policy._with_grid_memory(snapshot)
        policy._build_grid_index(snapshot)
        policy._chest_drop_origin = ORIGIN
        self.assertEqual(
            policy._chest_processing_key(snapshot, [], {displaced}), "s"
        )
        self.assertEqual(policy.last_reason, "chest:search")
        self.assertEqual(policy._chest_position, displaced)

    def test_single_chest_normal_drop_still_steps_off(self):
        # DECLARED CONSTRUCTED: a focused snapshot isolates one carried chest
        # and a clear neighboring floor for the ordinary drop path.
        chest = item("i", TVAL_CHEST, 1, name="opened chest")
        grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 12) for x in range(9, 12)
        }
        single = Snapshot(
            player(10, 10, hp=50, max_hp=50, class_id=PLAYER_CLASS_WARRIOR),
            grids, [], floor_key=(DUNGEON_YEEK_CAVE, 2, 0), width=30,
            height=30, inventory=[chest],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(single), "di")
        self.assertEqual(policy.last_reason, "chest:drop")

        grids = dict(grids)
        grids[Position(10, 10)] = grid(
            10, 10, objects=1, object_tvals=(TVAL_CHEST,)
        )
        dropped = replace(single, inventory=[], grids=grids)
        self.assertEqual(policy.choose_key(dropped), "7")
        self.assertEqual(policy.last_reason, "chest:step-off")


if __name__ == "__main__":
    unittest.main()
