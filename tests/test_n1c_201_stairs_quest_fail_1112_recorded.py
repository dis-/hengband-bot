"""Quest 31 on n1-c life-201 (2026-11-12 13:21:39): the emergency stair answers the leave question.

On the Quest 31 floor (『柳じじい』, fixed ONCE kill-all, dungeon 0 level 22) the bot read its last
Teleport scroll (decision 7596, ``emergency:teleport``), landed on the up stair [18,1] and posted
'<' (decision 7597, ``emergency:stairs-quest-fail``).  The game asks 「本当にこの階を去りますか？[y/n]」
on a taken ONCE quest floor (cmd-move.cpp confirm_leave_level); quest_leave_confirmation_owned
owned it only for a runtime kill quest, the light release, the breeder abandon and the Quest 25
plan, so the executor stopped on the unowned confirm.  The escape had already accepted the loss
(``_escape_by_stairs`` takes the stair only with the quest exit lock released, and the reason names
the quest failure), so the stair now owns the question and the executor answers 'y'.

The boards are the capture's last two state rows, replayed by one policy through the public
``choose_key``; the stair key is posted through the production executor
(``_send_decision_key_with_prompt_chain`` over ``_ExecutorInputPort``) into the recorded stop
screen (control-at-stop.json: the prompt line and its input context).  DECLARED CONSTRUCTED: the
skill-exp cache (the capture has no knowledge rows), and the boundary after the answer (the board
that follows the leave; the capture stopped before it).
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
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy_quest import QUEST_FAIL_STAIR_REASONS
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests.support import recorded as executor_pins

ROOT = Path(__file__).parents[1]
GAME = Path("C:/hengband/lib/edit")
RACES = load_monrace_knowledge(find_monrace_definitions(ROOT, None) or GAME / "MonraceDefinitions.jsonc")
QUESTS = load_quest_knowledge(find_quest_definitions(ROOT) or GAME / "quests")
STRATEGIES = load_quest_strategies(ROOT / "strategy" / "quests")

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-201-stairs-quest-fail-1112.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

QUESTION = "本当にこの階を去りますか？[y/n]"
STAIR = 7597
REASON = "emergency:stairs-quest-fail"


def replay():
    """(policy, {sequence: (key, reason)}, {sequence: snapshot}) of the two boards by one policy."""
    policy = ConservativePolicy(monrace_knowledge=RACES, quest_knowledge=QUESTS,
                                quest_strategies=STRATEGIES)
    policy.prime(parse_snapshot(copy.deepcopy(CASE["boards"][0]), policy._monrace_knowledge))
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
                         [("emergency:teleport", "re"), (REASON, "<")])
        last = CASE["boards"][-1]
        self.assertEqual(((last["player"]["y"], last["player"]["x"]), last["floor"]["dungeon_id"],
                          last["floor"]["level"], last["floor"]["quest_id"]), ((18, 1), 0, 22, 31))
        self.assertEqual((CASE["stop"]["input_kind"], CASE["stop"]["input_prompt"]), ("confirm", QUESTION))
        self.assertIn(f"owner={REASON}", CASE["stderr"][0])
        self.assertIn("unowned confirm", CASE["stderr"][0])


class ReplayTest(unittest.TestCase):

    def test_the_replay_takes_the_stair_with_the_quest_lock_released(self):
        policy, answers, snapshots = replay()
        self.assertEqual(answers, {row["sequence"]: (row["key"], row["reason"]) for row in CASE["recorded"]})
        board = snapshots[STAIR]
        self.assertFalse(policy._quest_floor_exit_locked(board))
        self.assertTrue(policy._quest_exit_would_fail(board))
        self.assertTrue(policy.quest_leave_confirmation_owned(board, "<"))

    def test_only_a_quest_fail_stair_reason_owns_the_question(self):
        policy, _answers, snapshots = replay()
        board = snapshots[STAIR]
        self.assertFalse(policy.quest_leave_confirmation_owned(board, "re"))
        for reason in sorted(QUEST_FAIL_STAIR_REASONS):
            policy.last_reason = reason
            self.assertTrue(policy.quest_leave_confirmation_owned(board, "<"), reason)
        # DECLARED CONSTRUCTED: an ordinary stair reason does not forfeit the quest.
        policy.last_reason = "emergency:stairs"
        self.assertFalse(policy.quest_leave_confirmation_owned(board, "<"))

    def test_a_held_quest_lock_leaves_the_question_unowned(self):
        policy, _answers, snapshots = replay()
        # DECLARED CONSTRUCTED: the lock still held (the escape would not have posted the stair).
        policy._quest_floor_exit_locked = lambda snapshot: True
        self.assertFalse(policy.quest_leave_confirmation_owned(snapshots[STAIR], "<"))


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

    def test_the_emergency_stair_is_answered_y_in_the_same_post(self):
        policy, answers, snapshots = replay()
        self.assertEqual(answers[STAIR], ("<", REASON))
        game, result, sent = self._post(policy, snapshots[STAIR], "<")
        self.assertTrue(sent)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["<", "y"])

    def test_an_unowned_stair_on_the_quest_floor_still_stops_visibly(self):
        policy, _answers, snapshots = replay()
        # DECLARED CONSTRUCTED: the same '<' under a reason that does not accept the quest loss.
        policy.last_reason = "emergency:stairs"
        self.assertFalse(policy.quest_leave_confirmation_owned(snapshots[STAIR], "<"))
        game, result, sent = self._post(policy, snapshots[STAIR], "<")
        self.assertFalse(sent)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["<"])


if __name__ == "__main__":
    unittest.main()
