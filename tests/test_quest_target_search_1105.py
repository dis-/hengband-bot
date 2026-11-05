"""A random quest's target not found: the floor is circled, and detection runs on the way.

Owner 2026-11-05: 「ランダムクエストで標的が見つからないときはフロアを周回して探す。既に地図が
完成している場合は全マス探索しない。標的に損傷を与えている場合、悠長な探索をすると回復されて
しまうからである。」, 「この探索モードのとき、邪悪感知や全感知など有効な感知手段があれば定期的に
使って発見を早める」 (quest_target_search).

Recorded: n1-c life-098, Angband 12F, RANDOM quest 43 (鬼殺隊の『先輩』, race 1164, EVIL), the
character, pack and quest rows of tests/fixtures/hunt-detect-1102.json.gz (recorded wandering on
stuck:wander until livelock:exhausted, viewing-incidents-20261102).

DECLARED CONSTRUCTED: the map.  A recorded board shows dark floor it no longer draws, so "the
map is complete" is laid out here: four rooms joined in a ring, the rest known rock.  Also the
player's walk (the player moved as the key says, the board otherwise the same), the devices,
the absorbed powers taken away, the warrior who holds a device (a Magic-Eater absorbs it, and
tests/test_hunt_redetect_1102_recorded.py pins the absorbed rows' spacing), and the next boards
after a device use.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import unittest

from hengbot import hunt_target, me_powers, quest_target_search as search
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, game_distance, parse_snapshot
from tests import test_hunt_detect_1102_recorded as detect

TARGET_RACE = 1164
WARRIOR = 0
ROD_TVAL, ROD_SVAL, STAFF_TVAL, STAFF_SVAL = 66, 6, 55, 15
WALL, FLOOR = 0, 1
PALETTE = [[56, 2, 163840, 1], [1, 2, 416, 1]]
ROOMS = ((5, 9, 5, 20), (5, 9, 60, 75), (30, 34, 60, 75), (30, 34, 5, 20))
HALLS = ((7, 7, 21, 59), (10, 29, 67, 67), (32, 32, 21, 59), (10, 29, 12, 12))
START = (7, 12)
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def _floor_cells():
    return {(y, x) for y0, y1, x0, x1 in (*ROOMS, *HALLS)
            for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}


def _lay_map(raw, unknown=frozenset()):
    """The whole known map of the module docstring on a recorded board."""
    floor = _floor_cells()
    height, width = raw["grid_map"]["h"], raw["grid_map"]["w"]
    raw["grid_map"] = {
        "h": height, "w": width, "palette": copy.deepcopy(PALETTE), "cells": [],
        "found_items": [], "found_item_ids": [], "found_item_names": [],
        "unsafe_rows": ["0" * (width // 4 + 1) for _ in range(height)],
        "runs": [[y, x, 1, FLOOR if (y, x) in floor else WALL]
                 for y in range(height) for x in range(width) if (y, x) not in unknown],
    }
    raw["player"]["y"], raw["player"]["x"] = START
    return raw


def _device(raw, tval, sval, name):
    raw["inventory"].append(dict(
        copy.deepcopy(raw["inventory"][0]), slot="s", tval=tval, sval=sval, count=1, known=True,
        aware=True, fully_known=True, charging=False, charging_count=0, charges=5, pval=5, name=name,
        weight=50))
    return raw


def _next_board(raw, key=None):
    board = copy.deepcopy(raw)
    board["turn"] += 10
    board["messages"] = []
    if key in MOVES:
        board["player"]["y"] += MOVES[key][0]
        board["player"]["x"] += MOVES[key][1]
    return board


class QuestTargetSearchTest(unittest.TestCase):
    setUpClass = classmethod(detect.HuntDetectRecordedTest.setUpClass.__func__)
    case = detect.HuntDetectRecordedTest.case
    recorded_policy = detect.HuntDetectRecordedTest.policy
    choose = detect.HuntDetectRecordedTest.choose

    def policy(self, *devices, unknown=frozenset(), quest_id=None):
        policy, raw = self.recorded_policy("senior-12f-993", keep=lambda use: False)
        policy._me_staff_sequence = MeStaffSequence(absorbed={})
        _lay_map(raw, unknown)
        for device in devices:
            _device(raw, *device)
        if devices:
            raw["player"]["class_id"] = WARRIOR  # DECLARED: a Magic-Eater absorbs a carried device
        if quest_id is not None:
            raw["floor"]["quest_id"] = quest_id
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(board)
        # DECLARED: the player has seen this floor (owner 2026-10-23: seen floor is explored).
        policy._remembered_marked_t.update(
            (y, x) for y in range(board.height) for x in range(board.width) if (y, x) not in unknown)
        return policy, raw

    def walk(self, policy, raw, steps):
        """(key, reason, position when deciding) of each decision, the player walking the keys."""
        rows = []
        for _ in range(steps):
            key = self.choose(policy, raw)
            rows.append((key, policy.last_reason, (raw["player"]["y"], raw["player"]["x"])))
            raw = _next_board(raw, key)
        return rows, raw

    # -- the loop ------------------------------------------------------------

    def test_a_complete_map_is_circled_by_its_stops_not_cell_by_cell(self):
        policy, raw = self.policy()
        rows, _ = self.walk(policy, raw, 170)
        self.assertEqual({reason for _, reason, _ in rows}, {search.LOOP_REASON})
        memory = getattr(policy, search.MEMORY)
        stops = {(stop.y, stop.x) for stop in memory.stops}
        # Each room's middle, and the far halls (out of MAX_SIGHT of every room).
        self.assertTrue({(7, 12), (7, 67), (32, 67), (32, 12)} <= stops, stops)
        self.assertEqual(len(stops), 6)
        walked = {position for _, _, position in rows}
        self.assertTrue({(7, 67), (32, 67), (32, 12)} <= walked)
        room_cells = sum((y1 - y0 + 1) * (x1 - x0 + 1) for y0, y1, x0, x1 in ROOMS)
        self.assertLess(len(walked & {(y, x) for y0, y1, x0, x1 in ROOMS
                                      for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}),
                        room_cells // 4)
        # No bound counts toward a stop or a leave.
        self.assertFalse(policy._nav_exhausted)
        self.assertLessEqual(policy._nav_stall_count, 1)  # the update after the last decision
        self.assertEqual(policy._stuck_escape_streak, 0)

    def test_the_lap_starts_again_when_every_stop_was_seen(self):
        policy, raw = self.policy()
        rows, _ = self.walk(policy, raw, 215)
        self.assertEqual({reason for _, reason, _ in rows}, {search.LOOP_REASON})
        positions = [position for _, _, position in rows]
        # The first room's middle again, after the far corner: a second lap.
        far = positions.index((32, 67))
        self.assertIn((7, 12), positions[far:])

    def test_an_unfinished_map_explores_as_any_floor(self):
        policy, raw = self.policy(unknown=frozenset({(8, 21)}))
        self.assertEqual(self.choose(policy, raw)[:1] in MOVES, True)
        self.assertEqual(policy.last_reason, "explore")

    def test_a_fixed_quest_floor_and_a_released_floor_are_not_circled(self):
        policy, raw = self.policy(quest_id=2)
        self.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, search.LOOP_REASON)
        policy, raw = self.policy()
        policy._unviable_quest_floor = parse_snapshot(
            copy.deepcopy(raw), policy._monrace_knowledge).floor_key
        self.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, search.LOOP_REASON)

    def test_the_last_seen_cell_comes_first_and_then_the_loop(self):
        policy, raw = self.policy()
        self.choose(policy, raw)
        board = _next_board(raw)
        stale = Position(32, 12)
        policy._hunt_target_memory.position = stale
        self.choose(policy, board)
        self.assertEqual(policy.last_reason, hunt_target.REASON)
        policy._hunt_target_memory.position = None  # DECLARED: seen empty on arrival
        self.choose(policy, _next_board(board))
        self.assertEqual(policy.last_reason, search.LOOP_REASON)

    # -- the detection -------------------------------------------------------

    def test_the_rod_is_cast_again_only_past_its_radius(self):
        policy, raw = self.policy((ROD_TVAL, ROD_SVAL, "全感知のロッド"))
        first = self.choose(policy, raw)
        self.assertEqual((first[0], policy.last_reason), ("z", search.DETECT_REASON))
        rows, _ = self.walk(policy, _next_board(raw), 40)
        casts = [index for index, row in enumerate(rows) if row[1] == search.DETECT_REASON]
        self.assertTrue(casts, rows)
        cast_at = rows[casts[0]][2]
        # The landed cast's radius: 30 in a known dungeon; this test's policy knows none, so
        # the smaller reading of me_powers.map_radius (a DARKNESS dungeon's third).
        memory = getattr(policy, search.MEMORY)
        self.assertEqual(memory.casts[0][0], Position(*START))
        radius = memory.casts[0][1]
        self.assertEqual(radius, me_powers.map_radius(
            policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        self.assertGreaterEqual(game_distance(Position(*START), Position(*cast_at)), radius)
        for _, reason, position in rows[:casts[0]]:
            self.assertEqual(reason, search.LOOP_REASON)
            self.assertLess(game_distance(Position(*START), Position(*position)), radius)

    def test_a_means_that_cannot_show_the_target_is_skipped(self):
        evil = (STAFF_TVAL, STAFF_SVAL, "邪悪感知の杖")
        policy, raw = self.policy(evil)
        self.assertEqual(self.choose(policy, raw)[0], "u")
        self.assertEqual(policy.last_reason, search.DETECT_REASON)
        policy, raw = self.policy(evil)
        policy._monrace_knowledge[TARGET_RACE] = replace(
            policy._monrace_knowledge[TARGET_RACE],
            flags=policy._monrace_knowledge[TARGET_RACE].flags - {"EVIL"})
        self.choose(policy, raw)
        self.assertEqual(policy.last_reason, search.LOOP_REASON)

    def test_the_rod_comes_before_the_staff(self):
        policy, raw = self.policy((STAFF_TVAL, STAFF_SVAL, "邪悪感知の杖"), (ROD_TVAL, ROD_SVAL, "全感知のロッド"))
        self.assertEqual(self.choose(policy, raw)[0], "z")

    def test_the_shown_target_is_hunted(self):
        policy, raw = self.policy((ROD_TVAL, ROD_SVAL, "全感知のロッド"))
        self.choose(policy, raw)
        shown = {"index": 77, "race_id": TARGET_RACE, "y": 7, "x": 30, "hp": 100, "max_hp": 100,
                 "distance": 18, "friendly": False, "pet": False, "speed": 110, "name": "target"}
        board = _next_board(raw)
        board["detected_monsters"] = [shown]
        self.assertIn(self.choose(policy, board), MOVES)
        self.assertEqual(policy.last_reason, hunt_target.REASON)
        self.assertEqual(policy._hunt_target_memory.position, Position(7, 30))


if __name__ == "__main__":
    unittest.main()
