"""The 2026-11-02 06:10-06:49 viewing-bot stops (hourly-0700-1102).

Each class pins one root on its recorded board; only the game's replies to
newly posted keys are constructed (marked DECLARED CONSTRUCTED) and facts the
capture keeps outside the board are marked DECLARED RECONSTRUCTED.
Fixture: tests/extract_hourly_0700_1102_fixtures.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import RECALL_DEPTH_PROMPT_MESSAGE_PREFIXES
from tests import test_input_executor as executor_pins
from test_esp_threat_rest_recorded import EDIT


FIXTURE = Path(__file__).with_name("fixtures") / "hourly-0700-1102.json.gz"


def _cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class EspThreatRecallDepthQuestionTest(executor_pins.ProductionHarness):
    """n1-c life-103 06:49:23: esp-threat:leave-recall read ``rh`` on depth 15.

    spells-world.cpp recall_player asked 「ここは最深到達階より浅い階です。
    この階に戻って来ますか？」 (underground, shallower than the saved depth, no
    recall active).  The executor answered it only for a listed set of
    recall owners, so this reader stopped as an unowned confirm.
    """

    READ_PROMPT = "どの巻物を読みますか? "

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["esp-recall"]

    def test_recorded_recall_read_answers_the_depth_question(self):
        decision, raw = self.case["decision"], self.case["board"]
        self.assertEqual((decision["decision_sequence"], decision["reason"], decision["key"]),
                         (3738, "esp-threat:leave-recall", "rh"))
        self.assertIn("owner=esp-threat:leave-recall", self.case["stuck_prompt"])
        self.assertIn("reason=unowned confirm", self.case["stuck_prompt"])
        question = RECALL_DEPTH_PROMPT_MESSAGE_PREFIXES[0]
        self.assertIn(question, self.case["stuck_prompt"])
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        snapshot = parse_snapshot(copy.deepcopy(raw), monrace)
        self.assertEqual(snapshot.floor_key[1], 15)
        self.assertFalse(snapshot.player.recalling)
        self.assertTrue(next(item for item in snapshot.inventory if item.slot == "h").is_recall_scroll)

        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [
            executor_pins.prompt_screen(self.READ_PROMPT),
            executor_pins.prompt_screen(question + " [y/n]"),
            executor_pins.command_screen(raw["turn"] + 1),
        ]
        game.states = [copy.deepcopy(raw) for _ in game.screens]
        # DECLARED CONSTRUCTED: recall_player's effect after the refusal
        # (word_recall set, 「回りの大気が張りつめてきた...」).
        game.states[-1]["turn"] = raw["turn"] + 1
        game.states[-1]["player"]["recalling"] = True
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", decision["key"], None, set(), in_store=False,
            decision={"sequence": decision["decision_sequence"], "reason": decision["reason"]},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        # Recorded: r, h, then stuck-prompt on the unowned depth question.
        self.assertEqual(game.accepted, ["r", "h", "n"])
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed")


if __name__ == "__main__":
    unittest.main()
