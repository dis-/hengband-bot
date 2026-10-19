"""Pins for #80: a refused exchange destroy must end the decision.

The full-pack loot triage binds its finder to one carried stack.  After the
superior-item refusal removes that stack, the finder returns the same object
again; the dispatch loop then repeated the identical refusal forever (the live
watchdog fired after 90 s with the item-identity hash as the top frame).
"""

import tests  # noqa: F401  -- runtime-file isolation
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import TVAL_SCROLL
from hengbot.policy import HengbotPolicy
from policy_fixtures import item
from tests.test_destroy_superior_item_guard import captured_rows, snapshot_at

FIXTURE = (
    Path(__file__).parent / "fixtures"
    / "victory-exchange-refusal-20261019.checkpoint.json.gz"
)
FIXTURE_SHA256 = "aff060dad698b7f789285b0bf7eb9b3a214b785c0c2b8d4e85802e221e0fff6b"
DECISION_BUDGET_SECONDS = 10.0


def _bounded(call):
    """Run ``call`` in a daemon thread; return (finished, result, seconds)."""
    outcome = {}

    def run():
        outcome["result"] = call()

    worker = threading.Thread(target=run, daemon=True)
    started = time.perf_counter()
    worker.start()
    worker.join(DECISION_BUDGET_SECONDS)
    return not worker.is_alive(), outcome.get("result"), time.perf_counter() - started


class VerifiedDestroyRefusalTerminatesTest(unittest.TestCase):
    def test_bound_finder_refusal_returns_without_destroying(self):
        """SEAM: the triage finder shape (bound stack, surplus re-check)."""
        policy = HengbotPolicy()
        snapshot = snapshot_at(captured_rows(), 2107)
        carried = item("a", TVAL_SCROLL, 1, name="Scroll", count=1, fully_known=True)
        snapshot = replace(snapshot, inventory=[carried])
        finder = lambda current, selected=carried: (  # noqa: E731
            selected if policy._entire_stack_is_surplus(current, selected) else None
        )
        with patch.object(policy, "_entire_stack_is_surplus", return_value=True), \
             patch.object(policy, "_destroy_would_discard_superior_item", return_value=True):
            finished, key, _seconds = _bounded(
                lambda: policy._verified_destroy_key(
                    snapshot, finder, "inventory:exchange-cheapest-surplus"
                )
            )
        self.assertTrue(finished, "refused bound stack must not be retried forever")
        self.assertIsNone(key)
        self.assertEqual(policy.last_reason, "inventory:destroy-refused-superior-item")

    def test_refusal_still_advances_to_a_different_candidate(self):
        """SEAM: a finder that yields another stack after the refusal keeps it."""
        policy = HengbotPolicy()
        snapshot = snapshot_at(captured_rows(), 2107)
        refused = item("a", TVAL_SCROLL, 1, name="Scroll A", count=1, fully_known=True)
        surplus = item("b", TVAL_SCROLL, 2, name="Scroll B", count=1, fully_known=True)
        snapshot = replace(snapshot, inventory=[refused, surplus])
        finder = lambda current: next(iter(current.inventory), None)  # noqa: E731
        with patch.object(policy, "_entire_stack_is_surplus", return_value=True), \
             patch.object(
                 policy, "_destroy_would_discard_superior_item",
                 side_effect=lambda _snapshot, candidate: candidate is refused,
             ):
            finished, key, _seconds = _bounded(
                lambda: policy._verified_destroy_key(
                    snapshot, finder, "inventory:exchange-cheapest-surplus"
                )
            )
        self.assertTrue(finished)
        self.assertIsNotNone(key)
        self.assertEqual(
            policy.last_reason, "inventory:destroy-after-superior-item-refusal"
        )

    def test_recorded_victory_board_decides_within_budget(self):
        """RECORDED: the replayed board that never returned at 8a1f6bba."""
        raw = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FIXTURE_SHA256)
        payload = json.loads(gzip.decompress(raw).decode("utf-8"))
        policy = restore_checkpoint(HengbotPolicy, payload["checkpoint"])
        _decoded, snapshots = _consume_response_sequence(
            [payload["board"]], policy, lambda _key: True
        )
        board = snapshots[-1]
        self.assertFalse(board.in_town)
        finished, key, seconds = _bounded(lambda: policy.choose_key(board))
        self.assertTrue(finished, f"decision exceeded {DECISION_BUDGET_SECONDS} s")
        self.assertLess(seconds, DECISION_BUDGET_SECONDS)
        self.assertTrue(key)


if __name__ == "__main__":
    unittest.main()
