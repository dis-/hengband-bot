"""Part B scope pin: DECLARED CONSTRUCTED magical ego jewelry.

J includes only non-ego magical jewelry. Existing recorded sale-count
expectations remain untouched so the task's contradictory 45 pin is visible.
"""
import tests  # noqa: F401
from dataclasses import replace
import unittest

from hengbot.equipment_optimizer import OwnedEquipment
from hengbot.equipment_sale_classifier import equipment_sale_scope
from hengbot.model import InventoryItem


class EquipmentSaleScopeB(unittest.TestCase):
    def test_j_excludes_ego_magical_jewelry(self):
        for tval in (40, 45):
            with self.subTest(tval=tval):
                item = InventoryItem("a", "constructed magic jewelry", 1,
                                     tval, 1, True, True, fully_known=True,
                                     is_equipment=True, known_flags=frozenset({62}))
                self.assertTrue(equipment_sale_scope(OwnedEquipment("plain", item, "home"), "J"))
                self.assertFalse(equipment_sale_scope(
                    OwnedEquipment("ego", replace(item, is_ego=True), "home"), "J"))


if __name__ == "__main__":
    unittest.main()
