"""Threat tiers plan step 6 (docs/threat-tiers-design.md 3.2, 3.4, 5 row 5): leave at T1 and at an
unselected T2.

Owner 2026-11-07, answer 6: 「勝てる(物資なし) -> fight; 倒しきれない -> don't fight, leave」; answer 4:
「選んで戦う。クエストの目標、逃げられない相手と『報酬の良い相手』を倒す。」 others: avoid / leave.
``_should_flee``'s core is the tiers on the shared ladder's dungeon floors (``threat_tiers.leave_due``,
reading step 1's selection, so a selected T2 is not left); T3 and a tier past the cost cap keep
today's HP-below-40% winnability, quest plan floors keep today's meaning (answer 11; Q2's
``_q2_encounter_key``).  me_powers' Teleport Away trigger reads the same answer on the one monster.
OQ-9 (C-1): outside the plans the Resistance potion is drunk only in a selected supply fight.

Every board here is DECLARED CONSTRUCTED (test_threat_tiers' open lit room); the recorded boards are
in test_threat_tiers_leave_recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.policy import HengbotPolicy  # first: threat_tiers' modules import through it
from hengbot import me_powers, resist_potion, threat_tiers
from hengbot.model import SV_POTION_HEALING, SV_POTION_RESISTANCE
from tests import test_threat_tiers as tt

GOOD_DUELIST = 40
RACES = {**tt.RACES, GOOD_DUELIST: replace(tt.RACES[tt.DUELIST], flags=frozenset({"DROP_GOOD"}))}


def duel(race_id=tt.DUELIST, hp=150, **board_args):
    return tt.board([tt.monster(1, race_id, 10, 11, hp=hp)], **board_args)


def assessment(tier, *, selected=False, plan=None):
    """DECLARED CONSTRUCTED: an assessment the test stands in for ``assess``."""
    result = threat_tiers.Assessment(tier=tier, supply_plan=plan)
    result.per_monster[1] = threat_tiers.MonsterAssessment(
        index=1, race_id=tt.DUELIST, name="d", speed=110,
        selected=("reward",) if selected else ())
    return result


class LeaveDueTest(unittest.TestCase):
    def setUp(self):
        tt.RACES.update(RACES)
        self.addCleanup(tt.RACES.pop, GOOD_DUELIST)
        self.policy = HengbotPolicy(monrace_knowledge=dict(RACES))

    def flee(self, snapshot):
        hostiles = list(snapshot.visible_monsters)
        return self.policy._should_flee(snapshot, hostiles, [m for m in hostiles if m.distance <= 1])

    def test_t1_is_left_at_full_hp(self):
        snapshot = duel()
        self.assertEqual(threat_tiers.assess(self.policy, snapshot).tier, threat_tiers.T1)
        self.assertTrue(self.flee(snapshot))
        # Today's core asked winnability only below 40% HP.
        with patch.object(threat_tiers, "leave_due", return_value=None):
            self.assertFalse(self.flee(snapshot))

    def test_an_unselected_t2_is_left(self):
        snapshot = duel(inventory=[tt.potion("a", SV_POTION_HEALING, 5)])
        result = threat_tiers.assess(self.policy, snapshot)
        self.assertEqual((result.tier, result.selected), (threat_tiers.T2, []))
        self.assertTrue(self.flee(snapshot))

    def test_a_selected_t2_is_not_left_even_below_the_flee_ratio(self):
        snapshot = duel(GOOD_DUELIST, hp=150, inventory=[tt.potion("a", SV_POTION_HEALING, 5)])
        result = threat_tiers.assess(self.policy, snapshot)
        self.assertEqual((result.tier, result.selected), (threat_tiers.T2, [1]))
        self.assertFalse(self.flee(snapshot))
        low = replace(snapshot, player=replace(snapshot.player, hp=100))
        with patch.object(threat_tiers, "tiered", return_value=assessment(threat_tiers.T2, selected=True)):
            self.assertFalse(self.flee(low))
        with patch.object(threat_tiers, "leave_due", return_value=None):
            self.assertTrue(self.flee(low))  # today's core fled it

    def test_t3_keeps_todays_core(self):
        snapshot = tt.board([tt.monster(1, tt.WEAK, 10, 11)], hp=100)
        self.assertEqual(threat_tiers.assess(self.policy, snapshot).tier, threat_tiers.T3)
        self.assertIsNone(threat_tiers.leave_due(self.policy, snapshot, list(snapshot.visible_monsters)))
        self.assertFalse(self.flee(snapshot))
        with patch.object(HengbotPolicy, "_engagement_is_winnable", return_value=False):
            self.assertTrue(self.flee(snapshot))  # below 40%: today's winnability still leaves

    def test_a_quest_plan_floor_keeps_todays_meaning(self):
        snapshot = duel()
        with patch.object(HengbotPolicy, "approved_quest_strategy", return_value=object()):
            self.assertIsNone(threat_tiers.leave_due(self.policy, snapshot, list(snapshot.visible_monsters)))
            self.assertFalse(self.flee(snapshot))

    def test_a_floor_leaving_fails_the_quest_keeps_todays_meaning(self):
        # Design 3.2: where leaving fails the quest, the quest's own rules decide.
        snapshot = duel()
        with patch.object(HengbotPolicy, "_floor_navigation_exit_locked", return_value=True):
            self.assertIsNone(threat_tiers.leave_due(self.policy, snapshot, list(snapshot.visible_monsters)))
            self.assertFalse(self.flee(snapshot))

    def test_an_unresisted_disenchanter_is_the_11_05_rules(self):
        # OQ-3 「全部 11-05 のとおり」: disenchant_avoid decides an engagement with one.
        snapshot = tt.board([tt.monster(1, tt.DISENCHANTER, 10, 11, hp=3000)])
        hostiles = list(snapshot.visible_monsters)
        self.assertEqual(threat_tiers.assess(self.policy, snapshot).tier, threat_tiers.T1)
        self.assertIsNone(threat_tiers.leave_due(self.policy, snapshot, hostiles))
        resisted = tt.board([tt.monster(1, tt.DISENCHANTER, 10, 11, hp=3000)],
                            abilities=("resist_disen",),
                            sources={"resist_disen": frozenset({"equipment"})})
        self.assertTrue(threat_tiers.leave_due(self.policy, resisted, list(resisted.visible_monsters)))

    def test_the_surface_keeps_todays_meaning(self):
        snapshot = replace(duel(), floor_key=(0, 0, 0))
        self.assertEqual(snapshot.dungeon_level, 0)
        self.assertIsNone(threat_tiers.leave_due(self.policy, snapshot, list(snapshot.visible_monsters)))

    def test_the_choke_judges_the_tiers_at_its_origin(self):
        snapshot = duel()
        seen = []

        def spy(policy, board, hostiles, melee_slots=None):
            seen.append(melee_slots)
            return None
        with patch.object(threat_tiers, "leave_due", spy):
            self.policy._should_flee(snapshot, list(snapshot.visible_monsters), [],
                                     melee_slots=(8, 0))
        self.assertEqual(seen, [(8, 0)])

    def test_the_choke_engagement_asks_at_its_origin(self):
        # Inventory 2.7: _choke_engagement_key's flee test is judged at the choke's origin.
        from hengbot.model import Position
        from hengbot.policy_types import ChokeEngagementPlan
        snapshot = duel()
        hostiles = list(snapshot.visible_monsters)
        self.policy._choke_engagement_plan = ChokeEngagementPlan(
            floor=snapshot.floor_key, phase="hold", destination=Position(10, 10),
            covered_retreat_direction=(0, 1), trigger_last_seen={1: hostiles[0].position},
            start_exp=0, start_gold=0, start_breeder_count=0, last_player_hp=300,
            origin=Position(12, 12))
        seen = []

        def spy(policy, board, hostiles, melee_slots=None):
            seen.append(melee_slots)
            return None
        with patch.object(HengbotPolicy, "_choke_plan_active", return_value=True), \
                patch.object(HengbotPolicy, "_choke_melee_slots", return_value=(5, 3)), \
                patch.object(HengbotPolicy, "_choke_predicted_damage", return_value=1), \
                patch.object(threat_tiers, "leave_due", spy):
            self.policy._choke_engagement_key(snapshot, hostiles, hostiles)
        self.assertIn((5, 3), seen)

    def test_assess_counts_the_given_melee_slots(self):
        snapshot = duel()
        seen = set()
        real = HengbotPolicy.threat_prediction

        def spy(policy, *args, **kwargs):
            seen.add(kwargs.get("melee_slots"))
            return real(policy, *args, **kwargs)
        with patch.object(HengbotPolicy, "threat_prediction", spy):
            threat_tiers.assess(self.policy, snapshot, melee_slots=(1, 0))
        self.assertEqual(seen, {(1, 0)})

    def test_the_assessment_is_memoised_for_the_decision(self):
        snapshot = duel()
        calls = []
        real = threat_tiers.assess

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)
        with patch.object(threat_tiers, "assess", counting):
            self.policy.choose_key(snapshot)
        self.assertLessEqual(len(calls), 3)  # one per hostile set the decision asks about


class LeaveWalkTest(unittest.TestCase):
    """Design 3.2: a leave the tiers decide walks only while no awake hostile is faster and none
    reaches at range; else the flee rung's relocation (n1-c life-168's Judge Death)."""

    def setUp(self):
        self.policy = HengbotPolicy(monrace_knowledge=dict(RACES))

    def test_walk_leaves(self):
        slow = duel()
        self.assertTrue(threat_tiers.walk_leaves(self.policy, slow, list(slow.visible_monsters)))
        fast = tt.board([tt.monster(1, tt.DUELIST, 10, 13, hp=150, speed=120)])
        self.assertFalse(threat_tiers.walk_leaves(self.policy, fast, list(fast.visible_monsters)))
        hasted = tt.board([tt.monster(1, tt.DUELIST, 10, 13, hp=150, fast=True)])
        self.assertFalse(threat_tiers.walk_leaves(self.policy, hasted, list(hasted.visible_monsters)))
        asleep = tt.board([tt.monster(1, tt.DUELIST, 10, 13, hp=150, speed=120, asleep=True)])
        self.assertTrue(threat_tiers.walk_leaves(self.policy, asleep, list(asleep.visible_monsters)))

    def test_a_faster_t1_engagement_is_left_by_the_scroll(self):
        from policy_fixtures import item
        from hengbot.model import TVAL_SCROLL
        scroll = item("a", TVAL_SCROLL, 9, count=3, name="Teleportation")
        fast = tt.board([tt.monster(1, tt.DUELIST, 10, 13, hp=150, speed=120)], inventory=[scroll])
        self.assertEqual(threat_tiers.assess(self.policy, fast).tier, threat_tiers.T1)
        self.assertEqual((self.policy.choose_key(fast), self.policy.last_reason), ("ra", "flee:scroll"))


class TeleportAwayTriggerTest(unittest.TestCase):
    def setUp(self):
        self.policy = HengbotPolicy(monrace_knowledge=dict(RACES))

    def due(self, snapshot):
        class Ctx:
            pass
        ctx = Ctx()
        ctx.policy, ctx.snapshot = self.policy, snapshot
        ctx.target_hostile, ctx.aim = snapshot.visible_monsters[0], "6"
        return me_powers._unbeatable_in_range(ctx, None)

    def test_the_trigger_reads_the_tiers(self):
        snapshot = duel()
        for result, expected in ((assessment(threat_tiers.T1), True),
                                 (assessment(threat_tiers.T2), True),
                                 (assessment(threat_tiers.T2, selected=True), False)):
            with self.subTest(tier=result.tier, selected=result.selected), \
                    patch.object(threat_tiers, "tiered", return_value=result):
                self.assertEqual(self.due(snapshot), expected)

    def test_t3_keeps_todays_winnability(self):
        snapshot = duel()
        with patch.object(threat_tiers, "tiered", return_value=assessment(threat_tiers.T3)), \
                patch.object(HengbotPolicy, "_engagement_is_winnable", return_value=False):
            self.assertTrue(self.due(snapshot))
        with patch.object(threat_tiers, "tiered", return_value=assessment(threat_tiers.T3)), \
                patch.object(HengbotPolicy, "_engagement_is_winnable", return_value=True):
            self.assertFalse(self.due(snapshot))


class ResistancePotionLadderTest(unittest.TestCase):
    """OQ-9 (C-1): on the shared ladder the drink is part of a selected supply fight only."""

    def setUp(self):
        self.policy = HengbotPolicy(monrace_knowledge=dict(RACES))
        self.snapshot = duel(inventory=[tt.potion("a", SV_POTION_RESISTANCE, 2)])

    def ladder(self, result):
        verdict = (self.snapshot.inventory[0], True)
        with patch.object(resist_potion, "_verdict", return_value=verdict), \
                patch.object(resist_potion, "_leave_key", return_value="LEAVE"), \
                patch.object(HengbotPolicy, "_should_flee", return_value=False), \
                patch.object(threat_tiers, "tiered", return_value=result):
            return resist_potion.ladder_key(self.policy, self.snapshot, [], [], [])

    def plan(self, resistance):
        return threat_tiers.SupplyPlan(categories=("resistance",), turns=5, incoming=1, capacity=2,
                                       reserve=1, resistance=resistance)

    def test_a_selected_supply_fight_that_spends_it_drinks(self):
        key = self.ladder(assessment(threat_tiers.T2, selected=True, plan=self.plan(1)))
        self.assertEqual((key, self.policy.last_reason), ("qa", resist_potion.QUAFF_REASON))

    def test_a_selected_fight_whose_plan_does_not_spend_it_does_not_drink(self):
        self.assertIsNone(self.ladder(assessment(threat_tiers.T2, selected=True, plan=self.plan(0))))

    def test_an_unselected_t2_and_t1_are_left(self):
        self.assertEqual(self.ladder(assessment(threat_tiers.T2, plan=self.plan(1))), "LEAVE")
        self.assertEqual(self.ladder(assessment(threat_tiers.T1)), "LEAVE")

    def test_a_t3_fight_is_fought_without_it(self):
        self.assertIsNone(self.ladder(assessment(threat_tiers.T3)))

    def test_a_plan_floor_keeps_the_11_05_drink(self):
        with patch.object(threat_tiers, "acts_here", return_value=False), \
                patch.object(resist_potion, "key", return_value="KEY"), \
                patch.object(resist_potion, "_verdict", return_value=(self.snapshot.inventory[0], True)), \
                patch.object(HengbotPolicy, "_should_flee", return_value=False):
            self.assertEqual(resist_potion.ladder_key(self.policy, self.snapshot, [], [], []), "KEY")


if __name__ == "__main__":
    unittest.main()
