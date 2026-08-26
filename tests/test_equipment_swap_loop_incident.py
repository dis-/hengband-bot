import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.cli import POLICY_FINAL_STOP_REASONS
from hengbot.equipment_optimizer import equipment_identity
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    PHASE_HOME_FINALIZE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy, WAIT_KEY


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.jsonl"
SNAPSHOTS = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"
RAG = "8cc0213094bf60d5"
HARD_ARMOUR = "ba9b081829fa4479"
DIRECTIONS = {
    "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
    "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
}


def captured_decisions():
    with DECISIONS.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def captured_snapshots():
    with SNAPSHOTS.open(encoding="utf-8") as stream:
        rows = (json.loads(line) for line in stream)
        return [
            parse_snapshot(row, {}) for row in rows
            if 1172205 <= row.get("turn", 0) <= 1172926
        ]


class EquipmentSwapLoopIncidentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decisions = captured_decisions()
        cls.snapshots = captured_snapshots()

    def _surface(self, turn, body_identity):
        return next(
            snapshot for snapshot in self.snapshots
            if snapshot.turn == turn and snapshot.store is None
            and any(
                item.slot == "body" and equipment_identity(item) == body_identity
                for item in snapshot.equipment
            )
        )

    def _apply_posted_key(self, snapshot, key, action):
        """Apply the incident's command-loop physics to the replay state."""
        here = snapshot.grid_at(snapshot.player.position)
        if key == WAIT_KEY and here is not None and here.store_number >= 0:
            matches = [
                candidate for candidate in self.snapshots
                if candidate.turn == snapshot.turn and candidate.store is not None
                and candidate.store.store_type == here.store_number
            ]
            self.assertTrue(matches, (snapshot.turn, snapshot.player.position, key))
            return matches[0]
        if key == "\x1b" and snapshot.store is not None:
            matches = [
                candidate for candidate in self.snapshots
                if candidate.turn == snapshot.turn and candidate.store is None
                and candidate.player.position == snapshot.player.position
            ]
            self.assertTrue(matches, (snapshot.turn, snapshot.player.position, key))
            return matches[0]
        if key and key[-1] in DIRECTIONS:
            dy, dx = DIRECTIONS[key[-1]]
            position = snapshot.player.position
            return replace(
                snapshot,
                player=replace(
                    snapshot.player,
                    position=replace(position, y=position.y + dy, x=position.x + dx),
                ),
            )
        if action is not None and action.kind == "takeoff" and key.startswith("t"):
            worn = next(item for item in snapshot.equipment if item.slot == action.target_slot)
            pack_slot = next(letter for letter in "abcdefghijklmnopqrstuvwxyz" if all(
                item.slot != letter for item in snapshot.inventory
            ))
            return replace(
                snapshot,
                equipment=[item for item in snapshot.equipment if item is not worn],
                inventory=snapshot.inventory + [replace(worn, slot=pack_slot)],
            )
        if action is not None and action.kind == "equip" and key.startswith("w"):
            packed = next(
                item for item in snapshot.inventory
                if equipment_identity(item) == action.item_identity
            )
            return replace(
                snapshot,
                inventory=[item for item in snapshot.inventory if item is not packed],
                equipment=snapshot.equipment + [replace(packed, slot=action.target_slot)],
            )
        return snapshot

    def test_captured_window_replay_cannot_recur_or_swap_armour_twice(self):
        captured_cycle = [
            "equipment-transaction:takeoff",
            "equipment-transaction:equip",
            "equipment-transaction:home-route-unavailable",
            "equipment-transaction:owns-town-leave-store",
            "equipment-transaction:abandon-blocked",
            "equipment-transaction:owns-town-leave-store",
        ]
        # Seed the captured pre-swap state so takeoff and equip both execute.
        actions = (
            EquipmentTransaction(PHASE_EQUIP, "takeoff", "rag", "body", RAG),
            EquipmentTransaction(PHASE_EQUIP, "equip", "hard", "body", HARD_ARMOUR),
            EquipmentTransaction(PHASE_HOME_FINALIZE, "deposit", "rag", None, RAG),
        )
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan(actions, (), 0)
        )
        policy._equipment_transaction_owned_items = [(RAG, "body")]
        snapshot = self._surface(1172821, RAG)
        reasons = []
        body_history = [RAG]

        for _ in range(8):
            key = policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            session = policy._equipment_transaction_session
            action = None if session is None else (
                session.prepared_action or session.pending_action or session.current_action
            )
            policy.confirm_key_posted(key)
            snapshot = self._apply_posted_key(snapshot, key, action)
            body = next(
                (equipment_identity(item) for item in snapshot.equipment if item.slot == "body"),
                None,
            )
            if body is not None and body != body_history[-1]:
                body_history.append(body)

        self.assertFalse(any(
            reasons[index:index + len(captured_cycle)] == captured_cycle
            for index in range(len(reasons) - len(captured_cycle) + 1)
        ), reasons)
        self.assertIn("equipment-transaction:takeoff", reasons)
        self.assertIn("equipment-transaction:equip", reasons)
        self.assertEqual(body_history, [RAG, HARD_ARMOUR], (body_history, reasons))

    def test_stale_takeoff_identity_is_invalidated_before_slot_letter_posts(self):
        snapshot = self._surface(1172858, HARD_ARMOUR)
        action = EquipmentTransaction(PHASE_EQUIP, "takeoff", "rag", "body", RAG)
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0)
        )
        policy._equipment_transaction_owned_items = [(RAG, "body")]
        key = policy.choose_key(snapshot)
        self.assertTrue(key)
        self.assertNotEqual(key, "")
        self.assertIsNone(policy._equipment_transaction_prepared_key)
        self.assertIn("stale-identity-invalidated:takeoff", policy.last_reason)
        self.assertIn("rag", policy._equipment_transaction_failed_items)

    def test_missing_equip_identity_ratchets_to_named_blocker(self):
        snapshot = self._surface(1172858, HARD_ARMOUR)
        action = EquipmentTransaction(PHASE_EQUIP, "equip", "missing", "body", "absent")
        policy = HengbotPolicy()
        session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 0))
        policy._equipment_transaction_session = session
        self.assertEqual(policy._equipment_transaction_town_key(snapshot), WAIT_KEY)
        self.assertIn("equip-item-missing:missing", session.blockers)

    def test_route_repeat_is_cancelled_by_changed_observation(self):
        snapshot = self._surface(1172821, RAG)
        action = EquipmentTransaction(PHASE_HOME_FINALIZE, "deposit", "old", None, HARD_ARMOUR)
        policy = HengbotPolicy()
        policy._equipment_transaction_owned_items = [(HARD_ARMOUR, "body")]
        for observed in (snapshot, snapshot, replace(snapshot, player=replace(snapshot.player, gold=snapshot.player.gold + 1))):
            session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 0))
            session.block("home-route-unavailable")
            policy._equipment_transaction_session = session
            policy._abandon_blocked_equipment_transaction(observed)
        self.assertFalse(policy._equipment_transaction_route_terminal_pending)
        self.assertIsNone(policy._equipment_transaction_route_terminal)

    def test_same_route_abandonment_reaches_cli_terminal(self):
        snapshot = self._surface(1172821, RAG)
        action = EquipmentTransaction(PHASE_HOME_FINALIZE, "deposit", "old", None, HARD_ARMOUR)
        policy = HengbotPolicy()
        observations = (
            snapshot,
            replace(
                snapshot,
                player=replace(
                    snapshot.player,
                    position=replace(snapshot.player.position, y=snapshot.player.position.y + 1),
                ),
            ),
        )
        for observed in observations:
            session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 0))
            session.block("home-route-unavailable")
            policy._equipment_transaction_session = session
            policy._abandon_blocked_equipment_transaction(observed)
        terminal = "equipment-transaction:home-route-repeat-terminal"
        self.assertEqual(policy._equipment_transaction_route_terminal, terminal)
        self.assertIn(terminal, POLICY_FINAL_STOP_REASONS)

    def test_live_home_work_survives_entrance_reason_rewrite(self):
        snapshot = self._surface(1172205, HARD_ARMOUR)
        action = EquipmentTransaction(PHASE_HOME_FINALIZE, "deposit", "old", None, RAG)
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0)
        )
        travel = "\x1b`n!."
        with patch.object(
            policy,
            "_town_procurement_progress_key",
            return_value=(travel, "town-progress-invariant:approach"),
        ):
            key = policy.choose_key(snapshot)
        self.assertEqual(key, WAIT_KEY)
        self.assertNotEqual(key, travel)

    def test_blocked_live_home_work_cannot_relocate_to_foreign_store(self):
        snapshot = self._surface(1172205, HARD_ARMOUR)
        actions = (
            EquipmentTransaction(PHASE_EQUIP, "equip", "hard", "body", HARD_ARMOUR),
            EquipmentTransaction(PHASE_HOME_FINALIZE, "deposit", "old", None, RAG),
        )
        policy = HengbotPolicy()
        session = EquipmentTransactionSession(EquipmentTransactionPlan(actions, (), 0))
        session.block("home-route-unavailable")
        policy._equipment_transaction_session = session
        travel = "\x1b`n!."
        def await_confirmation(_snapshot):
            policy.last_reason = "equipment-transaction:await-confirmation"
            return WAIT_KEY

        with patch.object(policy, "_choose_key_with_latch_capture", await_confirmation), \
             patch.object(
                 policy,
                 "_town_procurement_progress_key",
                 return_value=(travel, "town-progress-invariant:approach"),
             ):
            key = policy.choose_key(snapshot)
        self.assertEqual(key, WAIT_KEY)
        self.assertNotEqual(key, travel)

    def test_owned_equip_only_restore_cannot_relocate_to_foreign_store(self):
        snapshot = self._surface(1172205, HARD_ARMOUR)
        action = EquipmentTransaction(PHASE_EQUIP, "equip", "hard", "body", HARD_ARMOUR)
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0)
        )
        policy._equipment_transaction_owned_items = [(RAG, "body")]
        travel = "\x1b`n!."
        with patch.object(
            policy,
            "_town_procurement_progress_key",
            return_value=(travel, "town-progress-invariant:approach"),
        ):
            key = policy.choose_key(snapshot)
        self.assertEqual(key, WAIT_KEY)
        self.assertNotEqual(key, travel)

    def test_stale_invalidation_clears_pending_route_terminal(self):
        snapshot = self._surface(1172858, HARD_ARMOUR)
        action = EquipmentTransaction(PHASE_EQUIP, "takeoff", "rag", "body", RAG)
        policy = HengbotPolicy()
        policy._equipment_transaction_route_terminal_pending = True
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0)
        )
        policy._equipment_transaction_owned_items = [(RAG, "body")]
        self.assertTrue(policy.choose_key(snapshot))
        self.assertFalse(policy._equipment_transaction_route_terminal_pending)

    def test_non_route_abandonment_clears_pending_route_terminal(self):
        snapshot = self._surface(1172821, RAG)
        action = EquipmentTransaction(PHASE_EQUIP, "equip", "missing", "body", "absent")
        policy = HengbotPolicy()
        policy._equipment_transaction_route_terminal_pending = True
        session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 0))
        session.block("equip-item-missing:missing")
        policy._equipment_transaction_session = session
        policy._abandon_blocked_equipment_transaction(snapshot)
        self.assertFalse(policy._equipment_transaction_route_terminal_pending)
        self.assertIsNone(policy._equipment_transaction_route_terminal)

    def test_abandon_blocked_wait_steps_off_store_entrance(self):
        snapshot = self._surface(1172810, HARD_ARMOUR)
        policy = HengbotPolicy()
        policy.last_reason = "equipment-transaction:abandon-blocked"
        self.assertNotEqual(policy._forbid_wait_on_town_entrance(snapshot, WAIT_KEY), WAIT_KEY)
