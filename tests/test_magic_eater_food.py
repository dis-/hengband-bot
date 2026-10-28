import tests  # noqa: F401 -- runtime-file isolation

from dataclasses import replace
import unittest

from hengbot.magic_eater_devices import is_absorption_device
from hengbot.model import (
    Position, Snapshot, TVAL_FOOD, TVAL_ROD, TVAL_STAFF, TVAL_WAND,
    SV_STAFF_IDENTIFY,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import MANA_FOOD_CHARGE_TARGET, WAIT_KEY
from policy_fixtures import grid, item, player


class MagicEaterFoodTest(unittest.TestCase):
    def board(self, *devices, class_id=16, food=1500):
        return Snapshot(
            player(10, 10, food=food, food_type=4, class_id=class_id),
            {Position(10, 10): grid(10, 10)}, [],
            inventory=list(devices), town_flag=True, town_id=999,
        )

    def missile(self):
        return item("a", TVAL_WAND, 15, charges=30, name="Magic Missile wand")

    def nothing(self, *, count=1, charges=20):
        return item("b", TVAL_STAFF, 32, charges=charges, count=count,
                    name="Staff of Nothing")

    def test_hungry_magic_eater_eats_other_device_instead_of_magic_missile(self):
        board = self.board(self.missile(), self.nothing())
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(board), "Eb")
        self.assertEqual(policy.last_reason, "survival:mana-absorb")

    def test_magic_missile_alone_takes_existing_no_food_path(self):
        for food in (1500, 750, 400):
            with self.subTest(food=food):
                policy = HengbotPolicy()
                self.assertEqual(policy.choose_key(self.board(self.missile(), food=food)), WAIT_KEY)
                self.assertEqual(policy.last_reason, "town:blocked:survival-mana-no-charges")

    def test_unknown_device_is_still_food_for_magic_eater(self):
        unknown = item("c", TVAL_WAND, 0, aware=False)
        self.assertEqual(HengbotPolicy().choose_key(self.board(self.missile(), unknown)), "Ec")

    def test_warrior_still_eats_highest_charge_wand(self):
        self.assertEqual(HengbotPolicy().choose_key(
            self.board(self.missile(), self.nothing(), class_id=0)), "Ea")

    def test_absorption_inventory_never_counts_toward_food_target(self):
        identify = item("i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=10)
        for food in (12000, 1500, 750, 400):
            with self.subTest(food=food):
                board = self.board(self.missile(), identify, food=food)
                policy = HengbotPolicy()
                self.assertEqual(policy._count_mana_food_devices(board), 0)
                self.assertEqual(policy._count_mana_food_uses(board), 0)
                self.assertEqual(policy._supply_ledger(board, 1)["food"].count, 0)

    def test_protected_wand_does_not_satisfy_second_food_device(self):
        policy = HengbotPolicy()
        board = self.board(self.missile(), self.nothing(), food=12000)
        self.assertEqual(policy._count_mana_food_devices(board), 1)
        self.assertEqual(policy._count_mana_food_uses(board), 20)
        self.assertEqual(policy._supply_ledger(board, 1)["food"].count,
                         MANA_FOOD_CHARGE_TARGET - 1)
        two_food = replace(board, inventory=[self.missile(), self.nothing(count=2)])
        self.assertEqual(policy._count_mana_food_devices(two_food), 2)
        self.assertEqual(policy._count_mana_food_uses(two_food), 40)
        self.assertEqual(policy._supply_ledger(two_food, 1)["food"].count,
                         MANA_FOOD_CHARGE_TARGET)

    def test_absorption_predicate_matches_identification_and_device_kinds(self):
        devices = [self.missile(), item("s", TVAL_STAFF, SV_STAFF_IDENTIFY),
                   item("r", TVAL_ROD, 1)]
        for device in devices:
            with self.subTest(tval=device.tval):
                self.assertTrue(is_absorption_device(16, device))
                self.assertFalse(is_absorption_device(0, device))
                self.assertFalse(is_absorption_device(-1, device))
                self.assertFalse(is_absorption_device(16, replace(device, known=False)))
        self.assertFalse(is_absorption_device(16, self.nothing()))
        self.assertFalse(is_absorption_device(16, item("f", TVAL_FOOD, 35)))
        # Charging and drained devices are still planned absorption stock.
        self.assertTrue(is_absorption_device(16, replace(devices[-1], charging=True)))
        self.assertTrue(is_absorption_device(16, replace(self.missile(), charges=0)))


if __name__ == "__main__":
    unittest.main()
