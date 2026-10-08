"""Part B pins for non-ego jewelry scope and stable fallback ordering.

J includes only non-ego magical jewelry. The recorded line-724 catalogue
selects 44 J-D sales; the branch-local pin was corrected to that scope.
"""
import tests  # noqa: F401
from dataclasses import replace
import unittest

from hengbot.equipment_optimizer import OwnedEquipment
from hengbot.equipment_sale_classifier import (
    EquipmentSaleClassification, equipment_sale_fallback_order,
    equipment_sale_plan, equipment_sale_scope,
)
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

    def test_fallback_order_is_lowest_performance_then_stable_id(self):
        result = EquipmentSaleClassification(
            sold_ids=frozenset({"already-selected"}), pareto_ids=frozenset(),
            needs_identification_ids=frozenset(), reasons={}, dominators={},
            performance={"z": (1.0, 4.0), "b": (1.0, 2.0), "a": (1.0, 2.0)},
            eligible_ids=frozenset({"already-selected", "z", "b", "a", "protected"}),
            ranks={"already-selected": 11, "z": 12, "b": 13, "a": 14,
                   "protected": 1},
        )
        self.assertEqual(
            equipment_sale_fallback_order(result, excluded_ids=frozenset({"protected"})),
            ("a", "b", "z"),
        )
        self.assertEqual(
            equipment_sale_plan(
                result, home_ids=frozenset({"already-selected", "a", "b", "z"}),
                free_home_slots=0, target_free_slots=3,
            ),
            ("already-selected", "a", "b"),
        )

    def test_rank_21_is_always_sold_and_top_10_is_never_sold(self):
        result = EquipmentSaleClassification(
            sold_ids=frozenset({"rank-10", "rank-11"}), pareto_ids=frozenset(),
            needs_identification_ids=frozenset(), reasons={}, dominators={},
            performance={"rank-10": (10, 0), "rank-11": (9, 0),
                         "rank-21": (1, 0), "protected-rank-22": (0, 0)},
            eligible_ids=frozenset({"rank-10", "rank-11", "rank-21"}),
            ranks={"rank-10": 10, "rank-11": 11, "rank-21": 21,
                   "protected-rank-22": 22},
        )
        self.assertEqual(
            equipment_sale_plan(result, home_ids=frozenset(
                                    (*result.eligible_ids, "protected-rank-22")),
                                free_home_slots=30, target_free_slots=20),
            ("rank-11", "rank-21"),
        )
        self.assertEqual(
            equipment_sale_plan(result, home_ids=frozenset(
                                    (*result.eligible_ids, "protected-rank-22")),
                                free_home_slots=0, target_free_slots=20),
            ("rank-11", "rank-21"),
        )


if __name__ == "__main__":
    unittest.main()
