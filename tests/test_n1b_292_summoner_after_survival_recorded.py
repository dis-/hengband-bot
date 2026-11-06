"""n1-b life-292 (2026-11-02, 城18階): the emergency ladder answers before the summoner shots.

Owner 2026-11-06, the option 「命に関わる時の後へ回す」: 「緊急の薬や逃げる判断を先にします。
今日の「生存を優先」と揃います。記録で変わるのは1場面だけです。」  ``_summoner_ranged_kill_key``
stood above ``_emergency_item`` in ``_decide``; it now stands below the emergency ladder
(dungeon_ladder's "summoner-shots" layer).

Recorded: at turn 1376483 (HP 181/471) the Magic-Eater shot the summoner
(summoner:ranged-kill ``fu*t5``); the healing potion waited for the next board
(HP 165, item:heal ``qd``).  Source: tests/fixtures/n1b-292-summoner-after-survival-1102.json.gz
(tests/extract_n1b_292_summoner_after_survival_fixture.py).  The summons rules of 2026-11-04
(summon_response) did not exist then; replayed from the fight's start they answer this board
themselves, so the policy here starts on the board before (turn 1376478) with no summons
counted on the floor, as the record's policy had.  Every decision goes through the public
``choose_key``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-292-summoner-after-survival-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

BEFORE, SHOT, HEALED = 1376478, 1376483, 1376488


class SummonerAfterSurvivalRecordedTest(unittest.TestCase):
    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        self.assertEqual(recorded[SHOT], ("summoner:ranged-kill", "fu*t5\x1b"))
        self.assertEqual(recorded[HEALED], ("item:heal", "qd"))
        board = next(raw for raw in CASE["boards"] if raw["turn"] == SHOT)
        self.assertEqual((board["player"]["hp"], board["player"]["max_hp"]), (181, 471))

    def test_the_emergency_item_answers_before_the_summoner_shot(self):
        boards = [raw for raw in CASE["boards"] if BEFORE <= raw["turn"] <= SHOT]
        policy = d57.loops.new_policy(dict(CASE, boards=boards), CASE["skill"],
                                      monraces=CASE["monraces"])
        for raw in boards:
            key = d57.loops.decide(policy, copy.deepcopy(raw))
            if raw["turn"] == SHOT:
                break
            policy.confirm_key_posted(key)
        self.assertEqual((key, policy.last_reason), ("qd", "item:heal"))


if __name__ == "__main__":
    unittest.main()
