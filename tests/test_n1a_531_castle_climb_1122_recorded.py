"""n1-a life-531: the Castle's 50F landing is recalled to and climbed from at once.

Owner 2026-11-22 (verbatim choice) 「城の50Fに帰還してすぐ38〜42Fへ登る」 (deep_climb).  The Lv50
Warrior's device skill 42 makes its thirteen Home staves of *Destruction* about 3% (80% needs 60;
no MAGIC_MASTERY piece is owned), so Angband's 50F landing is refused for the means and telepathy;
the Castle's and the Mountain's recall landings are 50 as well, and before this rule the 11-19
exception (dive_floor.pick_refused, 「この場合だけ城40F付近を許す」) found neither: the visit
fundraised at the Yeek cave 1F (58 hours) and, the Alchemist out of Treasure Detection, stood in
town under ``town:blocked:depth-gate:destination-50:missing-destruction,telepathy``
(loop-detected 2026-11-22 06:12:30).

Recorded (tests/fixtures/n1a-531-castle-climb-1122-*, the server's town-arrival checkpoints):

* ``-blocked``: the arrival of 06:12:13; rows 0-8 replay, row 9 was the blocked '5';
* ``-fundraise``: the arrival of 06:10:53; rows 0-15 replay, row 16 opened the no-safe-destination
  fundraising.

DECLARED CONSTRUCTED:

* the dungeon boards: the recorded row-9 board moved to the Castle's 50F / 49F / the Mountain's
  49F and 50F (``floor_key``, ``town_flag``), the player's grid given up stairs; no dungeon board
  of this rule was recorded (the rule did not exist).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load
from town_work_corpus import replay_window

FIXTURES = Path(__file__).with_name("fixtures")
CASTLE, MOUNTAIN, ANGBAND = 12, 14, 1
BLOCKED = "town:blocked:depth-gate:destination-50:missing-destruction,telepathy"


def _arrival(name, scratch):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        policy, _journal, steps = load(FIXTURES / name, Path(scratch))
    return policy, steps


class BlockedArrivalRecordedTest(unittest.TestCase):
    """06:12:13: the visit that stood in town."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, steps = _arrival("n1a-531-castle-climb-1122-blocked", cls.scratch.name)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.replayed = replay_window("n1a-531-blocked", cls.policy, iter(steps[:9]))
            cls.recorded = steps[9][0]
            cls.board = steps[9][1]()
            cls.key = cls.policy.choose_key(cls.board)
        cls.reason = cls.policy.last_reason

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_rows_before_the_stop_replay(self):
        self.assertEqual(self.replayed.matched_rows, 9)
        self.assertIsNone(self.replayed.first_divergence)
        self.assertEqual(self.recorded["reason"], BLOCKED)

    def test_the_refused_angband_landing_switches_to_the_castle_instead_of_standing(self):
        from hengbot import dive_floor

        self.assertEqual((self.key, self.reason), ("5", "town:unsafe-recall-fallback"))
        self.assertEqual(self.policy._alternate_dungeon, CASTLE)
        self.assertEqual(self.policy._target_dungeon_id, CASTLE)
        self.assertTrue(dive_floor.refused_dive_held(self.policy, self.board))

    def test_the_castle_landing_50_lacks_only_the_50f_row(self):
        policy, board = self.policy, self.board
        self.assertEqual(board.dungeon_recall_depths[CASTLE], 50)
        self.assertEqual(board.dungeon_recall_depths[MOUNTAIN], 50)
        self.assertEqual(policy._missing_required_abilities(board, 50, owned=True),
                         frozenset({"destruction", "telepathy"}))
        self.assertEqual(policy._missing_required_abilities(board, 42, owned=True), frozenset())

    def test_the_recall_to_the_castle_50f_passes_every_departure_gate(self):
        from hengbot import deep_climb, destruction_means

        policy, board = self.policy, self.board
        self.assertTrue(policy._recall_destination_safe(board, CASTLE))
        self.assertTrue(policy._destination_depth_allowed(board, 50))
        self.assertTrue(destruction_means.departure_carried(policy, board, 50))
        self.assertTrue(deep_climb.departure_admits(policy, board, 50))
        # Angband's own 50F landing stays refused (only the Castle's climb is the exception).
        self.assertFalse(policy._recall_destination_safe(board, ANGBAND))
        self.assertFalse(deep_climb.departure_admits(policy, board, 50, dungeon_id=ANGBAND))

    def _dungeon_board(self, floor_key, *, up_stairs=False):
        # DECLARED CONSTRUCTED (module docstring).
        board = replace(self.board, floor_key=floor_key, town_flag=False)
        if up_stairs:
            here = board.player.position
            grids = dict(board.grids)
            grids[here] = replace(grids[here], has_up_stairs=True, has_down_stairs=False,
                                  has_entrance=False, store_number=-1, building_type=-1,
                                  passable=True, wall=False, known=True)
            board = replace(board, grids=grids)
        return board

    def test_on_the_castle_50f_the_row_starts_no_return_and_the_up_stairs_are_taken(self):
        from hengbot import deep_climb, destruction_use

        policy = self.policy
        board = self._dungeon_board((CASTLE, 50, 0), up_stairs=True)
        self.assertTrue(deep_climb.on_floor(policy, board))
        self.assertEqual(deep_climb.floor_gaps(policy, board, {"destruction", "telepathy"}),
                         frozenset())
        self.assertFalse(destruction_use.means_spent(policy, board))
        self.assertEqual(deep_climb.key(policy, board), "<")
        self.assertEqual(policy.last_reason, "castle-climb-landing-50:ascend")
        # 49F is no climb floor of this rule: the ordinary climb to the band plays there.
        self.assertFalse(deep_climb.on_floor(policy, self._dungeon_board((CASTLE, 49, 0))))

    def test_a_descent_into_50f_without_the_means_is_a_named_stop(self):
        from hengbot import deep_climb

        policy = self.policy
        saved = getattr(policy, deep_climb.MEMORY, None)
        try:
            setattr(policy, deep_climb.MEMORY, None)
            for floor_key in ((0, 0, 0), (CASTLE, 50, 0)):
                deep_climb.observe(policy, self._dungeon_board(floor_key)
                                   if floor_key[1] else self.board)
            # The recall's arrival from town is no descent.
            self.assertIsNone(deep_climb.stop_key(policy, self._dungeon_board((CASTLE, 50, 0))))
            for floor_key in ((MOUNTAIN, 49, 0), (MOUNTAIN, 50, 0)):
                deep_climb.observe(policy, self._dungeon_board(floor_key))
            board = self._dungeon_board((MOUNTAIN, 50, 0))
            self.assertEqual(deep_climb.stop_key(policy, board), "5")
            self.assertEqual(policy.last_reason, deep_climb.STOP_REASON)
            from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
            self.assertIn(deep_climb.STOP_REASON, POLICY_FINAL_STOP_REASONS)
        finally:
            setattr(policy, deep_climb.MEMORY, saved)


class FundraiseArrivalRecordedTest(unittest.TestCase):
    """06:10:53: the visit that opened the no-safe-destination fundraising."""

    def test_the_castle_is_taken_instead_of_the_yeek_fundraising(self):
        with TemporaryDirectory() as scratch:
            policy, steps = _arrival("n1a-531-castle-climb-1122-fundraise", scratch)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    replayed = replay_window("n1a-531-fundraise", policy, iter(steps[:16]))
                    recorded = steps[16][0]
                    key = policy.choose_key(steps[16][1]())
                self.assertEqual(replayed.matched_rows, 16)
                self.assertTrue(recorded["reason"].startswith(
                    "town:entrance-step-off:fundraising:no-safe-destination:"))
                self.assertEqual((key, policy.last_reason),
                                 ("6", "town:entrance-step-off:town:unsafe-recall-fallback"))
                self.assertEqual(policy._alternate_dungeon, CASTLE)
            finally:
                policy._home_disposal.history_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
