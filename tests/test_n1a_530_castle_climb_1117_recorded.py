"""n1-a life-530 2026-11-17: no safe destination, the Castle 49F is recalled to and climbed to ~40F.

The Lv42 Warrior (Angband 50 reached; the Castle and the Mountain landing at 49; the over-extended
depth 49 recorded in Angband) holds no *Destruction* means and no telepathy, so the Angband 50
landing is refused (depth gate destination-50: missing destruction, telepathy).  The unsafe-recall
fallback (policy._activate_safe_recall_fallback) found no entered landing between the fallback depth
floor (50 - 20 = 30) and the ceiling 48, and the Castle dive of 11-17 (dive_floor.pick_refused) took
only a landing above that floor (the Castle 49 is not): the visits fundraised -- Yeek cave 1F
mining, town:entrance-step-off:fundraising:no-safe-destination:depth-gate:destination-50:
missing-destruction,telepathy from 21:53 to 22:09, the mining walk-in of this checkpoint at 22:13.

Owner 2026-11-17 (verbatim): 「49Fに帰還して上り階段を探して適正階層まで行く」 -- no wilderness walk,
no recall-depth reset.  The fallback now takes the Castle wherever it lands (the band 38-42 within
it, its landing and band within the depth requirements), the over-extended depth does not bound it,
and below the band the up stairs are taken in the down stairs' place.

Recorded: the town-arrival checkpoint of 22:13:09 (tests/extract_n1a_530_castle_climb_1117_fixture.py),
its 12 journal rows replayed as recorded.

DECLARED CONSTRUCTED:
* ``castle_board``: the mining run's recorded Yeek cave 1F board (yeek-cave-1f-board.jsonl.gz)
  moved to the Castle at the depth asked, the 9x9 cells around the player opened and in view, an
  up staircase ``stair`` cells east of the player (or none) and a down staircase 3 cells west;
* the fundraising set of the recorded visit cleared on the policies that decide those boards (the
  dive is the Castle's, not the mining run's).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import dive_floor, escape_count, explored_floor, fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND, GridState, Position, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-castle-climb-1117"
CASTLE, MOUNTAIN = dive_floor.DUNGEON_CASTLE, dive_floor.DUNGEON_MOUNTAIN


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


class N1a530CastleClimbRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.arrival, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.policy = copy.deepcopy(cls.arrival)
        cls.boards = []
        for recorded, supply in steps:
            board = supply()
            cls.boards.append(board)
            key, reason = decide(cls.policy, board)
            assert (key, reason) == (recorded["key"], recorded["reason"]), recorded
            post(cls.policy, recorded["key"])
        cls.town = cls.boards[0]
        with gzip.open(FIXTURE / "yeek-cave-1f-board.jsonl.gz", "rt", encoding="utf-8") as stream:
            cls.mining_raw = json.loads(stream.read())

    @classmethod
    def tearDownClass(cls):
        for policy in (cls.arrival, cls.policy):
            policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def switched(self):
        policy = copy.deepcopy(self.arrival)
        self.assertEqual(policy._activate_safe_recall_fallback(self.town, 50), CASTLE)
        policy._fundraising_mode = None
        policy._planned_mining_runs = None
        policy._fundraising_purpose_record = None
        return policy

    def castle_board(self, policy, level, stair):
        """DECLARED CONSTRUCTED (the module docstring)."""
        raw = copy.deepcopy(self.mining_raw)
        raw["floor"] = {**raw["floor"], "dungeon_id": CASTLE, "level": level}
        board = parse_snapshot(raw, policy._monrace_knowledge)
        here = board.player.position
        grids = dict(board.grids)
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                cell = Position(here.y + dy, here.x + dx)
                base = grids.get(cell) or GridState(cell, True, True, False, False, False, False, False)
                grids[cell] = replace(
                    base, known=True, passable=True, wall=False, has_up_stairs=False,
                    has_down_stairs=False, can_dig=False, tunnel=False, permanent=False,
                    is_closed_door=False, is_door=False, trap=False, marked=True, in_view=True,
                    lit=True)
        if stair is not None:
            up = Position(here.y, here.x + stair)
            grids[up] = replace(grids[up], has_up_stairs=True)
        down = Position(here.y, here.x - 3)
        grids[down] = replace(grids[down], has_down_stairs=True)
        return replace(board, grids=grids)

    def test_a_the_recorded_no_destination_board(self):
        policy, board = self.arrival, self.town
        self.assertTrue(board.in_town)
        self.assertEqual(self.journal[11]["reason"], "descend")  # the Yeek cave mining walk-in
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon),
                         (DUNGEON_ANGBAND, None))
        self.assertEqual(policy._last_overextended_depth, 49)
        self.assertEqual({did: board.dungeon_recall_depths[did]
                          for did in (DUNGEON_ANGBAND, CASTLE, MOUNTAIN)},
                         {DUNGEON_ANGBAND: 50, CASTLE: 49, MOUNTAIN: 49})
        self.assertEqual((fallback_depth_floor.deepest_reached(policy, board),
                          fallback_depth_floor.floor(policy, board)), (50, 30))
        self.assertEqual(policy._missing_required_abilities(board, 50),
                         {"destruction", "telepathy"})
        self.assertEqual(policy._missing_required_abilities(board, 49), set())
        # Every landing that passes is under the floor 30 or not under the ceiling 48.
        self.assertIsNone(policy._pick_alternate_dungeon(
            board, max_entry_depth=48, prefer_deepest=True, refused_dungeon=DUNGEON_ANGBAND))

    def test_b_the_fallback_recalls_to_the_castle_49(self):
        policy = self.switched()
        board = self.town
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon,
                          policy._alternate_dungeon_reason), (CASTLE, CASTLE, "safe_fallback"))
        self.assertEqual(dive_floor.band(policy, board), (38, 42))
        self.assertEqual(getattr(policy, dive_floor.STATE), (CASTLE, 38))
        self.assertTrue(dive_floor.refused_dive_held(policy, board))
        # The over-extended depth 49 bounds no Castle landing here (the owner names it).
        self.assertTrue(policy._recall_destination_safe(board, CASTLE))
        self.assertEqual(policy._dungeon_entry_depth(board, CASTLE, via_recall=True), 49)
        # The depth floor does not end it on the next town board.
        self.assertFalse(fallback_depth_floor.settle(policy, board))
        self.assertEqual(policy._alternate_dungeon, CASTLE)

    def test_c_below_the_band_the_up_stairs_are_taken(self):
        policy = self.switched()
        board = self.castle_board(policy, 49, 3)
        self.assertTrue(dive_floor.climbing(policy, board))
        self.assertTrue(dive_floor.capped(policy, board, 50))
        key, reason = decide(policy, board)
        self.assertEqual(reason, "castle-climb:seek-upstairs")
        self.assertIn(key, {"3", "6", "9"})  # a step east, toward the up staircase

        policy = self.switched()
        key, reason = decide(policy, self.castle_board(policy, 49, 0))
        self.assertEqual((key, reason), ("<", "castle-climb:ascend"))

    def test_d_in_the_band_no_stair_below_it(self):
        policy = self.switched()
        board = self.castle_board(policy, 42, 3)
        self.assertFalse(dive_floor.climbing(policy, board))
        self.assertTrue(dive_floor.capped(policy, board, 43))
        _key, reason = decide(policy, board)
        self.assertNotIn(reason, {"castle-climb:seek-upstairs", "castle-climb:ascend",
                                  "seek-downstairs", "descend"})
        # Above the band the ordinary descent goes down to it.
        self.assertFalse(dive_floor.capped(policy, self.castle_board(policy, 38, 3), 39))
        # A switch held before the band (its record the floor 30) is read with the band too.
        setattr(policy, dive_floor.STATE, (CASTLE, 30))
        self.assertTrue(dive_floor.capped(policy, board, 43))
        self.assertFalse(dive_floor.capped(policy, board, 42))

    def test_e_climb_floors_are_no_over_extension_evidence(self):
        policy = self.switched()
        board = self.castle_board(policy, 49, 3)
        # Never a dead end recalled from (explored_floor): its way on is the up stairs.
        self.assertFalse(explored_floor.dead_end(policy, board))
        escape_count.start_dive(policy)
        escape_count.count(policy, judged=False)
        escape_count.count(policy, judged=False)
        self.assertEqual(policy._dive_emergencies, 2)  # the floor's return still counts them
        self.assertEqual(escape_count.dive_total(policy), 0)
        escape_count.reset(policy)
        escape_count.count(policy)
        self.assertEqual(escape_count.dive_total(policy), 1)

    def test_control_without_the_switch(self):
        policy = copy.deepcopy(self.arrival)
        policy._fundraising_mode = None
        policy._planned_mining_runs = None
        policy._fundraising_purpose_record = None
        board = self.castle_board(policy, 49, 3)
        self.assertFalse(dive_floor.climbing(policy, board))
        _key, reason = decide(policy, board)
        self.assertFalse(reason.startswith("castle-climb:"))


if __name__ == "__main__":
    unittest.main()
