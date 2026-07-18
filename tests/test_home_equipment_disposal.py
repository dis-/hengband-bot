from dataclasses import replace
from unittest.mock import patch
import unittest

from hengbot.model import PLAYER_CLASS_WARRIOR, STORE_HOME, STORE_WEAPON, TVAL_SWORD, StoreState
from hengbot.policy import HengbotPolicy
from tests.test_policy import Position, Snapshot, grid, item, player, store_item


class HomeEquipmentDisposalTest(unittest.TestCase):
    @staticmethod
    def sword(letter, name, to_d):
        return store_item(
            letter, TVAL_SWORD, 1, name=name, known=True, fully_known=True,
            is_equipment=True, to_d=to_d, damage_dice_num=2,
            damage_dice_sides=5,
        )

    @staticmethod
    def snapshot(items):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            store=StoreState(store_type=STORE_HOME, items=items), town_flag=True,
        )

    def test_capacity_two_sword_withdraws_and_routes_to_weapon_smith(self):
        home = self.snapshot([
            self.sword("a", "strong sword one", 5),
            self.sword("b", "strong sword two", 4),
            self.sword("c", "weak sword", 1),
        ])
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page(home.store.items)
        policy._home_disposal_pass = True
        self.assertEqual(policy._home_dominated_disposal_key(home), "pc\r")

        carried = item(
            "d", TVAL_SWORD, 1, name="weak sword", known=True,
            fully_known=True, is_equipment=True, to_d=1, damage_dice_num=2,
            damage_dice_sides=5,
        )
        outside = replace(home, inventory=[carried], store=None)
        self.assertIn(
            STORE_WEAPON,
            [need.store_type for need in policy._enumerate_town_needs(outside)],
        )
        smith = replace(outside, store=StoreState(store_type=STORE_WEAPON, items=[]))
        self.assertEqual(policy.choose_key(smith), "dd\r")

    def test_unknown_cursed_and_reserved_items_are_not_disposable(self):
        strong = store_item(
            "a", 37, 1, name="strong", known=True, fully_known=True,
            is_equipment=True, ac=5, to_a=5,
        )
        unknown = store_item("b", 37, 1, name="unknown", known=False, is_equipment=True)
        cursed = store_item(
            "c", 37, 1, name="cursed", known=True, fully_known=True,
            is_equipment=True, is_cursed=True,
        )
        reserved = store_item(
            "d", 37, 1, name="reserved", known=True, fully_known=True,
            is_equipment=True, ac=1,
        )
        snap = self.snapshot([strong, unknown, cursed, reserved])
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page(snap.store.items)
        self.assertFalse(policy._is_disposable_dominated_armour(snap, unknown))
        self.assertFalse(policy._is_disposable_dominated_armour(snap, cursed))
        with patch.object(
            policy, "_equipment_disposal_reserved",
            side_effect=lambda _snapshot, candidate: candidate.name == "reserved",
        ):
            self.assertFalse(policy._is_disposable_dominated_armour(snap, reserved))

    def test_unsellable_dominated_item_falls_back_to_destroy(self):
        target = item("a", TVAL_SWORD, 1, name="refused sword", known=True, fully_known=True, is_equipment=True)
        snap = replace(self.snapshot([]), inventory=[target], store=None)
        policy = HengbotPolicy()
        policy._pending_disposal_slot = "a"
        policy._pending_disposal_item = policy._item_signature(target)
        self.assertEqual(policy._dominated_disposal_store(target), STORE_WEAPON)
        policy._disposal_store_attempts.add(STORE_WEAPON)
        policy._destroy_pending = True
        self.assertEqual(policy._town_destroy_key(snap), "01ka")


if __name__ == "__main__":
    unittest.main()
