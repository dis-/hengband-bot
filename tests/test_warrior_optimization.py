import unittest
from types import SimpleNamespace

from hengbot.equipment_optimizer import (
    Loadout,
    OwnedEquipment,
    current_loadout,
    equipment_identity,
)
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    PHASE_HOME_PREPARE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import (
    EquipmentTransactionSession,
    observe_equipment_transactions,
)
from hengbot.model import (
    InventoryItem,
    PLAYER_CLASS_WARRIOR,
    STORE_HOME,
    StoreItem,
)
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.warrior_optimization import (
    _base_stat_without_current_gear,
    _conservative_intrinsic_abilities,
    prepare_warrior_optimization,
)
from hengbot.warrior_equipment_evaluator import TR_DEX, TR_STR


def gear(
    item_id, origin, *, slot=None, tval=23, ac=0, to_a=0, to_d=0,
    pval=0, flags=(),
):
    item = InventoryItem(
        slot=slot or item_id, name=item_id, count=1, tval=tval, sval=1,
        aware=True, known=True, fully_known=True, is_equipment=True,
        ac=ac, to_a=to_a, to_d=to_d, pval=pval,
        damage_dice_num=1, damage_dice_sides=4,
        known_flags=frozenset(flags),
    )
    return OwnedEquipment(item_id, item, origin, equipped_slot=slot)


class WarriorOptimizationTest(unittest.TestCase):
    def test_removes_only_current_equipment_pval_from_displayed_stats(self):
        ring = gear(
            "strength-ring", "equipped", slot="main_ring", tval=45,
            pval=2, flags=(TR_STR,),
        )
        current = current_loadout((ring,))

        self.assertEqual(
            _base_stat_without_current_gear(162, current, TR_STR), 142
        )
        self.assertEqual(
            _base_stat_without_current_gear(61, current, TR_DEX), 61
        )

    def test_reconstructs_weapon_and_shield(self):
        weapon = gear("weapon", "equipped", slot="main_hand")
        shield = gear("shield", "equipped", slot="sub_hand", tval=34)
        loadout = current_loadout((weapon, shield))
        self.assertEqual(loadout.hand_mode, "weapon_shield")
        self.assertEqual(loadout.item_ids, frozenset({"weapon", "shield"}))

    def test_current_equipment_ability_is_not_treated_as_intrinsic(self):
        ring = gear(
            "fire-ring", "equipped", slot="main_ring", tval=45,
            flags=(50,),
        )
        abilities = _conservative_intrinsic_abilities(
            frozenset({"resist_fire", "free_action"}),
            current_loadout((ring,)),
        )
        self.assertEqual(abilities, frozenset({"free_action"}))

    def test_fails_closed_without_static_monster_knowledge(self):
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, stat_cur=(18, 10, 10, 18),
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        prepared = prepare_warrior_optimization(
            snapshot, (), {}, depth=1, home_scan_complete=True
        )
        self.assertEqual(prepared.blockers, ("missing-monrace-knowledge",))

    def test_fails_closed_before_complete_home_scan(self):
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, stat_cur=(18, 10, 10, 18),
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        prepared = prepare_warrior_optimization(
            snapshot, (), {1: object()}, depth=1, home_scan_complete=False
        )
        self.assertEqual(prepared.blockers, ("home-scan-incomplete",))

    def test_builds_transaction_for_stronger_complete_loadout(self):
        light = gear("light", "equipped", slot="light", tval=39)
        old = gear("old", "equipped", slot="main_hand")
        better = gear("better", "home", to_d=20)
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(18, 10, 10, 18),
            level=10,
            shield_skill=0,
            speed=110,
            saving_skill=30,
            abilities=frozenset(),
            ac=0,
            melee_skill=60,
            two_weapon_skill=0,
            max_hp=100,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 4),),
        )
        prepared = prepare_warrior_optimization(
            snapshot, (light, old, better), {1: monster}, depth=1,
            home_scan_complete=True,
        )
        self.assertTrue(prepared.ready)
        self.assertIn("better", prepared.result.best.loadout.item_ids)
        self.assertTrue(
            any(
                action.kind == "withdraw" and action.item_id == "better"
                for action in prepared.transaction.actions
            )
        )

    def test_policy_dispatches_takeoff_with_equipment_slot_letter(self):
        shield = gear("shield", "equipped", slot="sub_hand", tval=34)
        action = EquipmentTransaction(
            PHASE_EQUIP, "takeoff", "shield", "sub_hand",
            item_identity=equipment_identity(shield.item),
        )
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=1,
        )
        snapshot = SimpleNamespace(
            in_town=True, store=None, inventory=(), equipment=(shield.item,),
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )
        self.assertEqual(policy._equipment_transaction_town_key(snapshot), "tb")

    def test_policy_dispatches_home_withdraw_from_visible_page(self):
        store_item = StoreItem(
            letter="c", name="stored", count=1, tval=23, sval=1,
            price=0, aware=True, known=True, fully_known=True,
            is_equipment=True, damage_dice_num=1, damage_dice_sides=4,
        )
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", "stored",
            item_identity=equipment_identity(store_item),
        )
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=1,
        )
        snapshot = SimpleNamespace(
            in_town=True,
            store=SimpleNamespace(store_type=STORE_HOME, items=(store_item,)),
            inventory=(), equipment=(),
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )
        self.assertEqual(
            policy._equipment_transaction_home_key(snapshot), "pc\r"
        )

        self.assertEqual(policy._equipment_transaction_home_key(snapshot), "5")
        self.assertEqual(
            policy.last_reason, "equipment-transaction:await-confirmation"
        )
        self.assertTrue(policy._equipment_transaction_session.executable)

    def test_policy_abandons_unconfirmed_home_withdraw_for_replanning(self):
        store_item = StoreItem(
            letter="c", name="stored", count=1, tval=23, sval=1,
            price=0, aware=True, known=True, fully_known=True,
            is_equipment=True, damage_dice_num=1, damage_dice_sides=4,
        )
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", "stored",
            item_identity=equipment_identity(store_item),
        )
        policy = HengbotPolicy()
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=1,
        )
        policy._equipment_transaction_session = session
        snapshot = SimpleNamespace(
            in_town=True,
            store=SimpleNamespace(store_type=STORE_HOME, items=(store_item,)),
            inventory=(), equipment=(),
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )

        self.assertEqual(policy._equipment_transaction_home_key(snapshot), "pc\r")
        session.observe(observe_equipment_transactions(snapshot))
        self.assertFalse(session.executable)
        self.assertEqual(policy._equipment_transaction_home_key(snapshot), "\x1b")
        self.assertEqual(
            policy.last_reason, "equipment-transaction:abandon-blocked-home"
        )
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertIn("stored", policy._equipment_transaction_failed_items)
        self.assertIsNone(policy._town_blocked_reason)


if __name__ == "__main__":
    unittest.main()
