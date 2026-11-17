"""The 50F+ instant-death judgement reads the line of fire as the damage estimate does (review Q5).

Owner 2026-11-15 「被害の見積りと同じにする」: deep_teleport ``fire_p95`` summed the engagement's p95 over
the monsters line_of_fire ``counting`` showed (an unknown grid a wall), while the damage estimate
(``threat_prediction``) reads an awake monster's line over the unknown grids open
(line_of_fire ``danger``, owner 2026-11-08 「未知のマスを壁と見ない」).  Both now read
that one function.

Recorded: tests/fixtures/escape-los-1114.jsonl.gz (tests/test_deep_teleport_1114_recorded, its
replay through the public ``choose_key``), the Angband 60F visit "1654".
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from unittest import mock

from hengbot import deep_teleport, line_of_fire
from tests import test_deep_teleport_1114_recorded as recorded_deep


def _as_before(policy, snapshot, monster):
    return line_of_fire.counting(policy, snapshot, monster)


class InstantDeathLineOfFireTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recorded_deep.DeepTeleportRecordedTest.setUpClass()
        cls.replay = recorded_deep.DeepTeleportRecordedTest("test_above_50f_the_rule_does_not_apply")

    def decide(self, role, turn):
        return self.replay.decide(role, turn)

    def test_one_reading(self):
        """fire_p95 counts exactly the monsters the damage estimate's reading shows."""
        policy, snapshot, _reason = self.decide("1654", 7836354)
        self.assertEqual(deep_teleport.fire_p95(policy, snapshot), 750)
        self.assertGreater(750, snapshot.player.hp)

    def test_hidden_line_over_unknown_grids_is_instant_death(self):
        """Awake monsters whose line crosses grids the board never showed: the estimate reaches
        750 over HP 520, so the teleport is let through (it walked toward *Destruction*)."""
        _policy, snapshot, reason = self.decide("1654", 7836354)
        self.assertEqual(snapshot.player.hp, 520)
        self.assertEqual(reason, "emergency:teleport")

    def test_the_wait_board_reads_the_teleport_too(self):
        _policy, snapshot, reason = self.decide("1654", 7836366)
        self.assertEqual(reason, "emergency:teleport")

    def test_control_the_old_reading_walks(self):
        """The same boards with the old reading (an unknown grid a wall): 0, the walk."""
        with mock.patch.object(type(self), "_reading", _as_before, create=True), \
                mock.patch("hengbot.line_of_fire.danger",
                           lambda policy, snapshot, monster: _as_before(policy, snapshot, monster)):
            policy, snapshot, reason = self.decide("1654", 7836354)
            self.assertEqual(deep_teleport.fire_p95(policy, snapshot), 0)
        self.assertEqual(reason, "sensed-t1:approach-destruction")


if __name__ == "__main__":
    unittest.main()
