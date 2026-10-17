"""Replay the October 17 overflow stop through the real disposal policy."""

import tests  # noqa: F401 -- isolate runtime writes

import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = (
    Path(__file__).parent / "fixtures"
    / "town-overflow-disposal-candidates-20261017.jsonl.gz"
)
SHA256 = "644f09f03c02484e9cf82f7f18b08b40518228a563737a23eeef7c1d2135614f"


class TownOverflowDisposalCandidatesRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.records = [json.loads(line) for line in stream if line.strip()]

    def test_captured_stop_releases_only_surplus_candidates(self):
        record, = self.records
        self.assertEqual(record["capture"], "20261017-212641")
        self.assertEqual(record["decision_sequence"], 7)
        self.assertEqual(record["reason"], "town:blocked:overflow-no-legal-disposal")
        board = parse_snapshot(record["board"])
        self.assertEqual((board.turn, len(board.inventory)), (1681211, 20))

        policy = HengbotPolicy()
        policy.prime(board)
        self.assertTrue(policy._town_pack_space_shortage(board))
        candidate = policy._overflow_disposal_item(board)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.slot, "p")
        empty_lantern = next(item for item in board.inventory if item.slot == "p")
        broken_weapon = next(item for item in board.inventory if item.slot == "q")
        self.assertTrue(policy._is_disposable_item(
            empty_lantern, overflow_pressure=policy._town_pack_space_shortage(board)
        ))
        self.assertTrue(policy._is_disposable_item(
            broken_weapon, overflow_pressure=policy._town_pack_space_shortage(board)
        ))
        self.assertEqual(policy._retention_reservation(board, candidate), 0)
        self.assertEqual(
            policy._retention_reservation(
                board, next(item for item in board.inventory if item.slot == "s")
            ),
            1,
        )
        duplicate_shovels = next(
            item for item in board.inventory if item.slot == "r"
        )
        self.assertEqual(policy._retention_reservation(board, duplicate_shovels), 0)
        self.assertTrue(policy._is_surplus_digging_tool(board, duplicate_shovels))
        key = policy._town_overflow_destroy_key(board)
        self.assertEqual((key, policy.last_reason), ("01kp", "town:destroy-overflow"))

        # The equipped lantern and best fueled torch remain available as light.
        self.assertEqual(
            next(item for item in board.equipment if item.slot == "light").fuel,
            6433,
        )
        kept_light, = [item for item in board.equipment if item.slot == "light"]
        self.assertIsNot(candidate, kept_light)
        for slot in ("l", "m", "n", "o"):
            torch = next(item for item in board.inventory if item.slot == slot)
            self.assertGreater(policy._retention_reservation(board, torch), 0)
        self.assertFalse(policy._is_spare_lantern(board, candidate))
        self.assertFalse(policy._is_surplus_digging_tool(
            board, next(item for item in board.inventory if item.slot == "s")
        ))

        # Departure-critical supplies remain protected by their normal reservations.
        for slot in ("c", "e", "f"):
            carried = next(item for item in board.inventory if item.slot == slot)
            self.assertTrue(policy._item_is_procurement_protected(board, carried))
            self.assertNotEqual(candidate.slot, slot)

    def test_constructed_torch_surplus_uses_existing_carry_target(self):
        record, = self.records
        board = parse_snapshot(record["board"])
        # DECLARED CONSTRUCTED: increase the four captured torch stacks to two
        # each, so one whole stack lies beyond the real policy carry target.
        board = replace(
            board,
            inventory=[
                replace(item, count=2) if item.is_torch else item
                for item in board.inventory
            ],
        )
        policy = HengbotPolicy()
        policy.prime(board)
        candidate = policy._overflow_disposal_item(board)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.slot, "o")
        self.assertEqual(policy._retention_reservation(board, candidate), 0)
        key = policy._town_overflow_destroy_key(board)
        self.assertEqual((key, policy.last_reason), ("02ko", "town:destroy-overflow"))


if __name__ == "__main__":
    unittest.main()
