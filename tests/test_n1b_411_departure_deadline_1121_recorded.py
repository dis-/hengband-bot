"""n1-b life-411 2026-11-21 05:51: the departure stage's deadline stopped a recall countdown.

Recorded: the town arrival of 05:50:19 (turn 11279683; tests/fixtures/
n1b-411-departure-deadline-1121, extracted from the incident capture
20261121-055141-town-blocked-stage-deadline-departure, bot main a473e70fd).  Row 132 read the
Word of Recall toward Angband (town:recall-to-angband; the read's spent scroll is the departure
stage's last observed unit of work), rows 133-135 stepped off and walked, and rows 136-265 were
130 town:wait-recall decisions on boards all showing the recall counting down (turn 11280524 to
11280836: 31 of the countdown's up to 35 ticks of 10 game turns; the character is fast).  The
departure stage's deadline is 130 (twice its measured 65), so row 266 stopped the visit:
town:blocked:stage-deadline:departure, the recall still counting down.

Owner 2026-11-14 「歩きは数えない」 / 2026-11-15 (a deadline catches a stuck stage): the
countdown is the game's, bounded by itself, not the stage's work.  Pinned on the recorded boards:
the 130 waits count nothing toward the departure stage, and the stop board's wait is no stop.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import town_visit_plan
from hengbot.town_visit import town_visit
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-departure-deadline-1121"
READ_ROW = 132      # town:recall-to-angband
FIRST_WAIT = 136    # the first of 130 town:wait-recall decisions
STOP_ROW = 266      # town:blocked:stage-deadline:departure
WAIT_KEY = "5"


class N1b411DepartureDeadlineRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.journal, cls.steps = load(FIXTURE, Path(cls.scratch.name))

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_recall_countdown_spends_no_departure_deadline(self):
        journal = self.journal
        self.assertEqual(journal[READ_ROW]["reason"], "town:recall-to-angband")
        waits = list(range(FIRST_WAIT, STOP_ROW))
        self.assertTrue(all(journal[row]["reason"] == "town:wait-recall" for row in waits))
        self.assertEqual(len(waits), town_visit_plan.STAGE_DEADLINES["departure"])
        self.assertEqual(journal[STOP_ROW]["reason"], "town:blocked:stage-deadline:departure")

        policy = self.policy
        visit = town_visit(policy)
        # The read's spent scroll was the stage's last observed unit of work: the count starts there.
        visit.stage_decisions["departure"] = 0
        for row in waits:
            board = self.steps[row][1]()
            self.assertTrue(board.player.recalling, row)
            self.assertTrue(board.in_town, row)
            policy.last_reason = journal[row]["reason"]
            self.assertIsNone(town_visit_plan.stage_deadline_stop(policy, board, WAIT_KEY), row)
            town_visit_plan.note_decision(policy, board, WAIT_KEY)
        self.assertEqual(visit.stage_decisions["departure"], 0)

        stop = self.steps[STOP_ROW][1]()
        self.assertTrue(stop.player.recalling)
        policy.last_reason = "town:wait-recall"
        self.assertIsNone(town_visit_plan.stage_deadline_stop(policy, stop, WAIT_KEY))


if __name__ == "__main__":
    unittest.main()
