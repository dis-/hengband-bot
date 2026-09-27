import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest

from hengbot.equipment_encounters import EncounterTarget
from hengbot.equipment_optimizer import (
    EvaluatedLoadout, Loadout, OwnedEquipment, _stable_operational_best,
)
from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext, WarriorRangedDefenseResult,
)
from hengbot.policy_constants import speed_energy
from hengbot.warrior_defense_evaluator import WarriorDefenseInputs, WarriorDefenseResult
from hengbot.warrior_equipment_evaluator import (
    HandMeleeResult, WarriorCombatInputs, WarriorMeleeResult,
)
from hengbot.warrior_loadout_evaluator import (
    CachedWarriorLoadoutEvaluator,
    WarriorLoadoutInputs,
    _combine_warrior_results,
    evaluate_warrior_loadout,
    loadout_max_hp,
    warrior_ranged_offense_dps,
)


class WarriorLoadoutEvaluatorTest(unittest.TestCase):
    def test_speed_energy_matches_hengband_table_edges(self):
        self.assertEqual(
            [speed_energy(speed) for speed in (69, 70, 87, 88, 89, 90, 110, 120, 199, 200)],
            [1, 2, 2, 3, 3, 3, 10, 20, 49, 49],
        )

    def test_recorded_161629_boots_choose_vearfana_in_player_turns(self):
        # The report has identical other slots. Its rank-1 boots had AC 110,
        # +1 speed and 30.1926 old survival turns; Vearfana had AC 109,
        # +4 speed, 29.9588 old turns, and 197.78 vs 146.15 melee output.
        shared_ids = {
            "body": "equipped:dd3160546605da93:0",
            "bow": "equipped:dfced2db72264354:0",
            "head": "equipped:58307ea4f2573e65:0",
            "light": "equipped:21b109e0d6b6382d:0",
            "main_hand": "equipped:6b618bb076845eeb:0",
            "main_ring": "equipped:cece0625c1832d34:0",
            "neck": "equipped:7a506b5e8e56f2b1:0",
            "outer": "equipped:330652cb223ea795:0",
            "sub_hand": "equipped:b2d48e11c9061cfe:0",
            "sub_ring": "equipped:b9b34c02a13b6580:0",
        }
        shared = tuple(
            (slot, OwnedEquipment(item_id, InventoryItem(
                slot=slot, name=slot, count=1, tval=0, sval=0,
                aware=True, known=True, fully_known=True, is_equipment=True,
            ), "equipped"))
            for slot, item_id in shared_ids.items()
        )
        inputs = WarriorLoadoutInputs(
            WarriorCombatInputs(50, 180, 180, 175),
            WarriorDefenseInputs(50, 180, base_speed=109),
            1000,
        )

        def entry(item_id, bonus, ac, old_survival, damage):
            boots = OwnedEquipment(item_id, InventoryItem(
                slot="feet", name=item_id, count=1, tval=30, sval=1,
                aware=True, known=True, fully_known=True, is_equipment=True,
                ac=2, to_a=ac - 2, pval=bonus,
                known_flags=frozenset({12}),
            ), "home" if bonus == 4 else "equipped")
            loadout = Loadout(shared + (("feet", boots),), "weapon-shield")
            melee = WarriorMeleeResult(
                180, 180, 37, 37,
                (HandMeleeResult(1, 0, 0, 0, 1.0, damage),),
                1000.0,
            )
            # The report's old denominator was unadjusted incoming damage.
            raw_incoming = 1000 / old_survival
            defense = WarriorDefenseResult(
                ac, raw_incoming, frozenset(),
                energy_weighted_melee_damage=raw_incoming * speed_energy(110),
            )
            ranged = WarriorRangedDefenseResult(0.0)
            result = _combine_warrior_results(loadout, inputs, melee, defense, ranged)
            return EvaluatedLoadout(loadout, result.metrics)

        current = entry(
            "equipped:33d89c1cd5b84647:0", 1, 110,
            30.19261321365014, 146.14683051692245,
        )
        vearfana = entry(
            "home:88e6d9b556672fc9:0", 4, 109,
            29.958847475659713, 197.77917357988827,
        )
        self.assertGreater(current.metrics.survival_turns, 30.0)
        self.assertGreater(vearfana.metrics.survival_turns, current.metrics.survival_turns)
        self.assertEqual(
            _stable_operational_best((current, vearfana), current.loadout.item_ids),
            vearfana,
        )

        # Without the +3 speed difference, the old 30-turn boundary still
        # excludes the lower-AC boots, despite their higher damage.
        neutral = entry(
            "home:88e6d9b556672fc9:0", 1, 109,
            29.958847475659713, 197.77917357988827,
        )
        self.assertLess(neutral.metrics.survival_turns, 30.0)
        self.assertEqual(
            _stable_operational_best((current, neutral), current.loadout.item_ids),
            current,
        )

    def test_monster_energy_scales_incoming_per_player_turn(self):
        race = MonraceKnowledge(
            max_hp=100, average_hp=100, speed=120, can_summon=False,
            friendly=False, level=20, spell_frequency=20,
            flags=frozenset({"STUPID"}), abilities=frozenset({"BR_FIRE"}),
            blows=(MonsterBlow("HIT", "HURT", 2, 6),),
        )
        inputs = self.inputs()
        result = evaluate_warrior_loadout(
            Loadout((), "empty"), inputs, (EncounterTarget(1, 1.0, race),),
        )
        self.assertAlmostEqual(
            result.metrics.survival_turns,
            100 / ((result.defense.expected_melee_damage
                    + result.ranged.expected_ranged_damage) * 20 / 10),
        )
        self.assertGreater(result.ranged.expected_ranged_damage, 0)

    def inputs(self, hp=100):
        return WarriorLoadoutInputs(
            WarriorCombatInputs(
                level=20, natural_str=18, natural_dex=18, melee_skill=60
            ),
            WarriorDefenseInputs(
                level=20, natural_dex=18, saving_skill=40
            ),
            hp,
        )

    def ring(self, flags):
        item = InventoryItem(
            slot="a", name="ring", count=1, tval=45, sval=1,
            aware=True, known=True, fully_known=True, is_equipment=True,
            known_flags=frozenset(flags),
        )
        return OwnedEquipment("ring", item, "home")

    def launcher(self, item_id, sval, *, to_h, to_d, weight):
        item = InventoryItem(
            slot="a", name=item_id, count=1, tval=19, sval=sval,
            aware=True, known=True, fully_known=True, is_equipment=True,
            to_h=to_h, to_d=to_d, weight=weight, weapon_proficiency=4000,
        )
        return OwnedEquipment(item_id, item, "home")

    def test_store_ammo_ranged_dps_prefers_light_xbow_over_current_short_bow(self):
        inputs = WarriorCombatInputs(
            level=25, natural_str=170, natural_dex=68,
            melee_skill=175, shooting_skill=70,
        )
        short = Loadout((("bow", self.launcher(
            "short", 12, to_h=3, to_d=5, weight=30
        )),), "empty")
        light_xbow = Loadout((("bow", self.launcher(
            "light-xbow", 23, to_h=4, to_d=3, weight=110
        )),), "empty")

        self.assertGreater(
            warrior_ranged_offense_dps(light_xbow, inputs),
            warrior_ranged_offense_dps(short, inputs),
        )

    def test_combines_melee_and_ranged_incoming_damage(self):
        race = MonraceKnowledge(
            max_hp=100, average_hp=100, speed=110, can_summon=False,
            friendly=False, level=20, spell_frequency=20,
            flags=frozenset({"STUPID"}), abilities=frozenset({"BR_FIRE"}),
            blows=(MonsterBlow("HIT", "HURT", 1, 6),),
        )
        result = evaluate_warrior_loadout(
            Loadout((), "empty"), self.inputs(),
            (EncounterTarget(1, 1.0, race),),
        )
        incoming = (
            result.defense.expected_melee_damage
            + result.ranged.expected_ranged_damage
        )
        self.assertAlmostEqual(result.metrics.survival_turns, 100 / incoming)
        self.assertTrue(result.metrics.evaluation_complete)

    def test_loadout_hp_tracks_constitution_pval(self):
        helm_item = InventoryItem(
            slot="head", name="stat helm", count=1, tval=33, sval=1,
            aware=True, known=True, fully_known=True, is_equipment=True,
            pval=3, known_flags=frozenset({4}),
        )
        helm = OwnedEquipment("stat-helm", helm_item, "equipped")
        inputs = WarriorLoadoutInputs(
            WarriorCombatInputs(
                level=25, natural_str=140, natural_dex=38, melee_skill=175
            ),
            WarriorDefenseInputs(level=25, natural_dex=38),
            current_hp=583,
            natural_con=180,
            base_hp=365,
        )

        self.assertEqual(loadout_max_hp(Loadout((), "empty"), inputs), 583)
        self.assertEqual(
            loadout_max_hp(Loadout((("head", helm),), "empty"), inputs),
            627,
        )

    def test_smart_selection_context_fails_closed(self):
        race = MonraceKnowledge(
            max_hp=100, average_hp=100, speed=110, can_summon=False,
            friendly=False, level=20, spell_frequency=20,
            abilities=frozenset({"BR_FIRE"}),
        )
        result = evaluate_warrior_loadout(
            Loadout((), "empty"), self.inputs(),
            (EncounterTarget(1, 1.0, race),),
        )
        self.assertFalse(result.metrics.evaluation_complete)

    def test_explicit_smart_selection_context_completes_metrics(self):
        race = MonraceKnowledge(
            max_hp=100, average_hp=100, speed=110, can_summon=False,
            friendly=False, level=20, spell_frequency=20,
            abilities=frozenset({"BR_FIRE"}),
        )
        inputs = WarriorLoadoutInputs(
            self.inputs().combat,
            self.inputs().defense,
            100,
            SpellSelectionContext(),
        )
        result = evaluate_warrior_loadout(
            Loadout((), "empty"), inputs,
            (EncounterTarget(1, 1.0, race),),
        )
        self.assertTrue(result.metrics.evaluation_complete)

    def test_no_offense_is_never_nan(self):
        result = evaluate_warrior_loadout(
            Loadout((), "empty"), self.inputs(), ()
        )
        self.assertEqual(result.metrics.combat_margin, -float("inf"))

    def test_confusion_resistance_improves_secondary_risk_value(self):
        race = MonraceKnowledge(
            max_hp=600, average_hp=600, speed=110, can_summon=False,
            friendly=False, level=30, spell_frequency=50,
            abilities=frozenset({"BR_CONF"}),
        )
        inputs = WarriorLoadoutInputs(
            self.inputs().combat,
            self.inputs().defense,
            100,
            SpellSelectionContext(),
        )
        encounter = (EncounterTarget(1, 1.0, race),)
        plain = evaluate_warrior_loadout(Loadout((), "empty"), inputs, encounter)
        resistant = evaluate_warrior_loadout(
            Loadout((("main_ring", self.ring({57})),), "empty"),
            inputs,
            encounter,
        )
        self.assertGreater(
            resistant.metrics.secondary_value,
            plain.metrics.secondary_value,
        )

    def test_component_cache_reuses_equivalent_loadout_inputs(self):
        first = self.ring({57})
        duplicate = OwnedEquipment("duplicate", first.item, "home")
        first_loadout = Loadout((("main_ring", first),), "empty")
        duplicate_loadout = Loadout((("main_ring", duplicate),), "empty")
        evaluator = CachedWarriorLoadoutEvaluator(self.inputs(), ())

        first_result = evaluator(first_loadout)
        duplicate_result = evaluator(duplicate_loadout)

        self.assertEqual(first_result.metrics, duplicate_result.metrics)
        self.assertEqual(evaluator.cache_sizes, (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
