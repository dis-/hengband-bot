"""Pins for the captured identify staff wake-up interruption."""
import tests  # noqa: F401
import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.input_executor import Continuation, Operation, ScreenKind
from hengbot.model import TVAL_STAFF
from hengbot.policy_identification import IDENTIFY_ITEM_PROMPT, SOURCE_PROMPT
import tests.test_input_executor as harness

FIXTURE = Path(__file__).with_name("fixtures") / "identify-wake-interrupt-20261017.jsonl.gz"


def rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def capture(kind, **fields):
    return next(row for row in rows() if row.get("kind") == kind
                and all(row.get(key) == value for key, value in fields.items()))


def state_from(row):
    return {
        "turn": row["turn"], "messages": list(row["messages"]),
        "inventory": copy.deepcopy(row["inventory"]), "equipment": [],
        "grid_map": {"runs": []},
    }


class IdentifyWakeInterruptPins(unittest.TestCase):
    def run_attempt(self, *, message=None, source_charges=None):
        before_row = capture("captured-board", role="before")
        after_row = capture("captured-board", role="after")
        before, after = state_from(before_row), state_from(after_row)
        if message is not None:
            after["messages"] = [message]
        if source_charges is not None:
            source = next(item for item in after["inventory"] if item["slot"] == "g")
            source["charges"] = source_charges
        game = harness.FaithfulHookGame()
        game.state = copy.deepcopy(before)
        # Source-derived chooser: the production selector validates visible rows.
        source_screen = harness.prompt_screen("(???:a-z, ESC) " + SOURCE_PROMPT["u"][0].rstrip())
        for row, item in enumerate(before["inventory"], 1):
            source_screen["lines"][row] = item["slot"] + ") " + item["name"]
        game.screens = [
            source_screen,
            harness.command_screen(after["turn"]),
        ]
        game.states = [copy.deepcopy(before), copy.deepcopy(after)]
        helper = harness.ProductionHarness()
        game, client, executor = helper.make(game)
        self.addCleanup(client.close)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        result = executor.submit(Operation(
            2529, "identify:pack-pressure", "u", before, [
                Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "g", SOURCE_PROMPT["u"]),
                Continuation(frozenset({ScreenKind.ITEM_TARGET}), "l", IDENTIFY_ITEM_PROMPT),
            ],
        ), deadline=9999999999)
        return game, executor, result

    def test_captured_wake_interruption_completes_and_drops_target_tail(self):
        decision = capture("captured-decision")
        before = capture("captured-board", role="before")
        after = capture("captured-board", role="after")
        terminal = capture("captured-terminal")
        self.assertEqual((decision["decision_sequence"], decision["key"], decision["reason"]),
                         (2529, "ugl", "identify:pack-pressure"))
        self.assertEqual(capture("captured-posted-keys")["characters"], ["u", "g"])
        self.assertEqual((terminal["outcome"], terminal["reason"]),
                         ("stuck-prompt", "expected prompt absent"))
        self.assertEqual(capture("captured-marker")["text"],
                         "<identify:staged-tail-dropped:executor-barrier>")
        self.assertEqual(before["messages"], ["\u6756\u3092\u3046\u307e\u304f\u4f7f\u3048\u306a\u304b\u3063\u305f\u3002"])
        self.assertEqual(after["messages"], ["\u30c0\u30fc\u30af\u30a8\u30eb\u30d5\u30fb\u30d7\u30ea\u30fc\u30b9\u30c8\u304c\u76ee\u3092\u899a\u307e\u3057\u305f\u3002"])
        old_staff = next(item for item in before["inventory"] if item["slot"] == "g")
        new_staff = next(item for item in after["inventory"] if item["slot"] == "g")
        old_target = next(item for item in before["inventory"] if item["slot"] == "l")
        new_target = next(item for item in after["inventory"] if item["slot"] == "l")
        self.assertEqual(old_staff["tval"], TVAL_STAFF)
        self.assertEqual((old_staff["charges"], new_staff["charges"]), (18, 18))
        self.assertEqual(old_target, new_target)
        self.assertFalse(new_target["known"])
        game, executor, result = self.run_attempt()
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertIsNone(result.reason)
        self.assertEqual(game.accepted, ["u", "g"])
        self.assertEqual(result.operation.dropped_continuations, ["l"])
        self.assertIsNone(executor.active)

    def test_unrelated_absent_prompt_still_stops_visibly(self):
        game, _executor, result = self.run_attempt(message="An unrelated message.")
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("expected prompt absent", result.reason)
        self.assertEqual(game.accepted, ["u", "g"])

    def test_wake_message_with_consumed_staff_charge_is_not_completion_evidence(self):
        game, _executor, result = self.run_attempt(source_charges=17)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("expected prompt absent", result.reason)
        self.assertEqual(game.accepted, ["u", "g"])


if __name__ == "__main__":
    unittest.main()
