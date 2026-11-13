"""2026-11-02: the summoner hold's teleport is never a Phase Door.

Owner 2026-11-02 (answer to: may Phase Door stand in for Teleportation when
the summoner hold has no point out of fire): 「ショートテレポートはテレポートの
代替にならない」.

Recorded board: tests/fixtures/flee-into-rubble-20261019.jsonl.gz row 0 (the
C4-A hold point in the line of fire, see tests/test_flee_into_rubble_recorded.py).
With Teleportation carried the refused rubble dig ends in ('rh',
summoner:hold-teleport) (pinned there).  DECLARED CONSTRUCTED: the carried
Scrolls of Teleportation turned into Scrolls of Phase Door (same slot and
count), plus the constructed parts of test_flee_into_rubble_recorded.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import unittest
from dataclasses import replace

import test_flee_into_rubble_recorded as rubble
from hengbot.model import SV_SCROLL_PHASE_DOOR, SV_STAFF_DESTRUCTION, TVAL_STAFF
from hengbot.summoner_wait import HOLD_TELEPORT_REASON
from tests.policy_fixtures import item


class SummonerHoldPhaseOnlyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rubble.FleeIntoRubbleRecordedTest.setUpClass()

    def setUp(self):
        self.recorded = rubble.FleeIntoRubbleRecordedTest(
            "test_refused_dig_is_not_repeated")
        self.recorded.setUp()
        self.addCleanup(self.recorded.doCleanups)

    def _phase_only(self, board):
        teleports = [item for item in board.inventory if item.is_teleport_scroll]
        self.assertTrue(teleports)
        # DECLARED CONSTRUCTED: Phase Door in place of Teleportation.
        return replace(board, inventory=tuple(
            replace(item, sval=SV_SCROLL_PHASE_DOOR, name="ショート・テレポートの巻物")
            if item.is_teleport_scroll else item
            for item in board.inventory))

    def test_phase_door_is_not_read_as_the_hold_teleport(self):
        policy = self.recorded.policy
        keys = []
        for _ in range(6):
            board = self._phase_only(self.recorded._board(0))
            self.assertIsNone(policy._find_teleport_scroll(board))
            self.assertIsNotNone(policy._escape_scroll(board))
            self.assertIsNone(policy._escape_scroll(board, teleport_only=True))
            keys.append((policy.choose_key(board), policy.last_reason))
        self.assertEqual(keys[:4], [("T8", "summoner:hold-reposition")] * 4)
        self.assertNotIn(HOLD_TELEPORT_REASON, [reason for _key, reason in keys])
        # The Phase Door stack keeps the Teleportation slot h: never read.
        self.assertNotIn("rh", [key for key, _reason in keys])

    def test_destruction_comes_before_the_hold_teleport(self):
        """Owner 2026-11-04 「テレポートに代わり*破壊*を使用する」 and 2026-11-13: with no other
        point out of fire, *Destruction* before the Teleportation scroll.  DECLARED
        CONSTRUCTED: a known staff of *Destruction* in the pack, device skill 60 (80%)."""
        policy = self.recorded.policy
        staff = item("x", TVAL_STAFF, SV_STAFF_DESTRUCTION, known=True, charges=5,
                     name="*破壊*の杖 (5回分)")
        keys = []
        for _ in range(6):
            board = self.recorded._board(0)
            board = replace(board, inventory=[*board.inventory, staff],
                            player=replace(board.player, device_skill=60))
            keys.append((policy.choose_key(board), policy.last_reason))
        self.assertEqual(keys[:4], [("T8", "summoner:hold-reposition")] * 4)
        # The sixth ask is the same board (the same turn): the game did not take the key, so the
        # rung reads its own scroll (destruction_use ``_falls_back``).
        self.assertEqual(keys[4:], [("ux", "emergency:destruction"), ("rh", HOLD_TELEPORT_REASON)])


if __name__ == "__main__":
    unittest.main()
