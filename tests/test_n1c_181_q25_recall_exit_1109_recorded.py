"""Quest 25 on n1-c life-181 (2026-11-09 19:18:31): the recall exit's '<' answers the leave question.

After the Recall was read the plan walked to the start stair [13,1] (decisions 19990-19994,
``quest25:recall-exit-walk``) and posted '<' there (decision 19995, ``quest25:recall-exit``).  On the
taken ONCE quest floor the game asks 「本当にこの階を去りますか？[y/n]」 (cmd-move.cpp
confirm_leave_level); nothing owned it, the executor stopped on the unowned confirm, and the three
stops retired the life.  The owner decided the leave (2026-11-04 「体力回復を使い切り HP 20% 以下で開始の
階段まで5歩以内なら踏む」, 2026-11-09 「段をやめ射線外で待つ」: 「開始の階段へ行ければ踏み」), so the stair
step owns the question (quest25_battle.owns_leave_confirmation) and the executor answers 'y'.

The boards are the capture's last six state rows, replayed by one policy through the public
``choose_key``; the stair key is posted through the production executor
(``_send_decision_key_with_prompt_chain`` over ``_ExecutorInputPort``) into the recorded stop
screen (control-at-stop.json: the prompt line and its input context).  DECLARED CONSTRUCTED: the
skill-exp cache (the capture has no knowledge rows), and the boundary after the answer (the town
board that follows the leave; the capture stopped before it).
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
import time
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest_room_sweep
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import parse_snapshot
from tests.support import recorded as executor_pins
from tests import test_q25_haunted_house as q25


with gzip.open(Path(__file__).with_name("fixtures") / "n1c-181-q25-recall-exit-1109.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

QUESTION = "本当にこの階を去りますか？[y/n]"
STAIR = 19995


def new_policy():
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy.prime(parse_snapshot(copy.deepcopy(CASE["boards"][0]), policy._monrace_knowledge))
    return policy


def replay():
    """(policy, {sequence: (key, reason)}, {sequence: snapshot}) of the six boards by one policy."""
    policy = new_policy()
    answers, snapshots = {}, {}
    for raw, row in zip(CASE["boards"], CASE["recorded"]):
        # DECLARED CONSTRUCTED: the skill-exp cache of this board (no ~f list in the capture).
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], policy._town_visit_epoch)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = str(policy.choose_key(snapshot))
        answers[row["sequence"]] = (key, policy.last_reason)
        snapshots[row["sequence"]] = snapshot
        if row["sequence"] != STAIR:
            policy.confirm_key_posted(key)
    return policy, answers, snapshots


class RecordingTest(unittest.TestCase):

    def test_the_process_stopped_on_the_unowned_leave_question(self):
        self.assertEqual([(row["reason"], row["key"]) for row in CASE["recorded"]],
                         [(battle.RECALL_EXIT_WALK_REASON, "2")] * 5 + [(battle.RECALL_EXIT_REASON, "<")])
        last = CASE["boards"][-1]
        self.assertEqual(((last["player"]["y"], last["player"]["x"]), last["floor"]["quest_id"],
                          last["player"]["recalling"]), ((13, 1), 25, True))
        self.assertEqual((CASE["stop"]["input_kind"], CASE["stop"]["input_prompt"]), ("confirm", QUESTION))
        self.assertIn("owner=quest25:recall-exit", CASE["stderr"][0])
        self.assertIn("unowned confirm", CASE["stderr"][0])


class ReplayTest(unittest.TestCase):

    def test_the_replay_walks_to_the_start_stair_and_takes_it(self):
        policy, answers, snapshots = replay()
        self.assertEqual(answers, {row["sequence"]: (row["key"], row["reason"]) for row in CASE["recorded"]})
        self.assertTrue(policy.quest_leave_confirmation_owned(snapshots[STAIR], "<"))

    def test_only_the_plans_stair_step_owns_the_question(self):
        policy, _answers, snapshots = replay()
        board = snapshots[STAIR]
        self.assertFalse(policy.quest_leave_confirmation_owned(board, "2"))
        policy.last_reason = battle.RECALL_EXIT_WALK_REASON
        self.assertFalse(policy.quest_leave_confirmation_owned(board, "<"))
        # The restored Healing-used-up exit (quest_room_sweep._leave_by_exit) takes the same stair.
        policy.last_reason = quest_room_sweep.EXIT_REASON
        self.assertTrue(policy.quest_leave_confirmation_owned(board, "<"))


class PostedThroughTheExecutorTest(executor_pins.ProductionHarness):

    def _post(self, policy, board, key):
        raw = copy.deepcopy(CASE["boards"][-1])
        stop = copy.deepcopy(CASE["stop"]["screen"])
        self.assertEqual(classify_screen(stop).kind, ScreenKind.CONFIRM)
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(board.turn)
        game.screens = [stop, executor_pins.command_screen(board.turn + 1)]
        game.states = [copy.deepcopy(raw) for _ in game.screens]
        game.states[0]["input_context"] = {"kind": "confirm", "prompt": QUESTION}
        # DECLARED CONSTRUCTED: the board after the answered leave (the town).
        game.states[-1]["turn"] = board.turn + 1
        game.states[-1]["floor"].update(level=0, quest_id=0, in_town=True)
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line, chain, _result = _send_decision_key_with_prompt_chain(
            port, "recorded-board", key, None, set(),
            policy=policy, shadow_client=None, file=io.StringIO(),
            deadline=time.monotonic() + 30, poll_interval=0.0,
            prompt_japanese=True,
            decision={"sequence": STAIR, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract(), in_store=False,
        )
        self.assertIsNone(chain)
        return game, port.last_result, sent

    def test_the_recall_exit_stair_is_answered_y_in_the_same_post(self):
        policy, answers, snapshots = replay()
        self.assertEqual(answers[STAIR], ("<", battle.RECALL_EXIT_REASON))
        game, result, sent = self._post(policy, snapshots[STAIR], "<")
        self.assertTrue(sent)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["<", "y"])

    def test_an_unowned_stair_on_the_quest_floor_still_stops_visibly(self):
        policy, _answers, snapshots = replay()
        # DECLARED CONSTRUCTED: the same '<' under a reason the plan does not leave by.
        policy.last_reason = battle.RECALL_WAIT_REASON
        self.assertFalse(policy.quest_leave_confirmation_owned(snapshots[STAIR], "<"))
        game, result, sent = self._post(policy, snapshots[STAIR], "<")
        self.assertFalse(sent)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["<"])


if __name__ == "__main__":
    unittest.main()
