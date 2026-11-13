"""n1-a life-519 stall:floor-dwell:ranged:fire-target (2026-11-13 11:16:57, 11:48:00, 12:41:03).

Lv37 zombie warrior on dungeon 3, 23F (bot-30771c7cc).  An awake 見習戦士 (Novice warrior,
race 110) stood in a wall niche at (17,158) with walls at (17,156), (17,157), (17,159) and
(16,159); the player walked (16,149)-(16,151).  Every third board the bot fired
``fm*t5<Esc>`` (ranged:fire-target) for 1.5 hours; the warrior stayed unhurt, the arrows
dropped along row 16 and the loot walk stepped onto them, which moved the player and reset
the three-miss guard (``_ranged_target_attempts`` is per position).

The game's ``*`` lists only target_able monsters, which needs projectable()
(target-preparation.cpp:34-59, projection-path-calculator.cpp:262-272); the bolt path from
row 16 ends on the wall (17,156), so ``*`` had no target, fell to the free cursor on the
player's grid (the recorded 「ランス (2d8)がある。」) and the shot was spent.  The fallback now
fires only when some hostile in range is projectable over the known map (``_may_project``).

Recorded: the capture's last boards (tests/extract_viewing_stops_1113_fixtures.py boards),
a fresh policy primed on the first of them, decided through the public choose_key; the new
key is posted through the production executor (_ExecutorInputPort).
DECLARED RECONSTRUCTED: the policy is fresh (the capture keeps no checkpoint); the skill
cache as tests.test_n1b_370_anaguma_hold_1111_recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import recorded as executor_harness
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "viewing-stops-1113" / "fire-target-519.json.xz"
NOVICE_WARRIOR = 110
FIRE_TARGET = "ranged:fire-target"


class FireTargetUnprojectableRecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        cls.boards = json.loads(lzma.decompress(FIXTURE.read_bytes()))["boards"]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        self.policy.prime(first)
        self.policy._skill_exp_cache = (0, 0, first.player.level, self.policy._town_visit_epoch)

    def test_the_niche_warrior_is_in_sight_but_not_projectable(self):
        board = parse_snapshot(copy.deepcopy(self.boards[-1]), self.monrace)
        warrior = next(m for m in board.visible_monsters if m.race_id == NOVICE_WARRIOR)
        self.assertEqual(warrior.position, Position(17, 158))
        self.assertFalse(warrior.asleep)
        self.assertFalse(self.policy._may_project(board, board.player.position, warrior.position))

    def test_no_board_fires_the_target_macro_at_nothing(self):
        for raw in self.boards:
            board = parse_snapshot(copy.deepcopy(raw), self.monrace)
            key = self.policy.choose_key(board)
            self.assertNotEqual(self.policy.last_reason, FIRE_TARGET, (board.turn, key))
            self.assertNotIn("*t", key or "")
            if key:
                self.policy.confirm_key_posted(key)

    def test_the_last_board_key_goes_through_the_executor(self):
        for raw in self.boards[:-1]:
            key = self.policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if key:
                self.policy.confirm_key_posted(key)
        raw = copy.deepcopy(self.boards[-1])
        key = self.policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
        self.assertNotEqual(self.policy.last_reason, FIRE_TARGET)
        self.assertTrue(key and len(key) == 1 and key in "12346789", (key, self.policy.last_reason))
        # DECLARED CONSTRUCTED: the board after the step.
        self.assertEqual(self.post(self.policy, raw, key, [], self.later(raw)), [key])


if __name__ == "__main__":
    unittest.main()
