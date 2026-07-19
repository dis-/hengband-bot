import unittest

from hengbot.equipment_encounters import EncounterTarget
from hengbot.equipment_optimizer import Loadout, OwnedEquipment
from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.monster_ranged_evaluator import SpellSelectionContext
from hengbot.warrior_defense_evaluator import WarriorDefenseInputs
from hengbot.warrior_equipment_evaluator import WarriorCombatInputs
from hengbot.warrior_loadout_evaluator import (
    CachedWarriorLoadoutEvaluator,
    WarriorLoadoutInputs,
    evaluate_warrior_loadout,
    warrior_ranged_offense_dps,
)


class WarriorLoadoutEvaluatorTest(unittest.TestCase):
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
