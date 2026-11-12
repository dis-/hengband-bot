"""n1-c life-205's stuck:recall-escape at full HP on an open floor (dungeon 12 49F, 2026-11-12 22:13).

Recorded: tests/fixtures/n1c-205-stuck-recall-1113.jsonl.gz (tests/extract_n1c_205_stuck_recall_1113_fixture.py),
the boards of decisions 5066-5082 and their records.

Live: seek-loot walked to the dead end (18,14), searched it eight times (5074-5081, the
SEARCH_LIMIT) and decision 5082 read Word of Recall ('rg', ``stuck:recall-escape``) at HP
498/498 with nothing in sight, 295 open frontiers and two known down stairs.  The
oscillation branch of ``_decide`` found no explore step there and left the floor because the
engagement retreats' vetoes were non-empty: two cells (38,65) and (53,77), 25 and more cells
away, left by earlier retreats on the floor.  That branch exists for vetoes that enclose the
player (n1-c life-103); these enclosed nothing.  16 of the life's returns on the evening of
11-12 were such ``stuck:recall-escape`` reads at full HP from ``_explore_step#1``.

The live policy's floor state is not recorded.  A policy restarted on the window's first
board replays it; at 5082 its explore memory differs from the live one, so the live outcome
(the explore finds nothing; the dead end is searched out) is set on that board, with the two
vetoes a replay of the whole visit holds there.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import hashlib
import json
from pathlib import Path
import unittest

from hengbot import engagement_avoid_seal
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import SEARCH_LIMIT


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-205-stuck-recall-1113.jsonl.gz"
FIXTURE_SHA256 = "dda624d85b1ef6f6ff2a627433249337d03a71baa553addf152dec2d8c269000"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")
RECALL_TURN = 2023535  # decision 5082
DEAD_END = Position(18, 14)
FAR_VETOES = {Position(38, 65), Position(53, 77)}


class N1c205StuckRecall1113RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.skill = next(row["board"] for row in rows if row["role"] == "skill-knowledge")
        cls.boards = [row["board"] for row in rows if row["role"] == "board"]
        cls.decisions = {row["decision"]["turn"]: row["decision"]
                         for row in rows if row["role"] == "decision"}
        cls.monrace = load_monrace_knowledge(MONRACES)

    def board_at_recall(self, vetoes):
        """The policy replayed up to decision 5082, with the live outcome set on its board."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy.consume_skill_knowledge(self.skill)
        # The window is short of the process's own ~f cycle (the skill list above).
        policy._skill_exp_request_key = lambda snapshot: None
        for board in self.boards[:-1]:
            key = policy.choose_key(parse_snapshot(board, self.monrace))
            if key:
                policy.confirm_key_posted(key)
        snapshot = parse_snapshot(self.boards[-1], self.monrace)
        self.assertEqual(self.boards[-1]["turn"], RECALL_TURN)
        self.assertEqual(snapshot.player.position, DEAD_END)
        policy._engagement_owned_avoid_cells |= vetoes
        policy._engagement_avoid_cells |= vetoes
        policy._search_counts[(DEAD_END.y, DEAD_END.x)] = SEARCH_LIMIT
        policy._explore_step = lambda board: None
        self.assertTrue(policy._is_oscillating())
        return policy, snapshot

    def test_recorded_window(self):
        recorded = self.decisions[RECALL_TURN]
        self.assertEqual((recorded["decision_sequence"], recorded["reason"], recorded["key"]),
                         (5082, "stuck:recall-escape", "rg"))
        searches = [self.decisions[board["turn"]]["reason"] for board in self.boards
                    if self.decisions.get(board["turn"], {}).get("decision_sequence", 0) in range(5074, 5082)]
        self.assertEqual(searches, ["search"] * 8)
        board = self.boards[-1]
        self.assertEqual(board["player"]["hp"], board["player"]["max_hp"])

    def test_far_vetoes_do_not_read_recall(self):
        """5082: the floor goes on (live read Recall)."""
        policy, snapshot = self.board_at_recall(FAR_VETOES)
        self.assertFalse(engagement_avoid_seal.encloses(policy, snapshot))
        key = policy.choose_key(snapshot)
        self.assertNotEqual(policy.last_reason, "stuck:recall-escape")
        self.assertFalse(policy._returning_to_town)
        self.assertNotEqual(key, "rg")

    def test_enclosing_vetoes_still_leave(self):
        """Vetoes on every way out of the dead end are the life-103 enclosure: it still leaves."""
        policy, snapshot = self.board_at_recall(set())
        walls = set(policy._walkable_neighbors(snapshot, DEAD_END))
        self.assertTrue(walls)
        policy._engagement_owned_avoid_cells |= walls
        policy._engagement_avoid_cells |= walls
        self.assertTrue(engagement_avoid_seal.encloses(policy, snapshot))
        policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "stuck:recall-escape")


if __name__ == "__main__":
    unittest.main()
