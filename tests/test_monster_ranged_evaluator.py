import unittest

from hengbot.equipment_encounters import EncounterTarget
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.monster_ranged_evaluator import (
    TR_IM_FIRE,
    TR_FREE_ACT,
    TR_INVULN_ARROW,
    TR_REFLECT,
    TR_RES_CHAOS,
    TR_RES_CONF,
    TR_RES_DISEN,
    TR_RES_FIRE,
    TR_RES_NEXUS,
    TR_RES_SHARDS,
    SpellSelectionContext,
    aggregate_ranged_damage_percentile,
    cause_damage_percentile,
    maximum_ability_hp_damage,
    ability_selection_probabilities,
    expected_ability_base_damage,
    expected_ability_hp_damage,
    evaluate_ability_effect,
    evaluate_warrior_ranged_defense,
    _ability_base_damage_distribution,
)


def monster(*, level=30, hp=300, powerful=False, shoot=(0, 0)):
    return MonraceKnowledge(
        max_hp=hp, average_hp=hp, speed=110, can_summon=False,
        friendly=False, level=level, powerful=powerful,
        shoot_dice_num=shoot[0], shoot_dice_sides=shoot[1],
    )


class AbilityDamageClassificationTest(unittest.TestCase):
    def test_known_non_damage_abilities_have_no_damage_distribution(self):
        race = monster()
        for ability in ("DRAIN_MANA", "TELE_TO", "HEAL", "HASTE", "BLINK", "TRAPS"):
            with self.subTest(ability=ability):
                self.assertIsNone(
                    _ability_base_damage_distribution(ability, race, 100)
                )

    def test_genuinely_unknown_ability_still_raises(self):
        with self.assertRaisesRegex(ValueError, "unsupported monster ability"):
            _ability_base_damage_distribution("NOT_A_REAL_ABILITY", monster(), 100)


