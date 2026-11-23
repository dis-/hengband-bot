"""The generic stuck escapes keep the 99F battle's Teleportation scrolls (n1-b life-416, 2026-11-23).

Owner 2026-11-20 (verbatim): the scroll is read 「召喚または攻撃を受けてHPが800を下回ったとき、または対象が
距離2より近づいたとき」 only, and 2026-11-21 「巻物が尽きたら取り込んだテレポートの杖、杖も尽きたら帰還して
補給」.  The investigation C:/hengband-backups/pdca/n1b-leave-99-1123: on 99F (18:30-18:46) the 39
scrolls were spent 25 by the battle, 11 by sealed_pocket's stuck:destroyed-circle-teleport and 4 by
the policy's stuck:teleport-escape (both from _explore_step#1); the empty pack then recalled the
character (return:recall teleport-low) with Oberon alive.

Fixture finale-stuck-teleport-n1b-416-1123 (tests/support/finale_416.py, DECLARED RECONSTRUCTED
device lists and expedition mark): the player_turn boards before two of those reads,
turns 4283900-4283966 (stuck:destroyed-circle-teleport at (3,165), seq 2993) and 4291180-4291225
(stuck:teleport-escape at (17,104), seq 5884).  DECLARED CONSTRUCTED on the read's own board: the
battle past its arrival sweep (the recorded run's was; the replay's fresh memory sweeps again)
and, for the circle's read, one *Destruction* circle of the player's on the floor at its cell (the
record of the recorded run's sweep); then the two escapes are asked directly.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale_battle, area_mapping, sealed_pocket
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

READS = {4283966: "stuck:destroyed-circle-teleport", 4291225: "stuck:teleport-escape"}
SCROLL_READS = ("stuck:destroyed-circle-teleport", "stuck:teleport-escape")


class FinaleStuckScrollsRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        raws = finale_416.boards("finale-stuck-teleport-n1b-416-1123.jsonl.gz")
        cls.asked = {}
        for read in READS:
            window = [raw for raw in raws if read - 70 <= raw["turn"] <= read]

            def prepare(policy, board, read=read):
                if board.turn != read:
                    return
                held = angband_finale_battle.battle(policy, board)
                held.phase = angband_finale_battle.BATTLE
                if READS[read] == "stuck:destroyed-circle-teleport":
                    area_mapping.note_destruction(policy, board, board.player.position, 15, 13)
                left = sealed_pocket.destroyed_leave_key(policy, board)
                left_reason = policy.last_reason if left is not None else None
                escape = policy._stuck_escape_key(board)
                escape_reason = policy.last_reason if escape is not None else None
                cls.asked[read] = (left, left_reason, escape, escape_reason,
                                   angband_finale_battle.applies(policy, board))
            finale_416.drive(window, monrace, prepare=prepare)

    def test_the_battle_holds_the_floors(self):
        for read in READS:
            self.assertTrue(self.asked[read][4], read)

    def test_the_destroyed_circle_leave_reads_no_scroll(self):
        for read in READS:
            left, reason, _escape, _escape_reason, _held = self.asked[read]
            self.assertIsNone(left, (read, reason))

    def test_the_stuck_escape_reads_no_scroll(self):
        for read in READS:
            _left, _reason, escape, reason, _held = self.asked[read]
            self.assertNotIn(reason, SCROLL_READS, (read, escape))


if __name__ == "__main__":
    unittest.main()
