"""DECLARED CONSTRUCTED R13 boards on the game's real Outpost map.

The tracked decision projection supplies coordinates, commands and owner order,
not state or executor checkpoints. Combat movement and the item confirmation
seam below are constructed. No game data is copied into this repository.
"""
import tests  # noqa: F401
import base64
import copy
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import cli
from hengbot.claim_register import reach
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession, observe_equipment_transactions
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import Position, StoreState, STORE_HOME, TVAL_LITE, SV_LITE_LANTERN
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_types import StoreVisit
from policy_fixtures import item
from test_surface_map_walks import _board, _policy

FIXTURES = Path(__file__).parent / "fixtures"
TRAVEL = "equipment-transaction:travel-home"
APPROACH = "equipment-transaction:approach-home"
AWAIT = TRAVEL + ":await-entry"
HOME = Position(45, 123)
NATIVE = "\x1b`n(."


def home_policy(kind="withdraw", *, staged=False):
    policy = _policy()
    target = item("d", TVAL_LITE, SV_LITE_LANTERN, name="constructed lantern", is_equipment=True)
    action = EquipmentTransaction("equip" if staged else "home_prepare", kind,
                                  "home:constructed:0", "light" if staged else None,
                                  equipment_identity(target))
    policy._equipment_transaction_session = EquipmentTransactionSession(
        EquipmentTransactionPlan((action,), (), 14),
        physical_context="home" if staged else "legacy")
    return policy, target


def home_visit(policy, goal=HOME):
    policy._store_visit = StoreVisit(owner="equipment-transaction",
                                    purpose="equipment-work", store_type=STORE_HOME, goal=goal)


def emit(policy, at, reason, key=NATIVE, *, store=None, inventory=()):
    board = replace(_board(0, at, turn=1000 + policy._decision_sequence,
                           inventory=inventory), store=store)
    policy.prime(board)
    def proposal(_board, *_args):
        policy.last_reason = reason
        if reason in {TRAVEL, APPROACH, AWAIT}:
            home_visit(policy)
            policy._declare_reach(HOME, family="equipment-txn")
        return key
    # Isolate one producer boundary, as the existing INN pins do. Preview,
    # final arbiter accounting and the CLI consume production observations.
    boundary = "_equipment_transaction_home_key" if store is not None else "_fixed_quest_key"
    with patch.object(policy, boundary, side_effect=proposal), \
            patch.object(policy, "_departure_supplier_counterfactual", return_value=None):
        selected = policy.choose_key(board)
    cli._observe_owner_retired_progress(policy, board, selected)
    return selected, board, policy._town_turn_arbiter.telemetry


