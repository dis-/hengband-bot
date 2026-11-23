"""The Castle's climb picks the pile on the cell it stands on with one action (1123).

Owner 2026-11-23 (verbatim choice): 「足元の品だけ1手で拾う — 登りの途中でも、立ったマスの品は1手で拾う。
品の方へ寄り道はしない。敵が隣にいる・見えている召喚の敵がいるなどの時は今までどおり拾わない。」
(deep_climb ``underfoot_key``.)  Until then the climb's rung (deep_climb ``key``, above the loot)
answered the climb's step on every such board: n1-a life-535 left the items of the cells it stood
on during the climb (C:/hengband-backups/pdca/loot-yield-1123/REPORT.md, 案7).

Recorded (tests/extract_climb_underfoot_1123_fixture.py), n1-a life-535 on the Castle's 45F:
  7925931  stepped onto a Potion of Restore Intelligence at (1,44), nothing in view.
           Live: ('4', 'castle-climb:search-upstairs').
  7925886  two items dropped at its feet at (4,49) during the fight before; it had not moved since.
           Live: ('7', 'castle-climb:search-upstairs').  The loot owner's pickup steps off a cell
           the player has not moved on (policy ``_current_floor_item_key``); the climb's does not.
  7936505  a Potion of Restore Intelligence under it at (13,80) with a フレイム・コボルド adjacent:
           the melee as recorded, and the climb's pickup refuses (the adjacent-hostile gate).
  7936513  the same pile after the kobold died, four hostiles in view, none adjacent.
           Live: ('6', 'castle-climb:search-upstairs').

DECLARED CONSTRUCTED: the climb switch is held on the first board (deep_climb ``_hold_climb``):
live held it from the unsafe-recall fallback of the town visit before, which the replay does not
include.  Each window is replayed from its first board as recorded.
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import deep_climb, dive_floor
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "climb-underfoot-1123.jsonl.xz"
CASTLE = 12
ROOM_POTION = 7925931
FIGHT_PILE = 7925886
KOBOLD_ADJACENT = 7936505
KOBOLD_DEAD = 7936513
SECOND_WINDOW = 7936486


class ClimbUnderfoot1123RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        lines = lzma.decompress(FIXTURE.read_bytes()).decode("utf-8").splitlines()
        cls.raws = [json.loads(line) for line in lines if line.strip()]

    def replay(self, until, *, first=None):
        """Replay the window holding ``until`` up to its board; (policy, board) before deciding."""
        raws = [raw for raw in self.raws
                if (raw["turn"] >= SECOND_WINDOW) == (until >= SECOND_WINDOW)]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        start = parse_snapshot(copy.deepcopy(raws[0]), self.monrace)
        policy.prime(start)
        policy._skill_exp_cache = (0, 0, start.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED (module docstring): the climb switch of the recording.
        self.assertTrue(deep_climb._hold_climb(policy, start, CASTLE))
        for raw in raws:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if board.turn == until:
                return policy, board
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError(f"turn {until} not in the fixture")

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def climbing(self, policy, board):
        self.assertEqual(board.floor_key, (CASTLE, 45, 0))
        self.assertEqual(dive_floor.climb_dungeon(policy), CASTLE)
        self.assertTrue(deep_climb.climb_floor(policy, board))

    def test_a_pile_stepped_onto_is_picked_up_with_one_action(self):
        policy, board = self.replay(ROOM_POTION)
        self.climbing(policy, board)
        here = board.grid_at(board.player.position)
        self.assertEqual((board.player.position, here.object_count), (Position(1, 44), 1))
        self.assertEqual([m for m in board.visible_monsters if m.hostile], [])

        key, reason = self.decide(policy, board)

        # Recorded: ('4', 'castle-climb:search-upstairs').
        self.assertEqual((key, reason), ("g", "castle-climb:pickup"))

    def test_items_dropped_at_its_feet_are_picked_up_without_a_step_off(self):
        policy, board = self.replay(FIGHT_PILE)
        self.climbing(policy, board)
        self.assertFalse(policy._position_changed)
        here = board.grid_at(board.player.position)
        self.assertEqual((board.player.position, here.object_count), (Position(4, 49), 2))

        key, reason = self.decide(policy, board)

        # Recorded: ('7', 'castle-climb:search-upstairs').  No step off the cell for the loot.
        self.assertEqual((key, reason), ("gaa", "castle-climb:pickup"))

    def test_an_adjacent_hostile_still_refuses_the_pickup(self):
        policy, board = self.replay(KOBOLD_ADJACENT)
        self.climbing(policy, board)
        self.assertEqual(board.grid_at(board.player.position).object_count, 1)
        self.assertTrue(policy._physical_adjacent_hostiles(board))
        self.assertEqual(policy._loot_block_reason(board, policy._strategic_hostiles(board)),
                         "adjacent-hostile")
        self.assertIsNone(deep_climb.underfoot_key(policy, board, deep_climb.CLIMB_REASON))

        key, reason = self.decide(policy, board)

        self.assertEqual(reason, "melee", key)

    def test_the_pile_is_picked_once_the_adjacent_hostile_is_gone(self):
        policy, board = self.replay(KOBOLD_DEAD)
        self.climbing(policy, board)
        self.assertEqual(board.grid_at(board.player.position).object_count, 1)
        self.assertFalse(policy._physical_adjacent_hostiles(board))
        self.assertTrue([m for m in board.visible_monsters if m.hostile])

        key, reason = self.decide(policy, board)

        # Recorded: ('6', 'castle-climb:search-upstairs').
        self.assertEqual((key, reason), ("g", "castle-climb:pickup"))


if __name__ == "__main__":
    unittest.main()
