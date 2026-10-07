"""Recorded 2026-10-07 refusal: do not repost a transaction deposit to a full Home."""
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.equipment_optimizer import (
    equipment_identity,
    equipment_move_identity,
    Loadout,
)
from hengbot.equipment_transaction_planner import (
    PHASE_HOME_FINALIZE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import parse_snapshot, STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import DOWN_STAIRS_KEY
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from hengbot.warrior_optimization import current_loadout

FIXTURE = Path(__file__).parent / "fixtures/equipment-home-full-20261007.json.gz"
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    "d633cdd4dd64fd317f986f0e089bda015cf8120d3a47d6d5cd0fed49458e1e3f"
)
BOARD = json.loads(gzip.decompress(FIXTURE.read_bytes()))["board"]


class EquipmentHomeFullIncidentRecordedTest(unittest.TestCase):
    def test_confirmation_stall_does_not_reapproach_a_blocked_home(self):
        board = parse_snapshot({**BOARD, "visible_monsters": [], "detected_monsters": []})
        board = replace(board, player=replace(
            board.player, two_weapon_skill=0, shield_skill=0,
        ))
        outside = replace(board, store=None)
        target = next(item for item in board.inventory if item.slot == "p")
        action = EquipmentTransaction(
            PHASE_HOME_FINALIZE, "deposit", "pack:recorded-requested-home:0", None,
            equipment_identity(target), equipment_move_identity(target),
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0), physical_context="home",
        )
        policy = HengbotPolicy()
        policy.prime(outside)
        policy._in_store_ops_enabled = True
        policy._town_claim_bar_enforced = True
        policy._equipment_transaction_session = session
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        # The live block came from the earlier refused full-Home deposit,
        # which records its reason with the Home block (7da1d2cf).
        policy._mark_equipment_home_full_unavailable(outside)
        policy._equipment_transaction_last_failure = {
            "reason": "confirmation-stall-bound",
        }

        with patch.object(policy, "_prepare_equipment_optimization", return_value=None):
            key = policy._equipment_transaction_town_key(outside)

        self.assertEqual(key, "5")
        self.assertEqual(policy.last_reason, "equipment-transaction:home-route-unavailable")
        self.assertIsNone(policy._store_visit)

    def test_full_home_ends_transaction_deposit_with_visible_reason(self):
        self.assertEqual(BOARD["turn"], 12986317)
        self.assertEqual(BOARD["store"]["stock_num"], BOARD["store"]["capacity"])
        board = parse_snapshot({**BOARD, "visible_monsters": [], "detected_monsters": []})
        board = replace(board, player=replace(
            board.player, two_weapon_skill=0, shield_skill=0,
        ))
        target = next(item for item in board.inventory if item.slot == "p")
        action = EquipmentTransaction(
            PHASE_HOME_FINALIZE, "deposit", "pack:recorded-full-home:0", None,
            equipment_identity(target), equipment_move_identity(target),
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0), physical_context="home",
        )
        session.block("deposit-refused")
        policy = HengbotPolicy()
        policy.prime(board)
        policy._in_store_ops_enabled = True
        policy._equipment_transaction_session = session
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        policy._store_visit = StoreVisit(
            "equipment-transaction", "equipment-work", STORE_HOME,
            StoreVisitPhase.OPERATING, opened_sequence=16,
        )

        key = policy.choose_key(board)

        self.assertNotEqual(key, "dp")
        self.assertEqual(policy.last_reason, "equipment-transaction:deposit-home-full")
        self.assertIn(action.item_id, policy._equipment_transaction_failed_items)
        self.assertIsNone(session.pending_action)
        self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(
            policy._town_store_attempted[STORE_HOME], board.turn
        )

        # Once the refused Home visit is observed as exited, the same town
        # state must not send the transaction back to the approach/ESC cycle.
        policy.confirm_key_posted(key)
        outside = replace(board, store=None)
        policy._equipment_catalog.refresh_carried(
            outside.inventory, outside.equipment
        )
        worn_loadout = current_loadout(policy._equipment_catalog.items)
        self.assertIsInstance(worn_loadout, Loadout)
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: reconstructs the recorded optimizer input key absent from the capture; the departure gate is the subject
        policy._equipment_optimizer_input_key = "recorded-home-full-input"
        preparation = SimpleNamespace(
            blockers=("equipment-transaction-failed",),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: the recorded board has no optimizer checkpoint; the worn loadout stands in for the confirmed-loadout gate under test
            result=SimpleNamespace(best=SimpleNamespace(loadout=worn_loadout)),
            transaction=None,
        )
        with TemporaryDirectory() as directory:
            policy._confirmed_loadout_path = Path(directory) / "confirmed.json"
            with patch.object(
                policy, "_prepare_equipment_optimization",
                return_value=preparation,
            ), patch.object(
                policy, "_missing_required_abilities", return_value=frozenset(),
            ):
                self.assertTrue(policy._equipment_departure_ready(outside))
                self.assertEqual(
                    policy._equipment_optional_failure_pending["reason"],
                    "optional-optimization-failure-confirmed-loadout",
                )
                with patch.object(
                    policy, "_missing_required_abilities", return_value=frozenset(),
                ):
                    policy._confirm_optional_equipment_failure_departure(
                        outside, DOWN_STAIRS_KEY
                    )
                self.assertEqual(
                    policy._equipment_optional_failure_departure["reason"],
                    "optional-optimization-failure-confirmed-loadout",
                )
                next_key = policy.choose_key(outside)
                self.assertNotIn(
                    policy.last_reason,
                    {
                        "equipment-transaction:approach-home",
                        "equipment-transaction:acquire-home-catalog",
                    },
                )
                self.assertNotEqual(next_key, "\x1b")
                self.assertNotIn(
                    policy._town_turn_arbiter.owner_for_reason(policy.last_reason),
                    (None, "unregistered", "equipment-txn"),
                )
        self.assertTrue(policy._equipment_optional_failure_departure["posted"])


if __name__ == "__main__":
    unittest.main()
