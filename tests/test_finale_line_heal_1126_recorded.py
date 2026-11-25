"""The 100F battle lines up with the Serpent away from it and heals to the full HP after a
teleport (n1-c life-222, Angband 100F, 2026-11-26 03:09-03:11; owner 2026-11-26).

Owner 2026-11-26 (verbatim):
1. 「距離を詰めすぎてテレポートで離れる動きがもったいない。位置関係が斜めの時に頻発していたように
   見えるので、縦または横でサーペントとラインを合わせる動きを徹底することで改善しそう。」
2. 「テレポート離脱後、HP800以上の時は回復せずに次の行動に移っているのが気になる。取り込んだ体力回復
   などを使用して満タンにしてから行動するべき。攻撃機会の損失に繋がっている。」

The recorded run (decision log of that floor): 151 teleports, 26 of them within distance 2; the
walks to a stand drawn for where the Serpent had been went on while it closed in:
* turns 10183954-72: the stand (10,130) drawn for the Serpent at (10,138); at (11,129) with it at
  (10,132) the walk stepped '9' onto the stand beside it, and the teleport;
* turns 10185943-64: the stand (10,127) 3 cells beyond the Serpent at (10,124) on its row, walked
  to from (3,109); at (1,116), the Serpent at (3,117), the teleport;
* turns 10186331-66: the stand (3,129) beyond the Serpent at (3,147), walked to from (9,164)
  past it.
And after the teleports at 10183972 (landed at 1011/1103 HP) and 10184041 (healed to 1040/1103)
the battle went on with the detection at once.

Fixture finale-line-heal-n1c-222-1126 (tests/extract_finale_line_heal_1126_fixture.py): the
floor's player_turn boards from the arrival to turn 10184060, and the two windows above, replayed
open-loop (tests/support/finale_416: DECLARED RECONSTRUCTED device lists and expedition mark;
DECLARED: the expedition's Restore Mana count held at 0).  DECLARED RECONSTRUCTED: on the first
board of each window the battle of that decision record (phase battle, the Serpent's last-seen
cell, no stand).
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale, angband_finale_battle as fb
from hengbot.model import Position, game_distance
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-line-heal-n1c-222-1126.jsonl.gz"
ARRIVAL_UNTIL = 10184060
# (first board of the window, the Serpent's last-seen cell on it); the first is inside the arrival's
# boards: the recorded run's recovery ended there (the open-loop boards never show the heal).
WINDOWS = {10183954: (10, 138), 10185943: (11, 125), 10186331: (3, 147)}
LANDED = (10183975, 10184052)
# The board after each recorded teleport: the escape's record (``Battle.escape``) read there.
# (the board after it: (the teleport's board, the rules))
ESCAPED = {10183975: (10183972, ["too-close"]), 10184045: (10184041, ["hp-below-800"]),
           10185966: (10185964, ["too-close"])}
KEY_STEP = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
            "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}  # the boards after the teleport (and its heal) recorded as detection


class FinaleLineHealRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        boards = finale_416.boards(FIXTURE)
        cls.escapes = {}

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            held = fb.battle(policy, board)
            if board.turn in ESCAPED and getattr(held, "escape", None) is not None:
                cls.escapes.setdefault(board.turn, dict(held.escape))
            if board.turn in WINDOWS:
                held.phase, held.stand = fb.BATTLE, None
                held.last_seen = WINDOWS[board.turn]
                held.refused.clear()
                fb._end_stalemate(held)

        cls.rows = []
        start = 0
        for index, board in enumerate(boards):
            if index and board["turn"] in WINDOWS and boards[index - 1]["turn"] < board["turn"] - 50:
                cls.rows += finale_416.drive(boards[start:index], cls.monrace, prepare=prepare)
                start = index
        cls.rows += finale_416.drive(boards[start:], cls.monrace, prepare=prepare)
        cls.by_turn = {}
        for row in cls.rows:
            cls.by_turn.setdefault(row[0], row)

    def test_the_landing_heals_to_the_full_hp(self):
        for turn in LANDED:
            row = self.by_turn[turn]
            # Recorded: angband-finale:detect (revert: the detection comes back).
            self.assertEqual(row[3], fb.ABSORBED_HEAL_REASON, row)

    def test_no_stand_walk_steps_beside_the_serpent(self):
        steps = []
        for (turn, here, key, reason, _phase, _seen, target) in self.rows:
            if reason != fb.STAND_WALK_REASON or target is None:
                continue
            dy, dx = KEY_STEP[key]
            to = Position(here[0] + dy, here[1] + dx)
            steps.append((turn, game_distance(to, Position(*target))))
        self.assertTrue(steps)
        # Recorded: the step '9' from (11,129) to (10,130) with the Serpent at (10,132), 2 away
        # (revert: it comes back).
        self.assertEqual([entry for entry in steps if entry[1] <= fb.TELEPORT_WITHIN], [])


    def test_the_step_off_the_stand_beside_the_serpent(self):
        # Recorded: at (11,129), the Serpent at (10,132), '9' onto the stand (10,130); at (1,115),
        # the Serpent at (4,117), '6' to (1,116) (revert: both come back).
        self.assertNotEqual(self.by_turn[10183969][2], "9")
        self.assertNotEqual(self.by_turn[10185962][2], "6")

    def test_each_escape_records_its_rule(self):
        # Recorded: no record of why (revert: the record is gone).
        for after, (turn, rules) in ESCAPED.items():
            escape = self.escapes.get(after)
            self.assertIsNotNone(escape, after)
            self.assertEqual((escape["turn"], escape["rules"]), (turn, rules), escape)
        self.assertEqual(self.escapes[10183975]["distance"], 1)
        self.assertEqual(self.escapes[10183975]["target"], [9, 131])


if __name__ == "__main__":
    unittest.main()
