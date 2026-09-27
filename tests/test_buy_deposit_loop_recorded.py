"""Pins from the 2026-09-28 Outpost buy/deposit capture.

The policy's earlier town visit state is not in the JSONL boards.  Replay
therefore begins at the recorded shop/Home operation boundary, with its
fundraising run target taken from the decision's retention ledger.  It stops
at the first Home deposit that must diverge from the recorded operation.
"""

import tests  # noqa: F401

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.purchase_rungs import PurchaseContext
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint


FIXTURE = Path(__file__).parent / "fixtures/buy-deposit-loop-20260928.json.gz"
SHA256 = "0f39722b99225509becc4933c8841888c62b97fa218490004d01dbc5229c5247"


class BuyDepositLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != SHA256:
            raise AssertionError("recorded buy/deposit fixture changed")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = json.load(stream)

    def _policy(self, row):
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        required = row["decision"]["retention_reservations"][0]["reservation"]
        policy._mining_detection_scroll_target = lambda snapshot: required
        return policy

    def test_recorded_purchase_then_first_home_divergence(self):
        buy, deposit, later_buy, later_deposit = self.rows
        self.assertEqual(
            [(r["decision"]["decision_sequence"], r["decision"]["key"],
              r["decision"]["reason"]) for r in self.rows],
            [(956, "pr5\r\r\x1b", "shop:one-shot-buy"),
             (958, "dg5\r\x1b", "home:weight-overload-deposit"),
             (1247, "pk5\r\r\x1b", "shop:one-shot-buy"),
             (1249, "df5\r\x1b", "home:weight-overload-deposit")],
        )
        for purchase, home, held, target in (
            (buy, deposit, 4, 9), (later_buy, later_deposit, 2, 7)
        ):
            shop = parse_snapshot(purchase["board"])
            policy = self._policy(purchase)
            scroll = next(i for i in shop.inventory if i.is_treasure_detection_scroll)
            ware = next(i for i in shop.store.items if i.is_treasure_detection_scroll)
            context = PurchaseContext(shop)
            rung = next(r for r in policy._purchase_rungs(context)
                        if r.rung_id == "mining:treasure-detection")
            match = rung.match(context, ware)
            self.assertEqual((scroll.count, match.current, match.target,
                              match.shortage), (held, held, target, 5))
            self.assertEqual(policy._purchase_quantity(shop, ware), 5)

            board = parse_snapshot(home["board"])
            policy = self._policy(home)
            carried = next(i for i in board.inventory if i.is_treasure_detection_scroll)
            self.assertEqual(carried.count, target)
            self.assertEqual(
                home["decision"]["retention_reservations"][0]["reservation"],
                held,
            )
            self.assertEqual(policy._mining_detection_stock_target(board), target)
            self.assertEqual(policy._retention_surplus(board, carried), 0)
            selected = policy._overweight_home_deposit(board)
            self.assertTrue(policy._inventory_overweight(board))
            self.assertTrue(selected is None or not selected.is_treasure_detection_scroll)

    def test_required_count_and_only_excess_can_be_deposited(self):
        row = self.rows[1]
        policy = self._policy(row)
        original = parse_snapshot(row["board"])
        detection = next(i for i in original.inventory if i.is_treasure_detection_scroll)
        target = policy._mining_detection_stock_target(original)
        # Keep the captured item and character, removing unrelated candidates.
        for count, expected in ((target, 0), (target + 3, 3)):
            carried = replace(detection, count=count)
            board = replace(original, inventory=(carried,))
            with patch.object(policy, "_inventory_overweight", return_value=True):
                selected = policy._overweight_home_deposit(board)
            self.assertEqual(policy._retention_surplus(board, carried), expected)
            self.assertEqual(selected, carried if expected else None)
            if selected is not None:
                self.assertEqual(policy._home_deposit_batch(board, selected),
                                 ((carried, expected),))

    def test_restored_checkpoint_preserves_purchased_scrolls(self):
        board = parse_snapshot(self.rows[1]["board"])
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_runs_completed = 1
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        carried = next(i for i in board.inventory if i.is_treasure_detection_scroll)

        self.assertEqual(restored._mining_detection_scroll_target(board), 4)
        self.assertEqual(restored._mining_detection_stock_target(board), 9)
        self.assertEqual(restored._retention_surplus(board, carried), 0)
        selected = restored._overweight_home_deposit(board)
        self.assertTrue(selected is None or not selected.is_treasure_detection_scroll)


if __name__ == "__main__":
    unittest.main()
