"""Turn-free refresh of the Magic-Eater lists for the spectator (owner 2026-10-30).

「取り込んだ魔道具の一覧を、ボットが定期的に（ゲームのターンを使わずに）開いて、
観戦の表示を新しくして。」

Every boundary is decided by the public ``choose_key``; each key is sent
through the production executor (``_ExecutorInputPort`` over
``OperationExecutor``).  DECLARED CONSTRUCTED: the class-16 town board, the
absorbed devices, their charges and failure rates.  The game is a model of
cmd-magiceat.cpp ``do_cmd_magic_eater(only_browse=true)`` for the keys it
reads: the ``[A] 杖, [B] 魔法棒, [C] ロッド:`` question, the browse prompt with
its list printed as ``select_magic_eater`` formats it (header on row 1, two
40-cell columns), 「その種類の魔法は覚えていない！」 for a kind with nothing
absorbed, and ``energy.reset_player_turn()`` on every cancel.  Game time
advances only by the energy a command sets, which browsing never does.
"""

import tests  # noqa: F401 -- isolate live runtime files
from dataclasses import replace
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from policy_fixtures import grid, hostile, player
import test_input_executor as input_tests
import test_policy_quest as quest_tests
from test_magic_eater_o3 import prompt
from test_spectator_me_powers import device, raw_board, rod, two_columns
from hengbot.cli import (
    SendResult, _ExecutorInputPort, _request_due_dump, _request_due_me_powers_refresh,
)
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot.me_powers_refresh import request_refresh
from hengbot.model import Position, Snapshot, parse_snapshot
from hengbot.spectator import SpectatorWriter
from test_spectator import _Clock


REASON = "periodic:magic-eater-powers"
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
BROWSE_PROMPT = "('*'で一覧, ESCで中断) どの魔力を見ますか？"
NOT_ABSORBED = "その種類の魔法は覚えていない！"
GROUP_SIZE = 32  # item_group_size: entries < size/2 sit in the left column
# DECLARED CONSTRUCTED absorbed devices: kind -> {sval: (name, current, count, fail)}.
ABSORBED = {
    "staff": {5: ("鑑定", 3, 1, 12), 10: ("財宝感知", 0, 1, 9)},
    "wand": {15: ("マジック・ミサイル", 9, 17, 35)},
    "rod": {},
}


