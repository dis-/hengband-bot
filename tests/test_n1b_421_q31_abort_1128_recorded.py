"""Quest 31 on n1-b life-421 (2026-11-28 18:13:47): the abort's stair owns the leave question,
and the Magic-Eater answers the monster beside it with its stronger attack.

On the Quest 31 floor (『柳じじい』, fixed ONCE kill-all, dungeon 0 level 22) the Klackon Magic-Eater
(CL31, HP 568, dual-wielding at main-hand to-hit -54) swung at the Vorpal bunnies, Sasquatches
and Sabre-tooth tigers beside the hold [18,1] (``quest-strategy:melee``, five blows a turn
missing), drank its six Healing potions, and at HP 135 posted the plan's withdrawal '<'
(``quest-strategy:abort``).  The game asked 「本当にこの階を去りますか？[y/n]」 and the executor stopped:
the abort's reason was in no list of the stair leaves that own the question.  The stair now names
the quest loss (``quest-strategy:abort:stairs-quest-fail``) and every reason with that suffix in
the reason registry owns it (reasons.quest_leave_stair_reasons).

Recorded (tests/extract_n1b_421_q31_abort_1128_fixture.py, ``n1b-421-q31-abort-1128``): three
boards of the capture (two melee boards and the abort board), their recorded decisions, the stop
screen and its stderr line.  Each board is decided through ``choose_key`` by a fresh production
policy; the stair is posted through the production executor into the recorded stop screen.

DECLARED CONSTRUCTED:
- the skill-exp cache (the capture has no knowledge rows);
- the Magic-Eater's absorbed list (the capture does not log it; the readiness record counted 46
  device rounds): one absorbed Fire Bolt wand power of 20 charges, listed before the melee board;
- the board after the answered leave (the town); the capture stopped before it.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import UP_STAIRS_KEY
from hengbot.policy_quest import QUEST_ABORT_STAIRS_REASON, QUEST_FAIL_STAIR_REASONS
from hengbot import reasons
from tests.support import recorded as executor_pins
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-421-q31-abort-1128.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

QUESTION = "本当にこの階を去りますか？[y/n]"
MELEE_BUNNY, MELEE_SASQUATCH, ABORT = 5050459, 5050506, 5050950
RACES = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
FIRE_BOLT = power_list("wand", row("ファイア・ボルト", 5, current=20, count=3))


def raw_board(turn):
    return copy.deepcopy(next(board for board in CASE["boards"] if board["turn"] == turn))


def decide(turn, *, powers=None):
    """(key, reason, policy, board) of the recorded board by a fresh production policy."""
    raw = raw_board(turn)
    policy = _policy(Path(tempfile.mkdtemp()), RACES)
    policy.prime(parse_snapshot(copy.deepcopy(raw), RACES))
    policy._skill_exp_cache = (0, 0, raw["player"]["level"], policy._town_visit_epoch)
    if powers is not None:
        observe_lists(policy, parse_snapshot(
            dict(copy.deepcopy(raw), turn=raw["turn"] - 1, _magic_eater_power_list=powers), RACES))
    board = policy.with_known_skill_exp(parse_snapshot(raw, RACES))
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason, policy, board


class RecordingTest(unittest.TestCase):

    def test_the_process_stopped_on_the_abort_stairs_unowned_leave_question(self):
        recorded = {row["turn"]: (row["key"], row["reason"]) for row in CASE["recorded"]}
        self.assertEqual(recorded[ABORT], ("<", "quest-strategy:abort"))
        self.assertEqual(recorded[MELEE_SASQUATCH][1], "quest-strategy:melee")
        last = raw_board(ABORT)
        self.assertEqual(((last["player"]["y"], last["player"]["x"]), last["floor"]["quest_id"],
                          last["player"]["hp"]), ((18, 1), 31, 135))
        self.assertEqual((CASE["stop"]["input_kind"], CASE["stop"]["input_prompt"]), ("confirm", QUESTION))
        self.assertIn("owner=quest-strategy:abort", CASE["stderr"][0])
        self.assertIn("unowned confirm", CASE["stderr"][0])


class AbortStairTest(unittest.TestCase):

    def test_the_abort_stair_names_the_quest_loss_and_owns_the_question(self):
        key, reason, policy, board = decide(ABORT)
        self.assertEqual((key, reason), (UP_STAIRS_KEY, QUEST_ABORT_STAIRS_REASON))
        self.assertFalse(policy._quest_floor_exit_locked(board))
        self.assertTrue(policy._quest_exit_would_fail(board))
        self.assertTrue(policy.quest_leave_confirmation_owned(board, UP_STAIRS_KEY))

    def test_the_owning_reasons_are_the_registry_rows_with_the_suffix(self):
        self.assertEqual(QUEST_FAIL_STAIR_REASONS, reasons.quest_leave_stair_reasons())
        self.assertIn(QUEST_ABORT_STAIRS_REASON, QUEST_FAIL_STAIR_REASONS)
        for reason in QUEST_FAIL_STAIR_REASONS:
            self.assertTrue(reason.endswith(reasons.QUEST_LEAVE_STAIR_SUFFIX), reason)
            self.assertIsNotNone(reasons.lookup(reason), reason)


class PostedThroughTheExecutorTest(executor_pins.ProductionHarness):

    def _post(self, policy, board, key):
        raw = raw_board(ABORT)
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
            decision={"sequence": CASE["recorded"][-1]["sequence"], "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract(), in_store=False,
        )
        self.assertIsNone(chain)
        return game, port.last_result, sent

    def test_the_abort_stair_is_answered_y_in_the_same_post(self):
        key, reason, policy, board = decide(ABORT)
        self.assertEqual((key, reason), (UP_STAIRS_KEY, QUEST_ABORT_STAIRS_REASON))
        game, result, sent = self._post(policy, board, key)
        self.assertTrue(sent)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["<", "y"])


class AdjacentAnswerTest(unittest.TestCase):

    def test_an_absorbed_bolt_beside_the_sasquatch_is_used_instead_of_the_missing_blows(self):
        for turn in (MELEE_BUNNY, MELEE_SASQUATCH):
            key, reason, _policy_, board = decide(turn, powers=FIRE_BOLT)
            self.assertTrue(any(monster.distance <= 1 for monster in board.visible_monsters))
            self.assertNotEqual(reason, "quest-strategy:melee", (turn, key))
            self.assertTrue(reason.startswith("ranged:magic-eater"), (turn, key, reason))

    def test_without_a_stronger_answer_the_blow_is_kept(self):
        key, reason, _policy_, _board = decide(MELEE_SASQUATCH)
        self.assertEqual(reason, "quest-strategy:melee", key)


if __name__ == "__main__":
    unittest.main()
