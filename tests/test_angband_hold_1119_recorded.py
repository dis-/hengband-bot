"""Owner 2026-11-19: from Angband 50F on no shallower fallback; only a dungeon lord's kill moves the target.

Owner (verbatim): 「鉄獄50F以降は浅い階層へのフォールバックをやめる。行き先を変えるのはダンジョンの主討伐のみと
する。」 (``hengbot.angband_hold``).  n1-c life-217 (Magic-Eater Lv41) alternated between Angband 80F and
the Castle 64F over 11-19 07:00-11:00: the 81F speed gate kept every Angband dive on 80F, five such
dives fired the no-depth-progress valve, and the valve took the deepest entered landing under 80 that
the fallback depth floor (80 - 20) allowed, the Castle 64, for a lease of 5, 10, 20 dives.

Recorded: tests/fixtures/n1c-217-angband-hold-1119 (tests/extract_n1c_217_angband_hold_1119_fixture.py),
n1-c life-217's 11:08:35 town-arrival checkpoint and its arrival board: back from Angband 80F, the
landings Angband 80, the Castle 64, dungeon 19 55, the Mountain 30, the fallback depth floor 60.
Recorded: tests/fixtures/n1a-530-castle-climb-1117 (n1-a life-530, Angband 50 refused for the
*Destruction* means and telepathy) for the unsafe-recall fallback.

DECLARED CONSTRUCTED:
* the n1-c streaks: four no-depth-progress dives before the recorded one (the valve fires on the
  fifth), or the over-extended streak at its limit;
* the n1-c held switch: the Castle held as a no-depth-progress switch with a lease of 10 and 3 dives
  (as life-217 held it 09:40-10:08, restored from the alternate-dungeon record);
* the controls: Angband's landing 49 (the saved depth and the recall depth) below the hold.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import alternate_lease, angband_hold, dive_floor, fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy_constants import NO_DEPTH_PROGRESS_DIVE_LIMIT
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
CASTLE, MOUNTAIN = dive_floor.DUNGEON_CASTLE, dive_floor.DUNGEON_MOUNTAIN


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


def at_49(board):
    """DECLARED CONSTRUCTED (the module docstring): Angband's landing 49."""
    return replace(board, recall_depth=49,
                   dungeon_recall_depths={**board.dungeon_recall_depths, DUNGEON_ANGBAND: 49})


