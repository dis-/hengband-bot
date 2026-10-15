"""Replay the October 16 terminal overflow capture through the real policy."""

import tests  # noqa: F401 -- isolate runtime writes

import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot.model import (
    Position, Snapshot, SV_SCROLL_WORD_OF_RECALL, TVAL_SCROLL, parse_snapshot,
)
from hengbot.item_reservation import reservation_verdict
from hengbot.policy import HengbotPolicy, WAIT_KEY
from policy_fixtures import grid, item, player


FIXTURE = Path(__file__).parent / "fixtures" / "town-overflow-disposal-20261016.jsonl.gz"
SHA256 = "c4b167b6e6d8e53c0e5a31ba5c98d391699201eff597a7d69749e7ad0fa1bf9e"


class TownOverflowDisposalRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.records = [json.loads(line) for line in stream if line.strip()]

    def test_captured_stops_replay_and_known_curse_frees_pack(self):
        self.assertEqual(
            [record["capture"] for record in self.records],
            [
                "life-002/20261016-013421",
                "life-003/20261016-030116",
            ],
        )
        for record in self.records:
            with self.subTest(capture=record["capture"]):
                board = parse_snapshot(record["board"])
                facts = record["decision"]
                self.assertEqual(board.turn, facts["turn"])
                self.assertEqual(
                    facts["reason"], "town:blocked:overflow-no-legal-disposal",
                )

        record = self.records[1]
        board = parse_snapshot(record["board"])
        policy = HengbotPolicy()
        policy.prime(board)
        cursed = [item for item in board.inventory if item.is_cursed]
        self.assertEqual([item.slot for item in cursed], ["t"])
        self.assertTrue(cursed[0].known)
        self.assertEqual(policy._overflow_disposal_item(board).slot, "t")

        key = policy._town_overflow_destroy_key(board)

        self.assertEqual(
            (key, policy.last_reason), ("01kt", "town:destroy-overflow"),
        )
        # The normal verified-disposal execution offer records every emitted
        # destruction's identity, count, and expected inventory effect.
        offer, = policy._execution_offers_for()
        self.assertEqual(offer[0], key)
        self.assertEqual(offer[1], "identification")
        self.assertEqual(
            offer[2], f"verified-destroy:{policy._item_signature(board.inventory[-1])}",
        )
        self.assertEqual(offer[3], "inventory.destroy.send")
        self.assertEqual(offer[5], "surplus-stack-removed")

    def test_recorded_supply_reservations_and_identify_first_are_preserved(self):
        record = self.records[1]
        board = parse_snapshot(record["board"])
        policy = HengbotPolicy()
        policy.prime(board)
        reserved_slots = {"a", "b", "c", "d", "e", "f", "i"}
        recorded_slots = {
            item.slot
            for item in board.inventory
            if policy._retention_reservation(board, item) > 0
        }
        self.assertTrue(reserved_slots <= recorded_slots)
        for carried in board.inventory:
            if carried.slot in reserved_slots:
                verdict = reservation_verdict(
                    policy, board, carried, "shop-sell", "sell",
                )
                self.assertEqual((verdict.owner, verdict.quantity), (None, 0))
        self.assertNotIn(
            next(item for item in board.inventory if item.is_cursed).slot,
            reserved_slots,
        )
        self.assertEqual(policy._overflow_disposal_item(board).slot, "t")

        unidentified = replace(
            board.inventory[-1], known=False, fully_known=False, aware=False,
            is_cursed=False, inscription="",
        )
        unknown_board = replace(board, inventory=[unidentified])
        unknown_policy = HengbotPolicy()
        unknown_policy.prime(unknown_board)
        self.assertTrue(
            unknown_policy._item_is_procurement_protected(unknown_board, unidentified)
        )
        self.assertIsNone(unknown_policy._overflow_disposal_item(unknown_board))

    def test_all_reserved_full_pack_still_stops_visibly(self):
        # CONSTRUCTED frame: the owner reservation predicate holds every stack.
        position = Position(10, 10)
        inventory = [
            item(
                chr(ord("a") + index), TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                name="Word of Recall", count=1, fully_known=True,
            )
            for index in range(20)
        ]
        board = Snapshot(
            player(10, 10, class_id=-1), {position: grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True, inventory=inventory,
        )
        policy = HengbotPolicy()
        policy.prime(board)

        with patch.object(policy, "_item_is_procurement_protected", return_value=True):
            self.assertTrue(all(
                policy._item_is_procurement_protected(board, carried)
                for carried in inventory
            ))
            key = policy.choose_key(board)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "town:blocked:overflow-no-legal-disposal",
        )


if __name__ == "__main__":
    unittest.main()