class HomeInterruptionTest(unittest.TestCase):
    def test_r13_history_and_resumed_native_route_entry_take_once(self):
        pins = json.loads((FIXTURES / "d2b-r13-decision-pins.json").read_text(encoding="utf-8"))
        resumed = next(row for row in pins if row["source_line"] == 9902)
        self.assertEqual((resumed["key"], resumed["reason"]), (NATIVE, TRAVEL))
        self.assertTrue(resumed["arbiter"]["retired"])
        policy, target = home_policy()
        session = policy._equipment_transaction_session
        for at, reason, key in [((46, 83), TRAVEL, NATIVE),
                               ((47, 101), "town:kill-mob-approach", "8"),
                               ((46, 101), "town:kill-mob-approach", "8"),
                               ((45, 101), "melee", "9")]:
            emit(policy, at, reason, key)
        policy._owner_retired_no_progress_count = 2
        selected, _, telemetry = emit(policy, (45, 101), TRAVEL)
        self.assertEqual((str(selected), policy.last_reason), (NATIVE, TRAVEL))
        self.assertFalse(telemetry["retired"])
        self.assertFalse(telemetry["progress"])
        receipt = policy._town_inn_accounting["receipt"]
        self.assertTrue(receipt["rebaseline"])
        self.assertEqual(policy._owner_retired_no_progress_count, 2)
        self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner["equipment-txn"], 1)
        pack = [item(chr(97 + i), TVAL_LITE, SV_LITE_LANTERN,
                     name=f"constructed pack lantern {i}") for i in range(13)]
        selected, before, _ = emit(policy, (45, 123), "equipment-transaction:withdraw",
                                   "pd1\r", store=StoreState(STORE_HOME), inventory=pack)
        self.assertEqual(str(selected), "pd1\r")
        self.assertTrue(policy._town_inn_accounting["receipt"]["productive"])
        self.assertTrue(policy._town_inn_accounting["routes"]["equipment-txn"]["entered"])
        self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner["equipment-txn"], 0)
        self.assertEqual(policy._owner_retired_no_progress_count, 0)
        # Constructed executor dispatch/effect seam: a real session consumes
        # this exact withdrawal only after the observed 13 -> 14 pack delta.
        self.assertTrue(session.dispatch(session.current_action, observe_equipment_transactions(before)))
        after = replace(before, inventory=pack + [target], turn=before.turn + 1)
        self.assertEqual((len(before.inventory), len(after.inventory)), (13, 14))
        self.assertTrue(session.observe(observe_equipment_transactions(after)))
        self.assertTrue(session.complete)
        self.assertFalse(session.observe(observe_equipment_transactions(after)))
        policy._decision_sequence += 1
        duplicate = policy._town_inn_route_receipt(after, "equipment-transaction:withdraw", "pd1\r", consume=True)
        self.assertFalse(duplicate["productive"])
        self.assertIsNone(duplicate["settled_owner"])
        arrival = next(row for row in pins if row["source_line"] == 9903)
        gain = next(row for row in pins if row["source_line"] == 9904)
        self.assertEqual((arrival["key"], arrival["inventory"]["used"], gain["inventory"]["used"]),
                         ("pd1\r", 13, 14))

    def test_physical_aliases_and_home_context_staged_work_register_bfs(self):
        for kind, staged in [("withdraw", False), ("deposit", False), ("equip", True)]:
            for reason in [TRAVEL, APPROACH, AWAIT]:
                with self.subTest(kind=kind, reason=reason):
                    policy, _ = home_policy(kind, staged=staged)
                    board = _board(0, (46, 83))
                    policy.prime(board)
                    home_visit(policy)
                    route = policy._town_map_goal_route(board, HOME)
                    vector = policy._town_arbiter_progress_vector(board, reason)
                    self.assertEqual(vector[-1], ("locomotion", "equipment-txn", board.floor_key,
                                                HOME, route.remaining_edges))
                    key = NATIVE if reason == TRAVEL else "6" if reason == APPROACH else "5"
                    if reason == AWAIT:
                        board = _board(0, (45, 123))
                        policy.prime(board)
                        home_visit(policy)
                    policy._decision_sequence += 1
                    receipt = policy._town_inn_route_receipt(board, reason, key, consume=True)
                    self.assertEqual(receipt["owner"], "equipment-txn")
                    self.assertTrue(receipt["qualified"])

    def test_prior_native_effect_settles_before_other_owner_and_cli(self):
        policy, _ = home_policy()
        emit(policy, (46, 83), TRAVEL)
        emit(policy, (46, 83), TRAVEL)
        self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner["equipment-txn"], 1)
        policy._owner_retired_no_progress_count = 2
        emit(policy, (47, 101), "town:kill-mob-approach", "8")
        receipt = policy._town_inn_accounting["receipt"]
        self.assertTrue(receipt["productive"])
        self.assertEqual(receipt["settled_owner"], "equipment-txn")
        self.assertGreater(receipt["minimum_before"], receipt["minimum_after"])
        self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner["equipment-txn"], 0)
        self.assertEqual(policy._owner_retired_no_progress_count, 0)
        self.assertEqual(policy._owner_retired_progress["last_settlement"]["operation_identity"],
                         receipt["operation_identity"])
        # The settled child is named as the physical Home action, not a teleport.
        self.assertIn("equipment-home", receipt["operation_identity"])
        self.assertNotIn("teleport", receipt["operation_identity"])

    def test_stationary_and_own_bounce_retire_within_eight_unsuccessful_decisions(self):
        for positions in [[(45, 101)], [(46, 101), (44, 101)]]:
            with self.subTest(positions=positions):
                policy, _ = home_policy()
                emit(policy, positions[0], TRAVEL)
                for own in range(1, 9):
                    _, _, telemetry = emit(policy, positions[own % len(positions)], TRAVEL)
                    self.assertFalse(telemetry["progress"])
                    self.assertFalse(policy._town_inn_accounting["receipt"]["rebaseline"])
                    if telemetry["retired"]:
                        break
                self.assertTrue(telemetry["retired"])
                self.assertLessEqual(own, 8)
                self.assertEqual(policy._town_turn_arbiter._retirement_diagnostic["trigger_category"], "budget")

    def test_external_baseline_preserves_spent_budget_and_is_consumed_once(self):
        policy, _ = home_policy()
        emit(policy, (45, 101), TRAVEL)
        emit(policy, (45, 101), TRAVEL)
        emit(policy, (45, 101), "melee", "9")
        board = _board(0, (45, 102))
        policy.prime(board)
        home_visit(policy)
        policy._decision_sequence += 1
        before = copy.deepcopy(policy._town_inn_accounting)
        preview = policy._town_inn_route_receipt(board, TRAVEL, NATIVE)
        self.assertTrue(preview["rebaseline"])
        self.assertFalse(preview["productive"])
        self.assertEqual(policy._town_inn_accounting, before)
        receipt = policy._town_inn_route_receipt(board, TRAVEL, NATIVE, consume=True)
        self.assertEqual(receipt, preview)
        self.assertEqual(policy._town_inn_route_receipt(board, TRAVEL, NATIVE, consume=True), receipt)
        self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner["equipment-txn"], 1)
        policy._decision_sequence += 1
        second = policy._town_inn_route_receipt(board, TRAVEL, NATIVE, consume=True)
        self.assertFalse(second["rebaseline"])
        self.assertFalse(second["progress"])

    def test_external_no_closing_route_still_retires_at_eight(self):
        policy, _ = home_policy()
        emit(policy, (45, 101), TRAVEL)
        emit(policy, (45, 101), "melee", "9")
        for own in range(1, 9):
            _, _, telemetry = emit(policy, (45, 102), TRAVEL)
            self.assertEqual(telemetry["retired"], own == 8)
            self.assertFalse(telemetry["progress"])
        self.assertEqual(policy._town_turn_arbiter._retirement_diagnostic["own_unsuccessful_count"], 8)

    def test_stationary_safety_save_alias_and_retarget_earn_no_baseline(self):
        for change in ["survival:mana-absorb", "periodic:save", "melee", "alias", "retarget"]:
            with self.subTest(change=change):
                policy, _ = home_policy()
                emit(policy, (45, 101), TRAVEL)
                if change in {"alias", "retarget"}:
                    emit(policy, (45, 101), "melee", "9")
                    at = (45, 102)
                else:
                    emit(policy, (45, 101), change, "5")
                    at = (45, 101)
                board = _board(0, at)
                policy.prime(board)
                home_visit(policy, Position(45, 124) if change == "retarget" else HOME)
                policy._decision_sequence += 1
                receipt = policy._town_inn_route_receipt(board, TRAVEL + "-renamed" if change == "alias" else TRAVEL,
                                                        NATIVE, consume=True)
                self.assertFalse(receipt["rebaseline"])
                self.assertFalse(receipt["productive"])
                if change in {"alias", "retarget"}:
                    self.assertFalse(receipt["progress"])

    def test_stationary_command_cannot_supply_an_own_edge(self):
        policy, _ = home_policy()
        emit(policy, (45, 101), TRAVEL)
        board = _board(0, (45, 101))
        policy.prime(board)
        home_visit(policy)
        policy._decision_sequence += 1
        policy._town_inn_route_receipt(board, TRAVEL, "5", consume=True)
        moved = _board(0, (45, 102))
        policy.prime(moved)
        home_visit(policy)
        policy._decision_sequence += 1
        receipt = policy._town_inn_route_receipt(moved, TRAVEL, NATIVE, consume=True)
        self.assertFalse(receipt["productive"])
        self.assertIsNone(receipt["settled_owner"])

    def test_await_entry_consumes_once_and_held_preview_uses_shared_receipt(self):
        policy, _ = home_policy()
        emit(policy, (45, 122), APPROACH, "6")
        emit(policy, (45, 123), AWAIT, "5")
        emit(policy, (45, 123), "equipment-transaction:withdraw", "pd1\r", store=StoreState(STORE_HOME))
        self.assertTrue(policy._town_inn_accounting["receipt"]["productive"])
        policy._decision_sequence += 1
        board = replace(_board(0, (45, 123)), store=StoreState(STORE_HOME))
        duplicate = policy._town_inn_route_receipt(board, "equipment-transaction:withdraw", "pd1\r", consume=True)
        self.assertFalse(duplicate["productive"])
        policy, _ = home_policy()
        emit(policy, (45, 101), TRAVEL)
        emit(policy, (45, 101), "melee", "9")
        emit(policy, (45, 102), TRAVEL)
        emit(policy, (45, 101), "melee", "9")
        holder = policy._claim_register.declare("equipment-txn", reach((45, 123)), floor=(0, 0, 0))
        with patch.object(policy, "_town_held_decision", return_value=holder):
            selected, _, telemetry = emit(policy, (45, 102), TRAVEL)
        self.assertEqual(str(selected), NATIVE)
        self.assertFalse(telemetry["retired"])
        self.assertFalse(telemetry["progress"])
        self.assertTrue(policy._town_inn_accounting["receipt"]["rebaseline"])

    def test_changed_action_opens_a_new_finite_entry_child(self):
        policy, target = home_policy()
        emit(policy, (45, 122), APPROACH, "6")
        _, before, _ = emit(policy, (45, 123), "equipment-transaction:withdraw", "pd1\r", store=StoreState(STORE_HOME))
        session = policy._equipment_transaction_session
        self.assertTrue(session.dispatch(session.current_action, observe_equipment_transactions(before)))
        self.assertTrue(session.observe(observe_equipment_transactions(replace(before, inventory=[target]))))
        old = policy._town_inn_accounting["routes"]["equipment-txn"]["operation"]
        action = EquipmentTransaction("home_finalize", "deposit", "pack:constructed:0", item_identity=equipment_identity(target))
        policy._equipment_transaction_session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 0))
        emit(policy, (45, 122), APPROACH, "6")
        self.assertNotEqual(policy._town_inn_accounting["routes"]["equipment-txn"]["operation"], old)
        emit(policy, (45, 123), "equipment-transaction:deposit", "sd1\r", store=StoreState(STORE_HOME))
        self.assertTrue(policy._town_inn_accounting["receipt"]["productive"])

    def test_full_home_closure_no_route_or_credit_and_catalogue_excluded(self):
        policy, _ = home_policy()
        emit(policy, (45, 101), TRAVEL)
        board = _board(0, (45, 123))
        policy.prime(board)
        home_visit(policy)
        policy._mark_equipment_home_full_unavailable(board)
        self.assertFalse(policy._equipment_work_home_route_available())
        self.assertIsNone(policy._town_equipment_home_route(board, TRAVEL))
        policy._decision_sequence += 1
        receipt = policy._town_inn_route_receipt(board, TRAVEL, NATIVE, consume=True)
        self.assertFalse(receipt["progress"])
        self.assertFalse(receipt["productive"])
        self.assertFalse(receipt["rebaseline"])
        fresh, _ = home_policy()
        fresh.prime(board)
        home_visit(fresh)
        for reason in ["equipment-transaction:acquire-home-catalog", "equipment-transaction:catalogue-request-knowledge"]:
            self.assertIsNone(fresh._town_equipment_home_route(board, reason))

    def test_no_path_no_credit_and_cli_cannot_use_a_fabricated_step(self):
        policy, _ = home_policy()
        claim = policy._claim_register.declare("equipment-txn", reach((45, 123)), floor=(0, 0, 0))
        policy._claim_register.declare_execution(claim.claim_id, work_id="constructed-home", producer="equipment-txn",
                                                 state="awaiting")
        with patch("hengbot.town_work.current_record", return_value={"work_id": "constructed-home"}):
            emit(policy, (45, 101), APPROACH, "6")
            policy._owner_retired_no_progress_count = 2
            _, _, telemetry = emit(policy, (45, 110), APPROACH, "6")
        self.assertFalse(telemetry["progress"])
        self.assertEqual(policy._owner_retired_no_progress_count, 2)
        board = _board(0, (45, 111))
        policy.prime(board)
        home_visit(policy)
        policy._floor_t.clear()
        policy._door_t.clear()
        policy._rubble_t.clear()
        policy._decision_sequence += 1
        receipt = policy._town_inn_route_receipt(board, TRAVEL, NATIVE, consume=True)
        self.assertFalse(receipt["progress"])
        self.assertFalse(receipt["productive"])

    def test_return_to_consumed_entry_cannot_credit_or_rebaseline(self):
        policy, _ = home_policy()
        emit(policy, (45, 122), APPROACH, "6")
        emit(policy, (45, 123), "equipment-transaction:withdraw", "pd1\r", store=StoreState(STORE_HOME))
        self.assertTrue(policy._town_inn_accounting["receipt"]["productive"])
        emit(policy, (45, 122), "melee", "6")
        emit(policy, (45, 122), TRAVEL)
        emit(policy, (45, 123), "equipment-transaction:withdraw", "pd1\r", store=StoreState(STORE_HOME))
        self.assertFalse(policy._town_inn_accounting["receipt"]["productive"])
        self.assertFalse(policy._town_inn_accounting["receipt"]["rebaseline"])

    def test_restore_and_restart_have_no_home_route_memory(self):
        policy, _ = home_policy()
        emit(policy, (45, 101), TRAVEL)
        encoded = checkpoint(policy)
        self.assertNotIn("_town_inn_accounting", pickle.loads(base64.b64decode(encoded)))
        with patch("hengbot.latch_onset_capture.find_monrace_definitions",
                   return_value=FIXTURES / "d3b-empty-monrace.json"):
            restored = restore_checkpoint(type(policy), encoded)
        self.assertIsNone(restored._town_inn_accounting)
        normalize_policy_state(policy, restart=True)
        self.assertIsNone(policy._town_inn_accounting)
        fresh, _ = home_policy()
        emit(fresh, (45, 102), TRAVEL)
        self.assertFalse(fresh._town_inn_accounting["receipt"]["rebaseline"])
