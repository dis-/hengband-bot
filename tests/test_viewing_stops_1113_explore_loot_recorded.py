"""n1-c life-205 stall:floor-dwell:explore (2026-11-13 09:15:54, dungeon 3, 23F, bot-30771c7cc).

Lv45 Magic-Eater.  The floor's items at (39,84), (40,75), (40,86), (40,88), (40,90) and
(41,75) lay in a room floored with known traps; the loot walk, which never routes over a
known trap, found no way to them on every board and noted them for the explore
(loot_frontier, owner 2026-11-13 「その品の方へ探索を寄せる」, merged 07:25).  From then on each
new explore goal was the reachable frontier nearest those items, wherever the player
stood: from 09:02 the player crossed the 190-column floor every 30 seconds between
x~40 and x~135 (the corridor (43,84)-(43,98) passed 51 times) until the floor-dwell guard.

Exploring cannot open a way that known traps close.  The steer now keeps only items whose
own walkable area reaches a remembered frontier (an unknown grid may still join it).

Recorded: the capture's last 40 boards (tests/extract_viewing_stops_1113_fixtures.py
boards ... explore-loot-205 40), a fresh policy primed on the first, decided through the
public choose_key; the last step is posted through the production executor.
DECLARED RECONSTRUCTED: the policy is fresh (no checkpoint for this stop); the skill
cache as tests.test_n1b_370_anaguma_hold_1111_recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import loot_frontier
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import recorded as executor_harness
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "viewing-stops-1113" / "explore-loot-205.json.xz"
TRAP_ROOM_LOOT = {Position(39, 84), Position(40, 75), Position(40, 86), Position(40, 88),
                  Position(40, 90), Position(41, 75)}


class ExploreTrapLootRecordedTest(executor_harness.RecordedHarness):
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

    def decide_all(self):
        key = None
        for raw in self.boards:
            board = parse_snapshot(copy.deepcopy(raw), self.monrace)
            key = self.policy.choose_key(board)
            if key:
                self.policy.confirm_key_posted(key)
        return board, key

    def test_the_trap_room_loot_is_noted_and_does_not_steer(self):
        board, _key = self.decide_all()
        note = getattr(self.policy, loot_frontier.NOTE)
        self.assertEqual(set(note[2]), TRAP_ROOM_LOOT)
        self.assertGreaterEqual(note[3], loot_frontier.STEER_AFTER_BOARDS)
        self.assertEqual(loot_frontier.explore_path(self.policy, board, frozenset()), [])

    def test_the_last_board_explores_through_the_executor(self):
        for raw in self.boards[:-1]:
            key = self.policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if key:
                self.policy.confirm_key_posted(key)
        raw = copy.deepcopy(self.boards[-1])
        key = self.policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
        self.assertEqual(self.policy.last_reason, "explore")
        self.assertTrue(key and len(key) == 1 and key in "12346789", key)
        # DECLARED CONSTRUCTED: the board after the step.
        self.assertEqual(self.post(self.policy, raw, key, [], self.later(raw)), [key])


if __name__ == "__main__":
    unittest.main()
