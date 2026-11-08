"""n1-b life-345 (2026-11-08 08:11-08:14, Magic-Eater Lv32): the Zul trip without a cure.

The mutation-cure trip (owner 2026-11-07) entered Zul three times (08:11:27, 08:13:23,
08:13:43).  The game places the player by the direction of the last global-map step
(movement-execution.cpp: up-right lands at (MAX_HGT - 2, 1) = (64,1)), on a MOUNTAIN
cell; Zul is mountain all round.  MOUNTAIN is WALL + CAN_FLY without MOVE: a levitating
player walks it, but the bot's floor index and the game's travel do not, so
building_step found no step to the Chaos Tower (b:14 at (21,68)) and each entry left on
the next decision without a cure.  On the third trip an ambush on the global map
refused '<' (no monster in view at night, 9 cells shown), no route to the map edge was
known, and the stuck escape read Recall on the surface (down to Orc cave L22); the
second Recall came up on the ambush tile and the nearest-town walk-in put the character
in Zul again, where Zul has no inn: me-staff return-outpost-unavailable, then
fixedquest:prepare-return:route-unavailable WAIT x11 until owner-retired-burst.

Now (1) a levitating player walks over the mountains to the Tower, (2) a Tower out of
reach closes the trip by name, (3) in Zul without the trip the cures are taken, else the
walk leaves for the inn town nearest Zul, (4) the trip's ambush heads for the map edge in
the dark and no Recall is read on the surface as a stuck escape.
Fixture: tests/extract_n1b_343_345_1108_fixtures.py (zul.tar.xz: the 08:13:57 restart
checkpoint in Zul at (64,1), its journal, and the boards of turns 1772427 and 1772550).
DECLARED CONSTRUCTED: the observed mutation signature (the character sheet is not on the
boards; the live trip ran, so one curable mutation was observed); the trip record of the
third entry (as the decision log shows it under way: start town 3, not returning); the
positions of the walk to the Tower (the recorded board with the player moved along the
chosen steps); the board without a mutation for the walk-out.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest

from hengbot import zul_trip
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import UP_STAIRS_KEY
from replay_town_arrival import decisions, journal, restore
from tests import test_input_executor as executor_pins

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-343-345-1108"
MUTATION = 1          # DECLARED CONSTRUCTED: one curable mutation
TOWER = Position(21, 68)
ENTRY_TURN = 1772427  # the third Zul entry, the trip under way
AMBUSH_TURN = 1772550
START_TOWN = 3        # the decision log: the inn teleport 'md' before '<'


class ZulRecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        visit = self.scratch / "town-arrival"
        visit.mkdir(parents=True)
        with tarfile.open(FIXTURES / "zul.tar.xz") as tar:
            tar.extractall(visit, filter="data")
        self.visit = visit
        with gzip.open(visit / "boards.jsonl.gz", "rt", encoding="utf-8") as stream:
            self.boards = [json.loads(line) for line in stream]

    def load(self):
        runtime = self.scratch / "runtime"
        runtime.mkdir(exist_ok=True)
        policy = restore(self.visit, runtime)
        return policy, journal(self.visit), list(decisions(policy, self.visit, runtime))

    def recorded(self, turn, index=-1):
        return [row for row in self.boards if row["turn"] == turn][index]

    def ready(self, *, mutation=True):
        """The restart's policy past its periodic reads, and the first errand row."""
        policy, recorded, steps = self.load()
        policy._mutation_signature = (MUTATION,) if mutation else ()
        row = next(index for index, entry in enumerate(recorded)
                   if not entry["reason"].startswith("periodic:"))
        for index in range(row):
            board = steps[index][1]()
            self.assertEqual((policy.choose_key(board), policy.last_reason),
                             (recorded[index]["key"], recorded[index]["reason"]))
            policy.confirm_key_posted(recorded[index]["key"])
        return policy, recorded, steps, row

    def stranded(self, *, mutation=True):
        """The restart's first errand board in Zul (recorded: the Home scan, then WAITs)."""
        policy, recorded, steps, row = self.ready(mutation=mutation)
        return policy, recorded[row], steps[row][1]()

    def at_restart(self, policy, raw):
        """DECLARED CONSTRUCTED: a recorded board moved after the restart's turn."""
        raw = copy.deepcopy(raw)
        raw["turn"] = self.restart_turn + 10
        return raw

    @property
    def restart_turn(self):
        return max(json.loads(entry["line"] or entry["inputs"][-1])["turn"]
                   for entry in journal(self.visit))

    @staticmethod
    def decide(policy, board):
        """choose_key past a Home knowledge read a fresh board may ask first."""
        for _ in range(4):
            key = policy.choose_key(board)
            if not policy.last_reason.startswith("home:request-knowledge"):
                return key
            policy.confirm_key_posted(key)
        return key

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

    # -- (1) the Tower over the mountains -----------------------------------

    def test_the_entry_board_walks_over_the_mountains_to_the_tower(self):
        policy, _recorded, _steps, _row = self.ready()
        raw = self.at_restart(policy, self.recorded(ENTRY_TURN))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual((board.town_id, board.player.position), (zul_trip.ZUL_TOWN_ID, Position(64, 1)))
        self.assertTrue(zul_trip.has_levitation(board))
        self.assertEqual(board.grid_at(board.player.position).terrain_id, zul_trip.MOUNTAIN_TERRAIN_ID)
        policy._zul_trip = zul_trip.ZulTrip(active=True, start_town=START_TOWN,
                                            curable=(MUTATION,), price=zul_trip.CURE_OTHER_PRICE)
        key = self.decide(policy, board)
        # Recorded: '<' town:zul:enter-global (no step to building 14).
        self.assertEqual(policy.last_reason, zul_trip.APPROACH_REASON, key)
        self.assertEqual(key, "9")  # up-right, over the mountain toward (21,68)
        self.assertFalse(zul_trip.state(policy).returning)
        self.assert_posts(policy, raw, board, key)

    def test_the_walk_reaches_the_tower_and_pays_the_cure(self):
        policy, _recorded, _steps, _row = self.ready()
        policy._zul_trip = zul_trip.ZulTrip(active=True, start_town=START_TOWN,
                                            curable=(MUTATION,), price=zul_trip.CURE_OTHER_PRICE)
        raw = self.at_restart(policy, self.recorded(ENTRY_TURN))
        deltas = {key: (dy, dx) for dy, dx, key in zul_trip._DIRECTIONS}
        for step in range(200):
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = self.decide(policy, board)
            if policy.last_reason == zul_trip.CURE_REASON:
                break
            policy.confirm_key_posted(key)
            if zul_trip.town_travel.is_travel_macro(key):
                # In the town core the game's travel serves: the cursor's cell.
                self.assertEqual(policy.last_reason, zul_trip.APPROACH_REASON,
                                 (step, key, raw["player"]["y"], raw["player"]["x"]))
                for cursor in key[len(zul_trip.town_travel.TRAVEL_MACRO_PREFIX):-1]:
                    dy, dx = deltas[cursor]
                    raw["player"]["y"] += dy
                    raw["player"]["x"] += dx
            else:
                self.assertIn(key, deltas, (step, key, policy.last_reason))
                dy, dx = deltas[key]
                raw["player"]["y"] += dy
                raw["player"]["x"] += dx
            raw["turn"] += 10
        else:
            self.fail("the walk never reached the Tower")
        # One cure paid: building 14's 'm', then ESC.
        self.assertTrue(key.endswith(zul_trip.CURE_KEY + "\x1b"), key)

    def test_a_tower_out_of_reach_closes_the_trip_by_name(self):
        policy, _recorded, _steps, _row = self.ready()
        record = zul_trip.ZulTrip(active=True, start_town=START_TOWN,
                                  curable=(MUTATION,), price=zul_trip.CURE_OTHER_PRICE)
        policy._zul_trip = record
        raw = self.at_restart(policy, self.recorded(ENTRY_TURN))
        # DECLARED CONSTRUCTED: no levitation shown (no flying over the mountains).
        raw["player"]["ability_sources"]["levitation"] = {
            "equipment": False, "permanent": False, "riding": None, "temporary": False}
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertFalse(zul_trip.has_levitation(board))
        key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), (UP_STAIRS_KEY, zul_trip.ENTER_GLOBAL_REASON))
        self.assertTrue(record.returning)
        self.assertEqual(record.failure, zul_trip.TOWER_UNREACHABLE)
        # Back in the start town the trip closes by name for the stay.
        zul_trip._finish(policy, board, record)
        closed = zul_trip.state(policy)
        self.assertEqual((closed.active, closed.failure, closed.closed_epoch),
                         (False, zul_trip.TOWER_UNREACHABLE, policy._town_visit_epoch))
        self.assertEqual(policy.last_reason, "town:zul:skipped:" + zul_trip.TOWER_UNREACHABLE)

    # -- (3) stranded in Zul --------------------------------------------------

    def test_the_stranded_board_takes_the_cure_walk(self):
        policy, recorded, board = self.stranded()
        self.assertEqual((board.town_id, board.player.position), (zul_trip.ZUL_TOWN_ID, Position(64, 1)))
        key = self.decide(policy, board)
        record = zul_trip.state(policy)
        self.assertTrue(record.active)
        self.assertFalse(record.returning)
        self.assertEqual(record.start_town, zul_trip.nearest_inn_town(policy, board))
        self.assertEqual((key, policy.last_reason), ("9", zul_trip.APPROACH_REASON))
        self.assert_posts(policy, json.loads(self.raw_line(recorded)), board, key)

    def test_the_stranded_board_without_a_cure_walks_out(self):
        policy, recorded, board = self.stranded(mutation=False)
        key = self.decide(policy, board)
        record = zul_trip.state(policy)
        self.assertEqual((key, policy.last_reason), (UP_STAIRS_KEY, zul_trip.ENTER_GLOBAL_REASON))
        self.assertTrue(record.active and record.returning)
        self.assertEqual(record.failure, zul_trip.WALK_OUT)
        self.assertIsNotNone(record.start_town)
        self.assert_posts(policy, json.loads(self.raw_line(recorded)), board, key)

    @staticmethod
    def raw_line(entry):
        return entry["line"] or entry["inputs"][-1]

    # -- (4) the ambush in the dark -------------------------------------------

    def test_the_dark_ambush_heads_for_the_edge_instead_of_recall(self):
        policy, _recorded, _steps, _row = self.ready()
        policy._zul_trip = zul_trip.ZulTrip(active=True, start_town=START_TOWN,
                                            curable=(MUTATION,), price=zul_trip.CURE_OTHER_PRICE)
        first, refused = (self.at_restart(policy, self.recorded(AMBUSH_TURN, 0)),
                          self.at_restart(policy, self.recorded(AMBUSH_TURN, 1)))
        self.assertIn("襲撃だ！", first["messages"])
        board = parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge)
        self.assertTrue(board.on_open_wilderness)
        key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), (UP_STAIRS_KEY, zul_trip.ENTER_GLOBAL_REASON))
        policy.confirm_key_posted(key)
        board = parse_snapshot(copy.deepcopy(refused), policy._monrace_knowledge)
        self.assertEqual(sum(1 for grid in board.grids.values() if grid.known), 9)
        key = self.decide(policy, board)
        # Recorded: 'rfc' stuck:recall-escape.  (53,120) on a 66-row map: down.
        self.assertEqual((key, policy.last_reason), ("2", zul_trip.EDGE_REASON))
        self.assert_posts(policy, refused, board, key)

    def test_no_recall_is_read_as_a_stuck_escape_on_the_trip(self):
        policy, _recorded, _steps, _row = self.ready()
        policy._zul_trip = zul_trip.ZulTrip(active=True, start_town=START_TOWN,
                                            curable=(MUTATION,), price=zul_trip.CURE_OTHER_PRICE)
        board = parse_snapshot(self.at_restart(policy, self.recorded(AMBUSH_TURN, 1)),
                               policy._monrace_knowledge)
        self.assertTrue(zul_trip.holds_surface_recall(policy, board))
        self.assertIsNotNone(policy._find_recall_scroll(board))
        key = policy._stuck_escape_key(board)
        self.assertNotEqual(policy.last_reason, "stuck:recall-escape", key)


if __name__ == "__main__":
    unittest.main()
