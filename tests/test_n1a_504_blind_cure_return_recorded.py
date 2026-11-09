"""Recorded replay of n1-a life-504 after its last blindness cure (鉄獄24階, random quest 41).

Source: tests/fixtures/n1a-504-blind-1110.json.gz (tests/extract_n1a_504_blind_rest_fixture.py),
boards of turns 880383-880451 and 895901-896673.  The light hounds took its last Healing at
880417 (test_n1a_504_short_blind_recorded); from 880426 it carried no potion that cures
blindness, and the random-quest exit lock (QuestPolicyMixin._quest_floor_exit_locked)
kept it on the floor with twelve or more Teleport scrolls (the 2026-11-01 reserve releases
below five) until the gas trap of 896684 blinded it with nothing to cure it.

Owner 2026-11-10 (G2) 「0本になったら帰還」: 「盲目を治す薬（致命傷の治癒・回復など）が0本に
なったら、ランダムクエストの階でも帰還してよい。クエストは後でやり直す。」
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot import random_quest_reserve
from tests.test_n1a_504_blind_rest_recorded import CASE, GAS_TRAP, LANDING, boards, decide, new_policy


NO_CURE, TELEPORTS = 880426, "テレポートの巻物"


def run(first, last):
    policy, answers = new_policy(first), {}
    for raw in boards(first, last):
        key = decide(policy, raw)
        answers[raw["turn"]] = (key, policy.last_reason, policy._last_return_trigger)
        policy.confirm_key_posted(key)
    return answers


class BlindCureReturnRecordedTest(unittest.TestCase):
    def test_recorded_boards(self):
        for raw in boards(NO_CURE, GAS_TRAP):
            self.assertEqual(raw["floor"]["quest_id"], 41, raw["turn"])
            names = " ".join(item["name"] for item in raw["inventory"])
            self.assertNotIn("致命傷の治癒", names, raw["turn"])
            self.assertNotIn("体力回復", names, raw["turn"])
            scrolls = sum(item["count"] for item in raw["inventory"] if TELEPORTS in item["name"])
            self.assertGreaterEqual(scrolls, random_quest_reserve.RANDOM_QUEST_TELEPORT_RESERVE,
                                    raw["turn"])
        recorded = {row["turn"]: row["reason"] for row in CASE["decisions"]}
        self.assertNotIn("return:recall", [recorded[turn] for turn in recorded if turn < GAS_TRAP])

    def test_no_blindness_cure_reads_recall_on_the_random_quest_floor(self):
        answers = run(880383, 880451)
        key, reason, trigger = answers[NO_CURE]
        self.assertEqual((key[:1], reason, trigger),
                         ("r", "return:recall", random_quest_reserve.BLIND_CURES_RETURN_TRIGGER))
        # The last Healing still carried: the floor holds the player.
        self.assertNotEqual(answers[880402][1], "return:recall")

    def test_the_landing_reads_recall_before_the_gas_trap(self):
        answers = run(LANDING, GAS_TRAP - 1)
        key, reason, trigger = answers[LANDING]
        self.assertEqual((key[:1], reason, trigger),
                         ("r", "return:recall", random_quest_reserve.BLIND_CURES_RETURN_TRIGGER))


if __name__ == "__main__":
    unittest.main()
