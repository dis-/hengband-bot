"""The 99F/100F Teleportation bought in the other towns (finale_teleport_tour, owner 2026-11-20).

Owner, verbatim: 「4つの街を回ってテレポートの巻物を買い足す処理をつけて」 (the four towns other
than Zul, owner 2026-11-17 「すべての町にズルは含まない」).

Recorded: n1-c life-217's town arrival of 2026-11-20 23:30:21 (tests/fixtures/
n1c-217-home-census-1120), its first two decisions replayed (the second brings the Home census):
the Outpost (town 0), towns 0-4 visited, 16,952 gold, Teleportation 24 owned (none at Home) of the
plan's 40.

DECLARED CONSTRUCTED: this town's suppliers of the plan (the Alchemist and the General Store)
marked visited this visit; the arrivals in the other towns (the expedition's tried towns, as the
leg's arrival records them); the gold of the funds test; a dungeon board (the census board as
Angband 95F) for the trip's end.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, finale_teleport_tour
from hengbot.model import DUNGEON_ANGBAND, STORE_ALCHEMIST, STORE_GENERAL
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-home-census-1120"
ZUL = 4


class N1c217TeleportTourRecordedTest(unittest.TestCase):
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

    def test_due_after_this_towns_suppliers(self):
        policy, board = self.policy, self.board
        self.assertEqual(finale_teleport_tour.shortage(policy, board), 16)
        self.assertFalse(finale_teleport_tour.due(policy, board))
        self.suppliers_visited()
        self.assertTrue(finale_teleport_tour.due(policy, board))

    def test_the_circuit_over_the_other_towns(self):
        policy, board = self.policy, self.board
        self.suppliers_visited()
        self.assertTrue(finale_teleport_tour.start(policy, board))
        expedition = finale_teleport_tour.circuit(policy)
        self.assertEqual(policy._effective_town_id(board), 0)
        self.assertEqual(tuple(sorted(board.visited_town_ids)), (0, 1, 2, 3, ZUL))
        self.assertEqual(expedition.candidate_order, (1, 2, 3))  # the other three, not Zul
        self.assertEqual(expedition.tried_towns, [0])
        self.assertTrue(policy._cross_town_trip_holds_town(board))
        # The expedition's Teleportation shortage is the plan's 16 (the ledger asks none).
        self.assertIn(("teleport", 16), policy._cross_town_shortages(board))
        # Each other town tried, the last one ends the loop.
        expedition.tried_towns.extend([1, 2])
        last = replace(board, town_id=3)  # DECLARED: the arrival in town 3
        self.assertFalse(finale_teleport_tour.start(policy, last))
        self.assertIsNone(policy._cross_town_shopping)
        self.assertEqual(policy._cross_town_shopping_funds["why"], "all-towns-tried")
        # The loop's end: the inn's night comes first (owner 2026-11-20 「一周する毎に宿屋で一泊
        # する」, tests/test_n1c_217_teleport_inn_night_1120_recorded.py).
        self.assertTrue(finale_teleport_tour.night(policy).due)
        self.assertNotIn(("teleport", 16), policy._cross_town_shortages(last))
        # A dungeon board ends the trip: the next town starts afresh.
        angband_finale.memory(policy).teleport_tour_done = True
        angband_finale.observe(policy, replace(board, floor_key=(DUNGEON_ANGBAND, 95, 0), town_flag=False))
        self.assertFalse(angband_finale.memory(policy).teleport_tour_done)
        self.assertFalse(finale_teleport_tour.night(policy).due)

    def test_funds_short_ends_it(self):
        policy = self.policy
        self.suppliers_visited()
        poor = replace(self.board, player=replace(self.board.player, gold=1000))
        self.assertFalse(finale_teleport_tour.start(policy, poor))
        self.assertEqual(policy._cross_town_shopping_funds["why"], "funds")
        self.assertIsNone(finale_teleport_tour.circuit(policy))


if __name__ == "__main__":
    unittest.main()
