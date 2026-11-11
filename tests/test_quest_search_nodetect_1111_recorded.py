"""The quest target search without any means: 「歩いて行ける床と、それに接する壁」.

Owner 2026-11-11: 「感知が無い時は、歩いて行ける床と、それに接する壁を2回見たら全域を覆ったとみなして
諦める（岩の中は数えない）。」  Recorded: tests/fixtures/n1a-508-1111/search-12f-1852.json.gz and
search-44f-0824.json.gz (tests/extract_n1a_508_1111_fixtures.py): n1-a life-507 (Angband 12F, RANDOM
quest 43, 8 hours, 2026-11-10) and life-508 (Angband 44F, RANDOM quest 47, ``stall:floor-dwell:search``
at 2026-11-11 08:24), neither with telepathy nor a detection.  The 11-08 coverage set (every grid but
the outer ring) holds the rock, never in view, so the sweep count stayed 0 and the floor was never
given up.

Every decision is the public ``choose_key`` of one fresh policy fed the recorded boards in order.
DECLARED CONSTRUCTED, after the recorded boards: the walk the game would make of the policy's own
keys -- a direction key moves the player onto a grid one of the recorded boards showed passable,
every decision advances 10 game turns, the grids in view are the player's grid and its neighbours
only (a subset of what the game shows); the frontiers the replayed explore names are written off
(the recorded explore answered nothing on these floors: its rows are ``search`` /
``quest-search:*``), as tests/test_n1b_62f_quest_cover_1108_recorded.py does.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import unittest
from unittest import mock

import numpy as np

from hengbot import quest_target_search as search
from hengbot import search_coverage
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT
from tests.test_empty_wand_1110_recorded import MOVES, case, replay
from tests.test_n1b_348_stops_1108_recorded import knowledge


class _SearchWalk:
    """1. The search walked on the recorded floor (module docstring, DECLARED CONSTRUCTED)."""

    NAME = ""

    @classmethod
    def setUpClass(cls):
        cls.case = case(cls.NAME)

    after_first = None  # how many decisions had been made when the first coverage completed

    def walk(self, limit):
        policy, races, raw, _ = replay(self.case)
        self.assertTrue(search.searching(policy, parse_snapshot(copy.deepcopy(raw), races)))
        raw = dict(copy.deepcopy(raw), messages=[])
        passable = {grid.position for row in self.case["rows"]
                    for grid in parse_snapshot(copy.deepcopy(row), races).grids.values()
                    if grid.known and grid.passable}
        ledger = policy._exploration_ledger
        reasons = []
        for _ in range(limit):
            board = parse_snapshot(copy.deepcopy(raw), races)
            here = board.player.position
            for position, grid in list(board.grids.items()):
                view = grid.known and game_distance(position, here) <= 1
                if grid.in_view != view:
                    board.grids[position] = dataclasses.replace(grid, in_view=view)
            key = policy.choose_key(board)
            key = "" if key is None else str(key)
            if policy.last_reason == "explore" or policy.last_reason.startswith(("breakout", "probe")):
                goal = policy._explore_goal_identity
                if goal is not None:
                    ledger.probed_frontiers.add(goal.position)
                    policy._clear_explore_path(None)
                    policy._explore_goal_identity = None
                    policy._recent.clear()
                    continue
            if key:
                policy.confirm_key_posted(key)
            reasons.append(policy.last_reason)
            memory = getattr(policy, search.MEMORY)
            if memory.sweeps.count == 1 and self.after_first is None:
                self.after_first = len(reasons)
            if memory.sweeps.count >= self.SWEEPS:
                return policy, board, reasons
            raw["turn"] += 10
            if key in MOVES:
                dy, dx = MOVES[key]
                to = Position(raw["player"]["y"] + dy, raw["player"]["x"] + dx)
                if to in passable:
                    raw["player"]["y"], raw["player"]["x"] = to.y, to.x
        self.fail(f"not given up after {limit} decisions: {reasons[-5:]}")

    def test_recorded_scene(self):
        races = knowledge(self.case)
        board = parse_snapshot(copy.deepcopy(self.case["rows"][-1]), races)
        self.assertEqual(board.floor_key[2], self.QUEST)
        self.assertNotIn("telepathy", board.player.abilities)
        reasons = {row["reason"] for row in self.case["decisions"]}
        self.assertTrue(reasons <= {"search", search.DOOR_REASON, search.LOOP_REASON}, reasons)

    def test_the_grids_are_the_walk_and_its_walls_not_the_rock(self):
        policy, races, raw, _ = replay(self.case)
        board = parse_snapshot(copy.deepcopy(raw), races)
        self.assertTrue(search.no_means(policy, board))
        routes = search._routes(policy, board)
        grids = search.sweep_grids(policy, board, routes)
        walk = np.zeros(grids.shape, dtype=bool)
        for cell in routes:
            walk[cell.y, cell.x] = True
        self.assertTrue((grids & walk).sum() == walk.sum())
        # Every grid of the set is walkable or touches a walkable grid: no rock inside.
        self.assertFalse((grids & ~search_coverage.beside(walk)).any())
        self.assertLess(grids.sum(), search_coverage.floor_grids(board).sum())


class Search44fRecordedTest(_SearchWalk, unittest.TestCase):
    """life-508 08:24, Angband 44F, RANDOM quest 47."""

    NAME, QUEST, LIMIT, SWEEPS = "search-44f-0824", 47, 900, search.SWEEPS_TO_GIVE_UP

    def test_two_coverages_give_the_floor_up(self):
        policy, board, reasons = self.walk(self.LIMIT)
        self.assertGreaterEqual(getattr(policy, search.MEMORY).sweeps.count, search.SWEEPS_TO_GIVE_UP)
        self.assertIn(search.LOOP_REASON, reasons)
        # The door search round a complete coverage starts comes before the give-up.
        self.assertIsNotNone(self.after_first)
        self.assertEqual(getattr(policy, search.MEMORY).door_sweep, 1)
        self.assertIn("search", reasons[self.after_first:])
        # The release is the coverage's, not the stall bound's.
        self.assertLess(policy._stuck_escape_streak, STUCK_ESCAPE_LIMIT)
        self.assertFalse(policy._quest_floor_exit_locked(board))
        self.assertFalse(search.searching(policy, board))


class Search12fRecordedTest(_SearchWalk, unittest.TestCase):
    """life-507 18:52, Angband 12F, RANDOM quest 43."""

    NAME, QUEST, LIMIT, SWEEPS = "search-12f-1852", 43, 900, 1

    def walk(self, limit):
        # DECLARED: no plain laps before the walk, for time (six laps of this floor are thousands
        # of decisions); the laps first are pinned by Search44fRecordedTest and
        # tests/test_quest_target_search_1105.py.
        with mock.patch.object(search, "SWEEP_WALK_AFTER_LAPS", 0):
            return super().walk(limit)

    def test_the_first_coverage_completes(self):
        policy, _, reasons = self.walk(self.LIMIT)
        self.assertEqual(getattr(policy, search.MEMORY).sweeps.count, 1)
        self.assertIn(search.LOOP_REASON, reasons)


if __name__ == "__main__":
    unittest.main()
