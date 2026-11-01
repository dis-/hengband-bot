"""Recorded Q31 entry: the absorbed Teleport Away moves the Huorn first (q31-huorn-first-1102).

Owner 2026-11-02: 「テレポートアウェイがあるなら初手でフォルンをどかす。その後の行動は作戦通り。」

Source: tests/fixtures/death-n1c-099-1102.json.gz (n1-c life-099, the
クエスト31『柳じじい』 floor; tests/extract_n1c_death_1102_fixture.py).  On the
entry board (turn 691290, sequence 1365) the Lv23 Magic-Eater stands on the
hold [18,1] with no hostile in sight and the recorded bot held ('5'); the
Huorn (race 329) at [16,3] is not lit yet.  Its TELE_TO pulled the player out
of the hold beside two sasquatches on turn 691383 (sequence 1381,
「フオルンがあなたを引き戻した。」), which began the death.  With the plan's
``opening_teleport_away`` row the first key aims the rod of Teleport Away
(priority 70, before the wand) north-east along [17,2] at [16,3]: 'mCn9'.

DECLARED RECONSTRUCTED: the displayed wand and rod lists are
test_n1c_death_1102_recorded.LISTS (the death dump's absorbed devices).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from tests import test_me_mining_death_recorded as mining_death
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_d57_me_combat_1101_recorded import DIRECTION_PROMPT, TELEPORT_AWAY, TYPE_PROMPT
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_n1c_death_1102_recorded import CASE, new_policy


ENTRY_TURN = 691290  # sequence 1365
OPENING_AWAY = ("mCn9", "me-power:quest-opening-target:teleport-away")


class Q31HuornFirstRecordedTest(d57.PostedDeathKey):

    post_power = mining_death.MagicEaterMiningDeathRecordedTest.post

    def test_the_entry_board_teleports_the_huorn_away_through_the_executor(self):
        self.assertEqual(d57.recorded(CASE)[ENTRY_TURN], ("quest-strategy:hold", "5"))
        raw = copy.deepcopy(CASE["boards"][0])
        self.assertEqual((raw["turn"], raw["player"]["y"], raw["player"]["x"]), (ENTRY_TURN, 18, 1))
        self.assertEqual(raw["visible_monsters"], [])
        policy = new_policy()
        key = d57.loops.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), OPENING_AWAY)
        game, _ = self.post_power(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("rod", [("n", TELEPORT_AWAY, 0, 1, 30)]),
            prompt(DIRECTION_PROMPT, "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "C", "n", "9"])


if __name__ == "__main__":
    unittest.main()
