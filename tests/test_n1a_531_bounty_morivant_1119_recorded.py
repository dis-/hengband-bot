"""Wanted remains outside the Outpost keep: no supplier is left for them (n1a-531-bounty-morivant-1119).

n1-a life-531 (warrior Lv44) arrived in Morivant at 2026-11-19 04:47:45 carrying
ニーベルング族の王アルベリヒの死体 {賞金首} and stopped at 04:48:25 with
town:blocked:stage-deadline:quest.  ``_town_order_step4_pending`` read the remains alone, so in
every supplier the bounty rung answered first and left it (bounty:leave-supplier, the visit's
"quest" stage), while outside ``_bounty_cashout_key`` had no office to walk to (only the
Outpost's building 13 is the Hunter's office: lib/edit/towns; Morivant's 13 is the Trump
Tower).  The buy stage walked back to a supplier and was turned out again: the capture's flow
alternates buy, quest, buy, quest ... until the quest stage's deadline.

Fix: the step-4 work is pending only in a town with the Hunter's office
(``_bounty_office_in_town``, the one reader the cash-out's own check also reads).

Recorded: the arrival checkpoint and journal rows 0-5
(tests/extract_n1a_531_bounty_morivant_1119_fixture.py).  Row 4 is a supplier page, decided live
as ``\\x1b`` bounty:leave-supplier.

DECLARED CONSTRUCTED: row 4's board with town_id 0 (the same remains in the Outpost stay pending).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-bounty-morivant-1119"
SUPPLIER_ROW = 4
MORIVANT = 2


class N1a531BountyMorivantRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        boards = [supply() for _, supply in steps[:SUPPLIER_ROW + 1]]
        cls.supplier = boards[SUPPLIER_ROW]

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_recorded_row_left_the_supplier_for_the_bounty(self):
        entry = self.journal[SUPPLIER_ROW]
        self.assertEqual((entry["key"], entry["reason"]), ("\x1b", "bounty:leave-supplier"))
        self.assertIsNotNone(self.supplier.store)
        self.assertEqual(self.policy._effective_town_id(self.supplier), MORIVANT)
        self.assertTrue(any(item.is_bounty for item in self.supplier.inventory))

    def test_no_bounty_work_in_morivant(self):
        self.assertFalse(self.policy._town_order_step4_pending(self.supplier))
        self.assertIsNone(self.policy._town_order_step4_key(self.supplier))
        self.assertNotEqual(self.policy.last_reason, "bounty:leave-supplier")

    def test_the_same_remains_in_the_outpost_stay_pending(self):
        outpost = replace(self.supplier, town_id=0)
        self.assertTrue(self.policy._town_order_step4_pending(outpost))


if __name__ == "__main__":
    unittest.main()
