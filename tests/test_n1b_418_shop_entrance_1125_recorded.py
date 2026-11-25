"""Town walks keep off the store entrances they do not go into (n1-b life-418, 2026-11-25 11:17-11:18).

Owner rule 2026-11-13 (pingpong-root-1113): a loop of two owners stepping opposite ways is fixed at
its root.  n1-b life-418 (Lv42 Zombie Magic-Eater) came back to town; walking to an item at
(44,98) (seek-loot) it met a sleeping あてどなくふらつく商人 at (31,91), and the town hunt walked up
to it (town:kill-mob-approach).  From (33,91) the hunt's goal was any cell beside the merchant, and
the nearest one was the store 4 entrance (32,90): the goal walk exempted every entrance its
predicate accepted, so '7' stepped toward the store, which opened a store visit for the walk, and
the town's committed loot walk took the board (``_committed_loot_transition``).  The loot walk's
shortest route from (33,91) to (44,98) began '1' on the store 5 entrance (34,90): stepping onto a
store's cell enters it (player-move.cpp ``move_player_effect``), shop:observe-and-leave left the
page, the hunt stepped '9' off it again, 18 rounds to town:blocked:stage-deadline:buy.

One rule for both walks: a town walk does not step onto an entrance it does not go into.  The goal
walks exempt an entrance only when the predicate names entrances alone (``_nearest_goal_route``),
and the loot walk keeps off the entrances (``walk_vetoes.route_left``: ``off_entrances``).

Recorded (tests/extract_n1b_418_shop_entrance_1125_fixture.py, ``n1b-418-shop-entrance-1125``): the
town-arrival checkpoint of 11:17:17 (turn 5021475) and its 170 journal rows, replayed open-loop
through the public ``choose_key`` (each row posts the recorded key, so the boards stay the live
ones).  Revert of the goal rule: row 113 steps '1' onto (34,90) under seek-loot again.  Revert of
the loot rule: the loot walk's first step from (33,91) is (34,90) again.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import Position
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-418-shop-entrance-1125"
LOOP_ROW = 113  # (33,91): recorded seek-loot '1' onto the store 5 entrance (34,90)
STORE_5 = Position(34, 90)
STORE_4 = Position(32, 90)
OFFSETS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
           "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
WALKS = ("seek-loot", "town:kill-mob-approach")


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class ShopEntrance1125RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(scratch.name))
        cls.rows = []
        for index, (recorded, supply) in enumerate(steps):
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            here = board.player.position
            offset = OFFSETS.get(key)
            to = None if offset is None else Position(here.y + offset[0], here.x + offset[1])
            entrances = frozenset(policy._town_entrance_cells(board))
            cls.rows.append((index, recorded["key"], recorded["reason"], key,
                             policy.last_reason, here, to, entrances))
            if index == LOOP_ROW:
                with contextlib.redirect_stdout(io.StringIO()):
                    cls.loot_first_step = policy._loot_step(board)
            post(policy, recorded["key"])

    def test_the_recorded_loop_is_in_the_fixture(self):
        index, recorded, reason, *_rest, here, _to, entrances = self.rows[LOOP_ROW]
        self.assertEqual((recorded, reason, here), ("1", "seek-loot", Position(33, 91)))
        self.assertIn(STORE_5, entrances)
        self.assertIn(STORE_4, entrances)
        looped = [row for row in self.rows if row[1] == "1" and row[2] == "seek-loot"
                  and row[5] == Position(33, 91)]
        self.assertGreaterEqual(len(looped), 15)
        self.assertEqual(self.rows[-1][2], "town:blocked:stage-deadline:buy")

    def test_the_hunt_walks_beside_the_merchant_off_the_store(self):
        _index, _recorded, _reason, key, reason, _here, to, _entrances = self.rows[LOOP_ROW]
        self.assertEqual(reason, "town:kill-mob-approach")
        self.assertEqual(to, Position(32, 91), key)

    def test_the_loot_walk_keeps_off_the_store_entrance(self):
        self.assertIsNotNone(self.loot_first_step)
        self.assertNotEqual(self.loot_first_step, STORE_5)

    def test_no_town_walk_steps_onto_an_entrance(self):
        for index, _recorded, _reason, key, reason, _here, to, entrances in self.rows:
            if reason in WALKS and to is not None:
                with self.subTest(row=index):
                    self.assertNotIn(to, entrances, (index, key, reason))


if __name__ == "__main__":
    unittest.main()
