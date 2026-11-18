"""The ordinary loot walk is not taken over by a beginning *Destruction* fetch, and the fetch's
bound counts each decision once (1119).

Owner 2026-11-18 (maintainability Q3, 「命の危険が無ければ取り終える」): 「取りに歩き始めたら、命の
危険（即死の見込み・見える強敵）が出ない限り、取り終えるまでほかの歩きに譲らない。今の回数の上限
（40回）は残す。」 (loot_walk).

n1-b life-397 (Magic-Eater Lv50, Angband 79F, 2026-11-15 10:47), the visit of
tests/test_n1b_397_deep_stuck_1115_recorded.py, its fixture and replay set-up (the absorbed
power lists, the descent deferral, the live Teleport Away's board).  The live build of
2026-11-15 had no destruction_loot (owner 2026-11-17) and explored here; the "before" below is
this replay on main 05cacb582 (the first Q3 commit):

- seek-loot walked toward the pile at (49,67) from 5734202 on (the sensed T1's approach
  between); on 5734210 at (43,73) the use was due and destruction_loot's fetch began toward
  another pile (before: '1', destruction-loot:fetch).  Now the ordinary walk goes on ('1',
  seek-loot, loot_walk ``fetch_yield_key``), and on 5734213 again.
- The fetch's bound: destruction_loot ``key`` counted a continued fetch's step in
  ``continue_fetch`` and again at its end, so the 21 fetch boards from 5734210 to 5734299 read
  41 decisions and the use was made on 5734305 (before: 'mA3',
  emergency:destruction:absorbed-power) at about half the owner's 40.  Now 21 boards are 21
  decisions and the fetch goes on.  DECLARED CONSTRUCTED for this one: the hold of the first
  point taken out (``fetch_yield_key`` None), so the window replays as before up to 5734305.

Only the first changed decision of each is examined: from there the recorded boards follow the
live run, not the keys the replay sends.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from contextlib import nullcontext
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import destruction_loot, destruction_use, loot_walk
from hengbot.model import Position, parse_snapshot
from tests import test_n1b_397_deep_stuck_1115_recorded as deep
from tests.test_me_device_attacks import power_list, row

WALK_TAKEN_OVER = 5734210   # before: '1' destruction-loot:fetch at (43,73)
NEXT_BOARD = 5734213        # before: '3' destruction-loot:fetch at (42,72)
LAST_FETCH = 5734299        # before: '6' destruction-loot:fetch, the 21st fetch board
USE_AT_HALF = 5734305       # before: 'mA3' emergency:destruction:absorbed-power at (33,62)
WALK_TARGET = Position(49, 67)


def _window(until, *, hold=True):
    """The visit replayed up to ``until``: (policy, {turn: (key, reason)})."""
    directory = TemporaryDirectory()
    boards = copy.deepcopy(deep.BOARDS)
    policy = deep._policy(Path(directory.name), deep.MONRACE)
    first = parse_snapshot(copy.deepcopy(boards[0]), deep.MONRACE)
    policy.prime(first)
    policy.consume_skill_knowledge({**deep.SKILL, "player": {"level": first.player.level}})
    deep._listed(policy, boards[0], boards[0]["turn"] - 2, power_list(
        "staff", row("*破壊*", 5, current=6, count=9), row("周辺感知", 5, current=3, count=3),
        row("ドア/階段感知", 5, current=3, count=3)))
    deep._listed(policy, boards[0], boards[0]["turn"] - 1, power_list(
        "rod", row("テレポート・アウェイ", 5, charging=False, count=1)))
    policy._defer_descent(first)
    answers, previous = {}, None
    unheld = (nullcontext() if hold else mock.patch.object(
        loot_walk, "fetch_yield_key", lambda policy, snapshot: None, create=True))
    with unheld:
        for raw in boards:
            raw = copy.deepcopy(raw)
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            board = policy.with_known_skill_exp(parse_snapshot(raw, deep.MONRACE))
            if raw["turn"] == deep.SENT_AWAY_TURN - 4:
                destruction_use._memory(policy).fallback = board.floor_key
            key = policy.choose_key(board)
            previous = policy.last_reason
            answers[raw["turn"]] = (key, previous)
            if raw["turn"] == until:
                directory.cleanup()
                return policy, answers
            if key:
                policy.confirm_key_posted(key)
    raise AssertionError(f"turn {until} not in the window")


def _decisions(policy):
    return getattr(policy, destruction_loot.MEMORY)["decisions"]


class LootWalkHeldTest(unittest.TestCase):
    def test_the_walk_to_the_pile_is_not_taken_over(self):
        policy, answers = _window(NEXT_BOARD)
        self.assertEqual(answers[WALK_TAKEN_OVER], ("1", "seek-loot"))
        self.assertEqual(answers[NEXT_BOARD], ("3", "seek-loot"))
        self.assertEqual(policy._loot_target, WALK_TARGET)
        self.assertIsNone(getattr(policy, destruction_loot.MEMORY)["fetch"])
        # The hold is counted in the scene's bound: the use is not held back for good.
        self.assertEqual(_decisions(policy), 2)

    def test_life_danger_ends_the_hold(self):
        """DECLARED CONSTRUCTED: ``life_danger`` read on the boards from 5734210 on."""
        real = loot_walk.life_danger
        with mock.patch.object(loot_walk, "life_danger", lambda policy, snapshot: (
                snapshot.turn >= WALK_TAKEN_OVER or real(policy, snapshot))):
            policy, answers = _window(WALK_TAKEN_OVER)
        self.assertEqual(answers[WALK_TAKEN_OVER][1], "destruction-loot:fetch")
        self.assertIsNone(getattr(policy, loot_walk.MEMORY))


class FetchBoundTest(unittest.TestCase):
    def test_each_fetch_board_is_one_decision(self):
        policy, answers = _window(LAST_FETCH, hold=False)
        fetch_boards = [turn for turn, (_key, reason) in answers.items()
                        if WALK_TAKEN_OVER <= turn <= LAST_FETCH]
        self.assertEqual(len(fetch_boards), 21)
        self.assertTrue(all(answers[turn][1] == "destruction-loot:fetch" for turn in fetch_boards))
        self.assertEqual(_decisions(policy), 21)

    def test_the_fetch_is_not_cut_at_half_the_bound(self):
        policy, answers = _window(USE_AT_HALF, hold=False)
        self.assertEqual(answers[USE_AT_HALF][1], "destruction-loot:fetch")
        self.assertEqual(_decisions(policy), 22)
        self.assertLess(_decisions(policy), destruction_loot.DECISIONS_MAX)


if __name__ == "__main__":
    unittest.main()