class N1c217AngbandHoldTest(unittest.TestCase):
    """Angband 80: the valves and the held switch leave the target on Angband."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.arrival, _journal, steps = load(FIXTURES / "n1c-217-angband-hold-1119",
                                            Path(cls.scratch.name))
        cls.recorded, supply = steps[0]
        cls.board = supply()

    @classmethod
    def tearDownClass(cls):
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def policy(self):
        return copy.deepcopy(self.arrival)

    def assert_on_angband(self, policy):
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon,
                          policy._alternate_dungeon_reason), (DUNGEON_ANGBAND, None, None))
        self.assertEqual(policy._alternate_lease, 0)
        self.assertIsNone(getattr(policy, dive_floor.STATE))

    def test_a_the_arrival_board(self):
        policy, board = self.policy(), self.board
        self.assertTrue(board.in_town)
        self.assertEqual(policy._floor_key, (DUNGEON_ANGBAND, 80, 0))  # a dive of 80F ends here
        self.assertEqual({did: board.dungeon_recall_depths[did]
                          for did in (DUNGEON_ANGBAND, CASTLE, MOUNTAIN)},
                         {DUNGEON_ANGBAND: 80, CASTLE: 64, MOUNTAIN: 30})
        self.assertEqual(fallback_depth_floor.floor(policy, board), 60)
        self.assertTrue(angband_hold.held(policy, board))
        self.assertIsNone(policy._conquest_target(board))
        key, reason = decide(policy, board)
        self.assertEqual((key, reason), (self.recorded["key"], self.recorded["reason"]))
        self.assert_on_angband(policy)

    def test_b_the_no_depth_progress_valve_stays_on_angband(self):
        policy, board = self.policy(), self.board
        policy._no_depth_progress_dives = NO_DEPTH_PROGRESS_DIVE_LIMIT - 1
        decide(policy, board)
        # Unfixed: (CASTLE, CASTLE, "no_depth_progress") with a lease of 5 -- life-217's 09:40.
        self.assert_on_angband(policy)
        self.assertEqual(policy._no_depth_progress_dives, 0)

    def test_c_the_over_extension_valve_picks_nothing(self):
        # The recorded dive kept loot, so the streak on this board restarts (over_extension); the
        # valve's own pick is read with the over-extended depth it records (the recall depth 80).
        policy, board = self.policy(), self.board
        policy._last_overextended_depth = board.recall_depth
        self.assertEqual(board.recall_depth, 80)
        # Unfixed: the Castle (its 64 under 80, at the floor 60).
        self.assertIsNone(policy._pick_alternate_dungeon(board, prefer_deepest=True))

    def test_d_a_held_castle_switch_is_dropped(self):
        policy, board = self.policy(), self.board
        policy._alternate_dungeon, policy._alternate_dungeon_reason = CASTLE, "no_depth_progress"
        policy._alternate_lease, policy._alternate_dives = 10, 3
        decide(policy, board)
        # Unfixed: the Castle held until its lease of 10 ends.
        self.assert_on_angband(policy)

    def test_e_the_picks_offer_angband_or_nothing(self):
        policy, board = self.policy(), self.board
        # Unfixed: the Castle (its 64 is the deepest under 80 at the floor 60).
        self.assertIsNone(policy._pick_alternate_dungeon(
            board, max_entry_depth=79, prefer_deepest=True))
        self.assertIsNone(policy._activate_safe_recall_fallback(board, 80))
        # A lord-kill trip's bounce or refusal goes back to Angband.
        self.assertEqual(policy._pick_alternate_dungeon(board, guardian_bounced_dungeon=CASTLE),
                         DUNGEON_ANGBAND)
        self.assertEqual(policy._pick_alternate_dungeon(
            board, max_entry_depth=63, prefer_deepest=True, refused_dungeon=CASTLE),
            DUNGEON_ANGBAND)
        self.assertEqual(alternate_lease.deepest_destination(policy, board), DUNGEON_ANGBAND)

    def test_control_below_50_the_valve_switches(self):
        policy, board = self.policy(), at_49(self.board)
        self.assertFalse(angband_hold.held(policy, board))
        policy._alternate_dungeon, policy._alternate_dungeon_reason = CASTLE, "no_depth_progress"
        policy._alternate_lease, policy._alternate_dives = 10, 3
        self.assertFalse(angband_hold.settle(policy, board))
        self.assertEqual(policy._alternate_dungeon, CASTLE)

    def test_control_the_guardian_valve_angband_is_kept(self):
        policy, board = self.policy(), self.board
        policy._alternate_dungeon, policy._alternate_dungeon_reason = DUNGEON_ANGBAND, "guardian_valve"
        self.assertFalse(angband_hold.settle(policy, board))
        self.assertEqual(policy._alternate_dungeon_reason, "guardian_valve")


class N1a530UnsafeAngbandTest(unittest.TestCase):
    """Angband 50 refused (no *Destruction* means, no telepathy): no Castle band any more."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.arrival, _journal, steps = load(FIXTURES / "n1a-530-castle-climb-1117",
                                            Path(cls.scratch.name))
        cls.town = steps[0][1]()

    @classmethod
    def tearDownClass(cls):
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_unsafe_recall_fallback_takes_nothing(self):
        policy, board = copy.deepcopy(self.arrival), self.town
        self.assertEqual(policy._dungeon_entry_depth(board, DUNGEON_ANGBAND, via_recall=True), 50)
        self.assertEqual(policy._missing_required_abilities(board, 50),
                         {"destruction", "telepathy"})
        self.assertTrue(angband_hold.held(policy, board))
        # Unfixed: the Castle band (owner 2026-11-17, test_n1a_530_castle_climb_1117_recorded).
        self.assertIsNone(policy._activate_safe_recall_fallback(board, 50))
        self.assertIsNone(policy._alternate_dungeon)

    def test_the_deepest_destination_is_angband_or_nothing(self):
        policy, board = copy.deepcopy(self.arrival), self.town
        self.assertFalse(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        # Unfixed: the Castle (its landing 49, the deepest that passes, at the floor 30).
        self.assertIsNone(alternate_lease.deepest_destination(policy, board))


if __name__ == "__main__":
    unittest.main()
