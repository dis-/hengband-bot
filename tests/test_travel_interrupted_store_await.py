"""Recorded regression pins for interrupted native travel to a store."""

import gzip
import json
import time
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.control_client import ControlClient
from hengbot.input_executor import Operation, OperationExecutor, ScreenKind
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase
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
SECOND_PROMPT_REPLAY = (
    ROOT / "jsonlog" /
    "replay-20260917-2355-travel-interrupt-state.jsonl"
)
OWNER_SET_RECORDED = (
    ROOT / "tests" / "fixtures" /
    "travel-entry-owner-set-turns-3751142-3751311.jsonl"
)
EDIT = Path("C:/hengband/lib/edit")
TRAVEL = "\x1b`n(."


def recorded_rows():
    with gzip.open(RECORDED, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


class TravelInterruptedStoreAwaitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

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

    def test_recorded_equipment_home_travel_owner_replans_interruption(self):
        rows = [
            json.loads(line)
            for line in OWNER_SET_RECORDED.read_bytes().splitlines()
        ]
        before = parse_snapshot(rows[0], {})
        self.assertEqual(
            (before.turn, before.player.position.y, before.player.position.x),
            (3_751_142, 31, 150),
        )

        policy = HengbotPolicy()
        policy.prime(before)
        policy._decision_sequence = 338
        policy._store_visit = StoreVisit(
            owner="equipment-transaction",
            purpose="equipment-work",
            store_type=STORE_HOME,
            phase=StoreVisitPhase.ENTERING,
            composed_key=TRAVEL,
            posted_sequence=338,
        )
        policy._store_entry_posted_owner = STORE_HOME
        policy._store_entry_wait_key = TRAVEL

        interrupted_row = dict(rows[1])
        interrupted_row["_completed_operation_owner"] = (
            "equipment-transaction:travel-home"
        )
        interrupted_row["_completed_operation_sequence"] = 338
        interrupted = parse_snapshot(interrupted_row, self.monrace)
        self.assertEqual(
            (interrupted.turn, interrupted.player.position.y,
             interrupted.player.position.x),
            (3_751_311, 36, 129),
        )
        self.assertIsNone(interrupted.store)

        retry = policy.choose_key(interrupted)
        self.assertEqual(
            (retry, policy.last_reason),
            (TRAVEL, "store:entry-interrupted-replan"),
        )
        self.assertEqual(policy._store_visit.phase, StoreVisitPhase.ENTERING)
        self.assertIsNone(policy._store_visit.posted_sequence)

    def test_second_recorded_travel_prompt_reissues_non_empty_macro(self):
        rows = [
            json.loads(line)
            for line in SECOND_PROMPT_REPLAY.read_bytes().splitlines()
        ]
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        # pin_vacuity: the second-prompt capture begins after the Home visit
        # request and its completed knowledge scan established route ownership;
        # even its earlier captured rows contain neither state and independently
        # request another scan.  The prior recorded Home-travel board is the
        # smallest production producer of that missing ownership: public
        # choose_key creates the visit, town plan, and native travel state.
        first = parse_snapshot(recorded_rows()[0], self.monrace)
        policy.prime(first)
        travel = policy.choose_key(first)
        self.assertEqual(travel, TRAVEL)
        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertTrue(policy.confirm_key_posted(travel))

        interrupted = replace(
            parse_snapshot(rows[1], self.monrace),
            completed_operation_owner="shop:travel",
            completed_operation_sequence=1,
        )
        retry = policy.choose_key(interrupted)
        self.assertEqual(
            (retry, policy.last_reason),
            (TRAVEL, "store:entry-interrupted-replan"),
        )
        self.assertTrue(policy.confirm_key_posted(retry))

        second_prompt = parse_snapshot(rows[2], self.monrace)
        second_retry = policy.choose_key(second_prompt)
        self.assertEqual(second_retry, TRAVEL)
        self.assertEqual(policy.last_reason, "store:entry-interrupted-replan")

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
