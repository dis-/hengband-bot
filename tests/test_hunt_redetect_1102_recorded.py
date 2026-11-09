"""The hunt search is cast again 1,000 game turns after the latest one, near
the same place (me_powers HUNT_REDETECT_GAME_TURNS).

Owner 2026-11-02: 「一定の時間ごとに使い直す」, interval 「1,000ゲームターン」 (the
answer to hunt-detect-evil-1102's open question 2: the hunted target moves,
and the radius rule alone never searched again where the bot wandered).

Recorded n1-c life-098, Angband 12F, RANDOM quest 43 (target 鬼殺隊の『先輩』,
race 1164, EVIL), the stuck:wander boards near the before-rest Detect Evil at
(16,17), turn 1173086 (tests/fixtures/hunt-detect-1102.json.gz, see
tests/extract_hunt_detect_1102_fixture.py): turn 1174079 (993 game turns
later, 7 cells away), turn 1174094 (1008 later, 8 cells away) and turn
1176550 (3464 later, 7 cells away; decision 8091 recorded ``search``).  The
floor's earlier uses are the recorded ones; through the public choose_key and
the production executor (the replies to the posted key are DECLARED
CONSTRUCTED, cmd-item/cmd-magiceat.cpp).
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import me_powers
from tests.support import recorded as harness
from tests import test_hunt_detect_1102_recorded as detect
from tests.test_hunt_detect_1102_recorded import DETECT_EVIL_KEY, TYPE_PROMPT, power_screen, prompt

CAST = (16, 17)
CAST_TURN = 1173086
REASON = "me-power:hunt-target-unseen:detect-evil"


class HuntRedetectRecordedTest(harness.ProductionHarness):
    # The recorded-board helpers of the hunt-detect test (through the module,
    # so the loader does not collect its cases here).
    setUpClass = classmethod(detect.HuntDetectRecordedTest.setUpClass.__func__)
    case = detect.HuntDetectRecordedTest.case
    policy = detect.HuntDetectRecordedTest.policy
    choose = detect.HuntDetectRecordedTest.choose
    post = detect.HuntDetectRecordedTest.post
    following = detect.HuntDetectRecordedTest.following

    def latest(self, name):
        case = self.case(name)
        use = max((use for use in case["uses"] if use["used"] == ["staff", 15]),
                  key=lambda use: use["turn"])
        return case["board"]["turn"] - use["turn"], tuple(use["position"])

    def test_interval_reached_near_the_cast_searches_again(self):
        self.assertEqual(me_powers.HUNT_REDETECT_GAME_TURNS, 1000)
        for name, elapsed in (("senior-12f-1008", 1008), ("senior-12f-search", 3464)):
            with self.subTest(name):
                self.assertEqual(self.latest(name), (elapsed, CAST))
                policy, raw = self.policy(name)
                self.assertEqual(raw["visible_monsters"], [])
                key = self.choose(policy, raw)
                self.assertEqual((key, policy.last_reason), (DETECT_EVIL_KEY, REASON))
                game, _ = self.post(policy, raw, key, [
                    prompt(TYPE_PROMPT), power_screen("staff", [("p", "邪悪存在感知", 14, 14, 5)])],
                    following=self.following(raw))
                self.assertEqual(game.accepted, ["m", "A", "p"])
        row = self.case("senior-12f-search")["rows"][0]
        self.assertEqual((row["decision_sequence"], row["reason"]), (8091, "search"))

    def test_before_the_interval_near_the_cast_does_not(self):
        self.assertEqual(self.latest("senior-12f-993"), (993, CAST))
        policy, raw = self.policy("senior-12f-993")
        self.choose(policy, raw)
        self.assertNotIn("hunt-target-unseen", policy.last_reason)


if __name__ == "__main__":
    unittest.main()
