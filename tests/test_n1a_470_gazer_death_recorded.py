"""Recorded replay of the n1-a life-470 death of 2026-11-03 09:50 (イークの洞穴13階).

Source: tests/fixtures/death-n1a-470-1103.json.gz
(tests/extract_n1a_470_gazer_death_fixture.py): the Lv15 warrior's boards of
turns 293167-293675 (310 max HP, no Free Action, build 96a499308) from the
arrival on 13F, and the recorded decision rows.

After the カミカゼ・イーク fight an awake ゲイザー (race 218, speed +0,
GAZE:PARALYZE/CONFUSE, HOLD) came two cells away.  The status-threat rung
read its escape scroll only beside the attacker and otherwise walked
(``status-threat:retreat``, 293657-293675) with 14 Teleportation scrolls in
the pack; the gazer kept pace, the player was paralyzed (status bar 「麻痺
混乱」) and died at the yeeks' and 『ボルドール』's hands from HP 234/310.

Owner 2026-11-03: 「階段が隣などとても近くにある場合を除き徒歩での逃走は
絶対に間に合わない。」 and survival first.  A walk cannot outpace a mover at
least as fast as the player (paralyzer_contact.follows_walk), so the rung
reads the Teleportation scroll.  Every decision is the public ``choose_key``;
the read keys go through the production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1a-470-1103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

RETREATS = (293657, 293668, 293675)   # the awake gazer two to three cells away
GAZER = 218


class GazerWalkRecordedTest(d57.PostedDeathKey):
    prompts = {**d57.PROMPTS, "r": "どの巻物を読みますか? "}

    def answers(self):
        policy, answers = d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"]), {}
        for raw in CASE["boards"]:
            raw = copy.deepcopy(raw)
            key = d57.loops.decide(policy, raw)
            answers[raw["turn"]] = (key, policy.last_reason)
            if raw["turn"] in RETREATS:
                self.post(policy, raw, key)
            policy.confirm_key_posted(key)
        return answers

    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        rows = {raw["turn"]: raw for raw in CASE["boards"]}
        for turn in RETREATS:
            self.assertEqual(recorded[turn][0], "status-threat:retreat", turn)
            gazer = [m for m in rows[turn]["visible_monsters"] if m["race_id"] == GAZER]
            self.assertEqual([m["asleep"] for m in gazer], [False], turn)

    def test_teleports_away_from_the_gazer_it_cannot_outwalk(self):
        answers = self.answers()
        scroll = next(item["slot"] for item in CASE["boards"][-1]["inventory"]
                      if item["name"].startswith("テレポートの巻物"))
        for turn in RETREATS:
            self.assertEqual(answers[turn], ("r" + scroll, "status-threat:scroll"), turn)


if __name__ == "__main__":
    unittest.main()
