"""A night at the inn between two loops of the 99F/100F Teleportation circuit (owner 2026-11-20).

Owner, verbatim: 「一周する毎に宿屋で一泊する」 -- a loop of the four towns (finale_teleport_tour)
that ends with the scrolls still short of 40 is followed by one night at the inn, and the loop
starts again, until the 40 are owned (only the expedition's funds rule stops it).  The night
moves the game to the next half day (world.cpp pass_game_turn_by_stay) and each store restocks by
the time passed when it is next entered (store.cpp store_maintenance).

Recorded: n1-c life-217's town arrival of 2026-11-20 23:30:21 (tests/fixtures/
n1c-217-home-census-1120), its first two decisions replayed: the Outpost (town 0), towns 0-4
visited, 16,952 gold, Teleportation 24 owned of the plan's 40.

DECLARED CONSTRUCTED: this town's suppliers (the Alchemist, the General Store) marked visited; the
other three towns marked tried (the loop's legs as their arrivals record them, the loop ending
back here); the player stood beside the inn's entrance for the stay; the board after the night
(the turn advanced).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, finale_teleport_tour as tour, me_inn_refill
from hengbot.model import DUNGEON_ANGBAND, Position, STORE_ALCHEMIST, STORE_GENERAL
from hengbot.policy_constants import TOWN_TELEPORT_BUILDING_TYPES
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-home-census-1120"


class N1c217TeleportInnNightRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, journal, steps = load(FIXTURE, Path(self.scratch.name))
        for recorded, supply in steps[:2]:
            self.board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                self.policy.choose_key(self.board)
            self.policy.confirm_key_posted(recorded["key"])

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def suppliers_visited(self):
        for store in (STORE_ALCHEMIST, STORE_GENERAL):
            self.policy._town_store_attempted[store] = self.board.turn

    def loop_done(self):
        """The loop started here, the other three towns tried, back here."""
        self.suppliers_visited()
        self.assertTrue(tour.start(self.policy, self.board))
        tour.circuit(self.policy).tried_towns.extend([1, 2, 3])
        return tour.start(self.policy, self.board)

    def beside_the_inn(self):
        inn = TOWN_TELEPORT_BUILDING_TYPES[0]
        door = next(grid.position for grid in self.board.grids.values()
                    if grid.building_type == inn)
        here = next(Position(door.y + dy, door.x + dx)
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if (grid := self.board.grids.get(Position(door.y + dy, door.x + dx))) is not None
                    and grid.passable and grid.building_type < 0 and not grid.has_monster)
        return replace(self.board, player=replace(self.board.player, position=here))

    def test_a_loop_done_short_brings_the_night(self):
        self.assertFalse(self.loop_done())
        self.assertIsNone(self.policy._cross_town_shopping)
        self.assertEqual(self.policy._cross_town_shopping_funds["why"], "all-towns-tried")
        self.assertTrue(tour.night(self.policy).due)
        self.assertFalse(angband_finale.memory(self.policy).teleport_tour_done)
        with contextlib.redirect_stdout(io.StringIO()):
            key = tour.night_key(self.policy, self.board)
        self.assertTrue(key)
        self.assertEqual(self.policy.last_reason, me_inn_refill.FINALE_TELEPORT_APPROACH_REASON)

    def test_the_night_then_the_next_loop(self):
        self.loop_done()
        board = self.beside_the_inn()
        with contextlib.redirect_stdout(io.StringIO()):
            key = tour.night_key(self.policy, board)
        self.assertEqual(self.policy.last_reason, me_inn_refill.FINALE_TELEPORT_REST_REASON)
        self.assertTrue(key.endswith(me_inn_refill.REST_KEY + "\x1b"), key)
        self.assertEqual(tour.night(self.policy).stay.posted_turn, board.turn)
        # The board after the night: the suppliers are to be shopped again (restocked).
        after = replace(board, turn=board.turn + 50_000)
        self.assertIsNone(tour.night_key(self.policy, after))
        self.assertEqual((tour.night(self.policy).due, tour.night(self.policy).nights), (False, 1))
        self.assertFalse(tour.due(self.policy, after))
        for store in (STORE_ALCHEMIST, STORE_GENERAL):
            self.policy._town_store_attempted[store] = after.turn
        self.assertTrue(tour.due(self.policy, after))
        self.assertTrue(tour.start(self.policy, after))
        self.assertEqual(tour.circuit(self.policy).tried_towns, [0])  # a new loop
        # Only the funds stop it.
        self.policy._cross_town_shopping = None
        poor = replace(after, player=replace(after.player, gold=1000))
        self.assertFalse(tour.start(self.policy, poor))
        self.assertEqual(self.policy._cross_town_shopping_funds["why"], "funds")
        self.assertTrue(angband_finale.memory(self.policy).teleport_tour_done)

    def test_a_dungeon_board_forgets_the_night(self):
        self.loop_done()
        angband_finale.observe(self.policy, replace(self.board, floor_key=(DUNGEON_ANGBAND, 95, 0),
                                                    town_flag=False))
        self.assertFalse(tour.night(self.policy).due)


if __name__ == "__main__":
    unittest.main()
