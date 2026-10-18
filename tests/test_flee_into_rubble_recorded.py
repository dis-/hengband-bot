"""Replay the C4-A no-wait flee into a pile of rubble (issue #75).

Fixture rows (copied as-is, raw encoding):
  0: state row 72 of c4a-loops-20261016/20261019-062555-loop-detected (turn
     3407514, random-quest floor (1, 24, 41), Level 30, HP 600/600).  Two
     蛇人間 (race 364) at (16,41) and (17,42) have a line of fire; the only
     neighbour farther from them is the rubble (terrain 49) north at (11,38).
     The recorded decision was '8' no-wait:flee, refused twelve times with
     "岩石が行く手をはばんでいる。" until the loop detector stopped the bot.
  1: state row 71 of .../20261019-062620-loop-detected (turn 3407549): the
     same square after the restart, one 蛇人間 at (15,40); recorded '8'
     no-wait:flee, again refused twelve times.

DECLARED CONSTRUCTED: the runtime state a single row cannot carry -- the ~f
skill-exp cache and the fixed-quest speed potion already tried (the recorded
policy had tried it); the refused-dig test reposts the same board at the same
turn (the dig spent no game turn); in the open-floor control the rubble north
of the player is replaced by the floor grid the player stands on.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "flee-into-rubble-20261019.jsonl.gz"
SHA256 = "8e7da7da8d97524032d1e38f3b0ec1231f8289f448fd3a77b7a43fa84a0a5301"
SERPENT_MAN = 364
RUBBLE_TERRAIN = 49
HERE = Position(12, 38)
NORTH = Position(11, 38)


class FleeIntoRubbleRecordedTest(unittest.TestCase):
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
        # DECLARED CONSTRUCTED: the quest speed potion was already tried.
        self.policy._fixed_quest_speed_attempted = True

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

    def _assert_recorded_board(self, board, turn, hostiles):
        self.assertEqual(board.turn, turn)
        self.assertEqual(board.player.position, HERE)
        self.assertEqual((board.player.hp, board.player.max_hp), (600, 600))
        self.assertEqual(
            [(m.race_id, m.position) for m in board.visible_monsters], hostiles
        )
        rubble = board.grid_at(NORTH)
        self.assertEqual(rubble.terrain_id, RUBBLE_TERRAIN)
        self.assertTrue(rubble.is_rubble)
        self.assertFalse(rubble.passable)

    def test_recorded_flee_tunnels_the_rubble_instead_of_walking_into_it(self):
        board = self._board(0)
        self._assert_recorded_board(
            board, 3407514,
            [(SERPENT_MAN, Position(16, 41)), (SERPENT_MAN, Position(17, 42))],
        )
        self.assertEqual(
            (self.policy.choose_key(board), self.policy.last_reason),
            ("T8", "no-wait:flee"),
        )

    def test_recorded_restart_board_tunnels_the_rubble(self):
        board = self._board(1)
        self._assert_recorded_board(
            board, 3407549, [(SERPENT_MAN, Position(15, 40))]
        )
        self.assertEqual(
            (self.policy.choose_key(board), self.policy.last_reason),
            ("T8", "no-wait:flee"),
        )

    def test_refused_dig_is_not_repeated(self):
        keys = []
        for _ in range(6):
            board = self._board(0)
            keys.append((self.policy.choose_key(board), self.policy.last_reason))
        self.assertNotIn(("8", "no-wait:flee"), keys)
        self.assertEqual(keys[:4], [("T8", "no-wait:flee")] * 4)
        self.assertEqual(keys[4:], [("1", "no-wait:least-visited")] * 2)

    def test_control_flee_over_open_floor_is_unchanged(self):
        board = self._board(0)
        grids = dict(board.grids)
        # DECLARED CONSTRUCTED: open floor where the rubble was.
        grids[NORTH] = replace(grids[HERE], position=NORTH)
        board = replace(board, grids=grids)
        # Open floor lets the summoner rung retreat before any WAIT exists,
        # so the control drives the no-wait rewrite of the recorded hold.
        self.policy._build_grid_index(board)
        self.policy.last_reason = "summoner:hold-choke"
        self.assertEqual(
            (
                self.policy._forbid_wait_while_damaged(board, "5"),
                self.policy.last_reason,
            ),
            ("8", "no-wait:flee"),
        )


if __name__ == "__main__":
    unittest.main()
