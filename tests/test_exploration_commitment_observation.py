"""Characterization tests for exploration commitment stages 1 and 2."""

import ast
import json
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, Snapshot, parse_snapshot
from hengbot.policy import (
    ExplorationGoalIdentity,
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
        source_root = Path(__file__).parents[1] / "src" / "hengbot"
        trees = [
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for path in sorted(source_root.glob("*.py"))
        ]
        writers = []
        clears = []
        for function in (
            node for tree in trees for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
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
                ("_explore_step", "[]"),
                ("_explore_step", "route[1:]"),
                ("_explore_step", "route[1:]"),
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
                ("_decide", "ExplorationPathOutcome.INVALIDATE"),
                ("_observe", "ExplorationPathOutcome.INVALIDATE"),
                ("_refresh_paralyzer_avoidance", "ExplorationPathOutcome.INVALIDATE"),
                ("_paralyzer_prevention_key", "ExplorationPathOutcome.INVALIDATE"),
                # Warning-grid avoidance: a committed path may not replay a
                # step into a grid a TR_WARNING prompt refused, so both the
                # refusal record and the per-decision avoidance refresh drop
                # an intersecting committed path.
                (
                    "_refresh_warning_avoidance",
                    "ExplorationPathOutcome.INVALIDATE",
                ),
                (
                    "_latch_warning_refusal",
                    "ExplorationPathOutcome.INVALIDATE",
                ),
                (
                    "_immobile_breeder_giveup_key",
                    "ExplorationPathOutcome.INVALIDATE",
                ),
                ("_fundraising_key", "ExplorationPathOutcome.ABANDON"),
                ("_return_to_town_key", "ExplorationPathOutcome.PAUSE"),
                ("_return_to_town_key", "ExplorationPathOutcome.PAUSE"),
                ("_dark_locomotion_key", "ExplorationPathOutcome.PAUSE"),
                (
                    "_break_positional_oscillation",
                    "ExplorationPathOutcome.ABANDON",
                ),
                ("_explore_step", "ExplorationPathOutcome.ABANDON"),
                ("_explore_step", "ExplorationPathOutcome.PAUSE"),
                ("_explore_step", "ExplorationPathOutcome.INVALIDATE"),
                (
                    "_retire_explore_goal",
                    "ExplorationPathOutcome.INVALIDATE",
                ),
                (
                    "_observe_one_step_explore",
                    "ExplorationPathOutcome.INVALIDATE",
                ),
            ],
        )


