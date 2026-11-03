"""Recorded board of the n1-a life-475 death of 2026-11-04 02:25 (城49階), decision 13214.

Source: tests/fixtures/death-n1a-475-1104.json.gz
(tests/extract_n1a_475_summoner_shots_fixture.py).  The second emergency teleport
latched the return (decision row: last_return_trigger emergency-repeat,
dive_emergencies 2) and landed at HP 848/970 with ten Recall scrolls among sleeping
undead.  It meleed, the room woke, and no Recall was read before the death.

Owner 2026-11-04: 「隣に起きた敵がいない、は条件として弱い。視界内=攻撃を受ける範囲に
起きた敵がいない、くらいの条件は必要。」

DECLARED RECONSTRUCTED: the fixture starts on this board, so the policy is seeded
with the recorded latch.  DECLARED CONSTRUCTED: the controls edit the recorded
board or stub the floor's quest state, as each states.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from unittest import mock

from hengbot import once_quest_recall
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_n1a_475_summoner_shots_recorded import CASE


LANDING = 2038869
RECALL_KEY = "rd"


def landing():
    raw = copy.deepcopy(CASE["boards"][0])
    assert raw["turn"] == LANDING
    return raw


def latched_policy():
    policy = d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
    policy._returning_to_town = True
    policy._last_return_trigger = "emergency-repeat"
    policy._dive_emergencies = 2
    return policy


def nearest_ghoul(raw):
    here = raw["player"]
    return next(monster for monster in raw["visible_monsters"]
                if (monster["y"], monster["x"]) == (here["y"] - 1, here["x"]))


class LatchedRecallRecordedTest(d57.PostedDeathKey):
    prompts = {**d57.PROMPTS, "r": "どの巻物を読みますか? "}

    def test_recorded_row(self):
        self.assertEqual(d57.recorded(CASE)[LANDING], ("melee", "8"))
        raw = landing()
        self.assertTrue(all(monster["asleep"] for monster in raw["visible_monsters"]))
        self.assertFalse(raw["player"]["recalling"])

    def test_sleepers_in_view_read_the_recall_first(self):
        policy, raw = latched_policy(), landing()
        key = d57.loops.decide(policy, copy.deepcopy(raw))
        self.assertEqual((key, policy.last_reason), (RECALL_KEY, "return:recall"))
        self.post(policy, raw, key)

    def test_awake_hostile_in_view_keeps_todays_answer(self):
        raw = landing()
        nearest_ghoul(raw)["asleep"] = False
        policy = latched_policy()
        key = d57.loops.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("8", "melee"))

    def test_awake_monster_known_by_detection_does_not_count(self):
        raw = landing()
        awake = dict(copy.deepcopy(raw["visible_monsters"][0]), asleep=False, detected=True,
                     esp=True, index=4000, y=raw["player"]["y"] + 30, x=raw["player"]["x"] + 40)
        raw["detected_monsters"] = [*raw.get("detected_monsters", []), awake]
        policy = latched_policy()
        self.assertEqual(d57.loops.decide(policy, raw), RECALL_KEY)

    def test_running_countdown_is_not_read_again(self):
        raw = landing()
        raw["player"]["recalling"] = True
        policy = latched_policy()
        key = d57.loops.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("8", "melee"))

    def test_once_quest_recall_hold_wins(self):
        policy = latched_policy()
        with mock.patch.object(once_quest_recall, "held", return_value=True):
            key = d57.loops.decide(policy, landing())
        self.assertEqual((key, policy.last_reason), ("8", "melee"))

    def test_quest_exit_lock_wins(self):
        policy = latched_policy()
        with mock.patch.object(type(policy), "_one_shot_quest_exit_lock_held", return_value=True):
            key = d57.loops.decide(policy, landing())
        self.assertNotEqual(key, RECALL_KEY)


if __name__ == "__main__":
    import unittest
    unittest.main()
