"""n1-a life-521's Q2 without its breach tool (2026-11-14 03:18, quest:blocked:q2-breach-tool).

Recorded: the town-arrival checkpoint of the 03:18:11 visit, journal rows
0-42 and sidecar files (tests/extract_n1a_521_breach_tool_1114_fixture.py),
through the public choose_key; the row-42 key is posted through the
production executor (``_ExecutorInputPort``).

The Lv25 character carried the Dwarven Shovel (+6 digging) and a Stone to Mud
wand of one charge.  Before row 41 the untaken Q2's wall_breach carry kept
the shovel (spare_gear.digger_needed).  Row 41 took Q2; the procurement plan
reads only untaken heads at Lv10+, so the carry went empty, the shovel became
spare gear, and row 42 walked Home and shelved it.  In Q2 the one charge
opened [7,47] and [8,47] stayed a wall: three stops at [7,47].

The breach count now reads the retention's plan
(item_use_route.prepared_strategy), which keeps a taken quest's carry until
its entrance: row 42 walks to the quest entrance with the shovel.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import spare_gear
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from support.town_arrival_fixture import load
from tests.support import recorded as executor_harness

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-521-breach-tool-1114"
TAKE_Q2_ROW = 41
SHELVE_ROW = 42


class N1a521BreachTool1114RecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def decide(self, row):
        board = self.steps[row][1]()
        return board, self.policy.choose_key(board), self.policy.last_reason

    def confirm(self, key):
        policy = self.policy
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    @staticmethod
    def shovel(board):
        return next(item for item in board.inventory if item.is_digging_tool)

    def test_taken_q2_keeps_the_shovel_to_its_entrance(self):
        self.assertEqual(
            [(self.recorded[row]["key"], self.recorded[row]["reason"])
             for row in (TAKE_Q2_ROW, SHELVE_ROW)],
            [("7q\x1b", "fixedquest:request"),
             ("\x1b`n(.", "equipment-transaction:travel-home")])
        for row in range(SHELVE_ROW):
            board, key, reason = self.decide(row)
            if row < TAKE_Q2_ROW:
                # The untaken Q2's carry keeps the shovel before and after.
                self.assertTrue(spare_gear.digger_stays_carried(
                    self.policy, board, self.shovel(board)), row)
            self.assertEqual((key, reason),
                             (self.recorded[row]["key"], self.recorded[row]["reason"]), row)
            self.confirm(key)

        board, key, reason = self.decide(SHELVE_ROW)
        quest = board.quests[2]
        self.assertEqual(quest.status, QUEST_STATUS_TAKEN)
        self.assertIn("シャベル", self.shovel(board).name)
        # Recorded: equipment-transaction:travel-home, then 'dm' shelved it.
        self.assertTrue(spare_gear.digger_stays_carried(self.policy, board, self.shovel(board)))
        self.assertEqual((key, reason), ("2", "quest:enter:approach"))
        # DECLARED CONSTRUCTED: the game's town map after the step.
        raw = {"turn": board.turn, "grid_map": {"runs": []}}
        self.assertEqual(self.post(self.policy, raw, key, [], self.later(raw)), ["2"])


if __name__ == "__main__":
    unittest.main()
