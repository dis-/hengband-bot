"""Characterization tests for exploration commitment stages 1 and 2."""

import ast
import json
import unittest
from collections import Counter
from pathlib import Path

from hengbot.model import Position, Snapshot, parse_snapshot
from hengbot.policy import (
    ExplorationGoalKind,
    ExplorationPathOutcome,
    HengbotPolicy,
)
from test_policy import grid, player


def corridor_snapshot(position: Position) -> Snapshot:
    cells = [
        grid(position.y, x, terrain_id=1, marked=True)
        for x in range(position.x, position.x + 3)
    ]
    return Snapshot(
        player(position.y, position.x),
        {cell.position: cell for cell in cells},
        [],
        turn=1,
        floor_key=(2, 5, 0),
        width=120,
        height=30,
    )


class ExplorationPathInventoryTest(unittest.TestCase):
    def test_every_path_writer_and_clear_outcome_is_inventoried(self):
        source_path = (
            Path(__file__).parents[1] / "src" / "hengbot" / "policy.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        writers = []
        clears = []
        for function in (
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ):
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Attribute)
                    and target.attr == "_explore_path"
                    for target in node.targets
                ):
                    writers.append((function.name, ast.unparse(node.value)))
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_clear_explore_path"
                ):
                    clears.append(
                        (function.name, ast.unparse(node.args[0]))
                    )

        self.assertCountEqual(
            writers,
            [
                ("_navigation_livelock_key", "edge_path[1:]"),
                ("_explore_step", "global_path[1:]"),
                ("_explore_step", "path[1:]"),
                ("_clear_explore_path", "[]"),
            ],
        )
        self.assertCountEqual(
            clears,
            [
                ("_decide", "ExplorationPathOutcome.INVALIDATE"),
                ("_decide", "ExplorationPathOutcome.INVALIDATE"),
                ("_decide", "ExplorationPathOutcome.INVALIDATE"),
                ("_decide", "ExplorationPathOutcome.INVALIDATE"),
                ("_observe", "ExplorationPathOutcome.INVALIDATE"),
                ("_fundraising_key", "ExplorationPathOutcome.ABANDON"),
                ("_return_to_town_key", "ExplorationPathOutcome.PAUSE"),
                ("_return_to_town_key", "ExplorationPathOutcome.PAUSE"),
                (
                    "_break_positional_oscillation",
                    "ExplorationPathOutcome.ABANDON",
                ),
                ("_explore_step", "ExplorationPathOutcome.ABANDON"),
                ("_explore_step", "ExplorationPathOutcome.ABANDON"),
                ("_explore_step", "ExplorationPathOutcome.INVALIDATE"),
                (
                    "_observe_one_step_explore",
                    "ExplorationPathOutcome.INVALIDATE",
                ),
            ],
        )


class CapturedGoalFlipCharacterizationTest(unittest.TestCase):
    def test_current_offline_planner_flips_between_two_goals(self):
        """Pin today's planner, not a full-process or revert-proof replay.

        The fixture states the reconstructed persistent-ledger and policy
        fields. In particular, the capture did not serialize the live
        ``_explore_path`` or ``_recent`` state.
        """
        fixture_path = (
            Path(__file__).with_name("fixtures")
            / "explore-two-cell-pingpong-s1.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertIn("not a full-process replay", fixture["description"])
        ledger = fixture["ledger"]
        expected = {
            Position(4, 95): (Position(3, 95), Position(2, 94), "8"),
            Position(5, 95): (Position(6, 95), Position(8, 96), "2"),
        }

        for row in fixture["snapshots"]:
            snapshot = parse_snapshot(row)
            policy = HengbotPolicy()
            policy._floor_key = snapshot.floor_key
            policy._visit_counts = Counter(
                {
                    Position(y, x): visits
                    for y, x, visits in ledger["visit_counts"]
                }
            )
            policy._probed_frontiers = {
                Position(y, x) for y, x in ledger["probed_frontiers"]
            }
            policy._search_counts = Counter(
                {
                    Position(y, x): searches
                    for y, x, searches in ledger["search_counts"]
                }
            )
            policy._wall_search_counts = Counter(
                {
                    Position(y, x): searches
                    for y, x, searches in ledger["wall_search_counts"]
                }
            )
            policy._blocked_unknown = {
                Position(y, x) for y, x in ledger["blocked_unknown"]
            }
            policy._build_grid_index(snapshot)

            path = policy._plan_explore_path(snapshot)
            first, destination, key = expected[snapshot.player.position]
            self.assertEqual(path[0], first)
            self.assertEqual(path[-1], destination)
            self.assertEqual(
                policy._direction_key(snapshot.player.position, path[0]), key
            )


class ExplorationIdentityObservationTest(unittest.TestCase):
    def test_visit_identity_records_signature_then_success_on_entry(self):
        start = Position(10, 10)
        snapshot = corridor_snapshot(start)
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._build_grid_index(snapshot)

        step = policy._explore_step(snapshot)

        self.assertEqual(step, Position(10, 11))
        identity = policy._explore_goal_identity
        self.assertIsNotNone(identity)
        self.assertEqual(identity.kind, ExplorationGoalKind.VISIT)
        self.assertEqual(identity.position, Position(10, 11))
        self.assertEqual(
            identity.evidence_signature,
            policy._explore_goal_signature(snapshot.grid_at(identity.position)),
        )
        self.assertEqual(
            policy._explore_path_outcome, ExplorationPathOutcome.PAUSE
        )
        entered = corridor_snapshot(step)
        policy._observe_one_step_explore(entered)
        self.assertEqual(
            policy._explore_path_outcome, ExplorationPathOutcome.SUCCESS
        )

    def test_frontier_and_window_edge_identities_remain_typed(self):
        start = Position(10, 10)
        snapshot = corridor_snapshot(start)
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._build_grid_index(snapshot)
        policy._visit_counts[Position(10, 11)] = 1

        self.assertEqual(policy._explore_step(snapshot), Position(10, 11))
        self.assertEqual(
            policy._explore_goal_identity.kind, ExplorationGoalKind.FRONTIER
        )

        edge = Position(10, 12)
        policy._record_explore_goal(
            snapshot, ExplorationGoalKind.WINDOW_EDGE, edge
        )
        self.assertEqual(
            policy._explore_goal_identity.kind,
            ExplorationGoalKind.WINDOW_EDGE,
        )
        policy._clear_explore_path(ExplorationPathOutcome.PAUSE)
        self.assertEqual(
            policy._explore_path_outcome, ExplorationPathOutcome.PAUSE
        )
        policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
        self.assertEqual(
            policy._explore_path_outcome, ExplorationPathOutcome.INVALIDATE
        )
        policy._clear_explore_path(ExplorationPathOutcome.ABANDON)
        self.assertEqual(
            policy._explore_path_outcome, ExplorationPathOutcome.ABANDON
        )


if __name__ == "__main__":
    unittest.main()
