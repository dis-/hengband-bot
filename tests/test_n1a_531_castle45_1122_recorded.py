"""n1-a life-531: the climb switch's Castle (else Mountain) is explored no deeper than 45F.

Owner 2026-11-22 (verbatim): 「鉄獄50Fのとき、城は45Fまでにする。ギリギリを攻めない。」 (dive_floor
``CLIMB_BAND_DEEPEST``).  The band stays 38-42 for n1-a (its fallback depth floor is shallower);
however deep that floor, no stair goes below 45F and every floor below it is climbed.  Word of
Recall read on a band floor answers the game's reset-recall question y, so the next visit lands
in the band instead of on the 50F landing the climb starts from.

Recorded: the 08:25:05 town-arrival checkpoint of n1-a life-531
(tests/fixtures/n1a-531-mountain-climb-1122-survival): the policy holding the unsafe-recall
fallback's Mountain climb (dungeon 14, saved recall depth 50), no *Destruction* means.

DECLARED CONSTRUCTED:

* the dungeon boards: the recorded row-13 board moved to a Mountain floor (``floor_key``,
  ``town_flag``) with a down staircase underfoot; no band board of this rule was journalled (the
  rule did not exist);
* the fallback depth floor 48 (``fallback_depth_floor.floor`` patched) for the band's cap;
* the executor's game: the recorded row-13 line, its floor moved to the Mountain floor and its
  saved Mountain depth 50, the read prompt and recall_player's reset question
  (src/spell-kind/spells-world.cpp:442-449) before the next board (``turn`` + 10).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import dive_floor
from hengbot.cli import _ExecutorInputPort
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins
from town_work_corpus import replay_window

FIXTURES = Path(__file__).with_name("fixtures")
ANGBAND, MOUNTAIN = 1, 14
RESET_PROMPT = "ここは最深到達階より浅い階です。この階に戻って来ますか？ [y/n]"


class Castle45Test(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, journal, steps = load(
                FIXTURES / "n1a-531-mountain-climb-1122-survival", Path(cls.scratch.name))
            replay_window("n1a-531-castle45", cls.policy, iter(steps[:13]))
            cls.row = journal[13]
            cls.town = steps[13][1]()
            cls.policy.choose_key(cls.town)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    # DECLARED CONSTRUCTED (module docstring).
    def _board(self, floor_key):
        board = replace(self.town, floor_key=floor_key, town_flag=False)
        here = board.player.position
        grids = dict(board.grids)
        grids[here] = replace(grids[here], passable=True, wall=False, known=True, trap=False,
                              has_up_stairs=False, has_down_stairs=True, has_entrance=False,
                              store_number=-1, building_type=-1, is_closed_door=False)
        return replace(board, grids=grids)

    def test_the_band_never_reaches_below_45f(self):
        policy = self.policy
        self.assertEqual(dive_floor.climb_dungeon(policy), MOUNTAIN)
        self.assertEqual(self.town.dungeon_recall_depths[MOUNTAIN], 50)
        self.assertEqual(dive_floor.band(policy, self.town), (38, 42))
        with mock.patch("hengbot.fallback_depth_floor.floor", return_value=48):
            self.assertEqual(dive_floor.band(policy, self.town), (45, 45))
            board = self._board((MOUNTAIN, 45, 0))
            self.assertTrue(dive_floor.capped(policy, board, 46))
            self.assertFalse(dive_floor.capped(policy, board, 45))
            self.assertTrue(dive_floor.climbing_floor(policy, board, (MOUNTAIN, 46, 0)))
            self.assertFalse(dive_floor.climbing_floor(policy, board, (MOUNTAIN, 45, 0)))
            grid = board.grid_at(board.player.position)
            self.assertFalse(policy._is_descent_target(board, grid))

    def _answer(self, floor_key):
        """The production executor's answer to the reset question after the recall read."""
        raw = json.loads(self.row["line"])
        raw["floor"] = dict(raw["floor"], dungeon_id=floor_key[0], level=floor_key[1],
                            in_town=False, town_id=0)
        raw["progress"] = dict(raw["progress"], dungeon_recall_depths={
            **raw["progress"].get("dungeon_recall_depths", {}), str(floor_key[0]): 50})
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(executor_pins.READ_PROMPT),
                        executor_pins.prompt_screen(RESET_PROMPT),
                        executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=self.policy)
        result = port("rh", decision={"sequence": self.policy._decision_sequence,
                                      "reason": "return:recall"})
        self.assertTrue(result, port.last_result.reason)
        return game.accepted[-1]

    def test_the_recall_read_on_a_band_floor_resets_the_saved_depth(self):
        policy = self.policy
        cases = (
            ((MOUNTAIN, 40, 0), "y"),   # in the band: the next visit lands on 40
            ((MOUNTAIN, 46, 0), "n"),   # read on the climb: the band's floor is kept for later
            ((ANGBAND, 40, 0), "n"),    # no climb switch there
        )
        for floor_key, expected in cases:
            with self.subTest(floor_key=floor_key):
                board = self._board(floor_key)
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    policy.choose_key(board)
                self.assertEqual(getattr(policy, dive_floor.RECALL_RESET), (MOUNTAIN, 38, 42))
                self.assertEqual(self._answer(floor_key), expected)
        policy._returning_to_town = False
        policy._last_return_trigger = None
        # The next town board: the saved depth 40 is a landing the switch keeps and the recall
        # passes every departure gate (no 50F landing to climb from).
        town = replace(self.town, dungeon_recall_depths={**self.town.dungeon_recall_depths,
                                                         MOUNTAIN: 40})
        self.assertTrue(dive_floor.reaches_band(policy, town, MOUNTAIN))
        self.assertTrue(dive_floor.refused_dive_held(policy, town))
        self.assertTrue(policy._recall_destination_safe(town, MOUNTAIN))
        self.assertTrue(policy._destination_depth_allowed(town, 40))


if __name__ == "__main__":
    unittest.main()
