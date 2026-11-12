"""n1-a life-512's town:blocked:survival:home_atomic_withdraw_clear stops (2026-11-12 09:36, 09:37).

Recorded: each capture's town-arrival checkpoint, visit journal and sidecar files
(tests/extract_idstaff_stockout_home_kit_1112_fixture.py, build bot-6564ab9d1).
The rows before the settled decision go through the public chooser and the live
CLI's owner-retirement entrance, as in test_idstaff_stockout_home_kit_1112_recorded.

Both visits opened a fundraising set whose kit (diggers, Treasure Detection)
waited in Home, and put a Home deposit batch that held two spare Identify staves
into a full Home: the game refused them ("我が家にはもう置く場所がない。"; at
09:37 the first staff landed and filled the last slot).  The
batch kept waiting for the deposit effect that could not come; its pending
(``_home_atomic_deposit_pending``) failed the departure minimum's
home_atomic_withdraw_clear, the Home executor stayed EXIT_PENDING, the kit's take
could not start and the town end stopped by that leaf (09:36 row 22; the
restarted process stopped the same way at 09:37 row 25, and the guard retired
the life).

The refusal now settles the batch on the next outside board (the n1-b life-370
02:08 settlement): what landed stands, the refused staves are rejected for the
visit and the Home list is read again.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot.model import SV_STAFF_IDENTIFY, TVAL_STAFF
from tests import test_idstaff_stockout_home_kit_1112_recorded as stockout_kit

REFUSED = "我が家にはもう置く場所がない。"


class HomeFullStaffDeposit1112RecordedTest(stockout_kit.IdstaffStockoutHomeKit1112RecordedTest):
    test_0720_stockout_set_routes_home_for_its_kit = None

    def assert_refused_batch_settles(self, stop, deposit_row, settle_row, stop_row, refused):
        policy, recorded, steps = self.load(stop)
        self.assertEqual(recorded[deposit_row]["reason"], "home:atomic-deposit")
        self.assertEqual((recorded[settle_row]["key"], recorded[settle_row]["reason"]),
                         ("5", "home:atomic-deposit-await-confirmation"))
        self.assertEqual((recorded[stop_row]["key"], recorded[stop_row]["reason"]),
                         ("5", "town:blocked:survival:home_atomic_withdraw_clear"))
        self.replay_live(policy, recorded, steps[:settle_row])
        board = steps[settle_row][1]()
        self.assertIsNone(board.store)
        self.assertIn(REFUSED, board.messages)
        self.assertEqual(policy._fundraising_mode, "prepare")
        pending = policy._home_atomic_deposit_pending
        self.assertIsNotNone(pending)
        staves = {entry[0] for entry in pending[0]
                  if entry[0][1:] == (TVAL_STAFF, SV_STAFF_IDENTIFY)}
        self.assertEqual(len(staves), 2)
        key = policy.choose_key(board)
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertEqual(len(staves & set(policy._home_rejected_deposits)), refused)
        self.assertNotEqual(policy._home_visit.state.name, "EXIT_PENDING")
        self.assertEqual(key, "~9\x1b")
        self.assertIn(policy.last_reason, {
            "home-errand:request-knowledge:identification-catalog",
            "home:request-knowledge-scan"})
        self.assertIsNone(policy._town_blocked_reason)

    def test_0936_refused_staff_deposit_settles(self):
        """09:36 row 18: the batch ``dodndldfdc`` (row 17) refused both staves.

        Live: ``5`` home:atomic-deposit-await-confirmation, then the stop on row 22.
        """
        self.assert_refused_batch_settles("n1a-512-0936", 17, 18, 22, refused=2)

    def test_0937_refused_staff_deposit_settles(self):
        """09:37 (restarted) row 21: the batch ``dkdi`` (row 20) landed the 4-charge
        staff; Home refused the 6-charge one.

        Live: ``5`` home:atomic-deposit-await-confirmation, then the stop on row 25.
        """
        self.assert_refused_batch_settles("n1a-512-0937", 20, 21, 25, refused=1)


if __name__ == "__main__":
    unittest.main()
