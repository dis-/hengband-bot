"""Recorded 2026-10-05 swap: successful combat rearm must not restore diggers.

Boards and plans are captured facts. The checkpoint is explicitly reconstructed
at the final equip observation; the optimizer is not replaced or rerun here.
"""
import ast
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import tests  # noqa: F401 -- isolate runtime files
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession, observe_equipment_transactions
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint

FIXTURE = Path(__file__).parent / "fixtures/equipment-alternation-20261005.json.gz"


class EquipmentAlternationRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == "54bd23a0caec2544f428e50ba54cecf73f1db6e3e6cf132902324dc878baf40f"
        cls.data = json.loads(gzip.decompress(payload))

    def board(self, sequence):
        row = self.data["rows"][str(sequence)]
        raw = self.data["boards"][str(row["turn"])]
        # DECLARED CONSTRUCTED: remove neutral town residents; their catalogue
        # is absent from the capture and irrelevant to the equipment seam.
        return parse_snapshot({**raw, "visible_monsters": [], "detected_monsters": []})

    def completed_swap_checkpoint(self):
        row = self.data["rows"]["4655"]
        text = next(s for s in row["claim"]["goal"]["expectation"]
                    if "EquipmentTransaction(" in s)
        actions = []
        for action in ast.literal_eval(text):
            node = ast.parse(action, mode="eval").body
            actions.append(EquipmentTransaction(**{
                kw.arg: ast.literal_eval(kw.value) for kw in node.keywords}))
        session = EquipmentTransactionSession(EquipmentTransactionPlan(tuple(actions), (), 0))
        session.index = 2  # both captured takeoffs already observed
        self.assertTrue(session.dispatch(session.current_action,
                                        observe_equipment_transactions(self.board(4657))))
        policy = HengbotPolicy()
        # Reconstructed captured flags: the decision rows report a complete,
        # current Home catalogue. No Home items participate in this swap.
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._equipment_transaction_session = session
        policy._equipment_transaction_owned_items = [
            (a.move_identity, a.target_slot) for a in actions if a.kind == "takeoff"]
        return restore_checkpoint(HengbotPolicy, checkpoint(policy)), self.board(4658)

    def test_capture_first_divergence_is_restore_after_success_not_optimizer_flip(self):
        rows = self.data["rows"]
        self.assertEqual([rows[str(n)]["key"] for n in range(4655, 4661)],
                         ["tb", "ta", "wm", "wny", "wma", "tb"])
        self.assertEqual(rows["4658"]["claim"]["closed_claim"]["closed_reason"],
                         "equipment-transaction-complete")
        self.assertTrue(rows["4658"]["equipment_optimization"]["transaction_next"]["item_id"].startswith("restore:"))
        after = self.board(4658)
        self.assertFalse(any(i.slot == "sub_hand" for i in after.equipment))
        self.assertFalse(any(i.is_cursed for i in after.equipment))

    def test_confirmed_two_handed_swap_stays_stable_across_observations(self):
        policy, after = self.completed_swap_checkpoint()
        for offset in range(3):
            policy._choose_key(replace(after, turn=after.turn + offset))
            self.assertEqual(policy._equipment_transaction_owned_items, [])
            self.assertFalse(policy._equipment_transaction_restoring)
            self.assertIsNone(policy._equipment_transaction_session)
        self.assertIsNone(policy._equipment_transaction_town_owner_key(after))

    def test_revert_proof_light_only_retirement_recreates_recorded_restore(self):
        policy, after = self.completed_swap_checkpoint()
        fixed = HengbotPolicy._retire_replaced_equipment_transaction_owned_items

        def light_only(self, snapshot, session):
            if any(a.target_slot == "light" for a in session.plan.actions):
                fixed(self, snapshot, session)

        with patch.object(HengbotPolicy, "_retire_replaced_equipment_transaction_owned_items", light_only):
            key = policy._choose_key(after)
        self.assertEqual(key, "wny")
        self.assertEqual(policy.last_reason, "equipment-transaction:equip")
        self.assertEqual(policy._equipment_transaction_session.target_loadout_id,
                         self.data["rows"]["4658"]["equipment_optimization"]["transaction_target_loadout_id"])

    def test_incomplete_or_restoration_session_preserves_recovery_debt(self):
        for restoring in (False, True):
            policy, after = self.completed_swap_checkpoint()
            session = policy._equipment_transaction_session
            if restoring:
                session.observe(observe_equipment_transactions(after))
                policy._equipment_transaction_restoring = True
            debt = list(policy._equipment_transaction_owned_items)
            policy._retire_replaced_equipment_transaction_owned_items(after, session)
            self.assertEqual(policy._equipment_transaction_owned_items, debt)

    def test_completion_retires_only_this_plans_confirmed_takeoffs(self):
        policy, after = self.completed_swap_checkpoint()
        session = policy._equipment_transaction_session
        session.observe(observe_equipment_transactions(after))
        unrelated = ("other-session-item", "head")
        policy._equipment_transaction_owned_items.append(unrelated)
        policy._retire_replaced_equipment_transaction_owned_items(after, session)
        self.assertEqual(policy._equipment_transaction_owned_items, [unrelated])


if __name__ == "__main__":
    unittest.main()
