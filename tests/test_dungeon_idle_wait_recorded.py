"""Replay the recorded dungeon idle board with captured search-loop context.

The board is captured. The repeated stationary history, exhausted searches,
and summoner retreat vetoes are DECLARED CONSTRUCTED because bot-decisions does
not serialize the policy checkpoint that held them.
"""

from __future__ import annotations

import tests  # noqa: F401

import gzip
import json
import unittest
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import MonsterState, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import EXTENDED_STUCK_WINDOW, HengbotPolicy, SEARCH_LIMIT


FIXTURE = Path(__file__).parent / "fixtures" / "dungeon-idle-wait-20261017.jsonl.gz"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")


class DungeonIdleWaitRecordedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.raw = json.loads(next(stream))
        cls.knowledge = load_monrace_knowledge(MONRACES)
        cls.captured = parse_snapshot(cls.raw, cls.knowledge)

    def policy_at_stuck_dead_end(self, snapshot):
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy.prime(snapshot)
        policy._build_grid_index(snapshot)
        here = snapshot.player.position

        # DECLARED CONSTRUCTED: decision history reports eight searches at this
        # tile and repeated confinement; bot-decisions does not serialize the
        # search, visit, probe, or choke-avoidance checkpoint.
        policy._search_counts[(here.y, here.x)] = SEARCH_LIMIT
        policy._stuck_escape_streak = 7
        policy._recent = deque(
            [here] * EXTENDED_STUCK_WINDOW,
            maxlen=EXTENDED_STUCK_WINDOW,
        )
        policy._visit_counts = Counter(
            {Position(y, x): 1 for y, x in policy._remembered_floor_t}
        )
        policy._probed_frontiers.update(
            Position(y, x) for y, x in policy._remembered_floor_t
        )
        policy._search_counts[(here.y, here.x)] = SEARCH_LIMIT
        for wall in policy._remembered_wall_t:
            policy._wall_search_counts[wall] = SEARCH_LIMIT
        for neighbor in policy._walkable_neighbors(snapshot, here):
            policy._engagement_avoid_cells.add(neighbor)
            policy._engagement_owned_avoid_cells.add(neighbor)
        for wall in policy._remembered_wall_t:
            policy._wall_search_counts[wall] = SEARCH_LIMIT
        policy.last_reason = "search"
        return policy

    def test_captured_dead_end_does_not_idle_after_searches_are_exhausted(self):
        self.assertEqual(self.captured.turn, 973783)
        self.assertEqual(self.captured.player.position, Position(38, 4))
        self.assertEqual(self.captured.floor_key, (2, 13, 0))
        self.assertEqual(self.raw["visible_monsters"], [])
        self.assertEqual(self.raw["floor"]["level"], 13)

        policy = self.policy_at_stuck_dead_end(self.captured)
        self.assertIsNotNone(policy._find_recall_scroll(self.captured))
        self.assertEqual(len(policy._remembered_floor_t), 9)
        self.assertEqual(len(policy._probed_frontiers), 9)
        self.assertEqual(policy._search_counts[(38, 4)], SEARCH_LIMIT)
        self.assertEqual(
            sorted((p.y, p.x) for p in policy._engagement_avoid_cells),
            [(37, 4), (37, 5), (38, 5)],
        )
        self.assertIsNone(policy._probe_unknown_step(self.captured))
        self.assertIsNone(policy._explore_step(self.captured))
        self.assertIsNone(policy._least_visited_neighbor(self.captured))

        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(self.captured)

        self.assertEqual(key, "rh")
        self.assertEqual(policy.last_reason, "stuck:recall-escape")

    def test_threat_still_takes_combat_priority(self):
        position = Position(37, 4)
        grids = dict(self.captured.grids)
        grids[position] = grids[position].__class__(
            **{
                **grids[position].__dict__,
                "has_monster": True,
                "monster_index": 1,
            }
        )
        threat = MonsterState(
            index=1,
            position=position,
            hp=30,
            max_hp=30,
            distance=1,
            friendly=False,
            pet=False,
            max_melee_damage=5,
        )
        board = self.captured.__class__(
            **{
                **self.captured.__dict__,
                "grids": grids,
                "visible_monsters": [threat],
            }
        )
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy.prime(board)

        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(board)

        self.assertEqual(key, "8")
        self.assertEqual(policy.last_reason, "melee")

    def test_fully_explored_floor_still_routes_to_known_up_stair(self):
        here = self.captured.player.position
        stair_position = Position(here.y, here.x + 1)
        grids = dict(self.captured.grids)
        for position, grid in tuple(grids.items()):
            if grid.object_count:
                grids[position] = replace(grid, object_count=0, object_tvals=())
        stair = grids[stair_position]
        grids[stair_position] = stair.__class__(
            **{**stair.__dict__, "has_up_stairs": True}
        )
        board = replace(self.captured, grids=grids, found_items=())
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy.prime(board)
        policy._build_grid_index(board)
        policy._visit_counts = Counter(
            {Position(y, x): 1 for y, x in policy._remembered_floor_t}
        )
        policy._probed_frontiers.update(
            Position(y, x) for y, x in policy._remembered_floor_t
        )
        policy._blocked_unknown.update(
            (here.y + dy, here.x + dx)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if (dy, dx) != (0, 0)
        )
        policy._search_counts[(here.y, here.x)] = SEARCH_LIMIT

        with (
            patch.object(policy, "_skill_exp_request_key", return_value=None),
            patch.object(policy, "_undersearched_walls", return_value=[]),
        ):
            key = policy.choose_key(board)

        self.assertEqual(key, "6", policy.last_reason)
        self.assertEqual(policy.last_reason, "stuck:seek-stairs")


if __name__ == "__main__":
    unittest.main()
