"""Return-owner frontier exploration and safety controls."""

import tests  # noqa: F401
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import Position, parse_snapshot
from hengbot.policy import DIRECTION_KEYS, HengbotPolicy, UP_STAIRS_KEY
from hengbot.policy_constants import SEARCH_LIMIT

FIXTURE = Path(__file__).parent / "fixtures/return-wander-20261016.jsonl.gz"
EXPECTED = {
    "20261016-055034-loop-detected": ("9", Position(10, 10)),
    "20261016-055146-loop-detected": ("4", Position(8, 22)),
    "20261016-055308-loop-detected": ("7", Position(11, 25)),
}


def captured_rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def returning_policy(record, snapshot=None):
    snapshot = snapshot or parse_snapshot(record["board"], {})
    policy = HengbotPolicy()
    policy.prime(snapshot)
    policy._returning_to_town = True
    policy._last_return_trigger = "escape-kit-empty"
    policy._build_grid_index(snapshot)
    # DECLARED REPLAY STATE: process-local return-loop evidence is reconstructed
    # from the captured loop detector; the JSONL board does not carry it.
    for position in snapshot.grids:
        policy._search_counts[(position.y, position.x)] = SEARCH_LIMIT
        policy._wall_search_counts[(position.y, position.x)] = SEARCH_LIMIT
    return policy, snapshot


class ReturnExploreForStairsTest(unittest.TestCase):
    def test_captured_boards_use_ordinary_frontier_route_during_return(self):
        records = captured_rows()
        self.assertEqual(len(records), 3)
        for record in records:
            with self.subTest(capture=record["capture"]):
                policy, snapshot = returning_policy(record)
                with (
                    patch.object(policy, "_is_oscillating", return_value=True),
                    patch.object(policy, "_probe_unknown_step", return_value=None),
                    patch.object(policy, "_undersearched_walls", return_value=False),
                    patch.object(policy, "_secret_wall_search_step", return_value=None),
                    patch.object(policy, "_skill_exp_request_key", return_value=None),
                ):
                    key = policy.choose_key(snapshot)
                expected_key, _target = EXPECTED[record["capture"]]
                self.assertEqual((key, policy.last_reason), (expected_key, "return:explore"))

    def test_known_reachable_upstairs_is_routed_before_exploration(self):
        record = captured_rows()[0]
        policy, snapshot = returning_policy(record)
        neighbor = next(iter(policy._walkable_neighbors(snapshot, snapshot.player.position)))
        grid = snapshot.grids[neighbor]
        snapshot = replace(
            snapshot,
            grids={**snapshot.grids, neighbor: replace(grid, has_up_stairs=True)},
        )
        policy.prime(snapshot)
        policy._returning_to_town = True
        policy._last_return_trigger = "escape-kit-empty"
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(snapshot)
        self.assertEqual(key, DIRECTION_KEYS[(neighbor.y - snapshot.player.position.y,
                                             neighbor.x - snapshot.player.position.x)])
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_low_hp_walk_gate_still_blocks_frontier_walk(self):
        record = captured_rows()[0]
        policy, snapshot = returning_policy(record)
        player = replace(snapshot.player, hp=1, max_hp=max(snapshot.player.max_hp, 10))
        snapshot = replace(snapshot, player=player)
        policy.prime(snapshot)
        policy._returning_to_town = True
        policy._last_return_trigger = "escape-kit-empty"
        with (
            patch.object(policy, "_is_oscillating", return_value=True),
            patch.object(policy, "_probe_unknown_step", return_value=None),
            patch.object(policy, "_undersearched_walls", return_value=False),
            patch.object(policy, "_secret_wall_search_step", return_value=None),
            patch.object(policy, "_skill_exp_request_key", return_value=None),
        ):
            key = policy.choose_key(snapshot)
        self.assertNotIn(key, DIRECTION_KEYS.values())
        self.assertIn(policy.last_reason, {"rest", "emergency:wait", "item:heal"})


if __name__ == "__main__":
    unittest.main()
