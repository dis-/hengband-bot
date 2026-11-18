"""In Zul a '<' refused for an unseen monster walks out of its range (n1-c life-217).

n1-c life-217 (Magic-Eater Lv35) walked from the Outpost to Zul for its mutation (owner
2026-11-07, zul_trip), had it cured at the Chaos Tower and pressed '<' for the global map at
night.  The game refused it (「敵がすぐ近くにいるときは広域マップに入れない！」, change_wild_mode:
an awake hostile within MAX_PLAYER_SIGHT, seen or not) with nothing in view or sensed.

- First stop (2026-11-19 01:14:29, build bot-febdf2f35): the trip left the refused board to the
  other owners; the Magic-Eater staff sequence's leg back to the Outpost is an inn teleport and
  Zul has no inn: quest:blocked:me-staff ``return-outpost-unavailable``.
- Second stop (01:49:49, build bot-b94db342c, after the first fix waited a turn between the
  tries): the restarted bot was refused nine times at (20,68); the monster did not move, the
  waits ran out and the same leg stopped it again.

Fix: zul_trip ``_out_of_range_key`` walks (levitating, as the Tower walk does) to the nearest
cell twice MAX_PLAYER_SIGHT from where '<' was refused, out of range of whatever refused it,
and presses '<' there; me_staff_sequence ``_travel`` no longer owns a board in a town without
an inn (its leg has no route there).

Recorded (tests/extract_n1c_217_zul_refused_1119_fixture.py):
- n1c-217-zul-unseen-1119: the restart's town-arrival checkpoint in Zul and its 25 journal rows
  up to the second stop, decided through the public choose_key.  The recorded boards after the
  first refusal stand still (the recorded bot did not walk), so only the decisions' kind is
  compared after it.
- n1c-217-zul-refused-1119: the first stop board, on the Outpost arrival's policy.
  DECLARED RECONSTRUCTED: the Zul trip's state is the stop's (policy-state.json ``_zul_trip``).
DECLARED CONSTRUCTED: the first stop board with the player moved to the walk's goal.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_staff_sequence, zul_trip
from hengbot.model import parse_snapshot
from hengbot.policy_constants import UP_STAIRS_KEY, ZUL_TOWN_ID
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
RESTART = FIXTURES / "n1c-217-zul-unseen-1119"
FIRST = FIXTURES / "n1c-217-zul-refused-1119"
REFUSED = "敵がすぐ近くにいるときは広域マップに入れない！"
FIRST_REFUSAL_ROW = 7


class RestartReplayTest(unittest.TestCase):
    """The second stop's restart: the refusal walks away, and nothing stops the bot."""

    def test_the_restart_walks_out_of_range_instead_of_stopping(self):
        with TemporaryDirectory(prefix="n1c-217-restart-") as scratch:
            policy, _journal, rows = load(RESTART, Path(scratch))
            decided = []
            for recorded, supply in rows:
                board = supply()
                decided.append((board, policy.choose_key(board), policy.last_reason, recorded))
                policy.confirm_key_posted(recorded["key"])
        # Recorded: the last row was the stop.
        self.assertEqual((decided[-1][3]["key"], decided[-1][3]["reason"]),
                         ("", me_staff_sequence.STOP_REASON))
        board, key, reason, recorded = decided[FIRST_REFUSAL_ROW]
        self.assertEqual(board.messages, (REFUSED,))
        self.assertEqual(recorded["reason"], "town:entrance-step-off:town:zul:wait-refused")
        self.assertEqual(reason, zul_trip.LEAVE_RANGE_REASON)
        self.assertTrue(key)
        self.assertNotIn(me_staff_sequence.STOP_REASON,
                         [reason for _board, _key, reason, _recorded in decided])


class FirstStopBoardTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory(prefix="n1c-217-zul-")
        self.addCleanup(scratch.cleanup)
        self.policy, _journal, rows = load(FIRST, Path(scratch.name))
        for recorded, supply in rows:
            self.policy.choose_key(supply())
            self.policy.confirm_key_posted(recorded["key"])
        self.raw = json.loads(lzma.decompress((FIRST / "stop-board.json.xz").read_bytes()))
        # The stop's trip (policy-state.json ``_zul_trip``).
        self.policy._zul_trip = zul_trip.ZulTrip(
            active=True, start_town=3, curable=(33,), price=5000, cured=1, returning=True)

    def decide(self, raw):
        board = self.policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge))
        return board, self.policy.choose_key(board), self.policy.last_reason

    def goal(self, board):
        record = zul_trip.state(self.policy)
        return zul_trip._flying_step(
            self.policy, board, lambda cell: not zul_trip._within_unseen_range(cell, record))[1]

    def test_the_refused_board_walks_toward_a_cell_out_of_range(self):
        board, key, reason = self.decide(self.raw)
        self.assertEqual(self.policy._effective_town_id(board), ZUL_TOWN_ID)
        self.assertEqual(board.messages, (REFUSED,))
        self.assertEqual((list(board.visible_monsters), list(board.detected_monsters)), ([], []))
        # Before: ('', 'quest:blocked:me-staff'), failure return-outpost-unavailable.
        self.assertEqual(reason, zul_trip.LEAVE_RANGE_REASON)
        self.assertTrue(key)
        self.assertEqual(zul_trip.state(self.policy).refused_at, board.player.position)
        goal = self.goal(board)
        self.assertFalse(zul_trip._within_unseen_range(goal, zul_trip.state(self.policy)))

    def test_the_walk_goes_on_without_pressing_on_the_way(self):
        board, _key, _reason = self.decide(self.raw)
        quiet = copy.deepcopy(self.raw)
        quiet["messages"] = []
        _board, key, reason = self.decide(quiet)
        self.assertEqual(reason, zul_trip.LEAVE_RANGE_REASON)
        self.assertNotEqual(key, UP_STAIRS_KEY)

    def test_at_the_goal_the_global_map_is_tried_again(self):
        board, _key, _reason = self.decide(self.raw)
        goal = self.goal(board)
        there = copy.deepcopy(self.raw)
        there["messages"] = []
        there["player"]["y"], there["player"]["x"] = goal.y, goal.x
        _board, key, reason = self.decide(there)
        self.assertEqual((key, reason), (UP_STAIRS_KEY, zul_trip.ENTER_GLOBAL_REASON))
        self.assertIsNone(zul_trip.state(self.policy).refused_at)

    def test_the_staff_sequence_leg_does_not_own_a_town_without_an_inn(self):
        board = self.policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(self.raw), self.policy._monrace_knowledge))
        self.assertIsNone(me_staff_sequence._travel(self.policy, board, 0, "return-outpost"))
        self.assertIsNone(me_staff_sequence.state(self.policy).failure)


if __name__ == "__main__":
    unittest.main()
