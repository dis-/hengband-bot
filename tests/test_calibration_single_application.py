import tests  # noqa: F401
import unittest

from hengbot.equipment_optimizer import Loadout, OwnedEquipment
from hengbot.model import InventoryItem
from hengbot.warrior_equipment_evaluator import WarriorCombatInputs, evaluate_warrior_melee
from hengbot.warrior_defense_evaluator import WarriorDefenseInputs, loadout_armor_class
from hengbot.warrior_loadout_evaluator import WarriorLoadoutInputs, loadout_max_hp


class SingleApplicationTest(unittest.TestCase):
    def test_mixed_sign_across_eighteen(self):
        item = InventoryItem(slot="main_ring", name="stats", count=1, tval=45,
                             sval=0, aware=True, known=True, fully_known=True,
                             is_equipment=True, pval=1, known_flags=frozenset({0, 3, 4}))
        loadout = Loadout((("main_ring", OwnedEquipment("ring", item, "pack")),), "single")
        combat = WarriorCombatInputs(28, 23, 23, 100,
                                     intrinsic_str=-1, intrinsic_dex=-1)
        result = evaluate_warrior_melee(loadout, combat)
        self.assertEqual((result.stat_str, result.stat_dex), (23, 23))
        defense = WarriorDefenseInputs(28, 23, intrinsic_dex=-1)
        self.assertEqual(loadout_armor_class(loadout, defense), 2)
        inputs = WarriorLoadoutInputs(combat, defense, 100, natural_con=23,
                                      intrinsic_con=-1, base_hp=10, hp_floor=29)
        self.assertEqual(loadout_max_hp(loadout, inputs), 38)


if __name__ == "__main__":
    unittest.main()
