import unittest

from hengbot.equipment_encounters import EncounterTarget
from hengbot.equipment_optimizer import Loadout, OwnedEquipment
from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.warrior_defense_evaluator import (
    WarriorDefenseInputs,
    evaluate_warrior_defense,
    expected_blow_hp_damage,
    loadout_armor_class,
    monster_melee_hit_chance,
)


def item(item_id, tval, *, ac=0, to_a=0, pval=0, flags=()):
    value = InventoryItem(
        slot=item_id, name=item_id, count=1, tval=tval, sval=1,
        aware=True, known=True, fully_known=True, is_equipment=True,
        ac=ac, to_a=to_a, pval=pval, known_flags=frozenset(flags),
    )
    return OwnedEquipment(item_id, value, "home")


class WarriorDefenseEvaluatorTest(unittest.TestCase):
    def test_loadout_ac_includes_dex_armor_shield_skill_and_supportive(self):
        shield = item("shield", 34, ac=8, to_a=2, flags={147})
        armor = item("armor", 37, ac=12, to_a=3)
        loadout = Loadout((("sub_hand", shield), ("body", armor)), "weapon_shield")
        result = loadout_armor_class(
            loadout,
            WarriorDefenseInputs(level=22, natural_dex=18, shield_skill=4000),
        )
        self.assertEqual(result, 2 + 10 + 15 + 4 + 5)

    def test_no_ac_flag_zeroes_all_armor(self):
        armor = item("armor", 37, ac=50, to_a=20, flags={141})
        self.assertEqual(
            loadout_armor_class(
                Loadout((("body", armor),), "empty"),
                WarriorDefenseInputs(level=10, natural_dex=18),
            ),
            0,
        )

    def test_monster_hit_chance_has_five_percent_floor(self):
        self.assertAlmostEqual(monster_melee_hit_chance("HURT", 10, 0), 0.95)
        self.assertAlmostEqual(monster_melee_hit_chance("HURT", 10, -100), 0.95)
        self.assertAlmostEqual(monster_melee_hit_chance("HURT", 10, 1000), 0.05)

    def test_hungry_and_chaos_follow_compiled_zero_power_table_entries(self):
        self.assertAlmostEqual(monster_melee_hit_chance("HUNGRY", 0, 0), 0.05)
        self.assertAlmostEqual(monster_melee_hit_chance("CHAOS", 0, 0), 0.05)

    def test_hurt_uses_integer_ac_reduction(self):
        damage = expected_blow_hp_damage(
            MonsterBlow("HIT", "HURT", 1, 10),
            monster_level=10,
            armor_class=100,
            flags=frozenset(),
        )
        expected = sum(value - value * 100 // 250 for value in range(1, 11)) / 10
        self.assertEqual(damage, expected)

    def test_superhurt_includes_source_critical_probability(self):
        hurt = expected_blow_hp_damage(
            MonsterBlow("HIT", "HURT", 1, 1),
            monster_level=50, armor_class=100, flags=frozenset(),
        )
        superhurt = expected_blow_hp_damage(
            MonsterBlow("HIT", "SUPERHURT", 1, 1),
            monster_level=50, armor_class=100, flags=frozenset(),
        )
        first = 100 / 400
        critical = first + (1 - first) / 13
        self.assertAlmostEqual(superhurt, hurt * (1 + critical))

    def test_elemental_resistance_vulnerability_and_immunity(self):
        blow = MonsterBlow("TOUCH", "FIRE", 1, 10)
        normal = expected_blow_hp_damage(
            blow, monster_level=10, armor_class=0, flags=frozenset()
        )
        resisted = expected_blow_hp_damage(
            blow, monster_level=10, armor_class=0, flags=frozenset({50})
        )
        vulnerable = expected_blow_hp_damage(
            blow, monster_level=10, armor_class=0, flags=frozenset({155})
        )
        immune = expected_blow_hp_damage(
            blow, monster_level=10, armor_class=0, flags=frozenset({42})
        )
        self.assertLess(resisted, normal)
        self.assertGreater(vulnerable, normal)
        self.assertEqual(immune, 0)

    def test_exploding_blow_has_no_hp_damage(self):
        self.assertEqual(
            expected_blow_hp_damage(
                MonsterBlow("EXPLODE", "FIRE", 20, 20),
                monster_level=40, armor_class=0, flags=frozenset(),
            ),
            0,
        )

    def test_non_hp_blow_resources_are_not_counted_as_hp(self):
        for effect in ("DR_MANA", "HUNGRY"):
            with self.subTest(effect=effect):
                self.assertEqual(
                    expected_blow_hp_damage(
                        MonsterBlow("TOUCH", effect, 10, 10),
                        monster_level=20, armor_class=0, flags=frozenset(),
                    ),
                    0,
                )

    def test_status_resistance_uses_random_integer_damage_reduction(self):
        blow = MonsterBlow("GAZE", "CONFUSE", 1, 10)
        result = expected_blow_hp_damage(
            blow, monster_level=10, armor_class=0, flags=frozenset({57})
        )
        expected = sum(
            sum(damage * (roll + 3) // 8 for roll in range(1, 5)) / 4
            for damage in range(1, 11)
        ) / 10
        self.assertEqual(result, expected)

    def test_shatter_uses_hurt_ac_reduction(self):
        blow = MonsterBlow("CRUSH", "SHATTER", 1, 10)
        result = expected_blow_hp_damage(
            blow, monster_level=20, armor_class=100, flags=frozenset()
        )
        expected = sum(damage - damage * 100 // 250 for damage in range(1, 11)) / 10
        self.assertEqual(result, expected)

    def test_chaos_resistance_uses_random_source_rates(self):
        blow = MonsterBlow("TOUCH", "CHAOS", 1, 100)
        normal = expected_blow_hp_damage(
            blow, monster_level=40, armor_class=0, flags=frozenset()
        )
        resisted = expected_blow_hp_damage(
            blow, monster_level=40, armor_class=0, flags=frozenset({62})
        )
        self.assertLess(resisted, normal)

    def test_evaluation_is_complete_for_modelled_side_effects(self):
        race = MonraceKnowledge(
            max_hp=10, speed=110, can_summon=False, friendly=False, level=10,
            blows=(
                MonsterBlow("HIT", "HURT", 1, 6),
                MonsterBlow("GAZE", "CONFUSE", 1, 1),
            ),
        )
        result = evaluate_warrior_defense(
            Loadout((), "empty"),
            WarriorDefenseInputs(level=10, natural_dex=18),
            (EncounterTarget(1, 1.0, race),),
        )
        self.assertGreater(result.expected_melee_damage, 0)
        self.assertEqual(result.unsupported_effects, frozenset())
        self.assertTrue(result.melee_complete)

    def test_confusion_resistance_removes_status_turn_exposure(self):
        race = MonraceKnowledge(
            max_hp=10, speed=110, can_summon=False, friendly=False, level=10,
            blows=(MonsterBlow("GAZE", "CONFUSE", 1, 1),),
        )
        encounters = (EncounterTarget(1, 1.0, race),)
        unprotected = evaluate_warrior_defense(
            Loadout((), "empty"),
            WarriorDefenseInputs(level=10, natural_dex=18),
            encounters,
        )
        protected = evaluate_warrior_defense(
            Loadout((), "empty"),
            WarriorDefenseInputs(
                level=10, natural_dex=18, intrinsic_flags=frozenset({57})
            ),
            encounters,
        )
        self.assertGreater(dict(unprotected.status_turn_exposure)["confused"], 0)
        self.assertNotIn("confused", dict(protected.status_turn_exposure))

    def test_free_action_and_saving_throw_reduce_paralysis_exposure(self):
        race = MonraceKnowledge(
            max_hp=10, speed=110, can_summon=False, friendly=False, level=20,
            blows=(MonsterBlow("TOUCH", "PARALYZE", 1, 1),),
        )
        encounters = (EncounterTarget(1, 1.0, race),)
        weak_save = evaluate_warrior_defense(
            Loadout((), "empty"),
            WarriorDefenseInputs(level=20, natural_dex=18, saving_skill=0),
            encounters,
        )
        strong_save = evaluate_warrior_defense(
            Loadout((), "empty"),
            WarriorDefenseInputs(level=20, natural_dex=18, saving_skill=100),
            encounters,
        )
        free_action = evaluate_warrior_defense(
            Loadout((), "empty"),
            WarriorDefenseInputs(
                level=20, natural_dex=18, intrinsic_flags=frozenset({46})
            ),
            encounters,
        )
        self.assertGreater(
            dict(weak_save.status_turn_exposure)["paralyzed"],
            dict(strong_save.status_turn_exposure)["paralyzed"],
        )
        self.assertNotIn("paralyzed", dict(free_action.status_turn_exposure))

    def test_sustain_removes_corresponding_stat_drain_event(self):
        race = MonraceKnowledge(
            max_hp=10, speed=110, can_summon=False, friendly=False, level=10,
            blows=(MonsterBlow("TOUCH", "LOSE_STR", 1, 1),),
        )
        result = evaluate_warrior_defense(
            Loadout((), "empty"),
            WarriorDefenseInputs(
                level=10, natural_dex=18, intrinsic_flags=frozenset({32})
            ),
            (EncounterTarget(1, 1.0, race),),
        )
        self.assertNotIn("strength-drain", dict(result.resource_event_exposure))


if __name__ == "__main__":
    unittest.main()
