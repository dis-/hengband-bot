"""n1-a life-535: the emergency's down-stair escape and the return's ascent do not alternate.

n1-a life-535 (Warrior Lv50, Castle) was stopped by the loop detector at 2026-11-24 09:39:24
(turn 10163939, floor (12, 42, 0), cells (18,37) and (6,125)): 40F's arrival stair (a down stair
at (6,125)) stood three cells from キリス・ウンゴルの番人 (never moves, summons).  Asleep, it had the
immobile summoner owner read Recall (``summoner:recall``); awake on the next board, the emergency
ladder (``summoner_open``; the Teleportation scroll withheld in the Recall wait, deep_teleport)
went down the stair underfoot as its last escape (``emergency:stairs-down``).  On 42F, Recall
running and nothing in sight, the return owner took the up stair underfoot (``return:ascend``):
the connected stairs (floor-leaver.cpp, a stair's ``special`` keeps the saved floor it leads to)
loaded the same 40F beside the same watcher, and the emergency went down again: 19 round trips
at HP 1278/1278 until the stop.  The down-stair escape is an escape by stairs (fled_floor_stairs,
owner 2026-10-31 「逃げた階に戻らないための決定」): the up stair it lands on leads back, and the return
waits for its Recall instead of taking it.

Recorded: the 09:36:00 town-arrival checkpoint of n1-a life-535
(tests/fixtures/n1a-535-stairs-pingpong-1124, its 139 town rows replayed as recorded) and the
capture's boards from 42F's up stair to the first return to it (``boards.jsonl.xz``, the
state.jsonl lines of turns 10163895-10163903 of capture 20261124-093926-loop-detected; of two
lines of one turn, the later, the board after the floor-transition ESC).

DECLARED CONSTRUCTED:

* the executor's game for the 42F wait: the recorded board the key is posted on, and the same
  board ten game turns on (the recorded next line is the 40F the recorded '<' loaded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-535-stairs-pingpong-1124"
STAIR_40F = Position(6, 125)
STAIR_42F = Position(18, 37)
WATCHER_RACE = 397


class StairsPingPongTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
            cls.town = replay_window("n1a-535-stairs-pingpong", cls.policy, iter(steps))
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode(
            "utf-8").splitlines()
        by_turn = {}
        for line in lines:
            raw = json.loads(line)
            if raw.get("type") == "player_turn":
                by_turn[raw["turn"]] = raw  # the later line of a turn
        cls.decided = []
        for raw in by_turn.values():
            board = parse_snapshot(raw, cls.policy._monrace_knowledge)
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                key = cls.policy.choose_key(board)
            cls.decided.append((raw, board, key, cls.policy.last_reason))

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def _post(self, key, raw, next_raw, reason):
        """The production executor posts ``key`` on the recorded ``raw`` line, the game showing
        ``next_raw`` after the command."""
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.command_screen(next_raw["turn"])]
        game.states = [next_raw]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": self.policy._decision_sequence, "reason": reason},
            snapshot=parse_snapshot(raw, self.policy._monrace_knowledge),
            posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        return game.accepted

    def test_the_town_visit_replays_as_recorded(self):
        self.assertIsNone(self.town.first_divergence)
        self.assertEqual(self.town.matched_rows, 139)

    def test_the_40f_watcher_board_escapes_down_the_stair_underfoot(self):
        raw, board, key, reason = next(
            row for row in self.decided if row[1].dungeon_level == 40 and row[1].player.recalling)
        self.assertEqual((board.floor_key, board.player.position), ((12, 40, 0), STAIR_40F))
        watcher = next(m for m in board.visible_monsters if m.race_id == WATCHER_RACE)
        self.assertFalse(watcher.asleep)
        # Recorded 09:39:17: ('>', 'emergency:stairs-down'), Recall already read.
        self.assertEqual((key, reason), (">", "emergency:stairs-down"))

    def test_the_return_does_not_take_the_stair_back_to_the_watcher(self):
        from hengbot import fled_floor_stairs

        raw, board, key, reason = self.decided[-1]
        self.assertEqual((board.floor_key, board.player.position), ((12, 42, 0), STAIR_42F))
        self.assertTrue(board.grid_at(STAIR_42F).has_up_stairs)
        self.assertTrue(board.player.recalling)
        # Recorded 09:39:18: ('<', 'return:ascend') loaded the same 40F again.
        self.assertTrue(fled_floor_stairs.leads_back(self.policy, board, STAIR_42F))
        self.assertNotEqual(key, "<")
        self.assertEqual(reason, "return:wait-recall")
        self.assertTrue(self._post(key, raw, dict(raw, turn=raw["turn"] + 10), reason))


if __name__ == "__main__":
    unittest.main()
