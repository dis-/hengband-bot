"""n1-c life-216 (Castle 64F, 2026-11-17 00:41): ``o8`` at a chest a friendly monster stood on.

The magic-eater (Lv46) ran the chest pipeline on the chest at [9,118] from [10,118]: six
searches, the absorbed disarming power (``mCo8``), two ``D8`` (the trap was already gone), then
``o8``.  A friendly 大バシリスク (race 668) stood on the chest's square.  cmd-open-close.cpp
do_cmd_open turns a monster on the square into do_cmd_attack (「モンスターが立ちふさがっている！」),
and cmd-attack.cpp asks input_check 「本当に攻撃しますか？」 of a visible non-hostile monster.
Nothing in the composed ``o8`` answered that question: stuck-prompt owner=chest:open.

Fix: the pipeline waits ('5', chest:await-occupant) while a known monster stands on the chest
and abandons the chest after CHEST_OCCUPANT_WAIT_LIMIT waits; the composed ``D``/``o`` answers
the attack question with 'n' when it is observed (a monster stepping on between board and key).

The board is the capture's last state row, the screen its control-at-stop screen.  DECLARED
CONSTRUCTED: the chest phase counts restored from the decision tail (search 6, disarm 2), the
board after the friend steps off, and the command screen after the 'n'.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_identification import CHEST_OCCUPANT_WAIT_LIMIT
import tests.support.recorded as executor_harness
from tests.support import recorded
from tests.support.recorded import FaithfulHookGame, command_screen

ROOT = Path(__file__).parents[1]
RACES = load_monrace_knowledge(
    find_monrace_definitions(ROOT, None) or recorded.EDIT / "MonraceDefinitions.jsonc")

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-216-chest-occupant-1117.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

CHEST = Position(9, 118)


def board(*, turn_offset: int = 0, friend_on_chest: bool = True) -> dict:
    raw = copy.deepcopy(CASE["board"])
    raw["turn"] += turn_offset
    if not friend_on_chest:
        # DECLARED CONSTRUCTED: the friend walked off the chest and out of view (the
        # board's monster positions come from the grid map, so it leaves the list).
        raw["visible_monsters"] = [
            monster for monster in raw["visible_monsters"]
            if (monster["y"], monster["x"]) != (CHEST.y, CHEST.x)
        ]
    return raw


class ChestOccupantPolicyTest(unittest.TestCase):
    def policy(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = recorded._policy(Path(directory.name), RACES)
        return policy

    def decide(self, policy, raw):
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        if policy._chest_position is None:
            policy._observe(policy._with_grid_memory(snapshot))
            # DECLARED CONSTRUCTED: the phase counts of the decision tail, and the disarm
            # press's answer that the chest is not trapped (the trap was already gone; owner
            # 2026-11-26 「外せない罠は開けない」 opens on that answer only).
            policy._chest_position = CHEST
            policy._chest_phase_counts = {"search": 6, "disarm": 2, "trap_clear": 1}
        # The capture has no checkpoint: a fresh policy's ladder would rank its own
        # recall first, so the chest producer the live ladder reached (decisions 2547-2556,
        # rung _chest_processing_key#2) is asked with the production hostile filter.
        policy.last_reason = None
        key = policy._chest_processing_key(snapshot, policy._physical_hostiles(snapshot))
        return key, policy.last_reason

    def test_capture_is_the_friend_on_the_chest_at_the_open(self):
        raw = CASE["board"]
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (10, 118))
        self.assertIn([9, 118, 1, 7], raw["grid_map"]["found_items"])
        friends = [m for m in raw["visible_monsters"] if (m["y"], m["x"]) == (9, 118)]
        self.assertEqual([(m["race_id"], m["friendly"], m["pet"]) for m in friends], [(668, True, False)])
        self.assertEqual(CASE["decision_tail"][-1]["key"], "o8")
        self.assertEqual(CASE["decision_tail"][-1]["reason"], "chest:open")
        self.assertEqual(classify_screen(CASE["screen"], None).kind, ScreenKind.CONFIRM)

    def test_friend_on_chest_is_waited_out_not_opened(self):
        policy = self.policy()
        key, reason = self.decide(policy, board())
        self.assertEqual((key, reason), (WAIT_KEY, "chest:await-occupant"))
        self.assertEqual(policy._chest_position, CHEST)
        key, reason = self.decide(policy, board(turn_offset=10, friend_on_chest=False))
        self.assertEqual((key, reason), ("o8", "chest:open"))

    def test_friend_that_never_leaves_abandons_the_chest(self):
        policy = self.policy()
        for wait in range(CHEST_OCCUPANT_WAIT_LIMIT):
            key, reason = self.decide(policy, board(turn_offset=10 * wait))
            self.assertEqual((key, reason), (WAIT_KEY, "chest:await-occupant"))
        key, reason = self.decide(policy, board(turn_offset=10 * CHEST_OCCUPANT_WAIT_LIMIT))
        self.assertIsNone(policy._chest_position)
        self.assertIn(CHEST, policy._processed_chest_positions)
        self.assertFalse(str(key).startswith(("o", "D")), (key, reason))


class ChestOccupantPromptTest(executor_harness.ProductionHarness):
    def post(self, owner, key):
        raw = board()
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        following = copy.deepcopy(raw)
        # DECLARED CONSTRUCTED: the command screen after the refused attack.
        following["turn"] += 10
        game.screens = [copy.deepcopy(CASE["screen"]), command_screen(following["turn"])]
        prompt_state = copy.deepcopy(raw)
        prompt_state["input_context"] = copy.deepcopy(CASE["screen"]["input_context"])
        game.states = [prompt_state, following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = recorded._policy(Path(directory.name), RACES)
        policy.last_reason = owner
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "n1c-216-chest-occupant", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": owner},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        # easy_open infers the sole adjacent chest: the recorded stop shows no direction
        # question, so the attack question comes right after the command key.
        self.assertEqual(game.accepted, [key[0], "n"])
        self.assertEqual(executor.ready_screen.kind, ScreenKind.COMMAND)
        self.assertFalse(game.screens, "every scheduled question was answered")

    def test_recorded_attack_question_is_refused_for_open_and_disarm(self):
        for owner, key in (("chest:open", "o8"), ("chest:disarm", "D8")):
            with self.subTest(owner=owner):
                self.post(owner, key)


if __name__ == "__main__":
    unittest.main()
