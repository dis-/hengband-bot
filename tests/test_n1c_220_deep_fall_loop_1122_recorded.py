"""n1-c life-220: the deep fall guard's leave of 49F does not alternate with the descent into it.

n1-c life-220 (Magic-Eater Lv32, Angband) was stopped by the loop detector at 2026-11-22
10:24:25 (turn 1827000, floor (1, 49, 0), cells (24,7) and (29,93)): on 48F ``descend`` took the
down stair at (29,93) (deep_fall_guard.descent_refused let it: the absorbed Detect Traps is held,
``mAm``), the 49F arrival stair at (24,7) stood in view of five sleeping ogres, so the absorbed
Detect Traps was not cast (me_powers ``_hostiles_allow``) and ``deep-fall-guard:ascend`` went up
the stair underfoot.  The connected stairs (floor-changer.cpp set_stairs, floor-leaver.cpp: a
stair's ``special`` keeps the saved floor it leads to) landed it on the same down stair of the
same saved 48F, ``descend`` loaded the same 49F: 20 round trips until the stop.  The leave is an
escape by stairs (fled_floor_stairs, owner 2026-10-31 「逃げた階に戻らないための決定」): the stair it
lands on is not taken again.

Recorded: the 10:23:55 town-arrival checkpoint of n1-c life-220
(tests/fixtures/n1c-220-deep-fall-loop-1122, its 62 town rows replayed as recorded) and the
capture's boards from the 48F down stair to the second 49F arrival (``boards.jsonl.xz``, the
state.jsonl lines of turns 1826818-1826849 of incident 20261122-102427-loop-detected).

DECLARED CONSTRUCTED:

* after a Magic-Eater power key, the next board carries the completed operation the production
  executor adds to it (``_completed_operation_owner``/``_sequence``/``_receipt``,
  input_executor.py), which the capture's state.jsonl lines do not keep;
* the executor's game: the recorded board the key is posted on, and the recorded next board
  (for the 48F walk step, the same board ten game turns on).
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

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-220-deep-fall-loop-1122"
STAIR_48F = Position(29, 93)
STAIR_49F = Position(24, 7)


class DeepFallLoopTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
            cls.town = replay_window("n1c-220-deep-fall-loop", cls.policy, iter(steps))
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode(
            "utf-8").splitlines()
        seen = set()
        cls.raws = []
        for line in lines:
            raw = json.loads(line)
            if raw.get("type") == "player_turn" and raw["turn"] not in seen:
                seen.add(raw["turn"])
                cls.raws.append(raw)
        cls.decided = []
        previous = None
        for raw in cls.raws:
            if previous is not None and previous[0][:1] in ("m", "U"):
                # DECLARED CONSTRUCTED (module docstring): the executor's completed operation.
                raw = dict(raw, _completed_operation_owner=previous[1],
                           _completed_operation_sequence=cls.policy._decision_sequence,
                           _completed_operation_receipt={})
            board = parse_snapshot(raw, cls.policy._monrace_knowledge)
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                key = cls.policy.choose_key(board)
            previous = (key or "", cls.policy.last_reason)
            cls.decided.append((raw, board, key, cls.policy.last_reason))
            if board.dungeon_level == 48 and board.player.position == STAIR_48F \
                    and cls.policy.last_reason not in ("me-power:new-floor:map-area",) \
                    and len(cls.decided) > 2:
                # The 48F board after the leave: the decision that took the stair again.
                break

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def _post(self, key, raw, next_raw, reason):
        """The production executor posts ``key`` on the recorded ``raw`` line, the game showing
        the recorded ``next_raw`` after the command."""
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
        self.assertEqual(self.town.matched_rows, 62)

    def test_the_49f_leave_goes_up_the_stair_underfoot(self):
        from hengbot import deep_fall_guard

        leave = next(index for index, (_raw, board, key, reason) in enumerate(self.decided)
                     if reason == deep_fall_guard.ASCEND_REASON)
        raw, board, key, _reason = self.decided[leave]
        self.assertEqual((board.floor_key, board.player.position), ((1, 49, 0), STAIR_49F))
        self.assertEqual(key, "<")
        # Five sleeping ogres in view: the absorbed Detect Traps is held but not cast here.
        self.assertTrue(deep_fall_guard.holds_detection(self.policy, board))
        self.assertTrue(self.policy._physical_hostiles(board))
        next_raw = self.decided[leave + 1][0]
        self.assertEqual(next_raw["floor"]["level"], 48)
        self.assertTrue(self._post(key, raw, next_raw, deep_fall_guard.ASCEND_REASON))

    def test_the_stair_back_to_the_left_49f_is_not_taken_again(self):
        from hengbot import fled_floor_stairs

        raw, board, key, reason = self.decided[-1]
        self.assertEqual((board.floor_key, board.player.position), ((1, 48, 0), STAIR_48F))
        self.assertTrue(board.grid_at(STAIR_48F).has_down_stairs)
        # Recorded 2026-11-22 10:24:20: ('>', 'descend') loaded the same 49F again.
        self.assertTrue(fled_floor_stairs.leads_back(self.policy, board, STAIR_48F))
        self.assertFalse(self.policy._is_descent_target(board, board.grid_at(STAIR_48F)))
        self.assertNotEqual(key, ">")
        self.assertNotEqual(reason, "descend")
        self.assertIsNotNone(key)
        # The walk goes on toward another down stair of 48F (a new 49F).
        self.assertEqual(reason, "clear-descent")
        # DECLARED CONSTRUCTED: the next board is the recorded one, ten game turns on (the
        # recorded next line is the 49F the stair loaded).
        self.assertTrue(self._post(key, raw, dict(raw, turn=raw["turn"] + 10), reason))


if __name__ == "__main__":
    unittest.main()
