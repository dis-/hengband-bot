"""n1-b life-365 2026-11-10 15:09: the fundraising return keeps the exit it chose.

Recorded stop (C:/hengband-backups/pdca/captures/stops-1110/n1-b/life-365/captures/
20261110-150915-loop-detected): Yeek cave 1F, the mining run returning, Lv32 Magic-Eater.
From [24,47] the stairs walk (``fundraise:seek-upstairs``) stepped '8' to [23,47]; from
[23,47] the door route (``fundraise:seek-upstairs-door``) stepped '2' back toward the closed
door at [27,47]; 40 decisions until the loop detector.

``RecordedExitTest`` (recorded): tests/fixtures/yeek-exit-loops-1110/upstairs-1509.json.gz
(tests/extract_yeek_exit_loops_1110_fixtures.py), the capture's 65 boards and decision rows
with the remembered terrain of its incident twin (policy-state.json; DECLARED
RECONSTRUCTION, as stops-1109 and n1c-183).  A fresh policy is fed the boards through
``choose_key`` (the observations and the terrain index); the decision under test is the
fundraising return's exit, ``_leave_fundraising_floor``, asked on each recorded board on that
same policy.  DECLARED COMPONENT PIN: the live build (c6e2443b2) carried the Anaguma code
since reverted on main, and on main's ``choose_key`` the combat rung fires at the floating
eye on these boards before the fundraising rung; asked directly, the exit reproduces the
recorded '8' / '2' alternation on the unfixed code (the A side asserted in ``test_the_exit_from_a_does_not_undo_b``).

``ReturnKeepsItsExitTest`` (DECLARED CONSTRUCTED, a component pin): the board is built to the recorded shape:
two up staircases, the near one (north) by a plain walk, the far one through a closed door
(south); and the walk veto of the one cell nearer a sleeping threat cuts the north way, as
the routes' veto does inside a sleeper's area (``_engagement_danger_cells``: the cells
nearer it than the player).  DECLARED WALL: ``_walk_veto`` is that rule over the built
board (the live veto's monster memory is not in the capture).  Every decision is the
production ``_leave_fundraising_floor`` on a fresh terrain index of the board
(``_build_grid_index``, as ``choose_key`` builds it); the latch is created by that same
producer on the same policy.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from policy_fixtures import grid, player

from hengbot.model import DUNGEON_YEEK_CAVE, Position, Snapshot, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.model import PLAYER_CLASS_WARRIOR
from tests.test_dungeon_1031_recorded import skill
from tests.test_n1b_348_stops_1108_recorded import knowledge

X = 5
NORTH_STAIRS = Position(2, X)
SLEEPER = Position(1, X)
B = Position(8, X)  # the cell inside the sleeper's area ([23,47] live)
A = Position(9, X)  # the cell outside it ([24,47] live)
DOOR = Position(11, X)
FAR_ROUTE = [Position(12, X + dx) for dx in range(0, 10)]
SOUTH_STAIRS = Position(13, X + 9)
AREA = 7


def cdis(a, b):
    dy, dx = abs(a.y - b.y), abs(a.x - b.x)
    return dy + (dx >> 1) if dy > dx else dx + (dy >> 1)


def board(at):
    cells = {Position(y, X) for y in range(2, 11)} | set(FAR_ROUTE) | {SOUTH_STAIRS}
    grids = {}
    for y in range(0, 15):
        for x in range(0, 17):
            pos = Position(y, x)
            if pos == DOOR:
                grids[pos] = grid(y, x, passable=False, closed_door=True)
            elif pos in cells:
                grids[pos] = grid(y, x, upstairs=pos in (NORTH_STAIRS, SOUTH_STAIRS),
                                  in_view=True)
            else:
                grids[pos] = grid(y, x, passable=False)
    return Snapshot(player(at.y, at.x, class_id=PLAYER_CLASS_WARRIOR), grids, [],
                    floor_key=(DUNGEON_YEEK_CAVE, 1, 0), turn=1000 + at.y)


def sleeper_veto(snapshot):
    """Inside the sleeper's area, the cells nearer it than the player."""
    here = snapshot.player.position
    reach = cdis(here, SLEEPER)
    if reach > AREA:
        return frozenset()
    return frozenset(pos for pos in snapshot.grids if cdis(pos, SLEEPER) < reach)


def step(at, key):
    moves = {"2": (1, 0), "8": (-1, 0)}
    dy, dx = moves[key]
    return Position(at.y + dy, at.x + dx)


