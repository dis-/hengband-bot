"""Threat tiers plan step 7 (docs/threat-tiers-design.md 3.4, 5 row 8; owner answer 4, OQ-4, D3, D4,
D7): the selected supply fight.

Owner 2026-11-07: 「選んで戦う。クエストの目標、逃げられない相手と『報酬の良い相手』を倒す。」 (answer
4); uniques alone are not chosen (OQ-4); the hunted guardian is selected (D3); the commitment keeps
today's stop conditions (blind / confused / afraid / paralysed, a breeder in view, another summoner
in view) plus the 1-turn 即死, and its adjacency requirement is dropped for ranged plans (D4);
「加速を先に。余裕は最大HPの1割と、95%被害のうち大きい方」 (D7): Speed first, then good ammo ->
wand/staff charges -> attack scrolls -> resistance -> healing, the reserve max(10% max HP,
next-action p95) (step 1's ``assess``).

Every board here is DECLARED CONSTRUCTED (test_threat_tiers' open lit room).  The recorded boards
are in test_threat_tiers_supply_fight_recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.policy import HengbotPolicy  # first: threat_tiers' modules import through it
from hengbot import hunt_target, me_device_attacks, threat_tiers
from hengbot.model import (
    SV_BOW_SHORT, SV_POTION_HEALING, SV_POTION_RESISTANCE, SV_POTION_SPEED, TVAL_BOW, TVAL_SCROLL,
    TVAL_WAND,
)
from tests import test_threat_tiers as tt
from policy_fixtures import item

GOOD, UNIQ, GUARDIAN = 40, 41, 42
RACES = {**tt.RACES,
         GOOD: replace(tt.RACES[tt.DUELIST], flags=frozenset({"DROP_GOOD"})),
         UNIQ: replace(tt.RACES[tt.DUELIST], flags=frozenset({"UNIQUE"})),
         GUARDIAN: replace(tt.RACES[tt.DUELIST], flags=frozenset({"UNIQUE"}))}
SPEED_AND_HEALING = [tt.potion("a", SV_POTION_SPEED, 3), tt.potion("b", SV_POTION_HEALING, 5)]
BOW = item("bow", TVAL_BOW, SV_BOW_SHORT, is_equipment=True)
WAND_SVAL = next(sval for (kind, sval), power in sorted(me_device_attacks.POWERS.items())
                 if kind == "wand" and not power.group_only and power.shape != "sight"
                 and me_device_attacks.expected_damage(power, 30, None) > 0)


def duel(race_id, *, monster_hp=100, at=(10, 11), **board_args):
    board_args.setdefault("hp", 340)
    board_args.setdefault("max_hp", 340)
    board_args.setdefault("device_skill", 60)
    return tt.board([tt.monster(1, race_id, *at, hp=monster_hp)], **board_args)


class Base(unittest.TestCase):
    def setUp(self):
        tt.RACES.update(RACES)
        for race in (GOOD, UNIQ, GUARDIAN):
            self.addCleanup(tt.RACES.pop, race, None)
        self.policy = HengbotPolicy(monrace_knowledge=dict(RACES))

    def decide(self, snapshot):
        return str(self.policy.choose_key(snapshot)), self.policy.last_reason


class SelectionTest(Base):
    def test_a_reward_race_gets_the_speed_dose_first(self):
        snapshot = duel(GOOD, inventory=SPEED_AND_HEALING)
        result = threat_tiers.assess(self.policy, snapshot)
        self.assertEqual((result.tier, result.selected), (threat_tiers.T2, [1]))
        self.assertEqual(result.supply_plan.speed_doses, 1)
        self.assertEqual(self.decide(snapshot), ("qa", threat_tiers.SUPPLY_SPEED_REASON))
        self.assertEqual(self.policy._unique_combat_committed_race_id, GOOD)

    def test_a_unique_alone_is_not_selected_and_is_left(self):
        snapshot = duel(UNIQ, inventory=SPEED_AND_HEALING)
        result = threat_tiers.assess(self.policy, snapshot)
        self.assertEqual((result.tier, result.selected), (threat_tiers.T2, []))
        self.assertIsNone(self.policy._unique_combat_consumable(snapshot, list(snapshot.visible_monsters)))
        key, reason = self.decide(snapshot)
        self.assertFalse(reason.startswith(("supply-fight", "unique:")), reason)

    def test_the_hunted_guardian_is_selected(self):
        snapshot = duel(GUARDIAN, inventory=SPEED_AND_HEALING)
        with patch.object(hunt_target, "target_race", return_value=GUARDIAN):
            result = threat_tiers.assess(self.policy, snapshot)
            self.assertEqual(result.per_monster[1].selected, ("hunted-guardian",))
            self.assertEqual(self.decide(snapshot), ("qa", threat_tiers.SUPPLY_SPEED_REASON))

    def test_a_plan_floor_keeps_the_unique_fight(self):
        snapshot = duel(GOOD, inventory=SPEED_AND_HEALING)
        with patch.object(threat_tiers, "supply_fight_applies", return_value=False), \
                patch.object(threat_tiers, "supply_fight_key") as new:
            self.policy._unique_combat_consumable(snapshot, list(snapshot.visible_monsters))
        new.assert_not_called()


def assessment(*, plan, p95=10, free=1.0, selected=True):
    """DECLARED CONSTRUCTED: an assessment standing in for ``assess``."""
    result = threat_tiers.Assessment(tier=threat_tiers.T2, supply_plan=plan, next_action_p95=p95,
                                     free_damage={1: free})
    result.per_monster[1] = threat_tiers.MonsterAssessment(
        index=1, race_id=GOOD, name="g", speed=110, selected=("reward",) if selected else ())
    return result


def plan(**spent):
    return threat_tiers.SupplyPlan(categories=threat_tiers.PLAN_ORDER, turns=10, incoming=1,
                                   capacity=2, reserve=spent.pop("reserve", 34), **spent)


class OrderTest(Base):
    """D7 「加速を先に」: what the fight spends first."""

    EVERYTHING = dict(speed_doses=1, good_ammo=1, charges=1, scrolls=1, resistance=1, heals=(300,))

    def key(self, snapshot, result):
        with patch.object(threat_tiers, "tiered", return_value=result):
            return threat_tiers.supply_fight_key(self.policy, snapshot, list(snapshot.visible_monsters))

    def pack(self, *, speed=True, healing=True, resistance=True, ammo=True, wand=True, scroll=True):
        inventory = []
        if speed:
            inventory.append(tt.potion("a", SV_POTION_SPEED, 1))
        if healing:
            inventory.append(tt.potion("b", SV_POTION_HEALING, 1))
        if resistance:
            inventory.append(tt.potion("c", SV_POTION_RESISTANCE, 1))
        if ammo:
            inventory.append(item("d", BOW.ammo_tval, 1, count=20, is_ego=True, known=True,
                                  damage_dice_num=9, damage_dice_sides=9, name="ego arrows"))
        if wand:
            inventory.append(item("e", TVAL_WAND, WAND_SVAL, known=True, charges=5, name="wand"))
        if scroll:
            inventory.append(item("f", TVAL_SCROLL, 48, count=1, name="Fire"))
        return inventory

    def test_speed_comes_first(self):
        snapshot = duel(GOOD, inventory=self.pack(), equipment=(tt.SWORD, BOW))
        self.assertEqual(self.key(snapshot, assessment(plan=plan(**self.EVERYTHING))), "qa")
        self.assertEqual(self.policy.last_reason, threat_tiers.SUPPLY_SPEED_REASON)

    def test_healing_when_the_dose_is_due(self):
        snapshot = duel(GOOD, hp=100, inventory=self.pack(speed=False), equipment=(tt.SWORD, BOW))
        self.assertEqual(self.key(snapshot, assessment(plan=plan(**self.EVERYTHING))), "qb")
        self.assertEqual(self.policy.last_reason, threat_tiers.SUPPLY_HEAL_REASON)

    def test_resistance_then_the_attack_supplies_in_the_owners_order(self):
        board = dict(at=(10, 13), equipment=(tt.SWORD, BOW))
        cases = (({"speed": False}, "qc", threat_tiers.SUPPLY_RESIST_REASON),
                 ({"speed": False, "resistance": False}, "fd6", threat_tiers.SUPPLY_AMMO_REASON),
                 ({"speed": False, "resistance": False, "ammo": False}, "ae6",
                  threat_tiers.SUPPLY_WAND_REASON),
                 ({"speed": False, "resistance": False, "ammo": False, "wand": False}, "rf",
                  threat_tiers.SUPPLY_SCROLL_REASON))
        for held, key, reason in cases:
            with self.subTest(reason=reason):
                snapshot = duel(GOOD, inventory=self.pack(**held), **board)
                self.assertEqual(self.key(snapshot, assessment(plan=plan(**self.EVERYTHING))), key)
                self.assertEqual(self.policy.last_reason, reason)

    def test_only_what_the_plan_spends(self):
        snapshot = duel(GOOD, inventory=self.pack(speed=False), equipment=(tt.SWORD, BOW))
        self.assertIsNone(self.key(snapshot, assessment(plan=plan(scrolls=0))))

    def test_a_melee_plan_needs_the_target_beside_the_player(self):
        snapshot = duel(GOOD, at=(10, 13), inventory=self.pack(), equipment=(tt.SWORD,))
        self.assertIsNone(self.key(snapshot, assessment(plan=plan(speed_doses=1))))
        beside = duel(GOOD, inventory=self.pack(), equipment=(tt.SWORD,))
        self.assertEqual(self.key(beside, assessment(plan=plan(speed_doses=1))), "qa")

    def test_an_unselected_t2_spends_nothing(self):
        snapshot = duel(GOOD, inventory=self.pack(), equipment=(tt.SWORD, BOW))
        self.assertIsNone(self.key(snapshot, assessment(plan=plan(**self.EVERYTHING), selected=False)))


class CommitmentTest(Base):
    """D4 and OQ-2: the committed fight is not fled while the projection wins."""

    def viable(self, snapshot, result, *, monsters=None):
        hostiles = list(monsters or snapshot.visible_monsters)
        with patch.object(threat_tiers, "tiered", return_value=result):
            return self.policy._committed_unique_fight_viable(snapshot, hostiles)

    def setUp(self):
        super().setUp()
        self.policy._unique_combat_committed_race_id = GOOD

    def test_committed_and_winning(self):
        self.assertTrue(self.viable(duel(GOOD), assessment(plan=plan(speed_doses=1))))

    def test_not_while_the_projection_fails(self):
        result = assessment(plan=None)
        result.tier = threat_tiers.T1
        self.assertFalse(self.viable(duel(GOOD), result))

    def test_the_stop_conditions(self):
        for status in ("blind", "confused", "afraid", "paralyzed"):
            with self.subTest(status=status):
                self.assertFalse(self.viable(duel(GOOD, **{status: True}),
                                             assessment(plan=plan(speed_doses=1))))
        breeder = tt.monster(2, tt.BREEDER, 10, 14)
        summoner = tt.monster(3, tt.SUMMONER, 10, 15)
        for other in (breeder, summoner):
            with self.subTest(other=other.race_id):
                snapshot = tt.board([tt.monster(1, GOOD, 10, 11, hp=100), other], hp=340, max_hp=340)
                self.assertFalse(self.viable(snapshot, assessment(plan=plan(speed_doses=1))))

    def test_adjacency_is_dropped_for_a_ranged_plan(self):
        far = duel(GOOD, at=(10, 13))
        self.assertFalse(self.viable(far, assessment(plan=plan(speed_doses=1))))
        self.assertTrue(self.viable(far, assessment(plan=plan(charges=2))))

    def test_the_committed_fight_is_not_fled(self):
        snapshot = duel(GOOD)
        hostiles = list(snapshot.visible_monsters)
        with patch.object(threat_tiers, "committed_supply_fight_viable", return_value=True), \
                patch.object(threat_tiers, "leave_due", return_value=True):
            self.assertFalse(self.policy._should_flee(snapshot, hostiles, hostiles))


if __name__ == "__main__":
    unittest.main()
