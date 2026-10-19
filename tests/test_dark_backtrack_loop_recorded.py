"""Replay the C4-A dark:backtrack / return:explore alternation (issue #81).

Fixture rows (copied as-is, raw encoding) are state rows 75 and 76 of
c4a-loops-20261016/20261019-103828-loop-detected (鉄獄 level 2, floor (1, 2, 0),
Level 24, latched walk-out "Return to town"):

  0: turn 1067563 at (17,67), own grid visible.  Recorded decision 7151
     ``return:explore`` '4' toward the claim goal (62,94), into the unmapped
     corridor cell (17,66).
  1: turn 1067571 at (17,66), own grid not visible.  Recorded decision 7152
     ``dark:backtrack`` '6' back to (17,67).

Both rows: worn 松明 with 0 turns, light radius 0, no oil, no spare torch,
帰還の詔の巻物 x10 in slot f.  The pair repeated 23 times until the loop
detector stopped the bot.

DECLARED CONSTRUCTED: the return latch (policy runtime state, not captured),
the ~f skill-exp cache, the return explore step: ``_explore_step`` is patched
to the recorded first step (17,66) toward the claim goal (62,94) -- the live
policy routed it over remembered cells one board does not carry -- and in the
controls the light radius / a fuelled pack torch.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import unittest
from unittest import mock
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "dark-backtrack-loop-20261019.jsonl.gz"
SHA256 = "68d2156e760b2e6f193e8eeab0b2a4ca4f1ae10258544854bf7d67941d1bdd98"
LIT = Position(17, 67)
DARK = Position(17, 66)
READ_RECALL_FROM_F = "rf"


class DarkBacktrackLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.lines = gzip.decompress(data).decode("utf-8").splitlines()
        assert len(cls.lines) == 2
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)
        self.policy._crossarea_fundraising_enforced = True

    def _board(self, index):
        _decoded, snapshots = _consume_response_sequence(
            [self.lines[index]], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        board = snapshots[-1]
        # DECLARED CONSTRUCTED: the ~f skill-exp cache.
        self.policy._skill_exp_cache = (
            0, 0, board.player.level, self.policy._town_visit_epoch
        )
        return board

    def _latch_walk_out(self):
        # DECLARED CONSTRUCTED: the latched return of the recorded walk and the
        # recorded explore step into (17,66) toward the claim goal (62,94).
        self.policy._returning_to_town = True
        self.policy._escape_state.enter("return", "return:explore")
        explore = mock.patch.object(
            self.policy, "_explore_step", return_value=DARK
        )
        explore.start()
        self.addCleanup(explore.stop)

    def _decide(self, board):
        return self.policy.choose_key(board), self.policy.last_reason

    def test_fixture_is_the_recorded_lightless_pair(self):
        lit, dark = self._board(0), self._board(1)
        self.assertEqual((lit.turn, dark.turn), (1067563, 1067571))
        self.assertEqual((lit.player.position, dark.player.position), (LIT, DARK))
        for board in (lit, dark):
            self.assertEqual(board.floor_key, (1, 2, 0))
            self.assertEqual(board.light_radius, 0)
            light = next(item for item in board.equipment if item.is_light)
            self.assertTrue(light.is_torch)
            self.assertEqual(light.fuel, 0)
            self.assertIsNone(self.policy._light_refill_item(board))
            self.assertIsNone(self.policy._darkness_torch(board))
            recall = self.policy._find_recall_scroll(board)
            self.assertEqual((recall.slot, recall.count), ("f", 10))
        self.assertFalse(self.policy._is_dark(lit))
        self.assertTrue(self.policy._is_dark(dark))
        self.assertIsNone(dark.grid_at(DARK))

    def test_recorded_lit_board_reads_recall_instead_of_stepping_into_the_dark(self):
        board = self._board(0)
        self._latch_walk_out()
        self.assertEqual(self._decide(board), (READ_RECALL_FROM_F, "return:recall"))

    def test_recorded_pair_no_longer_alternates(self):
        lit = self._board(0)
        self._latch_walk_out()
        first = self._decide(lit)
        dark = self._board(1)
        second = self._decide(dark)
        # 8a1f6bba: ('4', 'return:explore') then ('6', 'dark:backtrack') -- the
        # backtrack undoes the walk's step and the pair repeats.
        self.assertEqual(
            [first, second],
            [(READ_RECALL_FROM_F, "return:recall"), ("6", "dark:backtrack")],
        )

    def test_control_recorded_dark_board_still_backtracks_to_the_lit_cell(self):
        board = self._board(1)
        self.policy._returning_to_town = True
        self.policy._escape_state.enter("return", "return:explore")
        self.assertEqual(self._decide(board), ("6", "dark:backtrack"))
        self.assertEqual(self.policy._dark_route_goal, LIT)

    def test_control_own_light_keeps_the_shallow_walk_out(self):
        board = self._board(0)
        # DECLARED CONSTRUCTED: the character lights radius 1.
        board = replace(board, light_radius=1)
        self._latch_walk_out()
        self.assertEqual(self._decide(board), ("4", "return:explore"))

    def test_control_fuelled_pack_torch_keeps_the_shallow_walk_out(self):
        board = self._board(0)
        worn = next(item for item in board.equipment if item.is_light)
        # DECLARED CONSTRUCTED: a fuelled torch in a free pack slot.
        used = {item.slot for item in board.inventory}
        slot = next(
            letter for letter in "abcdefghijklmnopqrstuvw" if letter not in used
        )
        torch = replace(worn, slot=slot, fuel=2500, name="松明(2500ターンの寿命)")
        board = replace(
            board, inventory=type(board.inventory)((*board.inventory, torch))
        )
        self.assertIs(self.policy._darkness_torch(board), torch)
        self._latch_walk_out()
        self.assertEqual(self._decide(board), ("4", "return:explore"))


if __name__ == "__main__":
    unittest.main()
