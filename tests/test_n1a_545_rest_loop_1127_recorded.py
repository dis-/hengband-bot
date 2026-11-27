"""A caster whose maximum mana is drained to 0 no longer rests on a board the game ends the rest at
once (n1-a life-545, MAINTAINABILITY.md 2 and 3).

Recorded (tests/extract_n1a_545_rest_loop_1127_fixture.py, ``n1a-545-rest-loop-1127``): the
town-arrival checkpoint of 2026-11-27 14:35:37 (Amberite Sorcery Rogue CL34, 111 MP), its 33
journal rows (the visit recalled to Mountain 42F), then every board of the live snapshot generation
after them.  On 42F the Big Beholder's gazes drained INT 18/64 -> 7 (adj_mag_mana 0) and a level
(CL34 -> 33): the maximum mana fell 111 -> 0 (turns 4958466 -> 4960481).  The HP rests that
followed (568/766 at turn 4960613) were real; from turn 4960836 (766/766 HP, 0/0 MP, nothing in
sight) the recorded bot rested because ``0 < escape reserve 12`` (realm_spells.mana_rest_due), the
game ended each rest within one player turn (nothing to recover: is_fully_healthy), and 155 rests in
220 decisions ended in the loop detector's halt at turn 4963142.

Every board before ``FIRST_FULL_REST`` is decided through the public ``choose_key`` and compared with
the decision log (full state), except ``RECAST``: the live bot recast Detect Doors and Traps after
the failure message 「呪文をうまく唱えられなかった！」 (the executor's re-choice is not journalled); the
replay's own key is posted there, and every later board matches.

DECLARED CONSTRUCTED: ``PRE_FIX_MANA`` restores the old mana rest question (the reserve against the
current mana alone); the backstop test forces the rest question true on the recorded board; the
exploration test answers the browse (the spell list read at CL33), which the recorded boards, made
under rests, never carry.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import ladder_rest, realm_spell_book, realm_spells
from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import REST_MACRO
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-rest-loop-1127"
FIRST_FULL_REST = 4960836  # recorded ('R&\r', 'rest') on 766/766 HP and 0/0 MP
FIRST_HP_REST = 4960613    # recorded ('R&\r', 'rest') on 568/766 HP: a real rest
RECAST = 4960076
EXPLORATION = ("explore", "breakout:seek-frontier")  # alone the replay decides ('1', 'explore')


def _pre_fix_mana(policy, snapshot):
    if not realm_spells.applies(policy, snapshot) or snapshot.in_town:
        return False
    return (snapshot.player.mp < realm_spells.escape_reserve(policy, snapshot)
            or realm_spells.recall_rest_due(policy, snapshot))


PRE_FIX_MANA = mock.patch.object(realm_spells, "mana_rest_due", _pre_fix_mana)
MANA_DUE = mock.patch.object(realm_spells, "mana_rest_due", lambda *args: True)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


def ring_boards():
    """(lines delivered for a board, its player_turn record) in the CLI's order."""
    lines = lzma.decompress((FIXTURE / "ring.jsonl.xz").read_bytes()).decode(
        "utf-8", "surrogateescape").splitlines(True)
    pending = []
    for line in lines:
        pending.append(line)
        raw = json.loads(line)
        if raw.get("type") == "player_turn":
            yield pending, raw
            pending = []


