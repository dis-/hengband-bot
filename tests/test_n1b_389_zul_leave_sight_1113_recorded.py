"""n1-b life-389 (2026-11-13 16:32, Lv40, Zul at night): '<' refused by a sensed monster.

Recorded (build bot-6bddc7291): after the mutation cure the Zul trip read '<'
(town:zul:enter-global) at (20,68) five times; the game answered
「敵がすぐ近くにいるときは広域マップに入れない！」 each time (src/floor/wild.cpp
change_wild_mode: an awake hostile within MAX_PLAYER_SIGHT, seen or not).  The one
monster was a Black market agent sensed by telepathy at (11,72) (cdis 11), never in
view, so the town hunt (visible monsters only) had nothing to do.  The trip returned
None on each refused board and the Home work took the board in a town without a Home:
equipment-transaction:home-route-unavailable, abandon-blocked, and
equipment-transaction:home-route-repeat-terminal stopped the bot three times
(16:32:29, 16:32:45, 16:32:57) until the slot made a new character.

Fix: zul_trip._enter_global_key walks toward the nearest cell no perceived awake
hostile refuses '<' from (owner 2026-11-08 「敵から離れて…全体地図へ出る」), then '<'.

Fixture: tests/extract_n1b_389_zul_leave_sight_1113_fixture.py (``r1632``, the first
restart's checkpoint in Zul, rows 0-5).
DECLARED CONSTRUCTED: the board with the player moved to the walk's target.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import copy
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from dataclasses import replace

from hengbot import wilderness_exit, zul_trip
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position
from hengbot.policy_constants import UP_STAIRS_KEY
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import decisions, journal, restore
from tests.support.recorded import FaithfulHookGame, ProductionHarness, command_screen

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-389-zul-leave-sight-1113"
PLAYER = Position(20, 68)
AGENT = Position(11, 72)


class N1b389ZulLeaveSight1113RecordedTest(ProductionHarness):
    def load(self, name="r1632"):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        fixture, visit = FIXTURES / name, Path(scratch.name) / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((fixture / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = Path(scratch.name) / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def through(self, row):
        """The restart's periodic reads replayed as recorded, then the board of ``row``."""
        policy, recorded, steps = self.load()
        for index in range(row):
            board = steps[index][1]()
            if index < 3:
                self.assertEqual((policy.choose_key(board), policy.last_reason),
                                 (recorded[index]["key"], recorded[index]["reason"]))
            policy.confirm_key_posted(recorded[index]["key"])
        board = steps[row][1]()
        entry = recorded[row]
        raw = json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])
        return policy, recorded, raw, board

    def post(self, policy, raw, board, key):
        """``key`` through the production executor port on the recorded board."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the next board after the step.
        game.screens = [command_screen(raw["turn"] + 10)]
        game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        return game.accepted

    def assert_walks_out_of_sight(self, policy, raw, board):
        """The step toward a cell the agent does not refuse '<' from; that cell."""
        self.assertEqual((board.town_id, board.player.position), (zul_trip.ZUL_TOWN_ID, PLAYER))
        self.assertEqual(board.visible_monsters, [])
        awake = wilderness_exit.perceived_awake_hostiles(board)
        self.assertEqual([monster.position for monster in awake], [AGENT])
        self.assertTrue(wilderness_exit.refuses_from(PLAYER, awake))
        route = zul_trip.leave_sight_route(policy, board, awake)
        self.assertFalse(wilderness_exit.refuses_from(route.target, awake))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         (policy._direction_key(PLAYER, route.first_step), zul_trip.LEAVE_SIGHT_REASON))
        self.assertEqual(self.post(policy, raw, board, key), [key])
        return route.target

    def test_the_first_errand_board_walks_away_instead_of_reading_up(self):
        """Row 3.  Recorded: '<' town:zul:enter-global (refused on row 4's board)."""
        policy, recorded, raw, board = self.through(3)
        self.assertEqual((recorded[3]["key"], recorded[3]["reason"]),
                         (UP_STAIRS_KEY, zul_trip.ENTER_GLOBAL_REASON))
        self.assert_walks_out_of_sight(policy, raw, board)

    def test_the_refused_board_walks_away_then_reads_up_out_of_range(self):
        """Row 4 shows the refusal.  Recorded: 'bA' me-staff, then '<' again on row 5."""
        policy, recorded, raw, board = self.through(4)
        self.assertTrue(wilderness_exit.global_map_refused(board))
        target = self.assert_walks_out_of_sight(policy, raw, board)
        # DECLARED CONSTRUCTED: the walk arrived, the agent where it was.
        policy, recorded, raw, board = self.through(5)
        arrived = replace(board, player=replace(board.player, position=target))
        self.assertEqual((policy.choose_key(arrived), policy.last_reason),
                         (UP_STAIRS_KEY, zul_trip.ENTER_GLOBAL_REASON))


if __name__ == "__main__":
    unittest.main()
