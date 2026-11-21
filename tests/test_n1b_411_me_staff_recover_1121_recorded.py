"""n1-b life-411 2026-11-21 09:28: seven healing rests stopped the Magic-Eater's staff sequence.

Recorded: the town arrival of 09:28:30 (turn 11335422; tests/fixtures/
n1b-411-me-staff-recover-1121, extracted from the incident capture
20261121-092837-quest-blocked-me-staff, bot main 9e5e69774).  Row 0 travelled to Morivant for the
absorption ('1mc', me-staff:travel-morivant) and arrived with 948 of 1153 HP; the absorb step
rests first (me-staff:recover, 'R&\\r').  Every rest was cut short (no monster in view; the
telepathy-sensed town monsters moving), yet each healed: rows 1-7 raised the HP 948 -> 962 ->
990 -> 1004 -> 1018 -> 1073 -> 1101 -> 1115 on one cell, (43, 92).  The sequence's standstill
check (_no_progress) compared only the phase, the gold and the pack, so the seven rests were
seven boards without progress and row 8 stopped it: quest:blocked:me-staff (no-progress:absorb).

Pinned on the recorded boards: a recovery rest that restores HP is progress, so the eight rest
boards never reach the bound; a rest that restores nothing still counts toward it (the last board
repeated stops at STORE_STUCK_LIMIT).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_staff_sequence
from hengbot.policy_constants import REST_MACRO, STORE_STUCK_LIMIT
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-me-staff-recover-1121"
RESTS = range(1, 9)     # the boards of rows 1-8: rows 1-7 rested, row 8 stopped
RECOVER = "me-staff:recover"


class N1b411MeStaffRecoverRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, self.journal, self.steps = load(FIXTURE, Path(self.scratch.name))

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def _rest(self, board) -> bool:
        """One recovery rest offered on ``board`` and posted: True when the bound stops it."""
        policy = self.policy
        policy._decision_sequence += 1
        policy.last_reason = RECOVER
        stopped = me_staff_sequence._no_progress(policy, board, "absorb", REST_MACRO)
        if not stopped:
            me_staff_sequence.confirm_posted(policy, REST_MACRO)
        return stopped

    def test_healing_rests_are_progress(self):
        self.assertEqual([self.journal[row]["reason"] for row in range(1, 8)], [RECOVER] * 7)
        self.assertEqual(self.journal[8]["reason"], "quest:blocked:me-staff")
        boards = [self.steps[row][1]() for row in RESTS]
        self.assertEqual([board.player.hp for board in boards],
                         [948, 962, 990, 1004, 1018, 1073, 1101, 1115])
        self.assertEqual(len({board.player.position for board in boards}), 1)
        self.assertFalse(any(self._rest(board) for board in boards))

    def test_rests_that_heal_nothing_still_stop(self):
        board = self.steps[8][1]()
        stops = [self._rest(board) for _ in range(STORE_STUCK_LIMIT)]
        self.assertEqual(stops, [False] * (STORE_STUCK_LIMIT - 1) + [True])


if __name__ == "__main__":
    unittest.main()
