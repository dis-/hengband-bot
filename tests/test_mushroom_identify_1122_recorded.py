"""A carried unaware mushroom is identified with the carried means, like an unaware potion.

Owner 2026-11-22 「キノコも鑑定する」 (持っている未鑑定のキノコを、未鑑定の薬・巻物と同じく鑑定の手段で調べます。
治療のキノコと分かれば、盲目や混乱の時に食べられます。): n1-a life-533 died blind and confused on Orc
Cave 19F with an unknown Mushroom of Cure Serious Wounds (the curing mushroom is eaten only when
known, status_cure.cure_mushroom) and an Identify staff carried.  The identification flow owned
unaware potions and scrolls only (``_unaware_consumable_awaits_identification``, owner
2026-11-15).

Recorded: n1-a life-532's town visit of 2026-11-22 14:36 (tests/fixtures/
n1a-532-home-curse-take-1122): slot a holds an unaware ねばねばしたキノコ and slots q and r Identify
staffs (deepest 19F).  Decided through the public ``choose_key`` with the recorded keys posted;
rows 0-3 replay as recorded and row 4, the record's Remove Curse read, now uses the staff on the
mushroom (``identify:device``), as for an unaware potion.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import SV_STAFF_IDENTIFY, TVAL_FOOD, TVAL_STAFF
from support.town_arrival_fixture import load
from tests.test_n1a_532_home_curse_take_1122_recorded import FIXTURE, _decide, _post

IDENTIFY_ROW = 4


class MushroomIdentifyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()):
            policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for recorded, supply in steps[:IDENTIFY_ROW]:
            key = _decide(policy, supply())
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            _post(policy, recorded["key"])
        cls.board = steps[IDENTIFY_ROW][1]()
        cls.mushroom = next(item for item in cls.board.inventory if item.tval == TVAL_FOOD)
        cls.awaits = policy._unaware_consumable_awaits_identification(cls.mushroom)
        cls.key = _decide(policy, cls.board)
        cls.reason = policy.last_reason
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_record(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual((self.journal[IDENTIFY_ROW]["key"], self.journal[IDENTIFY_ROW]["reason"]),
                         ("ri", "town:remove-curse"))
        self.assertEqual((self.mushroom.slot, self.mushroom.aware), ("a", False))
        self.assertEqual(self.policy._deepest_level, 19)
        staffs = [item.slot for item in self.board.inventory
                  if (item.tval, item.sval) == (TVAL_STAFF, SV_STAFF_IDENTIFY)]
        self.assertIn("r", staffs)

    def test_the_unaware_mushroom_is_identified_with_the_carried_staff(self):
        # Before: not owned by the identification flow; the row read the Remove Curse.
        self.assertTrue(self.awaits)
        self.assertEqual((self.key, self.reason), ("ura", "identify:device"))


if __name__ == "__main__":
    unittest.main()
