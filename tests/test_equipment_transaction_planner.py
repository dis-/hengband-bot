import unittest

from hengbot.equipment_optimizer import Loadout, OwnedEquipment
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    PHASE_HOME_FINALIZE,
    PHASE_HOME_PREPARE,
    plan_equipment_transactions,
)
from hengbot.model import InventoryItem


def gear(item_id, origin, *, tval=23, flags=(), cursed=False):
    item = InventoryItem(
        slot=item_id, name=item_id, count=1, tval=tval, sval=1,
        aware=True, known=True, fully_known=True, is_equipment=True,
        is_cursed=cursed, known_flags=frozenset(flags),
    )
    return OwnedEquipment(item_id, item, origin)


class EquipmentTransactionPlannerTest(unittest.TestCase):
    def test_batches_pack_deposit_home_withdraw_equip_and_final_deposit(self):
        old = gear("old", "equipped")
        spare = gear("spare", "pack")
        best = gear("best", "home")
        current = Loadout((("main_hand", old),), "one_handed")
        target = Loadout((("main_hand", best),), "one_handed")
        plan = plan_equipment_transactions(
            (old, spare, best), current, target,
            current_pack_items=5, home_scan_complete=True,
        )
        self.assertTrue(plan.executable)
        self.assertEqual(
            [(action.kind, action.item_id) for action in plan.phase(PHASE_HOME_PREPARE)],
            [("deposit", "spare"), ("withdraw", "best")],
        )
        self.assertEqual(
            [(action.kind, action.item_id, action.target_slot)
             for action in plan.phase(PHASE_EQUIP)],
            [("equip", "best", "main_hand")],
        )
        self.assertEqual(
            [(action.kind, action.item_id) for action in plan.phase(PHASE_HOME_FINALIZE)],
            [("deposit", "old")],
        )

    def test_home_target_requires_complete_scan(self):
        best = gear("best", "home")
        plan = plan_equipment_transactions(
            (best,), Loadout((), "empty"),
            Loadout((("main_hand", best),), "one_handed"),
            current_pack_items=0, home_scan_complete=False,
        )
        self.assertIn("home-scan-incomplete", plan.blockers)

    def test_pack_capacity_accounts_for_deposits_before_withdrawals(self):
        spares = tuple(gear(f"spare-{index}", "pack") for index in range(3))
        targets = tuple(gear(f"target-{index}", "home", tval=45) for index in range(2))
        target = Loadout(
            (("main_ring", targets[0]), ("sub_ring", targets[1])), "empty"
        )
        plan = plan_equipment_transactions(
            (*spares, *targets), Loadout((), "empty"), target,
            current_pack_items=23, home_scan_complete=True,
        )
        self.assertTrue(plan.executable)
        self.assertEqual(plan.peak_pack_items, 22)

    def test_preserves_required_pack_equipment(self):
        digging_tool = gear("digging-tool", "pack")
        spare = gear("spare", "pack")
        plan = plan_equipment_transactions(
            (digging_tool, spare), Loadout((), "empty"), Loadout((), "empty"),
            current_pack_items=2, home_scan_complete=True,
            preserve_pack_item_ids=frozenset({"digging-tool"}),
        )
        self.assertEqual(
            [(action.kind, action.item_id)
             for action in plan.phase(PHASE_HOME_PREPARE)],
            [("deposit", "spare")],
        )

    def test_reports_pack_space_when_non_equipment_consumables_fill_pack(self):
        targets = tuple(gear(f"target-{index}", "home", tval=45) for index in range(2))
        target = Loadout(
            (("main_ring", targets[0]), ("sub_ring", targets[1])), "empty"
        )
        plan = plan_equipment_transactions(
            targets, Loadout((), "empty"), target,
            current_pack_items=22, home_scan_complete=True,
        )
        self.assertIn("pack-space-required:1", plan.blockers)

    def test_cursed_changed_equipment_blocks_plan(self):
        cursed = gear("cursed", "equipped", cursed=True)
        best = gear("best", "pack")
        plan = plan_equipment_transactions(
            (cursed, best),
            Loadout((("main_hand", cursed),), "one_handed"),
            Loadout((("main_hand", best),), "one_handed"),
            current_pack_items=1, home_scan_complete=True,
        )
        self.assertIn("cursed-equipped:cursed", plan.blockers)

    def test_repositions_an_already_equipped_item(self):
        weapon = gear("weapon", "equipped")
        plan = plan_equipment_transactions(
            (weapon,),
            Loadout((("sub_hand", weapon),), "dual_wield"),
            Loadout((("main_hand", weapon),), "one_handed"),
            current_pack_items=0, home_scan_complete=True,
        )
        self.assertEqual(
            [action.kind for action in plan.phase(PHASE_EQUIP)],
            ["takeoff", "reposition"],
        )

    def test_takes_off_shield_before_equipping_two_handed_weapon(self):
        old = gear("old", "equipped")
        shield = gear("shield", "equipped", tval=34)
        two_handed = gear("two-handed", "pack", tval=22)
        plan = plan_equipment_transactions(
            (old, shield, two_handed),
            Loadout(
                (("main_hand", old), ("sub_hand", shield)),
                "weapon_shield",
            ),
            Loadout((("main_hand", two_handed),), "two_handed"),
            current_pack_items=1,
            home_scan_complete=True,
        )
        self.assertEqual(
            [(action.kind, action.item_id, action.target_slot)
             for action in plan.phase(PHASE_EQUIP)],
            [
                ("takeoff", "shield", "sub_hand"),
                ("equip", "two-handed", "main_hand"),
            ],
        )

    def test_takes_off_equipment_when_target_slot_is_empty(self):
        cloak = gear("cloak", "equipped", tval=35)
        plan = plan_equipment_transactions(
            (cloak,), Loadout((("outer", cloak),), "empty"),
            Loadout((), "empty"), current_pack_items=0,
            home_scan_complete=True,
        )
        self.assertEqual(plan.phase(PHASE_EQUIP)[0].kind, "takeoff")

    def test_pack_capacity_includes_temporary_takeoff_items(self):
        shield = gear("shield", "equipped", tval=34)
        plan = plan_equipment_transactions(
            (shield,), Loadout((("sub_hand", shield),), "empty"),
            Loadout((), "empty"), current_pack_items=23,
            home_scan_complete=True,
        )
        self.assertEqual(plan.peak_pack_items, 24)
        self.assertIn("pack-space-required:1", plan.blockers)


if __name__ == "__main__":
    unittest.main()
