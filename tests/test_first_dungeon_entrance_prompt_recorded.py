"""Recorded first-entrance board and source-ordered modal transport pins."""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.cli import (
    PostingContract, SendResult, _ExecutorInputPort, _send_new_decision_key,
)
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import ENTER_DUNGEON_MACRO
from tests import test_input_executor as executor_pins


CAPTURE = Path(__file__).with_name("fixtures") / "first-dungeon-entrance-board.json.gz"
ENTRANCE_QUESTION = "\u672c\u5f53\u306b\u3053\u306e\u30c0\u30f3\u30b8\u30e7\u30f3\u306b\u5165\u308a\u307e\u3059\u304b\uff1f[y/n]"


class FirstDungeonEntrancePromptRecordedPins(executor_pins.ProductionHarness):
    def capture(self):
        with gzip.open(CAPTURE, "rt", encoding="utf-8") as stream:
            return json.load(stream)

    def drive(self, screens, *, restored=False):
        capture = self.capture()
        raw = capture["board"]
        snapshot = parse_snapshot(raw, {})
        policy = ConservativePolicy()
        policy.last_reason = capture["decision"]["reason"]
        policy._decision_sequence = capture["decision"]["decision_sequence"]
        if restored:
            policy = restore_checkpoint(ConservativePolicy, checkpoint(policy))
        self.assertIsNone(policy.peek_staged_prompt_chain())
        self.assertEqual(policy.last_reason, "descend")
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = screens
        game.states = [copy.deepcopy(raw) for _ in screens]
        final = game.states[-1]
        final["turn"] = raw["turn"] + 1
        final["floor"]["level"] = 1
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", capture["decision"]["key"], None, set(),
            in_store=False,
            decision={"sequence": policy._decision_sequence,
                      "reason": policy.last_reason},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        return capture, game, port, sent

    def test_capture_pins_preposted_macro_and_entrance_board(self):
        capture = self.capture()
        self.assertEqual(capture["source"],
                         "incident-20260928-2130-first-dungeon-entrance-prompt")
        self.assertEqual(capture["decision"], {
            "decision_sequence": 31, "turn": 82671, "reason": "descend",
            "key": ">\ry", "position": {"y": 31, "x": 150},
        })
        self.assertEqual(
            [(row["character"], row["character_index"], row["composed_key"])
             for row in capture["posted"]],
            [(char, index, ">\ry") for index, char in enumerate(">\ry")],
        )
        snapshot = parse_snapshot(capture["board"], {})
        self.assertTrue(snapshot.in_town)
        self.assertEqual(snapshot.dungeon_level, 0)
        self.assertTrue(snapshot.grid_at(snapshot.player.position).has_entrance)
        self.assertEqual(ENTER_DUNGEON_MACRO, ">\ry")

    def test_first_entrance_clears_observed_more_then_answers_observed_confirm(self):
        capture, game, port, sent = self.drive([
            executor_pins.prompt_screen("There is the entrance of Yeek cave -more-"),
            executor_pins.prompt_screen(ENTRANCE_QUESTION),
            executor_pins.command_screen(82672),
        ])
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, [">", " ", "y"])
        self.assertEqual(port.last_result.operation.accepted_segments,
                         [">", " ", "y"])
        self.assertEqual(port.last_result.board["floor"]["level"], 1)
        self.assertEqual(capture["decision"]["key"], ">\ry")

    def test_first_entrance_confirm_without_more_is_owned_after_restore(self):
        _capture, game, port, sent = self.drive([
            executor_pins.prompt_screen(ENTRANCE_QUESTION),
            executor_pins.command_screen(82672),
        ], restored=True)
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, [">", "y"])

    def test_english_first_entrance_confirmation_is_owned(self):
        _capture, game, port, sent = self.drive([
            executor_pins.prompt_screen("Do you really get in this dungeon? [y/n]"),
            executor_pins.command_screen(82672),
        ])
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, [">", "y"])

    def test_repeat_entrance_without_question_drops_optional_answer(self):
        _capture, game, port, sent = self.drive([
            executor_pins.command_screen(82672)
        ])
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, [">"])
        self.assertEqual(port.last_result.operation.continuations, [])

    def test_other_confirmation_is_never_answered_as_entrance(self):
        _capture, game, port, sent = self.drive([
            executor_pins.prompt_screen("Do you enter? [y/n]"),
        ])
        self.assertFalse(sent)
        self.assertEqual(port.last_result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, [">"])
        self.assertNotIn("y", game.accepted)

    def test_sender_without_prompt_observation_refuses_blind_macro(self):
        capture = self.capture()
        snapshot = parse_snapshot(capture["board"], {})
        accepted = []
        sent, _line = _send_new_decision_key(
            lambda key, **_kwargs: accepted.append(key) or SendResult.SENT,
            "recorded-board", ">\ry", None, set(), in_store=False,
            decision={"sequence": 31, "reason": "descend"},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        self.assertIs(sent, SendResult.TERMINAL)
        self.assertEqual(accepted, [])


if __name__ == "__main__":
    unittest.main()
