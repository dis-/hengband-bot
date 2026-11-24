"""The 100F stand is re-aimed at the target where it is, and a melt that changed nothing is not
made again (n1-c life-221, Angband 100F, 2026-11-24 14:46:51-14:47:11, the halt loop-detected).

At 14:46:51 the stand (26,55) was drawn on the ray south of the Serpent of Chaos, last seen at
(10,55).  On reaching it (14:47:05) the Serpent was shown at (26,50)/(25,50), 5 cells west, in the
vault's permanent rock; the stand's walls were still read toward (10,55): Stone to Mud north
('mBg8') at (22,55), a grid the board did not show, 47 times with no wall melted (no
「溶けて泥になった」), until the loop detector stopped the run.

Fixture finale-melt-repeat-n1c-221-1124 (tests/extract_finale_melt_repeat_1124_fixture.py): the
halt capture's player_turn boards from the 14:45 restart to the halt, 1133 boards (those before
14:46:51 build the map memory the stand's cell is read from), replayed open-loop
(tests/support/finale_416: DECLARED RECONSTRUCTED device lists and expedition mark; DECLARED: the
expedition's Restore Mana count held at 0).  DECLARED RECONSTRUCTED: on the board of 14:46:51
(turn 6271715) the battle of that decision record (phase battle, last seen (10,55), the stand
(26,55) on the ray south of it, distance 16; the stalemate's state cleared).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest

from hengbot import angband_finale, angband_finale_battle
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-melt-repeat-n1c-221-1124.jsonl.gz"
STAND = (26, 55)
STAND_DRAWN = 6271715  # 14:46:51
UNSHOWN = (22, 55)


class FinaleMeltRepeatRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.boards = finale_416.boards(FIXTURE)
        held_policy, drawn = [], []

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            battle = angband_finale_battle.battle(policy, board)
            if not held_policy:
                battle.phase = angband_finale_battle.BATTLE
            if board.turn == STAND_DRAWN and not drawn:
                drawn.append(board.turn)
                angband_finale_battle._end_stalemate(battle)
                battle.phase = angband_finale_battle.BATTLE
                battle.last_seen = (10, 55)
                battle.stand = angband_finale_battle.Stand(STAND, (10, 55), (1, 0), 16)
            held_policy[:] = [policy]

        cls.rows = finale_416.drive(cls.boards, cls.monrace, prepare=prepare)
        cls.policy = held_policy[0]

    def test_no_melt_on_the_stand_away_from_the_target(self):
        melts = [row[:4] for row in self.rows if row[1] == STAND
                 and (row[3] or "").startswith(angband_finale_battle.MELT_REASON)]
        # The recorded run: 47 melts north on (26,55) (revert: the melts north come back).
        self.assertEqual(melts, [])

    def test_the_stand_is_re_aimed_on_a_ray_only(self):
        self.assertEqual(angband_finale_battle._ray(STAND, (26, 50)), ((0, 1), 5))
        self.assertIsNone(angband_finale_battle._ray(STAND, (25, 50)))
        self.assertEqual(angband_finale_battle._ray(STAND, (10, 55)), ((1, 0), 16))

    def test_a_melt_that_changed_nothing_is_not_made_again(self):
        # DECLARED CONSTRUCTED: the recorded board on the stand after a melt north at (22,55)
        # (no message, the grid still not shown), as the 47 recorded ones.
        raw = copy.deepcopy(next(board for board in self.boards
                                 if (board["player"]["y"], board["player"]["x"]) == STAND))
        board = parse_snapshot(raw, self.monrace)
        held = angband_finale_battle.battle(self.policy, board)
        held.melt_aim = (board.turn - 1, UNSHOWN)
        angband_finale_battle._note_dud_melt(board, held)
        self.assertIn(Position(*UNSHOWN), angband_finale_battle._duds(held))
        self.assertIsNone(angband_finale_battle._battle_melt(self.policy, board,
                                                             Position(*UNSHOWN)))


if __name__ == "__main__":
    unittest.main()
