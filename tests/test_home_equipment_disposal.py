from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    STORE_HOME,
    STORE_WEAPON,
    SV_BOW_LIGHT_XBOW,
    SV_BOW_SHORT,
    TVAL_BOLT,
    TVAL_BOW,
    TVAL_SWORD,
    StoreState,
)
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
        policy._equipment_catalog.observe_home_page(
            home.store.items, allow_wrap=True
        )
        policy._home_disposal_pass = True
        self.assertEqual(policy._home_dominated_disposal_key(home), "\x1b")

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
        self.assertEqual(policy.choose_key(smith), "{d@0\r")

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

    @staticmethod
    def launcher(slot, sval, name, *, to_h, to_d, artifact=False):
        return item(
            slot, TVAL_BOW, sval, name=name, known=True, fully_known=True,
            is_equipment=True, is_artifact=artifact, to_h=to_h, to_d=to_d,
        )

    def launcher_snapshot(self, inventory, equipment, *, quests=None):
        return replace(
            self.snapshot([]),
            inventory=inventory,
            equipment=equipment,
            store=None,
            quests=quests or {},
        )

    def test_pack_crossbow_dominated_by_equipped_artifact_bow_is_routed(self):
        equipped = self.launcher(
            "bow", SV_BOW_SHORT, "artifact bow", to_h=15, to_d=17,
            artifact=True,
        )
        crossbow = self.launcher(
            "a", SV_BOW_LIGHT_XBOW, "plain crossbow", to_h=4, to_d=5,
        )
        snapshot = self.launcher_snapshot([crossbow], [equipped])
        policy = HengbotPolicy()

        needs = policy._enumerate_town_needs(snapshot)

        self.assertEqual(policy._pending_disposal_slot, "a")
        self.assertIn(
            (STORE_WEAPON, "disposal"),
            [(need.store_type, need.category) for need in needs],
        )

    def test_only_crossbow_and_bolts_are_untouched(self):
        crossbow = self.launcher(
            "a", SV_BOW_LIGHT_XBOW, "only crossbow", to_h=4, to_d=5,
        )
        bolts = item("b", TVAL_BOLT, 0, name="bolts", known=True, count=30)
        snapshot = self.launcher_snapshot([crossbow, bolts], [])
        policy = HengbotPolicy()

        needs = policy._enumerate_town_needs(snapshot)

        self.assertIsNone(policy._pending_disposal_item)
        self.assertNotIn("disposal", [need.category for need in needs])

    def test_equipped_and_quest_required_launchers_are_retained(self):
        bow = self.launcher(
            "bow", SV_BOW_SHORT, "artifact bow", to_h=15, to_d=17,
            artifact=True,
        )
        crossbow = self.launcher(
            "a", SV_BOW_LIGHT_XBOW, "quest crossbow", to_h=4, to_d=5,
        )
        snapshot = self.launcher_snapshot([crossbow], [bow])
        policy = HengbotPolicy()
        self.assertFalse(policy._is_disposable_dominated_launcher(snapshot, bow))

        profile = SimpleNamespace(
            required_force={
                "launcher": {
                    "ammo": "bolt",
                    "equipped": True,
                    "min_average_damage": 0,
                }
            }
        )
        with patch.object(
            policy, "_quest_strategy_for_errand_or_floor", return_value=profile
        ):
            self.assertFalse(
                policy._is_disposable_dominated_launcher(snapshot, crossbow)
            )


if __name__ == "__main__":
    unittest.main()
