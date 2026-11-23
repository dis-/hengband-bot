"""The 99F battle keeps the decision while Oberon is shown nowhere (n1-b life-416, 2026-11-23).

The investigation C:/hengband-backups/pdca/deep99-waste-1123: of n1-b's 15,050 game turns on
Angband 99F, 89% were wasted (search 4,703, explore 5,209, stuck:wander 1,912); Oberon was located
7% of the time and all 21,450 Rocket damage regenerated.  After each teleport the battle answered
only through ``_approach_key``, whose walk to the last-seen cell found no route (the cell lay in
ground a *Destruction* had forgotten), so the generic ladder took the board: explore, search,
stuck:wander (decisions 4842-5010 and 7891-8165).

Owner 2026-11-23 (verbatim) 「着いた所で全感知し見えなければ最後の位置へ歩く」: on landing the full
detection once, then the walk to the last-seen cell (toward the nearest frontier closer to it when
the board no longer shows it), the detection again on reaching it; then the quest search's lap
(「感知で回る」) from inside the battle.

Fixtures (tests/support/finale_416.py, DECLARED RECONSTRUCTED device lists and expedition mark):
- finale-seek-approach: turns 4288600-4288720, the teleport at 4288613 from (17,112) to (6,46),
  Oberon last seen at (11,106);
- finale-seek-wander: turns 4296295-4296430, the absorbed-staff teleport at 4296303 to (16,35),
  Oberon last seen at (10,121); the live bot wandered 275 decisions.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale_battle
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

GENERIC = ("explore", "search", "stuck:wander", "breakout", "breakout:seek-frontier")


class FinaleSeekRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.approach = finale_416.drive(
            finale_416.boards("finale-seek-approach-n1b-416-1123.jsonl.gz"), cls.monrace)
        cls.wander = finale_416.drive(
            finale_416.boards("finale-seek-wander-n1b-416-1123.jsonl.gz"), cls.monrace)

    def after_teleport(self, rows, landing_turn):
        return [row for row in rows if row[0] >= landing_turn]

    def assert_seeks(self, rows, landing_turn):
        after = self.after_teleport(rows, landing_turn)
        unseen = [row for row in after if row[6] is None]
        self.assertTrue(unseen, rows)
        generic = [row for row in unseen if row[3] in GENERIC or row[2] == "s"]
        self.assertEqual(generic, [], after)
        detects = [row for row in unseen if row[3].startswith(angband_finale_battle.DETECT_REASON)]
        self.assertTrue(detects, after)
        first_walk = next(index for index, row in enumerate(unseen)
                          if row[3] == angband_finale_battle.APPROACH_REASON)
        self.assertLess(unseen.index(detects[0]), first_walk, after)

    def test_after_the_teleport_toward_the_left_cell(self):
        self.assert_seeks(self.approach, 4288616)

    def test_after_the_staff_teleport_no_wander(self):
        self.assert_seeks(self.wander, 4296307)

    def test_detects_again_on_the_last_seen_cell(self):
        """DECLARED CONSTRUCTED: the battle past its arrival sweep (the replay starts mid-floor) and
        the last-seen cell set to the player's own cell on one board past the landing (as on
        reaching it): the detection is cast there."""
        landing = 4296320

        def prepare(policy, board):
            held = angband_finale_battle.battle(policy, board)
            if held.phase == angband_finale_battle.SWEEP:
                held.phase = angband_finale_battle.BATTLE
            if board.turn == landing:
                held.last_seen = (board.player.position.y, board.player.position.x)
                held.detect_due = False
        rows = finale_416.drive(
            [raw for raw in finale_416.boards("finale-seek-wander-n1b-416-1123.jsonl.gz")
             if raw["turn"] >= 4296303], self.monrace, prepare=prepare)
        row = next(row for row in rows if row[0] == landing)
        self.assertTrue(row[3].startswith(angband_finale_battle.DETECT_REASON), rows)


if __name__ == "__main__":
    unittest.main()
