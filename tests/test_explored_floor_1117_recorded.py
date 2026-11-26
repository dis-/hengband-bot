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
smaller (growth past the threshold; the window counts the cells the map has shown since 1118,
explored_floor ``note_explore``); for the cut itself, the last board's found items dropped (the
board shows detected items on unmapped ground, which the loot memory keeps since detected_loot and
which held the cut until n1-c life-217, 1120: no walk reaches them).  DECLARED CONSTRUCTED (1126):
the trip has left its ``deep_stairs.EXTRA_FLOORS`` explored floors by the stairs already, so the
cut reads Word of Recall (owner 2026-11-26: before that the floor is left by its stairs,
tests/test_deep_stairs_1126.py).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import deep_stairs, explored_floor, me_capability, sealed_loot
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

    def replay(self, seed_growth=None, *, no_loot=False):
        """The boards in order; before the last one the window is seeded (``seed_growth``: the
        share of the known map the 300 earlier explore decisions added; None: not seeded), and
        with ``no_loot`` its found items are dropped."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        setattr(policy, deep_stairs.FLOORS, deep_stairs.EXTRA_FLOORS)  # DECLARED CONSTRUCTED
        rows = {}
        for raw in self.boards:
            if raw["turn"] == LAST and no_loot:
                raw = copy.deepcopy(raw)
                for field in ("found_items", "found_item_names", "found_item_ids"):
                    raw["grid_map"][field] = []
                policy._known_loot.clear()
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if board.turn == LAST and seed_growth is not None:
                known = len(policy._remembered_known_t)
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

    def test_unreachable_remembered_loot_no_longer_holds_a_stalled_window(self):
        """The board's detected items (detected_loot) lie on unmapped ground no walk reaches.  They
        held the stalled window (owner 2026-11-13 「その品の方へ探索を寄せる」) until n1-c life-217
        (Angband 95F, 2026-11-20) explored a cave for half an hour toward such a helm with the map
        no longer growing.  Owner 2026-11-18 on loot whose surroundings the map does not know:
        「周辺感知があれば使用して入口を探す。なければ諦める。」 -- sealed_loot is asked first (no
        mapping means carried here), then Word of Recall is read."""
        policy, rows = self.replay(seed_growth=0.0)
        board = rows[LAST][3]
        candidates = policy._loot_candidates(board)
        self.assertTrue(candidates)
        self.assertFalse(candidates & sealed_loot.reach(policy, board))
        self.assertEqual(rows[LAST][1], explored_floor.REASON, rows[LAST][:3])
        self.assertEqual(rows[LAST][2], explored_floor.TRIGGER)

    def test_a_stalled_window_reads_word_of_recall(self):
        policy, rows = self.replay(seed_growth=0.0, no_loot=True)
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
