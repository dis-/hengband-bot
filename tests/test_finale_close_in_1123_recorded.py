"""The shown target with no stand keeps the decision in the 99F battle (n1-b life-416, 2026-11-23).

Owner 2026-11-20 (verbatim) 「なるべく距離をとって相対するように岩石溶解を使って射線を通す」 and 2026-11-21
「岩石溶解の消費量は問題ではない」.  The investigation C:/hengband-backups/pdca/n1b-leave-99-1123 (the
21:08 run of bot-decisions.jsonl.1): Oberon was detected at (13,113), 19 cells west of the player
at (12,132); every ray from him ran through ground the *Destruction*s had forgotten, so the stand
(``_stand_key``) found no open cell and answered None, and the generic hunt (_hunt_step#3,
seq 160-176) walked n1-b to the cell beside him; at distance 1 the battle had to teleport away
(seq 177).

Fixture finale-floor-2108-n1b-416-1123 (tests/support/finale_416.py, DECLARED RECONSTRUCTED device
lists and expedition mark), turns 4297309-4297369.  DECLARED CONSTRUCTED: the battle is past its
arrival sweep, as the recorded run was (its seq 156 was the battle's haste); the replay starts
mid-floor, so its fresh battle memory would sweep again.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale_battle
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

START, TELEPORT = 4297309, 4297369
GENERIC = ("hunt:", "anaguma:", "explore", "search", "stuck:", "breakout")


class FinaleCloseInRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

        def prepare(policy, board):
            held = angband_finale_battle.battle(policy, board)
            if held.phase == angband_finale_battle.SWEEP:
                held.phase = angband_finale_battle.BATTLE
        raws = [raw for raw in finale_416.boards("finale-floor-2108-n1b-416-1123.jsonl.gz")
                if START <= raw["turn"] < TELEPORT]
        cls.rows = finale_416.drive(raws, monrace, prepare=prepare)

    def test_the_battle_answers_while_the_target_is_shown(self):
        shown = [row for row in self.rows if row[6] is not None]
        self.assertTrue(shown, self.rows)
        generic = [row for row in shown if row[3].startswith(GENERIC)]
        self.assertEqual(generic, [], shown)

    def test_the_first_answer_closes_in_along_the_line(self):
        first = next((row for row in self.rows if row[6] is not None
                      and row[3].startswith((angband_finale_battle.APPROACH_REASON,
                                             angband_finale_battle.MELT_REASON))), None)
        self.assertIsNotNone(first, self.rows)


if __name__ == "__main__":
    unittest.main()