class MonsterRangedEvaluatorTest(unittest.TestCase):
    PLAYER_FLAGS = frozenset({46, 50, 51, 52, 53, 54, 55, 60, 61})

    def _aggregate(self, caster, actions):
        selection = ability_selection_probabilities(
            caster, SpellSelectionContext(distance=2)
        )
        return aggregate_ranged_damage_percentile(
            caster,
            actions=actions,
            selection_probabilities=selection,
            flags=self.PLAYER_FLAGS,
            player_hp=427,
            saving_skill=58,
        )

    def test_dark_elven_priest_cause_two_uses_95th_percentile(self):
        priest = MonraceKnowledge(
            max_hp=70,
            average_hp=38,
            speed=115,
            can_summon=False,
            friendly=False,
            level=12,
            abilities=frozenset(
                {"DARKNESS", "BLIND", "CAUSE_2", "MISSILE", "HEAL", "CONF"}
            ),
            spell_frequency=20,
        )
        selection = ability_selection_probabilities(
            priest, SpellSelectionContext(distance=2)
        )

        result = cause_damage_percentile(
            "CAUSE_2",
            priest,
            actions=6,
            selection_probability=selection["CAUSE_2"],
            saving_skill=52,
        )

        self.assertAlmostEqual(result.per_action_probability, 0.019537055047656085)
        self.assertEqual(result.successful_casts, 1)
        self.assertEqual(result.damage_per_cast, 47)
        self.assertEqual(result.total_damage, 47)

    def test_aggregate_p95_matches_random_depth_band_validation_samples(self):
        ring_mimic = MonraceKnowledge(
            max_hp=350, average_hp=350, speed=120, can_summon=True,
            friendly=False, level=29, spell_frequency=25,
            abilities=frozenset({
                "BLIND", "BO_ACID", "BO_COLD", "BO_ELEC", "BO_FIRE",
                "CAUSE_2", "CONF", "FORGET", "SCARE", "S_MONSTER",
            }),
        )
        planetar = MonraceKnowledge(
            max_hp=2200, average_hp=2200, speed=130, can_summon=True,
            friendly=False, level=50, spell_frequency=25, powerful=True,
            abilities=frozenset({
                "BO_MANA", "BO_PLAS", "CAUSE_4", "DISPEL", "HASTE",
                "HEAL", "INVULNER", "PSY_SPEAR", "S_ANGEL", "S_DRAGON",
                "S_MONSTERS", "TELE_AWAY",
            }),
        )
        lain = MonraceKnowledge(
            max_hp=6500, average_hp=6500, speed=130, can_summon=False,
            friendly=False, level=80, spell_frequency=50, powerful=True,
            abilities=frozenset({
                "BA_CHAO", "BA_DARK", "BA_LITE", "BRAIN_SMASH", "DISPEL",
                "HAND_DOOM", "HASTE", "HEAL", "INVULNER", "PSY_SPEAR",
                "SLOW", "TPORT", "WORLD",
            }),
        )

        fixtures = (
            (ring_mimic, 7, 46, 0.347713355),
            (planetar, 10, 319, 0.453931732),
            (lain, 10, 1329, 0.984498170),
        )
        for caster, actions, damage_p95, probability_any in fixtures:
            with self.subTest(level=caster.level):
                result = self._aggregate(caster, actions)
                self.assertEqual(result.total_damage, damage_p95)
                self.assertAlmostEqual(
                    result.probability_any_damage, probability_any, places=8
                )
                self.assertFalse(result.floor_applied)

        self.assertGreater(self._aggregate(lain, 10).total_damage, 620)

    def test_aggregate_p95_guarantees_one_single_hit_when_raw_p95_is_zero(self):
        rare_archer = MonraceKnowledge(
            max_hp=100, average_hp=100, speed=110, can_summon=False,
            friendly=False, level=1, spell_frequency=1,
            abilities=frozenset({"SHOOT"}), flags=frozenset({"STUPID"}),
            shoot_dice_num=2, shoot_dice_sides=6,
        )

        result = aggregate_ranged_damage_percentile(
            rare_archer,
            actions=1,
            selection_probabilities=ability_selection_probabilities(
                rare_archer, SpellSelectionContext(distance=2)
            ),
        )

        self.assertAlmostEqual(result.probability_any_damage, 0.01)
        self.assertEqual(result.single_hit_floor, 11)
        self.assertEqual(result.total_damage, 11)
        self.assertTrue(result.floor_applied)

    def test_poison_ball_maximum_matches_game_dice_and_resistance(self):
        caster = monster(level=12)

        self.assertEqual(maximum_ability_hp_damage("BA_POIS", caster), 24)
        self.assertEqual(
            maximum_ability_hp_damage(
                "BA_POIS", caster, flags=frozenset({52})
            ),
            8,
        )

    def test_breath_uses_hp_divisor_and_cap(self):
        self.assertEqual(expected_ability_base_damage("BR_FIRE", monster(hp=300)), 100)
        self.assertEqual(expected_ability_base_damage("BR_FIRE", monster(hp=9000)), 1600)

    def test_void_breath_preserves_source_asymmetric_conditional(self):
        self.assertEqual(expected_ability_base_damage("BR_VOID", monster(hp=600)), 100)
        self.assertEqual(expected_ability_base_damage("BR_VOID", monster(hp=900)), 250)

    def test_shoot_uses_definition_dice(self):
        self.assertEqual(
            expected_ability_base_damage("SHOOT", monster(shoot=(2, 6))),
            7,
        )

    def test_powerful_fire_ball_uses_source_base_and_dice(self):
        self.assertEqual(
            expected_ability_base_damage("BA_FIRE", monster(level=30, powerful=True)),
            225,
        )

    def test_non_damage_ability_returns_none(self):
        self.assertIsNone(expected_ability_base_damage("S_MONSTER", monster()))

    def test_hand_of_doom_requires_and_uses_current_hp(self):
        with self.assertRaises(ValueError):
            expected_ability_base_damage("HAND_DOOM", monster())
        self.assertEqual(
            expected_ability_base_damage("HAND_DOOM", monster(), player_hp=250),
            106.0,
        )

    def test_elemental_resistance_and_immunity_reduce_damage(self):
        target = monster(hp=300)
        self.assertEqual(
            expected_ability_hp_damage("BR_FIRE", target, flags=frozenset({TR_RES_FIRE})),
            34,
        )
        self.assertEqual(
            expected_ability_hp_damage("BR_FIRE", target, flags=frozenset({TR_IM_FIRE})),
            0,
        )

    def test_reflection_reduces_bolts_but_not_breaths(self):
        target = monster(level=30, hp=300)
        bolt = expected_ability_base_damage("BO_FIRE", target)
        self.assertAlmostEqual(
            expected_ability_hp_damage("BO_FIRE", target, flags=frozenset({TR_REFLECT})),
            bolt * 0.1,
        )
        self.assertEqual(
            expected_ability_hp_damage("BR_FIRE", target, flags=frozenset({TR_REFLECT})),
            100,
        )

    def test_shoot_immunity_only_works_while_not_blind(self):
        target = monster(shoot=(2, 6))
        flags = frozenset({TR_INVULN_ARROW})
        self.assertEqual(expected_ability_hp_damage("SHOOT", target, flags=flags), 0)
        self.assertEqual(
            expected_ability_hp_damage("SHOOT", target, flags=flags, blind=True),
            7,
        )

    def test_random_high_resistance_rates_preserve_integer_rounding(self):
        target = monster(hp=600)
        self.assertEqual(
            expected_ability_hp_damage("BR_CHAO", target, flags=frozenset({TR_RES_CHAOS})),
            (75 + 66 + 60 + 54) / 4,
        )

    def test_rocket_uses_shard_resistance(self):
        target = monster(hp=400)
        self.assertEqual(
            expected_ability_hp_damage("ROCKET", target, flags=frozenset({TR_RES_SHARDS})),
            50,
        )

    def test_nexus_hp_bug_is_source_compatible(self):
        target = monster(hp=300)
        self.assertEqual(
            expected_ability_hp_damage("BR_NEXU", target, flags=frozenset({TR_RES_NEXUS})),
            100,
        )
        self.assertLess(
            expected_ability_hp_damage("BR_NEXU", target, flags=frozenset({TR_RES_DISEN})),
            100,
        )

    def test_saving_throw_reduces_curse_expected_damage(self):
        target = monster(level=40)
        base = expected_ability_base_damage("CAUSE_2", target)
        self.assertAlmostEqual(
            expected_ability_hp_damage("CAUSE_2", target, saving_skill=60),
            base * 0.5,
        )

    def test_mind_attack_has_source_minimum_saving_skill(self):
        target = monster(level=0)
        base = expected_ability_base_damage("MIND_BLAST", target)
        self.assertAlmostEqual(
            expected_ability_hp_damage("MIND_BLAST", target, saving_skill=0),
            base * 0.95,
        )

    def test_confusion_breath_exposes_confusion_unless_resisted(self):
        target = monster(hp=600)
        exposed = evaluate_ability_effect("BR_CONF", target)
        protected = evaluate_ability_effect(
            "BR_CONF", target, flags=frozenset({TR_RES_CONF})
        )
        self.assertEqual(dict(exposed.status_turn_exposure)["confused"], 20.5)
        self.assertNotIn("confused", dict(protected.status_turn_exposure))

    def test_reflection_scales_bolt_side_effects(self):
        target = monster(level=30)
        normal = evaluate_ability_effect("BO_PLAS", target)
        reflected = evaluate_ability_effect(
            "BO_PLAS", target, flags=frozenset({TR_REFLECT})
        )
        self.assertAlmostEqual(
            dict(reflected.status_turn_exposure)["stunned"],
            dict(normal.status_turn_exposure)["stunned"] * 0.1,
        )

    def test_direct_hold_uses_save_and_free_action(self):
        target = monster(level=40)
        exposed = evaluate_ability_effect("HOLD", target, saving_skill=60)
        protected = evaluate_ability_effect(
            "HOLD", target, saving_skill=60, flags=frozenset({TR_FREE_ACT})
        )
        self.assertAlmostEqual(dict(exposed.status_turn_exposure)["paralyzed"], 2.75)
        self.assertNotIn("paralyzed", dict(protected.status_turn_exposure))

    def test_water_resistance_blocks_status_and_inventory_effects(self):
        target = monster(level=30)
        exposed = evaluate_ability_effect("BA_WATE", target)
        protected = evaluate_ability_effect(
            "BA_WATE", target, flags=frozenset({144})
        )
        self.assertIn("confused", dict(exposed.status_turn_exposure))
        self.assertEqual(protected.status_turn_exposure, ())
        self.assertEqual(protected.resource_event_exposure, ())

    def test_encounter_aggregation_uses_frequency_and_spell_failure(self):
        caster = MonraceKnowledge(
            max_hp=300, average_hp=300, speed=110, can_summon=False,
            friendly=False, level=20, spell_frequency=20,
            abilities=frozenset({"MISSILE"}), flags=frozenset({"STUPID"}),
        )
        result = evaluate_warrior_ranged_defense(
            frozenset(), saving_skill=0, player_hp=100,
            encounters=(EncounterTarget(1, 1.0, caster),),
        )
        self.assertAlmostEqual(
            result.expected_ranged_damage,
            expected_ability_base_damage("MISSILE", caster) * 0.2,
        )
        self.assertTrue(result.ranged_complete)

    def test_smart_caster_is_marked_context_incomplete(self):
        caster = MonraceKnowledge(
            max_hp=300, average_hp=300, speed=110, can_summon=False,
            friendly=False, level=20, spell_frequency=20,
            abilities=frozenset({"BR_FIRE"}),
        )
        result = evaluate_warrior_ranged_defense(
            frozenset(), saving_skill=0, player_hp=100,
            encounters=(EncounterTarget(1, 1.0, caster),),
        )
        self.assertIn("smart-spell-selection-context", result.unsupported_effects)
        self.assertFalse(result.ranged_complete)

    def test_stupid_selection_mixes_full_and_innate_abilities(self):
        caster = MonraceKnowledge(
            max_hp=300, average_hp=300, speed=110, can_summon=False,
            friendly=False, level=20, spell_frequency=20,
            abilities=frozenset({"BR_FIRE", "MISSILE"}),
            flags=frozenset({"STUPID"}),
        )
        probabilities = ability_selection_probabilities(
            caster, SpellSelectionContext()
        )
        self.assertAlmostEqual(probabilities["BR_FIRE"], 0.8)
        self.assertAlmostEqual(probabilities["MISSILE"], 0.2)

    def test_smart_selector_applies_summon_before_attack_and_retries(self):
        caster = MonraceKnowledge(
            max_hp=300, average_hp=300, speed=110, can_summon=True,
            friendly=False, level=50, spell_frequency=50,
            abilities=frozenset({"S_MONSTER", "BR_FIRE"}),
        )
        probabilities = ability_selection_probabilities(
            caster, SpellSelectionContext(summon_possible=True)
        )
        retry_total = sum(0.09 ** attempt for attempt in range(10))
        self.assertAlmostEqual(probabilities["S_MONSTER"], 0.4 * retry_total)
        self.assertAlmostEqual(probabilities["BR_FIRE"], 0.51 * retry_total)

    def test_explicit_context_completes_smart_ranged_evaluation(self):
        caster = MonraceKnowledge(
            max_hp=300, average_hp=300, speed=110, can_summon=False,
            friendly=False, level=20, spell_frequency=20,
            abilities=frozenset({"BR_FIRE"}),
        )
        result = evaluate_warrior_ranged_defense(
            frozenset(), saving_skill=0, player_hp=100,
            encounters=(EncounterTarget(1, 1.0, caster),),
            selection_context=SpellSelectionContext(),
        )
        self.assertTrue(result.ranged_complete)

    def test_summoning_is_retained_as_tactical_exposure(self):
        result = evaluate_ability_effect("S_MONSTER", monster())
        self.assertEqual(
            dict(result.resource_event_exposure)["summoning"], 1.0
        )


if __name__ == "__main__":
    unittest.main()
