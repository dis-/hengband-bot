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
from hengbot.model import SV_SCROLL_PHASE_DOOR
from hengbot.summoner_wait import HOLD_TELEPORT_REASON


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


if __name__ == "__main__":
    unittest.main()
