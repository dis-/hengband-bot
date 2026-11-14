"""A declared walk-out two steps from its up-stair walks on to it instead of fleeing into the swarm.

n1-c life-209 (zombie Magic-Eater Lv8, HP 133/133, no healing or escape item, mining Yeek cave 1F)
died at 2026-11-15 04:52:58 to a giant white mouse swarm (巨大ハツカネズミ, MULTIPLY) and a jackal
pack.  It was walking out to the up-stair at (34,29) (return:seek-upstairs, ``_returning_to_town``)
when, at turn 129065 two steps from the stair, the threat tiers decided the leave and the combat
layer's flee rung walked '9' away from the stair (``_flee_step`` maximises the distance to the
hostiles); four such steps later it stood in the open cave, the swarm grew to 16 around it and it
died there (the Word of Recall read at HP 85 did not activate in time).  walkout_stairs: the flee
rung walks a declared walk-out on to its up-stair when the player reaches it before any hostile
can come beside the route.

Recorded: tests/fixtures/n1c-209-death-1115.jsonl.gz (tests/extract_n1c_209_death_1115_fixture.py),
the live boards 129046-129075, one fresh policy replaying them from the walk-out board 129046
through the public ``choose_key``; the step is posted through the production executor
(``_ExecutorInputPort``).  DECLARED CONSTRUCTED: the boards after the step (the player moved one
cell, the monsters held), and a mouse moved beside the stair for the lost race.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from hengbot import walkout_stairs
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import UP_STAIRS_KEY
from tests.support import recorded as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-209-death-1115.jsonl.gz"
FIXTURE_SHA256 = "ba6b2b25c072eec370ed1f4a0fcc2df3f5f8ced3853c8eb529c890df6ff7c83d"
EDIT = Path(r"C:\hengband\lib\edit")
WALK_OUT, FLEE_BOARD = 129046, 129065
STAIR = Position(34, 29)
MOUSE = 27  # 巨大ハツカネズミ, MonraceDefinitions.jsonc
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


class N1c209Death1115RecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.raw = {board["turn"]: board for board in map(json.loads, stream)}
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")

    def policy(self):
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        return policy

    def board(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.monrace)

    def to_flee_board(self, *, start=WALK_OUT, edit=None):
        """(policy, the 129065 board, its key) after replaying the boards from ``start``;
        ``edit(board)`` returns the 129065 board to decide instead."""
        policy = self.policy()
        for turn in sorted(self.raw):
            if not start <= turn <= FLEE_BOARD:
                continue
            board = self.board(self.raw[turn])
            if turn == FLEE_BOARD and edit is not None:
                board = edit(board)
            key = policy.choose_key(board)
            if turn == FLEE_BOARD:
                return policy, board, key
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError(FLEE_BOARD)

    @staticmethod
    def moved(raw, key, turns=10):
        dy, dx = DIRECTIONS[key]
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + turns, messages=[])
        following["player"] = dict(following["player"], y=raw["player"]["y"] + dy,
                                   x=raw["player"]["x"] + dx)
        return following

    def test_the_live_walk_out_was_declared_two_steps_from_the_stair(self):
        policy, board, _key = self.to_flee_board()
        self.assertEqual((board.player.position, board.player.hp, board.player.max_hp),
                         (Position(32, 27), 133, 133))
        self.assertTrue(walkout_stairs.walkout_declared(policy, board))
        self.assertTrue(board.grid_at(STAIR).has_up_stairs)
        nearest = min(monster.position.distance_to(STAIR) for monster in board.visible_monsters)
        self.assertEqual(nearest, 5)

    def test_the_walk_out_steps_on_to_the_stair_through_the_executor(self):
        policy, _board, key = self.to_flee_board()
        raw = self.raw[FLEE_BOARD]
        self.assertEqual(policy.last_reason, walkout_stairs.REASON)
        self.assertEqual(key, "3")  # (33,28), toward the stair; the live flee was '9'
        self.assertEqual(self.post(policy, raw, key, [], self.moved(raw, key)), ["3"])

    def test_the_next_step_reaches_the_stair_and_climbs_it(self):
        policy, _board, key = self.to_flee_board()
        raw = self.raw[FLEE_BOARD]
        policy.confirm_key_posted(key)
        # DECLARED CONSTRUCTED: the player one cell on, the monsters where they were.
        beside = self.moved(raw, key)
        second = policy.choose_key(self.board(beside))
        # The board after the step reads no leave: the walk-out's own rung walks on.
        self.assertEqual((policy.last_reason, second), ("return:seek-upstairs", "3"))
        policy.confirm_key_posted(second)
        on_stair = self.moved(beside, second)
        self.assertEqual(self.board(on_stair).player.position, STAIR)
        self.assertEqual(policy.choose_key(self.board(on_stair)), UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_a_hostile_beside_the_route_keeps_the_flee_step(self):
        def mouse_by_the_stair(board):
            # DECLARED CONSTRUCTED: the mouse nearest the stair two cells from it, beside the
            # route's first cell (33,28).
            mouse = min((m for m in board.visible_monsters if m.race_id == MOUSE),
                        key=lambda m: m.position.distance_to(STAIR))
            cell = Position(STAIR.y, STAIR.x - 2)
            moved = replace(mouse, position=cell, distance=board.player.position.distance_to(cell))
            return replace(board, visible_monsters=[
                moved if m is mouse else m for m in board.visible_monsters])
        policy, board, key = self.to_flee_board(edit=mouse_by_the_stair)
        self.assertIsNone(walkout_stairs.step(policy, board))
        self.assertEqual((policy.last_reason, key), ("flee", "8"))  # away from the moved mouse

    def test_without_a_declared_walk_out_the_flee_step_is_unchanged(self):
        policy, board, key = self.to_flee_board(start=FLEE_BOARD)
        self.assertFalse(walkout_stairs.walkout_declared(policy, board))
        self.assertEqual((policy.last_reason, key), ("flee", "9"))


if __name__ == "__main__":
    unittest.main()