class BrowseGame(input_tests.FaithfulHookGame):
    """The browse command's key reads (cmd-magiceat.cpp), one key at a time."""

    capacity = 256

    def __init__(self, absorbed):
        super().__init__()
        self.absorbed, self.mode, self.kind, self.shown = absorbed, "command", None, False
        self.energy_use, self.message, self.commands = 0, "", []
        # A recorded protocol board as the class-16 player at the screen
        # cursor, so the CLI's parse_snapshot(executor.ready_board) applies.
        raw = raw_board(16, turn=5000)
        raw["player"] = dict(raw["player"], y=10, x=10)
        self.state = raw
        self.screen = self.render()

    def key(self, char):
        if self.mode == "command":
            self.commands.append(char)
            if char != "b":
                raise AssertionError(f"not a browse command: {char!r}")
            self.message, self.mode, self.energy_use = "", "kind", 0
        elif self.mode == "kind":
            if char == "\x1b":
                self.mode = "command"
                return
            self.kind = {"A": "staff", "B": "wand", "C": "rod"}[char.upper()]
            if not self.absorbed[self.kind]:
                # No count > 0 in the group: message, nullopt, energy reset.
                self.message, self.mode = NOT_ABSORBED, "command"
                return
            self.mode, self.shown = "power", False  # always_show_list off
        elif self.mode == "power":
            if char in " *?":
                self.shown = not self.shown
            elif char == "\x1b":
                self.mode = "command"  # nullopt: energy.reset_player_turn()
            else:
                raise AssertionError(f"browse answer {char!r} not expected")

    def render(self):
        if self.mode == "command":
            screen = input_tests.command_screen(self.state["turn"])
            screen["lines"][0] = self.message
            return screen
        if self.mode == "kind":
            return prompt(TYPE_PROMPT, "command_char")
        screen = prompt(BROWSE_PROMPT, "spell")
        if self.shown:
            lines = screen["lines"]
            for y in range(1, 20):
                lines[y] = ""
            header = "使用回数" if self.kind != "rod" else "  状態  "
            lines[1] = " " * 27 + f"{header} 失率" + " " * 27 + f"{header} 失率"
            for sval, (name, current, count, fail) in sorted(self.absorbed[self.kind].items()):
                label = f"{chr(ord('a') + sval)})"
                text = (rod(label, name, current, count, fail) if self.kind == "rod"
                        else device(label, name, current, count, fail))
                left = sval < GROUP_SIZE // 2
                y = 2 + (sval if left else sval - GROUP_SIZE // 2)
                lines[y] = two_columns(text) if left else two_columns(lines[y] or " ", text)
        return screen

    def _consume(self, *, pump_frontend=True):
        if pump_frontend and self.frontend_fifo:
            self.term_fifo.extend(self.frontend_fifo)
            self.frontend_fifo.clear()
        if not self.term_fifo:
            return
        raw = "".join(self.term_fifo)
        self.term_fifo.clear()
        for char in raw:
            self.key(char)
        if self.mode == "command":
            # process_player: only the energy a command set passes game time.
            self.state = dict(self.state, turn=self.state["turn"] + self.energy_use // 100)
            self.jsonl.append(dict(self.state))
        self.screen = self.render()


class MePowersRefreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()

    def policy(self):
        policy = quest_tests.ApprovedQuestStrategyExecutionTest()._policy()
        policy._fixed_quest_speed_attempted = True
        return policy

    def board(self, *, class_id=16, monsters=(), turn=5000):
        grids = {Position(y, x): grid(y, x) for y in range(5, 16) for x in range(5, 16)}
        return Snapshot(
            replace(player(10, 10, hp=100, max_hp=100, level=8, class_id=class_id,
                           food_type=4 if class_id == 16 else 0), race_id=25),
            grids, list(monsters), floor_key=(0, 0, 0), town_id=0, town_flag=True,
            turn=turn, visited_town_ids=(0,), protocol_version=3)

    def port(self, game):
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        return _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)

    def cli_decision(self, policy, board, port, spectator, clock, next_refresh_at):
        """One follow-loop decision as _run_follow makes it on an executor.

        The decision snapshot is parse_snapshot(executor.ready_board), the
        board the executor composed after the previous operation, and
        post_decision hands that snapshot to SpectatorWriter.observe before
        the key is posted.  The decision itself is taken on the declared
        town board (the recorded board is not a safe town filler board).
        """
        ready = port.executor.ready_board
        snapshot = parse_snapshot(ready, {})
        next_refresh_at = _request_due_me_powers_refresh(
            policy, spectator, clock.now, next_refresh_at, 180)
        key = policy.choose_key(board)
        spectator.observe(snapshot, key, policy.last_reason, 1, None,
                          state_line=json.dumps(ready, ensure_ascii=False, sort_keys=True),
                          append_frame=True, defer_frame=True)
        spectator.last_write = None
        if key and policy.last_reason == REASON:
            status = port(key, decision={"reason": policy.last_reason, "sequence": 1})
            self.assertEqual(status, SendResult.SENT, port.last_result.reason)
            policy.confirm_key_posted(key)
        return key, next_refresh_at

    def test_refresh_reaches_spectate_json_without_a_game_turn(self):
        policy, board = self.policy(), self.board()
        policy.prime(board)
        game = BrowseGame(ABSORBED)
        port = self.port(game)
        clock = _Clock()
        with TemporaryDirectory() as tmp:
            spectator = SpectatorWriter(Path(tmp) / "spectate.json", clock=clock)
            keys, next_at = [], 0.0
            for _ in range(5):
                key, next_at = self.cli_decision(policy, board, port, spectator, clock, next_at)
                keys.append((key, policy.last_reason))
                clock.now += 1
            powers = json.loads(spectator.path.read_text(encoding="utf-8"))["magic_eater_powers"]
        # Decision 1 makes the first class-16 observation; 2-4 are the cycle;
        # the cycle is not repeated.
        self.assertEqual([entry for entry in keys if entry[1] == REASON],
                         [("bA", REASON), ("bB", REASON), ("bC", REASON)])
        self.assertNotEqual(keys[-1][1], REASON)
        # Staff and wand: b, kind, '*' to show the list, ESC.  Rod: the game's
        # own "nothing absorbed" answer ends the command after the letter.
        self.assertEqual(game.accepted, ["b", "A", "*", "\x1b", "b", "B", "*", "\x1b",
                                         "b", "C"])
        self.assertEqual(game.state["turn"], 5000)
        # spectate.json as written from the CLI's barrier snapshots: every
        # kind observed at the unchanged game turn (rod empty, not 未確認).
        self.assertEqual(powers, {
            "staff": {"turn": 5000, "rows": [
                {"name": "鑑定", "fail": 12, "success": 88, "current": 3, "max": 1},
                {"name": "財宝感知", "fail": 9, "success": 91, "current": 0, "max": 1}]},
            "wand": {"turn": 5000, "rows": [
                {"name": "マジック・ミサイル", "fail": 35, "success": 65,
                 "current": 9, "max": 17}]},
            "rod": {"turn": 5000, "rows": []},
        })

    def test_one_cycle_per_interval_across_bot_restarts(self):
        """Live n1-c life-044: the soak runner restarted a stopped bot every
        ~12 s and each process start refreshed again (36 in ~6 minutes)."""
        clock = _Clock()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "spectate.json"
            first = SpectatorWriter(path, clock=clock)
            for kind in ("staff", "wand", "rod"):
                raw = dict(raw_board(16, turn=5000),
                           _magic_eater_power_list={"kind": kind, "rows": []})
                first.observe(parse_snapshot(raw, {}), "5", "pin", 1, None,
                              state_line=json.dumps(raw))
                first.last_write = None
            for seconds, due in ((12, False), (179, False), (181, True)):
                with self.subTest(restart_after=seconds):
                    clock.now = 1_000_000.0 + seconds
                    # A new bot process: new policy, writer and timers.
                    policy = SimpleNamespace(_me_power_refresh_pending=(),
                                             request_character_dump=lambda: None,
                                             request_game_save=lambda: None)
                    writer = SpectatorWriter(path, clock=clock)
                    later = raw_board(16, turn=5100)
                    writer.observe(parse_snapshot(later, {}), "5", "pin", 1, None,
                                   state_line=json.dumps(later))
                    _request_due_dump(policy, clock.now, 0.0)
                    next_at = _request_due_me_powers_refresh(
                        policy, writer, clock.now, clock.now, 180)
                    self.assertEqual(policy._me_power_refresh_pending,
                                     ("staff", "wand", "rod") if due else ())
                    # While latched, or within the interval, no second cycle.
                    self.assertEqual(_request_due_me_powers_refresh(
                        policy, writer, clock.now + 1, next_at, 180), next_at)
            # A different life (game turn backwards) is not resumed.
            writer = SpectatorWriter(path, clock=clock)
            reborn = raw_board(16, turn=10)
            writer.observe(parse_snapshot(reborn, {}), "5", "pin", 1, None,
                           state_line=json.dumps(reborn))
            self.assertTrue(writer.magic_eater_refresh_due(180))

    def test_refresh_waits_for_a_safe_board_and_is_class_16_only(self):
        policy = self.policy()
        danger = self.board(monsters=[hostile(1, 10, 14, distance=4)])
        policy.prime(danger)
        request_refresh(policy)
        policy.choose_key(danger)
        self.assertNotEqual(policy.last_reason, "periodic:magic-eater-powers")
        self.assertEqual(policy._me_power_refresh_pending, ("staff", "wand", "rod"))
        warrior = self.policy()
        board = self.board(class_id=1)
        warrior.prime(board)
        request_refresh(warrior)
        warrior.choose_key(board)
        self.assertNotEqual(warrior.last_reason, "periodic:magic-eater-powers")
        self.assertEqual(warrior._me_power_refresh_pending, ())


if __name__ == "__main__":
    unittest.main()
