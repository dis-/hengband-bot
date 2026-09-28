"""Record-only #8 delegation identity and requester-set pins."""

import pickle
import unittest
from unittest.mock import patch

import tests  # noqa: F401 -- policy runtime isolation

from hengbot.equipment_transaction_planner import (
    EquipmentTransaction, EquipmentTransactionPlan, PHASE_EQUIP,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit
from test_ownership_s2b1_ladder import _Decisions
from test_calibration_restore_deposits_recorded import (
    recorded_rows, stripped_obligation,
)
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import parse_snapshot
from dataclasses import replace
from hengbot.home_errand import HomeErrandRequest


class DelegationRecordTest(unittest.TestCase):
    def test_calibration_strip_installer_records_exact_session(self):
        rows = recorded_rows()
        dressed = parse_snapshot(rows[0], {})
        spacious = replace(dressed, inventory=[])
        policy = HengbotPolicy()
        policy._calibration_worn_before = stripped_obligation(rows)
        self.assertTrue(policy._install_calibration_strip_session(spacious))
        session = policy._equipment_transaction_session
        token = policy._execution_delegations[-1]
        self.assertEqual((token.parent_family, token.delegate_family),
                         ("calibration", "equipment-txn"))
        self.assertEqual(token.work_identity[1], "strip")
        self.assertEqual(token.work_identity[2], session.target_loadout_id)
        self.assertEqual(len(token.work_identity[3]), len(session.plan.actions))
        self.assertEqual(token.lifecycle, "reserved")

    def test_calibration_restore_installer_records_exact_session(self):
        rows = recorded_rows()
        dressed = parse_snapshot(rows[0], {})
        lance = next(item for item in dressed.equipment
                     if item.slot == "main_hand")
        naked = replace(dressed, equipment=[],
                        inventory=[replace(lance, slot="a")])
        policy = HengbotPolicy()
        policy._calibration_worn_before = (
            ("main_hand", equipment_identity(lance)),
        )
        self.assertTrue(policy._install_calibration_restore_session(naked))
        token = policy._execution_delegations[-1]
        self.assertEqual((token.parent_family, token.delegate_family),
                         ("calibration", "equipment-txn"))
        self.assertEqual(token.work_identity[1], "restore")
        self.assertEqual(token.work_identity[2],
                         policy._equipment_transaction_session.target_loadout_id)
        self.assertEqual(len(token.work_identity[3]), 1)
        self.assertEqual(token.lifecycle, "reserved")

    def test_town_family_producers_probe_existing_holder_at_entry(self):
        decisions = _Decisions()
        policy = decisions.policy
        board = decisions.board
        with patch.object(policy, "_claim_errand_hold", return_value=None) as hold:
            policy._town_equipped_identification_key(board)
            policy._town_device_processing_key(board)
            policy._town_enchant_launcher_key(board)
            policy._town_remove_curse_key(board)
            policy._morivant_full_identify_key(board)
            policy._cross_town_shopping_key(board)
        families = [call.args[0] for call in hold.call_args_list]
        self.assertGreaterEqual(families.count("identification"), 2)
        self.assertGreaterEqual(families.count("curse-enchant"), 2)
        self.assertGreaterEqual(families.count("cross-town"), 2)

    def test_rumor_branch_probes_holder_before_selecting_key(self):
        decisions = _Decisions()
        policy = decisions.policy
        policy._rumor_unlock_pending = True
        policy._town_travel_rumor_pending = 1
        with patch.object(policy, "_claim_errand_hold", return_value=None) as hold:
            policy._town_special_key(decisions.board)
        self.assertIn("rumor", [call.args[0] for call in hold.call_args_list])

    def test_session_child_binds_to_existing_parent_and_exact_session(self):
        decisions = _Decisions()
        held = decisions.decide("calibration:restore-wield")
        policy = decisions.policy
        action = EquipmentTransaction(
            PHASE_EQUIP, "equip", "calibration-restore:body", "body", "item-a"
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        policy._equipment_transaction_session = session
        work = ("session", "restore", session.target_loadout_id,
                ((action.kind, action.target_slot, action.item_identity),))
        token = policy._open_execution_delegation(
            "calibration", "equipment-txn", work, ("calibration", "restore"),
            "observed-equips", "claim-bound/equipment-confirmation-limit",
        )
        self.assertEqual(token.lifecycle, "reserved")
        self.assertIsNone(token.parent_claim_id)
        policy.last_reason = "calibration:restore-wield"
        policy._record_decision_claim(decisions.board, "k")
        self.assertEqual(token.parent_claim_id, held["claim_id"])
        self.assertEqual(token.lifecycle, "open")
        holder = policy._claim_errand_hold("equipment-txn")
        self.assertIs(policy._recorded_execution_token(
            holder, "equipment-txn", "town-key"), token)
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((), (), 1)
        )
        self.assertIsNone(policy._recorded_execution_token(
            holder, "equipment-txn", "town-key"))
        token.lifecycle = "released"
        policy._equipment_transaction_session = session
        self.assertIsNone(policy._recorded_execution_token(
            holder, "equipment-txn", "town-key"))
        restored = pickle.loads(pickle.dumps(policy))
        self.assertEqual(restored._execution_delegations[0].as_dict(),
                         token.as_dict())
        del restored._execution_delegations
        self.assertEqual(restored._delegation_records(), [])

    def test_unbound_reservation_cancels_at_different_exit(self):
        decisions = _Decisions()
        policy = decisions.policy
        policy._decision_sequence += 1
        token = policy._open_execution_delegation(
            "calibration", "equipment-txn", ("session", "strip", "x", ()),
            ("calibration", "strip"), "takeoffs", "claim-bound",
        )
        self.assertEqual(token.lifecycle, "reserved")
        policy.last_reason = "shop:approach"
        policy._record_decision_claim(decisions.board, "9")
        self.assertEqual(token.lifecycle, "released")
        self.assertEqual(token.ending, "exit-owner-mismatch")

    def test_reservation_without_a_claim_exit_is_cancelled_by_name(self):
        decisions = _Decisions()
        policy = decisions.policy
        token = policy._open_execution_delegation(
            "calibration", "equipment-txn", ("session", "strip", "orphan", ()),
            ("calibration", "strip"), "takeoffs", "claim-bound",
        )
        policy._bind_execution_delegations(None)
        self.assertEqual((token.work_identity, token.lifecycle, token.ending),
                         (("session", "strip", "orphan", ()),
                          "released", "exit-owner-mismatch"))

    def test_generic_scan_cannot_borrow_named_knowledge_child(self):
        decisions = _Decisions()
        held = decisions.decide("home-errand:request-knowledge:combat-weapon")
        policy = decisions.policy
        token = policy._open_execution_delegation(
            "home-errand", "home-scan",
            ("knowledge", 1, ("weapon", 1, 2), "combat-weapon"),
            ("home-request", "combat-weapon", ("weapon", 1, 2)),
            "catalogue-adopted", "home-knowledge-existing-epoch",
        )
        self.assertEqual(token.lifecycle, "reserved")
        policy.last_reason = "home-errand:request-knowledge:combat-weapon"
        policy._record_decision_claim(decisions.board, "k")
        self.assertEqual(token.parent_claim_id, held["claim_id"])
        holder = policy._claim_errand_hold("home-scan")
        self.assertIsNone(policy._recorded_execution_token(
            holder, "home-scan", "outside-scan"))
        policy._home_errand.file(
            HomeErrandRequest(("weapon", 1, 2), 1, "home-page",
                              "combat-weapon"),
            knowledge_current=False,
        )
        self.assertIs(policy._recorded_execution_token(
            holder, "home-scan", "choose-key-scan"), token)
        policy._home_atomic_deposit_pending = ("pending",)
        self.assertIsNone(policy._recorded_execution_token(
            holder, "home-scan", "choose-key-scan"))

    def test_filed_home_request_needs_matching_parent_and_purpose(self):
        decisions = _Decisions()
        held = decisions.decide("equipment-transaction:await-confirmation")
        policy = decisions.policy
        work = ("filed", ("weapon", 1, 2), 1, "home-page", "combat-weapon")
        token = policy._open_execution_delegation(
            "equipment-txn", "home-errand", work,
            ("combat-weapon", ("weapon", 1, 2)),
            "filed-home-request", "equipment/home-errand-existing-budget",
        )
        self.assertEqual(token.lifecycle, "reserved")
        policy._home_errand.file(
            HomeErrandRequest(("weapon", 1, 2), 1, "home-page",
                              "combat-weapon"),
            knowledge_current=False,
        )
        policy.last_reason = "equipment-transaction:await-confirmation"
        policy._record_decision_claim(decisions.board, "k")
        self.assertEqual(token.parent_claim_id, held["claim_id"])
        holder = policy._claim_errand_hold("home-errand")
        self.assertIs(policy._recorded_execution_token(
            holder, "home-errand", "file-combat-weapon",
            work_identity=work,
        ), token)
        self.assertIsNone(policy._recorded_execution_token(
            holder, "home-errand", "file-combat-weapon",
            work_identity=("filed", ("other", 1, 2), 1,
                           "home-page", "combat-weapon"),
        ))
        action = EquipmentTransaction(
            PHASE_EQUIP, "equip", "weapon", "main_hand", "weapon"
        )
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1)
        )
        self.assertIsNone(policy._recorded_execution_token(
            holder, "home-errand", "file-combat-weapon",
            work_identity=work,
        ))
        policy._equipment_transaction_session = None
        policy._store_visit = StoreVisit(
            owner="equipment-transaction", purpose="equipment-work",
            store_type=STORE_HOME, operation_posted=True,
        )
        self.assertIsNone(policy._recorded_execution_token(
            holder, "home-errand", "file-combat-weapon",
            work_identity=work,
        ))
        policy._store_visit = None
        policy._home_atomic_withdraw_pending = ("pending",)
        self.assertIsNone(policy._recorded_execution_token(
            holder, "home-errand", "file-combat-weapon",
            work_identity=work,
        ))

    def test_requester_set_survives_reused_visit_and_checkpoint(self):
        decisions = _Decisions()
        policy = decisions.policy
        visit = StoreVisit(
            owner="store-router", purpose="shopping", store_type=STORE_HOME,
            opened_sequence=1, requester_families=frozenset({"shop-buy"}),
        )
        policy._store_visit = visit
        policy._request_store_trip(STORE_HOME, "home-visit")
        self.assertEqual(visit.requester_families,
                         frozenset({"shop-buy", "home-visit"}))
        route = next(record for record in policy._execution_delegations
                     if record.work_identity[:1] == ("route",))
        self.assertEqual(route.work_identity,
                         ("route", 1, STORE_HOME))
        self.assertEqual(route.purpose_identity,
                         ("trip", "home-visit", "shopping", STORE_HOME))
        restored = pickle.loads(pickle.dumps(policy))
        self.assertEqual(restored._store_visit.requester_families,
                         visit.requester_families)
        del restored._store_visit.requester_families
        restored._request_store_trip(STORE_HOME, "home-errand")
        self.assertEqual(restored._store_visit.requester_families,
                         frozenset({"home-errand"}))

    def test_calibration_deposit_requires_registered_candidate(self):
        decisions = _Decisions()
        policy = decisions.policy
        decisions.decide("calibration:restore-wield")
        signature = ("calibration-item", 1, 2)
        policy._calibration_restore_signatures = [signature]
        policy._home_atomic_deposit_pending = (((signature, 1, 1),), None, 1, 0)
        self.assertTrue(policy._compose_home_operation(
            decisions.board, "key", "da\r\x1b", producer_family="calibration"
        ))
        self.assertFalse(any(record.work_identity[:1] == ("home-operation",)
                             for record in policy._execution_delegations))
        policy._store_visit = None
        policy._open_execution_delegation(
            "calibration", "home-visit", ("deposit-candidate", signature),
            ("calibration", "deposit"), "inventory-effect", "home-visit",
        )
        self.assertTrue(policy._compose_home_operation(
            decisions.board, "key", "da\r\x1b", producer_family="calibration"
        ))
        operation = next(record for record in policy._execution_delegations
                         if record.work_identity[:1] == ("home-operation",))
        self.assertEqual(operation.work_identity[1:],
                         policy._store_visit.claim_operation_identity)

    def test_filed_home_errand_opens_knowledge_child_before_scan(self):
        decisions = _Decisions()
        policy = decisions.policy
        request = HomeErrandRequest(
            ("weapon", 1, 2), 1, "home-page", "combat-weapon"
        )
        self.assertTrue(policy._file_home_errand(
            decisions.board, request, knowledge_current=False,
        ))
        records = policy._execution_delegations
        self.assertEqual(
            {(record.parent_family, record.delegate_family)
             for record in records},
            {("home-errand", "home-errand"),
             ("home-errand", "home-scan")},
        )
        self.assertEqual(records[0].work_identity,
                         ("filed", request.signature, 1,
                          "home-page", "combat-weapon"))

    def test_staged_tail_names_exact_visit_operation(self):
        decisions = _Decisions()
        policy = decisions.policy
        decisions.decide("home:atomic-deposit")
        self.assertTrue(policy._stage_home_operation(
            decisions.board, "di3\r\x1b", producer_family="home-visit"
        ))
        tail = next(record for record in policy._execution_delegations
                    if record.delegate_family == "home-tail")
        self.assertEqual(tail.work_identity[1:],
                         policy._store_visit.claim_operation_identity)
        self.assertFalse(policy._store_visit.operation_released)
        self.assertEqual(tail.lifecycle, "reserved")
        policy.last_reason = "home:atomic-deposit"
        policy._record_decision_claim(decisions.board, "k")
        policy._store_visit.operation_effect_observed = True
        policy._observe_execution_delegations()
        self.assertEqual((tail.lifecycle, tail.ending),
                         ("completed", "home-operation-effect-observed"))
