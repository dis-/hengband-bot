"""Replay the C4-A overflow stop with five spare torches (issue #69).

The fixture row is the last state row of the soak capture
c4a-loops-20261016/20261018-164159-town-blocked-overflow-no-legal-disposal,
copied as-is (turn 2784447, town, Level 28, 20 pack entries, three free
slots).  The recorded decision 3483 was ``town:blocked:overflow-no-legal-
disposal``.  The character wears a Feanorian lamp (a permanent light) and
carries five single torches, each of which the backup-light carry target
reserved.

DECLARED CONSTRUCTED: the policy runtime state that the single row cannot
carry -- the fundraising mode ``prepare`` (decision row ``fundraising.mode``),
the visit purchase of the four *Identify* scrolls (decision row retention
branch ``visit-purchase``) and the ~f skill-exp cache; in the controls, the
worn light named there.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import SV_LITE_LANTERN
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import FOOD_STOCK_TARGET
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "overflow-torches-20261018.jsonl.gz"
SHA256 = "dba8a172a9fbe28405698afde54cd2f2644c29ce21b82277d15b3284ab7cda37"
TORCH_SLOTS = ("m", "n", "o", "p", "q")


class OverflowTorchesRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.lines = gzip.decompress(data).decode("utf-8").splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _board(self):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        _decoded, snapshots = _consume_response_sequence(
            [self.lines[0]], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        board = snapshots[-1]
        self.assertEqual((board.turn, len(board.inventory)), (2784447, 20))
        # DECLARED CONSTRUCTED: runtime state recorded in decision 3483.
        policy._skill_exp_cache = (
            0, 0, board.player.level, policy._town_visit_epoch
        )
        policy._fundraising_mode = "prepare"
        identify = next(item for item in board.inventory if item.slot == "f")
        signature = policy._item_signature(identify)
        policy._town_visit_purchases.add(signature)
        policy._town_visit_purchase_quantities[signature] = identify.count
        return policy, board

    def _reserved_slots(self, policy, board):
        return {
            item.slot
            for item in board.inventory
            if policy._retention_reservation(board, item) > 0
            or policy._item_is_procurement_protected(board, item)
        }

    def test_recorded_stop_board_destroys_a_spare_torch(self):
        policy, board = self._board()
        worn = next(item for item in board.equipment if item.is_light)
        self.assertTrue(worn.is_feanorian_lamp)
        self.assertTrue(policy._town_pack_space_shortage(board))
        for slot in TORCH_SLOTS:
            torch = next(item for item in board.inventory if item.slot == slot)
            self.assertTrue(torch.is_torch and torch.count == 1)
            self.assertEqual(policy._retention_reservation(board, torch), 0)
        key = policy._town_overflow_destroy_key(board)
        self.assertEqual(
            (key, policy.last_reason), ("01km", "town:destroy-overflow")
        )
        # The Home path can now shelve the same surplus first.
        self.assertTrue(policy._town_space_deposit_actionable(board))
        self.assertEqual(policy._find_home_deposit(board).slot, "m")

    def test_control_reserved_supplies_are_never_chosen(self):
        policy, board = self._board()
        reserved = self._reserved_slots(policy, board)
        self.assertEqual(
            reserved, set("abcdefghirst"),
        )
        chosen = set()
        while True:
            candidate = policy._overflow_disposal_item(board)
            if candidate is None:
                break
            chosen.add(candidate.slot)
            board = replace(board, inventory=[
                item for item in board.inventory if item is not candidate
            ])
        # Only spare torches are released, and only until the shortage is
        # gone; the three Identify staves stay (useful devices within the
        # four-staff cap).
        self.assertEqual(chosen, {"m", "n"})
        self.assertFalse(policy._town_pack_space_shortage(board))
        self.assertEqual(
            self._reserved_slots(policy, board), set("abcdefghirst")
        )

    def test_control_fuelled_light_keeps_the_torch_reserve(self):
        policy, board = self._board()
        # Constructed: a fuelled lantern worn instead of the Feanorian lamp.
        board = replace(board, equipment=type(board.equipment)(
            replace(item, sval=SV_LITE_LANTERN, name="ランタン", is_artifact=False,
                    fuel=7500, light_turns=7500)
            if item.is_light else item
            for item in board.equipment
        ))
        self.assertFalse(policy._owns_usable_permanent_light(board))
        torch = next(item for item in board.inventory if item.slot == "m")
        self.assertEqual(
            policy._torch_carry_requirement(board, torch, None)[0],
            FOOD_STOCK_TARGET,
        )
        for slot in TORCH_SLOTS:
            torch = next(item for item in board.inventory if item.slot == slot)
            self.assertEqual(policy._retention_reservation(board, torch), 1)
        self.assertIsNone(policy._overflow_disposal_item(board))
        policy._town_overflow_destroy_key(board)
        self.assertEqual(
            policy.last_reason, "town:blocked:overflow-no-legal-disposal"
        )


if __name__ == "__main__":
    unittest.main()
