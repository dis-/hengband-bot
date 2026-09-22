import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest

from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    PHASE_HOME_PREPARE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import (
    EquipmentTransactionObservation,
    EquipmentTransactionSession,
    observe_equipment_transactions,
)
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.model import (
    STORE_HOME,
    InventoryItem,
    PlayerState,
    Position,
    Snapshot,
    StoreState,
)


def observation(*, home, pack=(), equipped=(), shelved=(), generation=None,
                outcome=None):
    return EquipmentTransactionObservation.create(
        in_home=home,
        pack_identities=pack,
        equipped_identities=equipped,
        home_identities=shelved,
        barrier_generation=generation,
        operation_outcome=outcome,
    )


class EquipmentTransactionSessionTest(unittest.TestCase):
    @staticmethod
    def _stack_snapshot(count):
        bolts = InventoryItem(
            "a", "incident bolts", count, 18, 1, True, True,
            fully_known=True, is_equipment=True, damage_dice_num=1,
            damage_dice_sides=5,
        )
        return Snapshot(
            PlayerState(Position(1, 1), 100, 100, 0, 0, 26),
            {}, [], inventory=[bolts], store=StoreState(STORE_HOME),
        )

    def test_real_snapshot_partial_withdraw_merges_into_existing_stack(self):
        target = InventoryItem(
            "b", "incident bolts", 96, 18, 1, True, True,
            fully_known=True, is_equipment=True, damage_dice_num=1,
            damage_dice_sides=5,
        )
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", "home:incident:0",
            item_identity=equipment_identity(target),
            move_identity=equipment_move_identity(target),
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        before = observe_equipment_transactions(self._stack_snapshot(95))
        after = observe_equipment_transactions(self._stack_snapshot(99))

        self.assertTrue(session.dispatch(action, before))
        self.assertTrue(session.observe(after))
        self.assertTrue(session.complete)

    def test_real_snapshot_unchanged_withdraw_remains_unconfirmed(self):
        before_snapshot = self._stack_snapshot(95)
        identity = equipment_identity(before_snapshot.inventory[0])
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", "home:incident:0",
            item_identity=identity,
            move_identity=equipment_move_identity(before_snapshot.inventory[0]),
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        before = observe_equipment_transactions(before_snapshot)

        self.assertTrue(session.dispatch(action, before))
        self.assertFalse(session.observe(observe_equipment_transactions(
            self._stack_snapshot(95)
        )))
        self.assertIs(session.pending_action, action)
        self.assertFalse(session.complete)

    def test_home_physical_context_keeps_equip_phase_inside(self):
        action = EquipmentTransaction(
            PHASE_EQUIP, "takeoff", "equipped:item:0", "outer", "item"
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            physical_context="home",
        )
        inside = observation(
            home=True, equipped=(("outer", "item"),), generation=7
        )
        self.assertEqual(session.required_context, "home")
        self.assertTrue(session.prepare(action, inside, "ta", ("home", 7)))
        self.assertTrue(session.confirm_posted("ta"))

    def test_takeoff_confirms_source_proven_home_overflow_on_new_barrier(self):
        action = EquipmentTransaction(
            PHASE_EQUIP, "takeoff", "equipped:item:0", "outer", "item"
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            physical_context="home",
        )
        before = observation(
            home=True, equipped=(("outer", "item"),), generation=10
        )
        self.assertTrue(session.dispatch(action, before))
        stale = observation(home=True, shelved=("item",), generation=10)
        self.assertFalse(session.observe(stale))
        after = observation(home=True, shelved=("item",), generation=11)
        self.assertTrue(session.observe(after))
        self.assertTrue(session.complete)

    def test_semantic_refusal_blocks_instead_of_waiting_for_more_boards(self):
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "deposit", "pack:item:0",
            item_identity="item",
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        before = observation(home=True, pack=("item",), generation=3)
        self.assertTrue(session.dispatch(action, before))
        self.assertFalse(session.observe(observation(
            home=True, pack=("item",), generation=4, outcome="refused"
        )))
        self.assertEqual(session.blockers, ["deposit-refused"])
        self.assertIs(session.pending_action, action)

    def test_confirms_deposit_by_pack_count(self):
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "deposit", "pack:item:0",
            item_identity="item",
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        before = observation(home=True, pack=("item", "item"))
        self.assertTrue(session.dispatch(action, before))
        self.assertTrue(session.observe(observation(home=True, pack=("item",))))
        self.assertTrue(session.complete)

    def test_confirms_withdraw_by_pack_count_across_origin_change(self):
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", "home:item:0",
            item_identity="item",
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        before = observation(home=True)
        self.assertTrue(session.dispatch(action, before))
        self.assertTrue(
            session.observe(observation(home=True, pack=("item",)))
        )

    def test_equip_requires_outside_home_and_target_slot_confirmation(self):
        action = EquipmentTransaction(
            PHASE_EQUIP, "equip", "pack:item:0", "main_hand", "item"
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        before = observation(home=False, pack=("item",))
        self.assertFalse(session.dispatch(action, observation(home=True, pack=("item",))))
        self.assertTrue(session.dispatch(action, before))
        self.assertFalse(
            session.observe(
                observation(home=False, equipped=(("sub_hand", "item"),))
            )
        )
        self.assertTrue(
            session.observe(
                observation(home=False, equipped=(("main_hand", "item"),))
            )
        )

    def test_repeated_unconfirmed_snapshots_retain_posted_action(self):
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "deposit", "pack:item:0",
            item_identity="item",
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=2,
        )
        before = observation(home=True, pack=("item",))
        session.dispatch(action, before)
        self.assertFalse(session.observe(before))
        self.assertFalse(session.observe(before))
        self.assertEqual(session.blockers, [])
        self.assertIs(session.pending_action, action)

    def test_prepared_command_has_no_state_until_post_is_confirmed(self):
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", "home:item:0",
            item_identity="item",
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        before = observation(home=True)
        self.assertTrue(session.prepare(action, before, "pa\r", ("home", 7)))
        self.assertIsNone(session.pending_action)
        self.assertIs(session.prepared_action, action)
        self.assertFalse(session.confirm_posted("pb\r"))
        self.assertIsNone(session.pending_action)
        self.assertTrue(session.confirm_posted("pa\r"))
        self.assertIs(session.pending_action, action)

    def test_target_loadout_id_is_stable_for_same_plan(self):
        action = EquipmentTransaction(
            PHASE_EQUIP, "equip", "pack:item:0", "body", "item"
        )
        plan = EquipmentTransactionPlan((action,), (), 1)
        self.assertEqual(
            EquipmentTransactionSession(plan).target_loadout_id,
            EquipmentTransactionSession(plan).target_loadout_id,
        )

    def test_free_action_home_item_withdraws_and_equips_exact_target_slot(self):
        withdraw = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw",
            "home:9dbac83f7ea707d2:0", item_identity="free-action-boots",
        )
        equip = EquipmentTransaction(
            PHASE_EQUIP, "equip", "home:9dbac83f7ea707d2:0",
            "feet", "free-action-boots",
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((withdraw, equip), (), 1)
        )
        home = observation(home=True)
        self.assertTrue(session.prepare(withdraw, home, "pa\r", ("home", 1)))
        self.assertTrue(session.confirm_posted("pa\r"))
        carried = observation(home=False, pack=("free-action-boots",))
        self.assertTrue(session.observe(carried))
        self.assertTrue(session.prepare(equip, carried, "wa", ("town", 2)))
        self.assertTrue(session.confirm_posted("wa"))
        wrong_slot = observation(
            home=False, equipped=(("body", "free-action-boots"),)
        )
        self.assertFalse(session.observe(wrong_slot))
        worn = observation(
            home=False, equipped=(("feet", "free-action-boots"),)
        )
        self.assertTrue(session.observe(worn))
        self.assertTrue(session.complete)
        self.assertFalse(session.prepare(equip, worn, "wa", ("town", 3)))

    def test_accepts_delayed_store_confirmation(self):
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "deposit", "pack:item:0",
            item_identity="item",
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=3,
        )
        before = observation(home=True, pack=("item",))
        session.dispatch(action, before)

        self.assertFalse(session.observe(before))
        self.assertFalse(session.observe(before))
        self.assertTrue(session.observe(observation(home=True)))
        self.assertTrue(session.complete)

    def test_confirms_takeoff_only_after_item_reaches_pack(self):
        action = EquipmentTransaction(
            PHASE_EQUIP, "takeoff", "equipped:item:0", "sub_hand", "item"
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        before = observation(home=False, equipped=(("sub_hand", "item"),))
        self.assertTrue(session.dispatch(action, before))
        self.assertFalse(session.observe(observation(home=False)))
        self.assertTrue(
            session.observe(observation(home=False, pack=("item",)))
        )

    def test_plan_blocker_prevents_dispatch(self):
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "deposit", "pack:item:0",
            item_identity="item",
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), ("home-scan-incomplete",), 1)
        )
        self.assertFalse(session.dispatch(action, observation(home=True)))


if __name__ == "__main__":
    unittest.main()
