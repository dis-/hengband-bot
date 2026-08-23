import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.policy import (
    BUY_KEY,
    FOOD_MIN_SVAL,
    HengbotPolicy,
    LEAVE_STORE_KEY,
)
from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    RESTORE_POTION_SVAL_BY_STAT,
    STORE_ALCHEMIST,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_POTION_CURE_CRITICAL,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE,
    SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_TELEPORT,
    SV_SCROLL_WORD_OF_RECALL,
    SV_STAFF_IDENTIFY,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_SCROLL,
    TVAL_STAFF,
    Position,
    Snapshot,
    StoreState,
)
from tests.test_policy import grid, item, player, store_item


class BlockedPurchaseNamespaceAcceptanceTest(unittest.TestCase):
    def _incident_shelf(self):
        return StoreState(
            STORE_ALCHEMIST,
            [
                store_item("d", TVAL_SCROLL, SV_SCROLL_TELEPORT, price=64, count=42),
                store_item("e", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=243, count=8),
                store_item("f", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=81),
                store_item("g", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=61),
                store_item("o", TVAL_POTION, SV_POTION_CURE_CRITICAL, price=48, count=23),
            ],
        )

    def _incident_snapshot(self):
        position = Position(36, 90)
        return Snapshot(
            player(36, 90, class_id=PLAYER_CLASS_WARRIOR, gold=6703),
            {position: replace(grid(36, 90), store_number=STORE_ALCHEMIST)},
            [],
            floor_key=(0, 0, 0),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=8),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=14),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=8),
            ],
            equipment=[],
            store=self._incident_shelf(),
            turn=4454,
        )

    @staticmethod
    def _incident_policy():
        policy = HengbotPolicy()
        policy._floor_key = (0, 0, 0)
        policy._deepest_level = 20
        policy._identification_need = "normal"
        policy._town_blocked_reason = "repetition"
        return policy

    def test_pin_vacuity_incident_store_stages_then_composes_recall_buy(self):
        policy = self._incident_policy()
        inside = self._incident_snapshot()

        self.assertEqual(policy._town_blocked_key(inside), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:observe-and-leave")
        self.assertEqual(policy._shop_observation[0], inside.store)
        outside = replace(inside, store=None, turn=inside.turn + 1)
        policy.choose_key(outside)
        posted = policy.choose_key(replace(inside, turn=inside.turn + 2))

        self.assertTrue(posted.startswith(BUY_KEY + "e"), posted)

    def test_pin_vacuity_classifier_families_match_need_families(self):
        registry_families = {
            spec.category.split(":", 1)[0]
            for spec in HengbotPolicy()._town_need_registry()
        }
        restore_stat, restore_sval = next(iter(RESTORE_POTION_SVAL_BY_STAT.items()))
        cases = (
            (store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL), "recall"),
            (store_item("b", TVAL_SCROLL, SV_SCROLL_TELEPORT), "teleport"),
            (store_item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL), "cure-critical"),
            (store_item("d", TVAL_FLASK, SV_FLASK_OIL), "oil"),
            (store_item("e", TVAL_FOOD, FOOD_MIN_SVAL), "food"),
            (store_item("f", TVAL_SCROLL, SV_SCROLL_IDENTIFY), "identification-source"),
            (store_item("g", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY), "identification-source"),
            (store_item("h", TVAL_STAFF, SV_STAFF_IDENTIFY), "identify-staff"),
            (store_item("i", TVAL_LITE, SV_LITE_LANTERN), "light"),
            (store_item("j", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE), "remove-curse"),
            (store_item("k", TVAL_POTION, restore_sval), "stat-restore"),
        )
        for ware, need_family in cases:
            with self.subTest(ware=ware.letter, need_family=need_family, stat=restore_stat):
                emitted = HengbotPolicy._cross_town_item_categories(ware)
                self.assertTrue(emitted)
                emitted_families = {
                    value.split(":", 1)[0] for value in emitted
                }
                self.assertIn(need_family, registry_families)
                self.assertIn(need_family, emitted_families)

    def test_pin_vacuity_identify_only_shelf_composes_real_need_intersection(self):
        policy = self._incident_policy()
        snapshot = replace(
            self._incident_snapshot(),
            store=StoreState(
                STORE_ALCHEMIST,
                [store_item("f", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=61)],
            ),
        )

        self.assertTrue(policy._town_blocked_purchase_is_composable(snapshot))
        self.assertEqual(policy._town_blocked_key(snapshot), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:observe-and-leave")
        self.assertEqual(policy._shop_observation[0], snapshot.store)

    def test_pin_vacuity_mandatory_recall_precedes_identify_then_falls_through(self):
        policy = self._incident_policy()
        snapshot = self._incident_snapshot()

        self.assertEqual(policy._next_purchase_unreserved(snapshot).letter, "e")
        rearmed = replace(
            snapshot,
            inventory=[
                replace(snapshot.inventory[0], count=10),
                replace(snapshot.inventory[1], count=15),
                replace(snapshot.inventory[2], count=10),
            ],
        )
        self.assertIn(
            policy._next_purchase_unreserved(rearmed).letter,
            {"f", "g"},
        )

    def test_pin_vacuity_supplier_router_and_repetition_handler_share_gate(self):
        policy = self._incident_policy()
        inside = self._incident_snapshot()
        outside = replace(inside, store=None)
        policy._town_supplier_stock[STORE_ALCHEMIST] = inside.store
        step = Position(outside.player.position.y, outside.player.position.x + 1)

        with patch.object(policy, "_shopping_approach_step", return_value=step):
            self.assertIsNotNone(policy._town_procurement_progress_key(outside))
        with patch.object(
            policy, "_town_blocked_purchase_is_composable", return_value=False
        ), patch.object(policy, "_shopping_approach_step", return_value=step):
            self.assertIsNone(policy._town_procurement_progress_key(outside))

if __name__ == "__main__":
    unittest.main()
