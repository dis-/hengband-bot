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
)


def observation(*, home, pack=(), equipped=()):
    return EquipmentTransactionObservation.create(
        in_home=home,
        pack_identities=pack,
        equipped_identities=equipped,
    )


class EquipmentTransactionSessionTest(unittest.TestCase):
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

    def test_blocks_after_repeated_unconfirmed_snapshots(self):
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
        self.assertEqual(
            session.blockers, ["unconfirmed:deposit:pack:item:0"]
        )

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
