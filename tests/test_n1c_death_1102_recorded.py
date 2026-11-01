"""Recorded replay of the n1-c life-099 death of 2026-11-02 (n1c-death-1102).

Source: tests/fixtures/death-n1c-099-1102.json.gz
(tests/extract_n1c_death_1102_fixture.py): every board of the クエスト31
『柳じじい』 floor of the Lv23 Magic-Eater, turns 691290 (entry) - 691735
(death), with the recorded decision rows.

- Survival first (owner 「生存処理を優先しなければキャラクタは死亡する。当然の結果。」):
  from turn 691606 (HP 199/310) the recorded bot aimed the absorbed Teleport
  Away (me_powers THREAT, ``unbeatable-in-range``) at one sasquatch after
  another down to HP 18 while 2-15 hostiles stayed in view; that rung ran
  before the emergency ladder, which never asked.  On the boards of turns
  691626 (HP 129, sequence 1416) and 691696 (HP 77, 1425) the ladder reads
  its Teleport scroll.
- The quest plan's Speed trigger (consumable_plan.speed_potion_use_when,
  the 3-turn projection at least half the HP) drank the first potion on
  691305; its haste ran out on 691537 (「動きの素早さがなくなったようだ。」)
  beside a vorpal bunny, a sasquatch and a sabre-tooth tiger (projection
  553 against HP 310), and the one-shot mark kept the second potion in the
  pack to the death.  That board drinks it.

DECLARED RECONSTRUCTED: the displayed wand and rod lists carry the death
dump's absorbed テレポート・アウェイ (wand 12, rod 1) and its other wands
(bot_test2_Autodump_2026-11-02_014825.txt); the fail percentages are
constructed.  The quest definition is the game's lib/edit (as
test_q31_survey_sweep_recorded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.quest_knowledge import load_quest_knowledge
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_d57_me_combat_1101_recorded import AWAY_REASON, TELEPORT_AWAY


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1c-099-1102.json.gz"
EDIT = Path("C:/hengband/lib/edit")
QUEST = 31
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

LOW_HP_TURNS = (691626, 691696)  # sequences 1416 (HP 129) and 1425 (HP 77)
EMERGENCY_TELEPORT = ("re", "emergency:teleport")
SPEED_DOSE_TURN, HASTE_ENDED_TURN = 691305, 691537  # sequences 1366, 1408
QUAFF_SPEED = ("qb", "quest-strategy:quaff-speed")
# DECLARED RECONSTRUCTED (module docstring).
LISTS = (
    {"kind": "wand", "rows": [
        {"name": TELEPORT_AWAY, "current": 12, "max": 12, "fail": 10, "success": 90},
        {"name": "トラップ解除", "current": 6, "max": 6, "fail": 10, "success": 90},
        {"name": "岩石溶解", "current": 12, "max": 12, "fail": 10, "success": 90},
        {"name": "悪臭雲", "current": 15, "max": 15, "fail": 10, "success": 90},
        {"name": "マジック・ミサイル", "current": 28, "max": 28, "fail": 5, "success": 95}]},
    {"kind": "rod", "rows": [
        {"name": TELEPORT_AWAY, "charging": 0, "max": 1, "fail": 30, "success": 70}]},
)


def new_policy():
    policy = d57.new_policy(CASE)
    policy._quest_knowledge[QUEST] = load_quest_knowledge(EDIT / "quests")[QUEST]
    for listed in LISTS:
        first = dict(copy.deepcopy(CASE["boards"][0]),
                     _magic_eater_power_list=copy.deepcopy(listed))
        first["turn"] -= 1  # an earlier board on which the game displayed it
        observe_lists(policy, parse_snapshot(first, policy._monrace_knowledge))
    return policy


class Q31DeathRecordedTest(d57.PostedDeathKey):
    prompts = {**d57.PROMPTS, "r": "どの巻物を読みますか? "}

    def drive(self, expected):
        """The quest floor's boards through the public choose_key up to the
        last board of ``expected`` (turn: (key, reason)); each of those boards
        answers as expected and its key goes through the production executor."""
        policy = new_policy()
        for raw in CASE["boards"]:
            if raw["turn"] > max(expected):
                break
            raw = copy.deepcopy(raw)
            key = d57.loops.decide(policy, raw)
            if raw["turn"] in expected:
                self.assertEqual((key, policy.last_reason), expected[raw["turn"]], raw["turn"])
                self.post(policy, raw, key)
            policy.confirm_key_posted(key)

    def test_low_hp_boards_take_the_emergency_ladder_through_the_executor(self):
        recorded = d57.recorded(CASE)
        boards = {raw["turn"]: raw for raw in CASE["boards"]}
        for turn in LOW_HP_TURNS:
            self.assertEqual(recorded[turn][0], AWAY_REASON)
            player = boards[turn]["player"]
            self.assertLess(player["hp"], player["max_hp"] // 2)
        self.drive(dict.fromkeys(LOW_HP_TURNS, EMERGENCY_TELEPORT))

    def test_the_second_speed_potion_follows_the_ended_haste_through_the_executor(self):
        recorded = d57.recorded(CASE)
        self.assertEqual(recorded[SPEED_DOSE_TURN], ("quest-strategy:quaff-speed", "qb"))
        self.assertEqual(recorded[HASTE_ENDED_TURN], ("quest-strategy:melee", "7"))
        self.drive({SPEED_DOSE_TURN: QUAFF_SPEED, HASTE_ENDED_TURN: QUAFF_SPEED})

if __name__ == "__main__":
    unittest.main()
