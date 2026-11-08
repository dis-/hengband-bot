"""n1-c life-169 (2026-11-08 13:42/13:43, Lv31): the Zul trip's walk to the inn retired.

Back in town at (31,150) from the Yeek cave fundraise, the mutation-cure trip
(zul_trip._prepare_key) walked to the inn for the teleport to its start town 3, one cell
at a time (town:zul:travel), then the game's travel to the inn's side and the inn step
'3md'.  The arbiter files every town:zul: reason under cross-town (town_arbiter), but the
walk declared its Reach under quest-request (zul_trip.PRODUCER), and the progress vector
measures a declared walk only for the owner that declared it (_declared_walk_part): each
step after the first scored no progress, cross-town retired nine steps in, again nine
steps later, and on the inn step a third time -> town:blocked:owner-retired-burst (twice:
13:42:04 and 13:43:17).

Now the inn walk declares its Reach under cross-town: every step, the travel and the inn
step are progress, nothing retires and the inn step is posted.
Fixture: tests/extract_n1c_169_1108_fixtures.py (inn.tar.xz: the 13:43:10 arrival
checkpoint at (31,150) and its whole journal; the boards are the recorded ones).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest

from hengbot import zul_trip
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position
from replay_town_arrival import decisions, journal, restore
from tests import test_input_executor as executor_pins

FIXTURES = Path(__file__).with_name("fixtures") / "n1c-169-1108"
START_TOWN = 3          # the inn's teleport: 'm' + chr(ord('a') + 3)
ARRIVAL = Position(31, 150)
INN_STEP = "3md"


class ZulInnWalkRecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        visit = self.scratch / "town-arrival"
        visit.mkdir(parents=True)
        with tarfile.open(FIXTURES / "inn.tar.xz") as tar:
            tar.extractall(visit, filter="data")
        self.visit = visit

    def load(self):
        runtime = self.scratch / "runtime"
        runtime.mkdir(exist_ok=True)
        policy = restore(self.visit, runtime)
        return policy, journal(self.visit), list(decisions(policy, self.visit, runtime))

    def assert_posts(self, policy, raw, board, key):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the next board after the command.
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)

    def test_every_step_of_the_inn_walk_is_cross_town_progress(self):
        policy, recorded, steps = self.load()
        arbiter = policy._town_turn_arbiter
        self.assertEqual([entry["reason"] for entry in recorded],
                         [zul_trip.TRAVEL_REASON] * len(recorded))
        self.assertEqual(recorded[-1]["key"], INN_STEP)
        travels = 0
        for index, (entry, supply) in enumerate(steps):
            board = supply()
            if index == 0:
                self.assertEqual(board.player.position, ARRIVAL)
            key = policy.choose_key(board)
            # Recorded: the ninth step (and the 18th, and the inn step) retired
            # cross-town; the CLI rewrote the inn step to the burst WAIT.
            self.assertEqual((key, policy.last_reason), (entry["key"], entry["reason"]),
                             (index, board.player.position))
            telemetry = arbiter.telemetry
            self.assertEqual(telemetry["owner"], "cross-town", index)
            self.assertFalse(telemetry["retired"], index)
            self.assertEqual(tuple(arbiter.pending_retirement_owners), (), index)
            self.assertTrue(telemetry["progress"], (index, board.player.position, key))
            travels += zul_trip.town_travel.is_travel_macro(key)
            if index < len(steps) - 1:
                policy.confirm_key_posted(key)
        self.assertEqual(travels, 1)
        self.assertEqual(key, "3m" + chr(ord("a") + START_TOWN))
        # The walk's Reach is declared under the owner the arbiter files it under.
        self.assertEqual(policy._decision_goal[0], "cross-town")
        self.assert_posts(policy, json.loads(recorded[-1]["line"] or recorded[-1]["inputs"][-1]),
                          board, key)


if __name__ == "__main__":
    unittest.main()
