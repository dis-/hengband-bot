import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest

from hengbot.equipment_optimizer import Loadout, OwnedEquipment, equipment_identity
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
            [
                ("takeoff", "old", "main_hand"),
                ("equip", "best", "main_hand"),
            ],
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

    def test_oscillation_stops_by_retaining_restoration_owned_body_item(self):
        armour = gear("equipped:523d457d37cb5b14:0", "equipped", tval=36)
        current = Loadout((("body", armour),), "empty")
        plan = plan_equipment_transactions(
            (armour,), current, Loadout((), "empty"),
            current_pack_items=0, home_scan_complete=True,
            preserve_pack_item_ids=frozenset({armour.id}),
        )

        self.assertEqual(plan.actions, ())
        self.assertEqual(dict(current.slots)["body"].id, armour.id)

    def test_stages_target_items_when_the_all_at_once_prefix_would_overflow(self):
        targets = tuple(gear(f"target-{index}", "home", tval=45) for index in range(2))
        target = Loadout(
            (("main_ring", targets[0]), ("sub_ring", targets[1])), "empty"
        )
        plan = plan_equipment_transactions(
            targets, Loadout((), "empty"), target,
            current_pack_items=22, home_scan_complete=True,
        )
        self.assertEqual(plan.blockers, ())
        self.assertEqual(
            [(action.kind, action.item_id) for action in plan.actions],
            [
                ("withdraw", "target-0"), ("equip", "target-0"),
                ("withdraw", "target-1"), ("equip", "target-1"),
            ],
        )

    def test_home_full_still_allows_a_fitting_staged_step(self):
        old = gear("old", "equipped")
        target = gear("home-target", "home")
        plan = plan_equipment_transactions(
            (old, target),
            Loadout((("main_hand", old),), "one_handed"),
            Loadout((("main_hand", target),), "one_handed"),
            current_pack_items=21,
            home_scan_complete=True,
            home_deposit_available=False,
        )

        # A full Home changes only the space accounting.  The deposit of the
        # replaced item stays planned: its refusal is the step-1.5a record.
        self.assertEqual(plan.blockers, ())
        self.assertEqual(
            [(action.kind, action.item_id) for action in plan.actions],
            [("withdraw", "home-target"), ("takeoff", "old"),
             ("equip", "home-target"), ("deposit", "old")],
        )

    def test_staged_slots_stay_worn_until_the_replacement_is_carried(self):
        old = [gear(f"old-{index}", "equipped", tval=45) for index in range(2)]
        new = [gear(f"new-{index}", "home", tval=45) for index in range(2)]
        plan = plan_equipment_transactions(
            (*old, *new),
            Loadout((("main_ring", old[0]), ("sub_ring", old[1])), "empty"),
            Loadout((("main_ring", new[0]), ("sub_ring", new[1])), "empty"),
            current_pack_items=21,
            home_scan_complete=True,
        )

        self.assertEqual(plan.blockers, ())
        kinds = [action.kind for action in plan.actions]
        self.assertEqual(
            kinds, ["withdraw", "takeoff", "equip", "deposit"] * 2
        )
        self.assertLessEqual(plan.peak_pack_items, 23)
        self.assertEqual(
            sorted(action.item_id for action in plan.actions if action.kind == "equip"),
            ["new-0", "new-1"],
        )
        self.assertEqual(
            sorted(action.item_id for action in plan.actions if action.kind == "deposit"),
            ["old-0", "old-1"],
        )
        # Staging reorders the unstaged plan; it never adds or drops a step,
        # so the resulting loadout is the same target.
        unstaged = plan_equipment_transactions(
            (*old, *new),
            Loadout((("main_ring", old[0]), ("sub_ring", old[1])), "empty"),
            Loadout((("main_ring", new[0]), ("sub_ring", new[1])), "empty"),
            current_pack_items=21,
            home_scan_complete=True,
            pack_capacity=99,
        )
        self.assertEqual(
            [action.phase for action in unstaged.actions],
            [PHASE_HOME_PREPARE] * 2 + [PHASE_EQUIP] * 4 + [PHASE_HOME_FINALIZE] * 2,
        )
        self.assertEqual(set(plan.actions), set(unstaged.actions))
        self.assertEqual(len(plan.actions), len(unstaged.actions))

    def test_deposit_first_order_only_when_in_place_does_not_fit(self):
        old = gear("old", "equipped")
        target = gear("home-target", "home")
        arguments = dict(
            current_pack_items=22,
            home_scan_complete=True,
        )
        plan = plan_equipment_transactions(
            (old, target),
            Loadout((("main_hand", old),), "one_handed"),
            Loadout((("main_hand", target),), "one_handed"),
            **arguments,
        )

        self.assertEqual(plan.blockers, ())
        self.assertEqual(
            [(action.kind, action.item_id) for action in plan.actions],
            [("takeoff", "old"), ("deposit", "old"),
             ("withdraw", "home-target"), ("equip", "home-target")],
        )
        self.assertEqual(plan.peak_pack_items, 23)

        # A full Home cannot free the slot first: the blocker stays visible.
        full = plan_equipment_transactions(
            (old, target),
            Loadout((("main_hand", old),), "one_handed"),
            Loadout((("main_hand", target),), "one_handed"),
            home_deposit_available=False,
            **arguments,
        )
        self.assertEqual(full.blockers, ("pack-space-required:1",))

    def test_pack_blocker_remains_when_no_single_staged_step_fits(self):
        old = gear("old", "equipped")
        target = gear("home-target", "home")
        plan = plan_equipment_transactions(
            (old, target),
            Loadout((("main_hand", old),), "one_handed"),
            Loadout((("main_hand", target),), "one_handed"),
            current_pack_items=23,
            home_scan_complete=True,
            home_deposit_available=False,
        )

        self.assertTrue(any(
            blocker.startswith("pack-space-required:")
            for blocker in plan.blockers
        ))

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
                ("takeoff", "old", "main_hand"),
                ("equip", "two-handed", "main_hand"),
            ],
        )

    def test_takes_off_occupied_sub_hand_before_home_shield_swap(self):
        weapon = gear("off-hand-weapon", "equipped")
        shield = gear("home-shield", "home", tval=34)
        plan = plan_equipment_transactions(
            (weapon, shield),
            Loadout((("sub_hand", weapon),), "dual_wield"),
            Loadout((("sub_hand", shield),), "weapon_shield"),
            current_pack_items=0,
            home_scan_complete=True,
        )

        self.assertEqual(
            [(action.kind, action.item_id, action.target_slot)
             for action in plan.actions],
            [
                ("withdraw", "home-shield", None),
                ("takeoff", "off-hand-weapon", "sub_hand"),
                ("equip", "home-shield", "sub_hand"),
                ("deposit", "off-hand-weapon", None),
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

    def test_retained_displaced_digger_stays_in_pack_without_final_deposit(self):
        digger = gear("equipped:3de78ae78c7ba624:0", "equipped")
        sword = gear("pack:sword:0", "pack")
        plan = plan_equipment_transactions(
            (digger, sword),
            Loadout((("main_hand", digger),), "one_handed"),
            Loadout((("main_hand", sword),), "one_handed"),
            current_pack_items=1,
            home_scan_complete=True,
            preserve_pack_item_ids=frozenset({sword.id}),
            retain_item_identities=frozenset({equipment_identity(digger.item)}),
        )

        self.assertEqual(
            [(action.kind, action.item_id) for action in plan.actions],
            [("takeoff", digger.id), ("equip", sword.id)],
        )
        self.assertEqual(plan.peak_pack_items, 2)

    def test_retained_displaced_launcher_uses_identity_not_origin_id(self):
        bow = gear("equipped:73244d56c331ef37:0", "equipped", tval=19)
        plan = plan_equipment_transactions(
            (bow,),
            Loadout((("bow", bow),), "empty"),
            Loadout((), "empty"),
            current_pack_items=0,
            home_scan_complete=True,
            retain_item_identities=frozenset({equipment_identity(bow.item)}),
        )

        self.assertEqual([action.kind for action in plan.actions], ["takeoff"])
        self.assertEqual(plan.phase(PHASE_HOME_FINALIZE), ())

    def test_retained_displaced_item_still_consumes_peak_pack_space(self):
        bow = gear("equipped:73244d56c331ef37:0", "equipped", tval=19)
        plan = plan_equipment_transactions(
            (bow,),
            Loadout((("bow", bow),), "empty"),
            Loadout((), "empty"),
            current_pack_items=23,
            home_scan_complete=True,
            retain_item_identities=frozenset({equipment_identity(bow.item)}),
        )

        self.assertEqual(plan.peak_pack_items, 24)
        self.assertIn("pack-space-required:1", plan.blockers)


if __name__ == "__main__":
    unittest.main()
