"""Issue #47: the light-low return owns its stair's leave confirmation.

Recorded substrate: light-rootfix fixture state rows 103/104 (indices 4/5).
DECLARED CONSTRUCTED: the exact Japanese leave prompt and next-floor screen,
the skill-exp cache, and controls with oil or a runtime RANDOM quest.
No policy methods are patched: choose_key feeds the production follow executor.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import gzip
import hashlib
import io
import json
import time
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _consume_response_sequence,
    _send_decision_key_with_prompt_chain,
)
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import SV_FLASK_OIL, TVAL_FLASK
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import OIL_TARGET
from hengbot.quest_knowledge import QUEST_TYPE_RANDOM
from test_esp_threat_rest_recorded import EDIT, _policy
from tests import test_input_executor as executor_pins

FIXTURE = Path(__file__).parent / "fixtures" / "light-rootfix-q2-20261025.jsonl.gz"
SHA256 = "decf4c8e3a4cc74e6d421ba8aecf5bf89cbabc21182d3bdb22d8d3464a05f27d"
QUESTION = "本当にこの階を去りますか？[y/n]"


class LightLeaveConfirmRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.lines = gzip.decompress(data).decode("utf-8").splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)
        self.policy._crossarea_fundraising_enforced = True

    def _board(self, index):
        self.raw = json.loads(self.lines[index])
        _decoded, snapshots = _consume_response_sequence(
            [self.lines[index]], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        board = snapshots[-1]
        # DECLARED CONSTRUCTED: same skill-exp cache as the root-fix pins.
        self.policy._skill_exp_cache = (
            0, 0, board.player.level, self.policy._town_visit_epoch
        )
        return board

    def _post(self, board, key, *, confirm=True):
        # DECLARED CONSTRUCTED: inner confirm emits no new JSONL, then the
        # command boundary reports that the staircase left the quest floor.
        raw = copy.deepcopy(self.raw)
        raw["floor"].update(zip(("dungeon_id", "level", "quest_id"), board.floor_key))
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(board.turn)
        game.screens = [
            executor_pins.prompt_screen(QUESTION),
            executor_pins.command_screen(board.turn + 1),
        ]
        game.screens[0]["input_context"] = {"kind": "confirm", "prompt": QUESTION}
        game.states = [copy.deepcopy(raw) for _ in game.screens]
        game.states[0]["input_context"] = {"kind": "confirm", "prompt": QUESTION}
        game.states[-1]["turn"] = board.turn + 1
        game.states[-1]["floor"]["level"] = 0
        game.states[-1]["floor"]["quest_id"] = 0
        self.assertEqual(classify_screen(game.screens[0]).kind, ScreenKind.CONFIRM)
        if not confirm:
            # The recorded dark walk from row 103 reaches row 104's stairs.
            next_raw = json.loads(self.lines[5])
            game.screens = [executor_pins.command_screen(next_raw["turn"])]
            game.states = [next_raw]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line, chain, _result = _send_decision_key_with_prompt_chain(
            port, "recorded-board", key, None, set(),
            policy=self.policy, shadow_client=None, file=io.StringIO(),
            deadline=time.monotonic() + 30, poll_interval=0.0,
            prompt_japanese=True,
            decision={"sequence": 104, "reason": self.policy.last_reason},
            snapshot=board, posting_contract=PostingContract(), in_store=False,
        )
        self.assertIsNone(chain)
        if port.last_result.outcome == "stuck-prompt":
            self.assertEqual(executor.last_input_context.kind, "confirm")
            self.assertEqual(executor.last_input_context.prompt, QUESTION)
        return game, port.last_result, sent

    def _return_on_stairs(self):
        first = self._board(4)
        walk = self.policy.choose_key(first)
        self.assertEqual(str(walk), "4")
        self.assertEqual(self.policy.last_reason, "dark:backtrack")
        game, result, sent = self._post(first, walk, confirm=False)
        self.assertTrue(sent)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["4"])
        self.policy.confirm_key_posted(walk)
        board = self._board(5)
        key = self.policy.choose_key(board)
        self.assertEqual((str(key), self.policy.last_reason), ("<", "return:ascend"))
        return board, key

    def test_fixed_once_light_return_answers_confirm_in_same_post(self):
        board, key = self._return_on_stairs()
        self.assertEqual(self.policy._active_fixed_quest_id(board), 2)
        self.assertTrue(self.policy._fixed_quest_is_once(2))
        game, result, sent = self._post(board, key)
        self.assertTrue(sent)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["<", "y"])

    def test_runtime_kill_light_return_answers_confirm_in_same_post(self):
        board = self._board(5)
        # DECLARED CONSTRUCTED: same empty-lantern staircase, runtime RANDOM
        # quest instead of fixed Q2. Its ordinary kill lock still holds.
        quest = replace(board.quests[2], id=41, type=QUEST_TYPE_RANDOM, fixed=False)
        board = replace(board, floor_key=(1, 15, 41), quests={41: quest})
        self.assertIsNone(self.policy._active_fixed_quest_id(board))
        self.assertEqual(self.policy._active_kill_quest_id(board), 41)
        self.assertTrue(self.policy._quest_floor_exit_locked(board))
        key = self.policy.choose_key(board)
        self.assertEqual((str(key), self.policy.last_reason), ("<", "return:ascend"))
        game, result, sent = self._post(board, key)
        self.assertTrue(sent)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["<", "y"])

    def _assert_held(self, board):
        self.assertTrue(self.policy._return_exit_locked(board))
        self.assertNotEqual(str(self.policy.choose_key(board)), "<")
        # DECLARED CONSTRUCTED: inject an unauthorized stair at the sender
        # boundary to prove the executor visibly stops without answering y.
        self.policy.last_reason = "return:ascend"
        game, result, sent = self._post(board, "<")
        self.assertFalse(sent)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["<"])

    def test_fuel_104_keeps_lock_and_confirm_unowned(self):
        self._assert_held(self._board(0))

    def test_oil_keeps_lock_and_confirm_unowned(self):
        board = self._board(5)
        lamp = next(item for item in board.equipment if item.is_light)
        slot = next(c for c in "abcdefghijklmnopqrstuvw"
                    if all(item.slot != c for item in board.inventory))
        # DECLARED CONSTRUCTED: refill oil carried in a free inventory slot.
        oil = replace(lamp, slot=slot, tval=TVAL_FLASK, sval=SV_FLASK_OIL,
                      count=OIL_TARGET, fuel=7500, name="油つぼ")
        board = replace(board, inventory=type(board.inventory)((*board.inventory, oil)))
        self._assert_held(board)

    def test_light_release_does_not_own_non_stair_or_town_confirm(self):
        board, _key = self._return_on_stairs()
        self.assertFalse(self.policy.quest_leave_confirmation_owned(board, "6"))
        self.assertFalse(self.policy.quest_leave_confirmation_owned(
            replace(board, town_flag=True), "<"
        ))


if __name__ == "__main__":
    import unittest
    unittest.main()
