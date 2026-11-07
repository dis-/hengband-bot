"""Threat tiers, plan step 1 (docs/threat-tiers-design.md): ``threat_tiers.assess`` on constructed boards.

Owner 2026-11-07 「『即死の危険がある』『物資を全て使っても倒しきれない』『物資を使えば勝てる』
『物資を使わなくても勝てる』この段階に分ける」, with the answers of design sections 0, 7 and 7.1.
Every board here is DECLARED CONSTRUCTED: an open lit room, the player at (10, 10), races built in
the test.  The recorded boards are in test_threat_tiers_recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.policy import HengbotPolicy  # first: threat_tiers' modules import through it
from hengbot import threat_tiers
from hengbot.model import (
    AbilitySources, MonsterState, Position, Snapshot, SV_POTION_HEALING, SV_POTION_SPEED,
    TVAL_POTION, TVAL_SCROLL, TVAL_SWORD,
)
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow

from policy_fixtures import grid, item, player

ORIGIN = Position(10, 10)
WEAK, BRUTE, DUELIST, PARALYZER, DRAINER, BREATHER, DISENCHANTER, TOUCHER = range(1, 9)
SUMMONER, BREEDER, SHRIEKER, ANCHORED, GOODIE, HOARDER, FEW_DROPS, SAGE = range(9, 17)


def race(*, hp=10, speed=110, level=5, exp=1, blows=(), flags=(), abilities=(),
         can_summon=False, can_multiply=False, frequency=0):
    return MonraceKnowledge(
        max_hp=hp, average_hp=hp, speed=speed, can_summon=can_summon, friendly=False,
        level=level, max_melee_damage=sum(b.dice_num * b.dice_sides for b in blows),
        can_multiply=can_multiply, flags=frozenset(flags), abilities=frozenset(abilities),
        blows=tuple(blows), spell_frequency=frequency, experience=exp)


RACES = {
    WEAK: race(hp=5, blows=(MonsterBlow("HIT", "HURT", 1, 2),)),
    BRUTE: race(hp=3000, level=40, blows=(MonsterBlow("HIT", "HURT", 10, 10),) * 4),
    DUELIST: race(hp=400, level=20, blows=(MonsterBlow("HIT", "HURT", 3, 10),) * 2),
    PARALYZER: race(hp=20, blows=(MonsterBlow("TOUCH", "PARALYZE", 1, 2),)),
    DRAINER: race(hp=20, blows=(MonsterBlow("TOUCH", "LOSE_STR", 1, 2),
                                MonsterBlow("TOUCH", "EXP_80", 1, 2))),
    BREATHER: race(hp=20, abilities=("BR_FIRE",)),
    DISENCHANTER: race(hp=20, blows=(MonsterBlow("TOUCH", "UN_BONUS", 1, 2),)),
    TOUCHER: race(hp=20, blows=(MonsterBlow("TOUCH", "EXP_80", 1, 2),
                                MonsterBlow("BITE", "HURT", 1, 2))),
    SUMMONER: race(hp=20, can_summon=True, abilities=("S_MONSTER",)),
    BREEDER: race(hp=5, flags=("MULTIPLY", "DROP_GOOD"), can_multiply=True,
                  blows=(MonsterBlow("BITE", "HURT", 1, 2),)),
    SHRIEKER: race(hp=5, flags=("NEVER_MOVE",), abilities=("SHRIEK",), frequency=25),
    ANCHORED: race(hp=20, flags=("NEVER_MOVE",), blows=(MonsterBlow("HIT", "HURT", 1, 8),)),
    GOODIE: race(hp=20, flags=("DROP_GOOD",), blows=(MonsterBlow("HIT", "HURT", 1, 2),)),
    HOARDER: race(hp=20, flags=("DROP_2D2",), blows=(MonsterBlow("HIT", "HURT", 1, 2),)),
    FEW_DROPS: race(hp=20, flags=("DROP_1D2", "DROP_90"), blows=(MonsterBlow("HIT", "HURT", 1, 2),)),
    SAGE: race(hp=20, level=10, exp=100, blows=(MonsterBlow("HIT", "HURT", 1, 2),)),
}
SWORD = item("main_hand", TVAL_SWORD, 1, count=1, is_equipment=True, damage_dice_num=2,
             damage_dice_sides=5)


def monster(index, race_id, y, x, *, hp=None, speed=None, fast=None, asleep=False,
            fearful=False):
    knowledge = RACES[race_id]
    hp = knowledge.max_hp if hp is None else hp
    return MonsterState(
        index=index, position=Position(y, x), hp=hp, max_hp=hp,
        distance=ORIGIN.distance_to(Position(y, x)), friendly=False, pet=False,
        speed=knowledge.speed if speed is None else speed, asleep=asleep, fearful=fearful,
        race_id=race_id, can_summon=knowledge.can_summon, can_multiply=knowledge.can_multiply,
        max_melee_damage=knowledge.max_melee_damage, level=knowledge.level, fast=fast)


def board(monsters, *, hp=300, max_hp=300, inventory=(), equipment=(SWORD,), abilities=(),
          sources=None, **status):
    grids = {Position(y, x): grid(y, x, lit=True, in_view=True)
             for y in range(2, 19) for x in range(2, 19)}
    for each in monsters:
        grids[each.position] = replace(grids[each.position], has_monster=True)
    hero = replace(player(10, 10, hp=hp, max_hp=max_hp, main_hand_blows=2,
                          abilities=frozenset(abilities)),
                   melee_skill=120, **status)
    if sources is not None:
        hero = replace(hero, ability_sources=AbilitySources(sources))
    return Snapshot(hero, grids, list(monsters), floor_key=(1, 10, 0), turn=1000,
                    inventory=list(inventory), equipment=list(equipment), width=40, height=30)


def potion(slot, sval, count):
    return item(slot, TVAL_POTION, sval, count=count, name=f"potion {sval}")


class ThreatTiersTest(unittest.TestCase):
    def setUp(self):
        self.policy = HengbotPolicy(monrace_knowledge=dict(RACES))

    def assess(self, snapshot):
        return threat_tiers.assess(self.policy, snapshot)

    # -- 3.3 / 3.4 / 3.2 tiers --------------------------------------------------

    def test_t3_a_weak_monster_falls_to_the_free_attacks(self):
        result = self.assess(board([monster(1, WEAK, 10, 11)]))
        self.assertEqual(result.tier, threat_tiers.T3)
        self.assertIsNone(result.supply_plan)
        self.assertFalse(result.instant_death)

    def test_t1_not_even_every_supply_wins(self):
        result = self.assess(board([monster(1, BRUTE, 10, 11)],
                                   inventory=[potion("a", SV_POTION_HEALING, 2)]))
        self.assertEqual(result.tier, threat_tiers.T1)
        self.assertIsNone(result.supply_plan)

    def test_t2_healing_wins_where_the_free_attacks_do_not(self):
        duel = [monster(1, DUELIST, 10, 11, hp=150)]
        without = self.assess(board(duel))
        self.assertEqual(without.tier, threat_tiers.T1)
        result = self.assess(board(duel, inventory=[potion("a", SV_POTION_HEALING, 5)]))
        self.assertEqual(result.tier, threat_tiers.T2)
        plan = result.supply_plan
        self.assertEqual(plan.categories, threat_tiers.PLAN_ORDER)  # healing is the last category
        self.assertTrue(plan.heals)
        # D7: the reserve is max(10% of max HP, the next-action p95).
        self.assertEqual(plan.reserve, max(30, result.next_action_p95))
        self.assertLessEqual(plan.incoming, plan.capacity - plan.reserve)

    def test_t2_speed_comes_first(self):
        # D7 「加速を先に」: with Speed and Healing both carried, the shortest winning prefix is
        # tried from the Speed dose on; a fight Speed alone wins never reaches the potions.
        duel = [monster(1, DUELIST, 10, 11, hp=100)]
        self.assertEqual(self.assess(board(duel, hp=340, max_hp=340)).tier, threat_tiers.T1)
        result = self.assess(board(duel, hp=340, max_hp=340,
                                   inventory=[potion("a", SV_POTION_SPEED, 3),
                                              potion("b", SV_POTION_HEALING, 5)]))
        self.assertEqual(result.tier, threat_tiers.T2)
        self.assertEqual(result.supply_plan.categories, ("speed",))
        self.assertEqual(result.supply_plan.speed_doses, 1)
        self.assertEqual(result.supply_plan.heals, ())

    def test_t3_keeps_todays_bound_without_a_reserve(self):
        # 3.3: incoming < hp, no reserve (deliberately looser than T2's).
        duel = [monster(1, DUELIST, 10, 11, hp=100)]
        incoming = self.assess(board(duel, hp=300, max_hp=1000)).free_incoming
        result = self.assess(board(duel, hp=incoming + 1, max_hp=1000))
        self.assertEqual(result.free_incoming, incoming)
        self.assertEqual(result.tier, threat_tiers.T3)

    def test_cure_critical_wounds_is_no_hp_recovery(self):
        self.assertEqual(set(threat_tiers.HEAL_AMOUNTS), {SV_POTION_HEALING, 38, 39})
        # Owner 11-03 / OQ-7: only Healing, *Healing* and Life count.
        duel = [monster(1, DUELIST, 10, 11)]
        result = self.assess(board(duel, inventory=[potion("a", 36, 20)]))
        self.assertEqual(result.tier, threat_tiers.T1)

    def test_attack_scroll_damage_falls_with_the_distance(self):
        fire = threat_tiers.ATTACK_SCROLLS[48]
        # effect-monster.cpp:108, integer (dam + r) / (r + 1); nothing beyond radius 4.
        self.assertEqual([threat_tiers.scroll_damage_at(fire, r) for r in range(6)],
                         [666, 333, 222, 167, 134, 0])

    def test_t2_attack_scrolls_credit_every_target_in_the_radius(self):
        duel = [monster(1, DUELIST, 10, 12, hp=600), monster(2, DUELIST, 10, 8, hp=600)]
        scrolls = [item("a", TVAL_SCROLL, 48, count=3, name="Fire")]
        result = self.assess(board(duel, hp=900, max_hp=900, inventory=scrolls,
                                   abilities=("resist_fire",)))
        self.assertEqual(result.tier, threat_tiers.T2)
        self.assertEqual(result.supply_plan.categories,
                         ("speed", "good_ammo", "charges", "scrolls"))
        # Each read is (666 + 2) // 3 = 222 to BOTH targets two cells away: 3 reads clear 600 each.
        self.assertEqual(result.supply_plan.scrolls, 3)
        blind = self.assess(board(duel, hp=900, max_hp=900, inventory=scrolls,
                                  abilities=("resist_fire",), blind=True))
        self.assertNotEqual(blind.tier, threat_tiers.T2)  # unreadable blind (cmd-read.cpp:37)

    # -- 3.1 即死 ----------------------------------------------------------------

    def test_a_hasted_monster_takes_its_extra_action_into_the_next_action_p95(self):
        duel = monster(1, DUELIST, 10, 11)
        calm = self.assess(board([duel], hp=60, max_hp=300))
        hasted = self.assess(board([replace(duel, fast=True)], hp=60, max_hp=300))
        self.assertGreater(hasted.next_action_p95, calm.next_action_p95)
        self.assertEqual(hasted.per_monster[1].speed, 120)
        hp = calm.next_action_p95 + 1  # survives the calm monster, not the hasted one
        self.assertFalse(self.assess(board([duel], hp=hp, max_hp=300)).instant_death)
        result = self.assess(board([replace(duel, fast=True)], hp=hp, max_hp=300))
        self.assertTrue(result.instant_death)
        self.assertEqual(result.instant_death_reasons, ("next-action-p95",))

    def test_a_slowed_monster_loses_ten_speed(self):
        duel = replace(monster(1, DUELIST, 10, 11), slow=True)
        self.assertEqual(self.assess(board([duel])).per_monster[1].speed, 100)

    def test_the_observed_loss_counts_once(self):
        duel = monster(1, DUELIST, 10, 11)
        snapshot = board([duel], hp=200, max_hp=300)
        p95 = self.assess(snapshot).next_action_p95
        self.policy._took_damage = True
        self.policy._last_damage_amount = 200 - p95
        # A loss with no unseen attacker evidenced is the visible duelist's, in the p95 already.
        self.policy._unseen_attack_evidence = None
        result = self.assess(snapshot)
        self.assertEqual(result.unseen_correction, 0)
        self.assertFalse(result.instant_death)
        self.policy._unseen_attack_evidence = "何かに攻撃された。"
        result = self.assess(snapshot)
        self.assertEqual(result.unseen_correction, 200 - p95)
        self.assertTrue(result.instant_death)

    def test_an_unresisted_paralyser_in_contact_is_instant_death(self):
        result = self.assess(board([monster(1, PARALYZER, 10, 11)]))
        self.assertEqual(result.instant_death_reasons, ("paralyzer-contact",))
        free = self.assess(board([monster(1, PARALYZER, 10, 11)],
                                 sources={"free_action": frozenset({"equipment"})}))
        self.assertFalse(free.instant_death)
        asleep = self.assess(board([monster(1, PARALYZER, 10, 11, asleep=True)]))
        self.assertFalse(asleep.instant_death)

    def test_hallucinated_below_the_low_hp_line_is_instant_death(self):
        weak = [monster(1, WEAK, 10, 12)]
        self.assertFalse(self.assess(board(weak, hp=290, hallucinated=True)).instant_death)
        result = self.assess(board(weak, hp=100, hallucinated=True))
        self.assertEqual(result.instant_death_reasons, ("hallucination",))

    # -- 4.1 irreversible --------------------------------------------------------

    def kinds(self, race_id, **board_args):
        return self.assess(board([monster(1, race_id, 10, 13)], **board_args)).per_monster[1].irreversible

    def test_stat_drain_counts_until_sustained_and_exp_drain_never(self):
        self.assertEqual(self.kinds(DRAINER), ("stat-drain",))
        self.assertEqual(self.kinds(DRAINER, abilities=("sustain_str",)), ())
        self.assertEqual(self.kinds(TOUCHER), ())  # EXP_80 alone (D5)

    def test_an_unresisted_fire_breather_drains_and_burns(self):
        self.assertEqual(self.kinds(BREATHER), ("stat-drain", "item-destruction"))
        lasting = {"resist_fire": frozenset({"equipment"})}
        self.assertEqual(self.kinds(BREATHER, abilities=("resist_fire",), sources=lasting),
                         ("item-destruction",))
        both = {"resist_fire": frozenset({"equipment", "temporary"})}
        self.assertEqual(self.kinds(BREATHER, abilities=("resist_fire",), sources=both), ())

    def test_disenchant_is_listed_until_resisted(self):
        self.assertEqual(self.kinds(DISENCHANTER), ("disenchant",))
        self.assertEqual(self.kinds(DISENCHANTER, abilities=("resist_disen",)), ())

    # -- 4.4 worsens with time ---------------------------------------------------

    def test_summoners_breeders_and_shriekers_worsen_with_time(self):
        result = self.assess(board([monster(1, SUMMONER, 10, 14), monster(2, BREEDER, 10, 6),
                                    monster(3, SHRIEKER, 6, 10)]))
        self.assertEqual(result.per_monster[1].worsens_with_time, ("summon",))
        self.assertEqual(result.per_monster[2].worsens_with_time, ("multiply",))
        self.assertEqual(result.per_monster[3].worsens_with_time, ("shriek",))
        self.assertEqual(result.flags()["worsens_with_time"],
                         {1: ["summon"], 2: ["multiply"], 3: ["shriek"]})

    # -- 4.3 need not fight ------------------------------------------------------

    def test_fearful_and_unreachable_monsters_need_not_be_fought(self):
        result = self.assess(board([monster(1, WEAK, 10, 14, fearful=True),
                                    monster(2, ANCHORED, 10, 5), monster(3, ANCHORED, 10, 11),
                                    monster(4, WEAK, 10, 6)]))
        self.assertEqual(result.per_monster[1].need_not_fight, "fearful")
        self.assertEqual(result.per_monster[2].need_not_fight, "cannot-reach")
        self.assertIsNone(result.per_monster[3].need_not_fight)  # adjacent: it reaches
        self.assertIsNone(result.per_monster[4].need_not_fight)

    def test_a_quest_target_is_never_left_alone(self):
        with patch.object(threat_tiers, "_quest_races", return_value={WEAK}):  # DECLARED CONSTRUCTED
            result = self.assess(board([monster(1, WEAK, 10, 14, fearful=True)]))
        self.assertIsNone(result.per_monster[1].need_not_fight)
        self.assertEqual(result.per_monster[1].selected, ("quest-target",))

    # -- 4.2 cannot escape -------------------------------------------------------

    def test_blind_with_a_faster_chaser_cannot_escape(self):
        chaser = [monster(1, DUELIST, 10, 12, speed=120)]
        scroll = [item("a", TVAL_SCROLL, 9, count=5, name="Teleportation")]
        sighted = self.assess(board(chaser, inventory=scroll))
        self.assertEqual(sighted.escape_means, ("teleport-scroll",))
        self.assertFalse(sighted.cannot_escape)
        blind = self.assess(board(chaser, inventory=scroll, blind=True))
        self.assertTrue(blind.cannot_escape)
        self.assertFalse(blind.escape_restorable)
        self.assertEqual(blind.per_monster[1].selected, ("cannot-escape",))
        curable = self.assess(board(chaser, inventory=[*scroll, potion("b", 36, 1)], blind=True))
        self.assertTrue(curable.escape_restorable)
        self.assertEqual(curable.per_monster[1].selected, ())

    def test_a_slower_monster_is_walked_away_from(self):
        result = self.assess(board([monster(1, DUELIST, 10, 12)], blind=True))
        self.assertEqual(result.escape_means, ("walk",))

    def test_a_worn_anti_teleport_item_blocks_the_scrolls(self):
        chaser = [monster(1, DUELIST, 10, 12, speed=120)]
        scroll = [item("a", TVAL_SCROLL, 9, count=5, name="Teleportation")]
        amulet = item("amulet", 40, 1, is_equipment=True, known_flags=frozenset({"NO_TELE"}))
        with patch.object(self.policy, "_blocks_teleport",
                          side_effect=lambda each: each is amulet):  # DECLARED CONSTRUCTED flag
            result = self.assess(board(chaser, inventory=scroll, equipment=(SWORD, amulet)))
        self.assertTrue(result.cannot_escape)
        self.assertTrue(result.escape_restorable)  # not cursed: it can be taken off

    # -- 3.4 selection: rewards --------------------------------------------------

    def rewards(self, race_id, **player_fields):
        snapshot = board([monster(1, race_id, 10, 13)])
        snapshot = replace(snapshot, player=replace(snapshot.player, **player_fields))
        return self.assess(snapshot).per_monster[1].reward

    def test_reward_races(self):
        self.assertEqual(self.rewards(GOODIE), ("drop_good",))
        self.assertEqual(self.rewards(HOARDER), ("many-drops",))   # DROP_2D2 = 3 items
        self.assertEqual(self.rewards(FEW_DROPS), ())              # 1.5 + 0.9 < 3
        self.assertEqual(self.rewards(BREEDER), ())                # breeders are no reward
        self.assertEqual(self.rewards(WEAK), ())

    def test_exp_reward_is_ten_percent_of_the_exp_still_needed(self):
        # 1.5 x level 10 x mexp 100 / (max level 10 + 2) = 125.
        self.assertEqual(self.rewards(SAGE, exp=1000, exp_to_advance=2250, max_level=10), ("exp",))
        self.assertEqual(self.rewards(SAGE, exp=1000, exp_to_advance=2260, max_level=10), ())
        self.assertEqual(self.rewards(SAGE, exp=1000, exp_to_advance=None, max_level=10), ())

    # -- the cost cap ------------------------------------------------------------

    def test_the_bracket_decides_without_the_long_projection(self):
        # DECLARED CONSTRUCTED budget: no horizon past one turn is computed.
        with patch.object(threat_tiers, "PROJECTION_COST_BUDGET", 0):
            brute = self.assess(board([monster(1, BRUTE, 10, 11)]))
            weak = self.assess(board([monster(1, WEAK, 10, 11, hp=40)]))
        self.assertEqual(brute.tier, threat_tiers.T1)  # one turn already outdamages the HP
        self.assertEqual(weak.tier, threat_tiers.T3)   # every blow at its maximum stays below it
        self.assertIsNone(weak.free_incoming)
        low, high = weak.free_incoming_bounds
        self.assertLess(high, 300)
        exact = self.assess(board([monster(1, WEAK, 10, 11, hp=40)])).free_incoming
        self.assertLessEqual(low, exact)
        self.assertLessEqual(exact, high)

    def test_an_undecided_bracket_is_skipped_not_computed(self):
        duel = [monster(1, DUELIST, 10, 11, hp=150)]
        with patch.object(threat_tiers, "PROJECTION_COST_BUDGET", 0):
            result = self.assess(board(duel, inventory=[potion("a", SV_POTION_HEALING, 5)]))
        self.assertIsNone(result.tier)
        self.assertEqual(result.skipped, "cost")
        self.assertIsNone(result.supply_plan)
        self.assertFalse(result.instant_death)  # 即死 and the flags are still recorded
        self.assertEqual(threat_tiers.facts(self.policy, board(duel))["skipped"], None)

    # -- telemetry ---------------------------------------------------------------

    def test_facts_are_json_shaped_and_empty_without_hostiles(self):
        self.assertEqual(threat_tiers.facts(self.policy, board([])), {})
        facts = threat_tiers.facts(self.policy, board([monster(1, WEAK, 10, 11)]))
        self.assertEqual(facts["tier"], threat_tiers.T3)
        self.assertEqual(facts["monsters"][0]["race_id"], WEAK)
        self.assertIn("flags", facts)


if __name__ == "__main__":
    unittest.main()
