"""The recall wait walks for loot only as far as the rest of the countdown surely reaches (1117).

Owner 2026-11-17 (the 50F+ efficiency study's 第3位, 「待ちの残りで届く所まで」; recall_wait_reach's
docstring has the game's countdown): the read is dated by the board before it, the least delay is 15
world ticks, and a tick gives ``speed_energy / 10`` actions; one is kept for the pickup.

Recorded (tests/fixtures/deep-efficiency-1117-recall-wait.jsonl.gz, see
tests/extract_deep_efficiency_1117_fixtures.py): n1-c life-216, Glass castle 55F, turns
5663846-5663864: Word of Recall read after the board of turn 5663857; on turn 5663864 the calm wait
stepped toward a pile beside it (``return:seek-loot`` '1').  DECLARED CONSTRUCTED: for the spent
countdown, the read's date set 15 ticks before turn 5663864 (nothing left to walk).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot import recall_wait_reach
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "deep-efficiency-1117-recall-wait.jsonl.gz"
SEEK = 5663864
READ_DECIDED = 5663857


class RecallWaitReachRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, *, spent=False):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        rows = {}
        for raw in self.boards:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if board.turn == SEEK and spent:
                # The observation keeps a dated read while the countdown runs on the floor.
                getattr(policy, recall_wait_reach.STATE)["read"] = (
                    board.floor_key,
                    board.turn - recall_wait_reach.DELAY_MIN_TICKS * recall_wait_reach.TURNS_PER_TICK)
            key = policy.choose_key(board)
            rows[board.turn] = (key, policy.last_reason, board)
            if key:
                policy.confirm_key_posted(key)
        return policy, rows

    def test_the_read_is_dated_by_the_board_before_it(self):
        policy, rows = self.replay()
        self.assertEqual(getattr(policy, recall_wait_reach.STATE)["read"][1], READ_DECIDED)

    def test_a_reachable_pile_is_still_collected(self):
        _policy_, rows = self.replay()
        key, reason, board = rows[SEEK]
        self.assertTrue(board.player.recalling)
        self.assertEqual(reason, "return:seek-loot", key)

    def test_with_the_countdown_spent_the_wait_stands(self):
        _policy_, rows = self.replay(spent=True)
        self.assertEqual(rows[SEEK][1], "return:wait-recall", rows[SEEK][:2])

    def test_the_reach_counts_the_least_delay_at_the_speed(self):
        policy = SimpleNamespace()
        floor = (20, 55, 0)

        def board(turn, speed, recalling=True):
            return SimpleNamespace(turn=turn, floor_key=floor, in_town=False,
                                   player=SimpleNamespace(recalling=recalling, speed=speed))

        recall_wait_reach.observe(policy, board(1000, 110, recalling=False))
        recall_wait_reach.observe(policy, board(1005, 110))
        # +0 speed: 10 energy a game turn, one action a tick; 15 ticks less the one from 1000 to 1010.
        self.assertEqual(recall_wait_reach.remaining_actions(policy, board(1010, 110)), 14)
        self.assertEqual(recall_wait_reach.max_path_distance(policy, board(1010, 110)), 13)
        # +20 speed (energy 30): three actions a tick.
        self.assertEqual(recall_wait_reach.remaining_actions(policy, board(1010, 130)), 42)
        self.assertEqual(recall_wait_reach.max_path_distance(policy, board(1150, 110)), 0)


if __name__ == "__main__":
    unittest.main()
