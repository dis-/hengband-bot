"""R4 capture of the completed lantern swap that restored the old torch."""

import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import tests  # noqa: F401  (bare module runs isolate runtime files)

from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP, EquipmentTransaction, EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import (
    EquipmentTransactionSession, observe_equipment_transactions,
)
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "newchar-light-churn-20260928.json.gz"


class NewCharacterLightChurnRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = json.load(stream)

    def board(self, line):
        return parse_snapshot(self.rows["state"][str(line)])

    def test_commands_and_physical_items_are_pinned(self):
        rows = self.rows["decisions"]
        self.assertEqual(
            [(rows[str(n)]["key"], rows[str(n)]["reason"])
             for n in (1133, 1134, 1135, 1136, 1137)],
            [("tg", "equipment-transaction:takeoff"),
             ("wd", "equipment-transaction:equip"),
             ("wc", "equipment-transaction:equip"),
             ("tg", "equipment-transaction:takeoff"),
             ("wd", "equipment-transaction:equip")],
        )
        before, stripped, lantern, restored, stripped_again = (
            self.board(n) for n in (1431, 1432, 1433, 1434, 1435)
        )
        self.assertEqual(
            [(item.slot, item.tval, item.sval) for item in before.equipment
             if item.slot == "light"], [("light", 39, 0)],
        )
        self.assertFalse(any(item.slot == "light" for item in stripped.equipment))
        known = next(item for item in stripped.inventory if item.slot == "d")
        unknown = next(item for item in stripped.inventory if item.slot == "e")
        self.assertEqual((known.tval, known.sval, known.known), (39, 1, True))
        self.assertEqual((unknown.tval, unknown.sval, unknown.known), (39, 1, False))
        policy = HengbotPolicy()
        self.assertFalse(policy._equip_blocked_by_identification(known))
        self.assertTrue(policy._equip_blocked_by_identification(unknown))
        self.assertEqual(
            equipment_identity(next(item for item in lantern.equipment
                                    if item.slot == "light")),
            equipment_identity(known),
        )
        self.assertEqual(
            equipment_identity(next(item for item in restored.equipment
                                    if item.slot == "light")),
            equipment_identity(next(item for item in before.equipment
                                    if item.slot == "light")),
        )
        self.assertFalse(any(item.slot == "light" for item in stripped_again.equipment))
        self.assertIn("光源からはずした", " ".join(rows["1134"]["messages"]))
        self.assertIn("光源にした", " ".join(rows["1135"]["messages"]))
        self.assertEqual(
            rows["1134"]["equipment_optimization"]["transaction_next"]["item_id"],
            "pack:cf9cbd9f667b29b6:0",
        )
        self.assertTrue(
            rows["1135"]["equipment_optimization"]["transaction_next"]["item_id"]
            .startswith("restore:")
        )

    def completed_swap_checkpoint(self):
        before, stripped, lantern = (self.board(n) for n in (1431, 1432, 1433))
        torch = next(item for item in before.equipment if item.slot == "light")
        known = next(item for item in stripped.inventory if item.slot == "d")
        takeoff = EquipmentTransaction(
            PHASE_EQUIP, "takeoff", "equipped:441248f0e6daf1d7:0", "light",
            equipment_identity(torch), equipment_move_identity(torch),
        )
        equip = EquipmentTransaction(
            PHASE_EQUIP, "equip", "pack:cf9cbd9f667b29b6:0", "light",
            equipment_identity(known), equipment_move_identity(known),
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((takeoff, equip), (), 0)
        )
        session.index = 1  # recorded tg already confirmed on the stripped board
        self.assertTrue(session.dispatch(equip, observe_equipment_transactions(stripped)))
        policy = HengbotPolicy()
        policy._equipment_transaction_session = session
        policy._equipment_transaction_owned_items = [(equipment_move_identity(torch), "light")]
        return restore_checkpoint(HengbotPolicy, checkpoint(policy)), lantern, session

    def test_restored_checkpoint_retires_torch_debt_after_confirmed_lantern(self):
        restored, lantern, session = self.completed_swap_checkpoint()
        key = restored._choose_key(lantern)
        self.assertTrue(session.index == 1)  # checkpoint owns an independent session
        self.assertEqual(restored._equipment_transaction_owned_items, [])
        self.assertFalse(restored._equipment_transaction_restoring)
        self.assertNotEqual(key, "wc")
        self.assertNotEqual(
            getattr(restored._equipment_transaction_session, "target_loadout_id", None),
            "f9e5352f0ed10c88",  # live torch restoration transaction
        )

    def test_revert_proof_recreates_live_restore_command(self):
        restored, lantern, _ = self.completed_swap_checkpoint()
        with patch.object(
            HengbotPolicy, "_retire_replaced_equipment_transaction_owned_items",
            return_value=None,
        ):
            key = restored._choose_key(lantern)
        self.assertEqual(key, "wc")
        self.assertEqual(restored.last_reason, "equipment-transaction:equip")
        self.assertEqual(len(restored._equipment_transaction_owned_items), 1)


if __name__ == "__main__":
    unittest.main()
