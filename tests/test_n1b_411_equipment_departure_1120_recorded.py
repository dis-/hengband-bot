"""n1-b life-411 2026-11-20 22:29-22:32: the 99F/100F switch began in the middle of a 95F visit.

Recorded: the town arrival of 22:29:50 (turn 11064734; tests/fixtures/
n1b-411-equipment-departure-1120, extracted from the incident capture
20261120-223208-town-blocked-unmet-equipment-departure-ready).  The Magic-Eater arrived with 11
Teleportation scrolls owned (40 needed); at the visit's 32nd decision it bought 29 at the Alchemist,
which completed the finale's supplies (angband_finale ``supplied``).  On a93836fd6 the optimizer's
order changed to the finale's there, mid-visit: from decision 48 a swap through Home ran a dozen
takeoffs and equips until the takeoff of the bastard sword (identity 28aedef5bc0c8b75) failed
(``equipment-transaction:stale-identity-invalidated:takeoff:missing``), the transaction failed and
the departure's gear check (equipment_departure_ready) stopped the town at 22:32:06
(``town:blocked:unmet:equipment_departure_ready``).

Owner 2026-11-20 (verbatim): 「上限を外す時に初めて着け替える」, and 2026-11-21 「専用の準備フェイズを
作って準備して」: the switch is the preparation phase's (finale_prep), whose swap is its own step,
after its check and supplies.  Replayed: the first 48 decisions match the record, the supplies are
complete from decision 33 and the phase is entered, but no swap starts and nothing is carried
before its own steps; at decision 48, where the record began the mid-visit swap, the departure
reads the Word of Recall to Angband and the phase, short of its check, stops by name.  (The replay posts the recorded keys; the
optimizer's own search is not reproduced here: its calibration and skill records are runtime
files the arrival checkpoint does not hold, so its swap is shown by the record, not replayed.)
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, finale_prep
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-equipment-departure-1120"
PURCHASE_ROW = 32   # 'pg29' at the Alchemist: the 40th Teleportation scroll owned
SWAP_ROW = 48       # the record's equipment-transaction:travel-home


class N1b411EquipmentDepartureRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.decided, cls.latches = [], []
        for row, (recorded, supply) in enumerate(steps[:SWAP_ROW + 1]):
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = cls.policy.choose_key(board)
            cls.decided.append((key, cls.policy.last_reason))
            held = angband_finale.memory(cls.policy)
            cls.latches.append((held.supplied, finale_prep.carrying(cls.policy)))
            cls.policy.confirm_key_posted(recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_visit_departs_without_a_mid_visit_switch(self):
        for row in range(SWAP_ROW):
            recorded = self.journal[row]
            self.assertEqual(self.decided[row], (recorded["key"], recorded["reason"]), row)
        self.assertEqual(self.journal[PURCHASE_ROW]["key"], "pg29\r\r")
        self.assertEqual(self.latches[PURCHASE_ROW - 1], (False, False))
        # The supplies are complete from the next board on; the visit switches nothing.
        self.assertTrue(all(latch == (True, False) for latch in self.latches[PURCHASE_ROW + 1:]))
        self.assertEqual(self.journal[SWAP_ROW]["reason"], "equipment-transaction:travel-home")
        self.assertEqual(self.decided[SWAP_ROW], ("rga", "town:recall-to-angband"))
        held = finale_prep.phase(self.policy)
        self.assertEqual((held.step, held.stopped),
                         (finale_prep.STOPPED, "check:unfinished-at-departure"))


if __name__ == "__main__":
    unittest.main()
