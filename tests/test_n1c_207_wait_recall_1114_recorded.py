"""n1-c life-207's recall countdown re-entering Home (2026-11-14 05:50, owner-retired-burst).

Recorded: the town-arrival checkpoint of the 05:50:38 visit (build bot-3eef22a25),
journal rows 0-34 and sidecar files (tests/extract_n1c_207_wait_recall_1114_fixture.py),
through the public choose_key; the keys are posted through the production
executor (``_ExecutorInputPort``).

Row 21 began the Home junk sweep (policy_home ``_begin_home_junk_sweep``): the two
Potions of Intelligence on the Home shelf were surplus, Intelligence being at the
character's maximum (consumable_policy.DRINK_AT_ONCE, f3c7369b38).  Row 24 read the
recall (town:recall-to-alt-dungeon) and row 25 stepped off the Home entrance.  The
relief in ``_decide`` runs before the departure's recall guard (ladder_objectives
town:wait-recall), so row 32 walked the sweep back onto the entrance ('1' under the
label town:wait-recall); the page was left for the recall (town:wait-recall-leave)
and the entrance re-entered (shop:travel:await-entry '5'), 40 decisions in 7
seconds, until the supervisor stopped the owner.

The relief now waits while a town recall counts down: the departure keeps the
countdown off the entrance.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.policy import WAIT_KEY, staged_prompt_chain_matches
from support.town_arrival_fixture import load
from tests.support import recorded as executor_harness

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-207-wait-recall-1114"
READ_RECALL_ROW = 24
STEP_ONTO_HOME_ROW = 32
AWAIT_ENTRY_ROW = 34


class N1c207WaitRecall1114RecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def raw(self, row):
        entry = self.recorded[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def confirm(self, key):
        policy = self.policy
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay_to(self, end):
        """Decide rows [0, end) posting the recorded keys; rows from the read on match."""
        for row in range(end):
            board = self.steps[row][1]()
            key = self.policy.choose_key(board)
            recorded = self.recorded[row]
            if row >= READ_RECALL_ROW:
                self.assertEqual((key, self.policy.last_reason),
                                 (recorded["key"], recorded["reason"]), row)
            # Rows 19 and 21 hold the CLI's periodic character dump, which it
            # posts in place of the policy's key (not journalled).
            self.confirm(recorded["key"])

    def test_recall_countdown_stays_off_the_home_entrance(self):
        self.replay_to(STEP_ONTO_HOME_ROW)
        board = self.steps[STEP_ONTO_HOME_ROW][1]()
        self.assertTrue(board.player.recalling)
        self.assertIsNotNone(self.policy._home_full_relief)   # the sweep began at row 21
        entrance = next(grid.position for grid in board.grids.values()
                        if grid.store_number == STORE_HOME)
        self.assertEqual(entrance.distance_to(board.player.position), 1)
        # Recorded: '1' onto the Home entrance under town:wait-recall.
        self.assertEqual((self.recorded[STEP_ONTO_HOME_ROW]["key"],
                          self.recorded[STEP_ONTO_HOME_ROW]["reason"]), ("1", "town:wait-recall"))
        raw = self.raw(STEP_ONTO_HOME_ROW)
        reasons = []
        for _ in range(8):
            key = self.policy.choose_key(board)
            reasons.append((key, self.policy.last_reason))
            self.assertEqual(reasons[-1], (WAIT_KEY, "town:wait-recall"), reasons)
            # DECLARED CONSTRUCTED: the countdown's next board (the wait spends a turn).
            following = self.later(raw)
            self.assertEqual(self.post(self.policy, raw, key, [], following), [key])
            self.confirm(key)
            raw = following
            board = parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge)
            self.assertEqual(board.player.position.distance_to(entrance), 1)

    def test_on_the_entrance_the_countdown_steps_off(self):
        self.replay_to(STEP_ONTO_HOME_ROW)
        # The recorded run: '1' onto the entrance, the page left for the recall.
        for row in (STEP_ONTO_HOME_ROW, STEP_ONTO_HOME_ROW + 1):
            board = self.steps[row][1]()
            key = self.policy.choose_key(board)
            if row == STEP_ONTO_HOME_ROW + 1:
                self.assertEqual((key, self.policy.last_reason),
                                 ("\x1b", "town:wait-recall-leave"))
            self.confirm(self.recorded[row]["key"])
        board = self.steps[AWAIT_ENTRY_ROW][1]()
        here = board.grid_at(board.player.position)
        self.assertEqual((here.store_number, board.player.recalling), (STORE_HOME, True))
        # Recorded: '5' shop:travel:await-entry re-entered Home.
        self.assertEqual((self.recorded[AWAIT_ENTRY_ROW]["key"],
                          self.recorded[AWAIT_ENTRY_ROW]["reason"]),
                         ("5", "shop:travel:await-entry"))
        key = self.policy.choose_key(board)
        self.assertEqual((key, self.policy.last_reason), ("9", "town:wait-recall-step-off"))
        raw = self.raw(AWAIT_ENTRY_ROW)
        self.assertEqual(self.post(self.policy, raw, key, [], self.later(raw)), [key])


if __name__ == "__main__":
    unittest.main()
