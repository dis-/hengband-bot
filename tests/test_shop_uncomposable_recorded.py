"""Recorded continuation pins for shop selection/emission disagreements."""

from __future__ import annotations

import gzip
import json
import unittest
import tests  # noqa: F401
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import LEAVE_STORE_KEY, STORE_STUCK_LIMIT
from hengbot.policy_types import StoreVisit, StoreVisitPhase


FIXTURE = Path(__file__).parent / "fixtures" / "shop-uncomposable-20261013.jsonl.gz"


def _records():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


class ShopUncomposableRecordedTest(unittest.TestCase):
    def _policy(self, record):
        board = parse_snapshot(record["board"])
        policy = HengbotPolicy()
        policy._observe(board)
        policy._build_grid_index(board)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        policy._in_store_ops_enabled = True
        policy._in_store_screen_verified = True
        policy._decision_sequence = record["turn"]
        store_type = board.store.store_type
        policy._store_visit = StoreVisit(
            "town-errand", "shopping", store_type,
            phase=StoreVisitPhase.OPERATING, opened_sequence=1,
        )
        policy._in_store_entry_ledger = {
            "store": store_type, "opened_sequence": 1,
            "ops": record["ledger_ops"], "pending": None, "ended": False,
        }
        return policy, board

    def _advance_observed_operation(self, policy):
        # DECLARED CONSTRUCTED: the emitted store operation was confirmed on
        # the following barrier; clear only its already observed pending state.
        policy._in_store_entry_ledger["ops"] += 1
        policy._in_store_entry_ledger["pending"] = None
        policy._store_visit.operation_posted = False
        policy._store_buy_inflight = None

    def test_both_captured_boards_post_verified_ordinary_buy_then_blocker(self):
        records = _records()
        self.assertEqual(len(records), 2)
        for record in records:
            with self.subTest(capture=record["capture"]):
                policy, board = self._policy(record)
                rows = {item.letter: item for item in board.store.items}
                blocker = rows[record["departure_row"]]
                ordinary = rows[record["ordinary_row"]]
                required = SimpleNamespace(item=blocker, quantity=1)
                self.assertLessEqual(record["ledger_ops"] + 2, STORE_STUCK_LIMIT)

                # The real continuation and _shop composition run. The
                # captured policy context is represented by these two
                # selector outcomes and its recorded purchase quantity.
                with patch.object(
                    policy, "_departure_blocking_page_purchase", return_value=required
                ), patch.object(policy, "_next_purchase", return_value=ordinary), patch.object(
                    policy, "_purchase_quantity",
                    side_effect=lambda _snapshot, item: (
                        record["ordinary_quantity"]
                        if item.letter == ordinary.letter else 1
                    ),
                ):
                    first_key = policy._in_store_entry_key(board)

                self.assertEqual(
                    first_key,
                    f"p{ordinary.letter}{record['ordinary_quantity']}\r\r",
                )
                verified = policy._in_store_telemetry["emitted-buy-verified"]
                self.assertEqual(verified["letter"], ordinary.letter)
                self.assertEqual(verified["identity"], (
                    ordinary.name, ordinary.tval, ordinary.sval, ordinary.count,
                    ordinary.price, ordinary.charges,
                ))
                self.assertTrue(verified["preconditions"]["page_one"])
                self.assertTrue(verified["preconditions"]["identity"])
                self.assertTrue(verified["preconditions"]["screen_on_page"])
                self.assertEqual(policy._in_store_entry_ledger["ops"],
                                 record["ledger_ops"])
                self.assertEqual(policy._in_store_entry_ledger["pending"]["kind"],
                                 "buy")

                # DECLARED CONSTRUCTED: the ordinary purchase is reflected
                # in a fresh shelf with its row removed, leaving the captured
                # departure blocker visible for the next same-visit decision.
                followup = replace(board, store=replace(
                    board.store,
                    items=tuple(item for item in board.store.items
                                if item.letter != ordinary.letter),
                ))
                self._advance_observed_operation(policy)
                remaining_rows = {item.letter: item for item in followup.store.items}
                blocker = remaining_rows[record["departure_row"]]
                required = SimpleNamespace(item=blocker, quantity=1)
                with patch.object(
                    policy, "_departure_blocking_page_purchase", return_value=required
                ), patch.object(policy, "_next_purchase", return_value=blocker), patch.object(
                    policy, "_purchase_quantity", return_value=1
                ):
                    blocker_key = policy._in_store_entry_key(followup)

                self.assertEqual(blocker_key, f"p{blocker.letter}1\r\r")
                self.assertEqual(
                    policy._in_store_entry_ledger["ops"], record["ledger_ops"] + 1
                )
                self.assertEqual(policy._in_store_entry_ledger["pending"]["kind"],
                                 "buy")

                # DECLARED CONSTRUCTED: the required buy is confirmed and
                # removed from the page; the real continuation now leaves.
                after_blocker = replace(followup, store=replace(
                    followup.store,
                    items=tuple(item for item in followup.store.items
                                if item.letter != blocker.letter),
                ))
                self._advance_observed_operation(policy)
                with patch.object(
                    policy, "_departure_blocking_page_purchase", return_value=None
                ), patch.object(policy, "_next_purchase", return_value=None):
                    leave_key = policy._in_store_entry_key(after_blocker)
                self.assertEqual(leave_key, LEAVE_STORE_KEY)
                self.assertLessEqual(
                    policy._in_store_entry_ledger["ops"], STORE_STUCK_LIMIT
                )

    def test_unverifiable_emitted_row_keeps_visible_uncomposable_stop(self):
        record = _records()[0]
        policy, board = self._policy(record)
        blocker = next(item for item in board.store.items
                       if item.letter == record["departure_row"])
        required = SimpleNamespace(item=blocker, quantity=1)
        with patch.object(
            policy, "_departure_blocking_page_purchase", return_value=required
        ), patch.object(policy, "_departure_blocking_page_operation",
                        return_value={"op": "buy", "purchase": required}), patch.object(
            policy, "_shop", return_value="pz\r\r"
        ):
            key = policy._in_store_entry_key(board)

        self.assertEqual(key, "\x1b")
        self.assertEqual(
            policy.last_reason,
            "town:blocked:shop-required-operation-uncomposable",
        )
        diagnostic = policy._shop_selector_diagnostics["required-page-continuation"]
        self.assertEqual(diagnostic["cause"], "selection-emission-mismatch")
        self.assertEqual(diagnostic["row"], blocker.letter)


if __name__ == "__main__":
    unittest.main()
