"""RES_ALL read as the game applies it: はぐれメタル is T1 and the T1 rules' *Destruction* answers it,
recorded.

Owner 2026-11-18 (verbatim): 「RES_ALLの読み取り方がおかしい。はぐれメタルには事実上ダメージを与える
方法がなく、倒せないのでT1扱い。」

Game (C:/hengband/src):
 * monster/monster-status.cpp:76-81 mon_damage_mod: against RESIST_ALL a physical hit (melee
   player-attack.cpp:488, a shot shoot.cpp:799, a throw throw-execution.cpp:517) is divided by
   100 after the armour; a hit left at 0 deals 1 when one_in_(3).
 * effect/effect-monster.cpp:145-167: a spell effect on a RESIST_ALL monster does nothing
   (「には完全な耐性がある！」) unless its attribute is DEBUG, MONSTER_MELEE or MONSTER_SHOOT (none
   the player sends) or a non-damaging OLD_CLONE/STAR_HEAL/OLD_HEAL/OLD_SPEED/CAPTURE/PHOTO.
 * spell-kind/spells-floor.cpp:277-300 destroy_area deletes every monster in the circle but a
   QUESTOR, with no damage roll: *Destruction* removes it.

n1-c life-216 (Angband 80F, 2026-11-18; tests/test_n1c_216_death_1118_recorded, fixture
tests/fixtures/n1c-216-death-1118.jsonl.gz): the metal (race 871: AC 10000, 3d2 HP, RES_ALL) was
in view at distance 3 on game turn 7228517.  The single damage reader (attack_expectation)
counted each landed blow at its full damage, so the kill read about four actions and the tiers
read T3 (fail-before: the replay fires the bow, ``ranged:fire``).  Each landed blow now deals
1/3 on average (the blow is far below 100): 18 landings, 72 actions, and the projection's
incoming over them passes every supply: T1, and the T1 rules use *Destruction*.

DECLARED CONSTRUCTED: the absorbed *Destruction* row (70 charges, 95%) is given to the fresh
policy, as the live character held it (its power list is not on these boards), for the decision
test; the controls remove RES_ALL from the race.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import unittest
from unittest import mock

from hengbot import (
    attack_expectation, destruction_use, me_capability, me_device_attacks, threat_projection,
    threat_tiers,
)
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.test_n1c_216_death_1118_recorded import METAL, SEEN, Replay


def destruction_row(turn):
    return {"staff": (turn, ({"name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0],
                              "current": 70, "max": 70, "fail": 5, "success": 95},))}


class ResAllReadingTest(unittest.TestCase):

    def test_a_landed_hit_through_res_all(self):
        # Below 100 the hit is left at 0, and 1 one time in 3.
        self.assertAlmostEqual(attack_expectation.res_all_landing(99), 1 / 3)
        self.assertEqual(attack_expectation.res_all_landing(250), 2.0)
        # Four landings an action at 30 each: 4/3 an action, 1/3 a landing.
        self.assertEqual(attack_expectation.physical_hits(frozenset({"RES_ALL"}), 120.0, 30.0),
                         (4 / 3, 1 / 3))
        # Without the flag nothing changes.
        self.assertEqual(attack_expectation.physical_hits(frozenset({"EVIL"}), 120.0, 30.0),
                         (120.0, 30.0))

    def test_spells_do_nothing(self):
        self.assertTrue(attack_expectation.spell_nullified(frozenset({"RES_ALL"})))
        power = me_device_attacks.POWERS[me_device_attacks.MISSILE]
        self.assertEqual(me_device_attacks.expected_damage(power, 50, frozenset({"RES_ALL"})), 0.0)

    def test_scrolls_do_nothing(self):
        fire = threat_projection.ATTACK_SCROLLS[48]
        policy = mock.Mock(_monrace_knowledge={1: mock.Mock(flags=frozenset({"RES_ALL"}))})
        self.assertEqual(threat_projection.scroll_damage_on(
            policy, fire, mock.Mock(race_id=1, distance=0)), 0)
        policy._monrace_knowledge[1].flags = frozenset()
        self.assertEqual(threat_projection.scroll_damage_on(
            policy, fire, mock.Mock(race_id=1, distance=0)), 666)


class MetalIsT1Test(Replay, unittest.TestCase):

    def metal(self, monrace=None):
        monrace = monrace or self.monrace
        policy = HengbotPolicy(monrace_knowledge=monrace, baseitem_costs=self.costs)
        snapshot = parse_snapshot(copy.deepcopy(self.board(SEEN)), monrace)
        metal = next(monster for monster in snapshot.visible_monsters if monster.race_id == METAL)
        return policy, snapshot, metal

    def without_res_all(self):
        """CONSTRUCTED: the metal's race without RES_ALL."""
        monrace = dict(self.monrace)
        monrace[METAL] = dataclasses.replace(
            monrace[METAL], flags=monrace[METAL].flags - {"RES_ALL"})
        return monrace

    def test_the_metal_reads_t1(self):
        policy, snapshot, metal = self.metal()
        self.assertIn("RES_ALL", self.monrace[METAL].flags)
        # Five blows at 5%: a quarter landing an action, each 1/3 (the blow far below 100).
        self.assertAlmostEqual(attack_expectation.melee(policy, snapshot, metal), 0.25 / 3)
        free, _cost = threat_projection.free_attack(policy, snapshot, metal)
        self.assertAlmostEqual(free, 0.25 / 3)
        result = threat_tiers.assess(policy, snapshot, [metal])
        self.assertEqual(result.free_turns, 72)
        self.assertEqual(result.tier, threat_tiers.T1)

    def test_without_res_all_the_metal_is_t3(self):
        # CONSTRUCTED control: the same board without the flag: the absorbed attack powers reach it
        # again (one action) and the engagement is T3.
        policy, snapshot, metal = self.metal(self.without_res_all())
        result = threat_tiers.assess(policy, snapshot, [metal])
        self.assertEqual((result.free_turns, result.tier), (1, threat_tiers.T3))

    def decide_seen(self, monrace=None):
        monrace = monrace or self.monrace
        policy = HengbotPolicy(monrace_knowledge=monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        policy._me_device_lists = destruction_row(self.boards[0]["turn"])
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            for raw in self.boards:
                snapshot = parse_snapshot(copy.deepcopy(raw), monrace)
                key = policy.choose_key(snapshot)
                if raw["turn"] == SEEN:
                    return policy, snapshot, key
                if key:
                    policy.confirm_key_posted(key)
        raise AssertionError(SEEN)

    def test_the_t1_answer_is_destruction(self):
        policy, snapshot, key = self.decide_seen()
        metal = next(monster for monster in snapshot.visible_monsters if monster.race_id == METAL)
        self.assertEqual(metal.distance, 3)
        self.assertTrue(destruction_use.in_sure_radius(snapshot, metal))
        # Before: T3, the bow fired at it ('fi8' ranged:fire).
        self.assertTrue(policy.last_reason.startswith(destruction_use.REASON), policy.last_reason)
        self.assertEqual(key, "mA3")

    def test_without_res_all_no_destruction(self):
        # CONSTRUCTED control: without the flag the metal is fought as before.
        policy, _snapshot, _key = self.decide_seen(self.without_res_all())
        self.assertFalse(policy.last_reason.startswith(destruction_use.REASON), policy.last_reason)


class OlderWinnabilityTest(MetalIsT1Test):
    """The older winnability readers (policy_combat): the metal is not winnable; without RES_ALL
    their reading is the one they had (melee at the reference armour, AC_REFERENCE)."""

    def beside(self, monrace=None):
        """CONSTRUCTED: the metal moved beside the player (``_fruitless_fight_is_winnable`` weighs
        melee only for an adjacent target)."""
        policy, snapshot, metal = self.metal(monrace)
        return policy, snapshot, dataclasses.replace(metal, distance=1)

    def test_engagement_is_not_winnable(self):
        policy, snapshot, metal = self.metal()
        self.assertFalse(policy._engagement_is_winnable(snapshot, [metal]))

    def test_engagement_without_res_all_is_winnable(self):
        policy, snapshot, metal = self.metal(self.without_res_all())
        self.assertTrue(policy._engagement_is_winnable(snapshot, [metal]))

    def test_fruitless_fight_is_not_winnable(self):
        policy, snapshot, metal = self.beside()
        self.assertFalse(policy._fruitless_fight_is_winnable(snapshot, [metal]))

    def test_fruitless_fight_without_res_all_is_winnable(self):
        policy, snapshot, metal = self.beside(self.without_res_all())
        self.assertTrue(policy._fruitless_fight_is_winnable(snapshot, [metal]))

    def test_esp_feasibility(self):
        policy, snapshot, metal = self.metal()
        result = policy._esp_threat_kill_feasibility(snapshot, [metal])
        self.assertEqual(result["attack_turns"], 72)
        self.assertFalse(result["feasible"])

    def test_esp_feasibility_without_res_all(self):
        policy, snapshot, metal = self.metal(self.without_res_all())
        result = policy._esp_threat_kill_feasibility(snapshot, [metal])
        self.assertEqual(result["attack_turns"], 1)   # the reference armour's one action
        self.assertTrue(result["feasible"])

    def test_other_races_keep_the_figure(self):
        policy, snapshot, metal = self.metal(self.without_res_all())
        self.assertEqual(attack_expectation.legacy_melee(policy, snapshot, metal, 123.0), 123.0)
        self.assertEqual(attack_expectation.legacy_shot(policy, snapshot, metal, 45.0), 45.0)

    # The decision tests run once, in MetalIsT1Test.
    test_the_t1_answer_is_destruction = None
    test_without_res_all_no_destruction = None
    test_the_metal_reads_t1 = None
    test_without_res_all_the_metal_is_t3 = None


if __name__ == "__main__":
    unittest.main()