class CapturedGoalFlipCharacterizationTest(unittest.TestCase):
    def test_replanning_holds_one_incident_destination(self):
        """Update the stage-1 characterization to pin committed replanning.

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
        policy = HengbotPolicy()
        destinations = []
        keys = []
        for index, row in enumerate(fixture["snapshots"][:2]):
            snapshot = parse_snapshot(row)
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
            if index == 0:
                path = policy._plan_explore_path(snapshot)
                policy._record_explore_goal(
                    snapshot, ExplorationGoalKind.FRONTIER, path[-1]
                )
            policy._explore_path = []
            policy._recent.extend(
                [Position(4, 95), Position(5, 95)] * 3
            )

            step = policy._explore_step(snapshot)
            self.assertIsNotNone(step)
            destinations.append(policy._explore_goal_identity.position)
            keys.append(policy._direction_key(snapshot.player.position, step))

        # The unmarked magic-mapped room remains unexplored, so replanning
        # commits to its reachable marked boundary instead of erasing it from
        # the frontier through the broader terrain-known axis.
        self.assertEqual(destinations, [Position(3, 95), Position(3, 95)])
        self.assertNotEqual(keys, ["8", "2"])


class ExplorationCommitmentReplanningTest(unittest.TestCase):
    def test_monster_on_goal_keeps_routing_with_same_identity(self):
        start = Position(10, 10)
        goal = Position(10, 11)
        occupied = corridor_snapshot(start)
        occupied.grids[goal] = grid(
            goal.y, goal.x, terrain_id=1, marked=True, monster=True
        )
        policy = HengbotPolicy()
        policy.prime(occupied)
        policy._build_grid_index(occupied)
        signature = policy._explore_goal_signature(occupied.grid_at(goal))
        policy._explore_goal_identity = ExplorationGoalIdentity(
            ExplorationGoalKind.VISIT, goal, signature
        )

        self.assertEqual(policy._explore_step(occupied), goal)
        self.assertEqual(policy._explore_goal_identity.position, goal)
        self.assertEqual(
            policy._explore_path_outcome, ExplorationPathOutcome.PAUSE
        )

        policy._build_grid_index(occupied)
        self.assertEqual(policy._explore_step(occupied), goal)
        self.assertEqual(policy._explore_goal_identity.position, goal)

    def test_stationary_occupant_retires_after_three_failed_origins(self):
        goal = Position(10, 10)
        origins = (
            Position(9, 9),
            Position(9, 10),
            Position(9, 11),
        )
        alternative = Position(8, 9)
        cells = {
            goal: grid(
                goal.y, goal.x, terrain_id=1, marked=True, monster=True
            ),
            alternative: grid(
                alternative.y, alternative.x, terrain_id=1, marked=True
            ),
        }
        cells.update(
            {
                origin: grid(
                    origin.y, origin.x, terrain_id=1, marked=True
                )
                for origin in origins
            }
        )
        policy = HengbotPolicy()
        first = Snapshot(
            player(origins[0].y, origins[0].x),
            cells,
            [],
            floor_key=(2, 5, 0),
            width=30,
            height=30,
        )
        policy.prime(first)
        policy._visit_counts.update({origin: 1 for origin in origins})
        policy._build_grid_index(first)
        signature = policy._explore_goal_signature(first.grid_at(goal))
        policy._explore_goal_identity = ExplorationGoalIdentity(
            ExplorationGoalKind.VISIT, goal, signature
        )

        for origin in origins:
            attempted = replace(
                first, player=replace(first.player, position=origin)
            )
            policy._build_grid_index(attempted)
            self.assertEqual(policy._explore_step(attempted), goal)
            policy._observe_one_step_explore(attempted)

        self.assertIsNone(policy._explore_goal_identity)
        self.assertIn(goal, policy._unenterable_explore_goals)
        policy._build_grid_index(first)
        self.assertEqual(policy._explore_step(first), alternative)

    def test_unreachable_identity_is_dropped_without_suppression_write(self):
        start = Position(10, 10)
        blocked_goal = Position(10, 11)
        alternative = Position(11, 10)
        cells = {
            start: grid(10, 10, terrain_id=1, marked=True),
            blocked_goal: grid(10, 11, terrain_id=1, marked=True),
            alternative: grid(11, 10, terrain_id=1, marked=True),
        }
        snapshot = Snapshot(
            player(10, 10),
            cells,
            [],
            floor_key=(2, 5, 0),
            width=30,
            height=30,
        )
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._build_grid_index(snapshot)
        policy._engagement_avoid_cells.add(blocked_goal)
        signature = policy._explore_goal_signature(
            snapshot.grid_at(blocked_goal)
        )
        policy._explore_goal_identity = ExplorationGoalIdentity(
            ExplorationGoalKind.VISIT, blocked_goal, signature
        )
        probed_before = set(policy._probed_frontiers)
        window_before = set(policy._window_edge_goals)
        unenterable_before = dict(policy._unenterable_explore_goals)

        step = policy._explore_step(snapshot)

        self.assertEqual(step, alternative)
        self.assertEqual(policy._probed_frontiers, probed_before)
        self.assertEqual(policy._window_edge_goals, window_before)
        self.assertEqual(policy._unenterable_explore_goals, unenterable_before)
        self.assertEqual(policy._explore_goal_identity.position, alternative)


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
