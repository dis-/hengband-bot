"""Recorded replay of the n1-c life-103 death of 2026-11-02 13:47 (城42階).

Source: tests/fixtures/death-n1c-103-1102.json.gz
(tests/extract_n1c_death_103_1102_fixture.py): the Lv36 Magic-Eater's boards
of turns 3831825-3831864 after 点『P』 teleported it beside gargoyles, an
アーチ=ヴァイル and 濃尾無双『岩本虎眼』, with the recorded decision rows.

Blind at HP 97/512 after a 291-HP round (turn 3831859), the emergency
ladder's status cure drank the cheapest cure, Cure Critical Wounds (6d8),
with Healing (300) carried; HP 45 on the next board, Teleport, death.  Owner
2026-11-01 (D57): 「致命傷治癒はHP回復の効果に期待しない。HPが減ったら体力回復か
テレポート。」  The blind player cannot read the Teleport, so that board
drinks Healing (the heal-vs-teleport rule's potion), and the key goes
through the production executor.  The earlier boards answer as recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1c-103-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

LOW_HP_BLIND_TURN = 3831859
QUAFF_HEALING = ("qb", "emergency:cure-status-healing")


class BlindLowHpHealRecordedTest(d57.PostedDeathKey):
    def test_blind_low_hp_board_drinks_healing_through_the_executor(self):
        recorded = d57.recorded(CASE)
        self.assertEqual(recorded[LOW_HP_BLIND_TURN], ("emergency:cure-critical", "qa"))
        board = next(raw for raw in CASE["boards"] if raw["turn"] == LOW_HP_BLIND_TURN)
        self.assertEqual((board["player"]["hp"], board["player"]["max_hp"]), (97, 512))
        self.assertEqual([item["name"] for item in board["inventory"]
                          if item["slot"] in "ab"], ["致命傷の治癒の薬", "体力回復の薬 {25%引き}"])
        policy = d57.new_policy(CASE)
        for raw in CASE["boards"]:
            raw = copy.deepcopy(raw)
            key = d57.loops.decide(policy, raw)
            if raw["turn"] == LOW_HP_BLIND_TURN:
                self.assertEqual((key, policy.last_reason), QUAFF_HEALING)
                self.post(policy, raw, key)
                return
            self.assertEqual((policy.last_reason, key), recorded[raw["turn"]], raw["turn"])
            policy.confirm_key_posted(key)


if __name__ == "__main__":
    unittest.main()
