"""Replay the fundraising exit board and pin its no-escape frontier route.

The captured board itself carries Recall and Teleport scrolls. The no-escape
variant and the at-player staircase control below are DECLARED CONSTRUCTED.
"""

from __future__ import annotations

import tests  # noqa: F401

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT, UP_STAIRS_KEY


FIXTURE = Path(__file__).parent / "fixtures" / "fundraise-upstairs-20261017.jsonl.gz"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")


class FundraiseUpstairsExploreReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.raw = json.loads(next(stream))
        cls.knowledge = load_monrace_knowledge(MONRACES)
        cls.captured = parse_snapshot(cls.raw, cls.knowledge)

    def policy_for_expired_exit(self, snapshot):
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy._fundraising_mode = "mine"
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        policy._build_grid_index(snapshot)
        return policy

    def test_captured_board_explores_when_escape_scrolls_are_absent(self):
        self.assertEqual(self.captured.turn, 211771)
        self.assertEqual(self.captured.player.position, Position(19, 4))
        self.assertEqual(self.captured.floor_key, (2, 1, 0))

        # DECLARED CONSTRUCTED: preserve the captured board and remove only its
        # carried Recall and Teleport stacks to model the reported no-escape case.
        no_escape = replace(
            self.captured,
            inventory=[
                item for item in self.captured.inventory
                if not (item.is_recall_scroll or item.is_teleport_scroll)
            ],
        )
        policy = self.policy_for_expired_exit(no_escape)
        self.assertIsNone(policy._find_recall_scroll(no_escape))
        self.assertIsNone(policy._escape_scroll(no_escape))
        self.assertEqual(
            sorted((pos.y, pos.x) for pos in policy._remembered_upstairs),
            [(19, 81)],
        )
        self.assertIsNone(
            policy._nearest_goal_step(no_escape, policy._is_upstairs_target)
        )

        key = policy._leave_fundraising_floor(no_escape)

        self.assertEqual(key, "9")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs-explore")

    def test_carried_recall_still_precedes_frontier_exploration(self):
        policy = self.policy_for_expired_exit(self.captured)
        self.assertEqual(policy._find_recall_scroll(self.captured).count, 8)

        key = policy._leave_fundraising_floor(self.captured)

        self.assertEqual(key, "rc")
        self.assertEqual(policy.last_reason, "fundraise:recall-stuck")

    def test_current_up_stair_is_taken_directly(self):
        position = self.captured.player.position
        grids = dict(self.captured.grids)
        grids[position] = replace(grids[position], has_up_stairs=True)
        # DECLARED CONSTRUCTED: the captured position is marked as the known stair.
        board = replace(self.captured, grids=grids)
        policy = self.policy_for_expired_exit(board)

        key = policy._leave_fundraising_floor(board)

        self.assertEqual(key, UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "fundraise:ascend")


if __name__ == "__main__":
    unittest.main()
