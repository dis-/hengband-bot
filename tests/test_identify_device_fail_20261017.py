"""Pins for the captured identify chooser disturbance."""
import tests  # noqa: F401
import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.input_executor import Continuation, Operation, ScreenKind
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_identification import IDENTIFY_ITEM_PROMPT, SOURCE_PROMPT
import tests.test_input_executor as harness

FIXTURE = Path(__file__).with_name("fixtures") / "identify-device-fail-20261017.jsonl.gz"


def boards():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [row for line in stream if line.strip()
                if (row := json.loads(line)).get("kind") == "captured-board"]


def terminal_pin():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return next(json.loads(line) for line in stream
                    if json.loads(line).get("kind") == "captured-terminal")


def state_from(row):
    return {
        "turn": row["turn"], "messages": list(row["messages"]),
        "inventory": copy.deepcopy(row["inventory"]), "equipment": [],
        "grid_map": {"runs": []},
    }


class IdentifyDeviceFailPins(unittest.TestCase):
    def run_attempt(self, ending_message=None):
        before_row, after_row = boards()
        before, after = state_from(before_row), state_from(after_row)
        if ending_message is not None:
            after["messages"] = [ending_message]
            if ending_message == "An unrelated message.":
                after["inventory"][1]["pseudo_feeling"] = None
        game = harness.FaithfulHookGame()
        game.state = copy.deepcopy(before)
        game.screens = [
            harness.prompt_screen(SOURCE_PROMPT["u"][0].rstrip()),
            harness.command_screen(after["turn"]),
        ]
        game.states = [copy.deepcopy(before), copy.deepcopy(after)]
        helper = harness.ProductionHarness()
        game, client, executor = helper.make(game)
        self.addCleanup(client.close)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        result = executor.submit(Operation(
            4412, "identify:dungeon-equipment", "u", before, [
                Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "i", SOURCE_PROMPT["u"]),
                Continuation(frozenset({ScreenKind.ITEM_TARGET}), "m", IDENTIFY_ITEM_PROMPT),
            ],
        ), deadline=9999999999)
        return game, executor, result

    def test_captured_disturbance_completes_operation_and_drops_target_tail(self):
        captured_before, captured_after = boards()
        captured_stop = terminal_pin()
        self.assertEqual((captured_stop["outcome"], captured_stop["reason"], captured_stop["marker"]),
                         ("stuck-prompt", "expected prompt absent",
                          "<identify:staged-tail-dropped:executor-barrier>"))
        self.assertEqual((captured_before["decision_sequence"], captured_before["turn"],
                          captured_before["key"], captured_before["reason"]),
                         (4412, 855720, "uim", "identify:dungeon-equipment"))
        self.assertEqual((captured_after["decision_sequence"], captured_after["turn"],
                          captured_after["key"], captured_after["reason"]),
                         (4412, 855731, "uim", "identify:dungeon-equipment"))
        self.assertEqual(captured_before["messages"], ["????????????"])
        self.assertEqual(captured_after["messages"], ["??????????????(m)??????????..."])
        game, executor, result = self.run_attempt()
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertIsNone(result.reason)
        self.assertEqual(game.accepted, ["u", "i"])
        self.assertEqual(result.operation.dropped_continuations, ["m"])
        self.assertEqual(result.board["inventory"][1]["pseudo_feeling"], "average")
        self.assertFalse(result.board["inventory"][1]["known"])
        self.assertIsNone(executor.active)

    def test_exact_device_failure_still_completes_without_target_key(self):
        game, _executor, result = self.run_attempt("You failed to use the staff properly.")
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(game.accepted, ["u", "i"])
        self.assertEqual(result.operation.dropped_continuations, ["m"])

    def test_unrelated_absent_target_still_stops_visibly(self):
        game, _executor, result = self.run_attempt("An unrelated message.")
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("expected prompt absent", result.reason)
        self.assertEqual(game.accepted, ["u", "i"])

    def test_policy_can_retry_unknown_sensed_target_with_existing_bound(self):
        raw = json.loads((Path(__file__).with_name("fixtures") / "live-screens" /
                          "20-sweep-identify-item-target.json").read_text(encoding="utf-8"))["state"]["result"]
        policy = ConservativePolicy()
        first_key = policy._identify_carried_item_key(
            parse_snapshot(raw, {}), lambda item: item.slot == "g", "identify:dungeon-equipment"
        )
        self.assertEqual((first_key, policy.last_reason), ("umg", "identify:dungeon-equipment"))
        sensed = copy.deepcopy(raw)
        target = next(item for item in sensed["inventory"] if item["slot"] == "g")
        target["pseudo_feeling"] = "average"
        retry = policy._identify_carried_item_key(
            parse_snapshot(sensed, {}), lambda item: item.slot == "g", "identify:dungeon-equipment"
        )
        self.assertEqual((retry, policy.last_reason), ("umg", "identify:dungeon-equipment"))
        self.assertEqual(policy._identify_fail_streak, 1)


if __name__ == "__main__":
    unittest.main()
