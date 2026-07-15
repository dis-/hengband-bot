import unittest

from hengbot.equipment_optimizer import Loadout, OwnedEquipment
from hengbot.equipment_encounters import EncounterTarget
from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.warrior_equipment_evaluator import (
    ADJ_DEX_BLOW,
    ADJ_STR_BLOW,
    ADJ_STR_HOLD,
    BLOWS_TABLE,
    WarriorCombatInputs,
    _warrior_blows,
    evaluate_warrior_melee,
    expected_critical_damage,
    hit_chance,
    modify_stat_value,
    stat_index,
    trunc_div,
)


def item(item_id, tval, *, pval=0, flags=(), weight=0, dd=0, ds=0, to_h=0, to_d=0, proficiency=0):
    value = InventoryItem(
        slot=item_id, name=item_id, count=1, tval=tval, sval=1,
        aware=True, known=True, fully_known=True, is_equipment=True,
        pval=pval, known_flags=frozenset(flags), weight=weight,
        damage_dice_num=dd, damage_dice_sides=ds, to_h=to_h, to_d=to_d,
        weapon_proficiency=proficiency,
    )
    return OwnedEquipment(item_id, value, "home")


class WarriorEquipmentEvaluatorTest(unittest.TestCase):
    def test_warrior_blow_count_matches_cpp_formula_across_boundaries(self):
        weights = (20, 69, 70, 71, 99, 100, 160, 500)
        levels = (1, 22, 23, 39, 40, 50)
        for str_idx in range(38):
            for dex_idx in range(38):
                for weight in weights:
                    weapon = item("weapon", 23, weight=weight, dd=1, ds=1)
                    for level in levels:
                        for two_hand_bonus in (False, True):
                            for extra_blows in (0, 1, 3):
                                if ADJ_STR_HOLD[str_idx] < weight // 10:
                                    expected = 1
                                else:
                                    p = ADJ_STR_BLOW[str_idx] * 5 // max(70, weight)
                                    if two_hand_bonus:
                                        p += level // 23 + 1
                                    p = min(11, p)
                                    d = min(11, ADJ_DEX_BLOW[dex_idx])
                                    expected = max(
                                        1,
                                        min(6, BLOWS_TABLE[p][d])
                                        + extra_blows
                                        + level // 40,
                                    )
                                self.assertEqual(
                                    _warrior_blows(
                                        weapon,
                                        str_idx=str_idx,
                                        dex_idx=dex_idx,
                                        level=level,
                                        two_hand_bonus=two_hand_bonus,
                                        extra_blows=extra_blows,
                                    ),
                                    expected,
                                )

    def test_cpp_division_truncates_negative_values_toward_zero(self):
        self.assertEqual(trunc_div(-7, 2), -3)

    def test_stat_modification_and_index_match_hengband_boundaries(self):
        self.assertEqual(modify_stat_value(17, 2), 28)
        self.assertEqual(modify_stat_value(19, -1), 18)
        self.assertEqual(stat_index(18), 15)
        self.assertEqual(stat_index(28), 16)
        self.assertEqual(stat_index(238), 37)

    def test_hit_chance_uses_ac100_reference_and_five_percent_floor(self):
        self.assertEqual(hit_chance(0), 0.05)
        self.assertEqual(hit_chance(100), 0.27)
        self.assertEqual(hit_chance(300), 0.72)

    def test_warrior_blows_follow_source_table_and_two_hand_bonus(self):
        sword = item("sword", 23, weight=70, dd=2, ds=5)
        polearm = item("polearm", 22, weight=70, dd=2, ds=5)
        one = Loadout((("main_hand", sword),), "one_handed")
        two = Loadout((("main_hand", polearm),), "two_handed")
        inputs = WarriorCombatInputs(level=23, natural_str=18, natural_dex=18, melee_skill=60)
        self.assertEqual(evaluate_warrior_melee(one, inputs).hands[0].blows, 1)
        self.assertEqual(evaluate_warrior_melee(two, inputs).hands[0].blows, 2)

    def test_live_modified_stats_produce_four_blows_with_heavy_polearm(self):
        # BOT_PLAY turn 2266781: natural STR 82 / DEX 31, but the character
        # sheet's race/class/personality-modified values are STR 162 / DEX 61.
        # Hengband reports four blows for the 16.0 lb pike while using a shield.
        pike = item("pike", 22, weight=160, dd=4, ds=5)
        shield = item("shield", 34, weight=160)
        loadout = Loadout(
            (("main_hand", pike), ("sub_hand", shield)),
            "weapon_shield",
        )

        result = evaluate_warrior_melee(
            loadout,
            WarriorCombatInputs(
                level=27,
                natural_str=162,
                natural_dex=61,
                melee_skill=60,
            ),
        )

        self.assertEqual(result.hands[0].blows, 4)

    def test_strength_pval_can_increase_real_damage_and_blows(self):
        sword = item("sword", 23, weight=70, dd=2, ds=5)
        ring = item("ring", 45, pval=2, flags={0})
        plain = Loadout((("main_hand", sword),), "one_handed")
        boosted = Loadout((("main_hand", sword), ("main_ring", ring)), "one_handed")
        inputs = WarriorCombatInputs(level=20, natural_str=17, natural_dex=18, melee_skill=60)
        before = evaluate_warrior_melee(plain, inputs)
        after = evaluate_warrior_melee(boosted, inputs)
        self.assertGreater(after.expected_dps_ac100, before.expected_dps_ac100)
        self.assertEqual(after.stat_str, 28)

    def test_weapon_proficiency_is_measured_from_beginner_4000(self):
        beginner = item(
            "beginner", 23, weight=70, dd=1, ds=4, proficiency=4000
        )
        skilled = item(
            "skilled", 23, weight=70, dd=1, ds=4, proficiency=6000
        )
        inputs = WarriorCombatInputs(
            level=10, natural_str=18, natural_dex=18, melee_skill=60
        )
        beginner_result = evaluate_warrior_melee(
            Loadout((("main_hand", beginner),), "one_handed"), inputs
        )
        skilled_result = evaluate_warrior_melee(
            Loadout((("main_hand", skilled),), "one_handed"), inputs
        )
        self.assertEqual(
            skilled_result.hands[0].to_hit - beginner_result.hands[0].to_hit,
            10,
        )

    def test_digger_is_evaluated_as_a_melee_weapon(self):
        pick = item("pick", 20, weight=80, dd=1, ds=3, proficiency=4000)
        result = evaluate_warrior_melee(
            Loadout((("main_hand", pick),), "one_handed"),
            WarriorCombatInputs(
                level=10, natural_str=18, natural_dex=18, melee_skill=60
            ),
        )
        self.assertEqual(len(result.hands), 1)

    def test_impact_increases_expected_critical_damage(self):
        normal = expected_critical_damage(
            weight=120, weapon_to_h=10, hand_to_h=10, melee_skill=80,
            base_damage=12,
        )
        impact = expected_critical_damage(
            weight=120, weapon_to_h=10, hand_to_h=10, melee_skill=80,
            base_damage=12, impact=True,
        )
        self.assertGreater(impact, normal)

    def test_encounter_weighted_slay_increases_dps_and_sets_kill_turns(self):
        plain = item(
            "plain", 23, weight=70, dd=2, ds=5, proficiency=4000
        )
        slay_orc = item(
            "slay-orc",
            23,
            weight=70,
            dd=2,
            ds=5,
            proficiency=4000,
            flags={20},
        )
        orc = MonraceKnowledge(
            max_hp=30,
            average_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            flags=frozenset({"ORC"}),
        )
        encounters = (EncounterTarget(1, 1.0, orc),)
        inputs = WarriorCombatInputs(
            level=10, natural_str=18, natural_dex=18, melee_skill=60
        )
        plain_result = evaluate_warrior_melee(
            Loadout((("main_hand", plain),), "one_handed"),
            inputs,
            encounters,
        )
        slay_result = evaluate_warrior_melee(
            Loadout((("main_hand", slay_orc),), "one_handed"),
            inputs,
            encounters,
        )
        self.assertGreater(slay_result.expected_dps_ac100, plain_result.expected_dps_ac100)
        self.assertEqual(slay_result.weighted_average_target_hp, 20)
        self.assertLess(slay_result.expected_kill_turns, plain_result.expected_kill_turns)


if __name__ == "__main__":
    unittest.main()
