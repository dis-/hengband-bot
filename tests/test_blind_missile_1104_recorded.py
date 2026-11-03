"""The blind walk under an unseen missile, on n1-b life-306's board of turn 4876827.

Source: tests/fixtures/death-n1b-306-1104.json.gz.  The recorded board's only hit is
「何か鋭いもので攻撃された！」, a loss of 9 from HP 311.

Owner 2026-11-04: 「ダメージ量で判断し、通常加速や体力回復を使用する場面で使用。脅威度が
低ければ歩いて離れる。」

DECLARED CONSTRUCTED: the Cure Critical Wounds are taken out of the boards after the
first cure (the recorded pack cures instead), and the heavy variants lower that one
board's HP, which is the loss the policy observes.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from tests import test_n1b_306_blind_death_recorded as life306
from tests import test_n1c_deaths_1101_recorded as d57


MISSILE_BOARD = 4876827
SPEED_KEY = "qc"


def answer(*, hp=None):
    policy = life306.new_policy()
    for raw in life306.boards(cures=False):
        if raw["turn"] == MISSILE_BOARD:
            raw["player"]["hp"] = hp or raw["player"]["hp"]
            return raw, d57.loops.decide(policy, raw), policy.last_reason
        policy.confirm_key_posted(d57.loops.decide(policy, raw))
    raise AssertionError(MISSILE_BOARD)


class BlindMissileRecordedTest(d57.PostedDeathKey):
    def test_recorded_board_is_a_missile_only(self):
        raw, _key, _reason = answer()
        self.assertIn("何か鋭いもので攻撃された！", raw["messages"])
        self.assertFalse([m for m in raw["messages"] if m.endswith("押し潰された。")])

    def test_low_damage_walks_away(self):
        _raw, key, reason = answer()
        self.assertEqual((key, reason), ("7", "no-wait:least-visited"))

    def test_heavy_loss_above_the_low_hp_line_takes_the_speed_dose(self):
        raw, key, reason = answer(hp=260)   # a loss of 51; three repeats reach half of HP
        self.assertEqual((key, reason), (SPEED_KEY, "item:strong-fight-speed"))
        self.post(life306.new_policy(), raw, key)

    def test_heavy_loss_below_the_low_hp_line_takes_the_speed_dose(self):
        _raw, key, reason = answer(hp=150)
        self.assertEqual(key, SPEED_KEY, reason)


if __name__ == "__main__":
    unittest.main()
