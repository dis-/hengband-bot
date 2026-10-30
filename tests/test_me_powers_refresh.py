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

from policy_fixtures import grid, hostile, player
import test_input_executor as input_tests
import test_policy_quest as quest_tests
from test_magic_eater_o3 import prompt
from test_spectator_me_powers import device, raw_board, rod, two_columns
from hengbot.cli import SendResult, _ExecutorInputPort, _request_due_dump
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot.model import Position, Snapshot, parse_snapshot
from hengbot.spectator import SpectatorWriter


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
        self.state = {"turn": 5000, "player": {"y": 10, "x": 10, "class_id": 16},
                      "inventory": [], "equipment": [], "grid_map": {"runs": []}}
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

    def test_timer_refreshes_all_three_kinds_without_a_game_turn(self):
        policy, board = self.policy(), self.board()
        policy.prime(board)
        game = BrowseGame(ABSORBED)
        port = self.port(game)
        # The CLI's wall-clock dump timer latches the refresh with save/dump.
        _request_due_dump(policy, 1000.0, 0.0)
        policy._periodic_save_requested = policy._periodic_dump_requested = False
        lists, keys = {}, []
        for sequence in range(1, 4):
            key = policy.choose_key(board)
            keys.append((key, policy.last_reason))
            status = port(key, decision={"reason": policy.last_reason, "sequence": sequence})
            self.assertEqual(status, SendResult.SENT, port.last_result.reason)
            policy.confirm_key_posted(key)
            listed = port.last_result.board["_magic_eater_power_list"]
            lists[listed["kind"]] = listed
        reason = "periodic:magic-eater-powers"
        self.assertEqual(keys, [("bA", reason), ("bB", reason), ("bC", reason)])
        # Staff and wand: b, kind, '*' to show the list, ESC.  Rod: the game's
        # own "nothing absorbed" answer ends the command after the letter.
        self.assertEqual(game.accepted, ["b", "A", "*", "\x1b", "b", "B", "*", "\x1b",
                                         "b", "C"])
        self.assertEqual(game.state["turn"], 5000)
        self.assertEqual(lists, {
            "staff": {"kind": "staff", "rows": [
                {"name": "鑑定", "fail": 12, "success": 88, "current": 3, "max": 1},
                {"name": "財宝感知", "fail": 9, "success": 91, "current": 0, "max": 1}]},
            "wand": {"kind": "wand", "rows": [
                {"name": "マジック・ミサイル", "fail": 35, "success": 65,
                 "current": 9, "max": 17}]},
            "rod": {"kind": "rod", "rows": []},
        })
        # Nothing pending: the next board keeps its own decision.
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, reason)
        # spectate.json: every kind observed (rod empty, not 未確認).
        with TemporaryDirectory() as tmp:
            writer = SpectatorWriter(Path(tmp) / "spectate.json")
            raw = raw_board(16)
            for listed in lists.values():
                writer.observe(parse_snapshot(dict(raw, _magic_eater_power_list=listed), {}),
                               "5", "pin", 1, None, state_line=json.dumps(raw))
                writer.last_write = None
            powers = json.loads(writer.path.read_text(encoding="utf-8"))["magic_eater_powers"]
        self.assertEqual({kind: value["rows"] for kind, value in powers.items()},
                         {kind: value["rows"] for kind, value in lists.items()})

    def test_refresh_waits_for_a_safe_board_and_is_class_16_only(self):
        policy = self.policy()
        danger = self.board(monsters=[hostile(1, 10, 14, distance=4)])
        policy.prime(danger)
        _request_due_dump(policy, 1000.0, 0.0)
        policy._periodic_save_requested = policy._periodic_dump_requested = False
        policy.choose_key(danger)
        self.assertNotEqual(policy.last_reason, "periodic:magic-eater-powers")
        self.assertEqual(policy._me_power_refresh_pending, ("staff", "wand", "rod"))
        warrior = self.policy()
        board = self.board(class_id=1)
        warrior.prime(board)
        _request_due_dump(warrior, 1000.0, 0.0)
        warrior._periodic_save_requested = warrior._periodic_dump_requested = False
        warrior.choose_key(board)
        self.assertNotEqual(warrior.last_reason, "periodic:magic-eater-powers")
        self.assertEqual(warrior._me_power_refresh_pending, ())


if __name__ == "__main__":
    unittest.main()
