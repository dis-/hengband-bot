"""Owner 2026-11-04 「要求は深くなるごとにAND条件で厳しくする想定」.

n1-a life-475 02:2x, a Lv39 warrior: row 12 of the visit recalled to dungeon 12's
49F ('rdg', town:recall-to-alt-dungeon) wearing every ability up to 49F.  49F asks
every band at or above its first floor, so the same board without free action (a
20F ability) does not land on 49F.  It does not stop either: the owner's
no-safe-destination set (2026-10-19) answers the gap.  The band-by-band reading
asked only resist_chaos and resist_neth here and recalled.
DECLARED RECONSTRUCTED: free action removed from the recorded departure board.
Fixture: tests/extract_depth_cumulative_1104_fixture.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from dataclasses import replace
from pathlib import Path
import unittest

from test_me_stops_1103_recorded import Visit


FIXTURE = Path(__file__).with_name("fixtures") / "depth-cumulative-1104"


class DepthCumulativeRecordedTest(unittest.TestCase):
    def test_a_low_band_gap_refuses_the_deep_landing_without_a_stop(self):
        visit = Visit(FIXTURE)
        self.addCleanup(visit.close)
        recorded, board = visit.replay_until_last(self)
        policy = visit.policy
        self.assertEqual((recorded["key"], recorded["reason"]), ("rdg", "town:recall-to-alt-dungeon"))
        self.assertTrue(policy._destination_depth_allowed(board, 49))

        gapped = replace(board, player=replace(
            board.player, abilities=board.player.abilities - {"free_action"}))
        key = policy.choose_key(gapped)

        self.assertNotEqual(key, recorded["key"])
        self.assertEqual(
            policy.last_reason,
            "town:entrance-step-off:fundraising:no-safe-destination:"
            "depth-gate:destination-49:missing-free_action")
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertTrue(policy._no_safe_destination_set)
        self.assertIsNone(policy._town_blocked_reason)


if __name__ == "__main__":
    unittest.main()
