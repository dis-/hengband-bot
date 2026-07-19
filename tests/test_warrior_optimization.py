import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.equipment_optimizer import (
    Loadout,
    OwnedEquipment,
    SLOT_MAIN_RING,
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
    WarriorOptimizationPreparation,
    _base_stat_without_current_gear,
    _conservative_intrinsic_abilities,
    prepare_warrior_optimization,
    weapon_expected_dps,
)
from hengbot.warrior_equipment_evaluator import TR_DEX, TR_STR


def gear(
    item_id, origin, *, slot=None, tval=23, ac=0, to_a=0, to_d=0,
    to_h=0, pval=0, flags=(), dice=(1, 4), weight=30, proficiency=0,
    cursed=False,
):
    item = InventoryItem(
        slot=slot or item_id, name=item_id, count=1, tval=tval, sval=1,
        aware=True, known=True, fully_known=True, is_equipment=True,
        ac=ac, to_a=to_a, to_h=to_h, to_d=to_d, pval=pval, weight=weight,
        damage_dice_num=dice[0], damage_dice_sides=dice[1],
        known_flags=frozenset(flags), weapon_proficiency=proficiency,
        is_cursed=cursed,
    )
    return OwnedEquipment(item_id, item, origin, equipped_slot=slot)


class WarriorOptimizationTest(unittest.TestCase):
    def test_reference_ac_dual_wield_brand_dps_crosses_q1_gate(self):
        main = gear(
            "main", "equipped", slot="main_hand", to_h=3, to_d=2,
            dice=(2, 4), weight=100, proficiency=6000,
        ).item
        branded_sub = gear(
            "sub", "equipped", slot="sub_hand", to_h=6, to_d=7,
            dice=(1, 5), weight=30, flags=(29,), proficiency=6000,
        ).item
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(43, 12, 16, 17), stat_use=(123, 3, 7, 38),
            level=14, melee_skill=136, two_weapon_skill=6000,
        )
        snapshot = SimpleNamespace(player=player, equipment=(main, branded_sub))

        self.assertGreaterEqual(weapon_expected_dps(snapshot, main, 24), 28)
        self.assertLess(weapon_expected_dps(snapshot, main, 100), 28)

    def test_weapon_dps_includes_branded_off_hand(self):
        main = gear(
            "main", "equipped", slot="main_hand", to_h=3, to_d=2,
            dice=(2, 4), weight=100, proficiency=6000,
        ).item
        branded_sub = gear(
            "sub", "equipped", slot="sub_hand", to_h=6, to_d=7,
            dice=(1, 5), weight=30, flags=(29,), proficiency=6000,
        ).item
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(43, 12, 16, 17), stat_use=(123, 3, 7, 38),
            level=14, melee_skill=136, two_weapon_skill=6000,
        )
        dual = SimpleNamespace(player=player, equipment=(main, branded_sub))
        single = SimpleNamespace(player=player, equipment=(main,))

        self.assertGreater(
            weapon_expected_dps(dual, main, 24),
            weapon_expected_dps(single, main, 24),
        )

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
        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertIn("better", prepared.result.best.loadout.item_ids)
        self.assertTrue(
            any(
                action.kind == "withdraw" and action.item_id == "better"
                for action in prepared.transaction.actions
            )
        )

    def test_constitution_helm_is_not_replaced_by_small_ac_gain(self):
        light = gear("light", "equipped", slot="light", tval=39)
        weapon = gear("weapon", "equipped", slot="main_hand", to_d=8)
        stat_helm = gear(
            "stat-helm", "equipped", slot="head", tval=33,
            ac=0, to_a=4, pval=3, flags=(TR_STR, TR_DEX, 4),
        )
        steel_helm = gear(
            "steel-helm", "home", tval=33, ac=6, to_a=2,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(60, 12, 16, 17, 110, 13),
            stat_use=(170, 3, 7, 68, 210, 9),
            level=25,
            shield_skill=4000,
            speed=110,
            saving_skill=57,
            abilities=frozenset(),
            ac=86,
            melee_skill=175,
            shooting_skill=130,
            two_weapon_skill=4184,
            max_hp=627,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=80, average_hp=80, speed=110, can_summon=False,
            friendly=False, level=15, armor_class=20, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 4, 6),),
        )

        prepared = prepare_warrior_optimization(
            snapshot,
            (light, weapon, stat_helm, steel_helm),
            {1: monster},
            depth=15,
            home_scan_complete=True,
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(
            prepared.result.best.loadout.item_at("head"),
            stat_helm,
        )

    def test_ac_five_does_not_beat_three_strength_dexterity_constitution(self):
        light = gear("light", "equipped", slot="light", tval=39)
        weapon = gear(
            "weapon", "equipped", slot="main_hand", to_h=6, to_d=12,
        )
        crown = gear(
            "crown-of-might", "equipped", slot="head", tval=33,
            ac=0, to_a=3, pval=3, flags=(TR_STR, TR_DEX, 4),
        )
        steel_helm = gear(
            "steel-helm", "home", tval=32, ac=6, to_a=2,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(60, 12, 16, 17, 110, 14),
            stat_use=(170, 3, 7, 68, 210, 10),
            level=27,
            shield_skill=4000,
            speed=110,
            saving_skill=59,
            abilities=frozenset(),
            ac=85,
            melee_skill=181,
            shooting_skill=136,
            two_weapon_skill=4184,
            max_hp=663,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        # Weak encounters expose the former AC overvaluation most strongly:
        # AC affected both hit probability and HURT reduction, so this exact
        # five-point gain used to displace all three +3 stats.
        monster = MonraceKnowledge(
            max_hp=80, average_hp=80, speed=110, can_summon=False,
            friendly=False, level=2, armor_class=20, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 4, 6),),
        )

        prepared = prepare_warrior_optimization(
            snapshot,
            (light, weapon, crown, steel_helm),
            {1: monster},
            depth=15,
            home_scan_complete=True,
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(prepared.result.best.loadout.item_at("head"), crown)

    def test_preserves_current_free_action_despite_large_ac_gain(self):
        light = gear("light", "equipped", slot="light", tval=39)
        weapon = gear("weapon", "equipped", slot="main_hand", to_d=8)
        crown = gear(
            "crown-of-might", "equipped", slot="head", tval=33,
            ac=0, to_a=3, pval=3, flags=(TR_STR, TR_DEX, 4, 46, 61),
        )
        steel_helm = gear(
            "steel-helm", "home", tval=32, ac=20, to_a=20,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR,
            stat_cur=(60, 12, 16, 17, 110, 14),
            stat_use=(170, 3, 7, 68, 210, 10),
            level=27,
            shield_skill=4000,
            speed=110,
            saving_skill=59,
            abilities=frozenset({"free_action", "resist_nexus"}),
            ac=85,
            melee_skill=181,
            shooting_skill=136,
            two_weapon_skill=4184,
            max_hp=663,
            max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=80, average_hp=80, speed=110, can_summon=False,
            friendly=False, level=15, armor_class=20, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 4, 6),),
        )

        prepared = prepare_warrior_optimization(
            snapshot,
            (light, weapon, crown, steel_helm),
            {1: monster},
            depth=15,
            home_scan_complete=True,
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(prepared.result.best.loadout.item_at("head"), crown)

    def test_cursed_equipped_ring_is_pinned_through_production_entry(self):
        # Guards the pin comprehension in prepare_warrior_optimization itself
        # (warrior_optimization.py), which is a separate copy from the one in
        # equipment_optimizer.py and is the real Warrior production path. Because
        # this entry supplies candidate_loadouts, optimize_loadout never
        # recomputes the pin, so a typo isolated to this copy would otherwise be
        # invisible to the unit tests. Revert proof: emptying that comprehension
        # drops the (non-exploration-legal) cursed ring from the candidates, the
        # planner then tries to remove it, and prepared.ready flips to False.
        light = gear("light", "equipped", slot="light", tval=39)
        cursed_ring = gear(
            "cursed-ring", "equipped", slot="main_ring", tval=45, cursed=True,
        )
        old_weapon = gear("old-weapon", "equipped", slot="main_hand")
        better_weapon = gear("better-weapon", "home", to_d=20)
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
            snapshot, (light, cursed_ring, old_weapon, better_weapon),
            {1: monster}, depth=1, home_scan_complete=True,
        )

        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(
            prepared.result.best.loadout.item_at(SLOT_MAIN_RING), cursed_ring
        )
        self.assertFalse(
            any(
                blocker.startswith("cursed-equipped:")
                for blocker in prepared.blockers
            )
        )
        # The free weapon slot is still optimized around the pinned cursed ring.
        self.assertIn("better-weapon", prepared.result.best.loadout.item_ids)
        self.assertTrue(
            any(
                action.kind == "withdraw" and action.item_id == "better-weapon"
                for action in prepared.transaction.actions
            )
        )

    def test_saber_loses_to_strictly_better_home_long_sword(self):
        light = gear("light", "equipped", slot="light", tval=39)
        saber = gear(
            "saber", "equipped", slot="main_hand", to_h=2, to_d=1,
            dice=(1, 7), weight=50,
        )
        gauche = gear(
            "gauche", "equipped", slot="sub_hand", to_h=3, to_d=3,
            dice=(1, 5), weight=30,
        )
        long_sword = gear(
            "long-sword", "home", to_h=5, to_d=7,
            dice=(2, 5), weight=130,
        )
        player = SimpleNamespace(
            class_id=PLAYER_CLASS_WARRIOR, stat_cur=(68, 10, 10, 68),
            stat_use=(68, 10, 10, 68), level=27, shield_skill=0,
            speed=110, saving_skill=40, abilities=frozenset(), ac=0,
            melee_skill=80, two_weapon_skill=4000, max_hp=494, max_mp=0,
        )
        snapshot = SimpleNamespace(player=player, inventory=())
        monster = MonraceKnowledge(
            max_hp=15, average_hp=15, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=100, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 6),),
        )
        with TemporaryDirectory() as directory:
            report = Path(directory) / "loadout-report.jsonl"
            prepared = prepare_warrior_optimization(
                snapshot, (light, saber, gauche, long_sword), {1: monster},
                depth=1, home_scan_complete=True, loadout_report_path=report,
            )
            record = json.loads(report.read_text(encoding="utf-8"))
        self.assertLessEqual(len(record["candidates"]), 3)
        self.assertEqual(record["candidates"][0]["rank"], 1)
        self.assertIn("melee_output", record["candidates"][0]["score"])
        self.assertIn("long-sword", {
            item["id"] for item in record["candidates"][0]["slots"].values()
        })
        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertIn("long-sword", prepared.result.best.loadout.item_ids)
        self.assertTrue(any(
            action.kind == "withdraw" and action.item_id == "long-sword"
            for action in prepared.transaction.actions
        ))

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

    def test_policy_equips_withdrawn_shield_after_off_hand_takeoff(self):
        shield = gear("shield", "pack", slot="a", tval=34)
        action = EquipmentTransaction(
            PHASE_EQUIP, "equip", "shield", "sub_hand",
            item_identity=equipment_identity(shield.item),
        )
        policy = HengbotPolicy()
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1),
            max_unconfirmed_observations=1,
        )
        policy._equipment_transaction_session = session
        before = SimpleNamespace(
            in_town=True, store=None, inventory=(shield.item,), equipment=(),
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )

        self.assertEqual(policy._equipment_transaction_town_key(before), "wa")
        equipped = SimpleNamespace(
            in_town=True, store=None, inventory=(),
            equipment=(gear("shield", "equipped", slot="sub_hand", tval=34).item,),
            player=before.player,
        )
        session.observe(observe_equipment_transactions(equipped))
        self.assertTrue(session.complete)

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

        self.assertEqual(policy._equipment_transaction_home_key(snapshot), "\x1b")
        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:await-confirmation-leave-home",
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

    def test_departure_releases_after_bounded_home_shield_withdraw_stall(self):
        """Live shape: the optimal main hand is on; Home sub hand never moves."""
        main = gear("main", "equipped", slot="main_hand")
        shield = gear("shield", "home", slot="sub_hand", tval=34)
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, "withdraw", shield.id,
            item_identity=equipment_identity(shield.item),
        )
        pending_plan = EquipmentTransactionPlan((action,), (), 1)
        achieved_plan = EquipmentTransactionPlan((), (), 1)
        current = Loadout((("main_hand", main),), "one_handed")
        pending = WarriorOptimizationPreparation(
            current, None, pending_plan, (),
        )
        achieved = WarriorOptimizationPreparation(
            current, None, achieved_plan, (),
        )
        policy = HengbotPolicy()
        session = EquipmentTransactionSession(
            pending_plan, max_unconfirmed_observations=3,
        )
        before = observe_equipment_transactions(SimpleNamespace(
            inventory=(), equipment=(main.item,), store=SimpleNamespace(
                store_type=STORE_HOME,
            ),
        ))
        self.assertTrue(session.dispatch(action, before))
        policy._equipment_transaction_session = session
        policy._equipment_optimization_preparation = pending
        policy._prepare_equipment_optimization = lambda _snapshot: (
            pending if policy._equipment_transaction_session is not None else achieved
        )
        snapshot = SimpleNamespace(
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )

        self.assertFalse(policy._equipment_departure_ready(snapshot))
        session.observe(before)
        self.assertFalse(policy._equipment_departure_ready(snapshot))
        session.observe(before)
        self.assertFalse(policy._equipment_departure_ready(snapshot))
        session.observe(before)
        self.assertTrue(policy._equipment_departure_ready(snapshot))
        self.assertIn(shield.id, policy._equipment_transaction_failed_items)

    def test_departure_is_immediate_for_already_optimal_loadout(self):
        policy = HengbotPolicy()
        current = Loadout((), "empty")
        prepared = WarriorOptimizationPreparation(
            current, None, EquipmentTransactionPlan((), (), 0), (),
        )
        policy._prepare_equipment_optimization = lambda _snapshot: prepared
        snapshot = SimpleNamespace(
            player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )
        self.assertTrue(policy._equipment_departure_ready(snapshot))


if __name__ == "__main__":
    unittest.main()
