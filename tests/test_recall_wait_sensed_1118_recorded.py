"""The recall wait collects loot when no hostile is in view, whatever telepathy senses (1118).

Owner 2026-11-18 (「見える敵がいなければ拾う」): 「テレパシーで感じている敵だけの敵は数えない。見える敵が
いず、HP が低くなければ、待ちの残りで届く品を拾う。見える敵が出たら今のとおりすぐやめる。」  The gate is
policy ``_loot_before_recall_calm``; the reach stays recall_wait_reach's (owner 2026-11-17).  Measured
before (C:/hengband-backups/pdca/deep-efficiency-after-1118/REPORT.md 4): 362 wait decisions with no
hostile in view, zero threat and an item within 5 cells were refused, every one for a hostile known
only by telepathy; ``return:seek-loot`` fired once in 2.7 hours x 2 characters.

Recorded (see tests/extract_recall_wait_sensed_1118_fixtures.py), n1-c life-216, both read and
countdown boards as live:
  detected: Angband 80F, Word of Recall read after the board of turn 6224305; on 6224308 nothing
            hostile in view, one hostile sensed, HP 996/996, items 4 cells away.  Live waited the
            whole countdown ('5' return:wait-recall); now it walks to the items.
  visible:  60F, read after 6108483; on 6108486 three hostiles in view, items 4 cells away: it still
            waits.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import recall_wait_reach
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
SENSED = (FIXTURES / "recall-wait-sensed-1118-detected.jsonl.gz", 6224305, 6224308)
VISIBLE = (FIXTURES / "recall-wait-sensed-1118-visible.jsonl.gz", 6108483, 6108486)


class RecallWaitSensed1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, fixture, until):
        with gzip.open(fixture, "rt", encoding="utf-8") as stream:
            boards = [json.loads(line) for line in stream if line.strip()]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for raw in boards:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if board.turn == until:
                return policy, board
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError(f"turn {until} not in {fixture.name}")

    def test_a_hostile_only_sensed_no_longer_holds_the_wait(self):
        fixture, read, wait = SENSED
        policy, board = self.replay(fixture, wait)
        self.assertTrue(board.player.recalling)
        self.assertEqual([m for m in board.visible_monsters if m.hostile], [])
        self.assertTrue([m for m in board.detected_monsters if m.hostile])
        self.assertTrue(policy._loot_before_recall_calm(board))

        key = policy.choose_key(board)

        self.assertEqual(policy.last_reason, "return:seek-loot", key)
        # The read is dated by the board before the countdown, and the items 4 cells away are
        # within what the rest of it surely reaches (the 2026-11-17 bound is unchanged).
        self.assertEqual(getattr(policy, recall_wait_reach.STATE)["read"][1], read)
        self.assertGreaterEqual(recall_wait_reach.max_path_distance(policy, board), 4)

    def test_a_hostile_in_view_still_holds_the_wait(self):
        fixture, _read, wait = VISIBLE
        policy, board = self.replay(fixture, wait)
        self.assertTrue(board.player.recalling)
        self.assertTrue([m for m in board.visible_monsters if m.hostile])
        self.assertFalse(policy._loot_before_recall_calm(board))

        key = policy.choose_key(board)

        self.assertEqual((policy.last_reason, key), ("return:wait-recall", "5"))


if __name__ == "__main__":
    unittest.main()