class RestLoop545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        policy, journal, steps = load(FIXTURE, scratch)
        for recorded, supply in steps:
            key, reason = decide(policy, supply())
            assert (key, reason) == (recorded["key"], recorded["reason"]), recorded["row"]
            post(policy, key)
        recorded = {turn: (key, reason) for turn, key, reason in
                    json.loads((FIXTURE / "recorded.json").read_text(encoding="utf-8"))}
        cls.mismatches, cls.decided, previous = [], {}, journal[-1]["reason"]
        cls.boards = {}
        for lines, raw in ring_boards():
            _consume_response_sequence(lines, policy, lambda _key: True, policy._monrace_knowledge,
                                       parse_snapshots=False,
                                       knowledge_ledger_path=scratch / "knowledge.jsonl")
            raw["_completed_operation_owner"] = previous
            board = parse_snapshot(raw, policy._monrace_knowledge)
            if board.turn >= FIRST_FULL_REST:
                cls.boards[board.turn] = board
                if board.turn == FIRST_FULL_REST:
                    cls.policy = policy
                continue
            key, reason = decide(policy, board)
            cls.decided[board.turn] = (key, reason)
            if (key, reason) != recorded.get(board.turn) and board.turn != RECAST:
                cls.mismatches.append((board.turn, key, reason, recorded.get(board.turn)))
            post(policy, key)
            previous = reason if key else previous
        cls.recorded = recorded
        cls.board = cls.boards[FIRST_FULL_REST]

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_replay_matches_the_log_up_to_the_loop(self):
        self.assertEqual(self.mismatches, [])
        self.assertEqual(self.decided[FIRST_HP_REST], (REST_MACRO, "rest"))

    def test_the_board_has_nothing_to_rest_for(self):
        player = self.board.player
        self.assertEqual((player.hp, player.max_hp, player.mp, player.max_mp), (766, 766, 0, 0))
        self.assertIn("int", player.drained_stats)
        self.assertTrue(player.level_drained or player.exp_drained)
        self.assertGreater(realm_spells.escape_reserve(self.policy, self.board), 0)
        self.assertFalse(realm_spells.mana_rest_due(self.policy, self.board))
        self.assertEqual(self.recorded[FIRST_FULL_REST], (REST_MACRO, "rest"))

    def test_no_rest_on_the_recorded_board(self):
        key, reason = decide(self.policy, self.board)
        self.assertNotEqual(key, REST_MACRO)
        # The level drain made the shown spell list stale (CL34 -> 33): the safe filler reads it.
        self.assertEqual(reason, "periodic:realm-spells")

    def test_with_the_list_read_the_recorded_rest_boards_explore(self):
        # DECLARED CONSTRUCTED: the browse's answer (the list at CL33) is not on the recorded boards.
        with mock.patch.object(realm_spell_book, "_stale_book", lambda *args: None):
            for turn in sorted(self.boards):
                # The other tests decide the same boards first (the breakout counts the repeats).
                key, reason = decide(self.policy, self.boards[turn])
                self.assertEqual(key, "1", turn)
                self.assertIn(reason, EXPLORATION, turn)
                self.assertEqual(self.recorded[turn], (REST_MACRO, "rest"), turn)

    def test_the_old_mana_question_rests(self):
        with PRE_FIX_MANA:
            key, reason = decide(self.policy, self.board)
        self.assertEqual((key, reason), (REST_MACRO, "rest"))

    def test_a_rest_the_game_ends_at_once_gives_the_board_back(self):
        policy, board = self.policy, self.board
        setattr(policy, ladder_rest.FUTILE_REST, None)
        keys = []
        with MANA_DUE:
            for _ in range(ladder_rest.FUTILE_REST_LIMIT + 1):
                policy._rest_count = 0
                keys.append(ladder_rest.key(policy, board, strategic_hostiles=[]))
        self.assertEqual(keys[:ladder_rest.FUTILE_REST_LIMIT],
                         [REST_MACRO] * ladder_rest.FUTILE_REST_LIMIT)
        self.assertNotEqual(keys[-1], REST_MACRO)
        # A changed signature (HP lost in a fight) asks the rest again.
        hurt = replace(board, player=replace(board.player, hp=600))
        with MANA_DUE:
            policy._rest_count = 0
            self.assertEqual(ladder_rest.key(policy, hurt, strategic_hostiles=[]), REST_MACRO)
        setattr(policy, ladder_rest.FUTILE_REST, None)


if __name__ == "__main__":
    unittest.main()
