"""A sleeper in view no longer withholds a survivable fetch before a *Destruction* (1118, 1128).

Recorded (tests/fixtures/n1c-216-dloot-inview-1118.jsonl.gz: the life's state.jsonl
~/hengbot-soak/n1-c/life-216/state.jsonl, turns 6228591-6228734, beside the capture
~/hengbot-soak/n1-c/life-216/captures/20261118-031230-loop-detected/; the capture's 49 boards
start too late for the remembered grids the fetch's route crosses): Angband 80F, build 1df9764b9,
the Magic-Eater Lv50.  The sensed-T1 approach walked west toward the T1s around (31,61)-(29,62);
at (26,74) the use was due and destruction_loot fetched toward the potion at (39,80) by (27,75),
(26,76), (25,77); at (25,77) a sleeping hostile (index 106, race 423) at (5,76) came into view,
the fetch dropped (owner 2026-11-17: pick up first only 「見える敵がいなければ」), and the approach
stepped back out of its sight by (26,76), (27,75) to (26,74), where the use was due again and the
fetch began afresh: until the loop detector (03:12:30).  From 2026-11-18 the sighting withheld the
fetch until the flash.  Supervisor 2026-11-28 (destruction_loot ``survivable``): a hostile in view
withholds it only when the awake hostiles' predicted damage over the walk is not survivable; the
sleeper withholds nothing, so the fetch goes on past (25,77) and the approach never takes the
board back (no loop).  The latch for a walk that is not survivable is tested in
tests/test_loot_before_destruction_1128_recorded.py (``test_b``).  DECLARED RECONSTRUCTED: the
absorbed *Destruction* list row (22 charges at 95%; the life's power_list records are skipped).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-dloot-inview-1118.jsonl.gz"
FETCH_BEGINS = 6228718   # (26,74): the use due, the fetch '3'
SIGHTED = 6228727        # (25,77): the sleeper in view, recorded approach '1'
DUE_AGAIN = 6228734      # (26,74): recorded destruction-loot:fetch '3' (the fetch afresh)
SLEEPER = 106


class DestructionLootInViewWithheldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.answers = cls.replay()

    @classmethod
    def replay(cls):
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), cls.monrace)
            first = parse_snapshot(copy.deepcopy(cls.boards[0]), cls.monrace)
            policy.prime(first)
            policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
            policy._me_device_lists = {"staff": (first.turn, ({
                "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
                "max": 22, "fail": 5, "success": 95},))}
            answers = {}
            for raw in cls.boards:
                board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), cls.monrace))
                key = policy.choose_key(board)
                answers[board.turn] = (board, key, policy.last_reason)
                if key:
                    policy.confirm_key_posted(key)
            return answers

    def test_the_fetch_begins_where_the_use_is_due(self):
        board, key, reason = self.answers[FETCH_BEGINS]
        self.assertEqual(board.player.position, Position(26, 74))
        self.assertEqual((key, reason), ("3", "destruction-loot:fetch"))

    def test_the_sleeper_in_view_does_not_end_the_fetch(self):
        board, key, reason = self.answers[SIGHTED]
        self.assertEqual(board.player.position, Position(25, 77))
        self.assertIn(SLEEPER, {monster.index for monster in board.visible_monsters})
        # Recorded: ('1', 'sensed-t1:approach-destruction'): the fetch dropped, the loop.
        self.assertEqual(reason, "destruction-loot:fetch")

    def test_out_of_its_sight_the_fetch_goes_on(self):
        board, key, reason = self.answers[DUE_AGAIN]
        self.assertEqual(board.player.position, Position(26, 74))
        self.assertNotIn(SLEEPER, {monster.index for monster in board.visible_monsters})
        # The fetch that never dropped goes on (no withheld latch: the walk was survivable).
        self.assertEqual(reason, "destruction-loot:fetch")

if __name__ == "__main__":
    unittest.main()
