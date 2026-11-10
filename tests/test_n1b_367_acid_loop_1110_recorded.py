"""n1-b life-367 2026-11-10 20:11 loop-detected (Orc cave 23F, build bot-c6308419e).

Recorded: tests/fixtures/n1b-367-acid-loop-1110.json.xz
(tests/extract_n1b_367_acid_loop_1110_fixture.py).  Every decision is the public ``choose_key``
of a policy built as the live one (tests.support.recorded._policy).

West of (45,61) lies a shallow acid puddle (浅い酸の沼, terrain 232, ACID_PUDDLE: hp-mp-processor.cpp
deals its damage every 10 game turns, ``deal_damege_by_feat``); across it the open door (42,56)
of the ogres' room, held by a black ogre (race 262, no IM_ACID, so monster-info.cpp
``monster_can_cross_terrain`` keeps it off the puddle).  The exploration stepped '1' onto the
puddle; there the ogre came into view and each shot at it became the step off
(damaging_ground.leave_first): '7' to (45,59), then '6' and '6' back to (45,61), because every
safe cell the puddle reaches lay on the dry ground the walk came from (``_left_ground``); and the
exploration (or breakout:seek-frontier) walked in again, until the loop guard.  Now a step off
that cannot cross gives the crossing up for the floor visit: the hazard ground connected to the
player is claimed as the engagement retreats claim the cells they leave, and every walker keeps
off it (``_walk_veto``).

DECLARED RECONSTRUCTION: the policy is primed on the ring's board of the player on (45,61) and
decides the recorded boards of one round of the loop.  The ground left behind is the live
process's: the dirt around (terrain 88, no REMEMBER) leaves the board out of view, and the live
process had seen it before the ring began, so every floor cell of the stop's remembered terrain
that a board does not show is put on it as remembered dirt; the stop's remembered terrain and
visit counts are seeded (as tests.test_dungeon_stops_1103_recorded's SEEDS).  With them the step
off decides '7', '6', '6' as recorded.
DECLARED COUNTERFACTUAL (the exploration's goal): the live exploration's goal lay past the
puddle (its recorded goal, the frontier (45,54) in the ogres' room, came from boards before the
ring), so every remembered frontier outside the ogres' room is taken as one the exploration
refused (``_unenterable_explore_goals`` with the board's signature).  With it the exploration
steps '1' onto the puddle as recorded, and the whole round decides as recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import damaging_ground
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-367-acid-loop-1110.json.xz"
STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}
STEP_OFF = damaging_ground.STEP_REASON
ACID, DIRT = 232, 88
DRY, BACK = Position(45, 61), 5143191
WET_TURNS = (5143180, 5143183, 5143187)
DOOR = Position(42, 56)
ROOM = (range(40, 57), range(36, 58))   # the ogres' room and its doors


class AcidCrossingRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.recorded = {row["turn"]: (row["key"], row["reason"]) for row in cls.case["decisions"]}
        cls.floor = {tuple(cell) for cell in cls.case["terrain"]["floor_t"]}

    def board(self, turn):
        return copy.deepcopy(next(raw for raw in self.case["boards"] if raw["turn"] == turn))

    def remembered(self, raw):
        """The board with the dirt the live process remembered (DECLARED RECONSTRUCTION)."""
        raw = copy.deepcopy(raw)
        grid_map = raw["grid_map"]
        shown = {(y, x) for y, x0, length, _index in grid_map["runs"] for x in range(x0, x0 + length)}
        dirt = next(index for index, entry in enumerate(grid_map["palette"])
                    if entry[0] == DIRT and entry[1] == 1)
        grid_map["runs"].extend([y, x, 1, dirt] for y, x in sorted(self.floor - shown))
        return raw

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.remembered(self.case["boards"][0])
        policy.prime(parse_snapshot(copy.deepcopy(first), self.monrace))
        policy.consume_skill_knowledge({
            "player": {"level": first["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        # SEEDS: the stop's remembered terrain and visit counts.
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in self.case["terrain"][f"{name}_t"])
        for row in self.case["visits"]:
            policy._visit_counts[Position(*row["key"])] = row["count"]
        return policy

    def decide(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(self.remembered(raw)), self.monrace)
        key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return board, key

    def round(self):
        """(policy, rows of (position, key, reason)) for the fixture's round of the loop."""
        policy = self.policy()
        first = parse_snapshot(copy.deepcopy(self.remembered(self.case["boards"][0])), self.monrace)
        board = policy._with_grid_memory(first)
        cells = {Position(y, x) for y, x in policy._floor_t | policy._door_t | policy._rubble_t}
        for cell in cells | set(board.grids):
            if (cell.y not in ROOM[0] or cell.x not in ROOM[1]) and policy._is_remembered_frontier(board, cell):
                # DECLARED COUNTERFACTUAL (module docstring).
                policy._unenterable_explore_goals[cell] = policy._explore_goal_signature(board.grid_at(cell))
        rows = []
        for raw in self.case["boards"]:
            board, key = self.decide(policy, raw)
            rows.append((board.player.position, key, policy.last_reason))
        return policy, board, rows

    def test_recorded_round(self):
        rows = [(raw["player"]["y"], raw["player"]["x"], self.recorded[raw["turn"]])
                for raw in self.case["boards"]]
        self.assertEqual(rows, [
            (45, 61, ("1", "explore")),
            (46, 60, ("7", STEP_OFF)),
            (45, 59, ("6", STEP_OFF)),
            (45, 60, ("6", STEP_OFF)),
            (45, 61, ("1", "explore")),
        ])
        for turn in WET_TURNS:
            raw = self.board(turn)
            board = parse_snapshot(copy.deepcopy(raw), self.monrace)
            self.assertEqual(board.grid_at(board.player.position).terrain_id, ACID)
            self.assertIn((DOOR.y, DOOR.x), [(m["y"], m["x"]) for m in raw["visible_monsters"]])
        self.assertEqual(self.board(BACK)["visible_monsters"], [])

    def test_the_round_decides_as_recorded(self):
        _policy_, _board, rows = self.round()
        self.assertEqual([(key, reason) for _here, key, reason in rows[:4]],
                         [self.recorded[raw["turn"]] for raw in self.case["boards"][:4]])

    def test_a_given_up_crossing_is_not_walked_again(self):
        policy, board, rows = self.round()
        here, key, reason = rows[-1]
        self.assertEqual(here, DRY)
        offset = STEPS.get((key or "").lstrip(""))
        if offset is not None:
            step = Position(DRY.y + offset[0], DRY.x + offset[1])
            self.assertFalse(damaging_ground.hurts_at(policy, board, step), (key, reason))
        # Every walker keeps off the puddle the step off gave up.
        veto = policy._walk_veto(board)
        for turn in WET_TURNS:
            raw = self.board(turn)
            self.assertIn(Position(raw["player"]["y"], raw["player"]["x"]), veto)

    def test_the_way_back_off_a_given_up_puddle_is_still_walked(self):
        # Back on the puddle at (45,59) (as the live walk was, turn 5143199) after the
        # crossing was given up, the step off still walks the puddle back to dry ground.
        policy, _board, _rows = self.round()
        raw = self.board(WET_TURNS[1])
        raw["turn"] = self.case["boards"][-1]["turn"] + 8
        board, key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("6", STEP_OFF))


if __name__ == "__main__":
    unittest.main()
