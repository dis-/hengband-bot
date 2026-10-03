"""Recorded outside-Home projection and DECLARED CONSTRUCTED continuations.

A1159:262 and A1702:232 supply the actual immutable action plans and item
boards. The small public corridor pins intentionally omit unrelated town
supplies; this is independent-seam replay, not a continuous live trajectory.
Reverting the context projection reintroduces a Home route for these actions.
"""
import ast
from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession, observe_equipment_transactions
from hengbot.model import parse_snapshot, Position, STORE_HOME
from hengbot.policy import HengbotPolicy
from policy_fixtures import grid
from test_s33_batch_admission import FIXTURE, corridor, route_policy


def captured_session(stamp, line):
    pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    pin = next(pin for pin in pins if stamp in pin["source"] and pin["line"] == line)
    actions = []
    for text in pin["row"]["claim"]["goal"]["expectation"]:
        if "EquipmentTransaction(" not in text:
            continue
        for action in ast.literal_eval(text):
            node = ast.parse(action, mode="eval").body
            actions.append(EquipmentTransaction(**{
                keyword.arg: ast.literal_eval(keyword.value) for keyword in node.keywords}))
    return pin, EquipmentTransactionSession(EquipmentTransactionPlan(tuple(actions), (), 0))


class ContextTest(unittest.TestCase):
    def test_recorded_outside_action_is_not_a_home_need(self):
        for stamp, line in (("115941", 262), ("170231", 232)):
            with self.subTest(capture=stamp):
                pin, session = captured_session(stamp, line)
                self.assertEqual(session.required_context, "outside_home")
                board = parse_snapshot(pin["board"])
                policy = HengbotPolicy()
                policy.prime(board)
                policy._equipment_transaction_session = session
                self.assertFalse(policy._equipment_transaction_home_work())
                self.assertTrue(policy._outstanding_equipment_work())
                self.assertFalse(policy._equipment_work_home_route_available())
                self.assertNotIn("equipment-transaction", {
                    need.category for need in policy._enumerate_live_store_claims(board)})

    def test_same_family_foreign_work_uses_the_same_off_on_admission(self):
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                pin, session = captured_session("115941", 262)
                board = corridor()
                policy = HengbotPolicy()
                policy.prime(board)
                policy._map_predicate_snapshot = board
                policy._town_claim_bar_enforced = enforced
                policy._equipment_transaction_session = session
                holder = policy._claim_register.declare(
                    "equipment-txn", observe(("physical-session",), 8, source="transaction"),
                    floor=board.floor_key)
                mutations = []
                def foreign():
                    mutations.append("inscription")
                    policy.last_reason = "equipment:suppress-random-teleport"
                    return "{a.\r"
                key = policy._town_producer_entry(
                    "_town_random_teleport_suppression_key", foreign)
                self.assertEqual(mutations, [] if enforced else ["inscription"])
                row = policy._decision_errand_deferred[0]
                self.assertEqual(row["holder_claim_id"], holder.claim_id)
                self.assertFalse(row["token_would_admit"])
                if not enforced:
                    self.assertEqual(row["producer_key"], key)
                self.assertEqual(key, None if enforced else "{a.\r")

    def test_extra_2341_has_real_home_deposits_not_outside_work(self):
        # Recorded controls, not a reconstructed executor checkpoint. The
        # preceding Home operation's effect checkpoint is absent, so no later
        # board is replayed. STORE_HOME is 7, not a foreign store.
        for stamp, line in (("234018", 224), ("234047", 223), ("234116", 219)):
            with self.subTest(capture=stamp):
                pin, session = captured_session(stamp, line)
                self.assertEqual(session.current_action.kind, "deposit")
                self.assertEqual(session.required_context, "home")
                policy = HengbotPolicy()
                policy._equipment_transaction_session = session
                self.assertTrue(policy._equipment_transaction_home_work())
                self.assertEqual(pin["row"]["store_visit"]["store_type"], STORE_HOME)
                pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
                onset = next(row for row in pins if stamp in row["source"]
                             and row["row"].get("decision_sequence") == 3)
                self.assertEqual(onset["row"]["reason"], "home:weight-overload-deposit")
                self.assertEqual(onset["row"]["store_type"], STORE_HOME)
                self.assertTrue(onset["row"]["store_visit"]["operation_posted"])
                self.assertTrue(onset["row"]["store_visit"]["operation_released"])
                self.assertFalse(onset["row"]["store_visit"]["operation_effect_observed"])
                self.assertEqual(pin["row"]["town_emit_ownership"]["in_flight_clause"],
                                 "operation-released-effect-not-observed")
                # DECLARED CONSTRUCTED admission seam: the executor checkpoint
                # is absent. A survival interruption is admitted on these real
                # item facts; this does not prove the preceding Home operation effect.
                observed = parse_snapshot(pin["board"])
                board = replace(corridor(), inventory=observed.inventory,
                                equipment=observed.equipment,
                                player=replace(observed.player, position=Position(10, 10)))
                policy = HengbotPolicy()
                policy.prime(board)
                policy._equipment_transaction_session = session
                policy._town_claim_bar_enforced = True
                holder = policy._claim_register.declare(
                    "equipment-txn", observe(("recorded-deposit",), 8, source="transaction"),
                    floor=board.floor_key)
                action = session.current_action
                policy._claim_register.declare_execution(
                    holder.claim_id, producer="equipment-txn",
                    work_id=f"equipment:{session.target_loadout_id}:0", state="acting",
                    next_step="equipment.next-action",
                    arguments=(action.kind, action.target_slot, action.item_identity),
                    expected_effect="equipment-action-confirmed", continuation="equipment.next-action")
                low = replace(board, player=replace(board.player, hp=1))
                key = policy.choose_key(low)
                self.assertTrue(policy.decision_claim["survival"])
                self.assertIsNone(policy.decision_claim["declaration_mismatch"])
                self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
                self.assertIsNone(policy._s33_shadow_verdict(low, key)["would_stop"])

    def test_outside_takeoff_runs_through_choose_key(self):
        for stamp, line in (("115941", 262), ("170231", 232)):
            with self.subTest(capture=stamp):
                pin, session = captured_session(stamp, line)
                recorded = parse_snapshot(pin["board"])
                inventory, equipment = recorded.inventory, recorded.equipment
                action = session.current_action
                if not any(gear.slot == action.target_slot for gear in equipment):
                    # A1702's available item board already carries this exact
                    # pick. DECLARED CONSTRUCTED precondition: put that actual
                    # item back in its planned slot, before takeoff. This is
                    # not an onset checkpoint or a replay of old command effects.
                    gear = next(gear for gear in inventory
                                if equipment_identity(gear) == action.item_identity)
                    inventory = tuple(other for other in inventory if other is not gear)
                    equipment = (*equipment, replace(gear, slot=action.target_slot))
                board = replace(corridor(), inventory=inventory, equipment=equipment)
                policy = HengbotPolicy()
                policy.prime(board)
                policy._home_knowledge_current = True
                policy._equipment_catalog.home_scan_complete = True
                policy._town_claim_bar_enforced = True
                policy._equipment_transaction_session = session
                session.opened_sequence = 1
                claim = policy._claim_register.declare(
                    "equipment-txn", observe(("recorded-session",), 8, source="transaction"),
                    floor=board.floor_key)
                policy._claim_register.declare_execution(
                    claim.claim_id, producer="equipment-txn", work_id="equipment:outside",
                    state="acting", next_step="equipment.next-action",
                    expected_effect="equipment-action-confirmed", continuation="equipment.next-action")
                key = policy.choose_key(board)
                self.assertEqual(policy.last_reason, "equipment-transaction:takeoff")
                self.assertTrue(key.startswith("t"), repr(key))
                self.assertIs(policy._equipment_transaction_session, session)
                self.assertIsNone(policy.decision_claim["declaration_mismatch"])
                self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
                self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])

    def test_posted_action_needs_observation_then_home_for_deposit(self):
        pin, session = captured_session("115941", 262)
        board = parse_snapshot(pin["board"])
        policy = HengbotPolicy()
        policy._equipment_transaction_session = session
        self.assertTrue(session.dispatch(session.current_action,
                                         observe_equipment_transactions(replace(board, store=None))))
        self.assertFalse(policy._equipment_transaction_home_work())
        # DECLARED CONSTRUCTED postcondition: action two already observed. The
        # remaining real captured action is a Home deposit, not outside equip.
        session._dispatched = None
        session.index = 2
        self.assertEqual(session.current_action.kind, "deposit")
        self.assertTrue(policy._equipment_transaction_home_work())

    def test_arrived_route_is_not_a_shadow_holder(self):
        board = corridor()
        policy = route_policy(board, enforced=False)
        arrived = replace(board, player=replace(board.player, position=Position(10, 14)))
        policy.last_reason = "home:request-knowledge-scan"
        self.assertIsNone(policy._town_errand_deferral("home-scan", "entry", arrived))
        self.assertIsNone(policy._s33_shadow_verdict(arrived, "~9\x1b\x1b")["would_stop"])
        # The pure shadow check must not complete or change the recorded claim.
        self.assertTrue(policy._claim_register.current.is_open)

    def test_survival_resumes_the_same_posted_equipment_route(self):
        # DECLARED CONSTRUCTED analogue of A1825:200-216: survival intervenes
        # in a posted Home route. No invented effect boards after a changed key.
        board = corridor()
        policy = route_policy(board, family="equipment-txn")
        claim = policy._claim_register.current
        policy._claim_register.declare_execution(
            claim.claim_id, producer="equipment-txn", work_id="route:constructed",
            state="awaiting", arguments=("store", (10, 14)),
            operation_ref="decision:0:6", expected_effect="arrive",
            continuation="route.resume", budget_ref="town-travel")
        low = replace(board, player=replace(board.player, hp=1))
        self.assertEqual(policy.choose_key(low), "R&\r")
        self.assertEqual(policy.decision_claim["suspended_depth"], 1)
        healthy = replace(board, turn=101)
        key = policy.choose_key(healthy)
        self.assertEqual(key, "6")
        self.assertIsNone(policy._s33_shadow_verdict(healthy, key)["would_stop"])
        self.assertEqual(policy.last_reason, "equipment-transaction:travel-home")
        self.assertEqual(policy.decision_claim["claim_id"], claim.claim_id)
        self.assertEqual(policy._claim_register.current.budget, claim.budget)
        self.assertEqual(policy._claim_register.current.execution.budget_ref, "town-travel")
        self.assertEqual(policy.decision_claim["suspended_depth"], 0)
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])

    def test_home_route_completes_on_observed_arrival(self):
        # DECLARED CONSTRUCTED A1204:223-226 completion seam; no session or
        # restoration debt remains. The route itself closes before admission.
        board = corridor()
        policy = route_policy(board)
        goal = Position(10, 14)
        claim_id = policy._claim_register.current.claim_id
        arrived = replace(board, turn=101, player=replace(board.player, position=goal))
        key = policy.choose_key(arrived)
        self.assertIsNone(policy._s33_shadow_verdict(arrived, key)["would_stop"])
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy._claim_errand_hold("home-visit"))
        self.assertEqual(policy.decision_claim["closed_claim"]["claim_id"], claim_id)
        self.assertEqual(policy.decision_claim["closed_claim"]["closed_reason"], "reached")
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])


if __name__ == "__main__":
    unittest.main()