class ReturnKeepsItsExitTest(unittest.TestCase):
    def policy(self):
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._returning_to_town = True
        policy._walk_veto = sleeper_veto  # DECLARED WALL (module docstring)
        return policy

    def decide(self, policy, at):
        snapshot = board(at)
        policy._build_grid_index(snapshot)
        return str(policy._leave_fundraising_floor(snapshot)), policy.last_reason

    def test_the_two_exits_disagree_on_the_built_board(self):
        # The recorded pair: the walk at A steps toward B, the door route at B steps back.
        policy = self.policy()
        self.assertEqual(self.decide(policy, A), ("8", "fundraise:seek-upstairs"))
        fresh = self.policy()
        self.assertEqual(self.decide(fresh, B), ("2", "fundraise:seek-upstairs-door"))

    def test_the_return_walks_through_the_door_it_chose(self):
        policy = self.policy()
        at, path = A, []
        for _ in range(4):
            key, reason = self.decide(policy, at)
            path.append((at, key, reason))
            if key in ("2", "8"):
                at = step(at, key)
        # Unfixed: A '8', B '2', A '8', B '2' (the recorded alternation).
        self.assertEqual([(cell, key) for cell, key, _ in path],
                         [(A, "8"), (B, "2"), (A, "2"), (Position(10, X), "o2")])
        self.assertEqual(path[2][2], "fundraise:seek-upstairs-door")
        self.assertEqual(path[3][2], "fundraise:open-upstairs-door")
        self.assertEqual(policy._fundraising_exit_latch,
                         ((DUNGEON_YEEK_CAVE, 1, 0), SOUTH_STAIRS, DOOR))

    def test_another_floor_releases_the_latch(self):
        policy = self.policy()
        self.decide(policy, A)
        self.decide(policy, B)
        snapshot = replace(board(A), floor_key=(DUNGEON_YEEK_CAVE, 1, 1))
        policy._build_grid_index(snapshot)
        policy._leave_fundraising_floor(snapshot)
        self.assertNotEqual(policy._fundraising_exit_latch[0], (DUNGEON_YEEK_CAVE, 1, 0))


FIXTURE = Path(__file__).with_name("fixtures") / "yeek-exit-loops-1110" / "upstairs-1509.json.gz"
LIVE_A, LIVE_B = Position(24, 47), Position(23, 47)
FIRST_ASKED = 3927104  # [24,46]: the step onto [23,47] that begins the alternation
LOOP_BOARDS = range(3927114, 3927175)  # the recorded '2' / '8' alternation up to [24,47]'s '2'
TERRAIN_SETS = ("known", "marked", "floor", "wall", "door", "rubble")


def recorded_case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class RecordedExitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = recorded_case()

    def exits(self):
        """The return's exit on every recorded board from FIRST_ASKED (module docstring)."""
        races = knowledge(self.case)
        policy = HengbotPolicy(monrace_knowledge=races)
        boards = self.case["rows"]
        first = copy.deepcopy(boards[0])
        policy.prime(parse_snapshot(first, races))
        terrain = self.case["terrain"]
        for name in TERRAIN_SETS:
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
        skill(policy, first)
        # DECLARED RECONSTRUCTED: the mining run's return, as the recorded objective shows.
        policy._fundraising_mode = "mine"
        policy._returning_to_town = True
        rows = []
        for raw in boards:
            snapshot = parse_snapshot(copy.deepcopy(raw), races)
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(str(key))
            if raw["turn"] >= FIRST_ASKED:
                exit_key = str(policy._leave_fundraising_floor(snapshot))
                rows.append((raw["turn"], snapshot.player.position, exit_key,
                             policy.last_reason, policy._fundraising_exit_latch))
        return rows

    def test_recorded_rows(self):
        recorded = {row["turn"]: (row["key"], row["reason"]) for row in self.case["decisions"]}
        positions = {raw["turn"]: Position(raw["player"]["y"], raw["player"]["x"])
                     for raw in self.case["rows"]}
        for turn in LOOP_BOARDS:
            if turn not in recorded:
                continue
            expected = ({LIVE_A: ("8", "fundraise:seek-upstairs"),
                         LIVE_B: ("2", "fundraise:seek-upstairs-door")}[positions[turn]])
            if turn != 3927182:
                self.assertEqual(recorded[turn], expected, turn)

    def test_the_exit_from_b_steps_to_a(self):
        # The exit asked on the recorded boards reproduces the recorded alternation's B side
        # on the fixed code too ('2' from [23,47]); see the A side below.
        rows = [row for row in self.exits() if row[0] in LOOP_BOARDS]
        self.assertTrue(rows)
        for _turn, position, key, _reason, _latch in rows:
            if position == LIVE_B:
                self.assertEqual(key, "2")

    def test_the_exit_from_a_does_not_undo_b(self):
        rows = [row for row in self.exits() if row[0] in LOOP_BOARDS]
        a_keys = {key for _turn, position, key, _reason, _latch in rows if position == LIVE_A}
        # Unfixed: '8', back to [23,47] (the recorded alternation).
        self.assertTrue(a_keys)
        self.assertNotIn("8", a_keys)
        latches = {latch for *_rest, latch in rows}
        self.assertEqual(len(latches), 1, latches)
        (latch,) = latches
        self.assertEqual(latch[0], (DUNGEON_YEEK_CAVE, 1, 0))


if __name__ == "__main__":
    unittest.main()
