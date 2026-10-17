"""Pin the required-store repetition-latch fallback against the captured loop."""

from __future__ import annotations

import gzip
import json
import unittest
from pathlib import Path

import tests  # noqa: F401
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "store-latch-select-20261017.jsonl.gz"
)


def _captured_inputs():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    states = [
        parse_snapshot(row)
        for row in rows
        if "grid_map" in row or "store" in row
    ]
    decisions = {
        row["decision_sequence"]: row
        for row in rows
        if "decision_sequence" in row
    }
    return states, decisions


class StoreLatchSelectRecordedTest(unittest.TestCase):
    def test_captured_base_decisions_repeat_the_uncomposable_store_route(self):
        _states, decisions = _captured_inputs()
        entry, inside, door, reentry = (
            decisions[sequence] for sequence in (100, 101, 102, 103)
        )

        self.assertEqual(
            (entry["key"], entry["reason"], entry["requested_store"]),
            ("9", "town:repetition-required-shopping", 2),
        )
        selector = entry["shop_selector"]
        self.assertEqual(selector["winning_rung"], "equipment:sale-refused")
        self.assertEqual(selector["rejection_reason"], "preempted")
        self.assertEqual(
            (
                selector["considered_candidate"]["name"],
                selector["considered_candidate"]["letter"],
                selector["considered_candidate"]["price"],
                selector["considered_candidate"]["count"],
            ),
            ("鉄弾 (1d3) (+0,+0) (20/shot 35/turn)", "s", 3, 99),
        )
        self.assertEqual((inside["key"], inside["reason"]), ("\x1b", "town:blocked:repetition"))
        self.assertFalse(inside["store_visit"]["operation_posted"])
        self.assertEqual((door["key"], door["reason"]), ("1", "town:blocked:repetition"))
        self.assertEqual(
            (reentry["key"], reentry["reason"]),
            ("9", "shop:approach"),
        )

    def test_captured_boards_exit_the_latch_without_reentering_store_two(self):
        states, _decisions = _captured_inputs()
        store_page = next(state for state in states if state.store is not None)
        door = next(state for state in states if state.turn == 1146953)
        outside = next(state for state in states if state.turn == 1146964)

        # DECLARED CONSTRUCTED: only the private repetition latch is restored;
        # its state is not serialized in the raw game board.
        policy = HengbotPolicy()
        policy.prime(door)
        policy._town_blocked_reason = "repetition"
        policy._visit_departure_committed = False

        self.assertFalse(policy._town_blocked_purchase_is_composable(store_page))
        self.assertEqual(policy._town_blocked_key(store_page), "\x1b")
        self.assertEqual(policy.last_reason, "town:blocked:repetition")

        self.assertEqual(policy._town_blocked_key(door), "1")
        self.assertEqual(policy.last_reason, "town:blocked:repetition")
        self.assertIsNone(policy._next_required_store_type(outside))

        self.assertEqual(policy._town_blocked_key(outside), "rga")
        self.assertEqual(policy.last_reason, "town:repetition-depart:recall")


if __name__ == "__main__":
    unittest.main()
