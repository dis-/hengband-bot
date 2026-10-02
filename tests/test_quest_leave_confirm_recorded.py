"""Recorded pins: '<' into the unowned quest-leave confirm on Angband 24F (2026-10-02).

Live stops 18:28:13 and 18:29:04 (and 18:33:48): on Angband 24F, random quest
41 (TAKEN, type RANDOM), ``breeder-breakthrough:ascend`` posted '<' and the
game asked 「本当にこの階を去りますか？[y/n]」 (cmd-move.cpp confirm_leave_level);
nothing owned it, so the executor stopped (``<stuck-prompt>
owner=breeder-breakthrough:ascend ... reason=unowned confirm``).

USER RULE (2026-07-26, bot-random-quest-teleport-giveup): leaving a random
quest floor accepts the quest's loss and is allowed only on the genuine
progress-based give-up, never on counts.  That give-up is the release of
``_quest_floor_exit_locked``.

Fix: (1) the breeder breakthrough takes no stair exit while the lock holds;
the ordinary ladder (fight, loot, explore, teleport) owns the decision, like
``_escape_by_stairs``.  (2) Once the lock released, the stair operation owns
the question and answers 'y' (``quest_leave_confirmation_owned`` +
``_quest_leave_continuations``).

Substrate: capture ``autorecover-20261002-182904-exit-no-marker``, the
process that attached at 18:28:18 with a fresh policy.  Its ring keeps the
boards of decisions 217-329.  A fresh policy fed those boards (warm-up
217-289, keys not asserted: the live process had walked this floor since
decision 0) reproduces every live (key, reason) of 290-298, arms the breeder
latch itself on 298 exactly as the live log shows (299 is the first
``breeder-breakthrough:*`` row), and 299 is the first divergence (R4).
DECLARED WALL: the ``skill_exp`` knowledge row and calibration file are the
same character's from the 11:51 process (castle fixture), as in the earlier
2026-10-02 pins.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import copy
import gzip
import hashlib
import io
import json
import re
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _consume_response_sequence,
    _quest_leave_continuations, _send_decision_key_with_prompt_chain,
)
from hengbot.input_executor import ScreenKind
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT, UP_STAIRS_KEY

from test_esp_threat_rest_recorded import EDIT, _policy
from tests import test_input_executor as executor_pins

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "quest-leave-confirm-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "quest-leave-confirm-20261002.boundaries.json"
CASTLE_FIXTURE = FIXTURES / "castle-top-floor-exit-20261002.jsonl.gz"
CALIBRATION = FIXTURES / "wild-ambush-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "6f36e0f9455b31be731a4b1d9eb282396af4239954f87302df486988077bbde9",
    BOUNDARIES: "fb60f2e0ac55dbcef859023ce966fdce15c2c687e436d8072ca73489b127a46f",
    CASTLE_FIXTURE: "a6469df8e139299e623602f9f389e4bbfe7458ffca5f1f7b7edf32c3637b6873",
    CALIBRATION: "a71a507ffe45da1e8ca3c32a59886b3be1c88c6f68b4c6f5d691ab51e0fb6ce5",
}
QUEST_FLOOR = (1, 24, 41)
FIRST = 217
REPRODUCED = range(290, 299)
DIVERGENCE = 299
ASCEND = 329
UPSTAIRS = (17, 31)
# cmd-move.cpp:71 msg_print before the input_check.
LEAVE_WARNING = "この階を一度去ると二度と戻って来られません。 -more-"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _load():
    for path, digest in SHA256.items():
        assert _sha(path) == digest, path
    boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    fields = boundaries["recorded_fields"]
    recorded = {
        row[0]: dict(zip(fields, row)) for row in boundaries["recorded"]
    }
    ends = {int(k): v for k, v in boundaries["board_end"].items()}
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        lines = [json.loads(line)["line"] for line in stream]
    return boundaries, recorded, ends, lines


def _recorded_question(stderr_stop: str) -> str:
    match = re.search(r"reason=unowned confirm: (.+)$", stderr_stop)
    assert match is not None, stderr_stop
    return match.group(1)


class QuestLeaveConfirmRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.boundaries, cls.recorded, cls.ends, cls.lines = _load()
        with gzip.open(CASTLE_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.knowledge = json.loads(stream.readline())
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.question = _recorded_question(cls.boundaries["stderr_stop"])

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        self.policy._crossarea_fundraising_enforced = True  # live argv
        self.policy.consume_skill_knowledge(self.knowledge)  # declared wall
        self._fed = -1

    def _board(self, sequence):
        end = self.ends[sequence]
        rows = self.lines[self._fed + 1: end + 1]
        self._fed = end
        _decoded, snapshots = _consume_response_sequence(
            rows, self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        return snapshots[-1]

    def _replay_through(self, last):
        rows, boards = {}, {}
        for sequence in range(FIRST, last + 1):
            board = self._board(sequence)
            key = self.policy.choose_key(board)
            rows[sequence] = (str(key), self.policy.last_reason)
            boards[sequence] = board
            self.policy.confirm_key_posted(key)
        return rows, boards

    def _live(self, sequence):
        return (self.recorded[sequence]["key"], self.recorded[sequence]["reason"])

    def test_recorded_rows_are_the_incident(self):
        self.assertEqual(self._live(ASCEND), ("<", "breeder-breakthrough:ascend"))
        self.assertEqual(tuple(self.recorded[ASCEND]["position"]), UPSTAIRS)
        self.assertEqual(
            {self._live(n)[1] for n in range(DIVERGENCE, ASCEND)},
            {"breeder-breakthrough:seek-upstairs", "melee"},
        )
        self.assertFalse(any(
            reason.startswith("breeder-breakthrough:")
            for _key, reason in map(self._live, range(FIRST, DIVERGENCE))
        ))
        self.assertTrue(self.boundaries["stderr_stop"].startswith(
            "<stuck-prompt> owner=breeder-breakthrough:ascend phase=continuation"
        ))
        self.assertEqual(self.question, "本当にこの階を去りますか？[y/n]")

    def test_replay_reproduces_live_and_arms_the_latch_on_the_locked_floor(self):
        rows, boards = self._replay_through(DIVERGENCE - 1)
        self.assertEqual(
            {n: rows[n] for n in REPRODUCED}, {n: self._live(n) for n in REPRODUCED}
        )
        board = boards[DIVERGENCE - 1]
        self.assertEqual(board.floor_key, QUEST_FLOOR)
        quest = board.quests[41]
        self.assertEqual((quest.status, quest.type), (1, 7))  # TAKEN, RANDOM
        self.assertEqual(self.policy._breeder_breakthrough_floor, QUEST_FLOOR)
        self.assertEqual(self.policy._active_kill_quest_id(board), 41)
        self.assertLess(self.policy._stuck_escape_streak, STUCK_ESCAPE_LIMIT)
        self.assertTrue(self.policy._quest_floor_exit_locked(board))

    def test_locked_quest_floor_is_not_left_by_the_breakthrough(self):
        rows, boards = self._replay_through(ASCEND)
        # First divergence (R4): live walked toward the stairs.
        self.assertEqual(
            self._live(DIVERGENCE), ("7", "breeder-breakthrough:seek-upstairs")
        )
        self.assertFalse(rows[DIVERGENCE][1].startswith("breeder-breakthrough:"))
        # Property over every recorded board of the window (not an effect
        # claim): while the lock holds no stair key is chosen, including on
        # the live ascend board where the player stands on the up staircase.
        for sequence in range(DIVERGENCE, ASCEND + 1):
            self.assertTrue(self.policy._quest_floor_exit_locked(boards[sequence]))
            self.assertNotEqual(rows[sequence][0], UP_STAIRS_KEY, sequence)
        board = boards[ASCEND]
        self.assertEqual(board.player.position.y, UPSTAIRS[0])
        self.assertEqual(board.player.position.x, UPSTAIRS[1])
        self.assertTrue(self.policy._is_upstairs_target(board.grid_at(board.player.position)))
        self.assertIsNone(self.policy._breeder_breakthrough_escape_key(board))
        self.assertFalse(
            self.policy.quest_leave_confirmation_owned(board, UP_STAIRS_KEY)
        )

    def test_given_up_quest_floor_owns_the_leave_confirm(self):
        _rows, boards = self._replay_through(ASCEND)
        board = boards[ASCEND]
        self.assertEqual(_quest_leave_continuations(board, UP_STAIRS_KEY, False), [])
        # DECLARED WALL: the progress-based give-up has decided (genuine
        # stall streak at the limit) -- the lock releases.
        self.policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        self.assertFalse(self.policy._quest_floor_exit_locked(board))
        self.assertEqual(
            self.policy._breeder_breakthrough_escape_key(board), UP_STAIRS_KEY
        )
        self.assertTrue(
            self.policy.quest_leave_confirmation_owned(board, UP_STAIRS_KEY)
        )
        continuations = _quest_leave_continuations(board, UP_STAIRS_KEY, True)
        self.assertEqual(len(continuations), 1)
        self.assertEqual(continuations[0].kinds, frozenset({ScreenKind.CONFIRM}))
        self.assertEqual(continuations[0].keys, "y")
        self.assertIn(self.question, continuations[0].feature)
        self.assertTrue(continuations[0].exact_feature)


class QuestLeaveConfirmTransportTest(executor_pins.ProductionHarness):
    """The stair operation answers the recorded question only after release."""

    @classmethod
    def setUpClass(cls):
        cls.boundaries, _recorded, cls.ends, cls.lines = _load()
        cls.raw = json.loads(cls.lines[cls.ends[ASCEND]])
        cls.question = _recorded_question(cls.boundaries["stderr_stop"])
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _post(self, *, released):
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), self.monrace)
            _decoded, snapshots = _consume_response_sequence(
                [self.lines[self.ends[ASCEND]]], policy, lambda _key: True,
                self.monrace,
                knowledge_ledger_path=Path(directory) / "knowledge.jsonl",
            )
            snapshot = snapshots[-1]
            policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT if released else 0
            policy.last_reason = "breeder-breakthrough:ascend"
            game = executor_pins.FaithfulHookGame()
            game.state = copy.deepcopy(self.raw)
            game.screen = executor_pins.command_screen(self.raw["turn"])
            game.screens = [
                executor_pins.prompt_screen(LEAVE_WARNING),
                executor_pins.prompt_screen(self.question),
                executor_pins.command_screen(self.raw["turn"] + 1),
            ]
            game.states = [copy.deepcopy(self.raw) for _ in game.screens]
            game.states[-1]["turn"] = self.raw["turn"] + 1
            game.states[-1]["floor"]["level"] = 23
            game.states[-1]["floor"]["quest_id"] = 0
            _game, _client, executor = self.make(game)
            self.assertEqual(
                executor.observe_boundary(deadline=9999999999).outcome, "ready"
            )
            port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                      request_budget=2)
            sent, _line, chain, _result = _send_decision_key_with_prompt_chain(
                port, "recorded-board", UP_STAIRS_KEY, None, set(),
                policy=policy, shadow_client=None, file=io.StringIO(),
                deadline=time.monotonic() + 30, poll_interval=0.0,
                prompt_japanese=True,
                decision={"sequence": ASCEND, "reason": policy.last_reason},
                snapshot=snapshot, posting_contract=PostingContract(),
                in_store=False,
            )
            self.assertIsNone(chain)
            return game, port, sent

    def test_released_lock_answers_the_recorded_question(self):
        game, port, sent = self._post(released=True)
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, ["<", " ", "y"])

    def test_held_lock_leaves_the_question_unowned(self):
        game, port, sent = self._post(released=False)
        self.assertFalse(sent)
        self.assertEqual(port.last_result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["<", " "])
        self.assertNotIn("y", game.accepted)


if __name__ == "__main__":
    unittest.main()
