"""D57 (#47) owner answers of 2026-11-01 on the n1-c Magic-Eater's combat.

Memory d57-survival-answers-decision-20261101 (owner, verbatim):

(b) 取り込んだテレポート・アウェイ 「勝てない敵が射程内にいればいつでも使って良い」
    -- the absorbed Teleport Away (wand 3 / rod 13) is aimed at a visible
    hostile on a beam's line that the engagement judgement says cannot be
    beaten (me_powers row, THREAT occasion).
(c) 隣の敵への攻撃 「見込みの大きい方を使う」 -- beside a hostile the
    Magic-Eater uses whichever of its absorbed powers / Magic Missile, a
    carried attack wand, a thrown lit torch and melee has the larger expected
    damage per player action; a monster that hurts on touch is no melee
    target (me_ranged_first, attack_expectation).

Recorded boards (every decision is the public ``choose_key``; posted keys go
through the production executor port):
- n1-c life-077 (D55, tests/fixtures/death-n1c-077-1101.json.gz): the Lv8
  town last stand beside a 見習戦士 (race 43), sixteen spare lit torches and
  the absorbed 2d6 Magic Missile.  A torch hits the AC 16 warrior for about
  22 per throw (throw-execution.cpp, attack_expectation.torch_throw), the
  missile 7; the recorded build fired neither, the D55 build fires the
  missile.
- n1-c life-085 (D57, tests/fixtures/death-n1c-085-1101.json.gz): the Lv18
  Magic-Eater beside 『スーパー・グレート・シルバー・ゼリー』 (race 1273, AC 1).
  Its two blades show to-hit -10/-14 with fighting skill 99: the hit chance
  is the 5% floor (warrior_equipment_evaluator.displayed_melee_hit_chance),
  so melee expects about 2 against the 3d6 missile's 10.5 and the recorded
  missile stays the answer.
- n1-c life-083 (tests/fixtures/d57-me-combat-083-1101.json.gz,
  tests/extract_d57_me_combat_1101_fixtures.py): sighted again at turn
  1190789 (HP 118/171) beside a ブラウン・キラービートル (race 236, 104 hp,
  three bites); the recorded answer was the Magic Missile and melee, then
  confusion and death beside it.  Missile 3d6 needs ten actions while the
  beetle's bites outdamage the 118 hp: not winnable.
DECLARED RECONSTRUCTED: the life-083 displayed wand list carries the absorbed
テレポート・アウェイ (12) and マジック・ミサイル (23) of the death dump
(bot_test2_Autodump_2026-11-01_064803.txt); the fail percentages are
constructed (10%, 5%).
DECLARED CONSTRUCTED: the life-085 melee cases raise both hands' displayed
to-hit by 30 (an off hand that hits, as me-dual-wield-1101 pursues), and the
aura case gives the jelly's race AURA_FIRE.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import gzip
import json
import unittest
from pathlib import Path

from hengbot.magic_eater import MISSILE_REASON
from hengbot.me_device_attacks import observe_lists
from hengbot.me_ranged_first import TORCH_REASON
from hengbot.model import parse_snapshot
from tests import test_me_staff_loops_1031_recorded as loops
from tests import test_n1c_deaths_1101_recorded as d57
from tests import test_town_last_stand_ranged_recorded as d55
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_mining_death_recorded import MagicEaterMiningDeathRecordedTest as mining


def _fixture(life):
    path = Path(__file__).with_name("fixtures") / f"d57-me-combat-{life}-1101.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


CASE_083, CASE_084 = _fixture("083"), _fixture("084")
BEETLE, BEETLE_TURN = 236, 1190789
TELEPORT_AWAY = "テレポート・アウェイ"
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
DIRECTION_PROMPT = "方向 ('*'でターゲット選択, ESCで中断)?"
AWAY_REASON = "me-power:unbeatable-in-range:teleport-away"
# DECLARED RECONSTRUCTED (module docstring): the death dump's wand counts.
WAND_LIST = {"kind": "wand", "rows": [
    {"name": TELEPORT_AWAY, "current": 12, "max": 12, "fail": 10, "success": 90},
    {"name": "マジック・ミサイル", "current": 23, "max": 23, "fail": 5, "success": 95}]}


JELLY = d57.JELLY
JELLY_TURNS = (1445315, 1445328)
TO_HIT_RAISE = 30


def jelly_boards(*, raise_to_hit=0):
    rows = d57.boards(d57.CASE_085, *JELLY_TURNS)
    for raw in rows:
        melee = raw["player"]["melee"]
        for hand in ("main_hand_to_h", "sub_hand_to_h"):
            melee[hand] += raise_to_hit
    return rows


class AdjacentAttackChoiceRecordedTest(d57.PostedDeathKey):
    """(c) beside the target, the larger expected damage per action."""

    def test_recorded_rows(self):
        stand = {raw["turn"] for raw in d55.CASE["boards"][1:]}
        self.assertEqual({(row["reason"], row["key"]) for row in d55.CASE["decisions"]
                          if row["turn"] in stand}, {(d55.STAND, "2")})
        rows = d57.recorded(d57.CASE_085)
        self.assertEqual({rows[turn] for turn in (1445315, 1445321, 1445328)},
                         {(MISSILE_REASON, "mBp8")})
        first = jelly_boards()[0]
        self.assertEqual((first["player"]["melee"]["main_hand_to_h"],
                          first["player"]["melee"]["sub_hand_to_h"]), (-10, -14))

    def test_beside_the_novice_warrior_the_torch_outscores_the_missile(self):
        policy = loops.new_policy(d55.CASE, d55.CASE["skill"], record=d55.CASE["sequence"],
                                  monraces=d55.CASE["monraces"])
        rows = loops.MeStaffLoopsRecordedTest.drive(self, policy, d55.boards())[1:]
        self.assertEqual({(key[0], key[-1], reason) for _raw, key, reason in rows},
                         {("v", "2", TORCH_REASON)})

    def test_missing_blades_leave_the_jelly_to_the_missile(self):
        rows = self.drive(d57.new_policy(d57.CASE_085), jelly_boards())
        self.assertEqual({(key, reason) for _raw, key, reason in rows},
                         {("mBp8", MISSILE_REASON)})

    def test_hitting_blades_melee_the_jelly(self):
        rows = self.drive(d57.new_policy(d57.CASE_085), jelly_boards(raise_to_hit=TO_HIT_RAISE))
        self.assertEqual({key for _raw, key, _reason in rows}, {"8"})

    def test_a_touch_aura_keeps_the_jelly_off_melee(self):
        policy = d57.new_policy(d57.CASE_085)
        race = policy._monrace_knowledge[JELLY]
        policy._monrace_knowledge[JELLY] = dataclasses.replace(
            race, flags=race.flags | {"AURA_FIRE"})
        rows = self.drive(policy, jelly_boards(raise_to_hit=TO_HIT_RAISE))
        self.assertEqual({(key, reason) for _raw, key, reason in rows},
                         {("mBp8", MISSILE_REASON)})



class TeleportAwayRecordedTest(d57.PostedDeathKey):
    """(b) an unbeatable hostile in range is sent away."""

    post_power = mining.post

    def decide_all(self, policy, rows):
        answers = []
        for raw in rows:
            key = loops.decide(policy, raw)
            answers.append((raw, key, policy.last_reason))
            policy.confirm_key_posted(key)
        return answers

    def beetle_policy(self, *, listed=True):
        policy = d57.new_policy(CASE_083)
        if listed:
            first = dict(copy.deepcopy(CASE_083["boards"][0]),
                         _magic_eater_power_list=copy.deepcopy(WAND_LIST))
            first["turn"] -= 1  # an earlier board on which the game displayed it
            observe_lists(policy, parse_snapshot(first, policy._monrace_knowledge))
        return policy

    def test_recorded_rows(self):
        rows = d57.recorded(CASE_083)
        self.assertEqual(rows[BEETLE_TURN], ("melee", "4"))
        raw = CASE_083["boards"][-1]
        self.assertEqual(raw["turn"], BEETLE_TURN)
        board = parse_snapshot(copy.deepcopy(raw), d57.new_policy(CASE_083)._monrace_knowledge)
        self.assertEqual([(m.race_id, m.distance) for m in board.visible_monsters
                          if m.hostile], [(BEETLE, 1)])
        self.assertFalse(board.player.blind or board.player.confused)

    def test_the_unbeatable_beetle_is_sent_away_through_the_executor(self):
        policy = self.beetle_policy()
        raw, key, reason = self.decide_all(policy, copy.deepcopy(CASE_083["boards"]))[-1]
        self.assertEqual((raw["turn"], key, reason), (BEETLE_TURN, "mBd4", AWAY_REASON))
        game, _ = self.post_power(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("wand", [("d", TELEPORT_AWAY, 12, 12, 10),
                                                       ("p", "マジック・ミサイル", 23, 23, 5)]),
            prompt(DIRECTION_PROMPT, "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "B", "d", "4"])

    def test_control_without_the_power_the_missile_answers(self):
        raw, key, reason = self.decide_all(self.beetle_policy(listed=False),
                                           copy.deepcopy(CASE_083["boards"]))[-1]
        self.assertEqual((key, reason), ("mBp4", MISSILE_REASON))

    def test_control_a_beatable_beetle_is_fought(self):
        # DECLARED CONSTRUCTED: the beetle is nearly dead (one missile).
        rows = copy.deepcopy(CASE_083["boards"])
        for monster in rows[-1]["visible_monsters"]:
            monster["health"] = "almost_dead"
        policy = self.beetle_policy()
        raw, key, reason = self.decide_all(policy, rows)[-1]
        self.assertNotEqual(reason, AWAY_REASON, key)


if __name__ == "__main__":
    unittest.main()
