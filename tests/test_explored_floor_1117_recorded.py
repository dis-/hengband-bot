"""A floor the dive goes no deeper from is left by Word of Recall once its map stops growing (1117).

Owner 2026-11-17 (the 50F+ efficiency study's 第1位, verbatim 「適当な閾値を決めて、探索が済んだら帰還
する。閾値は任せる。」; explored_floor's docstring has the threshold and its data).  n1-c life-216's
50 visits of Angband 80F and the Castle's 64F that ended by the up stairs took 38% of its 50F+
decisions; their last third added 4% of the map.

Recorded (tests/fixtures/deep-efficiency-1117-explored-floor.jsonl.gz, see
tests/extract_deep_efficiency_1117_fixtures.py): n1-c life-216's Angband 80F, the last 15 boards
(turns 5555750-5555864) of the visit that the record ended by the up stairs, all explore walks; 81F
asks speed +25 the character lacks, so the floor is a dead end.  DECLARED RECONSTRUCTED: the
absorbed *Destruction* list row (22 charges at 95%; the snapshots keep no power list), without
which the 50F+ means-spent return reads Recall first.  DECLARED CONSTRUCTED: the growth
window (explored_floor ``MEMORY``) before the last board, which the 15 boards cannot build: the 300
explore decisions before it seeded at the board's own known-map size (no growth), or at a size 1%
smaller (growth past the threshold).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import explored_floor, me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "deep-efficiency-1117-explored-floor.jsonl.gz"
LAST = 5555864


class ExploredFloorRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, seed_growth=None):
        """The boards in order; before the last one the window is seeded (``seed_growth``: the
        share of the known map the 300 earlier explore decisions added; None: not seeded)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        rows = {}
        for raw in self.boards:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if board.turn == LAST and seed_growth is not None:
                known = len(policy._remembered_marked_t)
                start = int(known * (1 - seed_growth))
                setattr(policy, explored_floor.MEMORY, {
                    "floor": board.floor_key,
                    "counts": (start,) * explored_floor.WINDOW})
            key = policy.choose_key(board)
            rows[board.turn] = (key, policy.last_reason, policy._last_return_trigger, board)
            if key:
                policy.confirm_key_posted(key)
        return policy, rows

    def test_the_record_explores_80f_and_the_floor_is_a_dead_end(self):
        policy, rows = self.replay()
        key, reason, _trigger, board = rows[LAST]
        self.assertEqual(board.floor_key, (1, 80, 0))
        self.assertTrue(explored_floor.dead_end(policy, board))
        self.assertEqual(reason, "explore")
        self.assertFalse(explored_floor.stalled(policy, board))

    def test_a_stalled_window_reads_word_of_recall(self):
        policy, rows = self.replay(seed_growth=0.0)
        key, reason, trigger, _board = rows[LAST]
        self.assertEqual(reason, "return:recall", rows[LAST][:3])
        self.assertEqual(trigger, explored_floor.TRIGGER)
        self.assertTrue(policy._returning_to_town)
        self.assertTrue(key.startswith("r"), key)

    def test_a_window_that_still_grows_explores_on(self):
        _policy_, rows = self.replay(seed_growth=0.01)
        self.assertEqual(rows[LAST][1], "explore", rows[LAST][:3])

    def test_the_threshold_is_the_growth_share_over_the_window(self):
        policy, rows = self.replay()
        board = rows[LAST][3]
        known = 10_000
        for added, stalled in ((49, True), (50, False)):
            setattr(policy, explored_floor.MEMORY, {
                "floor": board.floor_key,
                "counts": (known - added,) + (known,) * explored_floor.WINDOW})
            self.assertEqual(explored_floor.stalled(policy, board), stalled, added)
        setattr(policy, explored_floor.MEMORY, {"floor": board.floor_key,
                                                "counts": (known,) * explored_floor.WINDOW})
        self.assertFalse(explored_floor.stalled(policy, board))


if __name__ == "__main__":
    unittest.main()
