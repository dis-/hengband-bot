"""n1-a life-471 (2026-11-03 11:14): a hungry mana eater in Q2's final patrol.

The Magic-Eater-food character (FOOD_TYPE_MANA) turned hungry on the one-shot
Q2 floor with no wand or staff charge.  The ordinary return is refused by the
quest's exit lock, and the starvation gate (_survival_gate_key) leaves such a
floor only at weak-or-worse: while merely hungry the quest is finished first.
The mana override turned that deferral into a WAIT under
town:blocked:survival-mana-no-charges; three restarts stopped the same way
and the character was retired.

Recorded: the restarted process's board, its ~f response and the decision
after it (tests/extract_mana_quest_hunger_fixture.py).  Through the public
chooser the override now yields to the quest owner, and its key is posted
through the production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _consume_response_sequence,
    _send_new_decision_key,
)
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.support import recorded as executor_pins
from town_work_corpus import monraces


FIXTURE = Path(__file__).with_name("fixtures") / "mana-quest-hunger-20261103.json.gz"
STOP = "town:blocked:survival-mana-no-charges"
QUAFF_PROMPT = "どの薬を飲みますか? "


class ManaQuestHungerRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.races = monraces()

    def decide(self):
        """The restarted process: prime, request ~f, decide the stop board."""
        policy = HengbotPolicy()
        policy._monrace_knowledge = self.races
        primed = parse_snapshot(copy.deepcopy(self.case["primed"]), self.races)
        policy.prime(primed)
        self.assertEqual(policy.choose_key(primed), "~f\x1b")
        policy.confirm_key_posted("~f\x1b")
        with TemporaryDirectory() as raw:
            _consume_response_sequence(
                [json.dumps(self.case["response"], ensure_ascii=False) + "\n"],
                policy, lambda _key: True, self.races, parse_snapshots=False,
                knowledge_ledger_path=Path(raw) / "knowledge.jsonl")
        board = parse_snapshot(copy.deepcopy(self.case["board"]), self.races)
        return policy, board, policy.choose_key(board)

    def test_hungry_mana_eater_finishes_the_locked_quest(self):
        decision = self.case["decision"]
        self.assertEqual((decision["turn"], decision["key"], decision["reason"]),
                         (592761, "5", STOP))
        policy, board, key = self.decide()
        self.assertEqual((board.floor_key, board.player.food_state), ((0, 15, 2), "hungry"))
        self.assertTrue(policy._return_exit_locked(board))
        self.assertIsNone(policy._find_edible(board))
        self.assertNotEqual(policy.last_reason, STOP)
        # The quest owner acts (the fresh process quaffs its speed potion).
        self.assertEqual(policy.last_reason, "quest:quaff-speed")
        speed = next(item for item in board.inventory if key == "q" + item.slot)
        self.assertIn("スピード", speed.name)

        raw = self.case["board"]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the game's next board after the posted key.
        game.screens = [executor_pins.prompt_screen(QUAFF_PROMPT),
                        executor_pins.command_screen(raw["turn"] + 10)]
        following = copy.deepcopy(raw)
        following["turn"] += 10
        game.states = [copy.deepcopy(raw), following]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract(),
        )
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, ["q", speed.slot])


if __name__ == "__main__":
    unittest.main()
