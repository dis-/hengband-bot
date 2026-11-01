"""D57 (#47) owner answers of 2026-11-01 on the n1-c Magic-Eater's combat.

Memory d57-survival-answers-decision-20261101 (owner, verbatim):

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
DECLARED CONSTRUCTED: the life-085 melee cases raise both hands' displayed
to-hit by 30 (an off hand that hits, as me-dual-wield-1101 pursues), and the
aura case gives the jelly's race AURA_FIRE.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import unittest

from hengbot.magic_eater import MISSILE_REASON
from hengbot.me_ranged_first import TORCH_REASON
from tests import test_me_staff_loops_1031_recorded as loops
from tests import test_n1c_deaths_1101_recorded as d57
from tests import test_town_last_stand_ranged_recorded as d55


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


if __name__ == "__main__":
    unittest.main()
