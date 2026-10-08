"""Constructed pin for the 2026-10-08 equipment-sale prerequisite stall.

DECLARED CONSTRUCTED from the 19:36 decision rows: no suitable onset
checkpoint is available. The live sequence recorded no scan/calibration
request before deposit work. This pin recreates the missing-catalogue then
missing-calibration blockers and checks both existing producers run first.
"""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.model import (
    PLAYER_CLASS_WARRIOR, Snapshot, STORE_HOME, StoreItem,
    StoreState,
)
from hengbot.equipment_sale_classifier import EquipmentSaleClassification
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HOME_CHARACTER_DUMP_MACRO
from policy_fixtures import player


class EquipmentSalePrerequisiteRecoveryTest(unittest.TestCase):
    def test_scan_then_calibration_precede_home_relief_and_unblock_sale_list(self):
        policy = HengbotPolicy()
        policy._equipment_sale_session = {
            "built": False, "items": [], "attempted": set(),
            "withdrawals": 0, "refused": set(), "active_store": None,
        }
        page = [
            StoreItem(chr(ord("a") + index), f"constructed ring {index}",
                      1, 45, 1, 100, known=True, aware=True,
                      fully_known=True)
            for index in range(4)
        ]
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR), {}, [],
            store=StoreState(STORE_HOME, page, 4, 0, 4), town_flag=True,
        )

        # Prior to the fix, this state left the attempt set empty and ordinary
        # Home work could post a deposit. The sale blocker now invokes ~9 first.
        self.assertNotIn("prerequisite_attempted",
                         policy._equipment_sale_session)
        self.assertFalse(policy._home_knowledge_scan_requested)
        self.assertIsNone(policy._home_atomic_deposit_pending)
        key = policy.choose_key(home)
        self.assertEqual(key, "~9\x1b")
        self.assertEqual(policy.decision_claim["owner"], "home-scan")
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")
        policy.confirm_key_posted(key)
        self.assertTrue(policy._home_knowledge_scan_requested)

        # The fresh census resolves the catalogue blocker. With calibration
        # still absent, the normal bookkeeping producer posts the prepared C.
        catalogue = tuple(policy._inventory_item_from_store_item(item)
                          for item in page)
        policy.consume_home_knowledge(catalogue)
        key = policy.choose_key(home)
        self.assertEqual(key, HOME_CHARACTER_DUMP_MACRO)
        self.assertEqual(policy.decision_claim["owner"], "bookkeeping")
        self.assertEqual(policy.last_reason, "periodic:character-dump")
        policy.confirm_key_posted(key)
        self.assertIsNotNone(policy._calibration_dump_pending)
        self.assertIn("calibration",
                      policy._equipment_sale_session["prerequisite_attempted"])

        outside = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR), {}, [],
            town_flag=True, turn=1,
        )

        # A validated equipped calibration and available optimizer let the
        # same return build its saved list. Empty post-scan stock keeps this
        # focused on prerequisite acquisition rather than sale classification.
        policy._equipment_catalog.complete_home_scan(())
        policy._home_knowledge_current = True
        policy._home_knowledge_invalidated = False
        policy._warrior_evaluator_cache = SimpleNamespace(evaluator=object())
        with (patch.object(policy, "_validated_character_calibration",
                           return_value=SimpleNamespace(
                               intrinsic_abilities=frozenset())),
              patch.object(policy, "_prepare_equipment_optimization",
                           return_value=SimpleNamespace()),
              patch("hengbot.policy_equipment.classify_equipment_sales",
                    return_value=EquipmentSaleClassification(
                        frozenset(), frozenset(), frozenset(), {}, {},
                    ))):
            policy._build_equipment_sale_session(outside)
        self.assertTrue(policy._equipment_sale_session["built"])
        self.assertIsNone(policy._equipment_sale_session["blocker"])
        self.assertEqual(policy._equipment_sale_session["items"], [])

    def test_restored_sale_session_without_new_fields_gets_bounded_defaults(self):
        policy = HengbotPolicy()
        policy._equipment_sale_session = {
            "built": False, "items": [], "attempted": set(),
            "withdrawals": 0, "refused": set(), "active_store": None,
            "blocker": "calibration-required",
        }
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        outside = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR), {}, [],
            town_flag=True,
        )
        key = policy.choose_key(outside)
        self.assertEqual(key, "Cf\ry\x1b\x1b")
        self.assertEqual(
            policy._equipment_sale_session["prerequisite_attempted"],
            {"calibration"},
        )


if __name__ == "__main__":
    unittest.main()
