"""n1-c life-210's 05:00 town stop: a staff its food reservation keeps is no Home deposit.

n1-c life-210 (Lv8 zombie Magic-Eater) stopped at 2026-11-15 05:00 on
town:blocked:survival:food_ready (turn 141913, 1,414 gold).  The stage-1 staff rule
(me_staff_sequence.stows) made the carried unidentified 杖 (20回分) a Home deposit candidate although
its 'mana-device' retention keeps it (the zombie eats device charges); the Home page refused the
deposit, so the visit walked to Home and closed the page as home:route-claim-unfulfilled three
times until the CLI retired the home-visit owner, and the food gate then stopped the visit.  The
candidate now leaves a staff the reservation keeps: after the ring's deposit (row 68) the visit
goes on to its next store instead of back into Home.

Recorded: the capture's town-arrival checkpoint and journal rows 0-69
(tests/extract_n1c_210_food_staff_home_1115_fixture.py), replayed through the public ``choose_key``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import TVAL_STAFF
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
FOOD_STAFF = FIXTURES / "n1c-210-food-staff-home-1115"


class _Replay(unittest.TestCase):
    def replay(self, fixture, upto):
        """(policy, the board of row ``upto``, its key) after rows 0..upto-1 decided as recorded."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, rows = load(fixture, Path(scratch.name))
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        for recorded, supply in rows[:upto]:
            board = supply()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            policy.confirm_key_posted(key)
        board = rows[upto][1]()
        return policy, board, policy.choose_key(board), rows[upto][0]


class ReservedFoodStaffStaysOutOfHomeTest(_Replay):
    def test_after_the_ring_the_visit_does_not_return_to_home_for_the_staff(self):
        policy, board, key, recorded = self.replay(FOOD_STAFF, 68)
        self.assertEqual(recorded["reason"], "shop:travel:await-entry")  # back into Home, live
        staff = next(item for item in board.inventory if item.tval == TVAL_STAFF)
        self.assertEqual(policy._retention_surplus(board, staff), 0)
        self.assertFalse(policy._home_deposit_candidate(staff, board))
        self.assertIsNone(policy._find_home_deposit(board))
        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertEqual(key, "\x1b`n%.")


if __name__ == "__main__":
    unittest.main()
