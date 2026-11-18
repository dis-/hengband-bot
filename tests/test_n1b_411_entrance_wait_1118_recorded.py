"""n1-b life-411 2026-11-18 14:27:03, no-key-exhausted on the Home entrance (bot 8c523e614).

The Lv50 Magic-Eater (20 of 23 pack slots) stood on the Outpost Home entrance (45,123).  The
town chest pass had opened a chest on the entrance's north-east cell (44,124) and collected
its contents (rows 33-46); the empty chest stayed there.  After the Home errand's atomic
withdrawal (row 49) the decision on row 50 had to step off the entrance.  The step-off picked
the least-visited exit, (44,124), but the walk there is refused by the pack budget (a pile
whose pickup would eat the terminal reserve, town_pack_budget.floor_step_fits) and answered
WAIT; on an entrance that WAIT is the entrance's activation, so the final emitted-envelope seam
refused it as ``town:entrance-wait-refused:...`` with an empty key, and the CLI stopped with
no-key-exhausted.  The other two exits, (45,124) and (46,124), were free.

Fix: the step-off takes the least-visited exit whose walk is a step (policy_town
._town_entrance_step_off_key); row 50 steps east.  The approach's yield (approach_answer,
owner 2026-11-18 Q2) took no part: no approach yielded on these rows.

Recorded: the town-arrival checkpoint of 14:26:45 and all 51 journal rows
(tests/extract_n1b_411_entrance_wait_1118_fixture.py), posted through the live CLI's
owner-retirement entrance (--owner-retired-log-only).  Rows 0-49 are decided through the
public choose_key and compared with the record.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import approach_answer
from hengbot.model import Position
from hengbot.town_pack_budget import floor_step_fits
from support.town_arrival_fixture import load
from test_n1a_530_equip_restore_1118_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-entrance-wait-1118"
STOP_ROW = 50
ENTRANCE = Position(45, 123)
CHEST_CELL = Position(44, 124)


class N1b411EntranceWait1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed, cls.yields = [], []
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row == STOP_ROW:
                cls.board = board
                break
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            cls.yields.append(approach_answer.report(policy))
            post(policy, board, recorded["key"], before)
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_visit_replays_to_the_stop(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[49]["reason"], "home:atomic-withdraw")
        self.assertEqual(
            (self.journal[STOP_ROW]["key"], self.journal[STOP_ROW]["reason"]),
            ("", "town:entrance-wait-refused:town:entrance-step-off:"
                 "home:atomic-withdraw-complete"))
        self.assertEqual(self.yields, [None] * STOP_ROW)

    def test_the_entrance_step_off_walks_past_the_refused_chest(self):
        board = self.board
        self.assertEqual(board.player.position, ENTRANCE)
        self.assertEqual(board.grids[CHEST_CELL].object_count, 1)
        self.assertFalse(floor_step_fits(board, CHEST_CELL))

        key = self.policy.choose_key(board)
        self.assertEqual((key, self.policy.last_reason),
                         ("6", "town:entrance-step-off:home:atomic-withdraw-complete"))
        self.assertIsNone(approach_answer.report(self.policy))


if __name__ == "__main__":
    unittest.main()
