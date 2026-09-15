"""Recorded regression pins for interrupted native travel to a store."""

import gzip
import json
import time
import unittest
from pathlib import Path

from hengbot.control_client import ControlClient
from hengbot.input_executor import Operation, OperationExecutor, ScreenKind
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisitPhase
from tests.test_input_executor import FaithfulHookGame, command_screen


ROOT = Path(__file__).resolve().parents[1]
RECORDED = (
    ROOT / "tests" / "fixtures" /
    "travel-interrupted-store-await-20260915.jsonl.gz"
)
SCREEN = (
    ROOT / "jsonlog" /
    "live-screen-35-town-no-progress-stuck-20260915.json"
)
GENUINE_ENTRY = (
    ROOT / "tests" / "fixtures" /
    "barrier-home-auto-entry-lines-1-23.jsonl.gz"
)
TRAVEL = "\x1b`n(."


def recorded_rows():
    with gzip.open(RECORDED, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


class TravelInterruptedStoreAwaitTest(unittest.TestCase):
    def test_recorded_command_barrier_replans_interrupted_home_travel(self):
        rows = recorded_rows()
        policy = HengbotPolicy()
        before = parse_snapshot(rows[0], {})
        policy.prime(before)
        travel = policy.choose_key(before)
        self.assertEqual((travel, policy.last_reason), (TRAVEL, "shop:travel"))

        game = FaithfulHookGame()
        game.state = rows[0]
        game.screen = command_screen(rows[0]["turn"])
        game.states = [rows[-1]]
        game.screens = [json.loads(SCREEN.read_text(encoding="utf-8"))["result"]]
        client = ControlClient(
            1, request_budget=2, retries=1, backoff=0,
            socket_factory=game.socket_factory,
        )
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: ())
        self.assertEqual(
            executor.observe_boundary(deadline=time.monotonic() + 2).outcome,
            "ready",
        )
        result = executor.submit(
            Operation(1, "shop:travel", travel, rows[0]),
            deadline=time.monotonic() + 2,
        )
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(result.screen.kind, ScreenKind.COMMAND)
        self.assertEqual(game.accepted, [TRAVEL])

        policy.confirm_key_posted(travel)
        interrupted = parse_snapshot(result.board, {})
        retry = policy.choose_key(interrupted)
        self.assertEqual(
            (retry, policy.last_reason),
            (TRAVEL, "store:entry-interrupted-replan"),
        )
        self.assertEqual(policy._store_visit.phase, StoreVisitPhase.ENTERING)
        self.assertIsNone(policy._store_visit.posted_sequence)
        self.assertEqual(interrupted.completed_operation_owner, "shop:travel")
        self.assertEqual(interrupted.completed_operation_sequence, 1)

    def test_identical_jsonl_board_without_barrier_does_not_replan(self):
        rows = recorded_rows()
        policy = HengbotPolicy()
        before = parse_snapshot(rows[0], {})
        policy.prime(before)
        travel = policy.choose_key(before)
        policy.confirm_key_posted(travel)

        unbound = parse_snapshot(rows[-1], {})
        self.assertIsNone(unbound.completed_operation_sequence)
        policy.choose_key(unbound)
        self.assertNotEqual(policy.last_reason, "store:entry-interrupted-replan")

    def test_genuine_entry_waits_once_without_duplicate_post(self):
        rows = recorded_rows()
        policy = HengbotPolicy()
        before = parse_snapshot(rows[0], {})
        policy.prime(before)
        travel = policy.choose_key(before)
        policy.confirm_key_posted(travel)
        with gzip.open(GENUINE_ENTRY, "rt", encoding="utf-8-sig") as stream:
            entrance = parse_snapshot(
                [json.loads(line) for line in stream][21], {}
            )

        wait = policy.choose_key(entrance)
        self.assertEqual((wait, policy.last_reason), (
            "", "store:entry-await-observation",
        ))
        self.assertEqual(policy._store_visit.posted_sequence, 1)
        self.assertEqual(policy._store_visit.phase, StoreVisitPhase.ENTERING)
        self.assertEqual(TRAVEL, policy._store_visit.composed_key)

    def test_fixture_freezes_incident_state_facts(self):
        rows = recorded_rows()
        self.assertEqual([row["turn"] for row in rows], [
            2_898_514, 2_898_514, 2_898_514, 2_898_719,
        ])
        final = rows[-1]
        self.assertEqual((final["player"]["y"], final["player"]["x"]),
                         (41, 115))
        self.assertEqual(final["player"]["food_state"], "hungry")
        self.assertEqual(len(final["inventory"]), 23)
        self.assertEqual(len(final["messages"]), 2)
        self.assertNotIn("store", final)


if __name__ == "__main__":
    unittest.main()
