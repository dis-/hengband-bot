"""Part B pins for non-ego jewelry scope and stable fallback ordering.

J includes only non-ego magical jewelry. The recorded line-724 catalogue
selects 44 J-D sales; the branch-local pin was corrected to that scope.
"""
import tests  # noqa: F401
from dataclasses import replace
from types import SimpleNamespace
import unittest

from hengbot.equipment_optimizer import OwnedEquipment
from hengbot.equipment_sale_classifier import (
    EquipmentSaleClassification, equipment_sale_fallback_order,
    equipment_sale_plan, equipment_sale_scope,
)
from hengbot.model import InventoryItem, STORE_HOME
from hengbot.model import StoreState
from hengbot.policy import LEAVE_STORE_KEY
from policy_fixtures import store_item
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from test_policy import HengbotPolicy


class EquipmentSaleScopeB(unittest.TestCase):
    def test_j_excludes_ego_magical_jewelry(self):
        for tval in (40, 45):
            with self.subTest(tval=tval):
                item = InventoryItem("a", "constructed magic jewelry", 1,
                                     tval, 1, True, True, fully_known=True,
                                     is_equipment=True, known_flags=frozenset({62}))
                self.assertTrue(equipment_sale_scope(OwnedEquipment("plain", item, "home"), "J"))
                self.assertFalse(equipment_sale_scope(
                    OwnedEquipment("ego", replace(item, is_ego=True), "home"), "J"))

    def test_fallback_order_is_lowest_performance_then_stable_id(self):
        result = EquipmentSaleClassification(
            sold_ids=frozenset({"already-selected"}), pareto_ids=frozenset(),
            needs_identification_ids=frozenset(), reasons={}, dominators={},
            # Deliberately conflicts with the classifier rank: fallback must
            # reverse the same _prefer-based slot ordering, not re-sort a
            # different pair of metrics.
            performance={"z": (0.0, 0.0), "b": (100.0, 100.0),
                         "a": (200.0, 200.0)},
            eligible_ids=frozenset({"already-selected", "z", "b", "a", "protected"}),
            ranks={"already-selected": 11, "z": 12, "b": 13, "a": 14,
                   "protected": 1},
        )
        self.assertEqual(
            equipment_sale_fallback_order(result, excluded_ids=frozenset({"protected"})),
            ("a", "b", "z"),
        )
        self.assertEqual(
            equipment_sale_plan(
                result, home_ids=frozenset({"already-selected", "a", "b", "z"}),
                free_home_slots=0, target_free_slots=3,
            ),
            ("already-selected", "a", "b"),
        )

    def test_rank_21_is_always_sold_and_top_10_is_never_sold(self):
        result = EquipmentSaleClassification(
            sold_ids=frozenset({"rank-10", "rank-11"}), pareto_ids=frozenset(),
            needs_identification_ids=frozenset(), reasons={}, dominators={},
            performance={"rank-10": (10, 0), "rank-11": (9, 0),
                         "rank-21": (1, 0), "protected-rank-22": (0, 0)},
            eligible_ids=frozenset({"rank-10", "rank-11", "rank-21"}),
            ranks={"rank-10": 10, "rank-11": 11, "rank-21": 21,
                   "protected-rank-22": 22},
        )
        self.assertEqual(
            equipment_sale_plan(result, home_ids=frozenset(
                                    (*result.eligible_ids, "protected-rank-22")),
                                free_home_slots=30, target_free_slots=20),
            ("rank-11", "rank-21"),
        )
        self.assertEqual(
            equipment_sale_plan(result, home_ids=frozenset(
                                    (*result.eligible_ids, "protected-rank-22")),
                                free_home_slots=0, target_free_slots=20),
            ("rank-11", "rank-21"),
        )

    def test_sale_session_survives_restored_checkpoint(self):
        policy = HengbotPolicy()
        policy._returning_to_town = False
        policy._note_return_start("pack-full")
        policy._equipment_sale_session = {
            "built": True,
            "items": [{"signature": ("saved gear", 37, 4),
                       "origin": "home", "store_type": 7}],
            "attempted": {("saved gear", 37, 4)},
            "withdrawals": 2,
            "refused": set(),
            "active_store": 7,
        }
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertEqual(restored._equipment_sale_session["withdrawals"], 2)
        self.assertEqual(restored._equipment_sale_session["active_store"], 7)
        self.assertIn(("saved gear", 37, 4),
                      restored._equipment_sale_session["attempted"])

    def test_sale_item_does_not_release_transaction_relocation_ownership(self):
        from hengbot.policy_types import DecisionContext
        policy = HengbotPolicy()
        town = SimpleNamespace(in_town=True)
        policy._decision_context = DecisionContext(equipment_transaction_owned=True)
        self.assertTrue(policy._equipment_transaction_owns_town_relocation(town))
        signature = ("withdrawn sale gear", 37, 1)
        policy._equipment_sale_session = {
            "built": True,
            "items": [{"signature": signature, "origin": "home",
                       "store_type": 1, "weight": 1}],
            "attempted": {signature}, "withdrawals": 1, "refused": set(),
            "active_store": 1,
        }
        policy._pending_disposal_item = signature
        self.assertTrue(policy._equipment_transaction_owns_town_relocation(town))
        # Sale inventory never releases relocation while transaction owns it.
        policy._pending_disposal_item = None
        self.assertTrue(policy._equipment_transaction_owns_town_relocation(town))

    def test_sale_selection_waits_until_transaction_and_owned_items_are_gone(self):
        policy = HengbotPolicy()
        item = InventoryItem(
            "a", "pack sale candidate", 1, 37, 1, True, True,
            fully_known=True, is_equipment=True,
        )
        signature = policy._item_signature(item)
        policy._equipment_sale_session = {
            "built": True, "items": [{
                "signature": signature, "origin": "pack", "store_type": 2,
                "weight": 1,
            }],
            "attempted": set(), "planned": set(), "refused": set(),
            "withdrawals": 0, "active_store": None,
        }
        policy._equipment_transaction_session = object()
        policy._equipment_transaction_owned_items = [("stripped", "body")]
        board = SimpleNamespace(inventory=[item])

        self.assertIsNone(policy._equipment_sale_next_store(board))
        self.assertEqual(policy._equipment_sale_session["attempted"], set())
        self.assertEqual(policy._equipment_sale_session["withdrawals"], 0)
        policy._equipment_transaction_session = None
        self.assertIsNone(policy._equipment_sale_next_store(board))
        self.assertEqual(policy._equipment_sale_session["attempted"], set())
        policy._equipment_transaction_owned_items.clear()
        self.assertEqual(policy._equipment_sale_next_store(board), 2)

    def test_home_sale_batch_is_bounded_to_three_withdrawals(self):
        policy = HengbotPolicy()
        signatures = [(f"sale gear {index}", 37, 1) for index in range(5)]
        policy._equipment_sale_session = {
            "built": True,
            "items": [{"signature": signature, "origin": "home",
                       "store_type": STORE_HOME, "weight": 1}
                      for signature in signatures],
            "attempted": set(), "withdrawals": 0, "refused": set(),
            "active_store": None,
        }
        policy._build_equipment_sale_session = lambda _snapshot: None
        policy._home_available = lambda _snapshot: True
        policy._inventory_weight_limit = lambda _snapshot: 100
        policy._inventory_weight = lambda _snapshot: 0

        selected = policy._equipment_sale_next_store(SimpleNamespace(inventory=[]))

        self.assertEqual(selected, STORE_HOME)
        self.assertEqual(policy._equipment_sale_session["withdrawals"], 0)
        self.assertEqual(policy._equipment_sale_session["attempted"], set())
        self.assertEqual(
            policy._equipment_sale_session["planned"],
            set(signatures[:3]),
        )
        self.assertEqual(len(policy._equipment_sale_session["batch"]), 3)
        self.assertEqual(len(policy._home_pending_batch), 2)

    def test_relief_sells_carried_candidates_before_home_withdrawals(self):
        policy = HengbotPolicy()
        carried = InventoryItem(
            "a", "carried sale gear", 1, 37, 1, True, True,
            fully_known=True, is_equipment=True,
        )
        pack_signature = policy._item_signature(carried)
        home_signature = ("home sale gear", 37, 2)
        policy._equipment_sale_session = {
            "built": True,
            "items": [
                {"signature": home_signature, "origin": "home",
                 "store_type": STORE_HOME, "weight": 500},
                {"signature": pack_signature, "origin": "pack",
                 "store_type": 2, "weight": 1},
            ],
            "attempted": set(), "withdrawals": 0, "refused": set(),
            "active_store": None,
        }
        policy._build_equipment_sale_session = lambda _snapshot: None
        policy._equipment_sale_relief_active = lambda _snapshot: True
        policy._inventory_weight_limit = lambda _snapshot: 1
        policy._inventory_weight = lambda _snapshot: 100

        selected = policy._equipment_sale_next_store(
            SimpleNamespace(inventory=[carried])
        )

        self.assertEqual(selected, 2)
        self.assertEqual(policy._pending_disposal_item, pack_signature)

    def test_refused_sale_is_not_retried_on_the_same_return(self):
        policy = HengbotPolicy()
        signature = ("refused gear", 37, 1)
        policy._equipment_sale_session = {
            "built": True,
            "items": [{"signature": signature, "origin": "pack",
                       "store_type": STORE_HOME, "weight": 1}],
            "attempted": {signature}, "withdrawals": 0,
            "refused": set(), "active_store": STORE_HOME,
        }
        policy._build_equipment_sale_session = lambda _snapshot: None
        policy._pending_disposal_item = signature
        policy._unsellable_items.add(signature)

        self.assertIsNone(
            policy._equipment_sale_next_store(SimpleNamespace(inventory=[]))
        )
        self.assertIn(signature, policy._equipment_sale_session["refused"])
        self.assertIsNone(
            policy._equipment_sale_next_store(SimpleNamespace(inventory=[]))
        )

    def test_refused_sale_candidate_is_never_destroyed(self):
        policy = HengbotPolicy()
        item = InventoryItem("a", "refused gear", 1, 37, 1, True, True,
                             fully_known=True, is_equipment=True)
        signature = policy._item_signature(item)
        policy._pending_disposal_item = signature
        policy._pending_disposal_slot = "a"
        policy._destroy_pending = True
        policy._equipment_sale_session = {
            "built": True,
            "items": [{"signature": signature, "origin": "pack",
                       "store_type": STORE_HOME, "weight": 1}],
            "attempted": {signature}, "withdrawals": 0,
            "refused": {signature}, "active_store": STORE_HOME,
        }
        policy._offer_execution_no_step = lambda **_kwargs: None
        before = policy._destroy_attempts

        result = policy._town_destroy_key(
            SimpleNamespace(in_town=True, inventory=[item])
        )

        self.assertIsNone(result)
        self.assertEqual(policy._destroy_attempts, before)
        self.assertEqual(policy.last_reason, "equipment:sale-refused-carry")

    def test_refused_sale_is_redeposited_when_home_has_room(self):
        policy = HengbotPolicy()
        item = InventoryItem("a", "refused gear", 2, 37, 1, True, True,
                             fully_known=True, is_equipment=True)
        signature = policy._item_signature(item)
        policy._equipment_sale_session = {"refused": {signature}}
        policy._home_reserve_deposit_item = lambda _item: False
        policy._disposal_protected_by_identification = lambda _item: False

        self.assertTrue(policy._home_deposit_candidate(item, SimpleNamespace()))
        self.assertEqual(policy._home_deposit_quantity(SimpleNamespace(), item), 2)

    def test_planned_home_sale_uses_dominated_withdrawal_predicate(self):
        policy = HengbotPolicy()
        shelf_item = store_item("a", 37, 1, name="planned sale gear")
        signature = policy._item_signature(shelf_item)
        policy._home_disposal_pass = False
        policy._pending_disposal_item = signature
        policy._equipment_sale_session = {
            "built": True,
            "items": [{"signature": signature, "origin": "home",
                       "store_type": STORE_HOME, "weight": 1}],
            "attempted": {signature}, "withdrawals": 0,
            "refused": set(), "active_store": STORE_HOME,
        }
        policy._inventory_weight_limit = lambda _snapshot: 100
        policy._inventory_weight = lambda _snapshot: 0
        snapshot = SimpleNamespace(
            store=StoreState(STORE_HOME, [shelf_item]), inventory=[],
        )

        self.assertEqual(
            policy._home_dominated_disposal_key(snapshot), LEAVE_STORE_KEY
        )
        self.assertEqual(policy._home_pending_item, signature)


if __name__ == "__main__":
    unittest.main()
