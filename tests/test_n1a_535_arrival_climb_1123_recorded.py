"""n1-a life-535: a 50F+ arrival without the *Destruction* means climbs to the band.

n1-a life-535 (Warrior Lv40, no *Destruction* means) fell through a trap door from the Castle's
48F onto its 50F (2026-11-23 00:59:50, turn 5123386) and was stopped by
``dungeon:blocked:deep-arrival-without-destruction``.  Owner 2026-11-23 (verbatim choice):
「登りと同じにすぐ45F以浅へ登る」 -- by any path, the arrival climbs like the Castle climb: the up
stairs to the band (at most 45F), the teleport allowed during the climb even short of an instant
death, and the Recall read on a band floor setting the recall depth back to it (deep_climb
``_hold_climb``).

Recorded: the 00:58:36 town-arrival checkpoint of n1-a life-535
(tests/fixtures/n1a-535-deep-arrival-1123, its 148 town rows replayed as recorded) and the
capture's boards: the last 48F board (38,143) and the 50F arrival board (6,18).

DECLARED CONSTRUCTED:

* the town visit replays under the recall gates it was recorded with (deep_fall_guard
  ``landing_refused`` answers False while the rows replay, as in
  tests/test_n1a_535_deep_arrival_1123_recorded.py);
* the 48F walk is the recorded one: its last board is only observed (deep_climb.observe), not
  decided again (since 2026-11-23 the deep fall guard reads Recall there).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.model import Position, parse_snapshot
from support.town_arrival_fixture import load
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-535-deep-arrival-1123"
CASTLE = 12
FALL_STEP = Position(38, 143)
ARRIVAL = Position(6, 18)


class ArrivalClimbTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from hengbot import deep_climb

        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
            # DECLARED CONSTRUCTED (module docstring): the recall gates of the recording.
            with mock.patch("hengbot.deep_fall_guard.landing_refused", return_value=False):
                cls.town = replay_window("n1a-535-arrival-climb", cls.policy, iter(steps))
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode(
            "utf-8").splitlines()
        raws = [json.loads(line) for line in lines]
        raws = [raw for raw in raws if raw.get("type") == "player_turn"]
        cls.walk = cls._board(next(raw for raw in reversed(raws)
                                   if raw["floor"]["level"] == 48))
        cls.arrival = cls._board(raws[-1])
        # The restart: the same policy with no record of the floor before (deep_climb.MEMORY).
        cls.restarted = copy.deepcopy(cls.policy)
        setattr(cls.restarted, deep_climb.MEMORY, None)
        # DECLARED CONSTRUCTED (module docstring): the recorded 48F walk, observed.
        deep_climb.observe(cls.policy, cls.walk)
        cls.alternate_before = (cls.policy._alternate_dungeon,
                                cls.policy._alternate_dungeon_reason)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.key = cls.policy.choose_key(cls.arrival)
        cls.reason = cls.policy.last_reason

    @classmethod
    def _board(cls, raw):
        return parse_snapshot(raw, cls.policy._monrace_knowledge)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_recorded_boards(self):
        self.assertIsNone(self.town.first_divergence)
        self.assertEqual(self.town.matched_rows, 148)
        self.assertEqual((self.walk.floor_key, self.walk.player.position),
                         ((CASTLE, 48, 0), FALL_STEP))
        self.assertEqual((self.arrival.floor_key, self.arrival.player.position),
                         ((CASTLE, 50, 0), ARRIVAL))
        # The no-depth-progress lease, not the climb, sent it to the Castle.
        self.assertEqual(self.alternate_before, (CASTLE, "no_depth_progress"))

    def test_the_arrival_holds_the_climb_instead_of_the_named_stop(self):
        from hengbot import deep_climb, deep_teleport, destruction_use, dive_floor

        policy, board = self.policy, self.arrival
        self.assertFalse(destruction_use.holds_means(policy, board))
        # Recorded: dungeon:blocked:deep-arrival-without-destruction ('5').
        self.assertNotEqual(self.reason, deep_climb.STOP_REASON)
        self.assertIsNone(deep_climb.stop_key(policy, board))
        self.assertEqual(dive_floor.climb_dungeon(policy), CASTLE)
        self.assertLessEqual(dive_floor.band(policy, board)[1], dive_floor.CLIMB_BAND_DEEPEST)
        self.assertTrue(deep_climb.on_floor(policy, board))
        # The adjacent hostile is fought first (every rung above the climb is kept); the climb's
        # own rung climbs (deep_climb.key: the up stairs, else the search for them).
        self.assertEqual((self.key, self.reason), ("4", "melee"))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            climb = deep_climb.key(policy, board)
        self.assertIsNotNone(climb)
        self.assertTrue(policy.last_reason.startswith(deep_climb.REASON), policy.last_reason)
        # The climb reads the teleport as above 50F, and no Recall for the missing means.
        self.assertFalse(deep_teleport.applies(policy, board))
        self.assertFalse(destruction_use.means_spent(policy, board))

    def test_after_a_restart_standing_on_50f_holds_the_climb(self):
        """The first board after a restart has no previous floor (n1-a is resumed on the
        Castle's 50F): standing there without the means is enough."""
        from hengbot import deep_climb, dive_floor

        policy, board = self.restarted, self.arrival
        self.assertIsNone(getattr(policy, deep_climb.MEMORY, None))
        self.assertIsNone(dive_floor.climb_dungeon(policy))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, deep_climb.STOP_REASON)
        self.assertEqual(dive_floor.climb_dungeon(policy), CASTLE)
        self.assertTrue(deep_climb.on_floor(policy, board))
        self.assertIsNone(deep_climb.stop_key(policy, board))
        # A quest floor holds none.
        fresh = copy.deepcopy(self.restarted)
        fresh._alternate_dungeon, fresh._alternate_dungeon_reason = self.alternate_before
        setattr(fresh, dive_floor.STATE, None)
        from dataclasses import replace
        deep_climb.observe(fresh, replace(board, floor_key=(CASTLE, 50, 1)))
        self.assertIsNone(dive_floor.climb_dungeon(fresh))

    def test_the_recall_on_a_band_floor_resets_the_depth(self):
        from hengbot import dive_floor

        policy = self.policy
        dive_floor.observe_recall_reset(policy, self.arrival)
        held = getattr(policy, dive_floor.RECALL_RESET)
        self.assertIsNotNone(held)
        low, high = held[1], held[2]
        observation = {"floor": {"dungeon_id": CASTLE, "level": high, "quest_id": 0},
                       "progress": {"dungeon_recall_depths": {str(CASTLE): 50}}}
        self.assertTrue(dive_floor.reset_recall_depth(observation, held))
        self.assertLessEqual(low, high)


if __name__ == "__main__":
    unittest.main()
