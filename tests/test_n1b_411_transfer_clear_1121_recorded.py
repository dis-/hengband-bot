"""n1-b life-411 2026-11-21 01:09: a full Home's visit that could not leave.

Recorded: the town arrival of 01:08:34 (turn 11195981; tests/fixtures/
n1b-411-transfer-clear-1121, extracted from the incident capture
20261121-010918-town-blocked-survival-equipment-transfer-clear, bot main 31f2fa528).

1. The refused deposit's marker.  At row 71 the equipment transaction posted its deposit of the
   理力の首切りソード ('5' on the Home entrance), which put
   _equipment_transaction_posted_catalog_update; the Home held 240 stacks, the game refused the
   deposit, the session was blocked and row 79 abandoned it (equipment-transaction:
   abandon-blocked).  The marker is fenced to the session's id and action index and was cleared
   only when its action was confirmed or a session was installed through
   _set_equipment_transaction_session; the abandonment set the session to None directly, so it
   stayed, equipment_transfer_clear (a departure-minimum leaf) stayed false for the visit, and row
   121 stopped: town:blocked:survival:equipment_transfer_clear.

2. The queued Home take that never ran.  At row 98 the Black Market's home-first gate queued one
   Potion of Resistance from Home (_purchase_home_gate).  A Home take is composed only on the
   outside Home entrance (_atomic_home_withdraw_dispatch_key), but the shopping visit that walked
   into Home (rows 109, 112, 115, 118) closed as its page was left, and the next board, on the
   entrance, reached the town end, whose step-off (town:end-step-off, rows 111, 114, 117, 120)
   took the bot off the entrance every time; the visit would stop on home_pending_item_clear
   once (1) no longer did.  The town end now composes the queued take on the Home entrance before
   its step-off.

Pinned: the replay matches the record up to row 110; the abandonment clears the marker (the
refused deposit moved nothing, so the Home catalogue is kept) and the transfer leaf holds from
there on; row 111, on the Home entrance after the first such entry, takes the potion instead of
stepping off.  (From row 112 on the recorded boards are those of the step-off, not of the take,
so nothing later is compared.)
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-transfer-clear-1121"
POSTED_ROW = 71     # equipment-transaction deposit posted (home:atomic-deposit)
ABANDON_ROW = 79    # equipment-transaction:abandon-blocked
QUEUED_ROW = 98     # the home-first gate queues the Potion of Resistance
ENTRANCE_ROW = 111  # on the Home entrance: the record steps off
STOP_ROW = 121      # town:blocked:survival:equipment_transfer_clear
RESISTANCE = ("耐性の薬 {@2}", 75, 60)


class N1b411TransferClearRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.decided, cls.markers, cls.transfer, cls.pending = [], [], [], []
        for row, (recorded, supply) in enumerate(steps[:ENTRANCE_ROW + 1]):
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = cls.policy.choose_key(board)
            cls.decided.append((key, cls.policy.last_reason))
            cls.markers.append(cls.policy._equipment_transaction_posted_catalog_update)
            cls.pending.append(cls.policy._home_pending_item)
            if row >= ABANDON_ROW:
                minimum = cls.policy._departure_minimum(board, 95)
                cls.transfer.append(minimum["values"]["equipment_transfer_clear"])
            cls.policy.confirm_key_posted(recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_visit_matches_the_record_up_to_the_entrance(self):
        for row in range(ENTRANCE_ROW):
            recorded = self.journal[row]
            self.assertEqual(self.decided[row], (recorded["key"], recorded["reason"]), row)
        self.assertEqual(self.journal[STOP_ROW]["reason"],
                         "town:blocked:survival:equipment_transfer_clear")

    def test_the_abandoned_deposit_leaves_no_posted_marker(self):
        self.assertEqual(self.journal[ABANDON_ROW]["reason"], "equipment-transaction:abandon-blocked")
        self.assertIsNotNone(self.markers[POSTED_ROW])
        self.assertEqual(self.markers[POSTED_ROW][3], "deposit")
        self.assertIsNotNone(self.markers[ABANDON_ROW - 1])
        self.assertTrue(all(marker is None for marker in self.markers[ABANDON_ROW:]))
        self.assertTrue(all(self.transfer))

    def test_the_queued_home_take_is_composed_on_the_entrance(self):
        self.assertIsNone(self.pending[QUEUED_ROW - 1])
        self.assertEqual(tuple(self.pending[QUEUED_ROW]), RESISTANCE)
        self.assertEqual(self.journal[ENTRANCE_ROW]["reason"],
                         "town:entrance-step-off:town:end-step-off")
        key, reason = self.decided[ENTRANCE_ROW]
        self.assertEqual(reason, "home:atomic-withdraw")
        self.assertTrue(key.startswith("5p"), key)


if __name__ == "__main__":
    unittest.main()
