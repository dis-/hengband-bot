"""The walk to the last-seen cell goes on through the rock by Stone to Mud (n1-b life-416, 2026-11-23).

Owner 2026-11-23 (verbatim) 「着いた所で全感知し見えなければ最後の位置へ歩く」 and 2026-11-21
「岩石溶解の消費量は問題ではない」.  The investigation C:/hengband-backups/pdca/n1b-leave-99-1123 (the
21:08 run of bot-decisions.jsonl.1): after the teleport away from Oberon (seq 177, landing (11,39),
Oberon last seen at (11,120)) the approach walked to (3,62) and then dropped the last-seen cell
(seq 204-205): no walk reached it (the ground between lay forgotten by the *Destruction*s, the
board knew no floor east of x 63), no frontier nearer to it was reachable, and the openers' route
(retreat_enclosure ``open_toward_key``) runs over known grids only.  The floor was then searched
from x 16-63 for 390 decisions and regenerated without Oberon.

Fixture finale-floor-2108-n1b-416-1123 (tests/support/finale_416.py, DECLARED RECONSTRUCTED device
lists and expedition mark): the boards of that run, the teleport at turn 4297369 to the give-up
board 4297434.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale_battle
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

TELEPORT = 4297369
GIVE_UP = 4297434   # the recorded board (3,62) after the last-seen cell (11,120) was dropped
END = 4297460


class FinaleApproachLineRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        raws = [raw for raw in finale_416.boards("finale-floor-2108-n1b-416-1123.jsonl.gz")
                if TELEPORT - 60 <= raw["turn"] <= END]

        def prepare(policy, _board):
            # DECLARED: the battle's last melt (``Battle.melt_aim``, read for a melt that changed
            # nothing) cleared on every board, as the open-loop replay's melts never change the
            # recorded boards.
            held = getattr(policy, angband_finale_battle.MEMORY, None)
            if held is not None:
                held.melt_aim = None
        cls.rows = finale_416.drive(raws, monrace, prepare=prepare)

    def test_the_last_seen_cell_is_kept_and_the_rock_melted_toward_it(self):
        row = next(row for row in self.rows if row[0] == GIVE_UP)
        self.assertEqual(row[5], (11, 120), self.rows)
        self.assertTrue(row[3].startswith(angband_finale_battle.MELT_REASON), row)
        # The beam goes along the line toward (11,120): south-east, at the wall (4,63).
        self.assertEqual(row[2][-1], "3", row)

    def test_no_search_lap_while_the_cell_is_kept(self):
        after = [row for row in self.rows if row[0] >= GIVE_UP]
        self.assertTrue(after)
        self.assertEqual([row for row in after if row[3].startswith("quest-search")], [], after)
        self.assertTrue(all(row[5] == (11, 120) for row in after), after)


if __name__ == "__main__":
    unittest.main()
