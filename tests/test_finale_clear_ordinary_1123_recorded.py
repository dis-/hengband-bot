"""The 99F battle's *Destruction* at the other monsters: the ordinary one only, never powered.

Owner 2026-11-23 (verbatim): 「テレパシーに映らなければ破壊を使って良い」 and 「普通の *破壊* だけ
にする — 標的がテレパシーに映らない時は普通の *破壊* だけを撃ち、強力発動は使わない。即死の時の逃げは
今までどおり。」  The ordinary radius 13 + randint0(5) <= 17 (cmd-usestaff.cpp:282) lies inside
telepathy's 20 (monster-update.cpp:433), so the target, a QUESTOR healed to full and teleported
away when caught (spells-floor.cpp:284-287), cannot be in the circle; Powerful Activation's
18 + randint0(5) <= 22 can catch it.  n1-b life-416 (Angband 99F) cast the powered one 66 times with
Oberon unshown (decisions 5514 and 6697 among them).

Fixture finale-clear-unshown-n1b-416-1123 (tests/support/finale_416.py, DECLARED RECONSTRUCTED
device lists and expedition mark): turns 4290200-4290246 and 4293200-4293239, ending in those two
casts ('UA3' at 4290244 from (8,65) and at 4293237 from (13,105)).
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-clear-unshown-n1b-416-1123.jsonl.gz"


class FinaleClearOrdinaryRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        raw = finale_416.boards(FIXTURE)
        cls.rows = {}
        for start, stop in ((4290200, 4290246), (4293200, 4293239)):
            for row in finale_416.drive([b for b in raw if start <= b["turn"] <= stop], monrace):
                cls.rows[row[0]] = row

    def test_no_powered_destruction_with_oberon_unshown(self):
        for turn in (4290244, 4293237):
            row = self.rows[turn]
            self.assertIsNone(row[6], row)  # Oberon shown nowhere on the board
            self.assertNotEqual(row[2], "UA3", row)
            self.assertFalse((row[3] or "").endswith(":powered"), row)
        powered = [row for row in self.rows.values() if "clear:powered" in (row[3] or "")]
        self.assertEqual(powered, [])


if __name__ == "__main__":
    unittest.main()
