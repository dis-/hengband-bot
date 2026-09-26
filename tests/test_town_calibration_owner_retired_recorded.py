"""Pins from the 2026-09-27 Outpost calibration interruption."""

import tests  # noqa: F401 -- isolate live runtime files

import base64
import gzip
import hashlib
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.equipment_optimizer import equipment_identity
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = (Path(__file__).resolve().parent / "fixtures" /
           "town-calibration-owner-retired-20260927.jsonl.gz")
TURNS = (6712128, 6712132, 6712134, 6714217, 6714557, 6714564)
SHA256 = "3df3b92fa7f8629e69700510584b1ca698aaa7abefbefd04f20e54dae8ec5328"


def boards():
    with gzip.open(FIXTURE, "rb") as stream:
        raw = stream.read()
    assert hashlib.sha256(raw).hexdigest() == SHA256
    rows = [json.loads(line) for line in raw.splitlines()]
    assert tuple(row["turn"] for row in rows) == TURNS
    return {row["turn"]: parse_snapshot(row, {}) for row in rows}


class TownCalibrationOwnerRetiredRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshots = boards()

    def test_max_hp_loss_from_takeoff_is_not_damage(self):
        before = self.snapshots[6712132]
        after = self.snapshots[6712134]
        self.assertEqual((before.player.hp, before.player.max_hp), (810, 810))
        self.assertEqual((after.player.hp, after.player.max_hp), (731, 731))
        self.assertFalse(after.visible_monsters)
        policy = HengbotPolicy()
        policy._observe(before)
        policy._observe(after)
        self.assertFalse(policy._took_damage)

        damaged = replace(after, player=replace(after.player, hp=700))
        policy = HengbotPolicy()
        policy._observe(before)
        policy._observe(damaged)
        self.assertTrue(policy._took_damage)

    def test_old_checkpoint_defaults_max_hp_observation(self):
        state = vars(HengbotPolicy()).copy()
        state.pop("_last_max_hp")
        state["_last_hp"] = 810
        encoded = base64.b64encode(pickle.dumps(state, protocol=5)).decode("ascii")
        restored = restore_checkpoint(HengbotPolicy, encoded)
        restored._observe(self.snapshots[6712134])
        self.assertEqual(restored._last_max_hp, 731)

    def _install_strip(self, turn):
        snapshot = self.snapshots[turn]
        policy = HengbotPolicy()
        policy._calibration_phase = "deposit"
        policy._calibration_worn_before = tuple(
            (item.slot, equipment_identity(item))
            for item in snapshot.equipment if item.is_equipment
        )
        self.assertTrue(policy._install_calibration_strip_session(snapshot))
        return policy, snapshot

    def test_new_strip_session_keeps_home_movement_ownership(self):
        # Decision 20171 installed the strip session after Home deposits, then
        # the arbiter rewrote its key into shop travel in the same decision.
        policy, home_door = self._install_strip(6714217)
        session = policy._equipment_transaction_session
        self.assertEqual(session.required_context, "outside_home")
        self.assertTrue(policy._equipment_transaction_owns_town_relocation(home_door))
        key = policy._equipment_transaction_town_key(home_door)
        self.assertEqual((key, policy.last_reason),
                         ("tb", "equipment-transaction:takeoff"))
        self.assertIs(policy._equipment_transaction_session, session)

    def test_post_deposit_board_cannot_rewrite_strip_to_shop_travel(self):
        board = self.snapshots[6714217]
        policy = HengbotPolicy()
        policy.consume_home_knowledge(())
        policy._calibration_phase = "deposit"
        policy._calibration_worn_before = tuple(
            (item.slot, equipment_identity(item))
            for item in board.equipment if item.is_equipment
        )
        policy._town_order_operation = "calibration"
        policy._town_order_expected_observation = "home-deposit"
        # The captured protocol-3 board lacks the separately requested skill
        # list; ignore that unrelated bookkeeping request for this policy pin.
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("tb", "equipment-transaction:takeoff"))
        self.assertEqual(policy._calibration_phase, "strip")

    def test_weapon_shop_board_routes_back_to_home_before_takeoff(self):
        self.assertEqual(
            self.snapshots[6714564].grid_at(
                self.snapshots[6714564].player.position
            ).store_number, 3,
        )
        policy, shop_door = self._install_strip(6714564)
        session = policy._equipment_transaction_session
        self.assertEqual(session.required_context, "outside_home")
        key = policy._equipment_transaction_town_key(shop_door)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b`n(.", "equipment-transaction:travel-home"))
        self.assertIs(policy._equipment_transaction_session, session)
        self.assertNotEqual(key[0], "t")

    def test_restore_session_also_requires_home(self):
        policy = HengbotPolicy()
        before = self.snapshots[6712132]
        after = self.snapshots[6712134]
        policy._calibration_worn_before = tuple(
            (item.slot, equipment_identity(item))
            for item in before.equipment if item.is_equipment
        )
        self.assertTrue(policy._install_calibration_restore_session(after))
        session = policy._equipment_transaction_session
        self.assertEqual(session.required_context, "outside_home")
        self.assertTrue(policy._calibration_session_owned())
        policy._prepare_equipment_optimization(after)
        self.assertIs(policy._equipment_transaction_session, session)
        shop_door = self.snapshots[6714564]
        key = policy._equipment_transaction_town_key(shop_door)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b`n(.", "equipment-transaction:travel-home"))

    def test_restore_supplies_cannot_install_foreign_optimizer_session(self):
        policy = HengbotPolicy()
        policy._calibration_phase = "restore-supplies"
        board = self.snapshots[6714217]
        with patch.object(policy, "_validated_character_calibration",
                          side_effect=AssertionError("foreign optimization ran")):
            preparation = policy._prepare_equipment_optimization(board)
        self.assertEqual(preparation.blockers, ("calibration-required",))
        self.assertIsNone(policy._equipment_transaction_session)


if __name__ == "__main__":
    unittest.main()
